"""Cycle-level SOH and RUL models with strict cell-level isolation."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

from src.evaluation.nasa_loco import LocoFold, assert_no_fold_leakage
from src.training.train_multistate_lstm import metric_summary
from src.training.battery_protocol import acceptance


FEATURES = (
    "cycle_index", "cumulative_throughput_ah", "soh_history_mean", "capacity_drop_ah",
    "capacity_slope_3", "voltage_mean_v", "voltage_std_v", "temperature_mean_c", "temperature_max_c",
    "discharge_duration_s",
)
TARGETS = ("soh", "rul_cycles")
UNITS = {"soh": "fraction", "rul_cycles": "cycles"}
CANDIDATES = ({"max_leaf_nodes": 3, "l2_regularization": 1.0}, {"max_leaf_nodes": 7, "l2_regularization": 2.0})


class RulTrajectoryEstimator:
    """Project causal SOH history to the EOL threshold without label-range clipping."""

    def __init__(self, eol_soh: float = 0.70) -> None:
        self.eol_soh = float(eol_soh)
        self.slope_bounds: tuple[float, float] | None = None
        self.prior_slope: float | None = None

    @staticmethod
    def _slope(rows: list[dict[str, object]]) -> float:
        x = np.asarray([float(row["cycle_index"]) for row in rows], dtype=float)
        y = np.asarray([float(row["soh"]) for row in rows], dtype=float)
        if len(x) < 2 or np.ptp(x) <= 0:
            return 0.0
        return float(np.polyfit(x, y, 1)[0])

    def fit(self, rows: list[dict[str, object]]) -> "RulTrajectoryEstimator":
        by_cell: dict[str, list[dict[str, object]]] = {}
        for row in rows:
            by_cell.setdefault(str(row["cell_id"]), []).append(row)
        slopes = [self._slope(sorted(cell_rows, key=lambda row: float(row["cycle_index"]))) for cell_rows in by_cell.values()]
        negative = np.asarray([slope for slope in slopes if slope < -1e-9], dtype=float)
        if negative.size == 0:
            raise ValueError("RUL trajectory training requires at least one degrading cell.")
        self.slope_bounds = (float(np.percentile(negative, 10)), float(np.percentile(negative, 90)))
        self.prior_slope = float(np.median(negative))
        return self

    def predict(self, rows: list[dict[str, object]]) -> list[dict[str, float | bool]]:
        if self.slope_bounds is None or self.prior_slope is None:
            raise ValueError("RUL trajectory estimator must be fitted before prediction.")
        history: dict[str, list[dict[str, object]]] = {}
        output: list[dict[str, float | bool]] = []
        for row in rows:
            cell_rows = history.setdefault(str(row["cell_id"]), [])
            cell_rows.append(row)
            local_slope = self._slope(cell_rows)
            fallback = len(cell_rows) < 3 or local_slope >= -1e-9
            slope = self.prior_slope if fallback else float(np.clip(local_slope, *self.slope_bounds))
            remaining = max((float(row["soh"]) - self.eol_soh) / -slope, 0.0)
            output.append({"rul_cycles": float(remaining), "slope_used": slope, "used_prior_fallback": fallback})
        return output


def _load_rows(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with Path(path).open(encoding="utf-8", newline="") as handle:
        for raw in csv.DictReader(handle):
            row: dict[str, object] = {"cell_id": raw["cell_id"], "cycle_id": int(raw["cycle_id"])}
            for field in (*FEATURES, *TARGETS):
                row[field] = float(raw[field])
            rows.append(row)
    if not rows:
        raise ValueError("Lifecycle CSV contains no rows.")
    return rows


def _arrays(rows: list[dict[str, object]], target: str) -> tuple[np.ndarray, np.ndarray]:
    return (
        np.asarray([[float(row[field]) for field in FEATURES] for row in rows], dtype=float),
        np.asarray([float(row[target]) for row in rows], dtype=float),
    )


def training_median_baseline(train_values: np.ndarray, test_values: np.ndarray, unit: str) -> dict[str, float | int | str]:
    prediction = np.full_like(test_values, float(np.median(train_values)), dtype=float)
    return metric_summary(test_values, prediction, unit=unit)


def _select_params(train_rows: list[dict[str, object]], validation_rows: list[dict[str, object]], target: str, seed: int) -> dict[str, float | int]:
    x_train, y_train = _arrays(train_rows, target)
    x_validation, y_validation = _arrays(validation_rows, target)
    choices: list[tuple[float, dict[str, float | int]]] = []
    for candidate in CANDIDATES:
        model = HistGradientBoostingRegressor(random_state=seed, min_samples_leaf=1, **candidate)
        model.fit(x_train, y_train)
        mae = float(np.mean(np.abs(model.predict(x_validation) - y_validation)))
        choices.append((mae, dict(candidate)))
    return min(choices, key=lambda item: item[0])[1]


def run_lifecycle_fold(data_path: Path, fold: LocoFold, results_dir: Path, seed: int = 42) -> dict[str, Any]:
    """Train SOH/RUL models on two cells and evaluate a completely unseen cell."""
    assert_no_fold_leakage(fold)
    rows = _load_rows(data_path)
    train_rows = [row for row in rows if row["cell_id"] in fold.train_cells]
    validation_rows = [row for row in rows if row["cell_id"] == fold.validation_cell]
    test_rows = [row for row in rows if row["cell_id"] == fold.test_cell]
    if not train_rows or not validation_rows or not test_rows:
        raise ValueError(f"{fold.name} has an empty train, validation, or test partition.")
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    metrics: dict[str, dict[str, float | int | str]] = {}
    baseline_metrics: dict[str, dict[str, float | int | str]] = {}
    prediction_rows = [{"cell_id": str(row["cell_id"]), "cycle_id": int(row["cycle_id"])} for row in test_rows]
    selected: dict[str, dict[str, float | int]] = {}
    parameters = _select_params(train_rows, validation_rows, "soh", seed)
    selected["soh"] = parameters
    x_train, y_train_soh = _arrays(train_rows, "soh")
    x_test, y_test_soh = _arrays(test_rows, "soh")
    model = HistGradientBoostingRegressor(random_state=seed, min_samples_leaf=1, **parameters)
    model.fit(x_train, y_train_soh)
    predicted_soh = model.predict(x_test)
    metrics["soh"] = metric_summary(y_test_soh, predicted_soh, unit=UNITS["soh"])
    baseline_metrics["soh"] = training_median_baseline(y_train_soh, y_test_soh, UNITS["soh"])

    trajectory = RulTrajectoryEstimator().fit(train_rows)
    projected_rows = [{**row, "soh": float(soh)} for row, soh in zip(test_rows, predicted_soh)]
    rul_output = trajectory.predict(projected_rows)
    predicted_rul = np.asarray([float(item["rul_cycles"]) for item in rul_output])
    y_train_rul = np.asarray([float(row["rul_cycles"]) for row in train_rows])
    y_test_rul = np.asarray([float(row["rul_cycles"]) for row in test_rows])
    metrics["rul_cycles"] = metric_summary(y_test_rul, predicted_rul, unit=UNITS["rul_cycles"])
    baseline_metrics["rul_cycles"] = training_median_baseline(y_train_rul, y_test_rul, UNITS["rul_cycles"])
    for row, reference_soh, estimate_soh, reference_rul, estimate_rul, audit in zip(
        prediction_rows, y_test_soh, predicted_soh, y_test_rul, predicted_rul, rul_output,
    ):
        row.update({
            "reference_soh": float(reference_soh), "predicted_soh": float(estimate_soh),
            "reference_rul_cycles": float(reference_rul), "predicted_rul_cycles": float(estimate_rul),
            "rul_method": "causal_soh_threshold_projection", "slope_used": float(audit["slope_used"]),
            "used_prior_fallback": bool(audit["used_prior_fallback"]),
        })
    (results_dir / "metrics_by_target.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    (results_dir / "baseline_metrics.json").write_text(json.dumps(baseline_metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    (results_dir / "feature_importance_note.json").write_text(json.dumps({"method": "HistGradientBoostingRegressor has no intrinsic impurity importance; this run records the fixed causal feature set.", "features": FEATURES}, ensure_ascii=False, indent=2), encoding="utf-8")
    fallback_count = sum(bool(item["used_prior_fallback"]) for item in rul_output)
    (results_dir / "run_config.json").write_text(json.dumps({"fold": fold.name, "train_cells": list(fold.train_cells), "validation_cell": fold.validation_cell, "test_cell": fold.test_cell, "features": FEATURES, "targets": TARGETS, "selected_parameters": selected, "rul_method": "causal_soh_threshold_projection", "rul_prior_fallback_count": fallback_count, "seed": seed}, ensure_ascii=False, indent=2), encoding="utf-8")
    verdicts = {"soh": acceptance("soh", float(metrics["soh"]["MAE"]), y_test_soh), "rul_cycles": acceptance("rul_cycles", float(metrics["rul_cycles"]["MAE"]), y_test_rul)}
    (results_dir / "acceptance.json").write_text(json.dumps(verdicts, ensure_ascii=False, indent=2), encoding="utf-8")
    (results_dir / "leakage_audit.json").write_text(json.dumps({"train_cells": list(fold.train_cells), "validation_cell": fold.validation_cell, "test_cell": fold.test_cell, "feature_time_scope": "current_or_historical_cycles", "rul_label_clipping": False, "prior_fit": "train_only"}, ensure_ascii=False, indent=2), encoding="utf-8")
    with (results_dir / "test_predictions.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=tuple(prediction_rows[0]))
        writer.writeheader(); writer.writerows(prediction_rows)
    return {"fold": fold.name, "train_cells": list(fold.train_cells), "validation_cell": fold.validation_cell, "test_cell": fold.test_cell, "metrics_by_target": metrics, "baseline_metrics": baseline_metrics}
