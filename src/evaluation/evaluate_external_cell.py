"""Evaluate the frozen A123#3 export on an unseen target cell."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np
import torch

from src.training.train_lstm import LSTMSOC, load_sessions, make_sequences, svg_plot
from src.project_paths import DataCenterPaths


BAND_NAMES = ("0-20%", "20-40%", "40-60%", "60-80%", "80-100%")


def load_exported_model(model_path: Path):
    payload = torch.load(model_path, map_location="cpu", weights_only=False)
    features = tuple(payload["features"])
    mean = np.asarray(payload["mean"], dtype=np.float32)
    std = np.asarray(payload["std"], dtype=np.float32)
    window = int(payload["window"])
    hidden = int(payload["state_dict"]["lstm.weight_ih_l0"].shape[0] // 4)
    model = LSTMSOC(len(features), hidden=hidden)
    model.load_state_dict(payload["state_dict"])
    model.eval()
    return model, features, mean, std, window


def _validate_target(sessions: dict, expected_prefix: str) -> None:
    invalid = [name for name in sessions if not name.startswith(expected_prefix)]
    if invalid:
        raise ValueError(f"Target sessions must begin with {expected_prefix!r}; found {invalid[:3]}")


def _band_metrics(actual: np.ndarray, predicted: np.ndarray) -> dict:
    result = {}
    for index, name in enumerate(BAND_NAMES):
        lower, upper = index / 5, (index + 1) / 5
        mask = (actual >= lower) & ((actual < upper) if index < 4 else (actual <= upper))
        result[name] = {
            "n": int(mask.sum()),
            "MAE_pct": None if not mask.any() else float(np.abs(predicted[mask] - actual[mask]).mean() * 100),
        }
    return result


def predict_in_batches(model, sequences: np.ndarray, batch_size: int = 512) -> np.ndarray:
    predictions = []
    with torch.no_grad():
        for start in range(0, len(sequences), batch_size):
            batch = torch.from_numpy(sequences[start:start + batch_size])
            predictions.append(model(batch).numpy())
    return np.concatenate(predictions)


def evaluate_csv(data_path: Path, model_path: Path, expected_prefix: str):
    model, features, mean, std, window = load_exported_model(model_path)
    use_delta_ah = "window_delta_ah" in features
    sessions = load_sessions(data_path, use_delta_ah, window, 30.0)
    _validate_target(sessions, expected_prefix)
    actual_parts, predicted_parts = [], []
    for name in sorted(sessions):
        x, actual = make_sequences(sessions[name], mean, std, window)
        if not len(x):
            continue
        actual_parts.append(actual)
        predicted_parts.append(predict_in_batches(model, x))
    if not actual_parts:
        raise ValueError(f"No target session has at least {window} rows.")
    actual = np.concatenate(actual_parts)
    predicted = np.concatenate(predicted_parts)
    errors = predicted - actual
    metrics = {
        "source_cell": "A123#3",
        "target_cell": "A123#5",
        "model_path": str(model_path),
        "data_path": str(data_path),
        "target_sessions": sorted(sessions),
        "n_test": int(len(actual)),
        "features": list(features),
        "window_steps": window,
        "MAE_pct": float(np.abs(errors).mean() * 100),
        "RMSE_pct": float(np.sqrt(np.square(errors).mean()) * 100),
        "label_note": "Error is against an offline Coulomb-counting reference label, not physical SOC ground truth.",
    }
    return metrics, list(zip(actual.tolist(), predicted.tolist()))


def write_results(
    results_dir: Path,
    metrics: dict,
    predictions: list[tuple[float, float]],
    protected_dirs=(),
) -> None:
    resolved_output = Path(results_dir).resolve()
    protected = {Path(path).resolve() for path in protected_dirs}
    if resolved_output in protected:
        raise ValueError(f"Refusing to write cross-cell results into protected directory: {resolved_output}")
    results_dir.mkdir(parents=True, exist_ok=True)
    actual = np.asarray([item[0] for item in predictions], dtype=np.float32)
    predicted = np.asarray([item[1] for item in predictions], dtype=np.float32)
    (results_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (results_dir / "metrics_by_soc.json").write_text(json.dumps(_band_metrics(actual, predicted), indent=2), encoding="utf-8")
    with (results_dir / "test_predictions.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["reference_soc", "predicted_soc"])
        writer.writerows(predictions)
    svg_plot(actual, predicted, results_dir / "soc_prediction.svg", metrics["MAE_pct"], metrics["RMSE_pct"])


def build_parser() -> argparse.ArgumentParser:
    paths = DataCenterPaths.from_config()
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--model", type=Path, default=paths.baseline_results_dir / "lstm_soc.pt")
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--expected-session-prefix", default="A123#5")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    paths = DataCenterPaths.from_config()
    metrics, predictions = evaluate_csv(args.data, args.model, args.expected_session_prefix)
    write_results(
        args.results_dir,
        metrics,
        predictions,
        protected_dirs=[paths.baseline_results_dir, paths.cross_cell_results_dir],
    )
    print(json.dumps(metrics, ensure_ascii=False))


if __name__ == "__main__":
    main()
