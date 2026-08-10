from __future__ import annotations

import unittest

from src.research.schema import SampleKey, parse_record, validate_record


class ResearchSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.valid_mapping = {
            "dataset_id": "A123#3",
            "cell_id": "cell-3",
            "session_id": "run-1",
            "cycle_id": "cycle-7",
            "timestamp_s": "30.0",
            "voltage_v": "3.25",
            "current_a": "-1.5",
            "temperature_c": "25.0",
            "capacity_ah": "1.1",
            "soh": "0.95",
            "soc_reference": "0.7",
            "label_method": "offline_cycle_range",
            "split_role": "development",
            "source_file": "raw/a.xlsx",
        }

    def test_valid_record_preserves_traceability_key(self) -> None:
        record = parse_record(self.valid_mapping)

        self.assertEqual(
            SampleKey("A123#3", "cell-3", "run-1", "cycle-7", 30.0),
            record.key,
        )
        self.assertEqual((), validate_record(record))

    def test_optional_numeric_fields_accept_empty_values(self) -> None:
        mapping = self.valid_mapping | {
            "temperature_c": "",
            "capacity_ah": None,
            "soh": " ",
            "soc_reference": "",
        }

        record = parse_record(mapping)

        self.assertIsNone(record.temperature_c)
        self.assertIsNone(record.capacity_ah)
        self.assertIsNone(record.soh)
        self.assertIsNone(record.soc_reference)

    def test_invalid_voltage_soc_and_identity_are_all_reported(self) -> None:
        bad = self.valid_mapping | {
            "cell_id": "",
            "voltage_v": 9.0,
            "soc_reference": 1.2,
        }

        errors = validate_record(parse_record(bad))

        self.assertTrue(any("cell_id" in item for item in errors))
        self.assertTrue(any("voltage_v" in item for item in errors))
        self.assertTrue(any("soc_reference" in item for item in errors))

    def test_missing_required_numeric_field_names_the_field(self) -> None:
        mapping = dict(self.valid_mapping)
        del mapping["current_a"]

        with self.assertRaisesRegex(ValueError, "current_a"):
            parse_record(mapping)


if __name__ == "__main__":
    unittest.main()
