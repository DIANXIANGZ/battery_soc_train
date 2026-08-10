from __future__ import annotations

import unittest

import numpy as np

from src.data_processing.prepare_nasa_lifecycle import (
    CycleSummary,
    first_future_temperature,
    make_lifecycle_rows,
    validate_future_temperature_rows,
)


class PrepareNasaLifecycleTests(unittest.TestCase):
    def test_future_temperature_uses_a_later_sample(self) -> None:
        future = first_future_temperature(
            np.array([0.0, 100.0, 300.0]), np.array([20.0, 21.0, 23.0]), 0, 300.0
        )

        self.assertEqual(future, 23.0)
        self.assertNotEqual(future, 20.0)

    def test_future_temperature_uses_first_sample_at_or_after_horizon(self) -> None:
        future = first_future_temperature(
            np.array([0.0, 299.0, 301.0]), np.array([20.0, 21.0, 22.0]), 0, 300.0
        )

        self.assertEqual(future, 22.0)

    def test_future_temperature_contract_rejects_current_temperature_identity(self) -> None:
        rows = [{"time_s": 0.0, "temperature_c": 20.0, "sot_5min_c": 20.0}]

        with self.assertRaisesRegex(ValueError, "current temperature"):
            validate_future_temperature_rows(rows, horizon_s=300.0)

    def test_future_temperature_contract_accepts_actual_future_labels(self) -> None:
        rows = [
            {"time_s": 0.0, "temperature_c": 20.0, "sot_5min_c": 20.5},
            {"time_s": 10.0, "temperature_c": 20.1, "sot_5min_c": 20.6},
        ]

        result = validate_future_temperature_rows(rows, horizon_s=300.0)

        self.assertEqual(result["row_count"], 2)
        self.assertEqual(result["identity_count"], 0)

    def test_lifecycle_features_never_use_later_cycles(self) -> None:
        rows = make_lifecycle_rows(
            [
                CycleSummary("RW9", 0, 2.0, 3.7, 0.1, 25.0, 26.0, 1000.0, 20),
                CycleSummary("RW9", 1, 1.8, 3.6, 0.1, 25.0, 26.0, 1000.0, 19),
            ]
        )

        self.assertEqual(rows[0]["capacity_slope_3"], 0.0)
        self.assertGreater(rows[1]["cumulative_throughput_ah"], rows[0]["cumulative_throughput_ah"])
        self.assertAlmostEqual(rows[0]["soh_history_mean"], 1.0)
        self.assertAlmostEqual(rows[1]["soh_history_mean"], 1.0)


if __name__ == "__main__":
    unittest.main()
