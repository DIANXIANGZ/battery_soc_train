"""Audit helpers for five-target NASA prediction workbooks."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np


TARGET_UNITS = {
    "soc": "fraction",
    "soh": "fraction",
    "soe": "fraction",
    "rul_cycles": "cycles",
    "sot_c": "degC",
}


def summarize_target_errors(rows: list[dict[str, str]], target: str) -> dict[str, float | int | str]:
    """Return raw-unit MAE/RMSE from a saved prediction table."""

    if target not in TARGET_UNITS:
        raise ValueError(f"Unknown multi-state target: {target}")
    reference_key, prediction_key = f"reference_{target}", f"predicted_{target}"
    try:
        reference = np.asarray([float(row[reference_key]) for row in rows], dtype=np.float64)
        prediction = np.asarray([float(row[prediction_key]) for row in rows], dtype=np.float64)
    except KeyError as exc:
        raise ValueError(f"Prediction rows are missing required column: {exc.args[0]}") from exc
    if reference.size == 0:
        raise ValueError("Prediction rows are empty.")
    error = prediction - reference
    return {"MAE": float(np.mean(np.abs(error))), "RMSE": float(np.sqrt(np.mean(error ** 2))), "n_test": int(error.size), "unit": TARGET_UNITS[target]}


def read_prediction_table(path: Path) -> list[dict[str, str]]:
    """Load an auditable prediction CSV without changing its values."""

    with Path(path).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("Prediction CSV contains no rows.")
    return rows
