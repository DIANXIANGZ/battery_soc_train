from __future__ import annotations

import unittest

from src.training.train_nasa_hybrid import aggregate_target_metrics, parse_args


class TrainNasaHybridTests(unittest.TestCase):
    def test_aggregate_reports_macro_mean_worst_fold_and_baseline(self) -> None:
        metrics = {
            "test_RW9": {"MAE": 1.0, "RMSE": 1.2},
            "test_RW10": {"MAE": 2.0, "RMSE": 2.2},
            "test_RW11": {"MAE": 3.0, "RMSE": 3.2},
            "test_RW12": {"MAE": 4.0, "RMSE": 4.2},
        }
        baselines = {fold: {"MAE": 5.0} for fold in metrics}

        result = aggregate_target_metrics(metrics, baselines)

        self.assertEqual(result["fold_count"], 4)
        self.assertEqual(result["mean_MAE"], 2.5)
        self.assertEqual(result["worst_fold"], "test_RW12")
        self.assertTrue(result["beats_baseline"])

    def test_hybrid_cli_requires_explicit_results_directory(self) -> None:
        with self.assertRaises(SystemExit):
            parse_args(["--state-data", "state.csv", "--lifecycle-data", "cycles.csv", "--stage", "smoke"])


if __name__ == "__main__":
    unittest.main()
