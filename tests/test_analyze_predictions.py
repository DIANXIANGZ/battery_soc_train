from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from src.evaluation.analyze_predictions import analyze_predictions, write_analysis


class AnalyzePredictionsTests(unittest.TestCase):
    def test_reports_each_soc_band(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            predictions = Path(temp_dir) / "predictions.csv"
            with predictions.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(["reference_soc", "predicted_soc"])
                writer.writerows([
                    (0.10, 0.11), (0.30, 0.31), (0.50, 0.51),
                    (0.70, 0.71), (0.90, 0.91),
                ])

            report = analyze_predictions(predictions)

            self.assertEqual(1, report["0-20%"]["count"])
            self.assertAlmostEqual(1.0, report["0-20%"]["MAE_pct"], places=6)
            self.assertEqual(1, report["80-100%"]["count"])

    def test_empty_band_uses_json_safe_null_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            predictions = Path(temp_dir) / "predictions.csv"
            output = Path(temp_dir) / "metrics_by_soc.json"
            predictions.write_text(
                "reference_soc,predicted_soc\n0.1,0.11\n", encoding="utf-8"
            )

            report = write_analysis(predictions, output)

            self.assertEqual(0, report["20-40%"]["count"])
            self.assertIsNone(report["20-40%"]["MAE_pct"])
            self.assertIsNone(report["20-40%"]["bias_pct"])
            self.assertTrue(output.is_file())


if __name__ == "__main__":
    unittest.main()
