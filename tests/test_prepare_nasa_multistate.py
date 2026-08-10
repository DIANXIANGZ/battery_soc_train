from __future__ import annotations

import unittest

from src.data_processing.prepare_nasa_multistate import derive_cycle_labels, fixed_cell_split


class PrepareNasaMultistateTests(unittest.TestCase):
    def test_cycle_labels_use_initial_capacity_energy_and_eol_cycle(self) -> None:
        labels = derive_cycle_labels(
            capacity_ah=1.8,
            initial_capacity_ah=2.0,
            remaining_energy_wh=2.7,
            initial_energy_wh=3.0,
            cycle_index=10,
            eol_cycle_index=50,
        )

        self.assertAlmostEqual(labels["soh"], 0.9)
        self.assertAlmostEqual(labels["soe"], 0.9)
        self.assertEqual(labels["rul_cycles"], 40)

    def test_fixed_cell_split_keeps_cells_independent(self) -> None:
        split = fixed_cell_split(["B0018", "B0007", "B0006", "B0005"])

        self.assertEqual(split["train"], ["B0005", "B0006"])
        self.assertEqual(split["validation"], ["B0007"])
        self.assertEqual(split["test"], ["B0018"])
        self.assertFalse(set(split["train"]) & set(split["test"]))

    def test_fixed_cell_split_rejects_missing_required_cell(self) -> None:
        with self.assertRaisesRegex(ValueError, "Expected exactly"):
            fixed_cell_split(["B0005", "B0006", "B0007"])


if __name__ == "__main__":
    unittest.main()
