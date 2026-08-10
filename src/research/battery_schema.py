"""Canonical schemas and causal target derivation for public battery data."""

from __future__ import annotations

import re

import numpy as np
import pandas as pd


SAMPLE_REQUIRED_COLUMNS = (
    "source_id", "chemistry", "cell_id", "session_id", "cycle_id", "timestamp_s",
    "voltage_v", "current_a", "temperature_c", "source_hash",
)
CYCLE_REQUIRED_COLUMNS = (
    "source_id", "chemistry", "cell_id", "cycle_id", "capacity_ah", "energy_wh",
    "soh", "rul_cycles", "rul_observed", "eol_provenance", "source_hash",
)
SAMPLE_GROUP_COLUMNS = ("source_id", "cell_id", "session_id", "cycle_id")


def validate_canonical_samples(frame: pd.DataFrame) -> None:
    missing = sorted(set(SAMPLE_REQUIRED_COLUMNS) - set(frame.columns))
    if missing:
        raise ValueError(f"Canonical sample columns missing: {missing}")
    if frame[list(SAMPLE_GROUP_COLUMNS)].isna().any().any():
        raise ValueError("Canonical group identifiers must not be null")
    if not frame["source_hash"].astype(str).map(lambda value: bool(re.fullmatch(r"[0-9a-f]{64}", value))).all():
        raise ValueError("Every canonical sample requires a lowercase SHA-256 source hash")
    for _, group in frame.groupby(list(SAMPLE_GROUP_COLUMNS), sort=False):
        if not pd.to_numeric(group["timestamp_s"], errors="coerce").is_monotonic_increasing:
            raise ValueError("Canonical timestamps must be sorted within every group")


def derive_state_targets(frame: pd.DataFrame, horizon_s: float = 300.0) -> pd.DataFrame:
    """Derive causal SOC/SOE references and same-cycle future temperature labels."""

    if horizon_s <= 0:
        raise ValueError("horizon_s must be positive")
    reference_columns = ("capacity_reference_ah", "energy_reference_wh", "initial_soc", "initial_soe")
    missing_references = [column for column in reference_columns if column not in frame]
    if missing_references:
        raise ValueError(f"Causal state-reference columns missing: {missing_references}")
    validate_canonical_samples(frame)
    output = frame.sort_values([*SAMPLE_GROUP_COLUMNS, "timestamp_s"], kind="stable").copy()
    output["soc"] = np.nan
    output["soe"] = np.nan
    output["sot_c"] = np.nan
    for _, positions in output.groupby(list(SAMPLE_GROUP_COLUMNS), sort=False).groups.items():
        index = np.asarray(list(positions))
        group = output.loc[index]
        time_s = group["timestamp_s"].to_numpy(dtype=float)
        voltage = group["voltage_v"].to_numpy(dtype=float)
        current = group["current_a"].to_numpy(dtype=float)
        temperature = group["temperature_c"].to_numpy(dtype=float)
        if len(group) < 2 or np.any(np.diff(time_s) < 0):
            continue
        references = {
            column: group[column].to_numpy(dtype=float)
            for column in reference_columns
        }
        if any(not np.isfinite(values).all() or not np.allclose(values, values[0]) for values in references.values()):
            raise ValueError("Causal state references must be finite and constant within each cycle")
        capacity_reference = float(references["capacity_reference_ah"][0])
        energy_reference = float(references["energy_reference_wh"][0])
        if capacity_reference <= 0 or energy_reference <= 0:
            raise ValueError("Causal capacity and energy references must be positive")
        native_columns = ("native_cumulative_charge_ah", "native_cumulative_energy_wh")
        if all(column in group and group[column].notna().all() for column in native_columns):
            cumulative_charge = group[native_columns[0]].to_numpy(dtype=float)
            cumulative_energy = group[native_columns[1]].to_numpy(dtype=float)
            if (
                not np.isfinite(cumulative_charge).all()
                or not np.isfinite(cumulative_energy).all()
                or np.any(np.diff(cumulative_charge) < -1e-12)
                or np.any(np.diff(cumulative_energy) < -1e-12)
            ):
                raise ValueError("Native causal state counters must be finite and nondecreasing")
        else:
            dt_s = np.diff(time_s, prepend=time_s[0])
            charge_increment = np.abs(current) * np.maximum(dt_s, 0.0) / 3600.0
            energy_increment = np.abs(voltage * current) * np.maximum(dt_s, 0.0) / 3600.0
            cumulative_charge = np.cumsum(charge_increment)
            cumulative_energy = np.cumsum(energy_increment)
        output.loc[index, "soc"] = np.clip(
            float(references["initial_soc"][0]) - cumulative_charge / capacity_reference,
            0.0, 1.0,
        )
        output.loc[index, "soe"] = np.clip(
            float(references["initial_soe"][0]) - cumulative_energy / energy_reference,
            0.0, 1.0,
        )
        future_positions = np.searchsorted(time_s, time_s + horizon_s, side="left")
        valid = future_positions < len(time_s)
        future = np.full(len(time_s), np.nan, dtype=float)
        future[valid] = temperature[future_positions[valid]]
        output.loc[index, "sot_c"] = future
    return output


def derive_cycle_targets(frame: pd.DataFrame, eol_soh: float = 0.8) -> pd.DataFrame:
    """Derive SOH and observed/censored RUL without inventing EOL at dataset end."""

    required = {"source_id", "chemistry", "cell_id", "cycle_id", "capacity_ah", "energy_wh", "source_hash"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Canonical cycle columns missing: {missing}")
    if not 0 < eol_soh < 1:
        raise ValueError("eol_soh must be between zero and one")
    output = frame.sort_values(["source_id", "cell_id", "cycle_id"], kind="stable").copy()
    output["soh"] = np.nan
    output["rul_cycles"] = np.nan
    output["rul_observed"] = 0
    if "eol_provenance" not in output:
        output["eol_provenance"] = ""
    for _, positions in output.groupby(["source_id", "cell_id"], sort=False).groups.items():
        index = np.asarray(list(positions))
        capacity = output.loc[index, "capacity_ah"].to_numpy(dtype=float)
        if not len(capacity) or not np.isfinite(capacity[0]) or capacity[0] <= 0:
            continue
        soh = capacity / capacity[0]
        output.loc[index, "soh"] = soh
        provenance_values = output.loc[index, "eol_provenance"].dropna().astype(str)
        explicit_provenance = provenance_values.iloc[0] if not provenance_values.empty else ""
        if explicit_provenance == "right_censored":
            output.loc[index, "eol_provenance"] = "right_censored"
            continue
        if "eol_cycle" in output:
            eol_values = pd.to_numeric(output.loc[index, "eol_cycle"], errors="coerce").to_numpy(dtype=float)
            finite_eol = eol_values[np.isfinite(eol_values)]
            observed_eol = (
                pd.to_numeric(output.loc[index, "eol_cycle_observed"], errors="coerce").fillna(0).astype(bool).any()
                if "eol_cycle_observed" in output
                else False
            )
            cycle_values = pd.to_numeric(output.loc[index, "cycle_id"], errors="coerce").to_numpy(dtype=float)
            if observed_eol and finite_eol.size and np.isfinite(cycle_values).all():
                eol_cycle = float(finite_eol[0])
                output.loc[index, "rul_cycles"] = np.maximum(eol_cycle - cycle_values, 0.0)
                output.loc[index, "rul_observed"] = 1
                if explicit_provenance:
                    output.loc[index, "eol_provenance"] = explicit_provenance
                else:
                    output.loc[index, "eol_provenance"] = "observed_eol_crossing"
                continue
        crossings = np.flatnonzero(soh <= eol_soh)
        if crossings.size:
            eol_position = int(crossings[0])
            cycle_values = pd.to_numeric(output.loc[index, "cycle_id"], errors="coerce").to_numpy(dtype=float)
            if np.isfinite(cycle_values).all():
                output.loc[index, "rul_cycles"] = np.maximum(cycle_values[eol_position] - cycle_values, 0.0)
            else:
                output.loc[index, "rul_cycles"] = np.maximum(eol_position - np.arange(len(index)), 0).astype(float)
            output.loc[index, "rul_observed"] = 1
            output.loc[index, "eol_provenance"] = "observed_eol_crossing"
        else:
            output.loc[index, "eol_provenance"] = "right_censored"
    return output
