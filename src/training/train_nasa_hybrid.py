"""Unified four-cell NASA workflow for electrical state, temperature, and lifecycle health."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from src.evaluation.nasa_loco import make_loco_folds
from src.training.train_nasa_lifecycle import run_lifecycle_fold
from src.training.train_nasa_state import run_state_fold


TARGETS = ("soc", "soe", "soh", "rul_cycles", "sot_5min_c")


def aggregate_target_metrics(
    fold_metrics: dict[str, dict[str, float | int | str]],
    fold_baselines: dict[str, dict[str, float | int | str]] | None = None,
) -> dict[str, Any]:
    if set(fold_metrics) != {"test_RW9", "test_RW10", "test_RW11", "test_RW12"}:
        raise ValueError("Target aggregation requires all four held-out-cell folds.")
    mean_mae = float(np.mean([float(item["MAE"]) for item in fold_metrics.values()]))
    mean_rmse = float(np.mean([float(item["RMSE"]) for item in fold_metrics.values()]))
    worst_fold = max(fold_metrics, key=lambda fold: float(fold_metrics[fold]["MAE"]))
    result: dict[str, Any] = {
        "mean_MAE": mean_mae, "mean_RMSE": mean_rmse, "fold_count": 4,
        "worst_fold": worst_fold, "worst_MAE": float(fold_metrics[worst_fold]["MAE"]),
        "fold_metrics": fold_metrics,
    }
    if fold_baselines is not None:
        if set(fold_baselines) != set(fold_metrics):
            raise ValueError("Baseline folds must match model folds.")
        baseline_mae = float(np.mean([float(item["MAE"]) for item in fold_baselines.values()]))
        result.update({"baseline_mean_MAE": baseline_mae, "beats_baseline": mean_mae < baseline_mae})
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_tree(root: Path | None) -> dict[str, str]:
    if root is None:
        return {}
    root = Path(root)
    return {str(path.relative_to(root)): _sha256(path) for path in sorted(root.rglob("*")) if path.is_file()}


def _report(aggregate: dict[str, dict[str, Any]]) -> str:
    lines = ["# NASA 混合五状态四折泛化报告", "", "SOT 为未来 300 秒温度；指标为四个留一电芯折的宏平均。", "", "| 目标 | 平均 MAE | 最差电芯 | 最差 MAE | 基线结论 |", "|---|---:|---|---:|---|"]
    for target in TARGETS:
        item = aggregate[target]
        baseline = "不适用" if "beats_baseline" not in item else ("超过基线" if item["beats_baseline"] else "未超过基线")
        lines.append(f"| {target} | {item['mean_MAE']:.6f} | {item['worst_fold'].removeprefix('test_')} | {item['worst_MAE']:.6f} | {baseline} |")
    lines.extend(["", "只有四个 RW 电芯，本结果用于研究验证，不能直接宣称已达到通用部署标准。", ""])
    return "\n".join(lines)


def run_hybrid(state_data: Path, lifecycle_data: Path, results_dir: Path, *, stage: str, seed: int = 42,
               legacy_results_dir: Path | None = None) -> dict[str, Any]:
    if stage not in {"smoke", "formal"}:
        raise ValueError("stage must be smoke or formal")
    state_data, lifecycle_data, results_dir = Path(state_data), Path(lifecycle_data), Path(results_dir)
    if not state_data.is_file() or not lifecycle_data.is_file():
        raise FileNotFoundError("Both prepared NASA CSV files are required.")
    if results_dir.exists() and any(results_dir.iterdir()):
        raise ValueError(f"Hybrid results directory must be empty: {results_dir}")
    results_dir.mkdir(parents=True, exist_ok=True)
    hashes_before = _hash_tree(legacy_results_dir)
    fold_outputs: dict[str, dict[str, Any]] = {}
    epochs = 1 if stage == "smoke" else 25
    for index, fold in enumerate(make_loco_folds(("RW9", "RW10", "RW11", "RW12")), start=1):
        fold_dir = results_dir / fold.name
        state = run_state_fold(state_data, fold, fold_dir, window=30, epochs=epochs, seed=seed)
        lifecycle = run_lifecycle_fold(lifecycle_data, fold, fold_dir / "lifecycle", seed=seed)
        fold_outputs[fold.name] = {"state": state, "lifecycle": lifecycle}
        print(f"PROGRESS: {round(index * 90 / 4)}", flush=True)
    aggregate: dict[str, dict[str, Any]] = {}
    for target in TARGETS:
        metrics = {}
        baselines = {}
        for fold_name, output in fold_outputs.items():
            source = output["lifecycle"] if target in {"soh", "rul_cycles"} else output["state"]
            metrics[fold_name] = source["metrics_by_target"][target]
            if target in {"soh", "rul_cycles"}:
                baselines[fold_name] = source["baseline_metrics"][target]
            elif target == "sot_5min_c":
                baselines[fold_name] = source["persistence_metrics"][target]
        aggregate[target] = aggregate_target_metrics(metrics, baselines or None)
    hashes_after = _hash_tree(legacy_results_dir)
    if hashes_before != hashes_after:
        raise RuntimeError("The frozen legacy five-state baseline changed during training.")
    (results_dir / "aggregate_metrics.json").write_text(json.dumps(aggregate, ensure_ascii=False, indent=2), encoding="utf-8")
    acceptance: dict[str, dict[str, object]] = {}
    for target, item in aggregate.items():
        fold_verdicts: list[bool] = []
        for fold_name in fold_outputs:
            source_dir = results_dir / fold_name / ("lifecycle" if target in {"soh", "rul_cycles"} else "")
            if target in {"soc", "soe", "sot_5min_c"}:
                source_dir = results_dir / fold_name
            audit_path = source_dir / "acceptance.json"
            if audit_path.is_file():
                value = json.loads(audit_path.read_text(encoding="utf-8")).get(target, {})
                fold_verdicts.append(bool(value.get("passed", False)))
        acceptance[target] = {"passed": bool(fold_verdicts) and all(fold_verdicts), "fold_pass_count": sum(fold_verdicts), "fold_count": len(fold_verdicts), "mean_MAE": item["mean_MAE"]}
    (results_dir / "acceptance.json").write_text(json.dumps(acceptance, ensure_ascii=False, indent=2), encoding="utf-8")
    (results_dir / "comparison_report.md").write_text(_report(aggregate), encoding="utf-8")
    config = {"stage": stage, "seed": seed, "sot_horizon_s": 300.0, "state_data": str(state_data.resolve()), "state_data_sha256": _sha256(state_data), "lifecycle_data": str(lifecycle_data.resolve()), "lifecycle_data_sha256": _sha256(lifecycle_data), "folds": list(fold_outputs), "legacy_baseline_hash_verified": hashes_before == hashes_after}
    (results_dir / "run_config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    (results_dir / "baseline_hashes_before.json").write_text(json.dumps(hashes_before, indent=2), encoding="utf-8")
    (results_dir / "baseline_hashes_after.json").write_text(json.dumps(hashes_after, indent=2), encoding="utf-8")
    from src.desktop.hybrid_charts import build_hybrid_charts
    build_hybrid_charts(results_dir)
    print("PROGRESS: 100", flush=True)
    return {"aggregate": aggregate, "results_dir": results_dir, "folds": fold_outputs}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train the hybrid NASA five-state workflow.")
    parser.add_argument("--state-data", type=Path, required=True)
    parser.add_argument("--lifecycle-data", type=Path, required=True)
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--stage", choices=("smoke", "formal"), required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--legacy-results-dir", type=Path)
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    result = run_hybrid(args.state_data, args.lifecycle_data, args.results_dir, stage=args.stage, seed=args.seed, legacy_results_dir=args.legacy_results_dir)
    print(json.dumps(result["aggregate"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
