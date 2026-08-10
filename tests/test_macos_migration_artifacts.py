from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class MacOSMigrationArtifactTests(unittest.TestCase):
    def test_setup_script_requires_explicit_absolute_data_root(self) -> None:
        text = (ROOT / "scripts" / "macos_setup.sh").read_text(encoding="utf-8")
        self.assertIn("--data-root is required", text)
        self.assertIn('[[ "$DATA_ROOT" = /* ]]', text)
        self.assertIn("DataCenterPaths.save_config", text)

    def test_verification_is_non_training_and_runs_the_suite(self) -> None:
        text = (ROOT / "scripts" / "macos_verify.sh").read_text(encoding="utf-8")
        self.assertIn("unittest discover", text)
        self.assertNotIn("src.training.train_", text)

    def test_export_omits_windows_virtual_environment(self) -> None:
        text = (ROOT / "scripts" / "export_macos_bundle.ps1").read_text(encoding="utf-8")
        self.assertIn("battery_soc_project_macos_source.zip", text)
        self.assertIn("-Encoding utf8", text)
        self.assertIn("__pycache__", text)
        self.assertNotIn(".venv", text)

    def test_export_creates_posix_named_zip_entries(self) -> None:
        text = (ROOT / "scripts" / "export_macos_bundle.ps1").read_text(encoding="utf-8")
        self.assertIn("Add-Type -AssemblyName System.IO.Compression\n", text)
        self.assertIn("System.IO.Compression.ZipArchive", text)
        self.assertIn(".Replace('\\', '/')", text)
