"""Prepare leakage-audited state and lifecycle tables from NASA RW9--RW12 data."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.io import loadmat

from src.data_processing.prepare_nasa_randomized import CELL_IDS, _mat_path, _reference_steps, capacity_ah
from src.project_paths import DataCenterPaths


STATE_COLUMNS = (
    "cell_id", "cycle_id", "time_s", "source_file", "voltage_v", "current_a", "temperature_c",
    "dv_dt_v_s", "soc", "soe", "sot_5min_c",
)
LIFECYCLE_COLUMNS = (
    "cell_id", "cycle_id", "cycle_index", "cumulative_throughput_ah", "capacity_ah",
    "soh_history_mean", "capacity_drop_ah", "capacity_slope_3", "voltage_mean_v", "voltage_std_v",
    "temperature_mean_c", "temperature_max_c", "discharge_duration_s", "soh", "rul_cycles",
)


@dataclass(frozen=True)
class CycleSummary:
    cell_id: str
    cycle_id: int
    capacity_ah: float
    voltage_mean_v: float
    voltage_std_v: float
    temperature_mean_c: float
    temperature_max_c: float
    discharge_duration_s: float
    rul_cycles: int


def first_future_temperature(
    time_s: np.ndarray, temperature_c: np.ndarray, index: int, horizon_s: float,
) -> float | None:
    """Return the first observed temperature at least ``horizon_s`` after a sample."""
    future = np.flatnonzero(time_s >= time_s[index] + horizon_s)
    return None if future.size == 0 else float(temperature_c[int(future[0])])


def validate_future_temperature_rows(
    rows: list[dict[str, object]], horizon_s: float,
) -> dict[str, int | float]:
    """Reject a mislabeled current-temperature task before persisting the dataset."""
    if horizon_s <= 0:
        raise ValueError("Future-temperature horizon must be positive.")
    if not rows:
        raise ValueError("Future-temperature rows must not be empty.")
    identity_count = 0
    for row in rows:
        try:
            current = float(row["temperature_c"])
            future = float(row["sot_5min_c"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("Future-temperature rows require numeric temperature_c and sot_5min_c.") from error
        identity_count += int(abs(current - future) <= 1e-9)
    if identity_count == len(rows):
        raise ValueError("Future-temperature labels are identical to current temperature for every row.")
    return {"row_count": len(rows), "identity_count": identity_count, "horizon_s": float(horizon_s)}


def make_lifecycle_rows(cycles: list[CycleSummary]) -> list[dict[str, float | int | str]]:
    """Derive only causal cycle-history features; SOH/RUL remain labels, not inputs."""
    if not cycles:
        return []
    initial_capacity = float(cycles[0].capacity_ah)
    if initial_capacity <= 0:
        raise ValueError("The first cycle capacity must be positive.")
    rows: list[dict[str, float | int | str]] = []
    capacities: list[float] = []
    cumulative_throughput = 0.0
    for cycle in cycles:
        capacity = float(cycle.capacity_ah)
        history = capacities if capacities else [initial_capacity]
        trailing = history[max(0, len(history) - 3):]
        slope = 0.0 if len(trailing) < 2 else (trailing[-1] - trailing[0]) / (len(trailing) - 1)
        rows.append({
            "cell_id": cycle.cell_id,
            "cycle_id": cycle.cycle_id,
            "cycle_index": cycle.cycle_id,
            "cumulative_throughput_ah": cumulative_throughput,
            "capacity_ah": capacity,
            "soh_history_mean": float(np.mean(history) / initial_capacity),
            "capacity_drop_ah": initial_capacity - history[-1],
            "capacity_slope_3": slope,
            "voltage_mean_v": cycle.voltage_mean_v,
            "voltage_std_v": cycle.voltage_std_v,
            "temperature_mean_c": cycle.temperature_mean_c,
            "temperature_max_c": cycle.temperature_max_c,
            "discharge_duration_s": cycle.discharge_duration_s,
            "soh": capacity / initial_capacity,
            "rul_cycles": cycle.rul_cycles,
        })
        capacities.append(capacity)
        cumulative_throughput += capacity
    return rows


def _atomic_csv(path: Path, columns: tuple[str, ...], rows: list[dict[str, object]]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def _atomic_json(path: Path, payload: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _rows_for_cell(cell_id: str, source: Path, horizon_s: float, sample_stride: int) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    steps = _reference_steps(source)
    capacities = [capacity_ah(np.asarray(step.current, dtype=float), np.asarray(step.time, dtype=float)) for step in steps]
    initial_capacity = capacities[0]
    eol_cycle = next((index for index, value in enumerate(capacities) if value / initial_capacity <= 0.70), None)
    if eol_cycle is None:
        raise ValueError(f"{cell_id} does not reach the 70% SOH end-of-life threshold.")
    retained_steps = steps[: eol_cycle + 1]
    initial_time = np.asarray(retained_steps[0].time, dtype=float)
    initial_voltage = np.asarray(retained_steps[0].voltage, dtype=float)
    initial_current = np.asarray(retained_steps[0].current, dtype=float)
    initial_energy = float(np.trapezoid(np.abs(initial_voltage * initial_current), initial_time) / 3600.0)
    state_rows: list[dict[str, object]] = []
    summaries: list[CycleSummary] = []
    omitted_future_sot = 0
    for cycle_id, step in enumerate(retained_steps):
        time_s = np.asarray(step.time, dtype=float)
        voltage = np.asarray(step.voltage, dtype=float)
        current = np.asarray(step.current, dtype=float)
        temperature = np.asarray(step.temperature, dtype=float)
        if not (len(time_s) >= 2 and len(time_s) == len(voltage) == len(current) == len(temperature)):
            continue
        dt_s = np.diff(time_s, prepend=time_s[0])
        discharged_ah = np.cumsum(np.maximum(np.abs(current) * dt_s / 3600.0, 0.0))
        soc = 1.0 - discharged_ah / max(float(discharged_ah[-1]), 1e-12)
        energy_increment = np.maximum(np.abs(voltage * current) * dt_s / 3600.0, 0.0)
        remaining_energy = np.cumsum(energy_increment[::-1])[::-1]
        dv_dt = np.gradient(voltage, time_s)
        summaries.append(CycleSummary(
            cell_id, cycle_id, capacities[cycle_id], float(np.mean(voltage)), float(np.std(voltage)),
            float(np.mean(temperature)), float(np.max(temperature)), float(time_s[-1] - time_s[0]), eol_cycle - cycle_id,
        ))
        for index in range(0, len(time_s), sample_stride):
            future_temperature = first_future_temperature(time_s, temperature, index, horizon_s)
            if future_temperature is None:
                omitted_future_sot += 1
                continue
            state_rows.append({
                "cell_id": cell_id, "cycle_id": cycle_id, "time_s": float(time_s[index]),
                "source_file": str(source.resolve()), "voltage_v": float(voltage[index]),
                "current_a": float(current[index]), "temperature_c": float(temperature[index]),
                "dv_dt_v_s": float(dv_dt[index]), "soc": float(np.clip(soc[index], 0.0, 1.0)),
                "soe": float(np.clip(remaining_energy[index] / max(initial_energy, 1e-12), 0.0, 1.0)),
                "sot_5min_c": future_temperature,
            })
    lifecycle_rows = make_lifecycle_rows(summaries)
    return state_rows, lifecycle_rows, {
        "source_file": str(source.resolve()), "reference_cycles": len(steps), "retained_cycles": len(summaries),
        "eol_reference_cycle": eol_cycle, "initial_capacity_ah": initial_capacity,
        "future_sot_omissions": omitted_future_sot,
    }


def prepare_improved_nasa_dataset(
    raw_dir: Path, output_dir: Path, horizon_s: float = 300.0, sample_stride: int = 10, overwrite: bool = False,
) -> dict[str, object]:
    """Create separate state and cycle-level NASA tables without overwriting prior outputs."""
    if horizon_s <= 0 or sample_stride < 1:
        raise ValueError("horizon_s must be positive and sample_stride must be at least one.")
    output_dir = Path(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()) and not overwrite:
        raise ValueError(f"Output directory must be empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    all_state_rows: list[dict[str, object]] = []
    all_lifecycle_rows: list[dict[str, object]] = []
    cell_audit: dict[str, object] = {}
    for cell_id in CELL_IDS:
        source = _mat_path(raw_dir, cell_id)
        state_rows, lifecycle_rows, audit = _rows_for_cell(cell_id, source, horizon_s, sample_stride)
        all_state_rows.extend(state_rows)
        all_lifecycle_rows.extend(lifecycle_rows)
        cell_audit[cell_id] = audit
    if not all_state_rows or not all_lifecycle_rows:
        raise ValueError("No usable NASA state or lifecycle rows were produced.")
    future_temperature_audit = validate_future_temperature_rows(all_state_rows, horizon_s)
    _atomic_csv(output_dir / "nasa_state_future_samples.csv", STATE_COLUMNS, all_state_rows)
    _atomic_csv(output_dir / "nasa_lifecycle_cycles.csv", LIFECYCLE_COLUMNS, all_lifecycle_rows)
    manifest = {"cells": list(CELL_IDS), "state_targets": ["soc", "soe", "sot_5min_c"],
                "lifecycle_targets": ["soh", "rul_cycles"], "sot_horizon_s": horizon_s,
                "sample_stride": sample_stride, "label_version": "nasa_lifecycle_v1"}
    _atomic_json(output_dir / "split_manifest.json", manifest)
    audit = {"source": "NASA PCoE Randomized Battery Usage Data Set", "cells": cell_audit,
             "state_rows": len(all_state_rows), "lifecycle_rows": len(all_lifecycle_rows),
             "targets": manifest["state_targets"] + manifest["lifecycle_targets"],
             "sot_horizon_s": horizon_s,
             "future_temperature_identity_count": future_temperature_audit["identity_count"]}
    _atomic_json(output_dir / "data_audit.json", audit)
    return audit


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare leakage-audited NASA lifecycle data.")
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--horizon-s", type=float, default=300.0)
    parser.add_argument("--sample-stride", type=int, default=10)
    args = parser.parse_args()
    paths = DataCenterPaths(args.data_root) if args.data_root else DataCenterPaths.from_config()
    output_dir = args.output_dir or paths.nasa_improved_training_dir
    print(json.dumps(prepare_improved_nasa_dataset(paths.nasa_raw_dir / "randomized", output_dir, args.horizon_s, args.sample_stride), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
