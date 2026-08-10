"""Build a traceable five-target sample table from NASA PCoE aging data."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat

from src.project_paths import DataCenterPaths


CELL_IDS = ("B0005", "B0006", "B0007", "B0018")
TARGET_COLUMNS = ("soc", "soh", "soe", "rul_cycles", "sot_c")
FEATURE_COLUMNS = ("voltage_v", "current_a", "temperature_c", "dv_dt_v_s")
CSV_COLUMNS = (
    "cell_id", "cycle_id", "time_s", "split", "source_file", *FEATURE_COLUMNS, *TARGET_COLUMNS,
)


def fixed_cell_split(cell_ids: list[str]) -> dict[str, list[str]]:
    if sorted(cell_ids) != list(CELL_IDS):
        raise ValueError("Expected exactly NASA cells B0005, B0006, B0007, B0018")
    return {"train": ["B0005", "B0006"], "validation": ["B0007"], "test": ["B0018"]}


def derive_cycle_labels(*, capacity_ah: float, initial_capacity_ah: float,
                        remaining_energy_wh: float, initial_energy_wh: float,
                        cycle_index: int, eol_cycle_index: int) -> dict[str, float | int]:
    if initial_capacity_ah <= 0 or initial_energy_wh <= 0:
        raise ValueError("Initial capacity and energy must be positive.")
    return {
        "soh": capacity_ah / initial_capacity_ah,
        "soe": remaining_energy_wh / initial_energy_wh,
        "rul_cycles": eol_cycle_index - cycle_index,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mat_path(raw_dir: Path, cell_id: str) -> Path:
    matches = sorted(Path(raw_dir).rglob(f"{cell_id}.mat"))
    if len(matches) != 1:
        raise ValueError(f"Expected one source file for {cell_id}, found {len(matches)}")
    return matches[0]


def _discharge_cycles(path: Path, cell_id: str) -> list[object]:
    battery = loadmat(path, squeeze_me=True, struct_as_record=False)[cell_id]
    cycles = []
    for cycle in battery.cycle:
        fields = set(cycle.data._fieldnames)
        required = {"Voltage_measured", "Current_measured", "Temperature_measured", "Time", "Capacity"}
        if cycle.type == "discharge" and required.issubset(fields):
            cycles.append(cycle)
    if not cycles:
        raise ValueError(f"{cell_id} has no usable discharge cycles.")
    return cycles


def _energy_wh(voltage: np.ndarray, current: np.ndarray, time_s: np.ndarray) -> tuple[np.ndarray, float]:
    dt_s = np.diff(time_s, prepend=time_s[0])
    increments = np.maximum(np.abs(voltage * current) * dt_s / 3600.0, 0.0)
    remaining = np.cumsum(increments[::-1])[::-1]
    return remaining, float(remaining[0])


def _rows_for_cell(cell_id: str, source: Path, split: str) -> tuple[list[dict[str, object]], dict[str, object]]:
    cycles = _discharge_cycles(source, cell_id)
    capacities = [float(cycle.data.Capacity) for cycle in cycles]
    initial_capacity = capacities[0]
    eol_cycle = next((index + 1 for index, capacity in enumerate(capacities) if capacity / initial_capacity <= 0.70), None)
    if eol_cycle is None:
        raise ValueError(f"{cell_id} does not reach the 70% SOH end-of-life threshold.")

    first_voltage = np.asarray(cycles[0].data.Voltage_measured, dtype=np.float64)
    first_current = np.asarray(cycles[0].data.Current_measured, dtype=np.float64)
    first_time = np.asarray(cycles[0].data.Time, dtype=np.float64)
    _, initial_energy = _energy_wh(first_voltage, first_current, first_time)
    rows: list[dict[str, object]] = []
    for cycle_index, cycle in enumerate(cycles[:eol_cycle], start=1):
        voltage = np.asarray(cycle.data.Voltage_measured, dtype=np.float64)
        current = np.asarray(cycle.data.Current_measured, dtype=np.float64)
        temperature = np.asarray(cycle.data.Temperature_measured, dtype=np.float64)
        time_s = np.asarray(cycle.data.Time, dtype=np.float64)
        if not (len(voltage) == len(current) == len(temperature) == len(time_s) and len(time_s) >= 2):
            continue
        remaining_energy, _ = _energy_wh(voltage, current, time_s)
        labels = derive_cycle_labels(
            capacity_ah=capacities[cycle_index - 1], initial_capacity_ah=initial_capacity,
            remaining_energy_wh=1.0, initial_energy_wh=initial_energy,
            cycle_index=cycle_index, eol_cycle_index=eol_cycle,
        )
        total_ah = np.cumsum(np.maximum(np.abs(current) * np.diff(time_s, prepend=time_s[0]) / 3600.0, 0.0))
        soc = 1.0 - total_ah / max(float(total_ah[-1]), 1e-12)
        dv_dt = np.gradient(voltage, time_s)
        for index in range(len(time_s)):
            sample_labels = dict(labels)
            sample_labels["soe"] = float(remaining_energy[index] / initial_energy)
            rows.append({
                "cell_id": cell_id, "cycle_id": cycle_index, "time_s": float(time_s[index]),
                "split": split, "source_file": str(source.resolve()),
                "voltage_v": float(voltage[index]), "current_a": float(current[index]),
                "temperature_c": float(temperature[index]), "dv_dt_v_s": float(dv_dt[index]),
                "soc": float(np.clip(soc[index], 0.0, 1.0)), "soh": float(sample_labels["soh"]),
                "soe": float(np.clip(sample_labels["soe"], 0.0, 1.0)),
                "rul_cycles": int(sample_labels["rul_cycles"]), "sot_c": float(temperature[index]),
            })
    return rows, {"initial_capacity_ah": initial_capacity, "initial_energy_wh": initial_energy, "eol_cycle_index": eol_cycle, "discharge_cycles": len(cycles)}


def prepare_multistate_dataset(raw_dir: Path, output_dir: Path, eol_soh: float = 0.70) -> dict[str, object]:
    if eol_soh != 0.70:
        raise ValueError("This approved task fixes the end-of-life SOH threshold at 0.70.")
    raw_dir, output_dir = Path(raw_dir), Path(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"Output directory must be empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    split = fixed_cell_split(list(CELL_IDS))
    role_by_cell = {cell: role for role, cells in split.items() for cell in cells}
    all_rows: list[dict[str, object]] = []
    cells_audit: dict[str, object] = {}
    for cell_id in CELL_IDS:
        source = _mat_path(raw_dir, cell_id)
        rows, audit = _rows_for_cell(cell_id, source, role_by_cell[cell_id])
        all_rows.extend(rows)
        cells_audit[cell_id] = {**audit, "source_file": str(source.resolve()), "sha256": _sha256(source)}
    counts = {role: {target: sum(1 for row in all_rows if row["split"] == role and row[target] is not None) for target in TARGET_COLUMNS} for role in split}
    if any(count == 0 for role in counts.values() for count in role.values()):
        raise ValueError("Every target requires non-empty train, validation, and test labels.")
    csv_path = output_dir / "nasa_multistate_samples.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader(); writer.writerows(all_rows)
    manifest = {"split": split, "targets": TARGET_COLUMNS, "features": FEATURE_COLUMNS, "label_version": "nasa_multistate_v1"}
    (output_dir / "split_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "data_dictionary.json").write_text(json.dumps({"columns": CSV_COLUMNS, "label_definitions": {"soc": "coulomb-counted discharge fraction", "soh": "cycle capacity / initial capacity", "soe": "remaining discharge energy / initial energy", "rul_cycles": "cycles to first 70% SOH", "sot_c": "measured cell temperature"}}, ensure_ascii=False, indent=2), encoding="utf-8")
    audit = {"source": "NASA PCoE Battery Data Set", "cells": cells_audit, "label_counts": counts, "rows": len(all_rows)}
    (output_dir / "data_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    return audit


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare NASA five-target battery samples.")
    parser.add_argument("--data-root", type=Path, help="Configured SOC data-center root.")
    args = parser.parse_args()
    paths = DataCenterPaths(args.data_root) if args.data_root else DataCenterPaths.from_config()
    audit = prepare_multistate_dataset(paths.nasa_raw_dir / "extracted", paths.nasa_training_dir)
    print(json.dumps(audit, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
