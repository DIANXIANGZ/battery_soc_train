"""Train user-imported battery time series with selectable algorithms and strict splits."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from src.custom_training.algorithms import algorithm_keys
from src.custom_training.capability import verify_registry_capability
from src.training.battery_protocol import acceptance, audit_split, nested_group_folds, target_acceptance


SUPPORTED_ALGORITHMS = algorithm_keys()
BOUNDARY_COLUMNS = ("cell_id", "session_id", "cycle_id", "condition_id")


class Regressor(nn.Module):
    def __init__(self, kind: str, features: int, targets: int, hidden: int) -> None:
        super().__init__()
        self.kind = kind
        if kind == "transformer":
            self.input = nn.Linear(features, hidden)
            layer = nn.TransformerEncoderLayer(hidden, 2, hidden * 2, batch_first=True)
            self.core = nn.TransformerEncoder(layer, 1)
        else:
            self.core = (nn.LSTM if kind == "lstm" else nn.GRU)(features, hidden, batch_first=True)
        self.head = nn.Linear(hidden, targets)

    def forward(self, values: torch.Tensor) -> torch.Tensor:
        if self.kind == "transformer":
            return self.head(self.core(self.input(values))[:, -1])
        return self.head(self.core(values)[0][:, -1])


def _arrays(
    data: Path,
    features: tuple[str, ...],
    targets: tuple[str, ...],
    window: int,
) -> tuple[np.ndarray, np.ndarray, list[dict[str, str]], bool]:
    with Path(data).open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("数据文件为空。")
    x_rows = np.asarray([[float(row[column]) for column in features] for row in rows], np.float32)
    y_rows = np.asarray([[float(row[column]) for column in targets] for row in rows], np.float32)
    available_boundaries = tuple(column for column in BOUNDARY_COLUMNS if column in rows[0])
    grouped = "cell_id" in available_boundaries and "condition_id" in available_boundaries
    sequences: list[np.ndarray] = []
    labels: list[np.ndarray] = []
    metadata: list[dict[str, str]] = []
    for stop in range(window, len(rows) + 1):
        start = stop - window
        if available_boundaries:
            identities = {tuple(rows[index][column] for column in available_boundaries) for index in range(start, stop)}
            if len(identities) != 1:
                continue
        sequences.append(x_rows[start:stop])
        labels.append(y_rows[stop - 1])
        metadata.append({column: rows[stop - 1].get(column, "") for column in BOUNDARY_COLUMNS})
    if len(sequences) < max(30, window * 3):
        raise ValueError("数据不足以按所选窗口划分训练、验证和测试集。")
    return np.stack(sequences), np.stack(labels), metadata, grouped


def _partition_indices(metadata: list[dict[str, str]], grouped: bool, seed: int):
    size = len(metadata)
    if grouped:
        groups = np.asarray([item["cell_id"] for item in metadata])
        conditions = np.asarray([item["condition_id"] for item in metadata])
        fold = nested_group_folds(groups, conditions, seed=seed)[0]
        audit = audit_split(groups, conditions, fold)
        if not audit.passed:
            raise ValueError(f"自定义数据严格切分泄露审计失败：{audit.violations}")
        return fold.train_indices, fold.validation_indices, fold.test_indices, {
            "split": "strict_group_condition",
            "generalization_level": "unseen_cell_and_condition",
            "passed": True,
            "test_group": fold.test_group,
            "test_condition": fold.test_condition,
            "validation_group": fold.validation_group,
        }
    train_stop, validation_stop = int(size * 0.6), int(size * 0.8)
    return np.arange(train_stop), np.arange(train_stop, validation_stop), np.arange(validation_stop, size), {
        "split": "chronological",
        "generalization_level": "time_only",
        "passed": True,
    }


def _require_generalization(grouped: bool, required_level: str | None) -> None:
    if required_level == "unseen_cell_and_condition" and not grouped:
        raise ValueError("strict grouped generalization cannot degrade to time-only")


def run_training(
    data: Path,
    results_dir: Path,
    *,
    features: tuple[str, ...],
    targets: tuple[str, ...],
    algorithm: str,
    window: int,
    epochs: int,
    batch_size: int,
    hidden: int,
    seed: int,
    learning_rate: float = 3e-4,
    required_generalization_level: str | None = None,
) -> dict[str, object]:
    if algorithm not in SUPPORTED_ALGORITHMS:
        raise ValueError(f"Unsupported algorithm: {algorithm}")
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    x, y, metadata, grouped = _arrays(data, features, targets, window)
    _require_generalization(grouped, required_generalization_level)
    train_indices, validation_indices, test_indices, audit = _partition_indices(metadata, grouped, seed)
    train_x, validation_x, test_x = x[train_indices], x[validation_indices], x[test_indices]
    train_y, validation_y, test_y = y[train_indices], y[validation_indices], y[test_indices]
    mean = train_x.mean((0, 1))
    std = train_x.std((0, 1))
    std[std < 1e-8] = 1
    train_x = (train_x - mean) / std
    validation_x = (validation_x - mean) / std
    test_x = (test_x - mean) / std
    history: list[dict[str, object]] = []
    if algorithm == "xgboost":
        print("epoch 1", flush=True)
        with tempfile.TemporaryDirectory() as temporary_dir:
            exchange = Path(temporary_dir)
            np.savez(
                exchange / "input.npz",
                train_x=train_x.reshape(len(train_x), -1),
                train_y=train_y,
                test_x=test_x.reshape(len(test_x), -1),
            )
            subprocess.run(
                [
                    sys.executable, "-m", "src.training.xgboost_backend",
                    "--input", str(exchange / "input.npz"),
                    "--output", str(exchange / "prediction.npy"),
                    "--estimators", str(max(20, epochs * 10)),
                    "--seed", str(seed),
                ],
                check=True,
            )
            prediction = np.load(exchange / "prediction.npy")
        history = [{"epoch": epochs}]
        print(f"epoch {epochs}", flush=True)
    else:
        model = Regressor(algorithm, len(features), len(targets), hidden)
        optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)
        loss_function = nn.MSELoss()
        loader = DataLoader(
            TensorDataset(torch.from_numpy(train_x), torch.from_numpy(train_y)),
            batch_size=batch_size,
            shuffle=True,
        )
        for epoch in range(1, epochs + 1):
            model.train()
            losses = []
            for batch_x, batch_y in loader:
                optimizer.zero_grad()
                loss = loss_function(model(batch_x), batch_y)
                loss.backward()
                optimizer.step()
                losses.append(float(loss.detach()))
            history.append({"epoch": epoch, "train_loss": float(np.mean(losses))})
            print(f"epoch {epoch}", flush=True)
        model.eval()
        prediction = model(torch.from_numpy(test_x)).detach().numpy()

    metrics = {
        name: {
            "MAE": float(np.mean(np.abs(test_y[:, index] - prediction[:, index]))),
            "RMSE": float(np.sqrt(np.mean((test_y[:, index] - prediction[:, index]) ** 2))),
        }
        for index, name in enumerate(targets)
    }
    summary = {
        "MAE": float(np.mean([metric["MAE"] for metric in metrics.values()])),
        "RMSE": float(np.mean([metric["RMSE"] for metric in metrics.values()])),
        "n_train": len(train_y),
        "n_validation": len(validation_y),
        "n_test": len(test_y),
        "algorithm": algorithm,
        "targets": list(targets),
    }
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    payloads = {
        "metrics.json": summary,
        "metrics_by_target.json": metrics,
        "training_history.json": history,
        "run_config.json": {
            "algorithm": algorithm, "features": list(features), "targets": list(targets),
            "window": window, "seed": seed,
        },
    }
    for name, value in payloads.items():
        (results_dir / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    prediction_columns = [item for target in targets for item in (f"reference_{target}", f"predicted_{target}")]
    with (results_dir / "test_predictions.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=prediction_columns)
        writer.writeheader()
        writer.writerows(
            {
                key: float(value)
                for index, target in enumerate(targets)
                for key, value in (
                    (f"reference_{target}", reference[index]),
                    (f"predicted_{target}", estimate[index]),
                )
            }
            for reference, estimate in zip(test_y, prediction)
        )
    audit.update({
        "normalizer_fit": "train_only",
        "algorithm": algorithm,
        "window_boundary_crossing": False,
        "test_used_for_selection": False,
    })
    verdicts = {}
    for index, target in enumerate(targets):
        try:
            verdicts[target] = target_acceptance(target, test_y[:, index], prediction[:, index])
        except ValueError:
            verdicts[target] = acceptance(target, float(metrics[target]["MAE"]), test_y[:, index])
    (results_dir / "leakage_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    (results_dir / "acceptance.json").write_text(json.dumps(verdicts, ensure_ascii=False, indent=2), encoding="utf-8")
    (results_dir / "split_manifest.json").write_text(json.dumps({
        "train_indices": train_indices.tolist(),
        "validation_indices": validation_indices.tolist(),
        "test_indices": test_indices.tolist(),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"metrics": summary, "metrics_by_target": metrics, "results_dir": results_dir}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--admission-registry", type=Path, required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--features", nargs="+", required=True)
    parser.add_argument("--targets", nargs="+", required=True)
    parser.add_argument("--algorithm", choices=SUPPORTED_ALGORITHMS, default="lstm")
    parser.add_argument("--window", type=int, default=60)
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--hidden", type=int, default=32)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    try:
        capability = verify_registry_capability(
            args.admission_registry,
            args.project_id,
            args.data,
            algorithm=args.algorithm,
            features=tuple(args.features),
            targets=tuple(args.targets),
        )
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        parser.error(f"自定义训练仍被数据准入门禁阻塞：{error}")
    report = capability["target_report"]
    required_generalization_level = (
        str(report.get("generalization_level")) if isinstance(report, dict) else None
    )
    run_training(
        args.data, args.results_dir, features=tuple(args.features), targets=tuple(args.targets),
        algorithm=args.algorithm, window=args.window, epochs=args.epochs, batch_size=args.batch_size,
        hidden=args.hidden, learning_rate=args.learning_rate, seed=args.seed,
        required_generalization_level=required_generalization_level,
    )


if __name__ == "__main__":
    main()
