from __future__ import annotations

import unittest
import csv
import tempfile
from pathlib import Path

import numpy as np
import torch

from src.training.train_nasa_state import (
    compose_future_temperature,
    make_state_sequences,
    persistence_mae,
    temperature_features,
    run_state_fold,
)
from src.evaluation.nasa_loco import LocoFold


class TrainNasaStateTests(unittest.TestCase):
    def test_state_sequences_do_not_cross_cycle_or_cell_boundaries(self) -> None:
        rows = [
            {"cell_id": "RW9", "cycle_id": 0, "voltage_v": 3.7, "current_a": -1.0, "temperature_c": 20.0, "dv_dt_v_s": 0.0, "soc": 1.0, "soe": 1.0, "sot_5min_c": 21.0},
            {"cell_id": "RW9", "cycle_id": 0, "voltage_v": 3.6, "current_a": -1.0, "temperature_c": 21.0, "dv_dt_v_s": 0.0, "soc": 0.9, "soe": 0.9, "sot_5min_c": 22.0},
            {"cell_id": "RW9", "cycle_id": 0, "voltage_v": 3.5, "current_a": -1.0, "temperature_c": 22.0, "dv_dt_v_s": 0.0, "soc": 0.8, "soe": 0.8, "sot_5min_c": 24.0},
            {"cell_id": "RW10", "cycle_id": 0, "voltage_v": 3.7, "current_a": -1.0, "temperature_c": 20.0, "dv_dt_v_s": 0.0, "soc": 1.0, "soe": 1.0, "sot_5min_c": 25.0},
        ]
        features, targets = make_state_sequences(rows, window=2)

        self.assertEqual(features.shape[0], 2)
        self.assertEqual(targets["sot_5min_c"].tolist(), [22.0, 24.0])

    def test_future_sot_persistence_baseline_uses_last_input_temperature(self) -> None:
        self.assertEqual(persistence_mae(np.array([20.0, 22.0]), np.array([21.0, 24.0])), 1.5)

    def test_temperature_prediction_adds_delta_to_last_observation(self) -> None:
        prediction = compose_future_temperature(
            torch.tensor([20.0, 25.0]), torch.tensor([0.5, -1.0])
        )

        self.assertTrue(torch.equal(prediction, torch.tensor([20.5, 24.0])))

    def test_temperature_features_are_derived_from_history_window(self) -> None:
        block = np.array(
            [[3.7, -1.0, 20.0, 0.0], [3.6, -2.0, 21.0, -0.1]], dtype=np.float32
        )

        values = temperature_features(block)

        self.assertEqual(values.shape, (2, 7))
        self.assertAlmostEqual(float(values[-1, 4]), -7.2, places=5)
        self.assertAlmostEqual(float(values[-1, 5]), 1.0)
        self.assertAlmostEqual(float(values[-1, 6]), 1.0)

    def test_state_fold_writes_separate_electrical_and_temperature_artifacts(self) -> None:
        fields = (
            "cell_id", "cycle_id", "voltage_v", "current_a", "temperature_c", "dv_dt_v_s",
            "soc", "soe", "sot_5min_c",
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data_path = root / "state.csv"
            with data_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                for cell_offset, cell in enumerate(("RW9", "RW10", "RW11", "RW12")):
                    for index in range(6):
                        temperature = 20.0 + cell_offset + index * 0.2
                        writer.writerow({
                            "cell_id": cell, "cycle_id": 0, "voltage_v": 3.8 - index * 0.02,
                            "current_a": -1.0, "temperature_c": temperature, "dv_dt_v_s": -0.01,
                            "soc": 1.0 - index * 0.1, "soe": 1.0 - index * 0.09,
                            "sot_5min_c": temperature + 0.5,
                        })
            fold = LocoFold("test_RW12", ("RW9", "RW10"), "RW11", "RW12")

            run_state_fold(data_path, fold, root / "result", window=2, epochs=1, seed=7)

            for relative in (
                "state/metrics_by_target.json", "state/test_predictions.csv", "state/training_history.json",
                "temperature/metrics_by_target.json", "temperature/test_predictions.csv",
                "temperature/persistence_metrics.json", "temperature/training_history.json",
            ):
                self.assertTrue((root / "result" / relative).is_file(), relative)


if __name__ == "__main__":
    unittest.main()
