"""Run and report the isolated NASA lifecycle-model experiment suite."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from src.data_processing.prepare_nasa_lifecycle import prepare_improved_nasa_dataset
from src.evaluation.nasa_loco import make_loco_folds
from src.project_paths import DataCenterPaths
from src.training.train_nasa_lifecycle import run_lifecycle_fold
from src.training.train_nasa_state import run_state_fold


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_tree(root: Path) -> dict[str, str]:
    if not root.is_dir():
        return {"missing": str(root)}
    return {str(path.relative_to(root)): _sha256(path) for path in sorted(root.rglob("*")) if path.is_file()}


def comparison_summary(model_mae: float, baseline_mae: float) -> dict[str, float | bool]:
    return {"model_mae": float(model_mae), "baseline_mae": float(baseline_mae), "improved": bool(model_mae < baseline_mae), "mae_change": float(model_mae - baseline_mae)}


def result_dir_name(stage: str, seed: int) -> str:
    """Keep the established seed-42 directory names and isolate every other run."""
    if stage not in {"smoke", "formal"}:
        raise ValueError("stage must be 'smoke' or 'formal'.")
    if seed < 0:
        raise ValueError("seed must be a non-negative integer.")
    return stage if seed == 42 else f"{stage}_seed_{seed}"


def aggregate_folds(folds: list[dict[str, Any]]) -> dict[str, Any]:
    if len(folds) != 4 or {item.get("fold") for item in folds} != {"test_RW9", "test_RW10", "test_RW11", "test_RW12"}:
        raise ValueError("Aggregation requires four successful held-out-cell folds: RW9 through RW12.")
    targets: dict[str, dict[str, list[float]]] = {}
    for result in folds:
        for source in ("lifecycle", "state"):
            for target, metric in result[source]["metrics_by_target"].items():
                targets.setdefault(target, {"MAE": [], "RMSE": []})["MAE"].append(float(metric["MAE"]))
                targets[target]["RMSE"].append(float(metric["RMSE"]))
    return {target: {"mean_MAE": float(np.mean(values["MAE"])), "mean_RMSE": float(np.mean(values["RMSE"])), "fold_count": len(values["MAE"])} for target, values in targets.items()}


def _report(folds: list[dict[str, Any]], aggregate: dict[str, Any]) -> str:
    lines = ["# NASA 生命周期与未来温度模型报告", "", "## 评估方式", "", "四个 RW 电芯依次作为完全独立测试集；其余三个中两个训练、一个验证。旧五状态结果未用于训练。", "", "## 汇总结果", "", "| 目标 | 平均 MAE | 平均 RMSE |", "|---|---:|---:|"]
    lines.extend(f"| {target} | {metric['mean_MAE']:.6f} | {metric['mean_RMSE']:.6f} |" for target, metric in aggregate.items())
    lines.extend(["", "## 模型与标签", "", "- SOC、SOE 与未来 5 分钟温度由三头 LSTM 预测；未来温度不是当前输入温度。", "- SOH、RUL 使用每循环的因果历史特征单独预测；训练时不跨越电芯边界。", "- SOH/RUL 同训练集的中位数基线比较；未来温度同最后一个已观测温度的持续性基线比较。", "- 只有四个 NASA 电芯，结果用于研究验证，不能直接宣称已达到通用工程部署标准。", "", "## 每折结果", ""])
    for result in folds:
        lines.append(f"- {result['fold']}: 训练 {', '.join(result['train_cells'])}；验证 {result['validation_cell']}；测试 {result['test_cell']}。")
    return "\n".join(lines) + "\n"


def run_experiments(stage: str, paths: DataCenterPaths | None = None, seed: int = 42) -> dict[str, Any]:
    if stage not in {"smoke", "formal"}:
        raise ValueError("stage must be 'smoke' or 'formal'.")
    paths = paths or DataCenterPaths.from_config()
    data_dir = paths.nasa_improved_training_dir
    state_csv, lifecycle_csv = data_dir / "nasa_state_future_samples.csv", data_dir / "nasa_lifecycle_cycles.csv"
    prepare_improved_nasa_dataset(paths.nasa_raw_dir / "randomized", data_dir, overwrite=True)
    results_root = paths.nasa_lifecycle_results_dir / result_dir_name(stage, seed)
    results_root.mkdir(parents=True, exist_ok=True)
    baseline_dir = paths.nasa_results_dir / "run_20260726_5state"
    hashes_before = _hash_tree(baseline_dir)
    (results_root / "baseline_hashes_before.json").write_text(json.dumps(hashes_before, ensure_ascii=False, indent=2), encoding="utf-8")
    folds_output: list[dict[str, Any]] = []
    for fold in make_loco_folds(("RW9", "RW10", "RW11", "RW12")):
        fold_dir = results_root / fold.name
        lifecycle = run_lifecycle_fold(lifecycle_csv, fold, fold_dir / "lifecycle", seed=seed)
        state = run_state_fold(state_csv, fold, fold_dir / "state", window=30, epochs=1 if stage == "smoke" else 25, seed=seed)
        folds_output.append({"fold": fold.name, "train_cells": list(fold.train_cells), "validation_cell": fold.validation_cell, "test_cell": fold.test_cell, "lifecycle": lifecycle, "state": state})
    hashes_after = _hash_tree(baseline_dir)
    (results_root / "baseline_hashes_after.json").write_text(json.dumps(hashes_after, ensure_ascii=False, indent=2), encoding="utf-8")
    if hashes_before != hashes_after:
        raise RuntimeError("The frozen five-state baseline changed; new experiment is invalid.")
    aggregate = aggregate_folds(folds_output)
    (results_root / "aggregate_metrics.json").write_text(json.dumps(aggregate, ensure_ascii=False, indent=2), encoding="utf-8")
    (results_root / "comparison_report.md").write_text(_report(folds_output, aggregate), encoding="utf-8")
    manifest = {"stage": stage, "seed": seed, "data_dir": str(data_dir), "results_root": str(results_root), "folds": [item["fold"] for item in folds_output], "baseline_hash_verified": True}
    (results_root / "implementation_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"aggregate": aggregate, "results_root": results_root, "folds": folds_output}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run NASA lifecycle and future-temperature LOCO experiments.")
    parser.add_argument("--stage", choices=("smoke", "formal"), required=True)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    result = run_experiments(args.stage, seed=args.seed)
    print(json.dumps({"results_root": str(result["results_root"]), "aggregate": result["aggregate"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
