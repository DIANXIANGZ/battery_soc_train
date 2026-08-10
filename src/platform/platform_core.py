"""Safe local storage primitives for the multi-project training console."""

from __future__ import annotations

import json
import csv
import shutil
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.custom_training.algorithms import ALGORITHM_REGISTRY
from src.custom_training.capability import create_training_capability, verify_training_capability
from src.custom_training.dataset import CustomDatasetConfig, validate_and_export


@dataclass(frozen=True)
class Project:
    project_id: str
    name: str
    trainer_script: str
    data_path: str
    path: Path


@dataclass(frozen=True)
class RunResult:
    path: Path
    status: str
    metrics: Optional[Dict[str, object]]
    chart_path: Optional[Path]
    log_path: Optional[Path]


class PlatformStore:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.projects_dir = self.root / "projects"
        self.registry_path = self.root / "projects.json"
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        if not self.registry_path.exists():
            self.registry_path.write_text("[]", encoding="utf-8")

    def _load_records(self) -> List[dict]:
        return json.loads(self.registry_path.read_text(encoding="utf-8"))

    def _save_records(self, records: List[dict]) -> None:
        self.registry_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

    def _replace_record(self, project_id: str, **updates: object) -> None:
        records = self._load_records()
        for record in records:
            if record["project_id"] == project_id:
                record.update(updates)
                self._save_records(records)
                return
        raise ValueError("Project was not found.")

    def create_project(self, name: str, trainer_script: str, data_path: str) -> Project:
        cleaned_name = name.strip()
        if not cleaned_name:
            raise ValueError("Project name is required.")
        if any(record["name"] == cleaned_name for record in self._load_records()):
            raise ValueError("A project with this name already exists.")
        project_id = uuid.uuid4().hex[:12]
        project_path = self.projects_dir / project_id
        for directory in ("datasets", "runs", "archive"):
            (project_path / directory).mkdir(parents=True, exist_ok=True)
        record = {
            "project_id": project_id,
            "name": cleaned_name,
            "trainer_script": trainer_script,
            "data_path": data_path,
        }
        records = self._load_records(); records.append(record); self._save_records(records)
        return self._project_from_record(record)

    def _project_from_record(self, record: dict) -> Project:
        return Project(
            project_id=record["project_id"],
            name=record["name"],
            trainer_script=record["trainer_script"],
            data_path=record["data_path"],
            path=self.projects_dir / record["project_id"],
        )

    def list_projects(self) -> List[Project]:
        return [self._project_from_record(record) for record in self._load_records()]

    def get_project(self, project_id: str) -> Project:
        for project in self.list_projects():
            if project.project_id == project_id:
                return project
        raise ValueError("Project was not found.")

    def _ensure_named_project(self, name: str, trainer_script: Path, data_path: Path) -> Project:
        trainer = str(Path(trainer_script).resolve())
        data = str(Path(data_path).resolve())
        records = self._load_records()
        for record in records:
            if record["name"] == name:
                record["trainer_script"] = trainer
                record["data_path"] = data
                self._save_records(records)
                return self._project_from_record(record)
        return self.create_project(name, trainer, data)

    def ensure_soc_project(self, trainer_script: Path, data_path: Path) -> Project:
        return self._ensure_named_project("A123 SOC", trainer_script, data_path)

    def ensure_nasa_multistate_project(self, trainer_script: Path, data_path: Path) -> Project:
        return self._ensure_named_project("NASA 五状态", trainer_script, data_path)

    def ensure_nasa_lifecycle_project(self, trainer_script: Path, data_path: Path) -> Project:
        return self._ensure_named_project("NASA 生命周期模型", trainer_script, data_path)

    def ensure_nasa_hybrid_project(self, trainer_script: Path, lifecycle_data_path: Path) -> Project:
        return self._ensure_named_project("NASA 五状态（改进）", trainer_script, lifecycle_data_path)

    def create_custom_project(self, name: str, config: CustomDatasetConfig, trainer_script: Path) -> Project:
        """Create one self-contained project from an imported user dataset."""
        project = self.create_project(name, str(Path(trainer_script).resolve()), "")
        data_path = self.safe_child(project, "datasets/custom_training.csv")
        try:
            validate_and_export(config, data_path, minimum_rows=30)
            serialized_config = {
                "source_path": str(Path(config.source_path).resolve()),
                "sheet_name": config.sheet_name,
                "time_column": config.time_column,
                "feature_columns": list(config.feature_columns),
                "target_columns": list(config.target_columns),
                "algorithm": config.algorithm,
                "role_columns": [list(item) for item in config.role_columns],
            }
            self._replace_record(
                project.project_id,
                data_path=str(data_path),
                custom_config=serialized_config,
                custom_admission={
                    "configuration_allowed": True,
                    "training_allowed": False,
                    "blockers": ["configuration_changed", "chief_engineer_approval_required"],
                },
            )
        except Exception:
            records = [record for record in self._load_records() if record["project_id"] != project.project_id]
            self._save_records(records)
            shutil.rmtree(project.path, ignore_errors=True)
            raise
        return self.get_project(project.project_id)

    def custom_config_for(self, project: Project) -> dict:
        for record in self._load_records():
            if record["project_id"] == project.project_id:
                config = record.get("custom_config")
                if isinstance(config, dict):
                    return config
                break
        raise ValueError("该项目不是自定义数据集项目。")

    def update_custom_algorithm(self, project: Project, algorithm: str) -> dict:
        if algorithm not in ALGORITHM_REGISTRY:
            raise ValueError(f"不支持的训练算法：{algorithm}")
        records = self._load_records()
        for record in records:
            if record["project_id"] != project.project_id:
                continue
            config = record.get("custom_config")
            if not isinstance(config, dict):
                raise ValueError("该项目不是自定义数据集项目。")
            record["custom_config"] = {**config, "algorithm": algorithm}
            record["custom_admission"] = {
                "configuration_allowed": True,
                "training_allowed": False,
                "blockers": ["configuration_changed", "chief_engineer_approval_required"],
            }
            self._save_records(records)
            return record
        raise ValueError("Project was not found.")

    def custom_admission_for(self, project: Project) -> dict:
        for record in self._load_records():
            if record["project_id"] == project.project_id:
                admission = record.get("custom_admission")
                if isinstance(admission, dict):
                    if admission.get("training_allowed") is True:
                        config = record.get("custom_config")
                        try:
                            if not isinstance(config, dict):
                                raise ValueError("custom config is missing")
                            return verify_training_capability(
                                admission, config, Path(project.data_path)
                            )
                        except (KeyError, OSError, TypeError, ValueError):
                            return {
                                "configuration_allowed": True,
                                "training_allowed": False,
                                "blockers": ["admission_invalid_or_stale"],
                            }
                    return admission
                break
        raise ValueError("该自定义项目没有可用的数据准入报告。")

    def record_custom_training_capability(
        self,
        project: Project,
        *,
        manifest: dict[str, object],
        approved_by: str,
        approved_at: str,
    ) -> dict:
        config = self.custom_config_for(project)
        capability = create_training_capability(
            config,
            Path(project.data_path),
            manifest=manifest,
            approved_by=approved_by,
            approved_at=approved_at,
        )
        self._replace_record(project.project_id, custom_admission=capability)
        return capability

    def require_custom_training_admission(self, project: Project) -> dict:
        try:
            admission = self.custom_admission_for(project)
            config = self.custom_config_for(project)
            return verify_training_capability(admission, config, Path(project.data_path))
        except (KeyError, OSError, TypeError, ValueError):
            raise ValueError("自定义训练仍被数据准入门禁阻塞。")

    def safe_child(self, project: Project, relative_path: str) -> Path:
        root = project.path.resolve()
        target = (root / relative_path).resolve()
        if target != root and root not in target.parents:
            raise ValueError("Path escapes the project directory.")
        return target

    def archive_item(self, project_id: str, relative_path: str, confirmation: str) -> Path:
        project = self.get_project(project_id)
        source = self.safe_child(project, relative_path)
        if not source.exists():
            raise ValueError("The item to archive does not exist.")
        if confirmation != source.name:
            raise ValueError("Type the exact item name to archive it.")
        destination = project.path / "archive" / f"{datetime.now():%Y%m%d-%H%M%S}-{source.name}"
        shutil.move(str(source), str(destination))
        return destination

    def delete_run(self, project_id: str, run_name: str, confirmation: str) -> None:
        """Permanently delete one confirmed direct child of the runs directory."""
        project = self.get_project(project_id)
        if not run_name or Path(run_name).name != run_name or run_name in (".", ".."):
            raise ValueError("The training result name is invalid.")
        runs_dir = (project.path / "runs").resolve()
        source = self.safe_child(project, f"runs/{run_name}")
        if source.parent != runs_dir:
            raise ValueError("Only a direct training result can be deleted.")
        if not source.exists() or not source.is_dir() or source.is_symlink():
            raise ValueError("The training result to delete does not exist.")
        if confirmation != source.name:
            raise ValueError("Type the exact training result name to delete it permanently.")
        shutil.rmtree(source)


def create_run_dir(project: Project) -> Path:
    run_dir = project.path / "runs" / f"{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def resolve_training_python(project_root: Path, global_python: Path | None = None) -> Path:
    """Resolve the Windows runtime first, then the configured macOS global Python."""
    root = Path(project_root).resolve()
    candidates = [
        root / "runtime" / "python" / "python.exe",
        root.parents[1] / "work" / "soc_venv" / "Scripts" / "python.exe",
    ]
    if sys.platform == "darwin":
        candidates.extend([Path(global_python) if global_python is not None else Path("/opt/homebrew/bin/python3.12"), root / ".venv-macos" / "bin" / "python"])
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(f"Project PyTorch interpreter was not found: {candidates[0]}")


def build_soc_command(project: Project, settings: Dict[str, object], python_executable: Path) -> Tuple[List[str], Path]:
    """Create a fixed, safe command for the existing A123 LSTM trainer."""
    run_dir = create_run_dir(project)
    defaults = {
        "window": 60, "epochs": 40, "batch_size": 512, "max_train": 40000,
        "max_valid": 20000, "max_test": 20000, "hidden": 32,
        "learning_rate": 0.0003, "patience": 9, "seed": 42,
        "dropout": 0.1, "weight_decay": 1e-4, "lr_patience": 3,
        "lr_factor": 0.5, "min_learning_rate": 3e-5,
        "min_delta": 1e-5, "gradient_clip": 1.0,
        "add_delta_ah": True, "balance_soc": True,
    }
    values = {**defaults, **settings}
    trainer = ["-m", "src.training.train_lstm"] if project.name == "A123 SOC" else [str(project.trainer_script)]
    command = [
        str(python_executable), *trainer, "--data", str(project.data_path),
        "--results-dir", str(run_dir), "--window", str(values["window"]),
        "--epochs", str(values["epochs"]), "--batch-size", str(values["batch_size"]),
        "--max-train", str(values["max_train"]), "--max-valid", str(values["max_valid"]),
        "--max-test", str(values["max_test"]), "--hidden", str(values["hidden"]),
        "--learning-rate", str(values["learning_rate"]), "--patience", str(values["patience"]),
        "--dropout", str(values["dropout"]), "--weight-decay", str(values["weight_decay"]),
        "--lr-patience", str(values["lr_patience"]), "--lr-factor", str(values["lr_factor"]),
        "--min-learning-rate", str(values["min_learning_rate"]), "--min-delta", str(values["min_delta"]),
        "--gradient-clip", str(values["gradient_clip"]),
        "--seed", str(values["seed"]),
        "--add-delta-ah" if values["add_delta_ah"] else "--no-delta-ah",
        "--balance-soc" if values["balance_soc"] else "--no-balance-soc",
    ]
    return command, run_dir


def build_multistate_command(project: Project, settings: Dict[str, object], python_executable: Path) -> Tuple[List[str], Path]:
    """Create the fixed command for the NASA shared-LSTM five-state trainer."""

    if project.name != "NASA 五状态":
        raise ValueError("The multi-state trainer can only run the NASA 五状态 project.")
    run_dir = create_run_dir(project)
    defaults = {
        "window": 30, "epochs": 40, "batch_size": 128, "hidden": 32,
        "dropout": 0.1, "learning_rate": 0.0003, "seed": 42,
    }
    values = {**defaults, **settings}
    command = [
        str(python_executable), "-m", "src.training.train_multistate_lstm",
        "--data", str(project.data_path), "--results-dir", str(run_dir),
        "--window", str(values["window"]), "--epochs", str(values["epochs"]),
        "--batch-size", str(values["batch_size"]), "--hidden", str(values["hidden"]),
        "--dropout", str(values["dropout"]), "--learning-rate", str(values["learning_rate"]),
        "--seed", str(values["seed"]),
    ]
    return command, run_dir


def build_lifecycle_command(project: Project, settings: Dict[str, object], python_executable: Path) -> Tuple[List[str], Path]:
    """Create the safe four-fold NASA lifecycle experiment command."""
    if project.name != "NASA 生命周期模型":
        raise ValueError("The lifecycle command requires the NASA 生命周期模型 project.")
    stage = str(settings.get("stage", "formal"))
    seed = int(settings.get("seed", 42))
    if stage not in {"smoke", "formal"}:
        raise ValueError("Lifecycle stage must be smoke or formal.")
    if seed < 0:
        raise ValueError("Lifecycle seed must be a non-negative integer.")
    run_dir = create_run_dir(project)
    command = [
        str(python_executable), "-m", "src.evaluation.nasa_lifecycle_experiments",
        "--stage", stage, "--seed", str(seed),
    ]
    return command, run_dir


def build_hybrid_command(project: Project, settings: Dict[str, object], python_executable: Path) -> Tuple[List[str], Path]:
    """Create one explicit run for the improved four-fold NASA workflow."""
    if project.name != "NASA 五状态（改进）":
        raise ValueError("The hybrid command requires the improved NASA five-state project.")
    stage = str(settings.get("stage", "formal")); seed = int(settings.get("seed", 42))
    if stage not in {"smoke", "formal"} or seed < 0:
        raise ValueError("Hybrid stage must be smoke/formal and seed must be non-negative.")
    run_dir = create_run_dir(project)
    lifecycle_data = Path(project.data_path).resolve()
    state_data = lifecycle_data.with_name("nasa_state_future_samples.csv")
    command = [
        str(python_executable), "-m", "src.training.train_nasa_hybrid",
        "--state-data", str(state_data), "--lifecycle-data", str(lifecycle_data),
        "--results-dir", str(run_dir), "--stage", stage, "--seed", str(seed),
    ]
    return command, run_dir


def build_custom_command(project: Project, settings: Dict[str, object], python_executable: Path) -> Tuple[List[str], Path]:
    """Build the argument-list command for one imported dataset experiment."""
    config_path = project.path.parent.parent / "projects.json"
    store = PlatformStore(config_path.parent)
    store.require_custom_training_admission(project)
    config = store.custom_config_for(project)
    run_dir = create_run_dir(project)
    defaults = {"window": 60, "epochs": 40, "batch_size": 128, "hidden": 32, "learning_rate": 0.0003, "seed": 42}
    values = {**defaults, **settings}
    command = [
        str(python_executable), "-m", "src.training.train_custom", "--data", str(project.data_path),
        "--results-dir", str(run_dir),
        "--admission-registry", str(config_path), "--project-id", project.project_id,
        "--algorithm", str(config["algorithm"]),
        "--features", *[str(item) for item in config["feature_columns"]],
        "--targets", *[str(item) for item in config["target_columns"]],
        "--window", str(int(values["window"])), "--epochs", str(int(values["epochs"])),
        "--batch-size", str(int(values["batch_size"])), "--hidden", str(int(values["hidden"])),
        "--learning-rate", str(float(values["learning_rate"])), "--seed", str(int(values["seed"])),
    ]
    return command, run_dir


def read_nasa_lifecycle_result(formal_dir: Path) -> Dict[str, object]:
    """Read one complete lifecycle experiment without accepting partial evidence."""
    root = Path(formal_dir)
    required = {
        "aggregate_metrics.json", "comparison_report.md", "implementation_manifest.json",
        "baseline_hashes_before.json", "baseline_hashes_after.json",
    }
    missing = sorted(name for name in required if not (root / name).is_file())
    missing.extend(f"test_{cell}" for cell in ("RW9", "RW10", "RW11", "RW12") if not (root / f"test_{cell}").is_dir())
    if missing:
        raise ValueError(f"Lifecycle formal result is incomplete: {', '.join(missing)}")
    try:
        metrics = json.loads((root / "aggregate_metrics.json").read_text(encoding="utf-8"))
        manifest = json.loads((root / "implementation_manifest.json").read_text(encoding="utf-8"))
        hashes_before = json.loads((root / "baseline_hashes_before.json").read_text(encoding="utf-8"))
        hashes_after = json.loads((root / "baseline_hashes_after.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Lifecycle formal result cannot be read: {error}") from error
    expected_targets = {"soc", "soe", "soh", "rul_cycles", "sot_5min_c"}
    if not isinstance(metrics, dict) or not expected_targets.issubset(metrics):
        raise ValueError("Lifecycle aggregate metrics are missing required targets.")
    for target in expected_targets:
        entry = metrics[target]
        if not isinstance(entry, dict):
            raise ValueError(f"Lifecycle metric for {target} is invalid.")
        float(entry["mean_MAE"]); float(entry["mean_RMSE"]); int(entry["fold_count"])
    return {
        "path": root,
        "metrics": metrics,
        "manifest": manifest,
        "report_path": root / "comparison_report.md",
        "baseline_hash_verified": hashes_before == hashes_after,
        "folds": tuple(f"test_{cell}" for cell in ("RW9", "RW10", "RW11", "RW12")),
    }


def read_hybrid_result(run_dir: Path) -> Dict[str, object]:
    """Read only a complete four-fold hybrid run."""
    root = Path(run_dir)
    required = {"aggregate_metrics.json", "comparison_report.md", "run_config.json", "baseline_hashes_before.json", "baseline_hashes_after.json"}
    missing = sorted(name for name in required if not (root / name).is_file())
    missing.extend(f"test_{cell}" for cell in ("RW9", "RW10", "RW11", "RW12") if not (root / f"test_{cell}").is_dir())
    if missing:
        raise ValueError(f"Hybrid result is incomplete: {', '.join(missing)}")
    metrics = json.loads((root / "aggregate_metrics.json").read_text(encoding="utf-8"))
    config = json.loads((root / "run_config.json").read_text(encoding="utf-8"))
    before = json.loads((root / "baseline_hashes_before.json").read_text(encoding="utf-8"))
    after = json.loads((root / "baseline_hashes_after.json").read_text(encoding="utf-8"))
    expected = {"soc", "soe", "soh", "rul_cycles", "sot_5min_c"}
    if not isinstance(metrics, dict) or not expected.issubset(metrics):
        raise ValueError("Hybrid aggregate metrics are missing required targets.")
    return {"path": root, "metrics": metrics, "config": config, "report_path": root / "comparison_report.md", "baseline_hash_verified": before == after, "folds": tuple(f"test_{cell}" for cell in ("RW9", "RW10", "RW11", "RW12"))}


def read_run_result(run_dir: Path) -> RunResult:
    run_dir = Path(run_dir)
    metrics_path = run_dir / "metrics.json"
    log_path = run_dir / "run.log"
    chart_path = next((path for path in (run_dir / "soc_prediction.png", run_dir / "soc_prediction.svg") if path.exists()), None)
    if metrics_path.exists():
        return RunResult(run_dir, "complete", json.loads(metrics_path.read_text(encoding="utf-8")), chart_path, log_path if log_path.exists() else None)
    if log_path.exists() and "returncode=" in log_path.read_text(encoding="utf-8", errors="replace"):
        return RunResult(run_dir, "failed", None, chart_path, log_path)
    return RunResult(run_dir, "incomplete", None, chart_path, log_path if log_path.exists() else None)


def latest_complete_run_result(runs_dir: Path) -> Optional[RunResult]:
    """Return the newest run with readable overview metrics and prediction rows."""
    required_metrics = {"MAE_pct", "RMSE_pct", "n_test"}
    multistate_targets = {"soc", "soh", "soe", "rul_cycles", "sot_c"}
    runs_dir = Path(runs_dir)
    if not runs_dir.is_dir():
        return None
    for run_dir in sorted((path for path in runs_dir.iterdir() if path.is_dir()), reverse=True):
        metrics_path = run_dir / "metrics.json"
        predictions_path = run_dir / "test_predictions.csv"
        try:
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            if not isinstance(metrics, dict):
                continue
            if required_metrics.issubset(metrics):
                float(metrics["MAE_pct"])
                float(metrics["RMSE_pct"])
                int(metrics["n_test"])
            else:
                target_path = run_dir / "metrics_by_target.json"
                target_metrics = json.loads(target_path.read_text(encoding="utf-8"))
                if not isinstance(target_metrics, dict) or not multistate_targets.issubset(target_metrics):
                    continue
                for target in multistate_targets:
                    float(target_metrics[target]["MAE"])
                    float(target_metrics[target]["RMSE"])
                    int(target_metrics[target]["n_test"])
            with predictions_path.open(encoding="utf-8", newline="") as file:
                reader = csv.DictReader(file)
                if not reader.fieldnames or next(reader, None) is None:
                    continue
        except (OSError, UnicodeError, json.JSONDecodeError, csv.Error, TypeError, ValueError):
            continue
        return read_run_result(run_dir)
    return None


def read_generalization_summary(path: Path) -> dict:
    summary = json.loads(Path(path).read_text(encoding="utf-8"))
    required = {
        "seed_mean_MAE_pct",
        "loso_worst_MAE_pct",
        "A1235_MAE_pct",
        "decision",
    }
    missing = sorted(required - set(summary))
    if missing:
        raise ValueError(f"Generalization summary is missing required fields: {', '.join(missing)}")
    return summary


def summarize_csv(path: Path, preview_limit: int = 20) -> Dict[str, object]:
    """Read only lightweight dataset metadata and a small preview."""
    with Path(path).open(encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        headers = reader.fieldnames or []
        rows = 0
        sessions = set()
        preview = []
        for row in reader:
            rows += 1
            if "session" in row and row["session"]:
                sessions.add(row["session"])
            if len(preview) < preview_limit:
                preview.append(row)
    return {"headers": headers, "row_count": rows, "session_count": len(sessions), "preview": preview}
