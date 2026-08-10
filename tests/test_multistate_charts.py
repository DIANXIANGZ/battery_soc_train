from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from src.desktop.multistate_charts import build_multistate_charts


class MultiStateChartTests(unittest.TestCase):
    def test_build_multistate_charts_writes_one_png_per_target(self) -> None:
        targets = ("soc", "soh", "soe", "rul_cycles", "sot_c")
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            fieldnames = [item for target in targets for item in (f"reference_{target}", f"predicted_{target}")]
            with (run_dir / "test_predictions.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerow({name: "1" for name in fieldnames})
                writer.writerow({name: "0.8" for name in fieldnames})
            (run_dir / "metrics_by_target.json").write_text(json.dumps({target: {"MAE": 0.1, "RMSE": 0.2, "unit": "fraction"} for target in targets}), encoding="utf-8")

            charts = build_multistate_charts(run_dir)

            self.assertEqual(set(charts), set(targets))
            self.assertTrue(all(path.is_file() for path in charts.values()))
            with Image.open(charts["rul_cycles"]) as image:
                self.assertEqual(image.format, "PNG")


if __name__ == "__main__":
    unittest.main()
