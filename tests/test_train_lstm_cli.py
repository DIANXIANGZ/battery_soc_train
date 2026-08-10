"""Regression tests for reproducible training controls."""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest

import torch

from src.training import train_lstm


PROJECT = Path(__file__).resolve().parents[1]


class TrainLstmCliTests(unittest.TestCase):
    def test_explicit_session_split_is_disjoint_and_preserves_order(self) -> None:
        split = train_lstm.resolve_session_split(
            ["a", "b", "c", "d"], ["c", "a"], "b", "d"
        )
        self.assertEqual(split, (["c", "a"], "b", "d"))

    def test_explicit_session_split_rejects_overlap_and_unknown_names(self) -> None:
        with self.assertRaisesRegex(ValueError, "overlap"):
            train_lstm.resolve_session_split(["a", "b", "c"], ["a"], "a", "c")
        with self.assertRaisesRegex(ValueError, "unknown"):
            train_lstm.resolve_session_split(["a", "b", "c"], ["a"], "b", "x")

    def test_parser_exposes_approved_overfitting_controls(self) -> None:
        parser = train_lstm.build_parser()
        args = parser.parse_args([])
        self.assertEqual(0.10, args.dropout)
        self.assertEqual(1e-4, args.weight_decay)
        self.assertEqual(3, args.lr_patience)
        self.assertEqual(0.5, args.lr_factor)
        self.assertEqual(3e-5, args.min_learning_rate)
        self.assertEqual(1e-5, args.min_delta)
        self.assertEqual(1.0, args.gradient_clip)

    def test_model_uses_dropout_in_prediction_head(self) -> None:
        model = train_lstm.LSTMSOC(4, hidden=32, dropout=0.10)
        dropouts = [module for module in model.head if isinstance(module, torch.nn.Dropout)]
        self.assertEqual(1, len(dropouts))
        self.assertEqual(0.10, dropouts[0].p)

    def test_optimizer_and_scheduler_apply_regularization_policy(self) -> None:
        model = train_lstm.LSTMSOC(4, hidden=8, dropout=0.10)
        args = SimpleNamespace(
            learning_rate=3e-4,
            weight_decay=1e-4,
            lr_factor=0.5,
            lr_patience=3,
            min_learning_rate=3e-5,
        )
        optimizer, scheduler = train_lstm.build_optimizer_and_scheduler(model, args)
        self.assertIsInstance(optimizer, torch.optim.AdamW)
        self.assertEqual(1e-4, optimizer.param_groups[0]["weight_decay"])
        self.assertIsInstance(scheduler, torch.optim.lr_scheduler.ReduceLROnPlateau)

    def test_min_delta_ignores_noise_sized_improvements(self) -> None:
        self.assertFalse(train_lstm.is_meaningful_improvement(0.001995, 0.002000, 1e-5))
        self.assertTrue(train_lstm.is_meaningful_improvement(0.001980, 0.002000, 1e-5))

    def test_checkpoint_payload_keeps_the_current_training_state(self) -> None:
        current_state = {"weight": "current"}
        payload = train_lstm.make_checkpoint_payload(
            model_state=current_state,
            optimizer_state={"step": 2},
            best_state={"weight": "best"},
            best_loss=0.1,
            stale_epochs=1,
            epochs_completed=2,
            feature_names=("voltage_v",),
            window=60,
            seed=42,
        )
        self.assertEqual("current", payload["model_state"]["weight"])
        self.assertEqual("best", payload["best_state"]["weight"])

    def test_svg_plot_shows_final_error_metrics_and_axis_labels(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "plot.svg"
            train_lstm.svg_plot([0.2, 0.4], [0.21, 0.39], output, mae_pct=2.19, rmse_pct=3.36)
            content = output.read_text(encoding="utf-8")
        self.assertIn("MAE 2.19%", content)
        self.assertIn("RMSE 3.36%", content)
        self.assertIn("Sample index", content)
        self.assertIn("SOC (%)", content)

    def test_help_exposes_seed_option(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "src.training.train_lstm", "--help"],
            cwd=PROJECT,
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn("--seed", completed.stdout)

    def test_checkpoint_can_be_resumed_for_another_training_segment(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            data = temp / "soc.csv"
            checkpoint = temp / "checkpoint.pt"
            first_results = temp / "first"
            resumed_results = temp / "resumed"
            rows = ["session,voltage_v,current_a,dv_dt_v_s,soc"]
            for session_index, session in enumerate(("a", "b", "c")):
                for point in range(8):
                    rows.append(f"{session},{3.0 + session_index + point / 100},{point / 10},0.01,{point / 10}")
            data.write_text("\n".join(rows), encoding="utf-8")
            common = [
                sys.executable, "-m", "src.training.train_lstm", "--data", str(data),
                "--window", "2", "--epochs", "1", "--batch-size", "2", "--hidden", "4",
                "--max-train", "100", "--max-valid", "100", "--max-test", "100",
                "--patience", "0", "--seed", "7", "--checkpoint", str(checkpoint),
            ]
            subprocess.run(common + ["--results-dir", str(first_results)], cwd=PROJECT, check=True)
            subprocess.run(
                common + ["--results-dir", str(resumed_results), "--resume-from", str(checkpoint)],
                cwd=PROJECT,
                check=True,
            )
            self.assertTrue(checkpoint.exists())
            self.assertEqual(2, __import__("json").loads((resumed_results / "metrics.json").read_text())["epochs_completed"])

    def test_training_writes_validation_history_for_charting(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            data = temp / "soc.csv"
            results = temp / "results"
            rows = ["session,voltage_v,current_a,dv_dt_v_s,soc"]
            for session_index, session in enumerate(("a", "b", "c")):
                for point in range(8):
                    rows.append(f"{session},{3.0 + session_index},{point / 10},0.01,{point / 10}")
            data.write_text("\n".join(rows), encoding="utf-8")
            subprocess.run([
                sys.executable, "-m", "src.training.train_lstm", "--data", str(data), "--results-dir", str(results),
                "--window", "2", "--epochs", "2", "--batch-size", "2", "--hidden", "4",
                "--max-train", "100", "--max-valid", "100", "--max-test", "100", "--seed", "7",
            ], cwd=PROJECT, check=True)
            history = __import__("json").loads((results / "training_history.json").read_text(encoding="utf-8"))
            self.assertEqual(2, len(history))
            self.assertIn("training_mse", history[0])
            self.assertIn("validation_mse", history[0])
            self.assertIn("learning_rate", history[0])
            config = __import__("json").loads((results / "run_config.json").read_text(encoding="utf-8"))
            self.assertEqual(str(data.resolve()), config["data_path"])
            self.assertEqual(["a"], config["train_sessions"])
            self.assertEqual("b", config["validation_session"])
            self.assertEqual("c", config["test_session"])
            self.assertEqual(2, config["window_steps"])
            self.assertEqual(7, config["seed"])
            self.assertEqual(4, config["training_policy"]["hidden_size"])
            self.assertEqual(0.1, config["training_policy"]["dropout"])
            self.assertEqual("AdamW", config["training_policy"]["optimizer"])
            self.assertTrue((results / "metrics_by_soc.json").is_file())


if __name__ == "__main__":
    unittest.main()
