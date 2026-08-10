from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.data_processing import inspect_external_data


class InspectExternalDataTests(unittest.TestCase):
    def test_inventory_records_extensions_and_text_header(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "cx2"
            root.mkdir()
            (root / "record.txt").write_text("Time\tVoltage\tCurrent\n0\t3.7\t0.1\n", encoding="utf-8")
            output = Path(temp_dir) / "inventory.json"
            summary = inspect_external_data.write_inventory(root, output)
            saved = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(1, summary["file_count"])
        self.assertEqual(1, summary["extensions"][".txt"])
        self.assertEqual("Time\tVoltage\tCurrent", saved["text_previews"]["record.txt"][0])

    def test_inventory_handles_a_chartsheet_without_tabular_rows(self) -> None:
        class ChartSheet:
            title = "Plot"

        self.assertEqual([], inspect_external_data._sheet_header(ChartSheet()))


if __name__ == "__main__":
    unittest.main()
