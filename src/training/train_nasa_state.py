"""Three-target state model for SOC, SOE, and genuinely future temperature."""

from __future__ import annotations

import csv
import json
import random
from pathlib import Path
from typing import Any

from src.training.battery_protocol import acceptance

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from src.evaluation.nasa_loco import LocoFold, assert_no_fold_leakage
from src.training.train_multistate_lstm import metric_summary


FEATURES = ("voltage_v", "current_a", "temperature_c", "dv_dt_v_s")
TARGETS = ("soc", "soe", "sot_5min_c")
UNITS = {"soc": "fraction", "soe": "fraction", "sot_5min_c": "degC"}


def compose_future_temperature(last_temperature: torch.Tensor, predicted_delta: torch.Tensor) -> torch.Tensor:
    """Compose an absolute forecast from the persistence baseline and a learned residual."""
    if last_temperature.shape != predicted_delta.shape:
        raise ValueError("Temperature baseline and residual must have matching shapes.")
    return last_temperature + predicted_delta


def temperature_features(block: np.ndarray) -> np.ndarray:
    """Add causal power, temperature-change, and temperature-slope features to one window."""
    values = np.asarray(block, dtype=np.float32)
    if values.ndim != 2 or values.shape[1] != len(FEATURES) or len(values) == 0:
        raise ValueError("Temperature feature input must be a non-empty [time, feature] window.")
    power = values[:, 0] * values[:, 1]
    temperature_change = values[:, 2] - values[0, 2]
    temperature_slope = np.diff(values[:, 2], prepend=values[0, 2])
    return np.column_stack([values, power, temperature_change, temperature_slope]).astype(np.float32)


def _load_rows(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with Path(path).open(encoding="utf-8", newline="") as handle:
        for raw in csv.DictReader(handle):
            row: dict[str, object] = {"cell_id": raw["cell_id"], "cycle_id": int(raw["cycle_id"])}
            for field in FEATURES + TARGETS:
                row[field] = float(raw[field])
            rows.append(row)
    if not rows:
        raise ValueError("State CSV contains no rows.")
    return rows


def make_state_sequences(rows: list[dict[str, object]], window: int) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    if window < 1:
        raise ValueError("window must be at least one")
    grouped: dict[tuple[str, int], list[dict[str, object]]] = {}
    for row in rows:
        grouped.setdefault((str(row["cell_id"]), int(row["cycle_id"])), []).append(row)
    windows: list[list[list[float]]] = []
    targets = {target: [] for target in TARGETS}
    for group in grouped.values():
        for end in range(window - 1, len(group)):
            block = group[end - window + 1:end + 1]
            windows.append([[float(row[field]) for field in FEATURES] for row in block])
            for target in TARGETS:
                targets[target].append(float(group[end][target]))
    if not windows:
        raise ValueError("No valid state sequences were produced.")
    return np.asarray(windows, dtype=np.float32), {target: np.asarray(values, dtype=np.float32) for target, values in targets.items()}


def persistence_mae(last_temperature: np.ndarray, future_temperature: np.ndarray) -> float:
    return float(np.mean(np.abs(np.asarray(last_temperature, dtype=float) - np.asarray(future_temperature, dtype=float))))


class ElectricalStateLSTM(nn.Module):
    def __init__(self, n_features: int, hidden: int = 24) -> None:
        super().__init__()
        self.lstm = nn.LSTM(n_features, hidden, batch_first=True)
        self.head = nn.Linear(hidden, 2)

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        encoded, _ = self.lstm(inputs)
        return self.head(encoded[:, -1])


class TemperatureResidualLSTM(nn.Module):
    def __init__(self, n_features: int = 7, hidden: int = 16) -> None:
        super().__init__()
        self.lstm = nn.LSTM(n_features, hidden, batch_first=True)
        self.head = nn.Linear(hidden, 1)

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        encoded, _ = self.lstm(inputs)
        return self.head(encoded[:, -1]).squeeze(1)


def _split_sequences(rows: list[dict[str, object]], window: int, mean: np.ndarray | None = None, std: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    features, targets = make_state_sequences(rows, window)
    if mean is None or std is None:
        mean = features.reshape(-1, len(FEATURES)).mean(axis=0)
        std = features.reshape(-1, len(FEATURES)).std(axis=0)
        std[std < 1e-8] = 1.0
    normalized = (features - mean.reshape(1, 1, -1)) / std.reshape(1, 1, -1)
    labels = np.column_stack([targets[target] for target in TARGETS]).astype(np.float32)
    return normalized, labels, np.asarray([mean, std], dtype=np.float32)


def _fit_model(model: nn.Module, x_train: np.ndarray, y_train: np.ndarray,
               x_valid: np.ndarray, y_valid: np.ndarray, epochs: int) -> tuple[nn.Module, list[dict[str, float | int]]]:
    loader = DataLoader(TensorDataset(torch.from_numpy(x_train), torch.from_numpy(y_train)), batch_size=128, shuffle=True)
    optimizer = torch.optim.AdamW(model.parameters(), lr=3e-4, weight_decay=1e-4)
    best_loss, best_state, stale, history = float("inf"), None, 0, []
    for epoch in range(1, epochs + 1):
        model.train(); losses = []
        for inputs, labels in loader:
            optimizer.zero_grad(); loss = nn.functional.huber_loss(model(inputs), labels); loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0); optimizer.step(); losses.append(float(loss.detach()))
        model.eval()
        with torch.no_grad():
            validation_loss = float(nn.functional.huber_loss(model(torch.from_numpy(x_valid)), torch.from_numpy(y_valid)))
        history.append({"epoch": epoch, "train_loss": float(np.mean(losses)), "validation_loss": validation_loss})
        if validation_loss < best_loss:
            best_loss, stale = validation_loss, 0
            best_state = {name: value.detach().clone() for name, value in model.state_dict().items()}
        else:
            stale += 1
            if stale >= 6:
                break
    if best_state is None:
        raise RuntimeError("Training did not produce a checkpoint.")
    model.load_state_dict(best_state); model.eval()
    return model, history


def _write_prediction_csv(path: Path, fieldnames: tuple[str, ...], rows: list[dict[str, float]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames); writer.writeheader(); writer.writerows(rows)


def run_state_fold(data_path: Path, fold: LocoFold, results_dir: Path, window: int = 30, epochs: int = 25, seed: int = 42) -> dict[str, Any]:
    assert_no_fold_leakage(fold)
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    rows = _load_rows(data_path)
    parts = {"train": [row for row in rows if row["cell_id"] in fold.train_cells], "validation": [row for row in rows if row["cell_id"] == fold.validation_cell], "test": [row for row in rows if row["cell_id"] == fold.test_cell]}
    if any(not part for part in parts.values()):
        raise ValueError(f"{fold.name} has an empty state partition.")
    x_train, y_train, normalizer = _split_sequences(parts["train"], window)
    mean, std = normalizer[0], normalizer[1]
    x_valid, y_valid, _ = _split_sequences(parts["validation"], window, mean, std)
    x_test, y_test, _ = _split_sequences(parts["test"], window, mean, std)
    # Electrical state model owns only SOC and SOE.
    state_mean, state_std = y_train[:, :2].mean(axis=0), y_train[:, :2].std(axis=0)
    state_std[state_std < 1e-8] = 1.0
    electrical, state_history = _fit_model(
        ElectricalStateLSTM(len(FEATURES)), x_train, (y_train[:, :2] - state_mean) / state_std,
        x_valid, (y_valid[:, :2] - state_mean) / state_std, epochs,
    )
    with torch.no_grad():
        state_prediction = electrical(torch.from_numpy(x_test)).numpy() * state_std + state_mean

    # Temperature model learns only the delta over persistence.
    raw_train = x_train * std.reshape(1, 1, -1) + mean.reshape(1, 1, -1)
    raw_valid = x_valid * std.reshape(1, 1, -1) + mean.reshape(1, 1, -1)
    raw_test = x_test * std.reshape(1, 1, -1) + mean.reshape(1, 1, -1)
    temp_train = np.stack([temperature_features(block) for block in raw_train])
    temp_valid = np.stack([temperature_features(block) for block in raw_valid])
    temp_test = np.stack([temperature_features(block) for block in raw_test])
    temp_mean = temp_train.reshape(-1, 7).mean(axis=0); temp_std = temp_train.reshape(-1, 7).std(axis=0); temp_std[temp_std < 1e-8] = 1.0
    temp_train = ((temp_train - temp_mean) / temp_std).astype(np.float32)
    temp_valid = ((temp_valid - temp_mean) / temp_std).astype(np.float32)
    temp_test = ((temp_test - temp_mean) / temp_std).astype(np.float32)
    train_delta = (y_train[:, 2] - raw_train[:, -1, 2]).astype(np.float32)
    valid_delta = (y_valid[:, 2] - raw_valid[:, -1, 2]).astype(np.float32)
    temperature, temperature_history = _fit_model(
        TemperatureResidualLSTM(), temp_train, train_delta, temp_valid, valid_delta, epochs,
    )
    with torch.no_grad():
        predicted_delta = temperature(torch.from_numpy(temp_test))
        temperature_prediction = compose_future_temperature(torch.from_numpy(raw_test[:, -1, 2]), predicted_delta).numpy()
    persistence_values = raw_test[:, -1, 2]

    state_metrics = {target: metric_summary(y_test[:, index], state_prediction[:, index], unit=UNITS[target]) for index, target in enumerate(("soc", "soe"))}
    temperature_metrics = {"sot_5min_c": metric_summary(y_test[:, 2], temperature_prediction, unit="degC")}
    persistence = metric_summary(y_test[:, 2], persistence_values, unit="degC")
    verdicts = {target: acceptance(target, float(metric["MAE"]), y_test[:, index]) for index, (target, metric) in enumerate({**state_metrics, **temperature_metrics}.items())}
    results_dir = Path(results_dir); state_dir = results_dir / "state"; temperature_dir = results_dir / "temperature"
    state_dir.mkdir(parents=True, exist_ok=True); temperature_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "metrics_by_target.json").write_text(json.dumps(state_metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    (state_dir / "training_history.json").write_text(json.dumps(state_history, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_prediction_csv(state_dir / "test_predictions.csv", ("reference_soc", "predicted_soc", "reference_soe", "predicted_soe"), [
        {"reference_soc": float(ref[0]), "predicted_soc": float(pred[0]), "reference_soe": float(ref[1]), "predicted_soe": float(pred[1])}
        for ref, pred in zip(y_test, state_prediction)
    ])
    torch.save({"state_dict": electrical.state_dict(), "features": FEATURES, "targets": ("soc", "soe")}, state_dir / "state_lstm.pt")
    (temperature_dir / "metrics_by_target.json").write_text(json.dumps(temperature_metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    (temperature_dir / "persistence_metrics.json").write_text(json.dumps({"sot_5min_c": persistence}, ensure_ascii=False, indent=2), encoding="utf-8")
    (temperature_dir / "training_history.json").write_text(json.dumps(temperature_history, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_prediction_csv(temperature_dir / "test_predictions.csv", ("reference_sot_5min_c", "predicted_sot_5min_c", "baseline_sot_5min_c"), [
        {"reference_sot_5min_c": float(ref), "predicted_sot_5min_c": float(pred), "baseline_sot_5min_c": float(base)}
        for ref, pred, base in zip(y_test[:, 2], temperature_prediction, persistence_values)
    ])
    torch.save({"state_dict": temperature.state_dict(), "features": ("voltage_v", "current_a", "temperature_c", "dv_dt_v_s", "power_w", "temperature_change_c", "temperature_slope_c")}, temperature_dir / "temperature_lstm.pt")
    config = {"fold": fold.name, "train_cells": list(fold.train_cells), "validation_cell": fold.validation_cell, "test_cell": fold.test_cell, "window": window, "epochs": epochs, "seed": seed}
    (results_dir / "run_config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    (results_dir / "acceptance.json").write_text(json.dumps(verdicts, ensure_ascii=False, indent=2), encoding="utf-8")
    (results_dir / "leakage_audit.json").write_text(json.dumps({"train_cells": list(fold.train_cells), "validation_cell": fold.validation_cell, "test_cell": fold.test_cell, "normalizer_fit": "train_only", "window_crosses_groups": False}, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"fold": fold.name, "metrics_by_target": {**state_metrics, **temperature_metrics}, "persistence_metrics": {"sot_5min_c": persistence}}
