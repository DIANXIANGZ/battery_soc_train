"""Prepare five-target samples from NASA randomized reference-discharge cycles."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat

from src.project_paths import DataCenterPaths


CELL_IDS = ("RW9", "RW10", "RW11", "RW12")
COLUMNS = ("cell_id", "cycle_id", "time_s", "split", "source_file", "voltage_v", "current_a", "temperature_c", "dv_dt_v_s", "soc", "soh", "soe", "rul_cycles", "sot_c")


def capacity_ah(current_a: np.ndarray, time_s: np.ndarray) -> float:
    return float(np.trapezoid(np.abs(current_a), time_s) / 3600.0)


def randomized_cell_split(cell_ids: list[str]) -> dict[str, list[str]]:
    if set(cell_ids) != set(CELL_IDS) or len(cell_ids) != len(CELL_IDS):
        raise ValueError("Expected randomized cells RW9, RW10, RW11, RW12")
    return {"train": ["RW9", "RW10"], "validation": ["RW11"], "test": ["RW12"]}


def _mat_path(raw_dir: Path, cell_id: str) -> Path:
    matches = sorted(Path(raw_dir).rglob(f"{cell_id}.mat"))
    if len(matches) != 1:
        raise ValueError(f"Expected one {cell_id}.mat file, found {len(matches)}")
    return matches[0]


def _reference_steps(source: Path) -> list[object]:
    steps = loadmat(source, squeeze_me=True, struct_as_record=False)["data"].step
    rows = [step for step in steps if step.comment == "reference discharge"]
    if not rows:
        raise ValueError(f"No reference-discharge steps in {source.name}")
    return rows


def _rows_for_cell(cell_id: str, source: Path, split: str, stride: int) -> tuple[list[dict[str, object]], dict[str, object]]:
    steps = _reference_steps(source)
    capacities = [capacity_ah(np.asarray(step.current, dtype=float), np.asarray(step.time, dtype=float)) for step in steps]
    initial = capacities[0]
    eol = next((index for index, value in enumerate(capacities) if value / initial <= 0.70), None)
    if eol is None:
        raise ValueError(f"{cell_id} does not reach 70% SOH in reference-discharge records")
    initial_energy = float(np.trapezoid(np.abs(np.asarray(steps[0].voltage, dtype=float) * np.asarray(steps[0].current, dtype=float)), np.asarray(steps[0].time, dtype=float)) / 3600.0)
    rows: list[dict[str, object]] = []
    for cycle_index, step in enumerate(steps[:eol + 1]):
        time_s = np.asarray(step.time, dtype=float)
        voltage = np.asarray(step.voltage, dtype=float)
        current = np.asarray(step.current, dtype=float)
        temperature = np.asarray(step.temperature, dtype=float)
        dt = np.diff(time_s, prepend=time_s[0])
        consumed_ah = np.cumsum(np.maximum(np.abs(current) * dt / 3600.0, 0.0))
        soc = 1.0 - consumed_ah / max(consumed_ah[-1], 1e-12)
        energy_increment = np.maximum(np.abs(voltage * current) * dt / 3600.0, 0.0)
        remaining_energy = np.cumsum(energy_increment[::-1])[::-1]
        dv_dt = np.gradient(voltage, time_s)
        for index in range(0, len(time_s), stride):
            rows.append({"cell_id": cell_id, "cycle_id": cycle_index, "time_s": float(time_s[index]), "split": split, "source_file": str(source.resolve()), "voltage_v": float(voltage[index]), "current_a": float(current[index]), "temperature_c": float(temperature[index]), "dv_dt_v_s": float(dv_dt[index]), "soc": float(np.clip(soc[index], 0.0, 1.0)), "soh": float(capacities[cycle_index] / initial), "soe": float(np.clip(remaining_energy[index] / initial_energy, 0.0, 1.0)), "rul_cycles": int(eol - cycle_index), "sot_c": float(temperature[index])})
    return rows, {"reference_cycles": len(steps), "initial_capacity_ah": initial, "eol_reference_cycle": eol, "initial_energy_wh": initial_energy}


def prepare_randomized_dataset(raw_dir: Path, output_dir: Path, sample_stride: int = 10) -> dict[str, object]:
    if sample_stride < 1:
        raise ValueError("sample_stride must be at least one")
    output_dir = Path(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"Output directory must be empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    split = randomized_cell_split(list(CELL_IDS))
    roles = {cell: role for role, cells in split.items() for cell in cells}
    all_rows: list[dict[str, object]] = []
    cells: dict[str, object] = {}
    for cell_id in CELL_IDS:
        source = _mat_path(raw_dir, cell_id)
        rows, audit = _rows_for_cell(cell_id, source, roles[cell_id], sample_stride)
        all_rows.extend(rows); cells[cell_id] = {**audit, "source_file": str(source.resolve())}
    with (output_dir / "nasa_randomized_multistate_samples.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS); writer.writeheader(); writer.writerows(all_rows)
    counts = {role: sum(1 for row in all_rows if row["split"] == role) for role in split}
    if any(value == 0 for value in counts.values()):
        raise ValueError("Every split must contain samples")
    audit = {"source": "NASA PCoE Randomized Battery Usage Data Set", "sample_stride": sample_stride, "split": split, "rows_by_split": counts, "cells": cells, "targets": ["soc", "soh", "soe", "rul_cycles", "sot_c"]}
    (output_dir / "data_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "split_manifest.json").write_text(json.dumps(split, ensure_ascii=False, indent=2), encoding="utf-8")
    return audit


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare NASA randomized five-target samples.")
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--sample-stride", type=int, default=10)
    args = parser.parse_args()
    paths = DataCenterPaths(args.data_root) if args.data_root else DataCenterPaths.from_config()
    print(json.dumps(prepare_randomized_dataset(paths.nasa_raw_dir / "randomized", paths.nasa_training_dir, args.sample_stride), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
