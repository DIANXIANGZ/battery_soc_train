from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

import numpy as np
import torch

from src.training.train_multistate_lstm import MultiStateLSTM, TARGETS, load_rows, make_sequences, masked_huber_loss, metric_summary, partition_rows, run_training


class MultiStateLstmTests(unittest.TestCase):
    def test_model_returns_one_prediction_per_required_target(self) -> None:
        model = MultiStateLSTM(n_features=4, hidden=8, dropout=0.0)
        output = model(torch.zeros(3, 6, 4))

        self.assertEqual(TARGETS, ("soc", "soh", "soe", "rul_cycles", "sot_c"))
        self.assertEqual(set(output), set(TARGETS))
        self.assertEqual(output["rul_cycles"].shape, (3,))

    def test_masked_huber_loss_ignores_missing_label_positions(self) -> None:
        prediction = torch.tensor([1.0, 8.0])
        reference = torch.tensor([0.0, 0.0])
        mask = torch.tensor([True, False])

        loss = masked_huber_loss(prediction, reference, mask)

        self.assertAlmostEqual(float(loss), 0.5)

    def test_sequences_do_not_cross_cycle_boundaries(self) -> None:
        rows = [
            {"cell_id": "RW9", "cycle_id": "0", "voltage_v": 1, "current_a": 1, "temperature_c": 1, "dv_dt_v_s": 1, **{target: 1 for target in TARGETS}},
            {"cell_id": "RW9", "cycle_id": "0", "voltage_v": 2, "current_a": 2, "temperature_c": 2, "dv_dt_v_s": 2, **{target: 2 for target in TARGETS}},
            {"cell_id": "RW9", "cycle_id": "1", "voltage_v": 3, "current_a": 3, "temperature_c": 3, "dv_dt_v_s": 3, **{target: 3 for target in TARGETS}},
            {"cell_id": "RW9", "cycle_id": "1", "voltage_v": 4, "current_a": 4, "temperature_c": 4, "dv_dt_v_s": 4, **{target: 4 for target in TARGETS}},
        ]

        features, targets = make_sequences(rows, window=2)

        self.assertEqual(features.shape, (2, 2, 4))
        self.assertEqual(targets["soc"].tolist(), [2.0, 4.0])

    def test_partition_rows_keeps_split_roles_separate(self) -> None:
        rows = [{"split": "train"}, {"split": "validation"}, {"split": "test"}]

        parts = partition_rows(rows)

        self.assertEqual(parts["train"], [{"split": "train"}])
        self.assertEqual(parts["validation"], [{"split": "validation"}])
        self.assertEqual(parts["test"], [{"split": "test"}])

    def test_load_rows_reads_numeric_targets_from_training_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "samples.csv"
            path.write_text("cell_id,cycle_id,split,voltage_v,current_a,temperature_c,dv_dt_v_s,soc,soh,soe,rul_cycles,sot_c\nRW9,0,train,3.8,1.0,25,0.01,1,1,1,5,25\n", encoding="utf-8")

            rows = load_rows(path)

            self.assertEqual(rows[0]["cell_id"], "RW9")
            self.assertEqual(rows[0]["rul_cycles"], 5.0)

    def test_metric_summary_reports_raw_unit_errors(self) -> None:
        result = metric_summary(np.asarray([0.0, 1.0]), np.asarray([0.1, 0.8]), unit="fraction")

        self.assertEqual(result["n_test"], 2)
        self.assertEqual(result["unit"], "fraction")
        self.assertAlmostEqual(result["MAE"], 0.15)
        self.assertAlmostEqual(result["RMSE"], (0.025) ** 0.5)

    def test_run_training_writes_auditable_five_target_artifacts(self) -> None:
        header = "cell_id,cycle_id,split,voltage_v,current_a,temperature_c,dv_dt_v_s,soc,soh,soe,rul_cycles,sot_c\n"
        records = []
        for split, cell in (("train", "RW9"), ("validation", "RW11"), ("test", "RW12")):
            for index in range(4):
                records.append(f"{cell},0,{split},{3.8 - index * 0.01},1.0,25,{0.01},0.{9 - index},0.9,0.8,{5 - index},25\n")
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_path = root / "samples.csv"
            data_path.write_text(header + "".join(records), encoding="utf-8")
            result_dir = root / "result"

            result = run_training(data_path, result_dir, window=2, epochs=1, batch_size=2, hidden=4, dropout=0.0, learning_rate=0.001, seed=7)

            self.assertEqual(set(result["metrics_by_target"]), set(TARGETS))
            for name in ("multistate_lstm.pt", "metrics.json", "metrics_by_target.json", "training_history.json", "run_config.json", "test_predictions.csv"):
                self.assertTrue((result_dir / name).is_file(), name)
            prediction_header = (result_dir / "test_predictions.csv").read_text(encoding="utf-8").splitlines()[0]
            self.assertIn("reference_rul_cycles", prediction_header)
            self.assertIn("predicted_sot_c", prediction_header)


if __name__ == "__main__":
    unittest.main()
