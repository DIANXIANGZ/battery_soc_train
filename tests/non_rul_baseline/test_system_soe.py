import inspect
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone

import pytest

from src.data_processing.non_rul_baseline import CanonicalRow, DatasetContract
from src.data_processing.non_rul_baseline.build import (
    DatasetBuildError,
    build_version,
    verify_version,
)
from src.data_processing.non_rul_baseline.common import SUPPORTED_TARGETS, validate_contract


def _contract() -> DatasetContract:
    return DatasetContract(
        target="system_soe",
        source_id="zenodo-8381142-v1.0",
        feature_names=("SoC", "Ptcb", "Ptei"),
    )


def _rows() -> list[CanonicalRow]:
    first_time = datetime(2021, 6, 17, 7, 41, tzinfo=timezone.utc).timestamp()
    return [
        CanonicalRow(
            "system_soe",
            "zenodo-8381142-v1.0",
            "CBES_SYSTEM_NOT_CELL",
            "request-1",
            "Type=1|Subtype=0",
            10,
            first_time,
            {"SoC": 0.5, "Ptcb": 0.1, "Ptei": 0.2},
            328.02,
        ),
        CanonicalRow(
            "system_soe",
            "zenodo-8381142-v1.0",
            "CBES_SYSTEM_NOT_CELL",
            "request-1",
            "Type=1|Subtype=0",
            11,
            first_time,
            {"SoC": 0.6, "Ptcb": 0.2, "Ptei": 0.3},
            338.36,
        ),
    ]


def _split_rows() -> list[CanonicalRow]:
    rows = _rows()
    for index in range(2, 6):
        group = f"request-{index}"
        time_value = datetime(2021, 6, 17, 7, 40 + index, tzinfo=timezone.utc).timestamp()
        rows.append(
            CanonicalRow(
                "system_soe",
                "zenodo-8381142-v1.0",
                "CBES_SYSTEM_NOT_CELL",
                group,
                "Type=1|Subtype=0",
                20 + index,
                time_value,
                {"SoC": 0.5, "Ptcb": 0.1, "Ptei": 0.2},
                300.0 + index,
            ),
        )
    return rows


def _target_metadata() -> dict[str, object]:
    groups = [f"request-{index}" for index in range(1, 6)]
    earliest = {
        group: f"2021-06-17T07:4{index}:00Z"
        for index, group in enumerate(groups, start=1)
    }
    return {
        "schema_version": 1,
        "scope": "community_storage_system_only_not_cell_level",
        "configuration_path": "/tmp/system-soe-test.json",
        "configuration_sha256": "a" * 64,
        "source_audit": {
            "raw_data_row_count": 6,
            "accepted_row_count": 6,
            "rejected_row_count": 0,
            "unique_requid_count": 5,
            "accepted_group_count": 5,
            "soe_missing_count": 0,
            "soe_non_numeric_count": 0,
            "soe_min": 302.0,
            "soe_max": 338.36,
        },
        "identity": {
            "group_field": "RequID",
            "cell_id_semantics": "constant system marker; not a physical cell ID",
            "session_id_semantics": "source RequID group; not a time-series session",
            "cycle_index_semantics": "zero-based source data-row ordinal; not a cycle",
        },
        "label": {
            "name": "soe_source_value",
            "source_field": "SoE",
            "unit": "unspecified_source_unit",
        },
        "rollback": {
            "policy": "immutable atomic no-replace publication; preserve all prior versions; failure produces only INVALIDATED",
            "previous_versions_modified": False,
            "existing_target_overwritten": False,
        },
        "features": {
            "source_fields": ["SoC", "Ptcb", "Ptei"],
            "time_field": "Submission",
            "time_is_feature": False,
        },
        "split": {
            "axis": "RequID",
            "policy": "earliest_submission_utc_then_requid; train=floor(0.8*n); remainder=test",
            "train_fraction": 0.8,
            "ordered_group_ids": groups,
            "earliest_submission_utc": earliest,
            "train_group_ids": groups[:4],
            "test_group_ids": groups[4:],
            "train_row_count": 5,
            "test_row_count": 1,
            "validation": None,
            "early_stopping": False,
        },
    }


def _source(tmp_path: Path) -> Path:
    source = tmp_path / "official.csv"
    source.write_text("source-fixture\n", encoding="utf-8")
    return source


def _refresh_manifest_ready_hashes(version: Path) -> None:
    manifest_path = version / "manifest.json"
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    (version / "READY.json").write_text(
        json.dumps({"schema_version": 1, "manifest_sha256": manifest_sha}, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def test_system_soe_has_its_own_supported_target_namespace() -> None:
    assert "system_soe" in SUPPORTED_TARGETS
    assert "system_soe" != "soe"


def test_system_soe_allows_equal_submission_times_within_one_request_group() -> None:
    assert validate_contract(_contract(), _rows()) == []


def test_builder_exposes_opt_in_target_metadata_without_changing_legacy_parameters() -> None:
    parameters = inspect.signature(build_version).parameters
    assert "target_metadata" in parameters
    assert parameters["target_metadata"].kind is inspect.Parameter.KEYWORD_ONLY


def test_builder_records_and_verifies_group_split_metadata(tmp_path: Path) -> None:
    version = build_version(
        "system_soe",
        _split_rows(),
        _contract(),
        tmp_path,
        source_files=[_source(tmp_path)],
        target_metadata=_target_metadata(),
    )

    assert version == tmp_path / "system_soe-baseline-v1"
    assert verify_version(version) == []
    manifest = json.loads((version / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["target_metadata"]["split"]["train_group_ids"] == [
        "request-1", "request-2", "request-3", "request-4"
    ]
    assert manifest["target_metadata"]["rollback"]["previous_versions_modified"] is False


def test_system_soe_requires_metadata_and_rejects_metadata_on_other_targets(tmp_path: Path) -> None:
    with pytest.raises(DatasetBuildError):
        build_version("system_soe", _split_rows(), _contract(), tmp_path, source_files=[_source(tmp_path)])
    assert {path.name for path in (tmp_path / "system_soe-baseline-v1").iterdir()} == {"INVALIDATED.json"}

    other_root = tmp_path / "other"
    with pytest.raises(DatasetBuildError):
        build_version(
            "soe",
            _rows(),
            DatasetContract("soe", "source", ("SoC",)),
            other_root,
            source_files=[_source(tmp_path)],
            target_metadata=_target_metadata(),
        )


def test_system_soe_rejects_split_metadata_with_group_overlap(tmp_path: Path) -> None:
    metadata = _target_metadata()
    split = metadata["split"]
    assert isinstance(split, dict)
    split["test_group_ids"] = ["request-4", "request-5"]
    split["train_group_ids"] = ["request-1", "request-2", "request-3", "request-4"]

    with pytest.raises(DatasetBuildError):
        build_version(
            "system_soe",
            _split_rows(),
            _contract(),
            tmp_path,
            source_files=[_source(tmp_path)],
            target_metadata=metadata,
        )
    assert {path.name for path in (tmp_path / "system_soe-baseline-v1").iterdir()} == {"INVALIDATED.json"}


def test_system_soe_verify_rejects_semantic_metadata_tamper_after_hash_refresh(tmp_path: Path) -> None:
    version = build_version(
        "system_soe",
        _split_rows(),
        _contract(),
        tmp_path,
        source_files=[_source(tmp_path)],
        target_metadata=_target_metadata(),
    )
    manifest_path = version / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["target_metadata"]["split"]["train_group_ids"].append("request-5")
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    _refresh_manifest_ready_hashes(version)

    assert any("system_soe分组切分" in error for error in verify_version(version))
