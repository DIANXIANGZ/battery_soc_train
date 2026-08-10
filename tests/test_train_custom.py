from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from src.training.train_custom import run_training


def write_data(path: Path, rows: int = 90) -> Path:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("voltage", "current", "soc", "rul"))
        writer.writeheader()
        writer.writerows({"voltage": 3.5 + index / 1000, "current": index % 5, "soc": index / rows, "rul": rows - index} for index in range(rows))
    return path


def write_grouped_data(path: Path) -> Path:
    fields = ("cell_id", "session_id", "cycle_id", "condition_id", "voltage", "current", "soc")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for cell in range(4):
            for condition in ("cold", "warm"):
                for index in range(12):
                    writer.writerow({
                        "cell_id": f"c{cell}", "session_id": f"s{cell}", "cycle_id": 1,
                        "condition_id": condition, "voltage": 4.2 - index / 100,
                        "current": 1.0, "soc": 1.0 - index / 12,
                    })
    return path


class CustomTrainingTests(unittest.TestCase):
    def test_algorithms_write_a_common_result_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for algorithm in ("lstm", "gru", "xgboost", "transformer"):
                result = run_training(write_data(root / f"{algorithm}.csv"), root / algorithm, features=("voltage", "current"), targets=("soc", "rul"), algorithm=algorithm, window=5, epochs=1, batch_size=16, hidden=8, seed=42)
                self.assertGreater(result["metrics"]["n_test"], 0)
                self.assertEqual(set(json.loads((root / algorithm / "metrics_by_target.json").read_text(encoding="utf-8"))), {"soc", "rul"})
                self.assertTrue((root / algorithm / "test_predictions.csv").is_file())
                self.assertTrue((root / algorithm / "run_config.json").is_file())

    def test_unknown_algorithm_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with self.assertRaisesRegex(ValueError, "Unsupported algorithm"):
                run_training(write_data(root / "cell.csv"), root / "run", features=("voltage",), targets=("soc",), algorithm="forest", window=5, epochs=1, batch_size=8, hidden=8, seed=42)

    def test_canonical_group_columns_enable_strict_cell_condition_split(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run_training(
                write_grouped_data(root / "grouped.csv"), root / "run",
                features=("voltage", "current"), targets=("soc",), algorithm="xgboost",
                window=4, epochs=1, batch_size=8, hidden=8, seed=42,
            )
            audit = json.loads((root / "run" / "leakage_audit.json").read_text(encoding="utf-8"))
            self.assertEqual(audit["generalization_level"], "unseen_cell_and_condition")
            self.assertTrue(audit["passed"])
            self.assertFalse(audit["window_boundary_crossing"])
