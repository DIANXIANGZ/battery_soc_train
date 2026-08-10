from __future__ import annotations

import unittest
from pathlib import Path


class DesktopThemeTests(unittest.TestCase):
    def test_theme_uses_the_confirmed_blue_green_system_palette(self) -> None:
        from src.desktop.theme import COLORS

        self.assertEqual(COLORS["canvas"], "#E8F4F4")
        self.assertEqual(COLORS["sidebar"], "#103B53")
        self.assertEqual(COLORS["accent"], "#19A974")
        self.assertEqual(COLORS["selection"], "#1F7AE0")

    def test_sidebar_readability_uses_12_point_text_and_236_pixel_width(self) -> None:
        project = Path(__file__).resolve().parents[1]
        theme_source = (project / "src" / "desktop" / "theme.py").read_text(encoding="utf-8")
        app_source = (project / "src" / "desktop" / "app.py").read_text(encoding="utf-8")

        self.assertIn('font=(FONT, 12)', theme_source)
        self.assertIn('width=236', app_source)

    def test_training_progress_uses_the_success_green_style(self) -> None:
        project = Path(__file__).resolve().parents[1]
        theme_source = (project / "src" / "desktop" / "theme.py").read_text(encoding="utf-8")

        self.assertIn('"Training.Horizontal.TProgressbar"', theme_source)
        self.assertIn('background=COLORS["success"]', theme_source)


if __name__ == "__main__":
    unittest.main()
