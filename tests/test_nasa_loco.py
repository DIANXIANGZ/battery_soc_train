from __future__ import annotations

import unittest

from src.evaluation.nasa_loco import LocoFold, assert_no_fold_leakage, make_loco_folds


class NasaLocoTests(unittest.TestCase):
    def test_loco_folds_hold_out_each_cell_once(self) -> None:
        folds = make_loco_folds(("RW9", "RW10", "RW11", "RW12"))

        self.assertEqual({fold.test_cell for fold in folds}, {"RW9", "RW10", "RW11", "RW12"})
        self.assertTrue(all(len(fold.train_cells) == 2 for fold in folds))

    def test_overlap_is_rejected(self) -> None:
        fold = LocoFold("bad", ("RW9", "RW10"), "RW11", "RW10")

        with self.assertRaises(ValueError):
            assert_no_fold_leakage(fold)


if __name__ == "__main__":
    unittest.main()
