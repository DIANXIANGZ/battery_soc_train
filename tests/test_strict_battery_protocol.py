from __future__ import annotations

import unittest

import numpy as np
from sklearn.preprocessing import StandardScaler

from src.training.battery_protocol import (
    audit_split,
    fit_transform_train_only,
    nested_group_folds,
    target_acceptance,
    validate_windows,
)


class StrictBatteryProtocolTests(unittest.TestCase):
    def test_outer_folds_hold_out_cells_and_conditions(self) -> None:
        groups = np.array(["c1", "c1", "c2", "c2", "c3", "c3", "c4", "c4"])
        conditions = np.array(["cold", "warm"] * 4)
        folds = nested_group_folds(groups, conditions, seed=7)
        self.assertGreaterEqual(len(folds), 3)
        for fold in folds:
            train_groups = set(groups[fold.train_indices])
            train_conditions = set(conditions[fold.train_indices])
            self.assertNotIn(fold.test_group, train_groups)
            self.assertNotIn(fold.test_condition, train_conditions)
            self.assertTrue(set(fold.train_indices).isdisjoint(fold.test_indices))
            self.assertTrue(set(fold.validation_indices).isdisjoint(fold.test_indices))
            self.assertTrue(audit_split(groups, conditions, fold).passed)

    def test_preprocessor_is_fitted_on_training_values_only(self) -> None:
        train = np.array([[0.0], [2.0]])
        validation = np.array([[4.0]])
        test_a = np.array([[100.0]])
        test_b = np.array([[100000.0]])
        transformed_a = fit_transform_train_only(StandardScaler(), train, validation, test_a)
        transformed_b = fit_transform_train_only(StandardScaler(), train, validation, test_b)
        self.assertAlmostEqual(float(transformed_a.fitted.mean_[0]), 1.0)
        self.assertAlmostEqual(float(transformed_b.fitted.mean_[0]), 1.0)
        np.testing.assert_allclose(transformed_a.train, transformed_b.train)
        np.testing.assert_allclose(transformed_a.validation, transformed_b.validation)

    def test_windows_must_not_cross_group_boundaries(self) -> None:
        groups = np.array(["c1/s1/1", "c1/s1/1", "c1/s1/2"])
        validate_windows(groups, [(0, 2)])
        with self.assertRaisesRegex(ValueError, "boundary"):
            validate_windows(groups, [(1, 3)])

    def test_percentage_target_requires_mae_and_95_percent_coverage(self) -> None:
        reference = np.ones(100)
        prediction = reference.copy()
        prediction[:5] += 0.01
        result = target_acceptance("soc", reference, prediction)
        self.assertTrue(result["passed"])
        self.assertGreaterEqual(result["coverage"], 0.95)
        prediction[:6] += 0.02
        self.assertFalse(target_acceptance("soh", reference, prediction)["passed"])

    def test_rul_requires_one_cycle_mae_and_coverage(self) -> None:
        reference = np.arange(20, dtype=float)
        prediction = reference + 1.0
        result = target_acceptance("rul", reference, prediction)
        self.assertTrue(result["passed"])
        prediction[0] += 1.1
        self.assertFalse(target_acceptance("rul_cycles", reference, prediction)["passed"])

    def test_sot_uses_per_sample_relative_threshold(self) -> None:
        reference = np.array([10.0, 20.0, 30.0, 40.0])
        prediction = np.array([11.0, 22.0, 33.0, 44.0])
        result = target_acceptance("sot", reference, prediction, minimum_coverage=1.0)
        self.assertTrue(result["passed"])
        prediction[0] = 11.01
        self.assertFalse(target_acceptance("sot", reference, prediction, minimum_coverage=1.0)["passed"])


if __name__ == "__main__":
    unittest.main()
