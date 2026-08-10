from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from src.evaluation.v10_strict_smoke import (
    audit_soh_domain_residuals,
    causal_physics_prediction,
    rul_source_frames,
)


class V10StrictSmokeTests(unittest.TestCase):
    def test_physics_baseline_is_exact_and_future_tail_does_not_change_prefix(self) -> None:
        frame = pd.DataFrame({
            "cumulative_charge_ah": [0.0, 0.25, 0.5],
            "previous_capacity_ah": [1.0, 1.0, 1.0],
            "cumulative_energy_wh": [0.0, 1.0, 2.0],
            "previous_energy_wh": [4.0, 4.0, 4.0],
            "soc": [1.0, 0.75, 0.5],
            "soe": [1.0, 0.75, 0.5],
        })
        changed_tail = frame.copy()
        changed_tail.loc[2, ["cumulative_charge_ah", "cumulative_energy_wh", "soc", "soe"]] = [1.0, 4.0, 0.0, 0.0]
        for target in ("soc", "soe"):
            prediction = causal_physics_prediction(frame, target)
            changed = causal_physics_prediction(changed_tail, target)
            self.assertTrue(np.allclose(prediction, frame[target]))
            self.assertEqual(float((np.abs(prediction - frame[target]) <= 0.01).mean()), 1.0)
            self.assertTrue(np.allclose(prediction[:2], changed[:2]))

    def test_rul_sources_are_separate_and_never_return_a_combined_frame(self) -> None:
        frame = pd.DataFrame({
            "source_id": ["mit_stanford_fast_charge"] * 2 + ["oxford_battery_degradation_1"] * 2,
            "rul_cycles": [10.0, 9.0, 100.0, 0.0],
        })
        result = rul_source_frames(frame)
        self.assertEqual(set(result), {"mit_stanford_fast_charge", "oxford_battery_degradation_1"})
        self.assertTrue(all(part["source_id"].nunique() == 1 for part in result.values()))
        self.assertNotIn("combined", result)

    def test_soh_residuals_are_layered_by_unseen_strategy_and_train_cycle_range(self) -> None:
        experiment = pd.DataFrame({
            "condition_id": ["seen", "seen", "unseen", "seen"],
            "cycle_id": [0.0, 10.0, 20.0, 30.0],
        })
        predictions = pd.DataFrame({
            "target": ["soh", "soh"],
            "fold_id": ["outer-01", "outer-01"],
            "row_index": [2, 3],
            "absolute_error": [0.10, 0.02],
        })
        splits = {"folds": [{
            "target": "soh",
            "fold_id": "outer-01",
            "test_condition": "unseen",
            "train_rows": [0, 1],
            "test_rows": [2, 3],
        }]}
        result = audit_soh_domain_residuals(predictions, experiment, splits)
        self.assertEqual(set(result["unseen_strategy"]), {True, False})
        unseen = result[result["unseen_strategy"]]
        self.assertEqual(unseen["cycle_range"].tolist(), ["above_train_range"])
        self.assertEqual(unseen["sample_count"].tolist(), [1])
        self.assertEqual(unseen["mae"].tolist(), [0.10])


if __name__ == "__main__":
    unittest.main()
