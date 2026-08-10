from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.custom_training.dataset import CustomDatasetConfig
from src.platform.platform_core import PlatformStore
from src.training.train_custom import _require_generalization, main


class CustomCliAdmissionTests(unittest.TestCase):
    def test_strict_generalization_never_degrades_to_time_only(self) -> None:
        with self.assertRaisesRegex(ValueError, "strict grouped"):
            _require_generalization(False, "unseen_cell_and_condition")

    def _project(self, root: Path):
        source = root / "source.csv"
        source.write_text(
            "time,cell,condition,session,cycle,voltage,soc\n"
            + "\n".join(
                f"{index},c{index % 4},k{index % 2},s{index % 4},{index},3.7,0.8"
                for index in range(40)
            ),
            encoding="utf-8",
        )
        store = PlatformStore(root / "store")
        project = store.create_custom_project(
            "cli",
            CustomDatasetConfig(
                source,
                None,
                "time",
                ("voltage",),
                ("soc",),
                "lstm",
                role_columns=(
                    ("cell_id", "cell"),
                    ("condition_id", "condition"),
                    ("session_id", "session"),
                    ("cycle_id", "cycle"),
                ),
            ),
            Path("src/training/train_custom.py"),
        )
        manifest = {
            "manifest_version": "cli-test-v1",
            "valid_for_training": True,
            "training_authorized": True,
            "targets": {"soc": {"causal_label_audit_passed": True}},
        }
        return store, project, manifest

    @staticmethod
    def _argv(store: PlatformStore, project, results: Path) -> list[str]:
        return [
            "train_custom",
            "--data",
            str(project.data_path),
            "--results-dir",
            str(results),
            "--admission-registry",
            str(store.registry_path),
            "--project-id",
            project.project_id,
            "--features",
            "voltage",
            "--targets",
            "soc",
            "--algorithm",
            "lstm",
        ]

    def test_cli_requires_capability_before_calling_training(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data = root / "cell.csv"
            data.write_text("voltage,soc\n3.7,0.8\n", encoding="utf-8")
            results = root / "results"
            argv = [
                "train_custom",
                "--data",
                str(data),
                "--results-dir",
                str(results),
                "--features",
                "voltage",
                "--targets",
                "soc",
            ]

            with patch.object(sys, "argv", argv), patch(
                "src.training.train_custom.run_training"
            ) as run_training:
                with self.assertRaises(SystemExit):
                    main()

            run_training.assert_not_called()
            self.assertFalse(results.exists())

    def test_cli_rejects_boolean_only_capability_before_training(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store, project, _ = self._project(root)
            store._replace_record(project.project_id, custom_admission={"training_allowed": True})
            results = root / "results"

            with patch.object(sys, "argv", self._argv(store, project, results)), patch(
                "src.training.train_custom.run_training"
            ) as run_training:
                with self.assertRaises(SystemExit):
                    main()

            run_training.assert_not_called()
            self.assertFalse(results.exists())

    def test_cli_verified_capability_reaches_only_the_mocked_training_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store, project, manifest = self._project(root)
            store.record_custom_training_capability(
                project,
                manifest=manifest,
                approved_by="chief-engineer-test",
                approved_at="2026-08-04T12:00:00+08:00",
            )
            results = root / "results"

            with patch.object(sys, "argv", self._argv(store, project, results)), patch(
                "src.training.train_custom.run_training"
            ) as run_training:
                main()

            run_training.assert_called_once()
            self.assertFalse(results.exists())


if __name__ == "__main__":
    unittest.main()
