from __future__ import annotations

import unittest
from pathlib import Path

from src.research.protocol import DatasetRegistration
from src.research.quality import assess_compatibility, profile_records
from src.research.schema import parse_record


def record(timestamp: float, *, temperature=25.0, cell="c1", soc=0.5):
    return parse_record({
        "dataset_id": "A123#3", "cell_id": cell, "session_id": "s1",
        "cycle_id": "1", "timestamp_s": timestamp, "voltage_v": 3.2,
        "current_a": -1.0, "temperature_c": temperature, "capacity_ah": 1.0,
        "soh": 0.9, "soc_reference": soc, "label_method": "offline_cycle_range",
        "split_role": "development", "source_file": "a.csv",
    })


class QualityTests(unittest.TestCase):
    def test_profile_reports_rates_duplicates_time_reversal_and_coverage(self) -> None:
        first = record(0)
        records = [first, record(30, temperature=None), first, record(20, cell="c2")]

        report = profile_records(records)

        self.assertEqual(4, report.row_count)
        self.assertEqual(0.25, report.missing_temperature_rate)
        self.assertEqual(1, report.duplicate_key_count)
        self.assertEqual(1, report.time_reversal_count)
        self.assertEqual(("A123#3",), report.dataset_ids)
        self.assertEqual(2, report.distinct_cell_count)

    def test_profile_rejects_empty_input(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one"):
            profile_records([])

    def test_other_chemistry_is_compatibility_only(self) -> None:
        cx2 = DatasetRegistration("CX2_4", "LCO", "compatibility_audit", Path("x"), "source_defined")
        status = assess_compatibility(cx2, profile_records([record(0)]), target_chemistry="LFP")
        self.assertEqual("compatibility_only_chemistry_mismatch", status)

    def test_missing_soc_label_is_not_primary_experiment_eligible(self) -> None:
        source = DatasetRegistration("A", "LFP", "development", Path("x"), "unknown")
        status = assess_compatibility(source, profile_records([record(0, soc=None)]), "LFP")
        self.assertEqual("compatibility_only_missing_soc_label", status)


if __name__ == "__main__":
    unittest.main()
