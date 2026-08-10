from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np


class IsolatedXGBoostBackendTests(unittest.TestCase):
    def test_backend_avoids_torch_sklearn_and_duplicate_openmp_runtimes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            train_x = np.arange(120, dtype=np.float32).reshape(30, 4) / 100
            train_y = np.column_stack((train_x[:, 0] + train_x[:, 1], train_x[:, 2] - train_x[:, 3]))
            test_x = train_x[:5]
            np.savez(root / "input.npz", train_x=train_x, train_y=train_y, test_x=test_x)

            environment = {
                "PATH": os.environ.get("PATH", "/opt/homebrew/bin:/usr/bin:/bin"),
                "OMP_NUM_THREADS": "1",
                "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
            }
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "src.training.xgboost_backend",
                    "--input",
                    str(root / "input.npz"),
                    "--output",
                    str(root / "prediction.npy"),
                    "--runtime-report",
                    str(root / "runtime.json"),
                    "--estimators",
                    "4",
                    "--seed",
                    "42",
                ],
                check=True,
                cwd=Path(__file__).resolve().parents[1],
                env=environment,
            )

            prediction = np.load(root / "prediction.npy")
            report = json.loads((root / "runtime.json").read_text(encoding="utf-8"))
            self.assertEqual(prediction.shape, (5, 2))
            self.assertTrue(np.isfinite(prediction).all())
            self.assertFalse(report["torch_loaded"])
            self.assertFalse(report["sklearn_loaded"])
            self.assertLessEqual(len(report["openmp_runtimes"]), 1)


if __name__ == "__main__":
    unittest.main()
