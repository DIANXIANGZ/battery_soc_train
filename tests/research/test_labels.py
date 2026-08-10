from __future__ import annotations

import unittest

from src.research.labels import CapacityPoint, CurrentPoint, offline_cycle_range_labels, online_coulomb_labels


class LabelTests(unittest.TestCase):
    def test_offline_cycle_range_matches_reference_definition(self):
        points = tuple(CapacityPoint("A", "c", "s", "1", i, value) for i, value in enumerate((0.0, 0.5, 1.0)))
        labels = offline_cycle_range_labels(points)
        self.assertEqual([0.0, 0.5, 1.0], [x.soc for x in labels])
        self.assertTrue(all(x.label_method == "offline_cycle_range" for x in labels))

    def test_online_uses_past_current_and_fixed_capacity(self):
        points = tuple(CurrentPoint("A", "c", "s", "1", t, a) for t, a in ((0, 0), (3600, 1), (7200, 1)))
        labels = online_coulomb_labels(points, 0.2, 2.0)
        self.assertEqual([0.2, 0.45, 0.95], [round(x.soc, 6) for x in labels])

    def test_online_rejects_boundary_change_and_nonpositive_capacity(self):
        mixed = (CurrentPoint("A", "c1", "s", "1", 0, 0), CurrentPoint("A", "c2", "s", "1", 1, 0))
        with self.assertRaisesRegex(ValueError, "single boundary"):
            online_coulomb_labels(mixed, 0.5, 2.0)
        with self.assertRaisesRegex(ValueError, "positive"):
            online_coulomb_labels(mixed[:1], 0.5, 0.0)

    def test_future_current_cannot_change_past_online_labels(self):
        base = (CurrentPoint("A", "c", "s", "1", 0, 0), CurrentPoint("A", "c", "s", "1", 10, 1), CurrentPoint("A", "c", "s", "1", 20, 1))
        changed = base[:-1] + (CurrentPoint("A", "c", "s", "1", 20, 100),)
        self.assertEqual(online_coulomb_labels(base, .5, 2)[:2], online_coulomb_labels(changed, .5, 2)[:2])

if __name__ == "__main__": unittest.main()
