from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from src.evaluation.multidataset_battery_experiments import load_validated_experiment_table, run_multidataset_experiment


def fixture_frame() -> pd.DataFrame:
    rows = []
    for cell_number in range(4):
        source = "source_a" if cell_number < 2 else "source_b"
        for condition_number, condition in enumerate(("cold", "warm")):
            for index in range(12):
                temperature = 15.0 + 10.0 * condition_number + 0.1 * index
                rows.append({
                    "source_id": source,
                    "cell_id": f"cell_{cell_number}",
                    "condition_id": condition,
                    "cycle_id": index,
                    "timestamp_s": float(index * 60),
                    "voltage_v": 4.2 - 0.02 * index,
                    "current_a": 1.0 + 0.1 * condition_number,
                    "temperature_c": temperature,
                    "soc": 1.0 - index / 12,
                    "soe": 1.0 - index / 12,
                    "soh": 1.0 - 0.005 * index,
                    "rul_cycles": float(11 - index),
                    "sot_c": temperature + 0.5,
                })
    return pd.DataFrame(rows)


class MultidatasetExperimentTests(unittest.TestCase):
    def test_invalidated_corpus_is_rejected_before_training(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "public_battery_experiment.csv"
            fixture_frame().to_csv(path, index=False)
            (root / "INVALIDATED.json").write_text(json.dumps({
                "valid_for_training": False,
                "reason": "future-normalized SOC labels",
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "invalidated"):
                load_validated_experiment_table(path)

    def test_corpus_without_native_state_integration_contract_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "public_battery_experiment.csv"
            fixture_frame().to_csv(path, index=False)
            (root / "corpus_manifest.json").write_text(json.dumps({
                "version": "public_battery_corpus_v3",
                "state_label_protocol": "causal_precycle_reference_v2",
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "integration protocol"):
                load_validated_experiment_table(path)

    def test_corpus_without_aligned_feature_reference_contract_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "public_battery_experiment.csv"
            fixture_frame().to_csv(path, index=False)
            (root / "corpus_manifest.json").write_text(json.dumps({
                "version": "public_battery_corpus_v4",
                "state_label_protocol": "causal_precycle_reference_v2",
                "state_integration_protocol": "native_cumulative_qd_and_dq_times_voltage_when_available_v1",
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "feature-reference protocol"):
                load_validated_experiment_table(path)

    def test_smoke_run_writes_strict_auditable_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir)
            result = run_multidataset_experiment(
                fixture_frame(),
                output,
                feature_columns=("cycle_id", "timestamp_s", "voltage_v", "current_a", "temperature_c"),
                targets=("soc", "soe", "soh", "rul_cycles", "sot_c"),
                feature_provenance={"cycle_id": "current", "timestamp_s": "current", "voltage_v": "current", "current_a": "current", "temperature_c": "current"},
                seed=7,
                stage="smoke",
            )
            self.assertEqual(set(result["metrics_by_target"]), {"soc", "soe", "soh", "rul_cycles", "sot_c"})
            for name in (
                "data_manifest.json", "split_manifest.json", "leakage_audit.json",
                "metrics_by_target.json", "acceptance.json", "test_predictions.csv", "model_manifests.json",
            ):
                self.assertTrue((output / name).is_file(), name)
            audit = json.loads((output / "leakage_audit.json").read_text(encoding="utf-8"))
            self.assertTrue(audit["passed"])
            self.assertEqual(audit["test_used_for_selection"], False)
            manifest = json.loads((output / "data_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["source_count"], 2)

    def test_future_derived_feature_is_rejected_before_splitting(self) -> None:
        frame = fixture_frame().assign(next_capacity=1.0)
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "future"):
                run_multidataset_experiment(
                    frame,
                    Path(temp_dir),
                    feature_columns=("cycle_id", "next_capacity"),
                    targets=("soh",),
                    feature_provenance={"cycle_id": "current", "next_capacity": "future cycle capacity"},
                    seed=7,
                    stage="smoke",
                )


if __name__ == "__main__":
    unittest.main()
