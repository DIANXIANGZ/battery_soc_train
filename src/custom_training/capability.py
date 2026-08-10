"""Versioned custom-training capability bound to configuration and evidence."""

from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import csv
import json
from pathlib import Path
from typing import Any

from src.custom_training.admission import assess_custom_training
from src.custom_training.dataset import CustomDatasetConfig


CAPABILITY_SCHEMA_VERSION = 1


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: object) -> str:
    return sha256(_canonical_json(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized_custom_config(config: dict[str, object]) -> dict[str, object]:
    roles = config.get("role_columns")
    if not isinstance(roles, list):
        raise ValueError("custom_config.role_columns is invalid")
    normalized_roles: list[list[str]] = []
    for item in roles:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ValueError("custom_config.role_columns is invalid")
        normalized_roles.append([str(item[0]), str(item[1])])
    normalized_roles.sort(key=lambda item: (item[0], item[1]))

    def string_list(field: str) -> list[str]:
        values = config.get(field)
        if not isinstance(values, list) or not values:
            raise ValueError(f"custom_config.{field} is invalid")
        return [str(item) for item in values]

    algorithm = config.get("algorithm")
    if not isinstance(algorithm, str) or not algorithm:
        raise ValueError("custom_config.algorithm is invalid")
    time_column = config.get("time_column")
    if time_column is not None and not isinstance(time_column, str):
        raise ValueError("custom_config.time_column is invalid")
    return {
        "algorithm": algorithm,
        "time_column": time_column,
        "feature_columns": string_list("feature_columns"),
        "target_columns": string_list("target_columns"),
        "role_columns": normalized_roles,
    }


def configuration_fingerprint(config: dict[str, object]) -> str:
    return _digest(normalized_custom_config(config))


def validate_exported_headers(config: dict[str, object], data_path: Path) -> tuple[str, ...]:
    with Path(data_path).open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        headers = tuple(next(reader, ()))
    if not headers or len(headers) != len(set(headers)):
        raise ValueError("exported dataset headers are invalid")
    normalized = normalized_custom_config(config)
    declared_roles = {str(item[0]) for item in normalized["role_columns"]}
    missing_roles = sorted(declared_roles - set(headers))
    if missing_roles:
        raise ValueError(f"declared role columns are missing from export: {', '.join(missing_roles)}")
    required_data = set(normalized["feature_columns"]) | set(normalized["target_columns"])
    missing_data = sorted(required_data - set(headers))
    if missing_data:
        raise ValueError(f"configured data columns are missing from export: {', '.join(missing_data)}")
    return headers


def _config_for_assessment(config: dict[str, object], data_path: Path) -> CustomDatasetConfig:
    normalized = normalized_custom_config(config)
    return CustomDatasetConfig(
        source_path=Path(data_path),
        sheet_name=None,
        time_column=normalized["time_column"],
        feature_columns=tuple(normalized["feature_columns"]),
        target_columns=tuple(normalized["target_columns"]),
        algorithm=str(normalized["algorithm"]),
        role_columns=tuple(tuple(item) for item in normalized["role_columns"]),
    )


def _serialize_report(config: dict[str, object], data_path: Path, manifest: dict[str, object]) -> dict[str, object]:
    report = asdict(assess_custom_training(_config_for_assessment(config, data_path), manifest=manifest))
    return json.loads(_canonical_json(report))


def create_training_capability(
    config: dict[str, object],
    data_path: Path,
    *,
    manifest: dict[str, object],
    approved_by: str,
    approved_at: str,
) -> dict[str, object]:
    manifest_version = manifest.get("manifest_version")
    if not isinstance(manifest_version, str) or not manifest_version.strip():
        raise ValueError("manifest_version is required")
    if not approved_by.strip() or not approved_at.strip():
        raise ValueError("approval metadata is required")
    validate_exported_headers(config, data_path)
    report = _serialize_report(config, data_path, manifest)
    if report.get("training_allowed") is not True:
        raise ValueError("target admission report does not authorize training")
    body: dict[str, object] = {
        "schema_version": CAPABILITY_SCHEMA_VERSION,
        "training_allowed": True,
        "configuration_fingerprint": configuration_fingerprint(config),
        "dataset_sha256": file_sha256(data_path),
        "manifest_version": manifest_version,
        "manifest_fingerprint": _digest(manifest),
        "manifest": manifest,
        "target_report": report,
        "approval": {"approved_by": approved_by, "approved_at": approved_at},
    }
    return {**body, "capability_digest": _digest(body)}


def verify_training_capability(
    capability: dict[str, object],
    config: dict[str, object],
    data_path: Path,
) -> dict[str, object]:
    required = {
        "schema_version",
        "training_allowed",
        "configuration_fingerprint",
        "dataset_sha256",
        "manifest_version",
        "manifest_fingerprint",
        "manifest",
        "target_report",
        "approval",
        "capability_digest",
    }
    if not required.issubset(capability):
        raise ValueError("capability fields are incomplete")
    if capability.get("schema_version") != CAPABILITY_SCHEMA_VERSION:
        raise ValueError("capability schema version is invalid")
    body = {key: value for key, value in capability.items() if key != "capability_digest"}
    if capability.get("capability_digest") != _digest(body):
        raise ValueError("capability digest is invalid")
    if capability.get("training_allowed") is not True:
        raise ValueError("capability is not authorized")
    if capability.get("configuration_fingerprint") != configuration_fingerprint(config):
        raise ValueError("capability configuration is stale")
    validate_exported_headers(config, data_path)
    if capability.get("dataset_sha256") != file_sha256(data_path):
        raise ValueError("capability dataset is stale")
    manifest = capability.get("manifest")
    if not isinstance(manifest, dict):
        raise ValueError("capability manifest is invalid")
    manifest_version = manifest.get("manifest_version")
    if capability.get("manifest_version") != manifest_version or not isinstance(manifest_version, str):
        raise ValueError("capability manifest version is invalid")
    if capability.get("manifest_fingerprint") != _digest(manifest):
        raise ValueError("capability manifest fingerprint is invalid")
    approval = capability.get("approval")
    if not isinstance(approval, dict) or not all(
        isinstance(approval.get(field), str) and bool(str(approval[field]).strip())
        for field in ("approved_by", "approved_at")
    ):
        raise ValueError("capability approval metadata is invalid")
    expected_report = _serialize_report(config, data_path, manifest)
    if capability.get("target_report") != expected_report or expected_report.get("training_allowed") is not True:
        raise ValueError("capability target report is invalid")
    return capability


def verify_registry_capability(
    registry_path: Path,
    project_id: str,
    data_path: Path,
    *,
    algorithm: str,
    features: tuple[str, ...],
    targets: tuple[str, ...],
) -> dict[str, object]:
    records = json.loads(Path(registry_path).read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError("admission registry is invalid")
    record = next(
        (item for item in records if isinstance(item, dict) and item.get("project_id") == project_id),
        None,
    )
    if not isinstance(record, dict):
        raise ValueError("admission project identity is invalid")
    recorded_data = record.get("data_path")
    if not isinstance(recorded_data, str) or Path(recorded_data).resolve() != Path(data_path).resolve():
        raise ValueError("admission data identity is invalid")
    config = record.get("custom_config")
    capability = record.get("custom_admission")
    if not isinstance(config, dict) or not isinstance(capability, dict):
        raise ValueError("admission record is incomplete")
    normalized = normalized_custom_config(config)
    if (
        normalized["algorithm"] != algorithm
        or tuple(normalized["feature_columns"]) != features
        or tuple(normalized["target_columns"]) != targets
    ):
        raise ValueError("admission command configuration is stale")
    return verify_training_capability(capability, config, Path(data_path))
