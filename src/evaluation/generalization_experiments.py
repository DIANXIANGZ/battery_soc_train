"""Run leakage-safe A123#3 generalization experiments and gated A123#5 evaluation."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import argparse
import csv
import hashlib
import json
import re
import shutil
import statistics
import subprocess
import sys

from src.desktop.charts import ensure_run_charts
from src.project_paths import DataCenterPaths


APPROVED_SEEDS = (11, 23, 42, 67, 101)
REQUIRED_ARTIFACTS = {
    "metrics.json",
    "metrics_by_soc.json",
    "training_history.json",
    "test_predictions.csv",
    "soc_prediction.png",
    "validation_loss.png",
    "lstm_soc.pt",
    "run_config.json",
    "run.log",
}


@dataclass(frozen=True)
class ExperimentJob:
    job_id: str
    stage: str
    seed: int
    train_sessions: tuple[str, ...]
    validation_session: str
    test_session: str
    results_dir: Path


def _validate_formal_sessions(sessions) -> list[str]:
    ordered = sorted(sessions)
    if len(ordered) != 6 or len(set(ordered)) != 6:
        raise ValueError("Formal generalization experiments require exactly six unique sessions.")
    invalid = [name for name in ordered if not name.startswith("A123#3")]
    if invalid:
        raise ValueError(f"Formal sessions must all belong to A123#3: {invalid}")
    return ordered


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_")


def assert_a1233_only(job: ExperimentJob) -> None:
    selected = list(job.train_sessions) + [job.validation_session, job.test_session]
    if any(not name.startswith("A123#3") for name in selected):
        raise ValueError("Experiment jobs may contain A123#3 sessions only.")
    if len(selected) != len(set(selected)):
        raise ValueError("Experiment job contains overlap between train/validation/test sessions.")


def make_seed_jobs(sessions, root: Path) -> list[ExperimentJob]:
    ordered = _validate_formal_sessions(sessions)
    train, validation, test = tuple(ordered[:-2]), ordered[-2], ordered[-1]
    jobs = []
    for seed in APPROVED_SEEDS:
        job_id = f"seed-{seed:03d}"
        job = ExperimentJob(
            job_id=job_id,
            stage="seed",
            seed=seed,
            train_sessions=train,
            validation_session=validation,
            test_session=test,
            results_dir=Path(root) / "seed_runs" / job_id,
        )
        assert_a1233_only(job)
        jobs.append(job)
    return jobs


def make_loso_jobs(sessions, root: Path, seed: int) -> list[ExperimentJob]:
    ordered = _validate_formal_sessions(sessions)
    jobs = []
    for index, test in enumerate(ordered):
        validation = ordered[(index - 1) % len(ordered)]
        train = tuple(name for name in ordered if name not in (validation, test))
        job_id = f"loso-{index + 1:02d}-{_safe_name(test)}"
        job = ExperimentJob(
            job_id=job_id,
            stage="loso",
            seed=seed,
            train_sessions=train,
            validation_session=validation,
            test_session=test,
            results_dir=Path(root) / "loso_runs" / job_id,
        )
        assert_a1233_only(job)
        jobs.append(job)
    return jobs


def sha256_files(paths) -> dict[str, str]:
    hashes = {}
    for path in paths:
        resolved = Path(path).resolve()
        digest = hashlib.sha256()
        with resolved.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        hashes[str(resolved)] = digest.hexdigest()
    return hashes


def verify_required_artifacts(run_dir: Path) -> bool:
    run_dir = Path(run_dir)
    return all((run_dir / name).is_file() and (run_dir / name).stat().st_size > 0 for name in REQUIRED_ARTIFACTS)


def _write_json_atomic(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _training_command(job: ExperimentJob, python_executable: Path, data_path: Path) -> list[str]:
    return [
        str(python_executable),
        "-m", "src.training.train_lstm",
        "--data", str(data_path),
        "--results-dir", str(job.results_dir),
        "--train-sessions", *job.train_sessions,
        "--validation-session", job.validation_session,
        "--test-session", job.test_session,
        "--window", "60",
        "--epochs", "40",
        "--batch-size", "512",
        "--max-train", "40000",
        "--max-valid", "20000",
        "--max-test", "20000",
        "--hidden", "32",
        "--dropout", "0.1",
        "--learning-rate", "0.0003",
        "--weight-decay", "0.0001",
        "--lr-patience", "3",
        "--lr-factor", "0.5",
        "--min-learning-rate", "0.00003",
        "--min-delta", "0.00001",
        "--gradient-clip", "1.0",
        "--patience", "9",
        "--seed", str(job.seed),
        "--add-delta-ah",
        "--balance-soc",
    ]


def _apply_training_overrides(command: list[str], overrides: dict | None) -> list[str]:
    command = list(command)
    for key, value in (overrides or {}).items():
        option = "--" + key.replace("_", "-")
        if option not in command:
            raise ValueError(f"Unsupported training override: {key}")
        command[command.index(option) + 1] = str(value)
    return command


def run_job(
    job: ExperimentJob,
    python_executable: Path,
    data_path: Path,
    project_root: Path,
    *,
    command_override: list[str] | None = None,
    training_overrides: dict | None = None,
    minimum_free_bytes: int = 2 * 1024**3,
) -> dict:
    assert_a1233_only(job)
    run_dir = Path(job.results_dir)
    status_path = run_dir / "status.json"
    if run_dir.exists() and any(run_dir.iterdir()):
        if not status_path.is_file():
            raise FileExistsError(f"Refusing to overwrite unrecognized directory: {run_dir}")
        saved = json.loads(status_path.read_text(encoding="utf-8"))
        if saved.get("state") == "succeeded" and verify_required_artifacts(run_dir):
            return {**saved, "skipped": True}
    else:
        run_dir.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(run_dir).free < minimum_free_bytes:
        raise OSError("Not enough free disk space for a formal SOC training run.")

    command = command_override or _apply_training_overrides(
        _training_command(job, python_executable, data_path), training_overrides
    )
    running = {
        "job_id": job.job_id,
        "stage": job.stage,
        "state": "running",
        "command": command,
        "skipped": False,
    }
    _write_json_atomic(status_path, running)
    log_path = run_dir / "run.log"
    with log_path.open("w", encoding="utf-8") as log:
        completed = subprocess.run(
            command,
            cwd=Path(project_root),
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    if completed.returncode == 0:
        ensure_run_charts(run_dir)
    succeeded = completed.returncode == 0 and verify_required_artifacts(run_dir)
    final = {
        **running,
        "state": "succeeded" if succeeded else "failed",
        "returncode": completed.returncode,
    }
    if completed.returncode == 0 and not succeeded:
        final["error"] = "Training returned success but required artifacts are incomplete."
    _write_json_atomic(status_path, final)
    return final


def _metric_statistics(records: list[dict], key: str) -> dict:
    values = [float(record[key]) for record in records]
    worst = max(records, key=lambda record: (float(record[key]), record["job_id"]))
    return {
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "standard_deviation": statistics.pstdev(values),
        "minimum": min(values),
        "maximum": max(values),
        "worst_job_id": worst["job_id"],
    }


def summarize_stage(run_dirs) -> dict:
    records = []
    for run_dir in run_dirs:
        run_dir = Path(run_dir)
        status_path = run_dir / "status.json"
        metrics_path = run_dir / "metrics.json"
        if not status_path.is_file() or not metrics_path.is_file():
            continue
        status = json.loads(status_path.read_text(encoding="utf-8"))
        if status.get("state") != "succeeded":
            continue
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        records.append({
            "job_id": status.get("job_id", run_dir.name),
            "seed": int(metrics.get("seed", 0)),
            "MAE_pct": float(metrics["MAE_pct"]),
            "RMSE_pct": float(metrics["RMSE_pct"]),
        })
    summary = {"count": len(records), "runs": records}
    if records:
        summary["MAE_pct"] = _metric_statistics(records, "MAE_pct")
        summary["RMSE_pct"] = _metric_statistics(records, "RMSE_pct")
    return summary


def select_median_seed(records: list[dict]) -> dict:
    median_mae = statistics.median(float(record["MAE_pct"]) for record in records)
    selected = min(
        records,
        key=lambda record: (abs(float(record["MAE_pct"]) - median_mae), int(record["seed"])),
    )
    return {
        "seed": int(selected["seed"]),
        "job_id": selected["job_id"],
        "MAE_pct": float(selected["MAE_pct"]),
        "selection_rule": "closest_to_five_seed_median_mae_then_lower_seed",
    }


def evaluate_internal_gate(seed_summary: dict, loso_summary: dict) -> dict:
    if seed_summary.get("count") != 5 or loso_summary.get("count") != 6:
        return {
            "state": "incomplete",
            "passed": False,
            "required_seed_runs": 5,
            "required_loso_runs": 6,
        }
    seed_mean = float(seed_summary["MAE_pct"]["mean"])
    loso_worst = float(loso_summary["MAE_pct"]["maximum"])
    passed = seed_mean <= 3.5 and loso_worst <= 8.0
    result = {
        "state": "passed" if passed else "failed",
        "passed": passed,
        "seed_mean_MAE_pct": seed_mean,
        "loso_worst_MAE_pct": loso_worst,
        "thresholds": {"seed_mean_MAE_pct": 3.5, "loso_worst_MAE_pct": 8.0},
    }
    if seed_summary.get("runs"):
        result["selected_seed"] = select_median_seed(seed_summary["runs"])
    return result


def run_candidate_and_cross_cell(
    internal_gate: dict,
    candidate_model: Path,
    a1235_csv: Path,
    output_dir: Path,
    current_metrics_path: Path,
    *,
    protected_dirs=(),
    evaluator=None,
    writer=None,
) -> dict:
    if not internal_gate.get("passed") or internal_gate.get("state") != "passed":
        return {
            "decision": "skipped_internal_gate",
            "internal_gate_state": internal_gate.get("state", "incomplete"),
        }
    from src.evaluation.evaluate_external_cell import evaluate_csv, write_results

    evaluator = evaluator or evaluate_csv
    writer = writer or write_results
    output_dir = Path(output_dir)
    decision_path = output_dir.parent / "final_decision.json"
    if decision_path.is_file():
        return json.loads(decision_path.read_text(encoding="utf-8"))
    candidate_model = Path(candidate_model)
    a1235_csv = Path(a1235_csv)
    current_metrics_path = Path(current_metrics_path)
    for required in (candidate_model, a1235_csv, current_metrics_path):
        if not required.is_file():
            raise FileNotFoundError(required)

    metrics, predictions = evaluator(a1235_csv, candidate_model, "A123#5")
    writer(output_dir, metrics, predictions, protected_dirs=protected_dirs)
    current_metrics = json.loads(current_metrics_path.read_text(encoding="utf-8"))
    candidate_mae = float(metrics["MAE_pct"])
    current_mae = float(current_metrics["MAE_pct"])
    if candidate_mae <= 2.3:
        decision = "preferred_target_met"
    elif candidate_mae <= current_mae:
        decision = "non_degrading_candidate"
    else:
        decision = "keep_existing_baseline"
    result = {
        "decision": decision,
        "candidate_A1235_MAE_pct": candidate_mae,
        "current_A1235_MAE_pct": current_mae,
        "preferred_target_MAE_pct": 2.3,
        "candidate_model_sha256": sha256_files([candidate_model])[str(candidate_model.resolve())],
        "target_data": str(a1235_csv.resolve()),
        "label_note": "A123#5 error is against an offline Coulomb-counting reference label, not physical SOC ground truth.",
        "scope_note": "The decision covers only the processed A123#5 sessions listed in the evaluation metrics.",
    }
    _write_json_atomic(decision_path, result)
    return result


def read_session_names(data_path: Path) -> list[str]:
    names = []
    seen = set()
    with Path(data_path).open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            name = row.get("session", "")
            if name and name not in seen:
                seen.add(name)
                names.append(name)
    return names


def make_candidate_job(sessions, root: Path, seed: int) -> ExperimentJob:
    ordered = _validate_formal_sessions(sessions)
    job = ExperimentJob(
        job_id=f"candidate-seed-{seed:03d}",
        stage="candidate",
        seed=seed,
        train_sessions=tuple(ordered[:-2]),
        validation_session=ordered[-2],
        test_session=ordered[-1],
        results_dir=Path(root) / "candidate",
    )
    assert_a1233_only(job)
    return job


def _write_summary_csv(path: Path, loso_summary: dict) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["job_id", "MAE_pct", "RMSE_pct"],
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(loso_summary.get("runs", []))


def write_report(
    output: Path,
    seed_summary: dict,
    loso_summary: dict,
    gate: dict,
    decision: dict | None = None,
) -> None:
    decision = decision or {"decision": "not_run"}
    lines = [
        "# SOC 综合泛化验证报告",
        "",
        f"结论：`{decision.get('decision', gate.get('state', 'incomplete'))}`",
        "",
        "## 验收标准",
        "",
        "- 五随机种子平均 MAE ≤ 3.5%",
        "- 留一工况最差 MAE ≤ 8%",
        "- A123#5 当前结果不得退化，优选目标 MAE ≤ 2.3%",
        "",
        "## 内部验证",
        "",
        f"- 五种子数量：{seed_summary.get('count', 0)}",
        f"- 五种子平均 MAE：{seed_summary.get('MAE_pct', {}).get('mean')}",
        f"- 五种子标准差：{seed_summary.get('MAE_pct', {}).get('standard_deviation')}",
        f"- 留一工况数量：{loso_summary.get('count', 0)}",
        f"- 留一工况最差 MAE：{loso_summary.get('MAE_pct', {}).get('maximum')}",
        f"- 内部门状态：{gate.get('state', 'incomplete')}",
        "",
        "| 留一任务 | MAE (%) | RMSE (%) |",
        "|---|---:|---:|",
    ]
    for run in loso_summary.get("runs", []):
        lines.append(f"| {run['job_id']} | {run['MAE_pct']:.6f} | {run['RMSE_pct']:.6f} |")
    lines.extend([
        "",
        "## A123#5 跨电芯结果",
        "",
        f"- 决策：{decision.get('decision', 'not_run')}",
        f"- 候选 MAE：{decision.get('candidate_A1235_MAE_pct')}",
        f"- 范围：{decision.get('scope_note', '尚未执行跨电芯评估')}",
        "",
        "## 限制",
        "",
        "SOC 误差相对于离线库仑计量参考标签计算，不是独立测得的物理 SOC 真值。<!-- ���ؼ��� -->",
        "A123#5 不参与训练、归一化、早停、学习率调度或模型选择。",
    ])
    Path(output).write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_report(
    output: Path,
    seed_summary: dict,
    loso_summary: dict,
    gate: dict,
    decision: dict | None = None,
) -> None:
    """Write the user-facing report in valid UTF-8 Chinese."""
    decision = decision or {"decision": "not_run"}
    lines = [
        "# SOC 综合泛化验证报告", "",
        f"结论：`{decision.get('decision', gate.get('state', 'incomplete'))}`", "",
        "## 验收标准", "",
        "- 五随机种子平均 MAE ≤ 3.5%",
        "- 留一工况最差 MAE ≤ 8%",
        "- A123#5 当前结果不得退化，优选目标 MAE ≤ 2.3%", "",
        "## 内部验证", "",
        f"- 五种子数量：{seed_summary.get('count', 0)}",
        f"- 五种子平均 MAE：{seed_summary.get('MAE_pct', {}).get('mean')}",
        f"- 五种子标准差：{seed_summary.get('MAE_pct', {}).get('standard_deviation')}",
        f"- 留一工况数量：{loso_summary.get('count', 0)}",
        f"- 留一工况最差 MAE：{loso_summary.get('MAE_pct', {}).get('maximum')}",
        f"- 内部门状态：{gate.get('state', 'incomplete')}", "",
        "| 留一任务 | MAE (%) | RMSE (%) |", "|---|---:|---:|",
    ]
    for run in loso_summary.get("runs", []):
        lines.append(f"| {run['job_id']} | {run['MAE_pct']:.6f} | {run['RMSE_pct']:.6f} |")
    lines.extend([
        "", "## A123#5 跨电芯结果", "",
        f"- 决策：{decision.get('decision', 'not_run')}",
        f"- 候选 MAE：{decision.get('candidate_A1235_MAE_pct')}",
        f"- 范围：{decision.get('scope_note', '尚未执行跨电芯评估')}",
        "", "## 限制", "",
        "SOC 误差相对于离线库仑计量参考标签计算，不是独立测得的物理 SOC 真值。",
        "A123#5 不参与训练、归一化、早停、学习率调度或模型选择。",
    ])
    Path(output).write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_implementation_manifest(
    output: Path, *, project_root: Path, experiment_root: Path,
    code_paths, test_paths, baseline_before: dict, baseline_after: dict,
    test_count: int, final_decision: str,
) -> dict:
    import torch

    completed_jobs = sum(
        json.loads(path.read_text(encoding="utf-8")).get("state") == "succeeded"
        for path in Path(experiment_root).rglob("status.json")
    )
    payload = {
        "project_root": str(Path(project_root).resolve()),
        "experiment_root": str(Path(experiment_root).resolve()),
        "code_sha256": sha256_files(code_paths),
        "test_sha256": sha256_files(test_paths),
        "baseline_hashes_before": baseline_before,
        "baseline_hashes_after": baseline_after,
        "baseline_unchanged": baseline_before == baseline_after,
        "test_count": int(test_count),
        "python_version": sys.version.split()[0],
        "pytorch_version": torch.__version__,
        "completed_job_count": completed_jobs,
        "final_decision": final_decision,
    }
    _write_json_atomic(Path(output), payload)
    return payload


def _baseline_paths(paths: DataCenterPaths) -> list[Path]:
    return [
        paths.baseline_results_dir / "lstm_soc.pt",
        paths.baseline_results_dir / "metrics.json",
        paths.cross_cell_results_dir / "metrics.json",
    ]


def _write_internal_outputs(root: Path, seed_summary: dict, loso_summary: dict, gate: dict) -> dict:
    _write_json_atomic(root / "seed_summary.json", seed_summary)
    _write_json_atomic(root / "loso_summary.json", loso_summary)
    _write_json_atomic(root / "internal_gate.json", gate)
    generalization_summary = {
        "seed_mean_MAE_pct": seed_summary.get("MAE_pct", {}).get("mean"),
        "loso_worst_MAE_pct": loso_summary.get("MAE_pct", {}).get("maximum"),
        "A1235_MAE_pct": None,
        "decision": gate.get("state", "incomplete"),
    }
    _write_json_atomic(root / "generalization_summary.json", generalization_summary)
    _write_summary_csv(root / "generalization_summary.csv", loso_summary)
    write_report(root / "综合泛化验证报告.md", seed_summary, loso_summary, gate)
    return generalization_summary


def execute_internal(
    paths: DataCenterPaths,
    root: Path,
    python_executable: Path,
    project_root: Path,
    *,
    smoke: bool = False,
) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    sessions = read_session_names(paths.training_csv)
    _validate_formal_sessions(sessions)
    baseline_before = sha256_files(_baseline_paths(paths))
    _write_json_atomic(root / "baseline_hashes_before.json", baseline_before)
    overrides = {
        "epochs": 1,
        "max_train": 1000,
        "max_valid": 500,
        "max_test": 500,
        "batch_size": 64,
        "hidden": 8,
    } if smoke else None
    seed_jobs = make_seed_jobs(sessions, root)
    for job in seed_jobs:
        run_job(job, python_executable, paths.training_csv, project_root, training_overrides=overrides)
    seed_summary = summarize_stage([job.results_dir for job in seed_jobs])
    selected_seed = select_median_seed(seed_summary["runs"])["seed"] if seed_summary.get("runs") else 42
    loso_jobs = make_loso_jobs(sessions, root, selected_seed)
    for job in loso_jobs:
        run_job(job, python_executable, paths.training_csv, project_root, training_overrides=overrides)
    loso_summary = summarize_stage([job.results_dir for job in loso_jobs])
    gate = evaluate_internal_gate(seed_summary, loso_summary)
    summary = _write_internal_outputs(root, seed_summary, loso_summary, gate)
    baseline_after = sha256_files(_baseline_paths(paths))
    _write_json_atomic(root / "baseline_hashes_after.json", baseline_after)
    if baseline_before != baseline_after:
        raise RuntimeError("Protected baseline hashes changed during internal experiments.")
    return summary


def execute_cross_cell(
    paths: DataCenterPaths,
    root: Path,
    python_executable: Path,
    project_root: Path,
) -> dict:
    gate_path = root / "internal_gate.json"
    if not gate_path.is_file():
        raise ValueError("Internal evidence must be completed before cross-cell evaluation.")
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    if not gate.get("passed"):
        return {"decision": "skipped_internal_gate", "internal_gate_state": gate.get("state")}
    sessions = read_session_names(paths.training_csv)
    seed = int(gate["selected_seed"]["seed"])
    candidate = make_candidate_job(sessions, root, seed)
    status = run_job(candidate, python_executable, paths.training_csv, project_root)
    if status.get("state") != "succeeded":
        return {"decision": "candidate_training_failed"}
    decision = run_candidate_and_cross_cell(
        gate,
        candidate.results_dir / "lstm_soc.pt",
        paths.a1235_processed_csv,
        root / "cross_cell_candidate",
        paths.cross_cell_results_dir / "metrics.json",
        protected_dirs=[paths.baseline_results_dir, paths.cross_cell_results_dir],
    )
    seed_summary = json.loads((root / "seed_summary.json").read_text(encoding="utf-8"))
    loso_summary = json.loads((root / "loso_summary.json").read_text(encoding="utf-8"))
    summary = {
        "seed_mean_MAE_pct": seed_summary["MAE_pct"]["mean"],
        "loso_worst_MAE_pct": loso_summary["MAE_pct"]["maximum"],
        "A1235_MAE_pct": decision.get("candidate_A1235_MAE_pct"),
        "decision": decision["decision"],
    }
    _write_json_atomic(root / "generalization_summary.json", summary)
    write_report(root / "综合泛化验证报告.md", seed_summary, loso_summary, gate, decision)
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run leakage-safe SOC generalization experiments.")
    parser.add_argument("--stage", choices=("smoke", "internal", "cross-cell", "all"), required=True)
    parser.add_argument("--results-root", type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    paths = DataCenterPaths.from_config()
    from src.platform.platform_core import resolve_training_python

    project_root = Path(__file__).resolve().parents[2]
    python_executable = resolve_training_python(project_root)
    default_name = "smoke" if args.stage == "smoke" else "formal"
    root = args.results_root or paths.generalization_results_dir / default_name
    if args.stage == "smoke":
        result = execute_internal(paths, root, python_executable, project_root, smoke=True)
    elif args.stage == "internal":
        result = execute_internal(paths, root, python_executable, project_root)
    elif args.stage == "cross-cell":
        result = execute_cross_cell(paths, root, python_executable, project_root)
    else:
        result = execute_internal(paths, root, python_executable, project_root)
        gate = json.loads((root / "internal_gate.json").read_text(encoding="utf-8"))
        if gate.get("passed"):
            result = execute_cross_cell(paths, root, python_executable, project_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
