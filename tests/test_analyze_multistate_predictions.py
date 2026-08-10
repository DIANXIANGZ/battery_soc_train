from __future__ import annotations

import unittest

from src.evaluation.analyze_multistate_predictions import summarize_target_errors


class AnalyzeMultiStatePredictionTests(unittest.TestCase):
    def test_summarize_target_errors_uses_cycles_for_rul(self) -> None:
        rows = [
            {"reference_rul_cycles": "10", "predicted_rul_cycles": "8"},
            {"reference_rul_cycles": "4", "predicted_rul_cycles": "5"},
        ]

        summary = summarize_target_errors(rows, "rul_cycles")

        self.assertEqual(summary["unit"], "cycles")
        self.assertEqual(summary["n_test"], 2)
        self.assertAlmostEqual(summary["MAE"], 1.5)
        self.assertAlmostEqual(summary["RMSE"], (2.5) ** 0.5)


if __name__ == "__main__":
    unittest.main()
