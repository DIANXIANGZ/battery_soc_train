"""Compact, interpretable quality profiles for canonical SOC samples."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from src.research.protocol import DatasetRegistration
from src.research.schema import SampleRecord, validate_record


@dataclass(frozen=True)
class QualityReport:
    row_count: int
    invalid_row_count: int
    duplicate_key_count: int
    time_reversal_count: int
    missing_temperature_rate: float
    missing_capacity_rate: float
    missing_soh_rate: float
    missing_soc_rate: float
    dataset_ids: tuple[str, ...]
    distinct_cell_count: int
    distinct_session_count: int
    distinct_cycle_count: int
    voltage_min: float
    voltage_max: float
    current_min: float
    current_max: float
    issues: tuple[str, ...]

    @property
    def has_soc_reference(self) -> bool:
        return self.missing_soc_rate < 1.0


def _rate(count: int, total: int) -> float:
    return count / total


def profile_records(records: Iterable[SampleRecord]) -> QualityReport:
    rows = list(records)
    if not rows:
        raise ValueError("quality profile requires at least one record")

    seen = set()
    duplicate_count = 0
    previous_time: dict[tuple[str, str, str, str], float] = {}
    reversal_count = 0
    invalid_count = 0
    issue_names = set()
    for row in rows:
        if row.key in seen:
            duplicate_count += 1
        seen.add(row.key)
        boundary = (
            row.key.dataset_id,
            row.key.cell_id,
            row.key.session_id,
            row.key.cycle_id,
        )
        if boundary in previous_time and row.key.timestamp_s < previous_time[boundary]:
            reversal_count += 1
        previous_time[boundary] = row.key.timestamp_s
        errors = validate_record(row)
        if errors:
            invalid_count += 1
            issue_names.update(errors)

    total = len(rows)
    cells = {(r.key.dataset_id, r.key.cell_id) for r in rows}
    sessions = {(r.key.dataset_id, r.key.cell_id, r.key.session_id) for r in rows}
    cycles = {
        (r.key.dataset_id, r.key.cell_id, r.key.session_id, r.key.cycle_id)
        for r in rows
    }
    return QualityReport(
        row_count=total,
        invalid_row_count=invalid_count,
        duplicate_key_count=duplicate_count,
        time_reversal_count=reversal_count,
        missing_temperature_rate=_rate(sum(r.temperature_c is None for r in rows), total),
        missing_capacity_rate=_rate(sum(r.capacity_ah is None for r in rows), total),
        missing_soh_rate=_rate(sum(r.soh is None for r in rows), total),
        missing_soc_rate=_rate(sum(r.soc_reference is None for r in rows), total),
        dataset_ids=tuple(sorted({r.key.dataset_id for r in rows})),
        distinct_cell_count=len(cells),
        distinct_session_count=len(sessions),
        distinct_cycle_count=len(cycles),
        voltage_min=min(r.voltage_v for r in rows),
        voltage_max=max(r.voltage_v for r in rows),
        current_min=min(r.current_a for r in rows),
        current_max=max(r.current_a for r in rows),
        issues=tuple(sorted(issue_names)),
    )


def assess_compatibility(
    registration: DatasetRegistration,
    report: QualityReport,
    target_chemistry: str,
) -> str:
    if registration.chemistry != target_chemistry:
        return "compatibility_only_chemistry_mismatch"
    if not report.has_soc_reference:
        return "compatibility_only_missing_soc_label"
    if report.distinct_cell_count < 1:
        return "rejected_missing_cell_identity"
    if report.invalid_row_count:
        return "eligible_after_quality_remediation"
    return "eligible_pending_split_review"

