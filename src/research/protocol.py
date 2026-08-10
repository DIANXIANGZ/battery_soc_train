"""Load and validate the frozen research protocol and dataset registry."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


ALLOWED_DATASET_ROLES = {
    "development",
    "frozen_external_test",
    "compatibility_audit",
}


@dataclass(frozen=True)
class ResearchProtocol:
    """Rules that must remain fixed throughout one research version."""

    version: str
    scope: str
    seeds: tuple[int, ...]
    external_test_locked: bool
    minimum_primary_datasets: int


@dataclass(frozen=True)
class DatasetRegistration:
    """Traceable identity and pre-registered role of one source dataset."""

    dataset_id: str
    chemistry: str
    role: str
    source_root: Path
    label_method: str


def _read_json(path: Path) -> dict:
    path = Path(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Research configuration does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Research configuration is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Research configuration must contain a JSON object: {path}")
    return payload


def _required_text(payload: dict, field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"'{field}' must be a non-empty string")
    return value.strip()


def load_protocol(path: Path) -> ResearchProtocol:
    """Read a frozen protocol and reject settings that weaken independence."""

    payload = _read_json(path)
    raw_seeds = payload.get("seeds")
    if not isinstance(raw_seeds, list) or not raw_seeds:
        raise ValueError("'seeds' must be a non-empty list")
    try:
        seeds = tuple(int(value) for value in raw_seeds)
    except (TypeError, ValueError) as exc:
        raise ValueError("'seeds' must contain integers") from exc

    errors = []
    if len(seeds) != len(set(seeds)):
        errors.append("seeds must be unique")
    if payload.get("external_test_locked") is not True:
        errors.append("external test must be locked")
    minimum = payload.get("minimum_primary_datasets")
    if not isinstance(minimum, int) or isinstance(minimum, bool) or minimum < 3:
        errors.append("minimum_primary_datasets must be an integer of at least 3")
    if errors:
        raise ValueError("; ".join(errors))

    return ResearchProtocol(
        version=_required_text(payload, "version"),
        scope=_required_text(payload, "scope"),
        seeds=seeds,
        external_test_locked=True,
        minimum_primary_datasets=minimum,
    )


def load_dataset_registry(path: Path) -> tuple[DatasetRegistration, ...]:
    """Read dataset roles and require exactly one unique identity per entry."""

    payload = _read_json(path)
    raw_records = payload.get("datasets")
    if not isinstance(raw_records, list) or not raw_records:
        raise ValueError("'datasets' must be a non-empty list")

    records = []
    for index, item in enumerate(raw_records):
        if not isinstance(item, dict):
            raise ValueError(f"datasets[{index}] must be an object")
        role = _required_text(item, "role")
        if role not in ALLOWED_DATASET_ROLES:
            raise ValueError(f"datasets[{index}].role is not supported: {role}")
        source_root = Path(_required_text(item, "source_root"))
        records.append(
            DatasetRegistration(
                dataset_id=_required_text(item, "dataset_id"),
                chemistry=_required_text(item, "chemistry"),
                role=role,
                source_root=source_root,
                label_method=_required_text(item, "label_method"),
            )
        )

    ids = [record.dataset_id for record in records]
    if len(ids) != len(set(ids)):
        raise ValueError("dataset_id values must be unique")
    return tuple(records)

