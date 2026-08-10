from __future__ import annotations

import unittest


class ChartViewerTests(unittest.TestCase):
    def test_scale_is_clamped_to_the_confirmed_range(self) -> None:
        from src.desktop.chart_viewer import clamp_scale

        self.assertEqual(clamp_scale(0.2), 0.8)
        self.assertEqual(clamp_scale(1.25), 1.25)
        self.assertEqual(clamp_scale(4.0), 3.0)

    def test_mouse_wheel_step_is_ten_percent(self) -> None:
        from src.desktop.chart_viewer import next_scale

        self.assertEqual(next_scale(1.0, 1), 1.1)
        self.assertEqual(next_scale(1.0, -1), 0.9)


if __name__ == "__main__":
    unittest.main()
