from __future__ import annotations

import plistlib
import tempfile
import unittest
import base64
from pathlib import Path
from unittest.mock import patch

from scripts.install_macos_launcher import (
    BUNDLE_ID,
    BUNDLE_NAME,
    build_bundle,
    install_bundle,
    resolve_python,
)


class MacOSLauncherTests(unittest.TestCase):
    def _fixture_project(self, root: Path) -> tuple[Path, Path]:
        project = root / "project"
        (project / "src" / "desktop").mkdir(parents=True)
        (project / "src" / "desktop" / "app.py").write_text("# fixture\n", encoding="utf-8")
        summary = project / "docs" / "audits" / "2026-09-23-non-rul-four-target-completion.json"
        summary.parent.mkdir(parents=True)
        summary.write_text(
            '{"status":"COMPLETE_FOUR_TARGET_SCOPED_BASELINES",'
            '"targets":{"soc":{},"system_soe":{},"soh":{},"sot":{}}}',
            encoding="utf-8",
        )
        icon = root / "icon.png"
        icon.write_bytes(base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        ))
        return project, icon

    def test_build_bundle_creates_gui_bundle_metadata_and_launcher(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project, icon = self._fixture_project(root)
            bundle = build_bundle(project, root / BUNDLE_NAME, icon, Path("/opt/homebrew/bin/python3.12"))

            info = plistlib.loads((bundle / "Contents" / "Info.plist").read_bytes())
            self.assertEqual(info["CFBundleIdentifier"], BUNDLE_ID)
            self.assertEqual(info["CFBundleExecutable"], "SOCTrainingPlatformLauncher")
            self.assertTrue((bundle / "Contents" / "Resources" / "SOCTrainingPlatformIcon.icns").is_file())
            self.assertFalse((bundle / "Contents" / "Resources" / "SOCTrainingPlatformIcon.iconset").exists())
            launcher = bundle / "Contents" / "MacOS" / "SOCTrainingPlatformLauncher"
            self.assertTrue(launcher.stat().st_mode & 0o111)
            text = launcher.read_text(encoding="utf-8")
            self.assertIn("python3.12", text)
            self.assertIn("src.desktop.app", text)
            self.assertIn('"$HOME/Library/Logs/SOCBatteryTrainingPlatform"', text)
            self.assertIn('LOG_FILE="$LOG_DIR/launcher.log"', text)
            self.assertLess(text.index('cd "$PROJECT_ROOT"'), text.index('import sys; assert sys.version_info'))

    def test_install_is_idempotent_and_rejects_different_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project, icon = self._fixture_project(root)
            desktop = root / "Desktop"
            first = install_bundle(project, desktop, icon, Path("/opt/homebrew/bin/python3.12"))
            first_marker = first / "Contents" / "marker"
            first_marker.write_text("old", encoding="utf-8")
            second = install_bundle(project, desktop, icon, Path("/opt/homebrew/bin/python3.12"))
            self.assertEqual(second, first)
            self.assertFalse(first_marker.exists())

            info = second / "Contents" / "Info.plist"
            payload = plistlib.loads(info.read_bytes())
            payload["CFBundleIdentifier"] = "com.example.other"
            info.write_bytes(plistlib.dumps(payload))
            with self.assertRaisesRegex(RuntimeError, "bundle id"):
                install_bundle(project, desktop, icon, Path("/opt/homebrew/bin/python3.12"))

    def test_install_rejects_symlink_and_unusable_explicit_python(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project, icon = self._fixture_project(root)
            desktop = root / "Desktop"
            desktop.mkdir()
            target = root / "other.app"
            target.mkdir()
            (target / "Contents").mkdir()
            (target / "Contents" / "Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": BUNDLE_ID}))
            (desktop / BUNDLE_NAME).symlink_to(target, target_is_directory=True)
            with self.assertRaisesRegex(RuntimeError, "可识别的app bundle"):
                install_bundle(project, desktop, icon, Path("/opt/homebrew/bin/python3.12"))

        with tempfile.TemporaryDirectory() as temp_dir, patch("scripts.install_macos_launcher._python_is_usable", return_value=False):
            root = Path(temp_dir)
            project, icon = self._fixture_project(root)
            with self.assertRaisesRegex(RuntimeError, "预检失败"):
                install_bundle(project, root / "Desktop", icon, Path("/opt/homebrew/bin/python3.12"))

    def test_project_root_and_icon_are_required(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with self.assertRaisesRegex(RuntimeError, "app.py"):
                build_bundle(root, root / BUNDLE_NAME, root / "missing.png", Path("/opt/homebrew/bin/python3.12"))

    def test_resolve_python_prefers_homebrew_and_validates_version(self) -> None:
        with patch("scripts.install_macos_launcher._python_is_usable", side_effect=lambda path, _root: path == Path("/opt/homebrew/bin/python3.12")):
            self.assertEqual(resolve_python((Path("/opt/homebrew/bin/python3.12"), Path("/usr/bin/python3"))), Path("/opt/homebrew/bin/python3.12").resolve())
        with patch("scripts.install_macos_launcher._python_is_usable", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "Python 3.12"):
                resolve_python((Path("/usr/bin/python3"),))


if __name__ == "__main__":
    unittest.main()
