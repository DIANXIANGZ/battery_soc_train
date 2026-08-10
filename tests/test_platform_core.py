"""Tests for the local multi-project training platform core."""

from __future__ import annotations

import tempfile
import unittest
import json
from pathlib import Path

from src.custom_training.dataset import CustomDatasetConfig
from src.platform.platform_core import PlatformStore, build_custom_command, build_hybrid_command, build_lifecycle_command, build_multistate_command, build_soc_command, latest_complete_run_result, read_generalization_summary, read_nasa_lifecycle_result, read_run_result, resolve_training_python, summarize_csv


PROJECT = Path(__file__).resolve().parents[1]


class PlatformStoreTests(unittest.TestCase):
    def _make_admissible_custom_project(self, root: Path):
        root.mkdir(parents=True, exist_ok=True)
        source = root / "admissible.csv"
        source.write_text(
            "time,cell,condition,session,cycle,observed,provenance,voltage,current,soc,rul\n"
            + "\n".join(
                f"{index},cell-{index % 4},condition-{index % 2},session-{index % 4},{index},1,observed_eol_crossing,3.7,1.0,0.8,{80-index}"
                for index in range(40)
            ),
            encoding="utf-8",
        )
        store = PlatformStore(root / "store")
        config = CustomDatasetConfig(
            source,
            None,
            "time",
            ("voltage", "current"),
            ("soc", "rul"),
            "transformer",
            role_columns=(
                ("cell_id", "cell"),
                ("condition_id", "condition"),
                ("session_id", "session"),
                ("cycle_id", "cycle"),
                ("rul_observed", "observed"),
                ("eol_provenance", "provenance"),
            ),
        )
        project = store.create_custom_project(
            "admissible", config, PROJECT / "src" / "training" / "train_custom.py"
        )
        manifest = {
            "manifest_version": "test-v1",
            "valid_for_training": True,
            "training_authorized": True,
            "targets": {
                "soc": {"causal_label_audit_passed": True},
                "rul": {"causal_label_audit_passed": True},
            },
            "rul": {
                "exact_observed_cells": 8,
                "grid_cycles": 1,
                "task": "point",
                "censored_rows_are_exact_supervision": False,
            },
        }
        return store, project, manifest

    def test_boolean_only_custom_admission_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store, project, _ = self._make_admissible_custom_project(Path(temp_dir))
            store._replace_record(project.project_id, custom_admission={"training_allowed": True})
            before = tuple((project.path / "runs").iterdir())

            with self.assertRaisesRegex(ValueError, "数据准入门禁"):
                build_custom_command(project, {}, Path("/python"))

            self.assertEqual(tuple((project.path / "runs").iterdir()), before)
            self.assertFalse(store.custom_admission_for(project)["training_allowed"])

    def test_capability_is_bound_to_configuration_and_exported_data(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store, project, manifest = self._make_admissible_custom_project(root)
            store.record_custom_training_capability(
                project,
                manifest=manifest,
                approved_by="chief-engineer-test",
                approved_at="2026-08-04T12:00:00+08:00",
            )
            self.assertTrue(store.require_custom_training_admission(project)["training_allowed"])

            config = store.custom_config_for(project)
            store._replace_record(project.project_id, custom_config={**config, "target_columns": ["soc"]})
            with self.assertRaisesRegex(ValueError, "数据准入门禁"):
                store.require_custom_training_admission(project)

    def test_capability_rejects_role_and_manifest_tampering(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store, project, manifest = self._make_admissible_custom_project(root)
            capability = store.record_custom_training_capability(
                project,
                manifest=manifest,
                approved_by="chief-engineer-test",
                approved_at="2026-08-04T12:00:00+08:00",
            )
            config = store.custom_config_for(project)
            store._replace_record(
                project.project_id,
                custom_config={**config, "role_columns": config["role_columns"][:-1]},
            )
            with self.assertRaisesRegex(ValueError, "数据准入门禁"):
                store.require_custom_training_admission(project)

    def test_capability_requires_declared_roles_to_exist_in_exported_headers(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store, project, manifest = self._make_admissible_custom_project(root)
            data_path = Path(project.data_path)
            text = data_path.read_text(encoding="utf-8")
            data_path.write_text(text.replace("cell_id,", "missing_cell_id,", 1), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "role columns"):
                store.record_custom_training_capability(
                    project,
                    manifest=manifest,
                    approved_by="chief-engineer-test",
                    approved_at="2026-08-04T12:00:00+08:00",
                )

            store, project, manifest = self._make_admissible_custom_project(root / "manifest")
            capability = store.record_custom_training_capability(
                project,
                manifest=manifest,
                approved_by="chief-engineer-test",
                approved_at="2026-08-04T12:00:00+08:00",
            )
            tampered = json.loads(json.dumps(capability))
            tampered["manifest"]["manifest_version"] = "tampered"
            store._replace_record(project.project_id, custom_admission=tampered)
            with self.assertRaisesRegex(ValueError, "数据准入门禁"):
                store.require_custom_training_admission(project)

            store, project, manifest = self._make_admissible_custom_project(root / "second")
            store.record_custom_training_capability(
                project,
                manifest=manifest,
                approved_by="chief-engineer-test",
                approved_at="2026-08-04T12:00:00+08:00",
            )
            Path(project.data_path).write_text(
                Path(project.data_path).read_text(encoding="utf-8") + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "数据准入门禁"):
                store.require_custom_training_admission(project)
    def test_algorithm_update_persists_and_invalidates_admission(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.csv"
            source.write_text(
                "time,voltage,current,soc\n"
                + "\n".join(f"{index},3.7,1.0,0.8" for index in range(40)),
                encoding="utf-8",
            )
            store = PlatformStore(root / "store")
            config = CustomDatasetConfig(
                source, None, "time", ("voltage", "current"), ("soc",), "lstm"
            )
            project = store.create_custom_project(
                "我的电芯", config, PROJECT / "src" / "training" / "train_custom.py"
            )

            record = store.update_custom_algorithm(project, "gru")

            self.assertEqual(record["custom_config"]["algorithm"], "gru")
            self.assertFalse(record["custom_admission"]["training_allowed"])
            self.assertIn("configuration_changed", record["custom_admission"]["blockers"])
    def test_custom_project_persists_mapping_and_builds_fixed_command(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store, project, manifest = self._make_admissible_custom_project(root)
            store.record_custom_training_capability(
                project,
                manifest=manifest,
                approved_by="chief-engineer-test",
                approved_at="2026-08-04T12:00:00+08:00",
            )
            command, run_dir = build_custom_command(project, {"window": 12, "epochs": 2, "seed": 7}, Path("/python"))

            self.assertEqual(project.name, "admissible")
            self.assertTrue(Path(project.data_path).is_file())
            self.assertIn("-m", command)
            self.assertIn("src.training.train_custom", command)
            self.assertEqual(command[command.index("--algorithm") + 1], "transformer")
            self.assertEqual(command[command.index("--targets") + 1:command.index("--targets") + 3], ["soc", "rul"])
            self.assertEqual(
                command[command.index("--admission-registry") + 1],
                str(store.registry_path),
            )
            self.assertEqual(command[command.index("--project-id") + 1], project.project_id)
            self.assertEqual(run_dir.parent, project.path / "runs")

    def test_blocked_custom_command_creates_no_run_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.csv"
            source.write_text(
                "time,voltage,current,soc\n"
                + "\n".join(f"{index},3.7,1.0,0.8" for index in range(40)),
                encoding="utf-8",
            )
            store = PlatformStore(root / "store")
            project = store.create_custom_project(
                "blocked",
                CustomDatasetConfig(source, None, "time", ("voltage", "current"), ("soc",), "gru"),
                PROJECT / "src" / "training" / "train_custom.py",
            )
            runs = project.path / "runs"
            before = tuple(runs.iterdir())

            with self.assertRaisesRegex(ValueError, "数据准入门禁"):
                build_custom_command(project, {}, Path("/python"))

            self.assertEqual(tuple(runs.iterdir()), before)

    def test_hybrid_command_passes_platform_run_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = PlatformStore(root / "store")
            lifecycle = root / "nasa_lifecycle_cycles.csv"
            lifecycle.touch()
            project = store.ensure_nasa_hybrid_project(Path("train_nasa_hybrid.py"), lifecycle)

            command, run_dir = build_hybrid_command(project, {"stage": "smoke", "seed": 7}, Path("python"))

            self.assertEqual(project.name, "NASA 五状态（改进）")
            self.assertIn("src.training.train_nasa_hybrid", command)
            self.assertEqual(command[command.index("--results-dir") + 1], str(run_dir))
            self.assertEqual(command[command.index("--state-data") + 1], str(lifecycle.with_name("nasa_state_future_samples.csv").resolve()))
    def test_store_creates_independent_lifecycle_project_and_command(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = PlatformStore(Path(temp_dir))
            project = store.ensure_nasa_lifecycle_project(
                Path("nasa_lifecycle_experiments.py"), Path("nasa_lifecycle_cycles.csv")
            )

            command, run_dir = build_lifecycle_command(
                project, {"stage": "smoke", "seed": 42}, Path("python.exe")
            )

            self.assertEqual(project.name, "NASA 生命周期模型")
            self.assertEqual(command[1:3], ["-m", "src.evaluation.nasa_lifecycle_experiments"])
            self.assertEqual(command[command.index("--stage") + 1], "smoke")
            self.assertTrue(run_dir.is_dir())

    def test_lifecycle_reader_rejects_missing_baseline_hash(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            formal_dir = Path(temp_dir) / "formal"
            formal_dir.mkdir()
            (formal_dir / "aggregate_metrics.json").write_text("{}", encoding="utf-8")
            (formal_dir / "comparison_report.md").write_text("# report", encoding="utf-8")
            (formal_dir / "implementation_manifest.json").write_text("{}", encoding="utf-8")
            (formal_dir / "baseline_hashes_before.json").write_text("{}", encoding="utf-8")
            for cell in ("RW9", "RW10", "RW11", "RW12"):
                (formal_dir / f"test_{cell}").mkdir()

            with self.assertRaisesRegex(ValueError, "baseline_hashes_after"):
                read_nasa_lifecycle_result(formal_dir)
    def test_generalization_summary_reader_validates_required_fields(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "summary.json"
            path.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "seed_mean"):
                read_generalization_summary(path)
            path.write_text(
                json.dumps({
                    "seed_mean_MAE_pct": 2.8,
                    "loso_worst_MAE_pct": 5.1,
                    "A1235_MAE_pct": 2.2,
                    "decision": "preferred_target_met",
                }),
                encoding="utf-8",
            )
            summary = read_generalization_summary(path)
            self.assertEqual("preferred_target_met", summary["decision"])

    def test_installed_private_runtime_has_priority(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "outputs" / "SOCTrainingLab"
            installed = project_root / "runtime" / "python" / "python.exe"
            development = project_root.parent.parent / "work" / "soc_venv" / "Scripts" / "python.exe"
            installed.parent.mkdir(parents=True)
            development.parent.mkdir(parents=True)
            installed.touch()
            development.touch()

            self.assertEqual(resolve_training_python(project_root), installed.resolve())

    def test_latest_complete_run_result_requires_metrics_and_prediction_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runs_dir = Path(temp_dir) / "runs"
            older = runs_dir / "20260718-120000-old"
            newer = runs_dir / "20260718-130000-new"
            older.mkdir(parents=True)
            newer.mkdir()

            valid_metrics = {"MAE_pct": 2.1, "RMSE_pct": 3.2, "n_test": 20}
            (older / "metrics.json").write_text(json.dumps(valid_metrics), encoding="utf-8")
            (older / "test_predictions.csv").write_text(
                "reference_soc,predicted_soc\n0.8,0.79\n", encoding="utf-8"
            )
            (newer / "metrics.json").write_text(json.dumps(valid_metrics), encoding="utf-8")

            self.assertEqual(latest_complete_run_result(runs_dir).path, older)

            (older / "test_predictions.csv").write_text(
                "reference_soc,predicted_soc\n", encoding="utf-8"
            )
            self.assertIsNone(latest_complete_run_result(runs_dir))

            (older / "test_predictions.csv").write_text(
                "reference_soc,predicted_soc\n0.8,0.79\n", encoding="utf-8"
            )
            (older / "metrics.json").write_text("{not-json", encoding="utf-8")
            self.assertIsNone(latest_complete_run_result(runs_dir))

            (older / "metrics.json").write_text(
                json.dumps({"MAE_pct": 2.1, "RMSE_pct": 3.2}), encoding="utf-8"
            )
            self.assertIsNone(latest_complete_run_result(runs_dir))

            (newer / "test_predictions.csv").write_text(
                "reference_soc,predicted_soc\n0.7,0.71\n", encoding="utf-8"
            )
            self.assertEqual(latest_complete_run_result(runs_dir).path, newer)

    def test_latest_complete_run_result_accepts_complete_multistate_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "runs" / "nasa-five-state"
            run_dir.mkdir(parents=True)
            (run_dir / "metrics.json").write_text(json.dumps({"n_test": 12}), encoding="utf-8")
            (run_dir / "metrics_by_target.json").write_text(
                json.dumps({name: {"MAE": 0.1, "RMSE": 0.2, "n_test": 12} for name in ("soc", "soh", "soe", "rul_cycles", "sot_c")}),
                encoding="utf-8",
            )
            (run_dir / "test_predictions.csv").write_text("reference_soc,predicted_soc\n0.8,0.79\n", encoding="utf-8")

            result = latest_complete_run_result(run_dir.parent)

            self.assertIsNotNone(result)
            self.assertEqual(result.path, run_dir)

    def test_training_python_is_the_project_venv_not_the_web_runtime(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "outputs" / "battery_soc_project"
            expected = Path(temp_dir) / "work" / "soc_venv" / "Scripts" / "python.exe"
            expected.parent.mkdir(parents=True)
            expected.touch()

            self.assertEqual(resolve_training_python(root), expected.resolve())

    def test_training_python_uses_configured_macos_global_interpreter(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            root.mkdir()
            interpreter = Path(temp_dir) / "python3.12"
            interpreter.touch()
            self.assertEqual(resolve_training_python(root, global_python=interpreter), interpreter.resolve())

    def test_desktop_console_is_a_tkinter_application(self):
        source = (PROJECT / "src" / "desktop" / "app.py").read_text(encoding="utf-8")
        self.assertIn("class DesktopTrainingApp", source)
        self.assertNotIn("streamlit", source.lower())

    def test_archive_requires_exact_confirmation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = PlatformStore(Path(temp_dir))
            project = store.create_project("SOC", "train_lstm.py", "data/a.csv")
            dataset = project.path / "datasets" / "a.csv"
            dataset.write_text("value\n1\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                store.archive_item(project.project_id, "datasets/a.csv", "wrong")

    def test_delete_run_is_permanent_but_requires_an_exact_safe_name(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = PlatformStore(Path(temp_dir))
            project = store.create_project("SOC", "train_lstm.py", "data/a.csv")
            run = project.path / "runs" / "20260718-120000-abc123"
            run.mkdir()
            (run / "model.pt").write_bytes(b"model")

            with self.assertRaises(ValueError):
                store.delete_run(project.project_id, run.name, "wrong")
            with self.assertRaises(ValueError):
                store.delete_run(project.project_id, "../archive", "archive")
            self.assertTrue(run.is_dir())

            store.delete_run(project.project_id, run.name, run.name)

            self.assertFalse(run.exists())

    def test_soc_command_uses_a_new_run_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = PlatformStore(Path(temp_dir))
            project = store.create_project("A123 SOC", "train_lstm.py", "data/a.csv")
            command, run_dir = build_soc_command(
                project, {"window": 30, "max_train": 40000}, Path("python.exe")
            )
            self.assertIn("--results-dir", command)
            self.assertEqual(command[0], "python.exe")
            self.assertEqual(command[1:3], ["-m", "src.training.train_lstm"])
            self.assertEqual(command[command.index("--hidden") + 1], "32")
            self.assertEqual(command[command.index("--learning-rate") + 1], "0.0003")
            self.assertEqual(command[command.index("--patience") + 1], "9")
            self.assertEqual(command[command.index("--dropout") + 1], "0.1")
            self.assertEqual(command[command.index("--weight-decay") + 1], "0.0001")
            self.assertEqual(command[command.index("--lr-patience") + 1], "3")
            self.assertEqual(command[command.index("--lr-factor") + 1], "0.5")
            self.assertEqual(command[command.index("--min-learning-rate") + 1], "3e-05")
            self.assertEqual(command[command.index("--min-delta") + 1], "1e-05")
            self.assertEqual(command[command.index("--gradient-clip") + 1], "1.0")
            self.assertTrue(run_dir.is_dir())
            self.assertEqual(run_dir.parent.name, "runs")

    def test_missing_metrics_is_incomplete_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "run"
            run_dir.mkdir()
            result = read_run_result(run_dir)
            self.assertEqual(result.status, "incomplete")
            self.assertIsNone(result.metrics)

    def test_csv_summary_counts_rows_and_sessions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_path = Path(temp_dir) / "data.csv"
            data_path.write_text("session,soc\na,0.1\na,0.2\nb,0.3\n", encoding="utf-8")
            summary = summarize_csv(data_path)
            self.assertEqual(summary["row_count"], 3)
            self.assertEqual(summary["session_count"], 2)
            self.assertEqual(summary["headers"], ["session", "soc"])

    def test_soc_project_bootstrap_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = PlatformStore(Path(temp_dir))
            first = store.ensure_soc_project(Path("train_lstm.py"), Path("data/a123_soc_30s.csv"))
            second = store.ensure_soc_project(Path("train_lstm.py"), Path("data/a123_soc_30s.csv"))
            self.assertEqual(first.project_id, second.project_id)
            self.assertEqual(store.list_projects()[0].name, "A123 SOC")

    def test_store_creates_a_separate_nasa_multistate_project_and_command(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = PlatformStore(Path(temp_dir))
            project = store.ensure_nasa_multistate_project(Path("train_multistate_lstm.py"), Path("nasa_samples.csv"))

            command, run_dir = build_multistate_command(project, {"window": 30, "epochs": 2}, Path("python.exe"))

            self.assertEqual(project.name, "NASA 五状态")
            self.assertIn("src.training.train_multistate_lstm", command)
            self.assertEqual(command[command.index("--window") + 1], "30")
            self.assertEqual(command[command.index("--epochs") + 1], "2")
            self.assertTrue(run_dir.is_dir())

    def test_soc_project_bootstrap_refreshes_migrated_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = PlatformStore(Path(temp_dir))
            old = store.create_project("A123 SOC", "old_train.py", "old_data.csv")

            refreshed = store.ensure_soc_project(Path("src/training/train_lstm.py"), Path(r"E:\SOC电池数据中心\02_训练数据\a123_soc_30s.csv"))

            self.assertEqual(old.project_id, refreshed.project_id)
            self.assertEqual(str(Path("src/training/train_lstm.py").resolve()), refreshed.trainer_script)
            self.assertEqual(str(Path(r"E:\SOC电池数据中心\02_训练数据\a123_soc_30s.csv").resolve()), refreshed.data_path)


if __name__ == "__main__":
    unittest.main()
