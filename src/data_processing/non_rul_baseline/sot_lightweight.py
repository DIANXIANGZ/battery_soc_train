"""Small, pointwise SOT adapter for the approved Zenodo 13759419 source.

This module deliberately keeps only current-row voltage/current features and
the source-native temperature label.  Source row ordinal is retained only as
lineage/order metadata; it is never a model feature and is not a physical
time measurement.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
from typing import Iterable, Mapping, Sequence
from zipfile import ZipFile

from src.data_processing.non_rul_baseline.build import _rename_no_replace


SOURCE_ID = "zenodo-13759419-v1"
TARGET = "sot"
LABEL_NAME = "sot_source_native_temperature"
LABEL_UNIT = "source-native-temperature"
FEATURE_NAMES = ("voltage", "current")
REQUIRED_FIELDS = ("电压(V)", "电流(A)", "temp1_1")
FORBIDDEN_TOKENS = ("rul", "eol", "lifecycle", "trajectory", "cycle_life", "cyclelife")

_MEMBER_PATTERNS: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (re.compile(r"Dataset_1_40Ah_battery/-0118-0\.3C-100%DOD-[1-5]\.csv"), "cell_40ah_1", "40Ah|0.3C|100%DOD"),
    (re.compile(r"Dataset_1_40Ah_battery/-0291-1C-100%DOD-[1-5]\.csv"), "cell_40ah_1", "40Ah|1C|100%DOD"),
    (re.compile(r"Dataset_1_40Ah_battery/-0284-2C-100%DOD-[1-5]\.csv"), "cell_40ah_1", "40Ah|2C|100%DOD"),
    (re.compile(r"Dataset_2_280Ah_battery_1/001CB310000009B960502763-0\.5C-100%DOD-[1-5]\.csv"), "cell_280ah_1", "280Ah|0.5C|100%DOD"),
    (re.compile(r"Dataset_3_280Ah_battery_2/04QCB76718400JB630001092-0\.5C-100%DOD-[1-5]\.csv"), "cell_280ah_2", "280Ah|0.5C|100%DOD"),
)


class SOTLightweightError(ValueError):
    """Stable fail-closed error codes for the lightweight SOT contract."""


@dataclass(frozen=True)
class MemberRoles:
    source_id: str
    physical_cell_id: str
    condition_id: str
    member_relative_path: str


@dataclass(frozen=True)
class LightweightRow:
    roles: MemberRoles
    source_row_index: int
    voltage: float
    current: float
    temperature: float

    @property
    def features(self) -> dict[str, float]:
        return {"voltage": self.voltage, "current": self.current}


@dataclass(frozen=True)
class ParsedMember:
    roles: MemberRoles
    rows: tuple[LightweightRow, ...]
    rejected_rows: int = 0
    reason_codes: tuple[str, ...] = ()


def _contains_forbidden(value: object) -> bool:
    return isinstance(value, str) and any(token in value.casefold() for token in FORBIDDEN_TOKENS)


def map_source_member(member_relative_path: str) -> MemberRoles:
    if not isinstance(member_relative_path, str) or _contains_forbidden(member_relative_path):
        raise SOTLightweightError("FORBIDDEN_LIFECYCLE_SEMANTICS")
    for pattern, cell_id, condition_id in _MEMBER_PATTERNS:
        if pattern.fullmatch(member_relative_path):
            return MemberRoles(SOURCE_ID, cell_id, condition_id, member_relative_path)
    raise SOTLightweightError("UNRECOGNIZED_MEMBER_PATH")


def _as_finite(value: object, code: str) -> float:
    if value is None or not str(value).strip():
        raise SOTLightweightError(code)
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        raise SOTLightweightError(code) from None
    if not math.isfinite(number):
        raise SOTLightweightError("NON_FINITE_ROW")
    return number


def parse_member_csv(member_relative_path: str, csv_text: str, *, strict: bool = True) -> ParsedMember:
    """Parse one CSV without using sequence order as a feature.

    ``strict=True`` is the test-facing contract.  The archive reader uses
    ``strict=False`` so malformed individual rows are rejected while valid
    rows from the same member remain traceable.
    """

    roles = map_source_member(member_relative_path)
    if not isinstance(csv_text, str):
        raise SOTLightweightError("SOURCE_TEXT_NOT_READABLE")
    reader = csv.DictReader(io.StringIO(csv_text))
    fieldnames = tuple(reader.fieldnames or ())
    if any(_contains_forbidden(name) for name in fieldnames):
        raise SOTLightweightError("FORBIDDEN_LIFECYCLE_SEMANTICS")
    missing = [field for field in REQUIRED_FIELDS if field not in fieldnames]
    if missing:
        raise SOTLightweightError("MISSING_TEMPERATURE_FIELD" if "temp1_1" in missing else "REQUIRED_FIELD_MISSING")
    accepted: list[LightweightRow] = []
    rejected = 0
    reasons: set[str] = set()
    for source_row_index, values in enumerate(reader, start=2):
        try:
            voltage = _as_finite(values.get("电压(V)"), "MISSING_VOLTAGE_VALUE")
            current = _as_finite(values.get("电流(A)"), "MISSING_CURRENT_VALUE")
            temperature = _as_finite(values.get("temp1_1"), "MISSING_TEMPERATURE_VALUE")
        except SOTLightweightError as exc:
            if strict:
                raise
            rejected += 1
            reasons.add(str(exc))
            continue
        accepted.append(LightweightRow(roles, source_row_index, voltage, current, temperature))
    if not accepted and rejected:
        raise SOTLightweightError(next(iter(reasons)))
    return ParsedMember(roles, tuple(accepted), rejected, tuple(sorted(reasons)))


def assign_train_test_groups(groups: Iterable[str]) -> dict[str, list[str]]:
    ordered = sorted({group for group in groups if isinstance(group, str) and group})
    if len(ordered) < 2:
        raise SOTLightweightError("SPLIT_NOT_FEASIBLE")
    return {"train_groups": ordered[:-1], "test_groups": [ordered[-1]]}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def _invalidated(root: Path, errors: Sequence[str]) -> Path:
    destination = root / "sot-baseline-v1"
    destination.mkdir(parents=True, exist_ok=False)
    path = destination / "INVALIDATED.json"
    _write_json(path, {"schema_version": 1, "target": TARGET, "errors": list(errors)})
    return destination


def _decode_source(raw: bytes) -> str:
    try:
        return raw.decode("gb18030")
    except UnicodeDecodeError:
        raise SOTLightweightError("SOURCE_ENCODING_NOT_READABLE") from None


def build_sot_version(
    archive_paths: Sequence[str | Path],
    output_root: str | Path,
    *,
    source_id: str = SOURCE_ID,
) -> tuple[Path, dict[str, object]]:
    """Stream the approved archives into a new immutable lightweight version."""

    if source_id != SOURCE_ID:
        raise SOTLightweightError("SOURCE_BINDING_MISMATCH")
    archives = [Path(path).resolve() for path in archive_paths]
    if not archives or any(not path.is_file() for path in archives):
        raise SOTLightweightError("SOURCE_FILE_NOT_READABLE")
    root = Path(output_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    destination = root / "sot-baseline-v1"
    if destination.exists():
        raise FileExistsError(f"output_exists: {destination}")
    staging = root / f".sot-baseline-v1-staging-{os.getpid()}"
    if staging.exists():
        raise FileExistsError(f"staging_exists: {staging}")
    staging.mkdir(mode=0o700)
    group_counts: dict[str, int] = {}
    rejected_members: list[dict[str, object]] = []
    accepted_members = 0
    raw_members = 0
    try:
        samples_path = staging / "samples.csv"
        with samples_path.open("w", newline="", encoding="utf-8") as handle:
            fieldnames = [
                "target", "source_id", "physical_cell_id", "condition_id",
                "member_relative_path", "source_row_index", "time_s",
                "voltage", "current", "label",
            ]
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for archive in archives:
                with ZipFile(archive) as zf:
                    for member in sorted(zf.namelist()):
                        if member.endswith("/") or not member.lower().endswith(".csv"):
                            continue
                        raw_members += 1
                        try:
                            roles = map_source_member(member)
                            parsed = parse_member_csv(member, _decode_source(zf.read(member)), strict=False)
                        except SOTLightweightError as exc:
                            rejected_members.append({"archive": str(archive), "member": member, "reason": str(exc)})
                            continue
                        if not parsed.rows:
                            rejected_members.append({"archive": str(archive), "member": member, "reason": "EMPTY_VALID_ROWS"})
                            continue
                        accepted_members += 1
                        group_name = f"{roles.physical_cell_id}|{roles.condition_id}"
                        group_counts[group_name] = group_counts.get(group_name, 0) + len(parsed.rows)
                        for row in parsed.rows:
                            writer.writerow({
                                "target": TARGET,
                                "source_id": source_id,
                                "physical_cell_id": roles.physical_cell_id,
                                "condition_id": roles.condition_id,
                                "member_relative_path": roles.member_relative_path,
                                "source_row_index": row.source_row_index,
                                "time_s": row.source_row_index,
                                "voltage": row.voltage,
                                "current": row.current,
                                "label": row.temperature,
                            })
        if len(group_counts) < 2:
            raise SOTLightweightError("SPLIT_NOT_FEASIBLE")
        split = assign_train_test_groups(group_counts)
        source_files_path = staging / "source_files.csv"
        with source_files_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["path", "size_bytes", "sha256"])
            writer.writeheader()
            for archive in archives:
                writer.writerow({"path": str(archive), "size_bytes": archive.stat().st_size, "sha256": _sha256(archive)})
        manifest_path = staging / "manifest.json"
        row_count = sum(group_counts.values())
        manifest = {
            "schema_version": 1,
            "version": "sot-baseline-v1",
            "target": TARGET,
            "source_id": source_id,
            "feature_names": list(FEATURE_NAMES),
            "row_count": row_count,
            "files": {"samples.csv": _sha256(samples_path), "source_files.csv": _sha256(source_files_path)},
            "scope": "source_native_temperature_seen_cells_conditions_only",
            "label": {"name": LABEL_NAME, "unit": LABEL_UNIT, "source_field": "temp1_1"},
            "features": {"source_fields": ["电压(V)", "电流(A)"], "current_row_only": True},
            "split": {
                "axis": ["physical_cell_id", "condition_id"],
                "policy": "whole_group_train_test",
                "train_groups": split["train_groups"],
                "test_groups": split["test_groups"],
                "validation": None,
                "early_stopping": False,
                "group_row_counts": group_counts,
            },
            "source_audit": {
                "csv_member_count": raw_members,
                "accepted_member_count": accepted_members,
                "rejected_member_count": len(rejected_members),
                "rejected_members": rejected_members,
            },
            "training": {"formal_training_authorized": False},
        }
        _write_json(manifest_path, manifest)
        _write_json(staging / "READY.json", {"schema_version": 1, "manifest_sha256": _sha256(manifest_path)})
        _rename_no_replace(staging, destination)
        return destination, manifest
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


__all__ = [
    "FEATURE_NAMES",
    "LABEL_NAME",
    "LABEL_UNIT",
    "LightweightRow",
    "MemberRoles",
    "ParsedMember",
    "SOTLightweightError",
    "assign_train_test_groups",
    "build_sot_version",
    "map_source_member",
    "parse_member_csv",
]
