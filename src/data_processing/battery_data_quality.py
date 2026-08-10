"""Quality and leakage admission checks for canonical battery tables."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Mapping

import pandas as pd


@dataclass(frozen=True)
class BatteryTableSchema:
    group_columns: tuple[str, ...]
    time_column: str
    target_columns: tuple[str, ...]
    target_provenance: Mapping[str, str]
    feature_provenance: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class QualityFinding:
    severity: str
    code: str
    message: str
    count: int = 1


@dataclass(frozen=True)
class QualityReport:
    row_count: int
    column_count: int
    group_count: int
    duplicate_row_count: int
    null_counts: Mapping[str, int]
    target_provenance: Mapping[str, str]
    findings: tuple[QualityFinding, ...]

    @property
    def critical_count(self) -> int:
        return sum(finding.count for finding in self.findings if finding.severity == "critical")

    def to_dict(self) -> dict[str, object]:
        return {
            "row_count": self.row_count,
            "column_count": self.column_count,
            "group_count": self.group_count,
            "duplicate_row_count": self.duplicate_row_count,
            "null_counts": dict(self.null_counts),
            "target_provenance": dict(self.target_provenance),
            "critical_count": self.critical_count,
            "admitted": admit(self),
            "findings": [asdict(finding) for finding in self.findings],
        }


def _finding(findings: list[QualityFinding], code: str, message: str, count: int, severity: str = "critical") -> None:
    if count:
        findings.append(QualityFinding(severity, code, message, int(count)))


def profile_battery_table(frame: pd.DataFrame, schema: BatteryTableSchema) -> QualityReport:
    findings: list[QualityFinding] = []
    required = (*schema.group_columns, schema.time_column, *schema.target_columns)
    missing_columns = [column for column in required if column not in frame.columns]
    _finding(findings, "missing_required_column", f"Missing columns: {missing_columns}", len(missing_columns))

    null_counts = {str(column): int(value) for column, value in frame.isna().sum().items()}
    existing_groups = [column for column in schema.group_columns if column in frame.columns]
    missing_group_ids = sum(null_counts.get(column, 0) for column in existing_groups)
    _finding(findings, "missing_group_id", "Cell/session identifiers contain null values", missing_group_ids)

    duplicate_rows = int(frame.duplicated().sum())
    _finding(findings, "duplicate_rows", "Exact duplicate rows detected", duplicate_rows, severity="high")

    group_count = 0
    if len(existing_groups) == len(schema.group_columns) and not frame.empty:
        group_count = int(frame.groupby(existing_groups, dropna=False).ngroups)
    if all(column in frame.columns for column in (*schema.group_columns, schema.time_column)):
        keys = [*schema.group_columns, schema.time_column]
        duplicate_group_time = int(frame.duplicated(keys, keep=False).sum())
        _finding(
            findings,
            "duplicate_group_time",
            "A group contains repeated timestamps",
            duplicate_group_time,
        )
        reversals = 0
        for _, group in frame.groupby(list(schema.group_columns), sort=False, dropna=False):
            times = pd.to_numeric(group[schema.time_column], errors="coerce")
            reversals += int((times.diff() < 0).sum())
        _finding(findings, "time_reversal", "Time decreases within a group", reversals)
        invalid_time = int(pd.to_numeric(frame[schema.time_column], errors="coerce").isna().sum())
        _finding(findings, "invalid_time", "Time contains null or non-numeric values", invalid_time)

    range_checks = {
        "soc": (0.0, 1.0, "soc_out_of_range"),
        "soe": (0.0, 1.0, "soe_out_of_range"),
        "soh": (0.0, 1.1, "soh_out_of_range"),
        "temperature_c": (-80.0, 150.0, "temperature_out_of_range"),
        "sot_c": (-80.0, 150.0, "temperature_out_of_range"),
        "voltage_v": (0.0, 6.0, "voltage_out_of_range"),
    }
    for column, (minimum, maximum, code) in range_checks.items():
        if column not in frame.columns:
            continue
        values = pd.to_numeric(frame[column], errors="coerce")
        violations = int(((values < minimum) | (values > maximum)).sum())
        _finding(findings, code, f"{column} is outside [{minimum}, {maximum}]", violations)

    for target in schema.target_columns:
        provenance = schema.target_provenance.get(target, "").strip()
        _finding(
            findings,
            "missing_target_provenance",
            f"Target {target} has no auditable provenance",
            int(not provenance),
        )

    future_tokens = ("future", "lead", "next", "lookahead", "t+")
    for feature, provenance in schema.feature_provenance.items():
        description = f"{feature} {provenance}".lower()
        if any(token in description for token in future_tokens):
            _finding(
                findings,
                "future_derived_feature",
                f"Feature {feature} depends on future information: {provenance}",
                1,
            )

    return QualityReport(
        row_count=int(len(frame)),
        column_count=int(len(frame.columns)),
        group_count=group_count,
        duplicate_row_count=duplicate_rows,
        null_counts=null_counts,
        target_provenance=dict(schema.target_provenance),
        findings=tuple(findings),
    )


def admit(report: QualityReport) -> bool:
    return report.critical_count == 0 and report.row_count > 0 and report.group_count > 0


def write_quality_report(report: QualityReport, output_dir: Path, stem: str) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{stem}.quality.json"
    markdown_path = output_dir / f"{stem}.quality.md"
    json_path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    status = "ADMITTED" if admit(report) else "REJECTED"
    lines = [
        f"# Battery data quality: {stem}",
        "",
        f"Status: **{status}**",
        "",
        f"Rows: {report.row_count}; columns: {report.column_count}; groups: {report.group_count}.",
        "",
        "## Findings",
        "",
    ]
    if report.findings:
        lines.extend(
            f"- [{finding.severity.upper()}] `{finding.code}` ({finding.count}): {finding.message}"
            for finding in report.findings
        )
    else:
        lines.append("- No findings.")
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": json_path, "markdown": markdown_path}
