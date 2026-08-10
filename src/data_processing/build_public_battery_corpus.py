"""Build a traceable canonical corpus from admitted public battery archives."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.data_processing.adapters import calce, oxford, stanford
from src.data_processing.battery_data_quality import BatteryTableSchema, admit, profile_battery_table, write_quality_report
from src.project_paths import DataCenterPaths
from src.research.battery_schema import derive_cycle_targets, derive_state_targets


RUL_PROVENANCE_CLASSES = (
    "observed_eol_crossing",
    "official_continuation",
    "right_censored",
)


def summarize_rul_provenance(samples: pd.DataFrame, cycles: pd.DataFrame) -> dict[str, dict[str, int]]:
    required = {"cell_id", "eol_provenance"}
    if not required.issubset(samples.columns) or not (required | {"rul_observed", "rul_cycles"}).issubset(cycles.columns):
        raise ValueError("RUL provenance gate requires cell, observation, and provenance columns")
    unknown = sorted(set(cycles["eol_provenance"].dropna().astype(str)) - set(RUL_PROVENANCE_CLASSES))
    if unknown:
        raise ValueError(f"Unknown RUL provenance classes: {unknown}")
    observed = pd.to_numeric(cycles["rul_observed"], errors="coerce").fillna(0).astype(int).eq(1)
    labelled = pd.to_numeric(cycles["rul_cycles"], errors="coerce").notna()
    if not observed.equals(labelled):
        raise ValueError("Precise RUL supervision must contain observed labels only")
    summary: dict[str, dict[str, int]] = {}
    for provenance in RUL_PROVENANCE_CLASSES:
        sample_rows = samples[samples["eol_provenance"].eq(provenance)]
        cycle_rows = cycles[cycles["eol_provenance"].eq(provenance)]
        summary[provenance] = {
            "cell_count": int(cycle_rows["cell_id"].nunique()),
            "sample_rows": int(len(sample_rows)),
            "cycle_rows": int(len(cycle_rows)),
        }
    return summary


def build_cycle_table_from_samples(samples: pd.DataFrame, eol_soh: float = 0.8) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    keys = ["source_id", "chemistry", "cell_id", "cycle_id", "source_hash"]
    for identity, group in samples.groupby(keys, sort=False):
        group = group.sort_values("timestamp_s")
        time_s = group["timestamp_s"].to_numpy(dtype=float)
        voltage = group["voltage_v"].to_numpy(dtype=float)
        current = group["current_a"].to_numpy(dtype=float)
        if len(group) < 2:
            continue
        dt_s = np.diff(time_s, prepend=time_s[0])
        capacity = float(np.sum(np.abs(current) * np.maximum(dt_s, 0.0)) / 3600.0)
        energy = float(np.sum(np.abs(voltage * current) * np.maximum(dt_s, 0.0)) / 3600.0)
        if "cycle_capacity_ah" in group.columns:
            recorded_cycle = pd.to_numeric(group["cycle_capacity_ah"], errors="coerce")
            if recorded_cycle.notna().any() and float(recorded_cycle.max()) > 0:
                capacity = float(recorded_cycle.max())
        elif "Discharge_Capacity(Ah)" in group.columns:
            recorded = pd.to_numeric(group["Discharge_Capacity(Ah)"], errors="coerce")
            if recorded.notna().any() and float(recorded.max()) > 0:
                capacity = float(recorded.max())
        if "cycle_energy_wh" in group.columns:
            recorded_energy = pd.to_numeric(group["cycle_energy_wh"], errors="coerce")
            if recorded_energy.notna().any() and float(recorded_energy.max()) > 0:
                energy = float(recorded_energy.max())
        source_id, chemistry, cell_id, cycle_id, source_hash = identity
        row = {
            "source_id": source_id,
            "chemistry": chemistry,
            "cell_id": cell_id,
            "cycle_id": cycle_id,
            "capacity_ah": capacity,
            "energy_wh": energy,
            "voltage_mean_v": float(np.nanmean(voltage)),
            "current_mean_a": float(np.nanmean(current)),
            "temperature_mean_c": float(np.nanmean(group["temperature_c"])),
            "temperature_max_c": float(np.nanmax(group["temperature_c"])),
            "duration_s": float(time_s[-1] - time_s[0]),
            "source_hash": source_hash,
        }
        if "eol_cycle" in group.columns:
            eol_values = pd.to_numeric(group["eol_cycle"], errors="coerce")
            if eol_values.notna().any():
                row["eol_cycle"] = float(eol_values.dropna().iloc[0])
        if "eol_cycle_observed" in group.columns:
            observed_values = pd.to_numeric(group["eol_cycle_observed"], errors="coerce")
            if observed_values.notna().any():
                row["eol_cycle_observed"] = int(observed_values.fillna(0).astype(bool).any())
        if "eol_provenance" in group.columns:
            provenance_values = group["eol_provenance"].dropna().astype(str)
            if not provenance_values.empty:
                row["eol_provenance"] = provenance_values.iloc[0]
        rows.append(row)
    if not rows:
        return pd.DataFrame(columns=[*keys, "capacity_ah", "energy_wh", "soh", "rul_cycles", "rul_observed"])
    cycles = derive_cycle_targets(pd.DataFrame(rows), eol_soh=eol_soh)
    feature_rows = []
    for _, group in cycles.groupby(["source_id", "cell_id"], sort=False):
        group = group.sort_values("cycle_id").copy()
        cycle_ids = group["cycle_id"].to_numpy(dtype=float)
        soh = group["soh"].to_numpy(dtype=float)
        capacity = group["capacity_ah"].to_numpy(dtype=float)
        previous_soh = np.ones(len(group), dtype=float)
        history_mean = np.ones(len(group), dtype=float)
        slope = np.zeros(len(group), dtype=float)
        cumulative = np.zeros(len(group), dtype=float)
        for index in range(len(group)):
            history = soh[:index]
            if history.size:
                previous_soh[index] = history[-1]
                history_mean[index] = float(np.nanmean(history))
                cumulative[index] = float(np.nansum(capacity[:index]))
            if history.size >= 2:
                denominator = cycle_ids[index - 1] - cycle_ids[max(0, index - 3)]
                if denominator > 0:
                    slope[index] = float((history[-1] - history[max(0, index - 3)]) / denominator)
        group["previous_soh"] = previous_soh
        group["soh_history_mean"] = history_mean
        group["soh_slope_per_cycle"] = slope
        group["cumulative_throughput_ah"] = cumulative
        feature_rows.append(group)
    return pd.concat(feature_rows, ignore_index=True)


def add_causal_sample_features(samples: pd.DataFrame, cycles: pd.DataFrame) -> pd.DataFrame:
    output_frames = []
    for _, group in samples.groupby(["source_id", "cell_id", "session_id", "cycle_id"], sort=False):
        group = group.sort_values("timestamp_s").copy()
        time_s = group["timestamp_s"].to_numpy(dtype=float)
        voltage = group["voltage_v"].to_numpy(dtype=float)
        current = group["current_a"].to_numpy(dtype=float)
        native_columns = ("native_cumulative_charge_ah", "native_cumulative_energy_wh")
        if all(column in group and group[column].notna().all() for column in native_columns):
            group["cumulative_charge_ah"] = group[native_columns[0]].to_numpy(dtype=float)
            group["cumulative_energy_wh"] = group[native_columns[1]].to_numpy(dtype=float)
        else:
            dt_s = np.diff(time_s, prepend=time_s[0])
            group["cumulative_charge_ah"] = np.cumsum(np.abs(current) * np.maximum(dt_s, 0.0) / 3600.0)
            group["cumulative_energy_wh"] = np.cumsum(np.abs(voltage * current) * np.maximum(dt_s, 0.0) / 3600.0)
        output_frames.append(group)
    output = pd.concat(output_frames, ignore_index=True)
    references = cycles[["source_id", "cell_id", "cycle_id", "capacity_ah", "energy_wh"]].copy()
    references = references.sort_values(["source_id", "cell_id", "cycle_id"])
    causal_energy_references = samples.groupby(
        ["source_id", "cell_id", "cycle_id"], sort=False, as_index=False,
    )["energy_reference_wh"].first().rename(
        columns={"energy_reference_wh": "causal_energy_reference_wh"},
    )
    references = references.merge(
        causal_energy_references,
        on=["source_id", "cell_id", "cycle_id"],
        how="left",
        validate="one_to_one",
    )
    references["previous_capacity_ah"] = references.groupby(["source_id", "cell_id"])["capacity_ah"].shift()
    references["previous_energy_wh"] = references.groupby(["source_id", "cell_id"])["energy_wh"].shift()
    stanford_source = references["source_id"].eq("mit_stanford_fast_charge")
    calce_source = references["source_id"].str.startswith("calce")
    nominal_capacity = np.where(stanford_source | calce_source, 1.1, 0.74)
    references["previous_capacity_ah"] = references["previous_capacity_ah"].fillna(pd.Series(nominal_capacity, index=references.index))
    references["previous_energy_wh"] = references["previous_energy_wh"].fillna(references["causal_energy_reference_wh"])
    return output.merge(
        references[["source_id", "cell_id", "cycle_id", "previous_capacity_ah", "previous_energy_wh"]],
        on=["source_id", "cell_id", "cycle_id"], how="left",
    )


def build_experiment_table(samples: pd.DataFrame, cycles: pd.DataFrame) -> pd.DataFrame:
    """Combine sample-level state labels and one row per lifecycle observation."""

    cycles = cycles.copy()
    if "rul_observed" not in cycles:
        cycles["rul_observed"] = pd.to_numeric(cycles["rul_cycles"], errors="coerce").notna().astype(int)
    if "eol_provenance" not in cycles:
        cycles["eol_provenance"] = np.where(
            cycles["rul_observed"].eq(1), "observed_eol_crossing", "right_censored",
        )
    base_features = ["source_id", "cell_id", "condition_id", "cycle_id", "timestamp_s", "voltage_v", "current_a", "temperature_c"]
    state_features = ["cumulative_charge_ah", "cumulative_energy_wh", "previous_capacity_ah", "previous_energy_wh"]
    for column in state_features:
        if column not in samples:
            samples = samples.assign(**{column: np.nan})
    features = [*base_features, *state_features]
    state = samples.loc[:, [*features, "soc", "soe", "sot_c"]].copy()
    state["soh"] = np.nan
    state["rul_cycles"] = np.nan
    state["rul_observed"] = np.nan
    state["eol_provenance"] = np.nan
    aggregations = samples.groupby(["source_id", "cell_id", "cycle_id"], sort=False).agg(
        condition_id=("condition_id", lambda values: values.mode().iloc[0]),
        timestamp_s=("timestamp_s", "max"),
        voltage_v=("voltage_v", "mean"),
        current_a=("current_a", "mean"),
        temperature_c=("temperature_c", "mean"),
    ).reset_index()
    lifecycle = cycles.merge(aggregations, on=["source_id", "cell_id", "cycle_id"], how="inner")
    lifecycle["current_soh_for_rul"] = lifecycle["soh"]
    lifecycle_features = [
        "previous_soh", "soh_history_mean", "soh_slope_per_cycle",
        "cumulative_throughput_ah", "current_soh_for_rul",
    ]
    for column in lifecycle_features:
        if column not in lifecycle:
            lifecycle[column] = np.nan
    lifecycle = lifecycle.loc[:, [
        *base_features, *lifecycle_features, "soh", "rul_cycles", "rul_observed", "eol_provenance",
    ]]
    for column in state_features:
        lifecycle[column] = np.nan
    for column in lifecycle_features:
        state[column] = np.nan
    lifecycle["soc"] = np.nan
    lifecycle["soe"] = np.nan
    lifecycle["sot_c"] = np.nan
    return pd.concat([state, lifecycle], ignore_index=True, sort=False)


def _manifest(source_dir: Path) -> dict[str, object]:
    return json.loads((source_dir / "download_manifest.json").read_text(encoding="utf-8"))


def build_public_battery_corpus(
    raw_root: Path,
    output_dir: Path,
    report_dir: Path,
    *,
    stride: int = 20,
    overwrite: bool = False,
    require_matr_batch2: bool = False,
) -> dict[str, object]:
    if stride < 1:
        raise ValueError("stride must be positive")
    if output_dir.exists() and any(output_dir.iterdir()) and not overwrite:
        raise ValueError(f"Canonical output directory must be empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    batch2_dir = raw_root / "mit_stanford_fast_charge_batch2"
    batch2_manifest_path = batch2_dir / "download_manifest.json"
    batch2_evidence: dict[str, object] | None = None
    batch2_manifest: dict[str, object] | None = None
    if batch2_manifest_path.is_file():
        batch2_manifest = _manifest(batch2_dir)
        stanford.validate_official_batch2_manifest(batch2_manifest)
        batch2_archive = Path(str(batch2_manifest["archive_path"]))
        stanford.verify_archive_identity(
            batch2_archive,
            int(batch2_manifest["byte_count"]),
            str(batch2_manifest["sha256"]),
        )
        evidence_keys = [
            *stanford.OFFICIAL_BATCH2_EVIDENCE,
            "official_continuation_mapping",
        ]
        batch2_evidence = {key: batch2_manifest[key] for key in evidence_keys}
        batch2_evidence["archive_identity_verified"] = True
    elif require_matr_batch2:
        raise ValueError("v11 requires the verified official MATR Batch 2 manifest")
    loaders = {
        "oxford_battery_degradation_1": lambda path, digest, source_id: oxford.load_samples(path, digest, stride=stride),
        "mit_stanford_fast_charge": (
            (lambda path, digest, source_id: stanford.load_samples(
                path,
                digest,
                stride=stride,
                continuation_path=Path(str(batch2_manifest["archive_path"])),
                continuation_hash=str(batch2_manifest["sha256"]),
                continuation_mapping=batch2_manifest["official_continuation_mapping"],
            ))
            if batch2_manifest is not None
            else (lambda path, digest, source_id: stanford.load_samples(path, digest, stride=stride))
        ),
    }
    for source_dir in raw_root.glob("calce_a123_dynamic*"):
        loaders[source_dir.name] = lambda path, digest, source_id: calce.load_samples(
            path, digest, stride=stride, source_id=source_id,
        )
    admitted_samples: list[pd.DataFrame] = []
    source_records: list[dict[str, object]] = []
    for source_id, loader in loaders.items():
        source_dir = raw_root / source_id
        if not (source_dir / "download_manifest.json").is_file():
            continue
        manifest = _manifest(source_dir)
        samples = loader(Path(str(manifest["archive_path"])), str(manifest["sha256"]), source_id)
        excluded_cycles = list(samples.attrs.get("excluded_cycles", []))
        samples = derive_state_targets(samples, horizon_s=300.0)
        schema = BatteryTableSchema(
            group_columns=("source_id", "cell_id", "session_id", "cycle_id"),
            time_column="timestamp_s",
            target_columns=("soc", "soe", "sot_c"),
            target_provenance={
                "soc": "causal coulomb count from fixed pre-cycle capacity reference",
                "soe": "causal energy count from fixed pre-cycle energy reference",
                "sot_c": "same-cycle first observation at least 300 seconds ahead",
            },
            feature_provenance={
                "voltage_v": "current measurement",
                "current_a": "current measurement",
                "temperature_c": "current measurement",
                "capacity_reference_ah": "nominal or previous completed cycle only",
                "energy_reference_wh": "nominal or previous completed cycle only",
            },
        )
        report = profile_battery_table(samples, schema)
        write_quality_report(report, report_dir, source_id)
        source_record = {
            "source_id": source_id,
            "source_hash": manifest["sha256"],
            "row_count": int(len(samples)),
            "cell_count": int(samples["cell_id"].nunique()),
            "cycle_count": int(samples[["cell_id", "cycle_id"]].drop_duplicates().shape[0]),
            "admitted": admit(report),
            "critical_count": report.critical_count,
            "excluded_cycle_count": len(excluded_cycles),
            "excluded_cycles": excluded_cycles,
        }
        if source_id == "mit_stanford_fast_charge" and batch2_manifest is not None:
            source_record["continuation_source_hash"] = batch2_manifest["sha256"]
        source_records.append(source_record)
        if admit(report):
            admitted_samples.append(samples)
    if not admitted_samples:
        raise ValueError("No downloaded public battery source passed data-quality admission")
    source_samples = pd.concat(admitted_samples, ignore_index=True)
    cycle_corpus = build_cycle_table_from_samples(source_samples)
    matr_samples = source_samples[source_samples["source_id"].eq("mit_stanford_fast_charge")]
    matr_cycles = cycle_corpus[cycle_corpus["source_id"].eq("mit_stanford_fast_charge")]
    rul_provenance_counts = summarize_rul_provenance(matr_samples, matr_cycles)
    source_samples = add_causal_sample_features(source_samples, cycle_corpus)
    sample_columns = [
        "source_id", "chemistry", "cell_id", "session_id", "cycle_id", "condition_id",
        "timestamp_s", "voltage_v", "current_a", "temperature_c", "source_hash",
        "capacity_reference_ah", "energy_reference_wh", "initial_soc", "initial_soe",
        "cumulative_charge_ah", "cumulative_energy_wh", "previous_capacity_ah", "previous_energy_wh",
        "eol_cycle", "eol_cycle_observed", "eol_provenance", "soc", "soe", "sot_c",
    ]
    sample_corpus = source_samples.loc[:, sample_columns].copy()
    sample_path = output_dir / "public_battery_samples.csv"
    cycle_path = output_dir / "public_battery_cycles.csv"
    experiment_path = output_dir / "public_battery_experiment.csv"
    sample_corpus.to_csv(sample_path, index=False)
    cycle_corpus.to_csv(cycle_path, index=False)
    experiment_corpus = build_experiment_table(sample_corpus, cycle_corpus)
    experiment_corpus.to_csv(experiment_path, index=False)
    corpus_manifest = {
        "version": "public_battery_corpus_v6",
        "corpus_id": "public_battery_corpus_v11" if require_matr_batch2 else "public_battery_corpus",
        "valid_for_training": False,
        "training_authorized": False,
        "validation_status": "PENDING_FULL_V11_GATES",
        "training_block_reason": "Formal and smoke training require a new chief-engineer approval",
        "state_label_protocol": "causal_precycle_reference_v2",
        "state_integration_protocol": "native_cumulative_qd_and_dq_times_voltage_when_available_v1",
        "feature_reference_protocol": "first_cycle_reuses_sample_causal_reference_then_previous_completed_cycle_v1",
        "source_unit_protocol": {
            "mit_stanford_fast_charge": "raw_minutes_converted_to_seconds_v1",
        },
        "rul_label_protocol": "actual_0.88Ah_crossing_or_verified_official_continuation_else_right_censored_v1",
        "matr_batch2_evidence": batch2_evidence,
        "rul_provenance_counts": rul_provenance_counts,
        "precise_rul_supervision": {
            "required_rul_observed": 1,
            "censored_rows_are_exact_supervision": False,
            "observed_cycle_rows": int(matr_cycles["rul_observed"].eq(1).sum()),
        },
        "sot_horizon_s": 300.0,
        "eol_soh": 0.8,
        "sample_rows": int(len(sample_corpus)),
        "cycle_rows": int(len(cycle_corpus)),
        "experiment_rows": int(len(experiment_corpus)),
        "sources": source_records,
        "sample_path": str(sample_path),
        "cycle_path": str(cycle_path),
        "experiment_path": str(experiment_path),
    }
    (output_dir / "corpus_manifest.json").write_text(
        json.dumps(corpus_manifest, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return corpus_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--report-dir", type=Path)
    parser.add_argument("--stride", type=int, default=20)
    parser.add_argument("--require-matr-batch2", action="store_true")
    args = parser.parse_args()
    paths = DataCenterPaths(args.data_root) if args.data_root else DataCenterPaths.from_config()
    output_dir = args.output_dir or paths.public_battery_canonical_dir / "public_battery_corpus_v1"
    report_dir = args.report_dir or paths.public_battery_reports_dir / "public_battery_corpus_v1"
    result = build_public_battery_corpus(
        paths.public_battery_raw_dir,
        output_dir,
        report_dir,
        stride=args.stride,
        require_matr_batch2=args.require_matr_batch2,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
