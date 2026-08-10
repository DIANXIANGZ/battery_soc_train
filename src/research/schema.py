"""Canonical, traceable sample schema for cross-dataset SOC research."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping


@dataclass(frozen=True, order=True)
class SampleKey:
    dataset_id: str
    cell_id: str
    session_id: str
    cycle_id: str
    timestamp_s: float


@dataclass(frozen=True)
class SampleRecord:
    key: SampleKey
    voltage_v: float
    current_a: float
    temperature_c: float | None
    capacity_ah: float | None
    soh: float | None
    soc_reference: float | None
    label_method: str
    split_role: str
    source_file: str


def _text(mapping: Mapping[str, object], field: str) -> str:
    if field not in mapping:
        raise ValueError(f"Missing required field: {field}")
    value = mapping[field]
    return "" if value is None else str(value).strip()


def _number(mapping: Mapping[str, object], field: str) -> float:
    if field not in mapping:
        raise ValueError(f"Missing required field: {field}")
    try:
        value = float(mapping[field])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Field '{field}' must be numeric") from exc
    if not math.isfinite(value):
        raise ValueError(f"Field '{field}' must be finite")
    return value


def _optional_number(mapping: Mapping[str, object], field: str) -> float | None:
    value = mapping.get(field)
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Field '{field}' must be numeric or empty") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"Field '{field}' must be finite or empty")
    return parsed


def parse_record(mapping: Mapping[str, object]) -> SampleRecord:
    """Parse a mapping without silently inventing missing measurements."""

    key = SampleKey(
        dataset_id=_text(mapping, "dataset_id"),
        cell_id=_text(mapping, "cell_id"),
        session_id=_text(mapping, "session_id"),
        cycle_id=_text(mapping, "cycle_id"),
        timestamp_s=_number(mapping, "timestamp_s"),
    )
    return SampleRecord(
        key=key,
        voltage_v=_number(mapping, "voltage_v"),
        current_a=_number(mapping, "current_a"),
        temperature_c=_optional_number(mapping, "temperature_c"),
        capacity_ah=_optional_number(mapping, "capacity_ah"),
        soh=_optional_number(mapping, "soh"),
        soc_reference=_optional_number(mapping, "soc_reference"),
        label_method=_text(mapping, "label_method"),
        split_role=_text(mapping, "split_role"),
        source_file=_text(mapping, "source_file"),
    )


def validate_record(record: SampleRecord) -> tuple[str, ...]:
    """Return every high-signal contract violation in one inspection pass."""

    errors = []
    text_fields = (
        ("dataset_id", record.key.dataset_id),
        ("cell_id", record.key.cell_id),
        ("session_id", record.key.session_id),
        ("cycle_id", record.key.cycle_id),
        ("label_method", record.label_method),
        ("split_role", record.split_role),
        ("source_file", record.source_file),
    )
    for name, value in text_fields:
        if not value.strip():
            errors.append(f"{name} must be non-empty")
    if record.key.timestamp_s < 0.0:
        errors.append("timestamp_s must be non-negative")
    if not 0.0 < record.voltage_v <= 6.0:
        errors.append("voltage_v must be in (0, 6]")
    if record.temperature_c is not None and not -80.0 <= record.temperature_c <= 150.0:
        errors.append("temperature_c must be in [-80, 150]")
    if record.capacity_ah is not None and record.capacity_ah < 0.0:
        errors.append("capacity_ah must be non-negative")
    if record.soh is not None and not 0.0 < record.soh <= 2.0:
        errors.append("soh must be in (0, 2]")
    if record.soc_reference is not None and not 0.0 <= record.soc_reference <= 1.0:
        errors.append("soc_reference must be in [0, 1]")
    return tuple(errors)

