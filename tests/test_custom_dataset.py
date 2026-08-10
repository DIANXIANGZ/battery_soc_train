from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from src.custom_training.dataset import (
    SUPPORTED_SUFFIXES,
    CustomDatasetConfig,
    list_sheet_names,
    validate_and_export,
)


class CustomDatasetTests(unittest.TestCase):
    def test_csv_mapping_exports_only_time_features_and_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "cell.csv"
            with source.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=("time", "voltage", "current", "soc", "note"))
                writer.writeheader()
                writer.writerows(
                    {"time": index, "voltage": 3.7, "current": 1.0, "soc": 0.8, "note": "ignored"}
                    for index in range(40)
                )
            output = root / "custom_training.csv"
            config = CustomDatasetConfig(source, None, "time", ("voltage", "current"), ("soc",), "lstm")

            result = validate_and_export(config, output, minimum_rows=30)

            self.assertEqual(result["row_count"], 40)
            self.assertEqual(output.read_text(encoding="utf-8").splitlines()[0], "time,voltage,current,soc")

    def test_xlsx_exposes_sheet_names_and_xls_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workbook_path = Path(temp_dir) / "cell.xlsx"
            workbook = Workbook()
            workbook.active.title = "cycles"
            workbook.create_sheet("labels")
            workbook.save(workbook_path)

            self.assertEqual(list_sheet_names(workbook_path), ("cycles", "labels"))
            self.assertIn(".xls", SUPPORTED_SUFFIXES)

    def test_non_numeric_target_names_the_invalid_column(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "bad.csv"
            source.write_text("voltage,soc\n3.7,unknown\n", encoding="utf-8")
            config = CustomDatasetConfig(source, None, None, ("voltage",), ("soc",), "lstm")

            with self.assertRaisesRegex(ValueError, "soc.*数值"):
                validate_and_export(config, root / "out.csv", minimum_rows=1)

    def test_metadata_roles_are_renamed_and_not_numeric_cast(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "cells.csv"
            with source.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=("cell", "condition", "cycle", "observed", "provenance", "v", "i", "rul"),
                )
                writer.writeheader()
                writer.writerows(
                    {
                        "cell": "A",
                        "condition": "cold",
                        "cycle": index,
                        "observed": 1,
                        "provenance": "official_continuation",
                        "v": 3.7,
                        "i": 1.0,
                        "rul": 40 - index,
                    }
                    for index in range(30)
                )
            output = root / "out.csv"
            config = CustomDatasetConfig(
                source,
                None,
                None,
                ("v", "i"),
                ("rul",),
                "xgboost",
                role_columns=(
                    ("cell_id", "cell"),
                    ("condition_id", "condition"),
                    ("cycle_id", "cycle"),
                    ("rul_observed", "observed"),
                    ("eol_provenance", "provenance"),
                ),
            )

            validate_and_export(config, output)

            lines = output.read_text(encoding="utf-8").splitlines()
            self.assertEqual(
                lines[0],
                "cell_id,condition_id,cycle_id,rul_observed,eol_provenance,v,i,rul",
            )
            self.assertIn("A,cold,0,1,official_continuation", lines[1])


if __name__ == "__main__":
    unittest.main()
