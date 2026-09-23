import csv
import hashlib
import importlib
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest


def _module():
    try:
        return importlib.import_module("src.data_processing.non_rul_baseline.system_soe")
    except ModuleNotFoundError as exc:
        pytest.fail(f"RED: system_soe adapter is not implemented: {exc.name}")


HEADERS = [
    "RequID", "Alert", "Submission", "Note", "Priority", "Status", "Version",
    "Start", "End", "Type", "Subtype", "bulkStart", "bulkEnd", "bulkEnergy",
    "Final_SOF", "FlexDemand", "Ptcb", "Ptei", "SoC", "SoE", "ActiveSet", "maxSoC", "minSoC",
]


def _valid_rows():
    times = [
        "2021-06-17T07:41:00Z",
        "2021-06-17T07:42:00Z",
        "2021-06-17T07:43:00Z",
        "2021-06-17T07:44:00Z",
        "2021-06-17T07:45:00Z",
    ]
    rows = []
    for index, (group, submitted) in enumerate(zip(["request-a", "request-b", "request-c", "request-d", "request-e"], times)):
        for point in range(2 if index == 0 else 1):
            rows.append(
                {
                    "RequID": group,
                    "Alert": "",
                    "Submission": submitted,
                    "Note": "future text must not be a feature",
                    "Priority": "1",
                    "Status": "active",
                    "Version": "1",
                    "Start": "2021-06-16T00:00:00Z",
                    "End": "2021-06-18T00:00:00Z",
                    "Type": "1",
                    "Subtype": "0",
                    "bulkStart": "0",
                    "bulkEnd": "999",
                    "bulkEnergy": "777",
                    "Final_SOF": "0.99",
                    "FlexDemand": "0",
                    "Ptcb": f"{0.10 + index / 100:.2f}".replace(".", ","),
                    "Ptei": f"{0.20 + index / 100:.2f}".replace(".", ","),
                    "SoC": f"{0.50 + index / 100:.2f}".replace(".", ","),
                    "SoE": (f"{300.0 + index + point / 10:.1f}").replace(".", ","),
                    "ActiveSet": "",
                    "maxSoC": "1,0",
                    "minSoC": "0,0",
                },
            )
    return rows


def _write_source(path: Path, rows) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADERS, delimiter=";", lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(rows)


def _config_for_source(module, source: Path, *, expected_summary=None):
    base = module.load_system_soe_config()
    content = source.read_bytes()
    return replace(
        base,
        source_csv=source.resolve(),
        source_size_bytes=len(content),
        source_md5=hashlib.md5(content, usedforsecurity=False).hexdigest(),
        source_sha256=hashlib.sha256(content).hexdigest(),
        expected_summary=expected_summary,
    )


def test_default_config_is_system_level_and_training_disabled() -> None:
    module = _module()
    config = module.load_system_soe_config()

    assert config.target == "system_soe"
    assert config.source_id == "zenodo-8381142-v1.0"
    assert config.feature_names == ("SoC", "Ptcb", "Ptei")
    assert config.label_name == "soe_source_value"
    assert config.label_unit == "unspecified_source_unit"
    assert config.training_enabled is False


@pytest.mark.parametrize("forbidden", ["lifecycle", "rul"])
def test_non_path_configuration_field_with_forbidden_semantics_is_rejected(
    tmp_path: Path,
    forbidden: str,
) -> None:
    module = _module()
    config_path = module.DEFAULT_CONFIG_PATH
    config_text = config_path.read_text(encoding="utf-8")
    config_text = config_text.replace(
        '"scope": "community_storage_system_only_not_cell_level"',
        f'"scope": "{forbidden}"',
        1,
    )
    altered_path = tmp_path / f"forbidden-{forbidden}-scope.json"
    altered_path.write_text(config_text, encoding="utf-8")

    with pytest.raises(module.SystemSOEError, match="INVALID_CONFIGURATION_CONTRACT"):
        module.load_system_soe_config(altered_path)


def test_materializer_keeps_only_allowlisted_current_fields_and_soE_source_values(tmp_path: Path) -> None:
    module = _module()
    source = tmp_path / "fixture.csv"
    _write_source(source, _valid_rows())
    prepared = module.materialize_system_soe(source, _config_for_source(module, source))

    assert len(prepared.rows) == 6
    assert prepared.rows[0].features == {"SoC": 0.5, "Ptcb": 0.1, "Ptei": 0.2}
    assert prepared.rows[0].label == 300.0
    assert prepared.rows[1].label == 300.1
    assert prepared.rows[0].target == "system_soe"
    assert prepared.rows[0].cell_id == "CBES_SYSTEM_NOT_CELL"
    assert prepared.rows[0].session_id == "request-a"
    assert prepared.rows[0].time_s == datetime(2021, 6, 17, 7, 41, tzinfo=timezone.utc).timestamp()
    assert prepared.target_metadata["split"]["train_group_ids"] == [
        "request-a", "request-b", "request-c", "request-d"
    ]
    assert prepared.target_metadata["split"]["test_group_ids"] == ["request-e"]
    assert prepared.target_metadata["split"]["train_row_count"] == 5
    assert prepared.target_metadata["split"]["test_row_count"] == 1
    assert prepared.target_metadata["label"]["unit"] == "unspecified_source_unit"


def test_invalid_required_values_are_excluded_with_auditable_counts(tmp_path: Path) -> None:
    module = _module()
    source = tmp_path / "fixture.csv"
    rows = _valid_rows()
    missing_feature = dict(rows[0], RequID="bad-feature", SoC="")
    bad_time = dict(rows[0], RequID="bad-time", Submission="not-a-date")
    missing_label = dict(rows[0], RequID="missing-label", SoE="")
    non_numeric_label = dict(rows[0], RequID="bad-label", SoE="unknown")
    rows.extend([missing_feature, bad_time, missing_label, non_numeric_label])
    _write_source(source, rows)

    prepared = module.materialize_system_soe(source, _config_for_source(module, source))

    assert len(prepared.rows) == 6
    assert prepared.rejected_row_count == 4
    assert prepared.rejected_counts["invalid_numeric_feature"] == 1
    assert prepared.rejected_counts["invalid_submission"] == 1
    assert prepared.rejected_counts["missing_soe"] == 1
    assert prepared.rejected_counts["non_numeric_soe"] == 1


@pytest.mark.parametrize("forbidden", ["rul_cycles", "EOL_status", "trajectory_id", "lifecycle_state"])
def test_forbidden_header_semantics_are_rejected(tmp_path: Path, forbidden: str) -> None:
    module = _module()
    source = tmp_path / "fixture.csv"
    _write_source(source, _valid_rows())
    text = source.read_text(encoding="utf-8")
    source.write_text(text.replace("RequID;", f"{forbidden};RequID;", 1), encoding="utf-8")

    with pytest.raises(module.SystemSOEError, match="FORBIDDEN_SOURCE_FIELD"):
        module.materialize_system_soe(source, _config_for_source(module, source))


def test_source_sha_mismatch_fails_before_parsing(tmp_path: Path) -> None:
    module = _module()
    source = tmp_path / "fixture.csv"
    _write_source(source, _valid_rows())
    config = _config_for_source(module, source)
    config = replace(config, source_sha256="0" * 64)

    with pytest.raises(module.SystemSOEError, match="SOURCE_FINGERPRINT_MISMATCH"):
        module.materialize_system_soe(source, config)


def test_naive_or_ambiguous_submission_and_decimal_values_are_rejected(tmp_path: Path) -> None:
    module = _module()
    source = tmp_path / "fixture.csv"
    rows = _valid_rows()
    rows.append(dict(rows[0], RequID="naive-time", Submission="2021-06-17T07:46:00"))
    rows.append(dict(rows[0], RequID="ambiguous-number", SoC="1.234,56"))
    _write_source(source, rows)

    prepared = module.materialize_system_soe(source, _config_for_source(module, source))

    assert len(prepared.rows) == 6
    assert prepared.rejected_counts["invalid_submission"] == 1
    assert prepared.rejected_counts["invalid_numeric_feature"] == 1


def test_config_mismatch_cannot_enable_training_or_change_feature_allowlist(tmp_path: Path) -> None:
    module = _module()
    config_path = tmp_path / "bad.json"
    config_path.write_text(
        '{"schema_version":1,"target":"soe","training":{"enabled":true}}\n',
        encoding="utf-8",
    )

    with pytest.raises(module.SystemSOEError, match="INVALID_CONFIGURATION_CONTRACT"):
        module.load_system_soe_config(config_path)
