from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import json
import sys
import subprocess

from src.evaluation.generalization_experiments import (
    ExperimentJob,
    assert_a1233_only,
    make_loso_jobs,
    make_seed_jobs,
    run_job,
    run_candidate_and_cross_cell,
    evaluate_internal_gate,
    select_median_seed,
    sha256_files,
    summarize_stage,
    verify_required_artifacts,
    write_implementation_manifest,
    write_report,
)


SESSIONS = [
    "A123#3_05_28_13",
    "A123#3_06_20_13",
    "A123#3_09_13_12",
    "A123#3_09_24_12",
    "A123#3_10_25_12",
    "A123#3_11_01_12",
]


class GeneralizationExperimentTests(unittest.TestCase):
    def test_cli_help_lists_all_workflow_stages(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "src.evaluation.generalization_experiments", "--help"],
            text=True,
            capture_output=True,
            check=True,
        )
        for stage in ("smoke", "internal", "cross-cell", "all"):
            self.assertIn(stage, completed.stdout)

    def _summary_run(self, root: Path, name: str, state: str, mae: float, rmse: float, seed: int) -> Path:
        run = root / name
        run.mkdir()
        (run / "status.json").write_text(
            json.dumps({"state": state, "job_id": name}), encoding="utf-8"
        )
        (run / "metrics.json").write_text(
            json.dumps({"MAE_pct": mae, "RMSE_pct": rmse, "seed": seed}), encoding="utf-8"
        )
        return run

    def _job(self, results_dir: Path) -> ExperimentJob:
        return ExperimentJob(
            job_id="seed-042",
            stage="seed",
            seed=42,
            train_sessions=tuple(SESSIONS[:-2]),
            validation_session=SESSIONS[-2],
            test_session=SESSIONS[-1],
            results_dir=results_dir,
        )

    def test_sha256_files_detects_a_changed_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            baseline = Path(temp_dir) / "baseline.pt"
            baseline.write_bytes(b"before")
            before = sha256_files([baseline])
            baseline.write_bytes(b"after")
            after = sha256_files([baseline])
        self.assertNotEqual(before, after)

    def test_summary_uses_only_succeeded_runs_and_reports_statistics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runs = [
                self._summary_run(root, "seed-011", "succeeded", 2.0, 3.0, 11),
                self._summary_run(root, "seed-023", "succeeded", 3.0, 4.0, 23),
                self._summary_run(root, "seed-042", "succeeded", 4.0, 5.0, 42),
                self._summary_run(root, "seed-067", "failed", 99.0, 99.0, 67),
            ]
            summary = summarize_stage(runs)

        self.assertEqual(3, summary["count"])
        self.assertEqual(3.0, summary["MAE_pct"]["mean"])
        self.assertEqual(3.0, summary["MAE_pct"]["median"])
        self.assertEqual(2.0, summary["MAE_pct"]["minimum"])
        self.assertEqual(4.0, summary["MAE_pct"]["maximum"])
        self.assertEqual("seed-042", summary["MAE_pct"]["worst_job_id"])
        self.assertIn("standard_deviation", summary["RMSE_pct"])

    def test_internal_gate_uses_inclusive_thresholds_and_incomplete_counts(self) -> None:
        passed = evaluate_internal_gate(
            {"count": 5, "MAE_pct": {"mean": 3.5}},
            {"count": 6, "MAE_pct": {"maximum": 8.0}},
        )
        failed = evaluate_internal_gate(
            {"count": 5, "MAE_pct": {"mean": 3.5001}},
            {"count": 6, "MAE_pct": {"maximum": 8.0}},
        )
        incomplete = evaluate_internal_gate(
            {"count": 4, "MAE_pct": {"mean": 2.0}},
            {"count": 6, "MAE_pct": {"maximum": 3.0}},
        )
        self.assertTrue(passed["passed"])
        self.assertEqual("failed", failed["state"])
        self.assertEqual("incomplete", incomplete["state"])

    def test_median_seed_selection_is_deterministic(self) -> None:
        runs = [
            {"job_id": "seed-011", "seed": 11, "MAE_pct": 2.0},
            {"job_id": "seed-023", "seed": 23, "MAE_pct": 3.0},
            {"job_id": "seed-042", "seed": 42, "MAE_pct": 4.0},
            {"job_id": "seed-067", "seed": 67, "MAE_pct": 5.0},
            {"job_id": "seed-101", "seed": 101, "MAE_pct": 6.0},
        ]
        self.assertEqual(42, select_median_seed(runs)["seed"])

    def test_cross_cell_gate_does_not_evaluate_when_internal_evidence_fails(self) -> None:
        calls = []
        result = run_candidate_and_cross_cell(
            {"state": "failed", "passed": False},
            Path("candidate.pt"), Path("a1235.csv"), Path("output"), Path("current.json"),
            evaluator=lambda *args: calls.append(args),
        )
        self.assertEqual("skipped_internal_gate", result["decision"])
        self.assertEqual([], calls)

    def test_cross_cell_gate_classifies_a_preferred_candidate_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            model = root / "candidate.pt"
            data = root / "a1235.csv"
            current = root / "current.json"
            output = root / "cross_cell_candidate"
            model.write_bytes(b"model")
            data.write_text("data", encoding="utf-8")
            current.write_text(json.dumps({"MAE_pct": 2.55}), encoding="utf-8")
            calls = []

            def evaluator(data_path, model_path, expected_prefix):
                calls.append((data_path, model_path, expected_prefix))
                return {"MAE_pct": 2.2, "RMSE_pct": 3.0}, [(0.5, 0.5)]

            def writer(results_dir, metrics, predictions, protected_dirs=()):
                results_dir.mkdir(parents=True)
                (results_dir / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")

            first = run_candidate_and_cross_cell(
                {"state": "passed", "passed": True},
                model, data, output, current, evaluator=evaluator, writer=writer,
            )
            second = run_candidate_and_cross_cell(
                {"state": "passed", "passed": True},
                model, data, output, current, evaluator=evaluator, writer=writer,
            )

        self.assertEqual("preferred_target_met", first["decision"])
        self.assertEqual(first, second)
        self.assertEqual(1, len(calls))
        self.assertEqual("A123#5", calls[0][2])

    def test_report_contains_thresholds_folds_decision_and_label_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "综合泛化验证报告.md"
            seed_summary = {"count": 5, "MAE_pct": {"mean": 2.8, "standard_deviation": 0.2}}
            loso_summary = {
                "count": 6,
                "MAE_pct": {"mean": 3.2, "maximum": 5.1},
                "runs": [
                    {"job_id": f"loso-{index}", "MAE_pct": 3.0 + index / 10, "RMSE_pct": 4.0}
                    for index in range(6)
                ],
            }
            gate = {"state": "passed", "passed": True}
            decision = {
                "decision": "preferred_target_met",
                "candidate_A1235_MAE_pct": 2.2,
                "scope_note": "processed A123#5 session",
            }
            write_report(output, seed_summary, loso_summary, gate, decision)
            content = output.read_text(encoding="utf-8")
        self.assertIn("3.5%", content)
        self.assertIn("8%", content)
        self.assertIn("2.3%", content)
        self.assertEqual(6, content.count("| loso-"))
        self.assertIn("preferred_target_met", content)
        self.assertIn("库仑计量", content)
        self.assertIn("processed A123#5 session", content)

    def test_implementation_manifest_records_reproducibility_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            code = root / "code.py"
            test = root / "test_code.py"
            code.write_text("value = 1\n", encoding="utf-8")
            test.write_text("assert True\n", encoding="utf-8")
            run = root / "seed_runs" / "seed-011"
            run.mkdir(parents=True)
            (run / "status.json").write_text(json.dumps({"state": "succeeded"}), encoding="utf-8")
            hashes = {"baseline": "same"}
            manifest = write_implementation_manifest(
                root / "implementation_manifest.json",
                project_root=root,
                experiment_root=root,
                code_paths=[code],
                test_paths=[test],
                baseline_before=hashes,
                baseline_after=hashes,
                test_count=91,
                final_decision="passed",
            )

        self.assertTrue(manifest["baseline_unchanged"])
        self.assertEqual(91, manifest["test_count"])
        self.assertEqual(1, manifest["completed_job_count"])
        self.assertTrue(manifest["python_version"])
        self.assertTrue(manifest["pytorch_version"])

    def test_run_job_succeeds_and_skips_a_verified_completed_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            results = temp / "run"
            script = temp / "fake_trainer.py"
            script.write_text(
                "from pathlib import Path\n"
                "import json,sys\n"
                "p=Path(sys.argv[1]); p.mkdir(parents=True,exist_ok=True)\n"
                "(p/'metrics.json').write_text(json.dumps({'MAE_pct':2.0,'RMSE_pct':3.0}))\n"
                "(p/'metrics_by_soc.json').write_text('{}')\n"
                "(p/'training_history.json').write_text('[{\"epoch\":1,\"training_mse\":0.1,\"validation_mse\":0.2,\"learning_rate\":0.0003}]')\n"
                "(p/'test_predictions.csv').write_text('reference_soc,predicted_soc\\n0.5,0.5\\n')\n"
                "(p/'soc_prediction.png').write_bytes(b'png')\n"
                "(p/'validation_loss.png').write_bytes(b'png')\n"
                "(p/'lstm_soc.pt').write_bytes(b'model')\n"
                "(p/'run_config.json').write_text('{}')\n"
                "print('fake training complete')\n",
                encoding="utf-8",
            )
            job = self._job(results)
            first = run_job(
                job, Path(sys.executable), temp / "data.csv", temp,
                command_override=[sys.executable, str(script), str(results)],
                minimum_free_bytes=0,
            )
            second = run_job(
                job, Path(sys.executable), temp / "data.csv", temp,
                command_override=[sys.executable, "-c", "raise SystemExit(9)"],
                minimum_free_bytes=0,
            )

            self.assertEqual("succeeded", first["state"])
            self.assertTrue(second["skipped"])
            self.assertTrue(verify_required_artifacts(results))

    def test_run_job_records_failure_and_rejects_unrecognized_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            failed_dir = temp / "failed"
            status = run_job(
                self._job(failed_dir), Path(sys.executable), temp / "data.csv", temp,
                command_override=[sys.executable, "-c", "raise SystemExit(3)"],
                minimum_free_bytes=0,
            )
            self.assertEqual("failed", status["state"])
            self.assertEqual(3, status["returncode"])
            self.assertEqual("failed", json.loads((failed_dir / "status.json").read_text())["state"])

            unknown = temp / "unknown"
            unknown.mkdir()
            (unknown / "user.txt").write_text("preserve", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                run_job(
                    self._job(unknown), Path(sys.executable), temp / "data.csv", temp,
                    command_override=[sys.executable, "-c", "print('unused')"],
                    minimum_free_bytes=0,
                )

    def test_seed_jobs_use_the_approved_reproducible_seeds(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            jobs = make_seed_jobs(SESSIONS, Path(temp_dir))
        self.assertEqual([11, 23, 42, 67, 101], [job.seed for job in jobs])
        self.assertEqual(5, len({job.job_id for job in jobs}))
        self.assertTrue(all(job.stage == "seed" for job in jobs))

    def test_loso_jobs_cover_every_session_without_overlap(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            jobs = make_loso_jobs(SESSIONS, Path(temp_dir), seed=42)
        self.assertEqual(6, len(jobs))
        self.assertEqual(set(SESSIONS), {job.test_session for job in jobs})
        for job in jobs:
            self.assertNotIn(job.test_session, job.train_sessions)
            self.assertNotEqual(job.validation_session, job.test_session)
            self.assertEqual(4, len(job.train_sessions))

    def test_planning_rejects_external_cells_and_wrong_session_count(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with self.assertRaisesRegex(ValueError, "six"):
                make_seed_jobs(SESSIONS[:-1], root)
            with self.assertRaisesRegex(ValueError, "A123#3"):
                make_seed_jobs(SESSIONS[:-1] + ["A123#5_07_03_12"], root)

    def test_job_guard_rejects_overlap(self) -> None:
        job = ExperimentJob(
            job_id="bad",
            stage="seed",
            seed=42,
            train_sessions=(SESSIONS[0], SESSIONS[1]),
            validation_session=SESSIONS[0],
            test_session=SESSIONS[2],
            results_dir=Path("bad"),
        )
        with self.assertRaisesRegex(ValueError, "overlap"):
            assert_a1233_only(job)


if __name__ == "__main__":
    unittest.main()
