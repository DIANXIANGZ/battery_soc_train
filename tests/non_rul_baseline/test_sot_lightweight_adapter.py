from __future__ import annotations

import pytest

from src.data_processing.non_rul_baseline.sot_lightweight import (
    SOTLightweightError,
    assign_train_test_groups,
    map_source_member,
    parse_member_csv,
)


HEADER = "数据序号,电压(V),电流(A),temp1_1,绝对时间\n"
ROWS = "1,3.70,-1.0,25.0,2025-01-01 00:00:00\n2,3.69,-1.0,25.1,2025-01-01 00:00:01\n"


def test_member_mapping_proves_physical_cell_and_condition() -> None:
    roles = map_source_member(
        "Dataset_1_40Ah_battery/-0118-0.3C-100%DOD-1.csv"
    )
    assert roles.physical_cell_id == "cell_40ah_1"
    assert roles.condition_id == "40Ah|0.3C|100%DOD"


def test_missing_temperature_is_rejected() -> None:
    with pytest.raises(SOTLightweightError, match="MISSING_TEMPERATURE_FIELD"):
        parse_member_csv(
            "Dataset_3_280Ah_battery_2/04QCB76718400JB630001092-0.5C-100%DOD-1.csv",
            "数据序号,电压(V),电流(A),绝对时间\n1,3.7,-1,2025-01-01 00:00:00\n",
        )


def test_nonfinite_row_is_rejected_without_imputation() -> None:
    with pytest.raises(SOTLightweightError, match="NON_FINITE_ROW"):
        parse_member_csv(
            "Dataset_1_40Ah_battery/-0118-0.3C-100%DOD-1.csv",
            HEADER + "1,nan,-1.0,25.0,2025-01-01 00:00:00\n",
        )


def test_forbidden_lifecycle_header_is_rejected() -> None:
    with pytest.raises(SOTLightweightError, match="FORBIDDEN_LIFECYCLE_SEMANTICS"):
        parse_member_csv(
            "Dataset_1_40Ah_battery/-0118-0.3C-100%DOD-1.csv",
            "数据序号,电压(V),电流(A),temp1_1,rul_cycles\n"
            "1,3.7,-1,25,1\n",
        )


def test_current_row_features_exclude_temperature_and_future_order() -> None:
    parsed = parse_member_csv(
        "Dataset_1_40Ah_battery/-0118-0.3C-100%DOD-1.csv", HEADER + ROWS
    )
    assert parsed.rows[0].features == {"voltage": 3.7, "current": -1.0}
    assert "temperature" not in parsed.rows[0].features
    assert parsed.rows[0].source_row_index == 2


def test_duplicate_measurements_are_retained_with_source_provenance() -> None:
    parsed = parse_member_csv(
        "Dataset_1_40Ah_battery/-0118-0.3C-100%DOD-1.csv",
        HEADER + "1,3.7,-1.0,25.0,2025-01-01 00:00:00\n"
        "1,3.7,-1.0,25.0,2025-01-01 00:00:00\n",
    )
    assert len(parsed.rows) == 2
    assert [row.source_row_index for row in parsed.rows] == [2, 3]


def test_group_split_is_whole_group_and_has_two_nonempty_sides() -> None:
    groups = {
        "cell_40ah_1|40Ah|0.3C|100%DOD",
        "cell_40ah_1|40Ah|1C|100%DOD",
        "cell_280ah_1|280Ah|0.5C|100%DOD",
    }
    split = assign_train_test_groups(groups)
    assert split["train_groups"] and split["test_groups"]
    assert not set(split["train_groups"]) & set(split["test_groups"])
    assert set(split["train_groups"]) | set(split["test_groups"]) == groups


def test_single_group_split_is_blocked() -> None:
    with pytest.raises(SOTLightweightError, match="SPLIT_NOT_FEASIBLE"):
        assign_train_test_groups({"cell_40ah_1|40Ah|0.3C|100%DOD"})
