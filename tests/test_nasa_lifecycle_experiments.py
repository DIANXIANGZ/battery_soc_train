from __future__ import annotations

import unittest

from src.evaluation.nasa_lifecycle_experiments import aggregate_folds, comparison_summary, result_dir_name


class NasaLifecycleExperimentsTests(unittest.TestCase):
    def test_non_default_seed_uses_a_distinct_results_directory(self) -> None:
        self.assertEqual(result_dir_name("formal", 42), "formal")
        self.assertEqual(result_dir_name("formal", 7), "formal_seed_7")
        self.assertEqual(result_dir_name("smoke", 8), "smoke_seed_8")

    def test_aggregate_requires_all_four_successful_folds(self) -> None:
        with self.assertRaises(ValueError):
            aggregate_folds([{"fold": "test_RW9"}, {"fold": "test_RW10"}])

    def test_comparison_marks_no_improvement_when_model_loses_to_baseline(self) -> None:
        report = comparison_summary(model_mae=0.10, baseline_mae=0.08)

        self.assertFalse(report["improved"])


if __name__ == "__main__":
    unittest.main()
