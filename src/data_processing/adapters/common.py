"""Shared mechanics for source-specific battery adapters."""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd

from src.research.battery_schema import SAMPLE_GROUP_COLUMNS, validate_canonical_samples


def canonicalize_samples(
    frame: pd.DataFrame,
    *,
    source_id: str,
    chemistry: str,
    aliases: Mapping[str, str],
    source_hash: str,
) -> pd.DataFrame:
    output = frame.rename(columns=dict(aliases)).copy()
    output["source_id"] = source_id
    if "chemistry" not in output.columns:
        output["chemistry"] = chemistry
    output["source_hash"] = source_hash.lower()
    required_measurements = ("timestamp_s", "voltage_v", "current_a", "temperature_c")
    missing = [column for column in (*SAMPLE_GROUP_COLUMNS[1:], *required_measurements) if column not in output.columns]
    if missing:
        raise ValueError(f"Source table is missing adapter fields: {missing}")
    numeric = (*required_measurements, "cycle_id")
    for column in numeric:
        output[column] = pd.to_numeric(output[column], errors="raise")
    output = output.sort_values([*SAMPLE_GROUP_COLUMNS, "timestamp_s"], kind="stable").reset_index(drop=True)
    validate_canonical_samples(output)
    return output


def attach_causal_cycle_references(
    frame: pd.DataFrame,
    *,
    nominal_capacity_ah: float,
    nominal_voltage_v: float,
) -> pd.DataFrame:
    """Attach fixed pre-cycle references, updating them only after a cycle completes."""

    if nominal_capacity_ah <= 0 or nominal_voltage_v <= 0:
        raise ValueError("Nominal capacity and voltage must be positive")
    output = frame.sort_values([*SAMPLE_GROUP_COLUMNS, "timestamp_s"], kind="stable").copy()
    for column in ("capacity_reference_ah", "energy_reference_wh", "initial_soc", "initial_soe"):
        output[column] = np.nan
    for _, cell_positions in output.groupby(["source_id", "cell_id"], sort=False).groups.items():
        cell = output.loc[list(cell_positions)]
        previous_capacity_ah = nominal_capacity_ah
        previous_energy_wh = nominal_capacity_ah * nominal_voltage_v
        for _, cycle_positions in cell.groupby(["session_id", "cycle_id"], sort=False).groups.items():
            index = np.asarray(list(cycle_positions))
            cycle = output.loc[index]
            output.loc[index, "capacity_reference_ah"] = previous_capacity_ah
            output.loc[index, "energy_reference_wh"] = previous_energy_wh
            output.loc[index, "initial_soc"] = 1.0
            output.loc[index, "initial_soe"] = 1.0
            if "Discharge_Capacity(Ah)" in cycle:
                recorded_capacity = pd.to_numeric(cycle["Discharge_Capacity(Ah)"], errors="coerce")
                current_capacity_ah = float(recorded_capacity.max())
            else:
                time_s = cycle["timestamp_s"].to_numpy(dtype=float)
                current = cycle["current_a"].to_numpy(dtype=float)
                dt_s = np.diff(time_s, prepend=time_s[0])
                current_capacity_ah = float(np.sum(np.abs(current) * np.maximum(dt_s, 0.0)) / 3600.0)
            time_s = cycle["timestamp_s"].to_numpy(dtype=float)
            voltage = cycle["voltage_v"].to_numpy(dtype=float)
            current = cycle["current_a"].to_numpy(dtype=float)
            dt_s = np.diff(time_s, prepend=time_s[0])
            current_energy_wh = float(np.sum(
                np.abs(voltage * current) * np.maximum(dt_s, 0.0)
            ) / 3600.0)
            if np.isfinite(current_capacity_ah) and current_capacity_ah > 0:
                previous_capacity_ah = current_capacity_ah
            if np.isfinite(current_energy_wh) and current_energy_wh > 0:
                previous_energy_wh = current_energy_wh
    return output
