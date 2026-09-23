from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from src.desktop.formal_baselines import (
    build_formal_baseline_command,
    load_formal_baselines,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_summary(root: Path, *, result_exists: bool = False) -> dict:
    runner = root / "runner.py"
    config = root / "config.json"
    dataset = root / "dataset"
    dataset.mkdir()
    (dataset / "manifest.json").write_text("{}", encoding="utf-8")
    runner.write_text("# stable runner\n", encoding="utf-8")
    config.write_text("{}", encoding="utf-8")
    result = root / "results" / "formal"
    result.parent.mkdir(parents=True)
    if result_exists:
        result.mkdir(parents=True)
    target = {
        "status": "PYTORCH_FORMAL_PASS_SCOPED",
        "scope": "fixture scope",
        "model": "fixture model",
        "dataset_path": str(dataset),
        "code_config": {
            "runner_path": str(runner),
            "runner_sha256": _sha256(runner),
            "config_path": str(config),
            "config_sha256": _sha256(config),
        },
        "result_path": str(result),
        "metrics": {"mae": 0.1, "rmse": 0.2},
    }
    payload = {
        "schema_version": 1,
        "status": "COMPLETE_FOUR_TARGET_SCOPED_BASELINES",
        "targets": {name: dict(target, target=name) for name in ("soc", "system_soe", "soh", "sot")},
    }
    summary_path = root / "docs" / "audits" / "2026-09-23-non-rul-four-target-completion.json"
    summary_path.parent.mkdir(parents=True)
    summary_path.write_text(json.dumps(payload), encoding="utf-8")
    return payload


class FormalBaselineContractTests(unittest.TestCase):
    def test_desktop_app_exposes_read_only_four_target_entry(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "src" / "desktop" / "app.py").read_text(encoding="utf-8")

        self.assertIn("四目标正式基线", source)
        self.assertIn("def show_formal_baselines", source)
        self.assertIn("打开或刷新不会重新运行训练", source)

    def test_summary_exposes_all_four_targets_without_reading_samples(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_summary(root)

            summary = load_formal_baselines(root)

            self.assertEqual(summary.status, "COMPLETE_FOUR_TARGET_SCOPED_BASELINES")
            self.assertEqual(set(summary.targets), {"soc", "system_soe", "soh", "sot"})
            self.assertEqual(summary.targets["soc"].metrics["mae"], 0.1)

    def test_missing_summary_is_unavailable_with_reason(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            summary = load_formal_baselines(Path(temp_dir))

            self.assertEqual(summary.status, "UNAVAILABLE")
            self.assertIn("摘要", summary.reason)

    def test_start_requires_hashes_and_does_not_overwrite_existing_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_summary(root, result_exists=True)
            summary = load_formal_baselines(root)

            spec = build_formal_baseline_command(summary.targets["sot"], root)

            self.assertTrue(spec.available)
            self.assertNotEqual(spec.output_path, (root / "results" / "formal").resolve())
            self.assertIn("--output", spec.command)
            self.assertIn("desktop-", str(spec.output_path))

    def test_rul_path_component_is_rejected_but_non_rul_root_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir)
            safe_root = parent / "non_rul"
            safe_root.mkdir()
            _write_summary(safe_root)
            safe_summary = load_formal_baselines(safe_root)
            self.assertTrue(build_formal_baseline_command(safe_summary.targets["sot"], safe_root).available)

            blocked_root = parent / "rul"
            blocked_root.mkdir()
            _write_summary(blocked_root)
            blocked_summary = load_formal_baselines(blocked_root)
            blocked_spec = build_formal_baseline_command(blocked_summary.targets["sot"], blocked_root)
            self.assertFalse(blocked_spec.available)
            self.assertIn("冻结资产", blocked_spec.reason)

    def test_old_checkout_paths_are_rebound_to_current_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_summary(root)
            relative_runner = Path(".superpowers") / "sdd" / "runner.py"
            relative_config = Path("configs") / "baseline.json"
            (root / relative_runner).parent.mkdir(parents=True)
            (root / relative_config).parent.mkdir(parents=True)
            (root / relative_runner).write_text("runner", encoding="utf-8")
            (root / relative_config).write_text("config", encoding="utf-8")
            summary_path = root / "docs" / "audits" / "2026-09-23-non-rul-four-target-completion.json"
            payload = json.loads(summary_path.read_text(encoding="utf-8"))
            old_root = "/old/battery_soc_project/battery_soc_project"
            for target in payload["targets"].values():
                target["code_config"]["runner_path"] = f"{old_root}/{relative_runner}"
                target["code_config"]["config_path"] = f"{old_root}/{relative_config}"
            summary_path.write_text(json.dumps(payload), encoding="utf-8")

            summary = load_formal_baselines(root)

            self.assertEqual(summary.targets["sot"].runner_path, (root / relative_runner).resolve())
            self.assertEqual(summary.targets["sot"].config_path, (root / relative_config).resolve())

    def test_stable_runner_command_is_only_available_for_empty_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "05_非RUL独立候选"
            root.mkdir()
            _write_summary(root)
            summary = load_formal_baselines(root)

            spec = build_formal_baseline_command(summary.targets["sot"], root)

            self.assertTrue(spec.available)
            self.assertIn("--formal-authorized", spec.command)
            self.assertNotEqual(spec.output_path, (root / "results" / "formal").resolve())


if __name__ == "__main__":
    unittest.main()
