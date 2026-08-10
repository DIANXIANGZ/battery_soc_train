from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from src.desktop.training_controller import TrainingController, epoch_progress, hidden_process_options, smooth_progress_step


def wait_until(predicate, timeout_s: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


class TrainingControllerTests(unittest.TestCase):
    def test_blocked_admission_never_starts_a_subprocess(self) -> None:
        controller = TrainingController()

        with patch("src.desktop.training_controller.subprocess.Popen") as popen:
            with self.assertRaisesRegex(ValueError, "数据准入门禁"):
                controller.start(
                    [sys.executable, "-c", "print('must not run')"],
                    Path("unused-run"),
                    Path.cwd(),
                    admission={"training_allowed": False},
                )

        popen.assert_not_called()

    def test_custom_script_path_without_admission_never_starts_a_subprocess(self) -> None:
        controller = TrainingController()
        command = [sys.executable, "src/training/train_custom.py", "--data", "cell.csv"]

        with patch("src.desktop.training_controller.threading.Thread"), patch(
            "src.desktop.training_controller.subprocess.Popen"
        ) as popen:
            with self.assertRaisesRegex(ValueError, "数据准入门禁"):
                controller.start(command, Path("unused-run"), Path.cwd())

        popen.assert_not_called()

    def test_custom_module_rejects_boolean_only_admission(self) -> None:
        controller = TrainingController()
        command = [sys.executable, "-m", "src.training.train_custom", "--data", "cell.csv"]

        with patch("src.desktop.training_controller.threading.Thread"), patch(
            "src.desktop.training_controller.subprocess.Popen"
        ) as popen:
            with self.assertRaisesRegex(ValueError, "数据准入门禁"):
                controller.start(
                    command,
                    Path("unused-run"),
                    Path.cwd(),
                    admission={"training_allowed": True},
                )

        popen.assert_not_called()
    def test_windows_training_process_is_hidden(self) -> None:
        import subprocess

        expected_flag = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        self.assertEqual(hidden_process_options("win32"), {"creationflags": expected_flag})
        self.assertEqual(hidden_process_options("linux"), {})

    def test_epoch_log_line_maps_to_bounded_percentage(self) -> None:
        self.assertEqual(epoch_progress("epoch 10 training_mse=0.01", 40), 25)
        self.assertEqual(epoch_progress("epoch 50 training_mse=0.01", 40), 100)
        self.assertIsNone(epoch_progress("preparing data", 40))

    def test_smooth_progress_step_moves_forward_without_overshooting(self) -> None:
        first = smooth_progress_step(0.0, 25.0)

        self.assertGreater(first, 0.0)
        self.assertLess(first, 25.0)
        self.assertEqual(smooth_progress_step(24.9, 25.0), 25.0)
        self.assertEqual(smooth_progress_step(40.0, 25.0), 25.0)

    def test_controller_reports_completed_command_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "run"
            run_dir.mkdir()
            controller = TrainingController()

            controller.start([sys.executable, "-c", "print('epoch 1')"], run_dir, Path(temp_dir))

            self.assertTrue(wait_until(lambda: controller.status() != "running"))
            self.assertEqual(controller.status(), "succeeded")
            self.assertIn("epoch 1", "".join(controller.poll()))
            self.assertIn("returncode=0", (run_dir / "run.log").read_text(encoding="utf-8"))

    def test_controller_rejects_a_second_running_training(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "run"
            run_dir.mkdir()
            controller = TrainingController()
            controller.start([sys.executable, "-c", "import time; time.sleep(0.2)"], run_dir, Path(temp_dir))

            with self.assertRaisesRegex(RuntimeError, "already running"):
                controller.start([sys.executable, "-c", "print('second')"], run_dir, Path(temp_dir))

            self.assertTrue(wait_until(lambda: controller.status() != "running"))


if __name__ == "__main__":
    unittest.main()
