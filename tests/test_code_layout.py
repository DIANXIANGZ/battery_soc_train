from __future__ import annotations

import unittest
from pathlib import Path
import subprocess
import sys


class CodeLayoutTests(unittest.TestCase):
    def test_desktop_launchers_do_not_reference_streamlit_or_localhost(self) -> None:
        project = Path(__file__).resolve().parents[1]
        init_text = (project / "scripts" / "初始化环境.bat").read_text(encoding="utf-8")
        launch_text = (project / "scripts" / "启动训练平台.bat").read_text(encoding="utf-8")

        self.assertIn('-m venv "%PROJECT_ROOT%\\..\\..\\work\\soc_venv"', init_text)
        self.assertIn('work\\soc_venv\\Scripts\\python.exe', init_text)
        self.assertIn('work\\soc_venv\\Scripts\\python.exe" -m src.desktop.app', launch_text)
        self.assertNotIn("streamlit", init_text.lower() + launch_text.lower())
        self.assertNotIn("localhost", init_text.lower() + launch_text.lower())
        self.assertFalse((project / "scripts" / "launch_platform.bat").exists())

    def test_training_module_is_importable_from_the_src_package(self) -> None:
        from src.training import train_lstm

        self.assertTrue(callable(train_lstm.main))

    def test_external_evaluator_imports_training_interfaces_from_the_package(self) -> None:
        from src.evaluation import evaluate_external_cell

        self.assertTrue(callable(evaluate_external_cell.evaluate_csv))

    def test_platform_module_is_importable_without_running_streamlit(self) -> None:
        from src.platform import platform_core

        self.assertTrue(callable(platform_core.build_soc_command))

    def test_pycharm_run_configurations_reference_moved_source_files(self) -> None:
        project = Path(__file__).resolve().parents[1]
        combine = (project / ".run" / "Combine Samples.run.xml").read_text(encoding="utf-8")
        training = (project / ".run" / "Train LSTM.run.xml").read_text(encoding="utf-8")

        self.assertIn('name="SCRIPT_NAME" value="$PROJECT_DIR$/src/data_processing/combine_samples.py"', combine)
        self.assertIn('name="SCRIPT_NAME" value="$PROJECT_DIR$/src/training/train_lstm.py"', training)
        self.assertIn('name="MODULE_MODE" value="false"', combine)
        self.assertIn('name="MODULE_MODE" value="false"', training)

    def test_training_script_can_start_directly_from_pycharm(self) -> None:
        project = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, str(project / "src" / "training" / "train_lstm.py"), "--help"],
            cwd=project,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
