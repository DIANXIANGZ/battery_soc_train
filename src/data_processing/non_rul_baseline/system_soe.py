"""Pointwise, system-level SoE preparation for Zenodo 8381142 V1.0."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Mapping, Sequence

from src.data_processing.non_rul_baseline.common import CanonicalRow, DatasetContract


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[3] / "configs" / "training" / "non_rul_baseline" / "system-soe.json"
SOURCE_ID = "zenodo-8381142-v1.0"
TARGET = "system_soe"
FEATURE_NAMES = ("SoC", "Ptcb", "Ptei")
SOURCE_LABEL_FIELD = "SoE"
LABEL_NAME = "soe_source_value"
LABEL_UNIT = "unspecified_source_unit"
SYSTEM_CELL_MARKER = "CBES_SYSTEM_NOT_CELL"
GROUP_FIELD = "RequID"
REQUIRED_FIELDS = frozenset({GROUP_FIELD, "Submission", *FEATURE_NAMES, SOURCE_LABEL_FIELD})
FORBIDDEN_HEADER_TOKENS = (
    "rul", "remaining_life", "remaininglife", "eol", "trajectory", "lifecycle", "cycle_life", "cyclelife",
)


class SystemSOEError(ValueError):
    """Stable fail-closed error for the system-level SOE source contract."""

    def __init__(self, *reason_codes: str):
        self.reason_codes = tuple(reason_codes)
        super().__init__(";".join(self.reason_codes))


@dataclass(frozen=True)
class SystemSOEConfiguration:
    target: str
    source_id: str
    source_csv: Path
    source_size_bytes: int
    source_md5: str
    source_sha256: str
    output_root: Path
    configuration_path: Path
    configuration_sha256: str
    expected_summary: Mapping[str, object] | None
    rollback_policy: str
    doi: str
    version: str
    license: str
    training_enabled: bool
    feature_names: tuple[str, ...] = FEATURE_NAMES
    label_name: str = LABEL_NAME
    label_unit: str = LABEL_UNIT


@dataclass(frozen=True)
class PreparedSystemSOE:
    rows: tuple[CanonicalRow, ...]
    target_metadata: Mapping[str, object]
    raw_row_count: int
    accepted_row_count: int
    rejected_row_count: int
    unique_requid_count: int
    accepted_group_count: int
    rejected_counts: Mapping[str, int]
    soe_missing_count: int
    soe_non_numeric_count: int


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _contains_forbidden_semantics(value: object) -> bool:
    if isinstance(value, str):
        normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
        return any(token in normalized for token in FORBIDDEN_HEADER_TOKENS)
    if isinstance(value, Mapping):
        return any(
            _contains_forbidden_semantics(key) or _contains_forbidden_semantics(nested)
            for key, nested in value.items()
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return any(_contains_forbidden_semantics(item) for item in value)
    return False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _md5(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _number(value: object) -> float | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or ("," in text and "." in text) or text.count(",") > 1:
        return None
    try:
        result = float(text.replace(",", "."))
    except ValueError:
        return None
    return result if math.isfinite(result) else None


def _submission(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _utc_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_json_keys)


def load_system_soe_config(path: str | Path = DEFAULT_CONFIG_PATH) -> SystemSOEConfiguration:
    config_path = Path(path).resolve()
    try:
        payload = _load_json(config_path)
    except (OSError, UnicodeError, ValueError):
        raise SystemSOEError("CONFIGURATION_NOT_READABLE") from None
    if not isinstance(payload, Mapping):
        raise SystemSOEError("INVALID_CONFIGURATION_CONTRACT")
    semantic_payload = dict(payload)
    source_for_semantic_scan = payload.get("source")
    dataset_for_semantic_scan = payload.get("dataset")
    if isinstance(source_for_semantic_scan, Mapping):
        semantic_payload["source"] = {
            key: value for key, value in source_for_semantic_scan.items() if key != "source_csv"
        }
    if isinstance(dataset_for_semantic_scan, Mapping):
        semantic_payload["dataset"] = {
            key: value for key, value in dataset_for_semantic_scan.items() if key != "output_root"
        }
    if _contains_forbidden_semantics(semantic_payload):
        raise SystemSOEError("INVALID_CONFIGURATION_CONTRACT")
    try:
        source = payload["source"]
        features = payload["features"]
        label = payload["label"]
        dataset = payload["dataset"]
        training = payload["training"]
        split = payload["split"]
        identity = payload["identity"]
        summary = payload["expected_source_summary"]
        valid = (
            set(payload) == {
                "schema_version", "target", "source", "scope", "identity", "label", "features",
                "split", "expected_source_summary", "dataset", "training",
            }
            and payload["schema_version"] == 1
            and payload["target"] == TARGET
            and source["source_id"] == SOURCE_ID
            and source["record_id"] == "8381142"
            and source["doi"] == "10.5281/zenodo.8381142"
            and source["version"] == "1.0"
            and source["license"] == "CC BY 4.0"
            and source["file_name"] == "UC Setting Data.csv"
            and type(source["size_bytes"]) is int
            and re.fullmatch(r"[0-9a-f]{32}", source["md5"]) is not None
            and re.fullmatch(r"[0-9a-f]{64}", source["sha256"]) is not None
            and payload["scope"] == "community_storage_system_only_not_cell_level"
            and identity["group_field"] == "RequID"
            and identity["cell_id_marker"] == SYSTEM_CELL_MARKER
            and identity["cell_id_semantics"] == "constant system marker; not a physical cell ID"
            and identity["session_id_semantics"] == "source RequID group; not a time-series session"
            and identity["cycle_index_semantics"] == "zero-based source data-row ordinal; not a cycle"
            and label == {
                "name": LABEL_NAME,
                "source_field": SOURCE_LABEL_FIELD,
                "unit": LABEL_UNIT,
                "unit_conversion": None,
            }
            and features == {
                "source_fields": list(FEATURE_NAMES),
                "time_field": "Submission",
                "time_is_feature": False,
                "allowlist_only": True,
            }
            and split == {
                "axis": "RequID",
                "policy": "earliest_submission_utc_then_requid; train=floor(0.8*n); remainder=test",
                "train_fraction": 0.8,
                "validation": None,
                "early_stopping": False,
            }
            and set(summary) == {
                "raw_data_row_count", "unique_requid_count", "accepted_row_count", "accepted_group_count",
                "soe_missing_count", "soe_non_numeric_count", "soe_min", "soe_max",
            }
            and dataset["version_name"] == "system_soe-baseline-v1"
            and dataset["rollback_policy"]
            == "immutable atomic no-replace publication; preserve all prior versions; failure produces only INVALIDATED"
            and type(training["enabled"]) is bool
            and training["enabled"] is False
            and type(training["formal_training_authorized"]) is bool
            and training["formal_training_authorized"] is False
        )
        if not valid:
            raise ValueError("invalid contract")
        source_csv = Path(source["source_csv"]).resolve()
        output_root = Path(dataset["output_root"]).resolve()
        if not source_csv.is_absolute() or not output_root.is_absolute():
            raise ValueError("paths must be absolute")
        expected_summary = dict(summary)
        if (
            any(type(expected_summary[key]) is not int or expected_summary[key] < 0 for key in (
                "raw_data_row_count", "unique_requid_count", "accepted_row_count", "accepted_group_count",
                "soe_missing_count", "soe_non_numeric_count",
            ))
            or type(expected_summary["soe_min"]) not in (int, float)
            or type(expected_summary["soe_max"]) not in (int, float)
        ):
            raise ValueError("invalid expected summary")
        return SystemSOEConfiguration(
            target=TARGET,
            source_id=SOURCE_ID,
            source_csv=source_csv,
            source_size_bytes=source["size_bytes"],
            source_md5=source["md5"],
            source_sha256=source["sha256"],
            output_root=output_root,
            configuration_path=config_path,
            configuration_sha256=_sha256(config_path),
            expected_summary=expected_summary,
            rollback_policy=dataset["rollback_policy"],
            doi=source["doi"],
            version=source["version"],
            license=source["license"],
            training_enabled=training["enabled"],
        )
    except (KeyError, TypeError, ValueError, OSError):
        raise SystemSOEError("INVALID_CONFIGURATION_CONTRACT") from None


def _metadata(
    *,
    config: SystemSOEConfiguration,
    rows: Sequence[CanonicalRow],
    raw_data_row_count: int,
    unique_requid_count: int,
    rejected_counts: Mapping[str, int],
    soe_missing_count: int,
    soe_non_numeric_count: int,
    all_numeric_soe_values: Sequence[float],
) -> dict[str, object]:
    grouped: dict[str, list[CanonicalRow]] = {}
    for row in rows:
        grouped.setdefault(row.session_id, []).append(row)
    earliest = {group: min(row.time_s for row in members) for group, members in grouped.items()}
    ordered_groups = sorted(grouped, key=lambda group: (earliest[group], group))
    if len(ordered_groups) < 2:
        raise SystemSOEError("INSUFFICIENT_REQUId_GROUPS_FOR_SPLIT")
    train_count = math.floor(len(ordered_groups) * 0.8)
    if train_count < 1 or train_count >= len(ordered_groups):
        raise SystemSOEError("EMPTY_CHRONOLOGICAL_SPLIT")
    train_groups = ordered_groups[:train_count]
    test_groups = ordered_groups[train_count:]
    accepted_labels = [float(row.label) for row in rows if row.label is not None]
    return {
        "schema_version": 1,
        "scope": "community_storage_system_only_not_cell_level",
        "configuration_path": str(config.configuration_path),
        "configuration_sha256": config.configuration_sha256,
        "source_audit": {
            "raw_data_row_count": raw_data_row_count,
            "accepted_row_count": len(rows),
            "rejected_row_count": sum(rejected_counts.values()),
            "unique_requid_count": unique_requid_count,
            "accepted_group_count": len(grouped),
            "soe_missing_count": soe_missing_count,
            "soe_non_numeric_count": soe_non_numeric_count,
            "soe_min": min(accepted_labels),
            "soe_max": max(accepted_labels),
        },
        "identity": {
            "group_field": "RequID",
            "cell_id_semantics": "constant system marker; not a physical cell ID",
            "session_id_semantics": "source RequID group; not a time-series session",
            "cycle_index_semantics": "zero-based source data-row ordinal; not a cycle",
        },
        "label": {"name": LABEL_NAME, "source_field": SOURCE_LABEL_FIELD, "unit": LABEL_UNIT},
        "features": {"source_fields": list(FEATURE_NAMES), "time_field": "Submission", "time_is_feature": False},
        "rollback": {
            "policy": config.rollback_policy,
            "previous_versions_modified": False,
            "existing_target_overwritten": False,
        },
        "split": {
            "axis": GROUP_FIELD,
            "policy": "earliest_submission_utc_then_requid; train=floor(0.8*n); remainder=test",
            "train_fraction": 0.8,
            "ordered_group_ids": ordered_groups,
            "earliest_submission_utc": {
                group: _utc_z(datetime.fromtimestamp(earliest[group], timezone.utc)) for group in ordered_groups
            },
            "train_group_ids": train_groups,
            "test_group_ids": test_groups,
            "train_row_count": sum(len(grouped[group]) for group in train_groups),
            "test_row_count": sum(len(grouped[group]) for group in test_groups),
            "validation": None,
            "early_stopping": False,
        },
    }


def materialize_system_soe(
    csv_path: str | Path,
    config: SystemSOEConfiguration | None = None,
) -> PreparedSystemSOE:
    """Read one hash-bound source CSV and produce RequID-grouped canonical rows."""

    active_config = config if config is not None else load_system_soe_config()
    source_path = Path(csv_path).resolve()
    if source_path != active_config.source_csv:
        raise SystemSOEError("SOURCE_PATH_MISMATCH")
    if not source_path.is_file():
        raise SystemSOEError("SOURCE_FILE_NOT_FOUND")
    if (
        source_path.stat().st_size != active_config.source_size_bytes
        or _md5(source_path) != active_config.source_md5
        or _sha256(source_path) != active_config.source_sha256
    ):
        raise SystemSOEError("SOURCE_FINGERPRINT_MISMATCH")

    rejected: dict[str, int] = {}
    accepted: list[tuple[int, datetime, str, str, dict[str, float], float]] = []
    raw_groups: set[str] = set()
    all_numeric_soe_values: list[float] = []
    soe_missing_count = 0
    soe_non_numeric_count = 0
    raw_row_count = 0
    try:
        with source_path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle, delimiter=";")
            headers = reader.fieldnames
            if headers is None or len(headers) != len(set(headers)) or not REQUIRED_FIELDS <= set(headers):
                raise SystemSOEError("REQUIRED_FIELD_OR_HEADER_INVALID")
            normalized_headers = [re.sub(r"[^a-z0-9]+", "_", item.strip().lower()).strip("_") for item in headers]
            if any(
                token in normalized
                for normalized in normalized_headers
                for token in FORBIDDEN_HEADER_TOKENS
            ):
                raise SystemSOEError("FORBIDDEN_SOURCE_FIELD")

            for source_row_index, record in enumerate(reader):
                raw_row_count += 1
                if None in record:
                    rejected["malformed_csv_row"] = rejected.get("malformed_csv_row", 0) + 1
                    continue
                requid_raw = record.get(GROUP_FIELD)
                requid = requid_raw.strip() if isinstance(requid_raw, str) else ""
                if requid:
                    raw_groups.add(requid)
                submitted = _submission(record.get("Submission"))
                soe_raw = record.get(SOURCE_LABEL_FIELD)
                if not isinstance(soe_raw, str) or not soe_raw.strip():
                    soe_missing_count += 1
                    soe_value = None
                else:
                    soe_value = _number(soe_raw)
                    if soe_value is None:
                        soe_non_numeric_count += 1
                    else:
                        all_numeric_soe_values.append(soe_value)
                feature_values = {name: _number(record.get(name)) for name in FEATURE_NAMES}

                reason: str | None = None
                if not requid:
                    reason = "missing_requid"
                elif submitted is None:
                    reason = "invalid_submission"
                elif soe_value is None:
                    reason = "missing_soe" if not isinstance(soe_raw, str) or not soe_raw.strip() else "non_numeric_soe"
                elif any(value is None for value in feature_values.values()):
                    reason = "invalid_numeric_feature"
                if reason is not None:
                    rejected[reason] = rejected.get(reason, 0) + 1
                    continue

                type_value = record.get("Type", "").strip() if isinstance(record.get("Type"), str) else ""
                subtype_value = record.get("Subtype", "").strip() if isinstance(record.get("Subtype"), str) else ""
                condition_id = f"Type={type_value or 'unknown'}|Subtype={subtype_value or 'unknown'}"
                accepted.append(
                    (
                        source_row_index,
                        submitted,
                        requid,
                        condition_id,
                        {name: float(value) for name, value in feature_values.items() if value is not None},
                        float(soe_value),
                    ),
                )
    except SystemSOEError:
        raise
    except (OSError, UnicodeError, csv.Error):
        raise SystemSOEError("SOURCE_CSV_UNREADABLE") from None

    if not accepted or not all_numeric_soe_values:
        raise SystemSOEError("NO_VALID_SYSTEM_SOE_ROWS")
    if active_config.expected_summary is not None:
        actual = {
            "raw_data_row_count": raw_row_count,
            "unique_requid_count": len(raw_groups),
            "accepted_row_count": len(accepted),
            "accepted_group_count": len({entry[2] for entry in accepted}),
            "soe_missing_count": soe_missing_count,
            "soe_non_numeric_count": soe_non_numeric_count,
            "soe_min": min(all_numeric_soe_values),
            "soe_max": max(all_numeric_soe_values),
        }
        expected = dict(active_config.expected_summary)
        if actual != expected:
            raise SystemSOEError("EXPECTED_SOURCE_SUMMARY_MISMATCH")

    by_group: dict[str, list[tuple[int, datetime, str, str, dict[str, float], float]]] = {}
    for entry in accepted:
        by_group.setdefault(entry[2], []).append(entry)
    ordered_group_ids = sorted(
        by_group,
        key=lambda group: (min(item[1] for item in by_group[group]), group),
    )
    rows: list[CanonicalRow] = []
    for group in ordered_group_ids:
        for source_row_index, submitted, requid, condition_id, features, label in sorted(
            by_group[group], key=lambda item: (item[1], item[0])
        ):
            rows.append(
                CanonicalRow(
                    target=TARGET,
                    source_id=active_config.source_id,
                    cell_id=SYSTEM_CELL_MARKER,
                    session_id=requid,
                    condition_id=condition_id,
                    cycle_index=source_row_index,
                    time_s=submitted.timestamp(),
                    features=features,
                    label=label,
                ),
            )
    target_metadata = _metadata(
        config=active_config,
        rows=rows,
        raw_data_row_count=raw_row_count,
        unique_requid_count=len(raw_groups),
        rejected_counts=rejected,
        soe_missing_count=soe_missing_count,
        soe_non_numeric_count=soe_non_numeric_count,
        all_numeric_soe_values=all_numeric_soe_values,
    )
    return PreparedSystemSOE(
        rows=tuple(rows),
        target_metadata=target_metadata,
        raw_row_count=raw_row_count,
        accepted_row_count=len(rows),
        rejected_row_count=sum(rejected.values()),
        unique_requid_count=len(raw_groups),
        accepted_group_count=len(by_group),
        rejected_counts=dict(sorted(rejected.items())),
        soe_missing_count=soe_missing_count,
        soe_non_numeric_count=soe_non_numeric_count,
    )


__all__ = [
    "FEATURE_NAMES",
    "LABEL_NAME",
    "LABEL_UNIT",
    "SOURCE_ID",
    "SystemSOEConfiguration",
    "SystemSOEError",
    "PreparedSystemSOE",
    "load_system_soe_config",
    "materialize_system_soe",
]
