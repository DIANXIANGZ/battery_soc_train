from __future__ import annotations

from dataclasses import replace

from src.data_processing.non_rul_baseline.common import (
    CanonicalRow,
    DatasetContract,
    validate_contract,
)


def _contract() -> DatasetContract:
    return DatasetContract(
        target="sot",
        source_id="zenodo-13759419-v1",
        feature_names=("voltage_v", "current_a"),
    )


def _row(**changes: object) -> CanonicalRow:
    row = CanonicalRow(
        target="sot",
        source_id="zenodo-13759419-v1",
        cell_id="cell-01",
        session_id="session-01",
        condition_id="25c-1c",
        cycle_index=1,
        time_s=0.0,
        features={"voltage_v": 3.7, "current_a": 1.0},
        label=25.0,
    )
    return replace(row, **changes)


def test_valid_contract_has_no_errors() -> None:
    errors = validate_contract(_contract(), [_row(), _row(time_s=1.0)])

    assert errors == []


def test_missing_label_is_rejected() -> None:
    errors = validate_contract(_contract(), [_row(label=None)])

    assert "第1行缺少目标标签" in errors


def test_time_must_increase_inside_the_same_session() -> None:
    errors = validate_contract(_contract(), [_row(time_s=2.0), _row(time_s=1.0)])

    assert "cell-01/session-01的时间顺序不递增" in errors


def test_empty_group_identifiers_are_rejected() -> None:
    errors = validate_contract(
        _contract(),
        [_row(cell_id="", session_id=" ", condition_id="")],
    )

    assert "第1行缺少cell_id" in errors
    assert "第1行缺少session_id" in errors
    assert "第1行缺少condition_id" in errors


def test_rul_and_eol_fields_are_rejected() -> None:
    contract = DatasetContract(
        target="sot",
        source_id="zenodo-13759419-v1",
        feature_names=("voltage_v", "rul_cycles"),
    )
    row = _row(features={"voltage_v": 3.7, "rul_cycles": 10.0})

    errors = validate_contract(contract, [row])

    assert "禁止字段：rul_cycles" in errors


def test_contract_and_rows_must_have_matching_target_and_source() -> None:
    errors = validate_contract(
        _contract(),
        [_row(target="soc", source_id="other-source")],
    )

    assert "第1行目标与合同不一致" in errors
    assert "第1行来源与合同不一致" in errors


def test_declared_features_must_exist_and_be_finite() -> None:
    errors = validate_contract(
        _contract(),
        [_row(features={"voltage_v": float("nan")})],
    )

    assert "第1行缺少特征：current_a" in errors
    assert "第1行特征voltage_v不是有限数值" in errors
