"""Reproducible Phase 1/2 diagnostics for a rejected v9 strict smoke run.

This module never fits a model. It preserves prediction evidence and compares
label definitions under the already-persisted strict splits.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.training.battery_protocol import nested_group_folds


STATE_TARGETS = ("soc", "soe")
NOMINAL_CAPACITY_AH = {
    "mit_stanford_fast_charge": 1.1,
    "oxford_battery_degradation_1": 0.74,
}


def _json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _distribution(values: pd.Series) -> dict[str, float | int]:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    if clean.empty:
        return {"count": 0}
    return {
        "count": int(len(clean)),
        "mean": float(clean.mean()),
        "std": float(clean.std(ddof=0)),
        "p05": float(clean.quantile(0.05)),
        "median": float(clean.median()),
        "p95": float(clean.quantile(0.95)),
        "min": float(clean.min()),
        "max": float(clean.max()),
    }


def enrich_predictions(experiment: pd.DataFrame, predictions: pd.DataFrame) -> pd.DataFrame:
    evidence_columns = [
        "source_id", "cell_id", "condition_id", "cycle_id", "timestamp_s",
        "cumulative_charge_ah", "cumulative_energy_wh",
        "previous_capacity_ah", "previous_energy_wh",
        "soc", "soe", "soh", "rul_cycles",
    ]
    evidence = experiment.loc[:, evidence_columns].copy()
    evidence["row_index"] = np.arange(len(evidence), dtype=int)
    enriched = predictions.merge(evidence, on="row_index", how="left", suffixes=("", "_table"), validate="many_to_one")
    for identity in ("source_id", "cell_id", "condition_id"):
        table_column = f"{identity}_table"
        if not enriched[identity].astype(str).equals(enriched[table_column].astype(str)):
            raise ValueError(f"Prediction evidence identity mismatch: {identity}")
        enriched = enriched.drop(columns=table_column)
    if enriched[["previous_capacity_ah", "previous_energy_wh"]].isna().all(axis=None):
        raise ValueError("Prediction evidence has no persisted state references")
    return enriched


def state_label_evidence(experiment: pd.DataFrame) -> pd.DataFrame:
    """Create pre-training state evidence without fitting or predicting."""

    frames: list[pd.DataFrame] = []
    columns = [
        "source_id", "cell_id", "condition_id", "cycle_id", "timestamp_s",
        "cumulative_charge_ah", "cumulative_energy_wh",
        "previous_capacity_ah", "previous_energy_wh",
    ]
    for target in STATE_TARGETS:
        frame = experiment[experiment[target].notna()].loc[:, columns].copy()
        frame["row_index"] = frame.index.astype(int)
        frame["target"] = target
        frame["reference"] = experiment.loc[frame.index, target].to_numpy(dtype=float)
        frame["prediction"] = np.nan
        frame["absolute_error"] = np.nan
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def strict_soh_split_manifest(experiment: pd.DataFrame, seed: int = 43) -> dict[str, object]:
    positions = np.flatnonzero(experiment["soh"].notna().to_numpy())
    frame = experiment.iloc[positions]
    folds = nested_group_folds(
        frame["cell_id"].astype(str).to_numpy(),
        frame["condition_id"].astype(str).to_numpy(),
        seed=seed,
    )[:3]
    return {"folds": [
        {
            "target": "soh",
            "fold_id": fold.fold_id,
            "test_group": fold.test_group,
            "test_condition": fold.test_condition,
            "validation_group": fold.validation_group,
            "train_rows": positions[fold.train_indices].tolist(),
            "validation_rows": positions[fold.validation_indices].tolist(),
            "test_rows": positions[fold.test_indices].tolist(),
        }
        for fold in folds
    ]}


def audit_state_physics(enriched: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, object]]:
    rows: list[pd.DataFrame] = []
    summaries: dict[str, object] = {}
    for target in STATE_TARGETS:
        frame = enriched[enriched["target"].eq(target)].copy()
        if target == "soc":
            numerator = frame["cumulative_charge_ah"]
            denominator = frame["previous_capacity_ah"]
        else:
            numerator = frame["cumulative_energy_wh"]
            denominator = frame["previous_energy_wh"]
        if denominator.isna().any() or (denominator <= 0).any():
            raise ValueError(f"{target} contains invalid fixed pre-cycle references")
        frame["physical_candidate"] = np.clip(1.0 - numerator / denominator, 0.0, 1.0)
        frame["physical_absolute_error"] = (frame["physical_candidate"] - frame["reference"]).abs()
        frame["causal_progress"] = numerator / denominator
        frame["discharge_stage"] = pd.cut(
            frame["causal_progress"],
            bins=[-np.inf, 0.25, 0.50, 0.75, 1.0, np.inf],
            labels=["0-25%", "25-50%", "50-75%", "75-100%", ">100%"],
            right=False,
        ).astype(str)
        rows.append(frame)
        summaries[target] = {
            "model_absolute_error": _distribution(frame["absolute_error"]),
            "physical_absolute_error": _distribution(frame["physical_absolute_error"]),
            "physical_within_0_01_coverage": float((frame["physical_absolute_error"] <= 0.01).mean()),
            "causal_inputs": [
                "current-or-past cumulative counter",
                "fixed nominal or previous completed cycle reference",
            ],
            "uses_future_information": False,
        }
    state = pd.concat(rows, ignore_index=True)
    grouped = state.groupby(
        ["target", "source_id", "cell_id", "condition_id", "discharge_stage"],
        observed=True,
        dropna=False,
    ).agg(
        sample_count=("reference", "size"),
        model_mae=("absolute_error", "mean"),
        model_p95_absolute_error=("absolute_error", lambda values: values.quantile(0.95)),
        physical_mae=("physical_absolute_error", "mean"),
        physical_max_absolute_error=("physical_absolute_error", "max"),
    ).reset_index()
    return state, {"targets": summaries, "group_count": int(len(grouped)), "grouped": grouped}


def _nominal_capacity(source_id: str) -> float:
    if source_id in NOMINAL_CAPACITY_AH:
        return NOMINAL_CAPACITY_AH[source_id]
    if source_id.startswith("calce"):
        return 1.1
    raise ValueError(f"No audited nominal capacity for {source_id}")


def audit_soh_definitions(
    experiment: pd.DataFrame,
    cycles: pd.DataFrame,
    split_manifest: dict[str, object],
) -> tuple[pd.DataFrame, dict[str, object]]:
    lifecycle = experiment[experiment["soh"].notna()].copy()
    lifecycle["row_index"] = lifecycle.index.astype(int)
    capacity = cycles.loc[:, ["source_id", "cell_id", "cycle_id", "capacity_ah"]]
    lifecycle = lifecycle.merge(capacity, on=["source_id", "cell_id", "cycle_id"], validate="one_to_one")
    first_capacity = (
        cycles.sort_values(["source_id", "cell_id", "cycle_id"])
        .groupby(["source_id", "cell_id"], as_index=False)
        .first()[["source_id", "cell_id", "capacity_ah"]]
        .rename(columns={"capacity_ah": "first_complete_capacity_ah"})
    )
    lifecycle = lifecycle.merge(first_capacity, on=["source_id", "cell_id"], validate="many_to_one")
    lifecycle["nominal_capacity_ah"] = lifecycle["source_id"].map(_nominal_capacity)
    lifecycle["soh_nominal"] = lifecycle["capacity_ah"] / lifecycle["nominal_capacity_ah"]
    lifecycle["soh_first_complete"] = lifecycle["capacity_ah"] / lifecycle["first_complete_capacity_ah"]

    audit_rows: list[pd.DataFrame] = []
    shift_rows: list[dict[str, object]] = []
    folds = [fold for fold in split_manifest["folds"] if fold["target"] == "soh"]
    for fold in folds:
        train_rows = set(map(int, fold["train_rows"]))
        test_rows = set(map(int, fold["test_rows"]))
        fold_frame = lifecycle[lifecycle["row_index"].isin(train_rows | test_rows)].copy()
        fold_frame["split"] = np.where(fold_frame["row_index"].isin(train_rows), "train", "test")
        train_cells = fold_frame[fold_frame["split"].eq("train")][
            ["source_id", "cell_id", "first_complete_capacity_ah"]
        ].drop_duplicates()
        source_reference = train_cells.groupby("source_id")["first_complete_capacity_ah"].median()
        global_reference = float(train_cells["first_complete_capacity_ah"].median())
        fold_frame["train_cells_reference_ah"] = fold_frame["source_id"].map(source_reference).fillna(global_reference)
        fold_frame["soh_train_cells_stat"] = fold_frame["capacity_ah"] / fold_frame["train_cells_reference_ah"]
        fold_frame["fold_id"] = fold["fold_id"]
        audit_rows.append(fold_frame)
        for definition in ("soh_nominal", "soh_first_complete", "soh_train_cells_stat"):
            train_means = fold_frame[fold_frame["split"].eq("train")].groupby("source_id")[definition].mean()
            for (source, condition), group in fold_frame[fold_frame["split"].eq("test")].groupby(["source_id", "condition_id"]):
                shift_rows.append({
                    "fold_id": fold["fold_id"],
                    "definition": definition,
                    "source_id": source,
                    "condition_id": condition,
                    "sample_count": int(len(group)),
                    "test_mean": float(group[definition].mean()),
                    "train_source_mean": float(train_means.get(source, np.nan)),
                    "mean_shift_from_train_source": float(group[definition].mean() - train_means.get(source, np.nan)),
                })
    audit = pd.concat(audit_rows, ignore_index=True)
    shifts = pd.DataFrame(shift_rows)
    summary: dict[str, object] = {"fold_count": len(folds), "definitions": {}}
    for definition in ("soh_nominal", "soh_first_complete", "soh_train_cells_stat"):
        definition_shifts = shifts[shifts["definition"].eq(definition)]["mean_shift_from_train_source"].abs()
        summary["definitions"][definition] = {
            "all_rows": _distribution(audit[definition]),
            "absolute_condition_shift": _distribution(definition_shifts),
        }
    return shifts, summary


def audit_rul_sources(cycles: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, object]]:
    observed = cycles[cycles["rul_observed"].eq(1) & cycles["rul_cycles"].notna()].copy()
    rows: list[dict[str, object]] = []
    for source, group in observed.groupby("source_id"):
        steps = group.sort_values(["cell_id", "cycle_id"]).groupby("cell_id")["cycle_id"].diff().dropna()
        rows.append({
            "source_id": source,
            "cell_count": int(group["cell_id"].nunique()),
            "label_rows": int(len(group)),
            "cycle_id_min": float(group["cycle_id"].min()),
            "cycle_id_max": float(group["cycle_id"].max()),
            "median_observation_step_cycles": float(steps.median()),
            "rul_min_cycles": float(group["rul_cycles"].min()),
            "rul_median_cycles": float(group["rul_cycles"].median()),
            "rul_p95_cycles": float(group["rul_cycles"].quantile(0.95)),
            "rul_max_cycles": float(group["rul_cycles"].max()),
        })
    comparison = pd.DataFrame(rows)
    protocols = {
        "mit_stanford_fast_charge": {
            "cycle_life": "official per-cell cycle_life descriptor",
            "eol_threshold": "0.88 Ah, equal to 80% of 1.1 Ah nominal capacity",
            "cycle_count_origin": "1-based physical cycle count; cycle 1 trace omitted, observed traces begin at cycle 2",
            "sampling_protocol": "approximately every physical cycle",
        },
        "oxford_battery_degradation_1": {
            "cycle_life": "first observed cycle where capacity/first-complete-cycle capacity <= 0.80",
            "eol_threshold": "80% of each cell's first complete observed-cycle capacity",
            "cycle_count_origin": "physical cycle counter begins at 0 in the canonical source",
            "sampling_protocol": "diagnostic observations approximately every 100 physical cycles",
        },
    }
    return comparison, {
        "protocols": protocols,
        "same_numeric_unit": "physical cycles",
        "same_supervised_task": False,
        "noncomparability_reasons": [
            "different EOL capacity reference (nominal versus first observed cycle)",
            "different observation cadence (about 1 versus 100 cycles)",
            "substantially different lifetime ranges and cell domains",
        ],
    }


def run_audit(data_dir: Path, results_dir: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=False)
    not_accepted = json.loads((results_dir / "NOT_ACCEPTED.json").read_text(encoding="utf-8"))
    if not not_accepted.get("valid_as_diagnostic_evidence") or not_accepted.get("accepted_for_deployment"):
        raise ValueError("Smoke run is not frozen as rejected diagnostic evidence")
    experiment = pd.read_csv(data_dir / "public_battery_experiment.csv")
    cycles = pd.read_csv(data_dir / "public_battery_cycles.csv")
    predictions = pd.read_csv(results_dir / "test_predictions.csv")
    splits = json.loads((results_dir / "split_manifest.json").read_text(encoding="utf-8"))

    enriched = enrich_predictions(experiment, predictions)
    enriched.to_csv(output_dir / "smoke_predictions_enriched.csv", index=False)
    state_rows, state_summary = audit_state_physics(enriched)
    state_rows.to_csv(output_dir / "soc_soe_physics_rows.csv", index=False)
    state_summary.pop("grouped").to_csv(output_dir / "soc_soe_physics_by_source_cell_stage.csv", index=False)
    _json(output_dir / "soc_soe_physics_summary.json", state_summary)
    soh_shifts, soh_summary = audit_soh_definitions(experiment, cycles, splits)
    soh_shifts.to_csv(output_dir / "soh_normalization_condition_shifts.csv", index=False)
    _json(output_dir / "soh_normalization_summary.json", soh_summary)
    rul_comparison, rul_summary = audit_rul_sources(cycles)
    rul_comparison.to_csv(output_dir / "rul_source_comparison.csv", index=False)
    _json(output_dir / "rul_source_protocols.json", rul_summary)


def run_pretraining_audit(data_dir: Path, output_dir: Path) -> None:
    """Run the same label-definition diagnostics before any new smoke fit."""

    output_dir.mkdir(parents=True, exist_ok=False)
    experiment = pd.read_csv(data_dir / "public_battery_experiment.csv")
    cycles = pd.read_csv(data_dir / "public_battery_cycles.csv")
    state_rows, state_summary = audit_state_physics(state_label_evidence(experiment))
    state_rows.to_csv(output_dir / "soc_soe_physics_rows.csv", index=False)
    state_summary.pop("grouped").to_csv(output_dir / "soc_soe_physics_by_source_cell_stage.csv", index=False)
    _json(output_dir / "soc_soe_physics_summary.json", state_summary)
    splits = strict_soh_split_manifest(experiment)
    _json(output_dir / "strict_soh_split_manifest.json", splits)
    soh_shifts, soh_summary = audit_soh_definitions(experiment, cycles, splits)
    soh_shifts.to_csv(output_dir / "soh_normalization_condition_shifts.csv", index=False)
    _json(output_dir / "soh_normalization_summary.json", soh_summary)
    rul_comparison, rul_summary = audit_rul_sources(cycles)
    rul_comparison.to_csv(output_dir / "rul_source_comparison.csv", index=False)
    _json(output_dir / "rul_source_protocols.json", rul_summary)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--results-dir", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.results_dir:
        run_audit(args.data_dir, args.results_dir, args.output_dir)
    else:
        run_pretraining_audit(args.data_dir, args.output_dir)


if __name__ == "__main__":
    main()
