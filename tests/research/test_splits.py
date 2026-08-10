from __future__ import annotations
import unittest
from tests.research.test_leakage import row
from src.research.leakage import assert_disjoint_domains
from src.research.splits import leave_one_cell_out, leave_one_dataset_out

class SplitTests(unittest.TestCase):
    def setUp(self):
        self.rows=[row(d,f"{d}-{c}",0) for d in "ABC" for c in "123"]
    def test_lodo_tests_each_dataset_once_without_overlap(self):
        folds=leave_one_dataset_out(self.rows)
        self.assertEqual(set("ABC"),{x.test_domain for x in folds})
        for fold in folds: assert_disjoint_domains(fold.train,fold.validation,fold.test)
    def test_loco_is_deterministic_and_tests_each_cell_once(self):
        first=leave_one_cell_out(self.rows); second=leave_one_cell_out(reversed(self.rows))
        self.assertEqual(first,second)
        self.assertEqual({f"{d}-{c}" for d in "ABC" for c in "123"},{x.test_domain for x in first})
    def test_insufficient_domains_are_rejected(self):
        with self.assertRaisesRegex(ValueError,"at least three"):
            leave_one_dataset_out([row("A","1",0),row("B","2",0)])
if __name__=="__main__": unittest.main()
