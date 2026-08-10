"""Contract tests for the lightweight Windows installer."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]


class InstallerPackagingTests(unittest.TestCase):
    def test_desktop_entrypoint_uses_installed_root_when_frozen(self) -> None:
        source = (PROJECT / "src" / "desktop" / "app.py").read_text(encoding="utf-8")

        self.assertIn('getattr(sys, "frozen", False)', source)
        self.assertIn("Path(sys.executable).resolve().parent", source)

    def test_runtime_bootstrap_is_private_logged_and_verified(self) -> None:
        source = (PROJECT / "installer" / "setup_runtime.ps1").read_text(encoding="utf-8")

        self.assertIn("param(", source)
        self.assertIn("[string]$InstallRoot", source)
        self.assertIn("[string]$PythonPackage", source)
        self.assertIn("ExtractToDirectory", source)
        self.assertIn('"tools"', source)
        self.assertIn('runtime\\python', source)
        self.assertIn('logs\\install-runtime.log', source)
        self.assertIn('"-m", "ensurepip"', source)
        self.assertIn('"-m", "pip"', source)
        self.assertIn('"-m", "src.training.verify_pytorch"', source)
        self.assertIn("Start-Process", source)
        self.assertIn("RedirectStandardError", source)
        self.assertIn("[Console]::Error.WriteLine", source)
        self.assertNotIn("Write-Error", source)
        self.assertNotRegex(source, r"(?im)^\s*(py|pip)(\.exe)?\s")
        self.assertNotIn("SOC电池数据中心", source)

    def test_installer_requirements_match_runtime_requirements(self) -> None:
        expected = {
            line.strip()
            for line in (PROJECT / "requirements.txt").read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
        actual = {
            line.strip()
            for line in (PROJECT / "installer" / "installer_requirements.txt").read_text(encoding="utf-8").splitlines()
            if line.strip()
        }

        self.assertEqual(actual, expected)

    def test_inno_manifest_is_safe_portable_and_exactly_named(self) -> None:
        source = (PROJECT / "installer" / "SOCTrainingLab.iss").read_text(encoding="utf-8")

        for fragment in (
            "PrivilegesRequired=lowest",
            "ArchitecturesAllowed=x64compatible",
            "OutputBaseFilename=SOC电池训练平台安装程序",
            "setup_runtime.ps1",
            "ewWaitUntilTerminated",
            "SW_HIDE",
            "RaiseException",
            "SOC电池训练平台.exe",
            "{autodesktop}",
            "{group}",
            "[UninstallDelete]",
        ):
            self.assertIn(fragment, source)
        self.assertIn('Name: "desktopicon"', source)
        self.assertIn('Name: "{app}\\configs"', source)
        self.assertIn('Excludes: "__pycache__\\*;*.pyc"', source)
        self.assertIn('Name: "{app}\\src"', source.split("[UninstallDelete]", 1)[1])
        self.assertNotIn("configs\\paths.json", source)
        self.assertNotIn("SOC电池数据中心", source)
        uninstall_section = source.split("[UninstallDelete]", 1)[1]
        self.assertNotRegex(uninstall_section, r"(?i)E:\\|data_center|数据中心")

    def test_build_script_pins_and_verifies_official_python(self) -> None:
        source = (PROJECT / "scripts" / "build_installer.ps1").read_text(encoding="utf-8")

        self.assertIn("https://www.nuget.org/api/v2/package/python/3.12.10", source)
        self.assertIn("0EB85C2DFCCCCF1B17352DE4C397F69194035B7D37149EACC16F1147D93DE3B8", source)
        self.assertIn("JRSoftware.InnoSetup", source)
        self.assertIn("ISCC.exe", source)
        self.assertIn("PyInstaller", source)
        self.assertIn("--exclude-module", source)
        self.assertIn("@($isccCandidates)[0]", source)
        self.assertIn("Get-FileHash", source)
        self.assertIn("U09D55S15rGg6K6t57uD5bmz5Y+w5a6J6KOF56iL5bqPLmV4ZQ==", source)
        self.assertNotIn('"/FSOC', source)


if __name__ == "__main__":
    unittest.main()
