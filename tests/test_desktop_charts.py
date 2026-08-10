from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image


class DesktopChartTests(unittest.TestCase):
    def test_ensure_run_charts_writes_prediction_and_validation_pngs(self) -> None:
        from src.desktop.charts import ensure_run_charts

        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            (run_dir / "metrics.json").write_text(
                json.dumps({"MAE_pct": 2.19, "RMSE_pct": 3.36}), encoding="utf-8"
            )
            (run_dir / "training_history.json").write_text(
                json.dumps([
                    {"epoch": 1, "training_mse": 0.08, "validation_mse": 0.06, "learning_rate": 3e-4},
                    {"epoch": 2, "training_mse": 0.05, "validation_mse": 0.04, "learning_rate": 3e-4},
                    {"epoch": 3, "training_mse": 0.02, "validation_mse": 0.03, "learning_rate": 1.5e-4},
                ]),
                encoding="utf-8",
            )
            with (run_dir / "test_predictions.csv").open("w", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow(["reference_soc", "predicted_soc"])
                writer.writerows([(0.9, 0.88), (0.6, 0.63), (0.2, 0.25)])

            paths = ensure_run_charts(run_dir)

            self.assertTrue(paths["prediction"].is_file())
            self.assertTrue(paths["validation_loss"].is_file())
            self.assertGreater(paths["prediction"].stat().st_size, 1000)
            self.assertGreater(paths["validation_loss"].stat().st_size, 1000)
            colors = set(Image.open(paths["validation_loss"]).get_flattened_data())
            self.assertIn((25, 103, 210), colors)
            self.assertIn((124, 58, 237), colors)

    def test_ensure_run_charts_skips_missing_inputs(self) -> None:
        from src.desktop.charts import ensure_run_charts

        with tempfile.TemporaryDirectory() as temp_dir:
            self.assertEqual(ensure_run_charts(Path(temp_dir)), {})


if __name__ == "__main__":
    unittest.main()
