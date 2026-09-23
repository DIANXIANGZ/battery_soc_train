"""Shared row contract and fail-closed checks for non-RUL datasets."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping, Sequence


SUPPORTED_TARGETS = frozenset({"soc", "soe", "soh", "sot", "energy_proxy", "system_soe"})
FORBIDDEN_FIELD_TOKENS = (
    "rul",
    "remaining_life",
    "remaininglife",
    "eol",
    "cycle_life",
    "cyclelife",
)


@dataclass(frozen=True)
class CanonicalRow:
    """One time-ordered training observation with explicit grouping identity."""

    target: str
    source_id: str
    cell_id: str
    session_id: str
    condition_id: str
    cycle_index: int
    time_s: float
    features: Mapping[str, float]
    label: float | None


@dataclass(frozen=True)
class DatasetContract:
    """The immutable target, source, and feature declaration for one dataset."""

    target: str
    source_id: str
    feature_names: tuple[str, ...]


def _is_blank(value: object) -> bool:
    return not isinstance(value, str) or not value.strip()


def _is_finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _is_forbidden_field(name: str) -> bool:
    normalized = name.strip().lower().replace("-", "_").replace(" ", "_")
    return any(token in normalized for token in FORBIDDEN_FIELD_TOKENS)


def validate_contract(contract: DatasetContract, rows: Sequence[CanonicalRow]) -> list[str]:
    """Return stable validation errors without mutating or repairing input rows."""

    errors: list[str] = []
    if contract.target not in SUPPORTED_TARGETS:
        errors.append(f"不支持的目标：{contract.target}")
    if _is_blank(contract.source_id):
        errors.append("合同缺少source_id")
    if not contract.feature_names:
        errors.append("合同未声明特征")
    if len(contract.feature_names) != len(set(contract.feature_names)):
        errors.append("合同特征名重复")
    for name in contract.feature_names:
        if _is_forbidden_field(name):
            errors.append(f"禁止字段：{name}")

    previous_time: dict[tuple[str, str], float] = {}
    for index, row in enumerate(rows, start=1):
        if row.target != contract.target:
            errors.append(f"第{index}行目标与合同不一致")
        if row.source_id != contract.source_id:
            errors.append(f"第{index}行来源与合同不一致")
        for field_name in ("cell_id", "session_id", "condition_id"):
            if _is_blank(getattr(row, field_name)):
                errors.append(f"第{index}行缺少{field_name}")
        if row.label is None:
            errors.append(f"第{index}行缺少目标标签")
        elif not _is_finite_number(row.label):
            errors.append(f"第{index}行目标标签不是有限数值")
        if not isinstance(row.cycle_index, int) or isinstance(row.cycle_index, bool) or row.cycle_index < 0:
            errors.append(f"第{index}行cycle_index无效")
        if not _is_finite_number(row.time_s):
            errors.append(f"第{index}行time_s不是有限数值")

        for name in row.features:
            if _is_forbidden_field(name):
                message = f"禁止字段：{name}"
                if message not in errors:
                    errors.append(message)
        for name in contract.feature_names:
            if name not in row.features:
                errors.append(f"第{index}行缺少特征：{name}")
                continue
            if not _is_finite_number(row.features[name]):
                errors.append(f"第{index}行特征{name}不是有限数值")

        if not _is_blank(row.cell_id) and not _is_blank(row.session_id) and _is_finite_number(row.time_s):
            group = (row.cell_id, row.session_id)
            time_value = float(row.time_s)
            if group in previous_time and (
                time_value < previous_time[group]
                if contract.target == "system_soe"
                else time_value <= previous_time[group]
            ):
                errors.append(f"{row.cell_id}/{row.session_id}的时间顺序不递增")
            previous_time[group] = time_value
    if not rows:
        errors.append("数据行为空")
    return errors
