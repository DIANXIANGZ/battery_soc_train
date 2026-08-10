from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch

from src.evaluation import evaluate_external_cell
from src.training.train_lstm import LSTMSOC


def make_export(path: Path) -> None:
    model = LSTMSOC(4, hidden=3)
    torch.save({
        "state_dict": model.state_dict(),
        "features": ("voltage_v", "current_a", "dv_dt_v_s", "window_delta_ah"),
        "mean": np.zeros(4, dtype=np.float32),
        "std": np.ones(4, dtype=np.float32),
        "window": 2,
    }, path)


def make_csv(path: Path, session: str) -> None:
    rows = ["session,voltage_v,current_a,dv_dt_v_s,soc"]
    rows.extend(f"{session},{3.4 + i / 100},0.1,0.01,{i / 10}" for i in range(4))
    path.write_text("\n".join(rows), encoding="utf-8")


class EvaluateExternalCellTests(unittest.TestCase):
    def test_predicts_in_bounded_batches(self) -> None:
        class Probe(torch.nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.max_batch = 0

            def forward(self, value):
                self.max_batch = max(self.max_batch, len(value))
                return torch.zeros(len(value))

        probe = Probe()
        predicted = evaluate_external_cell.predict_in_batches(
            probe, np.zeros((5, 2, 4), dtype=np.float32), batch_size=2
        )
        self.assertEqual(2, probe.max_batch)
        self.assertEqual((5,), predicted.shape)

    def test_restores_saved_window_and_infers_hidden_width(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            export = Path(temp_dir) / "model.pt"
            make_export(export)
            model, features, mean, std, window = evaluate_external_cell.load_exported_model(export)
        self.assertEqual(3, model.lstm.hidden_size)
        self.assertEqual(2, window)
        self.assertEqual(("voltage_v", "current_a", "dv_dt_v_s", "window_delta_ah"), features)
        self.assertEqual((4,), mean.shape)
        self.assertEqual((4,), std.shape)

    def test_rejects_source_cell_rows_as_cross_cell_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            export, data = root / "model.pt", root / "source.csv"
            make_export(export)
            make_csv(data, "A123#3_source")
            with self.assertRaisesRegex(ValueError, "A123#5"):
                evaluate_external_cell.evaluate_csv(data, export, "A123#5")

    def test_writes_metrics_only_to_requested_new_results_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            export, data, output = root / "model.pt", root / "target.csv", root / "new_results"
            make_export(export)
            make_csv(data, "A123#5_target")
            metrics, predictions = evaluate_external_cell.evaluate_csv(data, export, "A123#5")
            evaluate_external_cell.write_results(output, metrics, predictions)
            saved = json.loads((output / "metrics.json").read_text(encoding="utf-8"))
            self.assertEqual("A123#3", saved["source_cell"])
            self.assertEqual("A123#5", saved["target_cell"])
            self.assertTrue((output / "metrics_by_soc.json").exists())
            self.assertTrue((output / "test_predictions.csv").exists())

    def test_rejects_a_protected_results_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            protected = Path(temp_dir) / "baseline"
            protected.mkdir()
            with self.assertRaisesRegex(ValueError, "protected"):
                evaluate_external_cell.write_results(
                    protected,
                    {"MAE_pct": 1.0, "RMSE_pct": 2.0},
                    [(0.5, 0.5)],
                    protected_dirs=[protected],
                )


if __name__ == "__main__":
    unittest.main()
