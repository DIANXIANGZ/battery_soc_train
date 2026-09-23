"""Read-only metadata and guarded commands for the four formal baselines."""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping
from uuid import uuid4


SUMMARY_RELATIVE_PATH = Path("docs/audits/2026-09-23-non-rul-four-target-completion.json")
TARGETS = ("soc", "system_soe", "soh", "sot")
DISPLAY_NAMES = {"soc": "SOC", "system_soe": "SOE（系统级）", "soh": "SOH", "sot": "SOT"}
FORBIDDEN_PATH_COMPONENTS = {
    "rul", "rul_assets", "rul_results", "eol", "trajectory", "v9", "v10", "v11", "invalidated",
}


@dataclass(frozen=True)
class FormalBaseline:
    target: str
    status: str
    scope: str
    model: str
    metrics: dict[str, object]
    dataset_path: Path | None
    result_path: Path | None
    report_path: Path | None
    runner_path: Path | None
    runner_sha256: str | None
    config_path: Path | None
    config_sha256: str | None
    reason: str = ""

    @property
    def display_name(self) -> str:
        return DISPLAY_NAMES.get(self.target, self.target)


@dataclass(frozen=True)
class FormalBaselineSummary:
    status: str
    summary_path: Path
    targets: dict[str, FormalBaseline]
    reason: str = ""


@dataclass(frozen=True)
class FormalCommandSpec:
    available: bool
    target: str
    command: tuple[str, ...] = ()
    output_path: Path | None = None
    reason: str = ""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_path(project_root: Path, value: object) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        return (project_root / path).resolve()
    parts = path.parts
    for index in range(len(parts) - 1):
        if parts[index:index + 2] == ("battery_soc_project", "battery_soc_project"):
            relocated = project_root.joinpath(*parts[index + 2:])
            # Archive entries may point at the old checkout. Always prefer the
            # current worktree, even when the old checkout still exists.
            return relocated.resolve()
    if path.exists():
        return path.resolve()
    return path.resolve()


def _forbidden_path(path: Path | None) -> bool:
    if path is None:
        return False
    components = {part.casefold().replace("-", "_") for part in path.parts}
    return bool(components & FORBIDDEN_PATH_COMPONENTS)


def _target_from_payload(project_root: Path, target: str, payload: object) -> FormalBaseline:
    if not isinstance(payload, Mapping):
        return FormalBaseline(target, "UNAVAILABLE", "", "", {}, None, None, None, None, None, None, None, "目标归档条目不是对象")
    code_config = payload.get("code_config")
    code_config = code_config if isinstance(code_config, Mapping) else {}
    dataset_path = _resolve_path(project_root, payload.get("dataset_path"))
    result_path = _resolve_path(project_root, payload.get("result_path"))
    report_path = _resolve_path(project_root, payload.get("report_path"))
    runner_path = _resolve_path(project_root, code_config.get("runner_path"))
    config_path = _resolve_path(project_root, code_config.get("config_path"))
    paths = (dataset_path, result_path, runner_path, config_path)
    reason = ""
    if any(_forbidden_path(path) for path in paths):
        reason = "目标路径命中RUL或冻结资产禁用路径"
    elif dataset_path is None or result_path is None:
        reason = "数据版本或结果路径缺失"
    elif runner_path is None or config_path is None:
        reason = "稳定训练入口或配置路径缺失"
    return FormalBaseline(
        target=target,
        status=str(payload.get("status", "UNAVAILABLE")),
        scope=str(payload.get("scope", "")),
        model=str(payload.get("model", "")),
        metrics=dict(payload.get("metrics", {})) if isinstance(payload.get("metrics"), Mapping) else {},
        dataset_path=dataset_path,
        result_path=result_path,
        report_path=report_path,
        runner_path=runner_path,
        runner_sha256=code_config.get("runner_sha256") if isinstance(code_config.get("runner_sha256"), str) else None,
        config_path=config_path,
        config_sha256=code_config.get("config_sha256") if isinstance(code_config.get("config_sha256"), str) else None,
        reason=reason,
    )


def load_formal_baselines(project_root: Path) -> FormalBaselineSummary:
    """Load only the small formal-result archive; never reads samples or model files."""
    root = Path(project_root).resolve()
    summary_path = root / SUMMARY_RELATIVE_PATH
    if not summary_path.is_file():
        return FormalBaselineSummary("UNAVAILABLE", summary_path, {}, "四目标正式基线摘要不存在")
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return FormalBaselineSummary("UNAVAILABLE", summary_path, {}, "四目标正式基线摘要无法读取")
    if not isinstance(payload, Mapping) or payload.get("status") != "COMPLETE_FOUR_TARGET_SCOPED_BASELINES":
        return FormalBaselineSummary("UNAVAILABLE", summary_path, {}, "四目标正式基线摘要状态无效")
    raw_targets = payload.get("targets")
    if not isinstance(raw_targets, Mapping):
        return FormalBaselineSummary("UNAVAILABLE", summary_path, {}, "四目标正式基线条目缺失")
    targets = {target: _target_from_payload(root, target, raw_targets.get(target)) for target in TARGETS}
    return FormalBaselineSummary(str(payload.get("status")), summary_path, targets)


def build_formal_baseline_command(
    baseline: FormalBaseline,
    project_root: Path,
    *,
    python_executable: Path | None = None,
) -> FormalCommandSpec:
    """Validate a stable runner before a user explicitly starts it."""
    if baseline.reason:
        return FormalCommandSpec(False, baseline.target, reason=baseline.reason)
    if baseline.status != "PYTORCH_FORMAL_PASS_SCOPED":
        return FormalCommandSpec(False, baseline.target, reason="正式基线状态不可启动")
    if baseline.dataset_path is None or not baseline.dataset_path.is_dir() or not (baseline.dataset_path / "manifest.json").is_file():
        return FormalCommandSpec(False, baseline.target, reason="数据版本或manifest不存在")
    if baseline.runner_path is None or not baseline.runner_path.is_file():
        return FormalCommandSpec(False, baseline.target, reason="稳定训练入口不存在")
    if baseline.config_path is None or not baseline.config_path.is_file():
        return FormalCommandSpec(False, baseline.target, reason="训练配置不存在")
    if baseline.runner_sha256 != _sha256(baseline.runner_path):
        return FormalCommandSpec(False, baseline.target, reason="训练入口SHA不匹配")
    if baseline.config_sha256 != _sha256(baseline.config_path):
        return FormalCommandSpec(False, baseline.target, reason="训练配置SHA不匹配")
    if baseline.result_path is None:
        return FormalCommandSpec(False, baseline.target, reason="结果路径缺失")
    if not baseline.result_path.parent.is_dir():
        return FormalCommandSpec(False, baseline.target, output_path=baseline.result_path, reason="结果父目录不存在")
    executable = Path(python_executable or sys.executable).resolve()
    if not executable.is_file():
        return FormalCommandSpec(False, baseline.target, reason="Python解释器不存在")
    if baseline.target == "sot":
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output = baseline.result_path.parent / f"{baseline.result_path.name}-desktop-{stamp}-{uuid4().hex[:8]}"
        if output.exists():
            return FormalCommandSpec(False, baseline.target, output_path=output, reason="受控输出目录已存在，拒绝覆盖")
        command = (
            str(executable), str(baseline.runner_path), "--config", str(baseline.config_path),
            "--output", str(output), "--stage", "formal", "--formal-authorized",
        )
        return FormalCommandSpec(True, baseline.target, command, output)
    elif baseline.target == "system_soe":
        if baseline.result_path.exists():
            return FormalCommandSpec(False, baseline.target, output_path=baseline.result_path, reason="系统SOE入口固定输出到既有正式结果，禁止覆盖")
        command = (
            str(executable), str(baseline.runner_path), "--stage", "formal",
            "--output-dir", str(baseline.result_path), "--formal-authorized",
        )
    else:
        return FormalCommandSpec(False, baseline.target, output_path=baseline.result_path, reason="当前工作树没有稳定可验证的训练入口")
    return FormalCommandSpec(True, baseline.target, command, baseline.result_path)
