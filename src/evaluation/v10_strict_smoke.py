"""One approved v10 strict smoke run with separated diagnostic contracts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.evaluation.multidataset_battery_experiments import (
    load_validated_experiment_table,
    run_multidataset_experiment,
)
from src.training.battery_protocol import target_acceptance


RUL_SOURCES = ("mit_stanford_fast_charge", "oxford_battery_degradation_1")


def _json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def causal_physics_prediction(frame: pd.DataFrame, target: str) -> np.ndarray:
    """Return the non-trained causal state baseline defined by current/past counters."""

    if target == "soc":
        numerator, denominator = "cumulative_charge_ah", "previous_capacity_ah"
    elif target == "soe":
        numerator, denominator = "cumulative_energy_wh", "previous_energy_wh"
    else:
        raise ValueError("Causal physics baseline supports only soc and soe")
    values = frame[[numerator, denominator]].to_numpy(dtype=float)
    if not np.isfinite(values).all() or np.any(values[:, 1] <= 0):
        raise ValueError(f"Invalid causal inputs for {target} physics baseline")
    return np.clip(1.0 - values[:, 0] / values[:, 1], 0.0, 1.0)


def rul_source_frames(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Partition observed RUL tasks without ever returning a combined target table."""

    result: dict[str, pd.DataFrame] = {}
    for source in RUL_SOURCES:
        part = frame[frame["source_id"].eq(source) & frame["rul_cycles"].notna()].copy()
        if part.empty:
            raise ValueError(f"No observed RUL rows for {source}")
        result[source] = part
    return result


def audit_soh_domain_residuals(
    predictions: pd.DataFrame,
    experiment: pd.DataFrame,
    split_manifest: dict[str, object],
) -> pd.DataFrame:
    """Layer unchanged SOH residuals by unseen policy and train-only cycle range."""

    rows: list[pd.DataFrame] = []
    soh_predictions = predictions[predictions["target"].eq("soh")]
    for fold in split_manifest["folds"]:
        if fold["target"] != "soh":
            continue
        train_cycles = experiment.iloc[np.asarray(fold["train_rows"], dtype=int)]["cycle_id"].astype(float)
        if train_cycles.empty:
            raise ValueError(f"SOH fold {fold['fold_id']} has no train cycles")
        low, q33, q67, high = (
            float(train_cycles.min()),
            float(train_cycles.quantile(1 / 3)),
            float(train_cycles.quantile(2 / 3)),
            float(train_cycles.max()),
        )
        part = soh_predictions[soh_predictions["fold_id"].eq(fold["fold_id"])].copy()
        evidence = experiment.iloc[part["row_index"].to_numpy(dtype=int)]
        part["condition_id"] = evidence["condition_id"].astype(str).to_numpy()
        part["cycle_id"] = evidence["cycle_id"].astype(float).to_numpy()
        part["unseen_strategy"] = part["condition_id"].eq(str(fold["test_condition"]))
        part["cycle_range"] = pd.cut(
            part["cycle_id"],
            bins=[-np.inf, low, q33, q67, high, np.inf],
            labels=["below_train_range", "train_early", "train_middle", "train_late", "above_train_range"],
            include_lowest=True,
            duplicates="drop",
        ).astype(str)
        rows.append(part)
    evidence = pd.concat(rows, ignore_index=True)
    return evidence.groupby(
        ["fold_id", "unseen_strategy", "cycle_range"], observed=True, dropna=False,
    ).agg(
        sample_count=("absolute_error", "size"),
        mae=("absolute_error", "mean"),
        coverage_within_0_01=("absolute_error", lambda values: float((values <= 0.01).mean())),
        max_absolute_error=("absolute_error", "max"),
    ).reset_index()


def _group_metrics(predictions: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for (target, source, fold), group in predictions.groupby(["target", "source_id", "fold_id"], sort=False):
        metrics = target_acceptance(
            str(target), group["reference"].to_numpy(dtype=float), group["prediction"].to_numpy(dtype=float),
        )
        rows.append({"target": target, "source_id": source, "fold_id": fold, **metrics})
    return pd.DataFrame(rows)


def _physics_baseline(
    experiment: pd.DataFrame,
    split_manifest: dict[str, object],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[pd.DataFrame] = []
    for fold in split_manifest["folds"]:
        target = str(fold["target"])
        if target not in {"soc", "soe"}:
            continue
        indices = np.asarray(fold["test_rows"], dtype=int)
        frame = experiment.iloc[indices].copy()
        prediction = causal_physics_prediction(frame, target)
        reference = frame[target].to_numpy(dtype=float)
        rows.append(pd.DataFrame({
            "target": target,
            "source_id": frame["source_id"].astype(str).to_numpy(),
            "cell_id": frame["cell_id"].astype(str).to_numpy(),
            "condition_id": frame["condition_id"].astype(str).to_numpy(),
            "fold_id": fold["fold_id"],
            "row_index": indices,
            "reference": reference,
            "prediction": prediction,
            "absolute_error": np.abs(reference - prediction),
            "baseline_kind": "non_trained_causal_physics",
        }))
    predictions = pd.concat(rows, ignore_index=True)
    return predictions, _group_metrics(predictions)


def _features() -> dict[str, tuple[str, ...]]:
    return {
        "soc": (
            "cycle_id", "timestamp_s", "voltage_v", "current_a", "temperature_c",
            "cumulative_charge_ah", "previous_capacity_ah",
        ),
        "soe": (
            "cycle_id", "timestamp_s", "voltage_v", "current_a", "temperature_c",
            "cumulative_energy_wh", "previous_energy_wh",
        ),
        "soh": (
            "cycle_id", "timestamp_s", "voltage_v", "current_a", "temperature_c",
            "previous_soh", "soh_history_mean", "soh_slope_per_cycle", "cumulative_throughput_ah",
        ),
        "rul_cycles": (
            "cycle_id", "current_soh_for_rul", "previous_soh", "soh_history_mean",
            "soh_slope_per_cycle", "cumulative_throughput_ah", "temperature_c",
        ),
        "sot_c": (
            "cycle_id", "timestamp_s", "voltage_v", "current_a", "temperature_c", "cumulative_charge_ah",
        ),
    }


def run_v10_smoke(data_path: Path, results_dir: Path, seed: int = 43) -> None:
    if results_dir.exists():
        raise ValueError(f"Results directory already exists: {results_dir}")
    results_dir.mkdir(parents=True)
    experiment = load_validated_experiment_table(data_path)
    features = _features()
    feature_union = {feature for columns in features.values() for feature in columns}
    provenance = {feature: "current or historical observation" for feature in feature_union}

    learned_dir = results_dir / "learned_state_soh_sot"
    learned = run_multidataset_experiment(
        experiment,
        learned_dir,
        feature_columns={target: features[target] for target in ("soc", "soe", "soh", "sot_c")},
        targets=("soc", "soe", "soh", "sot_c"),
        feature_provenance=provenance,
        seed=seed,
        stage="smoke",
        sequence_window=10,
    )
    learned_predictions = pd.read_csv(learned_dir / "test_predictions.csv")
    _group_metrics(learned_predictions).to_csv(results_dir / "learned_metrics_by_source_fold.csv", index=False)
    split_manifest = json.loads((learned_dir / "split_manifest.json").read_text(encoding="utf-8"))
    physics_predictions, physics_metrics = _physics_baseline(experiment, split_manifest)
    physics_predictions.to_csv(results_dir / "physics_baseline_predictions.csv", index=False)
    physics_metrics.to_csv(results_dir / "physics_baseline_metrics_by_source_fold.csv", index=False)
    soh_domain = audit_soh_domain_residuals(learned_predictions, experiment, split_manifest)
    soh_domain.to_csv(results_dir / "soh_unseen_strategy_cycle_range_audit.csv", index=False)

    rul_results: dict[str, object] = {}
    for source, source_frame in rul_source_frames(experiment).items():
        source_dir = results_dir / "rul_by_source" / source
        result = run_multidataset_experiment(
            source_frame,
            source_dir,
            feature_columns={"rul_cycles": features["rul_cycles"]},
            targets=("rul_cycles",),
            feature_provenance=provenance,
            seed=seed,
            stage="smoke",
            sequence_window=1,
        )
        predictions = pd.read_csv(source_dir / "test_predictions.csv")
        _group_metrics(predictions).to_csv(source_dir / "metrics_by_source_fold.csv", index=False)
        rul_results[source] = result["metrics_by_target"]["rul_cycles"]

    physics_passed = bool((physics_metrics["passed"] == True).all())  # noqa: E712
    learned_acceptance = learned["acceptance"]
    _json(results_dir / "smoke_summary.json", {
        "stage": "strict_smoke",
        "seed": seed,
        "formal_training_allowed": False,
        "physics_baseline": {
            "kind": "non_trained_causal_physics",
            "passed": physics_passed,
            "must_not_be_reported_as_learned_model": True,
        },
        "learned_models": learned_acceptance,
        "rul_by_source": rul_results,
        "combined_rul_metric_created": False,
        "all_learned_targets_passed": bool(learned_acceptance) and all(learned_acceptance.values()),
        "all_rul_sources_passed": all(bool(metrics["passed"]) for metrics in rul_results.values()),
    })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=43)
    args = parser.parse_args()
    run_v10_smoke(args.data, args.results_dir, seed=args.seed)


if __name__ == "__main__":
    main()
