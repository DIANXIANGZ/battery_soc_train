"""Strict multi-source battery experiments with target-specific specialists."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from src.training.battery_protocol import audit_split, nested_group_folds, target_acceptance
from src.training.models.common import SpecialistDataset
from src.training.models.rul import RULSpecialist
from src.training.models.soc import SOCSpecialist
from src.training.models.soe import SOESpecialist
from src.training.models.soh import SOHSpecialist
from src.training.models.sot import SOTResidualSpecialist


def _json(path: Path, payload: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def load_validated_experiment_table(path: Path) -> pd.DataFrame:
    """Load a corpus only after enforcing its persisted label-validity contract."""

    path = Path(path)
    invalidation_path = path.parent / "INVALIDATED.json"
    if invalidation_path.is_file():
        invalidation = json.loads(invalidation_path.read_text(encoding="utf-8"))
        raise ValueError(f"Corpus is invalidated: {invalidation.get('reason', 'unspecified reason')}")
    manifest_path = path.parent / "corpus_manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("valid_for_training") is False:
            raise ValueError(f"Corpus is invalidated: {manifest.get('invalidation_reason', 'unspecified reason')}")
        if manifest.get("state_label_protocol") != "causal_precycle_reference_v2":
            raise ValueError("Corpus predates the causal state-label protocol and cannot be trained")
        if manifest.get("state_integration_protocol") != "native_cumulative_qd_and_dq_times_voltage_when_available_v1":
            raise ValueError("Corpus predates the admitted native state-integration protocol and cannot be trained")
        if manifest.get("feature_reference_protocol") != "first_cycle_reuses_sample_causal_reference_then_previous_completed_cycle_v1":
            raise ValueError("Corpus predates the aligned feature-reference protocol and cannot be trained")
    return pd.read_csv(path)


def _frame_hash(frame: pd.DataFrame) -> str:
    values = pd.util.hash_pandas_object(frame, index=True).to_numpy(dtype=np.uint64)
    return hashlib.sha256(values.tobytes()).hexdigest()


def _specialist(
    target: str,
    feature_columns: tuple[str, ...],
    seed: int,
    *,
    sequence_shape: tuple[int, int] | None = None,
    deep_kinds: tuple[str, ...] = (),
    deep_epochs: int = 5,
):
    if target == "soc":
        return SOCSpecialist(seed=seed, sequence_shape=sequence_shape, deep_kinds=deep_kinds, deep_epochs=deep_epochs)
    if target == "soe":
        return SOESpecialist(seed=seed, sequence_shape=sequence_shape, deep_kinds=deep_kinds, deep_epochs=deep_epochs)
    if target == "soh":
        return SOHSpecialist(seed=seed)
    if target in {"rul", "rul_cycles"}:
        if "current_soh_for_rul" in feature_columns and "soh_slope_per_cycle" in feature_columns:
            return RULSpecialist(
                feature_columns.index("current_soh_for_rul"),
                feature_columns.index("soh_slope_per_cycle"),
                seed=seed,
            )
        return RULSpecialist(seed=seed)
    if target in {"sot", "sot_c", "sot_5min_c"}:
        if "temperature_c" not in feature_columns:
            raise ValueError("SOT specialist requires temperature_c as a current feature")
        temperature_index = feature_columns.index("temperature_c")
        if sequence_shape is not None:
            temperature_index += (sequence_shape[0] - 1) * sequence_shape[1]
        return SOTResidualSpecialist(
            temperature_index, seed=seed, sequence_shape=sequence_shape,
            deep_kinds=deep_kinds, deep_epochs=deep_epochs,
        )
    raise ValueError(f"Unsupported target: {target}")


def _validate_feature_provenance(feature_columns: tuple[str, ...], feature_provenance: dict[str, str]) -> None:
    future_tokens = ("future", "next", "lead", "lookahead", "t+")
    for feature in feature_columns:
        if feature not in feature_provenance:
            raise ValueError(f"Feature {feature} has no provenance")
        description = f"{feature} {feature_provenance[feature]}".lower()
        if any(token in description for token in future_tokens):
            raise ValueError(f"Feature {feature} depends on future information")


def _smoke_limit(indices: np.ndarray, maximum: int, seed: int) -> np.ndarray:
    if len(indices) <= maximum:
        return indices
    random = np.random.default_rng(seed)
    return np.sort(random.choice(indices, size=maximum, replace=False))


def _target_observations(
    frame: pd.DataFrame,
    target: str,
    columns: tuple[str, ...],
    sequence_window: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    available_positions = np.flatnonzero(frame[target].notna().to_numpy())
    state_target = target in {"soc", "soe", "sot", "sot_c", "sot_5min_c"}
    if sequence_window <= 1 or not state_target:
        return (
            frame.iloc[available_positions].loc[:, columns].to_numpy(dtype=float),
            frame.iloc[available_positions][target].to_numpy(dtype=float),
            available_positions,
        )
    windows: list[np.ndarray] = []
    targets: list[float] = []
    endpoints: list[int] = []
    available = frame.iloc[available_positions].copy()
    available["_row_position"] = available_positions
    group_columns = ["source_id", "cell_id", "condition_id", "cycle_id"]
    for _, group in available.groupby(group_columns, sort=False):
        group = group.sort_values("timestamp_s")
        values = group.loc[:, columns].to_numpy(dtype=float)
        labels = group[target].to_numpy(dtype=float)
        positions = group["_row_position"].to_numpy(dtype=int)
        for stop in range(sequence_window, len(group) + 1):
            windows.append(values[stop - sequence_window:stop])
            targets.append(float(labels[stop - 1]))
            endpoints.append(int(positions[stop - 1]))
    if not windows:
        raise ValueError(f"No causal {sequence_window}-sample windows available for {target}")
    return np.stack(windows), np.asarray(targets), np.asarray(endpoints, dtype=int)


def run_multidataset_experiment(
    frame: pd.DataFrame,
    results_dir: Path,
    *,
    feature_columns: tuple[str, ...] | dict[str, tuple[str, ...]],
    targets: tuple[str, ...],
    feature_provenance: dict[str, str],
    seed: int = 43,
    stage: str = "smoke",
    sequence_window: int = 1,
) -> dict[str, object]:
    """Fit specialists by nested validation and score strict held-out cells/conditions."""

    if stage not in {"smoke", "formal"}:
        raise ValueError("stage must be smoke or formal")
    target_features = (
        {target: tuple(feature_columns[target]) for target in targets}
        if isinstance(feature_columns, dict)
        else {target: tuple(feature_columns) for target in targets}
    )
    feature_union = sorted({feature for columns in target_features.values() for feature in columns})
    required = {"source_id", "cell_id", "condition_id", *feature_union, *targets}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Experiment table is missing columns: {missing}")
    _validate_feature_provenance(tuple(feature_union), feature_provenance)
    if not targets:
        raise ValueError("At least one target is required")
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    models_dir = results_dir / "models"
    models_dir.mkdir(exist_ok=True)

    data_manifest = {
        "stage": stage,
        "seed": seed,
        "row_count": int(len(frame)),
        "source_count": int(frame["source_id"].nunique()),
        "cell_count": int(frame["cell_id"].nunique()),
        "condition_count": int(frame["condition_id"].nunique()),
        "sources": sorted(map(str, frame["source_id"].unique())),
        "features_by_target": {target: list(columns) for target, columns in target_features.items()},
        "feature_provenance": feature_provenance,
        "targets": list(targets),
        "frame_hash": _frame_hash(frame.loc[:, sorted(required)]),
        "sequence_window": sequence_window,
        "source_row_counts": {str(key): int(value) for key, value in frame.groupby("source_id").size().items()},
    }
    _json(results_dir / "data_manifest.json", data_manifest)

    prediction_rows: list[dict[str, object]] = []
    split_records: list[dict[str, object]] = []
    audit_records: list[dict[str, object]] = []
    model_manifests: dict[str, list[dict[str, object]]] = {}
    for target in targets:
        columns = target_features[target]
        features_all, target_values, target_positions = _target_observations(
            frame, target, columns, sequence_window,
        )
        target_frame = frame.iloc[target_positions]
        folds = nested_group_folds(
            target_frame["cell_id"].astype(str).to_numpy(),
            target_frame["condition_id"].astype(str).to_numpy(),
            seed=seed,
        )
        if stage == "smoke":
            folds = folds[:3]
        model_manifests[target] = []
        for fold in folds:
            audit = audit_split(
                target_frame["cell_id"].astype(str).to_numpy(),
                target_frame["condition_id"].astype(str).to_numpy(),
                fold,
            )
            audit_records.append({"target": target, "fold_id": fold.fold_id, **audit.__dict__})
            if not audit.passed:
                raise ValueError(f"Leakage audit failed for {target}/{fold.fold_id}: {audit.violations}")
            train_indices = fold.train_indices
            validation_indices = fold.validation_indices
            test_indices = fold.test_indices
            if stage == "smoke":
                train_indices = _smoke_limit(train_indices, 5000, seed)
                validation_indices = _smoke_limit(validation_indices, 2000, seed + 1)
                test_indices = _smoke_limit(test_indices, 3000, seed + 2)
            global_train = target_positions[train_indices]
            global_validation = target_positions[validation_indices]
            global_test = target_positions[test_indices]
            is_sequence = sequence_window > 1 and target in {"soc", "soe", "sot", "sot_c", "sot_5min_c"}
            sequence_shape = (sequence_window, len(columns)) if is_sequence else None
            specialist = _specialist(
                target, columns, seed, sequence_shape=sequence_shape,
                deep_kinds=("lstm", "gru", "tcn", "transformer") if is_sequence else (),
                deep_epochs=3 if stage == "smoke" else 20,
            )
            specialist.fit(
                SpecialistDataset(features_all[train_indices], target_values[train_indices]),
                SpecialistDataset(features_all[validation_indices], target_values[validation_indices]),
            )
            prediction = specialist.predict(features_all[test_indices])
            reference = target_values[test_indices]
            checkpoint = models_dir / f"{target}.{fold.fold_id}.joblib"
            joblib.dump(specialist, checkpoint)
            manifest = specialist.artifact_manifest()
            manifest.update({"fold_id": fold.fold_id, "checkpoint": str(checkpoint)})
            model_manifests[target].append(manifest)
            split_records.append({
                "target": target,
                "fold_id": fold.fold_id,
                "test_group": fold.test_group,
                "test_condition": fold.test_condition,
                "validation_group": fold.validation_group,
                "train_rows": global_train.tolist(),
                "validation_rows": global_validation.tolist(),
                "test_rows": global_test.tolist(),
            })
            for position, truth, estimate in zip(global_test, reference, prediction):
                row = frame.iloc[int(position)]
                prediction_rows.append({
                    "target": target,
                    "fold_id": fold.fold_id,
                    "source_id": row["source_id"],
                    "cell_id": row["cell_id"],
                    "condition_id": row["condition_id"],
                    "row_index": int(position),
                    "reference": float(truth),
                    "prediction": float(estimate),
                    "absolute_error": float(abs(truth - estimate)),
                })

    predictions = pd.DataFrame(prediction_rows)
    predictions.to_csv(results_dir / "test_predictions.csv", index=False)
    metrics_by_target: dict[str, dict[str, object]] = {}
    for target, target_predictions in predictions.groupby("target", sort=False):
        result = target_acceptance(
            str(target),
            target_predictions["reference"].to_numpy(),
            target_predictions["prediction"].to_numpy(),
        )
        worst_cell = target_predictions.groupby("cell_id")["absolute_error"].mean().idxmax()
        worst_condition = target_predictions.groupby("condition_id")["absolute_error"].mean().idxmax()
        result.update({"worst_cell": str(worst_cell), "worst_condition": str(worst_condition)})
        metrics_by_target[str(target)] = result
    acceptance = {target: bool(metrics["passed"]) for target, metrics in metrics_by_target.items()}
    _json(results_dir / "split_manifest.json", {"folds": split_records})
    _json(results_dir / "leakage_audit.json", {
        "passed": all(record["passed"] for record in audit_records),
        "test_used_for_selection": False,
        "preprocessing_fit": "train_only",
        "records": audit_records,
    })
    _json(results_dir / "model_manifests.json", model_manifests)
    _json(results_dir / "metrics_by_target.json", metrics_by_target)
    _json(results_dir / "acceptance.json", {
        "targets": acceptance,
        "all_targets_passed": bool(acceptance) and all(acceptance.values()),
    })
    return {
        "metrics_by_target": metrics_by_target,
        "acceptance": acceptance,
        "results_dir": results_dir,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--stage", choices=("smoke", "formal"), default="smoke")
    parser.add_argument("--seed", type=int, default=43)
    args = parser.parse_args()
    features = {
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
    feature_union = {feature for columns in features.values() for feature in columns}
    result = run_multidataset_experiment(
        load_validated_experiment_table(args.data),
        args.results_dir,
        feature_columns=features,
        targets=("soc", "soe", "soh", "rul_cycles", "sot_c"),
        feature_provenance={feature: "current or historical observation" for feature in feature_union},
        seed=args.seed,
        stage=args.stage,
        sequence_window=20,
    )
    print(json.dumps({"results_dir": str(result["results_dir"]), "acceptance": result["acceptance"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
