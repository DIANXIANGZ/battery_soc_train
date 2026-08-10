"""Shared-LSTM core for SOC, SOH, SOE, RUL, and SOT prediction."""

from __future__ import annotations

import csv
import argparse
import hashlib
import json
import random
from pathlib import Path
from typing import Any
import torch
import numpy as np
from torch import nn
from torch.utils.data import DataLoader, TensorDataset


TARGETS = ("soc", "soh", "soe", "rul_cycles", "sot_c")
FEATURES = ("voltage_v", "current_a", "temperature_c", "dv_dt_v_s")


def metric_summary(reference: np.ndarray, prediction: np.ndarray, *, unit: str) -> dict[str, float | int | str]:
    """Summarize raw-unit test errors for one target."""

    reference = np.asarray(reference, dtype=np.float64)
    prediction = np.asarray(prediction, dtype=np.float64)
    if reference.shape != prediction.shape or reference.size == 0:
        raise ValueError("Reference and prediction must be non-empty arrays with matching shapes.")
    error = prediction - reference
    return {
        "MAE": float(np.mean(np.abs(error))),
        "RMSE": float(np.sqrt(np.mean(error ** 2))),
        "n_test": int(error.size),
        "unit": unit,
    }


def load_rows(path: Path) -> list[dict[str, object]]:
    """Read the audited multi-state CSV with numeric features and targets."""

    rows: list[dict[str, object]] = []
    with Path(path).open(encoding="utf-8", newline="") as handle:
        for raw in csv.DictReader(handle):
            row: dict[str, object] = dict(raw)
            for field in (*FEATURES, *TARGETS):
                row[field] = float(raw[field])
            rows.append(row)
    if not rows:
        raise ValueError("Training CSV contains no rows.")
    return rows


def make_sequences(rows: list[dict[str, object]], window: int) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Create windows only within one cell and one reference-discharge cycle."""

    if window < 1:
        raise ValueError("window must be at least one")
    grouped: dict[tuple[str, str], list[dict[str, object]]] = {}
    for row in rows:
        grouped.setdefault((str(row["cell_id"]), str(row["cycle_id"])), []).append(row)
    feature_windows, target_values = [], {target: [] for target in TARGETS}
    for group_rows in grouped.values():
        for end in range(window - 1, len(group_rows)):
            block = group_rows[end - window + 1:end + 1]
            feature_windows.append([[float(row[name]) for name in FEATURES] for row in block])
            for target in TARGETS:
                target_values[target].append(float(group_rows[end][target]))
    if not feature_windows:
        raise ValueError("No sequences were created; reduce window or provide longer cycles.")
    return np.asarray(feature_windows, dtype=np.float32), {target: np.asarray(values, dtype=np.float32) for target, values in target_values.items()}


def partition_rows(rows: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    """Partition parsed samples strictly by their audited split role."""

    parts = {"train": [], "validation": [], "test": []}
    for row in rows:
        role = str(row["split"])
        if role not in parts:
            raise ValueError(f"Unknown split role: {role}")
        parts[role].append(row)
    if any(not part for part in parts.values()):
        raise ValueError("Train, validation, and test splits must all be non-empty.")
    return parts


class MultiStateLSTM(nn.Module):
    """Encode one signal window once, then regress five battery states."""

    def __init__(self, n_features: int, hidden: int = 32, dropout: float = 0.10):
        super().__init__()
        self.lstm = nn.LSTM(n_features, hidden, batch_first=True)
        self.heads = nn.ModuleDict({
            target: nn.Sequential(
                nn.Linear(hidden, 16), nn.ReLU(), nn.Dropout(dropout), nn.Linear(16, 1),
            )
            for target in TARGETS
        })

    def forward(self, inputs: torch.Tensor) -> dict[str, torch.Tensor]:
        encoded, _ = self.lstm(inputs)
        last = encoded[:, -1]
        return {target: head(last).squeeze(1) for target, head in self.heads.items()}


def masked_huber_loss(prediction: torch.Tensor, reference: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    """Return Huber loss over available labels only, preserving gradients."""

    if prediction.shape != reference.shape or prediction.shape != mask.shape:
        raise ValueError("Prediction, reference, and mask must have matching shapes.")
    if not torch.any(mask):
        return prediction.sum() * 0.0
    return nn.functional.huber_loss(prediction[mask], reference[mask])


def multistate_loss(predictions: dict[str, torch.Tensor], references: dict[str, torch.Tensor], masks: dict[str, torch.Tensor]) -> torch.Tensor:
    """Average the available target losses so missing labels do not distort training."""

    losses = [masked_huber_loss(predictions[target], references[target], masks[target]) for target in TARGETS if torch.any(masks[target])]
    if not losses:
        raise ValueError("A training batch must contain at least one available target label.")
    return torch.stack(losses).mean()


TARGET_UNITS = {
    "soc": "fraction",
    "soh": "fraction",
    "soe": "fraction",
    "rul_cycles": "cycles",
    "sot_c": "degC",
}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _select_limit(values: np.ndarray, limit: int | None) -> np.ndarray:
    if limit is None or limit <= 0 or len(values) <= limit:
        return values
    return values[:limit]


def _normalization(rows: list[dict[str, object]]) -> tuple[np.ndarray, np.ndarray]:
    values = np.asarray([[float(row[field]) for field in FEATURES] for row in rows], dtype=np.float32)
    mean, std = values.mean(axis=0), values.std(axis=0)
    std[std < 1e-8] = 1.0
    return mean, std


def _target_normalization(targets: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    values = np.column_stack([targets[target] for target in TARGETS]).astype(np.float32)
    mean, std = values.mean(axis=0), values.std(axis=0)
    std[std < 1e-8] = 1.0
    return mean, std


def _sequence_arrays(rows: list[dict[str, object]], *, window: int, feature_mean: np.ndarray, feature_std: np.ndarray, target_mean: np.ndarray, target_std: np.ndarray, limit: int | None) -> tuple[np.ndarray, np.ndarray]:
    features, targets = make_sequences(rows, window)
    features = (features - feature_mean.reshape(1, 1, -1)) / feature_std.reshape(1, 1, -1)
    target_values = np.column_stack([targets[target] for target in TARGETS]).astype(np.float32)
    target_values = (target_values - target_mean.reshape(1, -1)) / target_std.reshape(1, -1)
    return _select_limit(features, limit), _select_limit(target_values, limit)


def _loader(features: np.ndarray, targets: np.ndarray, *, batch_size: int, shuffle: bool) -> DataLoader[tuple[torch.Tensor, torch.Tensor]]:
    dataset = TensorDataset(torch.from_numpy(features), torch.from_numpy(targets))
    return DataLoader(dataset, batch_size=batch_size, shuffle=shuffle)


def _batch_loss(model: MultiStateLSTM, inputs: torch.Tensor, target_values: torch.Tensor) -> torch.Tensor:
    predictions = model(inputs)
    references = {target: target_values[:, index] for index, target in enumerate(TARGETS)}
    masks = {target: torch.isfinite(reference) for target, reference in references.items()}
    return multistate_loss(predictions, references, masks)


def _mean_loss(model: MultiStateLSTM, loader: DataLoader[tuple[torch.Tensor, torch.Tensor]]) -> float:
    model.eval()
    losses: list[float] = []
    with torch.no_grad():
        for inputs, target_values in loader:
            losses.append(float(_batch_loss(model, inputs, target_values)))
    return float(np.mean(losses))


def run_training(data_path: Path, results_dir: Path, *, window: int = 60, epochs: int = 40, batch_size: int = 128, hidden: int = 32, dropout: float = 0.10, learning_rate: float = 3e-4, seed: int = 42, max_train: int | None = None, max_valid: int | None = None, max_test: int | None = None) -> dict[str, Any]:
    """Train and save a leak-safe five-target LSTM experiment."""

    if epochs < 1 or batch_size < 1 or hidden < 1 or window < 1:
        raise ValueError("epochs, batch_size, hidden, and window must all be positive.")
    data_path, results_dir = Path(data_path), Path(results_dir)
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)

    parts = partition_rows(load_rows(data_path))
    feature_mean, feature_std = _normalization(parts["train"])
    raw_train_features, raw_train_targets = make_sequences(parts["train"], window)
    del raw_train_features
    target_mean, target_std = _target_normalization(raw_train_targets)
    x_train, y_train = _sequence_arrays(parts["train"], window=window, feature_mean=feature_mean, feature_std=feature_std, target_mean=target_mean, target_std=target_std, limit=max_train)
    x_valid, y_valid = _sequence_arrays(parts["validation"], window=window, feature_mean=feature_mean, feature_std=feature_std, target_mean=target_mean, target_std=target_std, limit=max_valid)
    x_test, y_test = _sequence_arrays(parts["test"], window=window, feature_mean=feature_mean, feature_std=feature_std, target_mean=target_mean, target_std=target_std, limit=max_test)
    train_loader = _loader(x_train, y_train, batch_size=batch_size, shuffle=True)
    valid_loader = _loader(x_valid, y_valid, batch_size=batch_size, shuffle=False)
    test_loader = _loader(x_test, y_test, batch_size=batch_size, shuffle=False)

    model = MultiStateLSTM(n_features=len(FEATURES), hidden=hidden, dropout=dropout)
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)
    best_state: dict[str, torch.Tensor] | None = None
    best_validation = float("inf")
    history: list[dict[str, float | int]] = []
    for epoch in range(1, epochs + 1):
        model.train()
        train_losses: list[float] = []
        for inputs, target_values in train_loader:
            optimizer.zero_grad()
            loss = _batch_loss(model, inputs, target_values)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            train_losses.append(float(loss.detach()))
        validation_loss = _mean_loss(model, valid_loader)
        train_loss = float(np.mean(train_losses))
        history.append({"epoch": epoch, "train_loss": train_loss, "validation_loss": validation_loss})
        if validation_loss < best_validation:
            best_validation = validation_loss
            best_state = {name: value.detach().clone() for name, value in model.state_dict().items()}
        print(f"PROGRESS: {round(epoch * 100 / epochs)}", flush=True)

    if best_state is None:
        raise RuntimeError("Training did not produce a valid model state.")
    model.load_state_dict(best_state)
    model.eval()
    normalized_predictions: list[np.ndarray] = []
    with torch.no_grad():
        for inputs, _ in test_loader:
            outputs = model(inputs)
            normalized_predictions.append(np.column_stack([outputs[target].cpu().numpy() for target in TARGETS]))
    prediction_values = np.concatenate(normalized_predictions, axis=0) * target_std.reshape(1, -1) + target_mean.reshape(1, -1)
    reference_values = y_test * target_std.reshape(1, -1) + target_mean.reshape(1, -1)
    metrics_by_target = {target: metric_summary(reference_values[:, index], prediction_values[:, index], unit=TARGET_UNITS[target]) for index, target in enumerate(TARGETS)}

    results_dir.mkdir(parents=True, exist_ok=True)
    torch.save({"state_dict": model.state_dict(), "features": FEATURES, "targets": TARGETS, "feature_mean": feature_mean, "feature_std": feature_std, "target_mean": target_mean, "target_std": target_std}, results_dir / "multistate_lstm.pt")
    (results_dir / "metrics_by_target.json").write_text(json.dumps(metrics_by_target, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {"best_validation_loss": best_validation, "n_train": int(len(y_train)), "n_validation": int(len(y_valid)), "n_test": int(len(y_test)), "targets": list(TARGETS)}
    (results_dir / "metrics.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (results_dir / "training_history.json").write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    run_config = {"data_path": str(data_path.resolve()), "data_sha256": _sha256_file(data_path), "window": window, "epochs": epochs, "batch_size": batch_size, "hidden": hidden, "dropout": dropout, "learning_rate": learning_rate, "seed": seed, "feature_mean": feature_mean.tolist(), "feature_std": feature_std.tolist(), "target_mean": target_mean.tolist(), "target_std": target_std.tolist()}
    (results_dir / "run_config.json").write_text(json.dumps(run_config, ensure_ascii=False, indent=2), encoding="utf-8")
    with (results_dir / "test_predictions.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[field for target in TARGETS for field in (f"reference_{target}", f"predicted_{target}")])
        writer.writeheader()
        for reference, prediction in zip(reference_values, prediction_values):
            writer.writerow({field: float(value) for target_index, target in enumerate(TARGETS) for field, value in ((f"reference_{target}", reference[target_index]), (f"predicted_{target}", prediction[target_index]))})
    return {"metrics": summary, "metrics_by_target": metrics_by_target, "results_dir": results_dir}


def main() -> None:
    parser = argparse.ArgumentParser(description="Train shared-LSTM NASA five-state battery predictor.")
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--window", type=int, default=60)
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--hidden", type=int, default=32)
    parser.add_argument("--dropout", type=float, default=0.10)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-train", type=int)
    parser.add_argument("--max-valid", type=int)
    parser.add_argument("--max-test", type=int)
    args = parser.parse_args()
    result = run_training(args.data, args.results_dir, window=args.window, epochs=args.epochs, batch_size=args.batch_size, hidden=args.hidden, dropout=args.dropout, learning_rate=args.learning_rate, seed=args.seed, max_train=args.max_train, max_valid=args.max_valid, max_test=args.max_test)
    print(json.dumps(result["metrics_by_target"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
