"""Train an LSTM SOC estimator with an independent-session test split."""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
from pathlib import Path

import numpy as np
import torch
from torch import nn


if __package__ in (None, ""):
    project_root = str(Path(__file__).resolve().parents[2])
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

from src.project_paths import DataCenterPaths
from src.evaluation.analyze_predictions import write_analysis
from torch.utils.data import DataLoader, TensorDataset


BASE_FEATURES = ("voltage_v", "current_a", "dv_dt_v_s")


def make_checkpoint_payload(model_state, optimizer_state, best_state, best_loss, stale_epochs, epochs_completed, feature_names, window, seed, scheduler_state=None, training_policy=None):
    """Keep the current optimizer/model pair for continuation and the best weights for evaluation."""
    return {
        "model_state": model_state,
        "optimizer_state": optimizer_state,
        "best_state": best_state,
        "best_loss": best_loss,
        "stale_epochs": stale_epochs,
        "epochs_completed": epochs_completed,
        "features": feature_names,
        "window": window,
        "seed": seed,
        "scheduler_state": scheduler_state,
        "training_policy": training_policy or {},
    }


class LSTMSOC(nn.Module):
    def __init__(self, n_features: int, hidden: int = 32, dropout: float = 0.0):
        super().__init__()
        self.lstm = nn.LSTM(n_features, hidden, batch_first=True)
        self.head = nn.Sequential(
            nn.Linear(hidden, 16),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(16, 1),
            nn.Sigmoid(),
        )

    def forward(self, x):
        y, _ = self.lstm(x)
        return self.head(y[:, -1]).squeeze(1)


def build_optimizer_and_scheduler(model: nn.Module, args):
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=args.learning_rate,
        weight_decay=args.weight_decay,
    )
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer,
        mode="min",
        factor=args.lr_factor,
        patience=args.lr_patience,
        min_lr=args.min_learning_rate,
    )
    return optimizer, scheduler


def is_meaningful_improvement(value: float, best: float, min_delta: float) -> bool:
    return value < best - min_delta


def resolve_session_split(available, requested_train=None, requested_validation=None, requested_test=None):
    if requested_train is None and requested_validation is None and requested_test is None:
        return list(available[:-2]), available[-2], available[-1]
    if not requested_train or not requested_validation or not requested_test:
        raise ValueError("Explicit split requires train, validation, and test sessions.")
    selected = list(requested_train) + [requested_validation, requested_test]
    unknown = sorted(set(selected) - set(available))
    if unknown:
        raise ValueError(f"Explicit split contains unknown sessions: {unknown}")
    if len(selected) != len(set(selected)):
        raise ValueError("Explicit split contains overlap between train/validation/test.")
    return list(requested_train), requested_validation, requested_test


def load_sessions(path: Path, add_delta_ah: bool, ah_window: int, sample_interval_s: float):
    sessions = {}
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            values = [float(row[col]) for col in BASE_FEATURES] + [float(row["soc"])]
            sessions.setdefault(row["session"], []).append(values)
    arrays = {name: np.asarray(rows, dtype=np.float32) for name, rows in sessions.items()}
    if not add_delta_ah:
        return arrays
    augmented = {}
    for name, data in arrays.items():
        increments = data[:, 1] * (sample_interval_s / 3600.0)
        cumulative = np.cumsum(increments)
        previous = np.concatenate([np.zeros(ah_window, dtype=np.float32), cumulative[:-ah_window]])
        rolling_ah = cumulative - previous
        augmented[name] = np.column_stack([data[:, :-1], rolling_ah, data[:, -1]]).astype(np.float32)
    return augmented


def make_sequences(data, mean, std, window):
    x = (data[:, :-1] - mean) / std
    y = data[:, -1]
    seq = np.stack([x[i - window + 1:i + 1] for i in range(window - 1, len(x))])
    return seq.astype(np.float32), y[window - 1:].astype(np.float32)


def svg_plot(actual, predicted, output: Path, mae_pct: float | None = None, rmse_pct: float | None = None):
    actual, predicted = actual[:800], predicted[:800]
    width, height, pad, top = 1100, 440, 76, 92
    def points(values, color):
        n = max(len(values) - 1, 1)
        return " ".join(f"{pad + (width-2*pad)*i/n:.1f},{height-pad-(height-top-pad)*v:.1f}" for i, v in enumerate(values))
    metric_text = "" if mae_pct is None or rmse_pct is None else f"MAE {mae_pct:.2f}% | RMSE {rmse_pct:.2f}%"
    output.write_text(f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<title>Independent SOC prediction, first 800 test samples. {metric_text}</title><desc>Reference SOC and LSTM estimate are shown as percentages over sample index.</desc>
<rect width="100%" height="100%" fill="white"/><path d="M {pad} {top} V {height-pad} H {width-pad}" stroke="#333" fill="none"/>
<text x="{pad}" y="30" font-family="Arial" font-size="22">Independent-test SOC prediction</text><text x="{pad}" y="56" font-family="Arial" font-size="16" fill="#444">First 800 samples | {metric_text}</text>
<polyline points="{points(actual, '#1967d2')}" fill="none" stroke="#1967d2" stroke-width="2"/><polyline points="{points(predicted, '#e87326')}" fill="none" stroke="#e87326" stroke-width="2"/>
<line x1="{width-255}" y1="27" x2="{width-230}" y2="27" stroke="#1967d2" stroke-width="2"/><text x="{width-220}" y="32" font-family="Arial" fill="#1967d2">Reference SOC</text><line x1="{width-255}" y1="53" x2="{width-230}" y2="53" stroke="#e87326" stroke-width="2"/><text x="{width-220}" y="58" font-family="Arial" fill="#e87326">LSTM estimate</text>
<text x="20" y="{top+5}" font-family="Arial" font-size="13">100%</text><text x="34" y="{height-pad}" font-family="Arial" font-size="13">0%</text>
<text x="{width/2-42}" y="{height-22}" font-family="Arial" font-size="15">Sample index</text><text x="22" y="{height/2+28}" font-family="Arial" font-size="15" transform="rotate(-90 22 {height/2+28})">SOC (%)</text></svg>''', encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    paths = DataCenterPaths.from_config()
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, default=paths.training_csv)
    p.add_argument("--results-dir", type=Path, default=paths.baseline_results_dir)
    p.add_argument("--train-sessions", nargs="+")
    p.add_argument("--validation-session")
    p.add_argument("--test-session")
    p.add_argument("--window", type=int, default=60)
    p.add_argument("--epochs", type=int, default=40)
    p.add_argument("--batch-size", type=int, default=512)
    p.add_argument("--max-train", type=int, default=40000, help="Training sequence cap for CPU training.")
    p.add_argument("--max-valid", type=int, default=20000)
    p.add_argument("--max-test", type=int, default=20000)
    delta_group = p.add_mutually_exclusive_group()
    delta_group.add_argument("--add-delta-ah", dest="add_delta_ah", action="store_true", help="Add rolling current integral as a fourth feature.")
    delta_group.add_argument("--no-delta-ah", dest="add_delta_ah", action="store_false")
    balance_group = p.add_mutually_exclusive_group()
    balance_group.add_argument("--balance-soc", dest="balance_soc", action="store_true", help="Balance training samples across five SOC bands.")
    balance_group.add_argument("--no-balance-soc", dest="balance_soc", action="store_false")
    p.set_defaults(add_delta_ah=True, balance_soc=True)
    p.add_argument("--hidden", type=int, default=32)
    p.add_argument("--dropout", type=float, default=0.10)
    p.add_argument("--learning-rate", type=float, default=3e-4)
    p.add_argument("--weight-decay", type=float, default=1e-4)
    p.add_argument("--lr-patience", type=int, default=3)
    p.add_argument("--lr-factor", type=float, default=0.5)
    p.add_argument("--min-learning-rate", type=float, default=3e-5)
    p.add_argument("--min-delta", type=float, default=1e-5)
    p.add_argument("--gradient-clip", type=float, default=1.0)
    p.add_argument("--patience", type=int, default=9, help="Early-stop patience; zero disables early stopping.")
    p.add_argument("--seed", type=int, default=42, help="Random seed for reproducible sampling and model initialization.")
    p.add_argument("--checkpoint", type=Path, help="Optional path for a resumable training checkpoint.")
    p.add_argument("--resume-from", type=Path, help="Continue training from a checkpoint created with --checkpoint.")
    return p


def main():
    args = build_parser().parse_args()
    random.seed(args.seed); np.random.seed(args.seed); torch.manual_seed(args.seed)
    sessions = load_sessions(args.data, args.add_delta_ah, args.window, 30.0)
    feature_names = BASE_FEATURES + (("window_delta_ah",) if args.add_delta_ah else ())
    names = list(sessions)
    if len(names) < 3:
        raise ValueError("Need at least three independent sessions for train/validation/test.")
    train_names, valid_name, test_name = resolve_session_split(
        names,
        args.train_sessions,
        args.validation_session,
        args.test_session,
    )
    train = np.concatenate([sessions[name] for name in train_names], axis=0)
    mean, std = train[:, :-1].mean(axis=0), train[:, :-1].std(axis=0)
    std[std < 1e-8] = 1.0
    # Build sequences inside each session only; never let a window cross a session boundary.
    train_sequences = [make_sequences(sessions[name], mean, std, args.window) for name in train_names]
    x_train = np.concatenate([item[0] for item in train_sequences], axis=0)
    y_train = np.concatenate([item[1] for item in train_sequences], axis=0)
    x_valid, y_valid = make_sequences(sessions[valid_name], mean, std, args.window)
    x_test, y_test = make_sequences(sessions[test_name], mean, std, args.window)
    def cap(x, y, n, balance=False):
        if len(x) <= n:
            return x, y
        if balance:
            rng = np.random.default_rng(args.seed)
            bands = np.digitize(y, [0.2, 0.4, 0.6, 0.8])
            selected = []
            target = n // 5
            for band in range(5):
                candidates = np.flatnonzero(bands == band)
                take = min(target, len(candidates))
                if take:
                    selected.extend(rng.choice(candidates, size=take, replace=False).tolist())
            if len(selected) < n:
                remaining = np.setdiff1d(np.arange(len(y)), np.asarray(selected, dtype=int), assume_unique=False)
                take = min(n - len(selected), len(remaining))
                selected.extend(rng.choice(remaining, size=take, replace=False).tolist())
            idx = np.asarray(selected, dtype=int)
            return x[idx], y[idx]
        idx = np.linspace(0, len(x) - 1, n, dtype=int)
        return x[idx], y[idx]
    x_train, y_train = cap(x_train, y_train, args.max_train, args.balance_soc)
    x_valid, y_valid = cap(x_valid, y_valid, args.max_valid)
    x_test, y_test = cap(x_test, y_test, args.max_test)
    loader = DataLoader(TensorDataset(torch.from_numpy(x_train), torch.from_numpy(y_train)), batch_size=args.batch_size, shuffle=True)
    model = LSTMSOC(len(feature_names), args.hidden, args.dropout)
    opt, scheduler = build_optimizer_and_scheduler(model, args)
    loss_fn = nn.MSELoss()
    best, best_loss, stale_epochs, completed_epochs = None, math.inf, 0, 0
    if args.resume_from:
        checkpoint = torch.load(args.resume_from, map_location="cpu")
        if tuple(checkpoint["features"]) != feature_names or checkpoint["window"] != args.window:
            raise ValueError("Checkpoint features or window do not match this training command.")
        if checkpoint["seed"] != args.seed:
            raise ValueError("Checkpoint seed does not match this training command.")
        model.load_state_dict(checkpoint["model_state"])
        opt.load_state_dict(checkpoint["optimizer_state"])
        if checkpoint.get("scheduler_state"):
            scheduler.load_state_dict(checkpoint["scheduler_state"])
        best = checkpoint["best_state"]
        best_loss = float(checkpoint["best_loss"])
        stale_epochs = int(checkpoint["stale_epochs"])
        completed_epochs = int(checkpoint["epochs_completed"])
    training_history = []
    for epoch in range(1, args.epochs + 1):
        model.train()
        training_squared_error = 0.0
        training_samples = 0
        epoch_learning_rate = float(opt.param_groups[0]["lr"])
        for xb, yb in loader:
            opt.zero_grad()
            loss = loss_fn(model(xb), yb)
            loss.backward()
            if args.gradient_clip > 0:
                torch.nn.utils.clip_grad_norm_(model.parameters(), args.gradient_clip)
            opt.step()
            training_squared_error += float(loss.detach()) * len(yb)
            training_samples += len(yb)
        training_loss = training_squared_error / training_samples
        model.eval()
        with torch.no_grad():
            valid_loss = loss_fn(model(torch.from_numpy(x_valid)), torch.from_numpy(y_valid)).item()
        if is_meaningful_improvement(valid_loss, best_loss, args.min_delta):
            best_loss = valid_loss; best = {k: v.detach().clone() for k, v in model.state_dict().items()}; stale_epochs = 0
        else:
            stale_epochs += 1
        scheduler.step(valid_loss)
        completed_epochs += 1
        training_history.append({
            "epoch": completed_epochs,
            "training_mse": training_loss,
            "validation_mse": valid_loss,
            "learning_rate": epoch_learning_rate,
        })
        print(
            f"epoch {completed_epochs} training_mse={training_loss:.6f} "
            f"validation_mse={valid_loss:.6f} learning_rate={epoch_learning_rate:.6g}",
            flush=True,
        )
        if args.patience and stale_epochs >= args.patience:
            print(f"early stopping at epoch {epoch}", flush=True)
            break
    resume_model_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
    model.load_state_dict(best); model.eval()
    with torch.no_grad(): pred = model(torch.from_numpy(x_test)).numpy()
    errors = pred - y_test
    metrics = {"MAE_pct": float(np.mean(np.abs(errors))*100), "RMSE_pct": float(np.sqrt(np.mean(errors**2))*100), "n_train": int(len(y_train)), "n_validation": int(len(y_valid)), "n_test": int(len(y_test)), "train_sessions": train_names, "validation_session": valid_name, "test_session": test_name, "window_steps": args.window, "sample_interval_s": 30, "features": feature_names, "balanced_soc": args.balance_soc, "hidden_size": args.hidden, "dropout": args.dropout, "learning_rate": args.learning_rate, "weight_decay": args.weight_decay, "lr_patience": args.lr_patience, "lr_factor": args.lr_factor, "min_learning_rate": args.min_learning_rate, "min_delta": args.min_delta, "gradient_clip": args.gradient_clip, "seed": args.seed, "epochs_completed": completed_epochs, "best_validation_mse": best_loss}
    args.results_dir.mkdir(parents=True, exist_ok=True)
    (args.results_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (args.results_dir / "training_history.json").write_text(json.dumps(training_history, indent=2), encoding="utf-8")
    training_policy = {
        "hidden_size": args.hidden,
        "dropout": args.dropout,
        "optimizer": "AdamW",
        "learning_rate": args.learning_rate,
        "weight_decay": args.weight_decay,
        "lr_patience": args.lr_patience,
        "lr_factor": args.lr_factor,
        "min_learning_rate": args.min_learning_rate,
        "min_delta": args.min_delta,
        "gradient_clip": args.gradient_clip,
        "patience": args.patience,
    }
    run_config = {
        "data_path": str(args.data.resolve()),
        "train_sessions": train_names,
        "validation_session": valid_name,
        "test_session": test_name,
        "window_steps": args.window,
        "seed": args.seed,
        "training_policy": training_policy,
    }
    (args.results_dir / "run_config.json").write_text(
        json.dumps(run_config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (args.results_dir / "test_predictions.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f); writer.writerow(["reference_soc", "predicted_soc"]); writer.writerows(zip(y_test, pred))
    write_analysis(
        args.results_dir / "test_predictions.csv",
        args.results_dir / "metrics_by_soc.json",
    )
    svg_plot(y_test, pred, args.results_dir / "soc_prediction.svg", metrics["MAE_pct"], metrics["RMSE_pct"])
    torch.save({"state_dict": model.state_dict(), "features": feature_names, "mean": mean, "std": std, "window": args.window}, args.results_dir / "lstm_soc.pt")
    if args.checkpoint:
        args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
        torch.save(make_checkpoint_payload(resume_model_state, opt.state_dict(), best, best_loss, stale_epochs, completed_epochs, feature_names, args.window, args.seed, scheduler.state_dict(), training_policy), args.checkpoint)
    print(json.dumps(metrics, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
