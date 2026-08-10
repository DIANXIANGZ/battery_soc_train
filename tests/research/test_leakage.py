from __future__ import annotations
import unittest
from src.research.leakage import WindowSpec, assert_disjoint_domains, assert_statistics_provenance, assert_window_boundaries, fit_training_statistics
from src.research.schema import parse_record

def row(dataset, cell, time, voltage=3.2):
    return parse_record({"dataset_id":dataset,"cell_id":cell,"session_id":"s","cycle_id":"1","timestamp_s":time,"voltage_v":voltage,"current_a":1,"temperature_c":25,"capacity_ah":1,"soh":.9,"soc_reference":.5,"label_method":"x","split_role":"x","source_file":"x"})

class LeakageTests(unittest.TestCase):
    def test_window_crossing_cells_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "window crosses"):
            assert_window_boundaries([row("A","c1",0),row("A","c2",1)], [WindowSpec(0,2)])
    def test_cell_overlap_is_rejected(self):
        shared=row("A","c",0)
        with self.assertRaisesRegex(ValueError, "cell overlap"):
            assert_disjoint_domains([shared], [row("A","v",0)], [shared])
    def test_statistics_provenance_rejects_test_rows(self):
        train=[row("A","c1",0)]; test=[row("B","c2",0)]
        stats=fit_training_statistics(train+test)
        with self.assertRaisesRegex(ValueError, "outside training domain"):
            assert_statistics_provenance(stats,{x.key for x in train})
if __name__=="__main__": unittest.main()
