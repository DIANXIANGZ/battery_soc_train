from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.data_processing.battery_data_quality import (
    BatteryTableSchema,
    admit,
    profile_battery_table,
    write_quality_report,
)


def valid_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "cell_id": ["c1", "c1", "c1", "c2", "c2"],
        "session_id": ["s1", "s1", "s1", "s2", "s2"],
        "timestamp_s": [0.0, 1.0, 2.0, 0.0, 1.0],
        "voltage_v": [3.6, 3.5, 3.4, 3.7, 3.6],
        "current_a": [1.0, 1.0, 1.0, 0.5, 0.5],
        "temperature_c": [25.0, 25.2, 25.4, 20.0, 20.1],
        "soc": [1.0, 0.9, 0.8, 1.0, 0.95],
    })


SCHEMA = BatteryTableSchema(
    group_columns=("cell_id", "session_id"),
    time_column="timestamp_s",
    target_columns=("soc",),
    target_provenance={"soc": "measured_or_causal_integral"},
)


class BatteryDataQualityTests(unittest.TestCase):
    def test_valid_table_is_admitted_and_reports_group_coverage(self) -> None:
        report = profile_battery_table(valid_frame(), SCHEMA)
        self.assertTrue(admit(report))
        self.assertEqual(report.row_count, 5)
        self.assertEqual(report.group_count, 2)
        self.assertEqual(report.critical_count, 0)

    def test_duplicate_group_timestamp_is_rejected(self) -> None:
        frame = valid_frame()
        frame.loc[2, "timestamp_s"] = 1.0
        report = profile_battery_table(frame, SCHEMA)
        self.assertFalse(admit(report))
        self.assertIn("duplicate_group_time", {finding.code for finding in report.findings})

    def test_reversed_time_is_rejected(self) -> None:
        frame = valid_frame()
        frame.loc[2, "timestamp_s"] = 0.5
        report = profile_battery_table(frame, SCHEMA)
        self.assertFalse(admit(report))
        self.assertIn("time_reversal", {finding.code for finding in report.findings})

    def test_impossible_soc_and_temperature_are_rejected(self) -> None:
        frame = valid_frame()
        frame.loc[0, "soc"] = 1.2
        frame.loc[1, "temperature_c"] = 250.0
        report = profile_battery_table(frame, SCHEMA)
        codes = {finding.code for finding in report.findings}
        self.assertFalse(admit(report))
        self.assertTrue({"soc_out_of_range", "temperature_out_of_range"}.issubset(codes))

    def test_missing_cell_id_is_rejected(self) -> None:
        frame = valid_frame()
        frame.loc[0, "cell_id"] = None
        report = profile_battery_table(frame, SCHEMA)
        self.assertFalse(admit(report))
        self.assertIn("missing_group_id", {finding.code for finding in report.findings})

    def test_future_derived_feature_is_rejected(self) -> None:
        frame = valid_frame().assign(future_capacity=[1, 1, 1, 1, 1])
        schema = BatteryTableSchema(
            group_columns=SCHEMA.group_columns,
            time_column=SCHEMA.time_column,
            target_columns=SCHEMA.target_columns,
            target_provenance=SCHEMA.target_provenance,
            feature_provenance={"future_capacity": "future_cycle_capacity"},
        )
        report = profile_battery_table(frame, schema)
        self.assertFalse(admit(report))
        self.assertIn("future_derived_feature", {finding.code for finding in report.findings})

    def test_reports_are_written_as_json_and_markdown(self) -> None:
        report = profile_battery_table(valid_frame(), SCHEMA)
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = write_quality_report(report, Path(temp_dir), "sample")
            payload = json.loads(paths["json"].read_text(encoding="utf-8"))
            self.assertEqual(payload["row_count"], 5)
            self.assertIn("ADMITTED", paths["markdown"].read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
