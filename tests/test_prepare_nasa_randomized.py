from __future__ import annotations

import unittest

import numpy as np

from src.data_processing.prepare_nasa_randomized import capacity_ah, randomized_cell_split


class PrepareNasaRandomizedTests(unittest.TestCase):
    def test_reference_capacity_integrates_current_over_time(self) -> None:
        capacity = capacity_ah(np.array([1.0, 1.0, 1.0]), np.array([0.0, 1800.0, 3600.0]))

        self.assertAlmostEqual(capacity, 1.0)

    def test_randomized_cell_split_is_independent(self) -> None:
        split = randomized_cell_split(["RW12", "RW10", "RW9", "RW11"])

        self.assertEqual(split, {"train": ["RW9", "RW10"], "validation": ["RW11"], "test": ["RW12"]})


if __name__ == "__main__":
    unittest.main()
