from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from src.evaluation.nasa_loco import LocoFold
from src.training.train_nasa_lifecycle import RulTrajectoryEstimator, run_lifecycle_fold


class TrainNasaLifecycleTests(unittest.TestCase):
    @staticmethod
    def _trajectory_rows(cell: str, sohs: list[float], rul_start: int) -> list[dict[str, object]]:
        return [
            {"cell_id": cell, "cycle_index": index, "soh": soh, "rul_cycles": rul_start - index}
            for index, soh in enumerate(sohs)
        ]

    def test_rul_trajectory_can_exceed_training_label_maximum(self) -> None:
        training = self._trajectory_rows("RW9", [1.0, 0.96, 0.92, 0.88], 5)
        training += self._trajectory_rows("RW10", [1.0, 0.95, 0.90, 0.85], 5)
        test = self._trajectory_rows("RW12", [1.0, 0.995, 0.99], 50)
        estimator = RulTrajectoryEstimator(eol_soh=0.70).fit(training)

        prediction = estimator.predict(test)

        self.assertGreater(float(prediction[0]["rul_cycles"]), 5.0)

    def test_rul_prediction_for_cycle_is_unchanged_by_future_test_rows(self) -> None:
        training = self._trajectory_rows("RW9", [1.0, 0.96, 0.92, 0.88], 5)
        training += self._trajectory_rows("RW10", [1.0, 0.95, 0.90, 0.85], 5)
        test = self._trajectory_rows("RW12", [1.0, 0.98, 0.96, 0.94, 0.92], 20)
        estimator = RulTrajectoryEstimator(eol_soh=0.70).fit(training)

        prefix = estimator.predict(test[:3])[-1]["rul_cycles"]
        extended = estimator.predict(test)[2]["rul_cycles"]

        self.assertAlmostEqual(float(prefix), float(extended))

    def test_lifecycle_fold_uses_only_train_cells_for_fit(self) -> None:
        fields = ("cell_id", "cycle_id", "cycle_index", "cumulative_throughput_ah", "capacity_ah", "soh_history_mean", "capacity_drop_ah", "capacity_slope_3", "voltage_mean_v", "voltage_std_v", "temperature_mean_c", "temperature_max_c", "discharge_duration_s", "soh", "rul_cycles")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            csv_path = root / "cycles.csv"
            with csv_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                for cell_index, cell in enumerate(("RW9", "RW10", "RW11", "RW12")):
                    for cycle in range(3):
                        capacity = 2.0 - 0.05 * cycle - 0.02 * cell_index
                        writer.writerow({"cell_id": cell, "cycle_id": cycle, "cycle_index": cycle, "cumulative_throughput_ah": 2.0 * (cycle + 1), "capacity_ah": capacity, "soh_history_mean": 1.0 - 0.02 * cycle, "capacity_drop_ah": 0.05 * cycle, "capacity_slope_3": -0.05, "voltage_mean_v": 3.7, "voltage_std_v": 0.1, "temperature_mean_c": 25.0, "temperature_max_c": 26.0, "discharge_duration_s": 1000.0, "soh": capacity / 2.0, "rul_cycles": 2 - cycle})
            fold = LocoFold("test_RW12", ("RW9", "RW10"), "RW11", "RW12")
            result = run_lifecycle_fold(csv_path, fold, root / "result")

            self.assertEqual(result["train_cells"], ["RW9", "RW10"])
            self.assertEqual(result["test_cell"], "RW12")
            self.assertTrue((root / "result" / "baseline_metrics.json").is_file())


if __name__ == "__main__":
    unittest.main()
