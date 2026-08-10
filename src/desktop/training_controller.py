"""Non-blocking subprocess control for desktop training runs."""

from __future__ import annotations

import queue
import re
import subprocess
import sys
import threading
from pathlib import Path

from src.custom_training.capability import verify_registry_capability


def _command_value(command: list[str], option: str) -> str:
    index = command.index(option) + 1
    if index >= len(command) or command[index].startswith("--"):
        raise ValueError(f"missing command option: {option}")
    return command[index]


def _command_values(command: list[str], option: str) -> tuple[str, ...]:
    index = command.index(option) + 1
    values: list[str] = []
    while index < len(command) and not command[index].startswith("--"):
        values.append(command[index])
        index += 1
    if not values:
        raise ValueError(f"missing command option: {option}")
    return tuple(values)


def hidden_process_options(platform_name: str) -> dict[str, int]:
    """Return subprocess flags that suppress a child console on Windows."""
    if platform_name == "win32":
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)}
    return {}


def epoch_progress(line: str, total_epochs: int) -> int | None:
    """Convert one training epoch log line into a bounded percentage."""
    match = re.match(r"^\s*epoch\s+(\d+)\b", line)
    if match is None or total_epochs <= 0:
        return None
    return min(100, max(0, int(int(match.group(1)) * 100 / total_epochs)))


def smooth_progress_step(current: float, target: float) -> float:
    """Move a displayed percentage smoothly toward its real target."""
    current = min(100.0, max(0.0, float(current)))
    target = min(100.0, max(0.0, float(target)))
    if target <= current or target - current <= 0.25:
        return target
    return min(target, current + max(0.5, (target - current) * 0.18))


class TrainingController:
    def __init__(self) -> None:
        self._lines: queue.Queue[str] = queue.Queue()
        self._status = "idle"
        self._process: subprocess.Popen[str] | None = None

    def start(
        self,
        command: list[str],
        run_dir: Path,
        cwd: Path,
        *,
        admission: dict[str, object] | None = None,
    ) -> None:
        is_custom_training = "src.training.train_custom" in command or any(
            Path(part).name == "train_custom.py" for part in command
        )
        admission_is_blocked = admission is not None and (
            not isinstance(admission, dict) or admission.get("training_allowed") is not True
        )
        admission_is_missing = is_custom_training and admission is None
        if admission_is_blocked or admission_is_missing:
            raise ValueError("自定义训练仍被数据准入门禁阻塞。")
        if is_custom_training:
            try:
                verified = verify_registry_capability(
                    Path(_command_value(command, "--admission-registry")),
                    _command_value(command, "--project-id"),
                    Path(_command_value(command, "--data")),
                    algorithm=_command_value(command, "--algorithm"),
                    features=_command_values(command, "--features"),
                    targets=_command_values(command, "--targets"),
                )
                if not isinstance(admission, dict) or (
                    admission.get("capability_digest") != verified.get("capability_digest")
                ):
                    raise ValueError("controller capability does not match")
            except (KeyError, OSError, TypeError, ValueError):
                raise ValueError("自定义训练仍被数据准入门禁阻塞。")
        if self._status == "running":
            raise RuntimeError("Training is already running.")
        self._status = "running"
        self._lines = queue.Queue()
        self._process = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            **hidden_process_options(sys.platform),
        )
        threading.Thread(target=self._collect_output, args=(run_dir,), daemon=True).start()

    def _collect_output(self, run_dir: Path) -> None:
        assert self._process is not None
        output: list[str] = []
        assert self._process.stdout is not None
        for line in self._process.stdout:
            output.append(line)
            self._lines.put(line)
        self._process.stdout.close()
        returncode = self._process.wait()
        (run_dir / "run.log").write_text(
            f"returncode={returncode}\n\nOUTPUT\n{''.join(output)}",
            encoding="utf-8",
        )
        self._status = "succeeded" if returncode == 0 else "failed"

    def poll(self) -> list[str]:
        lines: list[str] = []
        while True:
            try:
                lines.append(self._lines.get_nowait())
            except queue.Empty:
                return lines

    def status(self) -> str:
        return self._status
