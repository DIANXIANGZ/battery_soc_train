from __future__ import annotations

import unittest
from pathlib import Path

from src.custom_training.admission import assess_custom_training
from src.custom_training.algorithms import ALGORITHM_REGISTRY, algorithm_keys, recommend_algorithm
from src.custom_training.dataset import CustomDatasetConfig


def custom_config(
    *,
    targets: tuple[str, ...] = ("soc",),
    algorithm: str = "lstm",
    roles: tuple[tuple[str, str], ...] = (),
) -> CustomDatasetConfig:
    return CustomDatasetConfig(
        source_path=Path("cell.csv"),
        sheet_name=None,
        time_column="time",
        feature_columns=("voltage", "current"),
        target_columns=targets,
        algorithm=algorithm,
        role_columns=roles,
    )


class CustomTrainingAdmissionTests(unittest.TestCase):
    def test_xgboost_worker_remains_torch_free_and_single_threaded(self) -> None:
        project = Path(__file__).resolve().parents[1]
        source = (project / "src" / "training" / "xgboost_backend.py").read_text(encoding="utf-8")
        self.assertNotIn("import torch", source)
        self.assertIn('if "torch" in sys.modules', source)
        self.assertIn('"nthread": 1', source)
        parent = (project / "src" / "training" / "train_custom.py").read_text(encoding="utf-8")
        self.assertIn('"-m", "src.training.xgboost_backend"', parent)

    def test_current_v11_and_oxford_rul_facts_never_authorize_training(self) -> None:
        roles = (
            ("cell_id", "cell"),
            ("condition_id", "condition"),
            ("cycle_id", "cycle"),
            ("rul_observed", "observed"),
            ("eol_provenance", "provenance"),
        )
        common = {
            "targets": {"rul_cycles": {"causal_label_audit_passed": True}},
        }
        v11 = assess_custom_training(
            custom_config(targets=("rul_cycles",), algorithm="xgboost", roles=roles),
            manifest={
                **common,
                "valid_for_training": False,
                "training_authorized": False,
                "rul": {
                    "exact_observed_cells": 5,
                    "grid_cycles": 1,
                    "task": "point",
                    "censored_rows_are_exact_supervision": False,
                },
            },
        )
        oxford = assess_custom_training(
            custom_config(targets=("rul_cycles",), algorithm="xgboost", roles=roles),
            manifest={
                **common,
                "valid_for_training": True,
                "training_authorized": True,
                "rul": {
                    "exact_observed_cells": 8,
                    "grid_cycles": 100,
                    "task": "interval",
                    "censored_rows_are_exact_supervision": False,
                },
            },
        )

        self.assertFalse(v11.training_allowed)
        self.assertFalse(oxford.training_allowed)

    def test_registry_drives_the_four_algorithm_contract_and_recommendation(self) -> None:
        self.assertEqual(algorithm_keys(), ("lstm", "gru", "xgboost", "transformer"))
        self.assertTrue(ALGORITHM_REGISTRY["xgboost"].isolated_worker)
        self.assertEqual(recommend_algorithm(("rul_cycles",)), "xgboost")
        self.assertEqual(recommend_algorithm(("soc", "soe")), "lstm")

    def test_user_override_changes_configuration_but_never_authorizes_training(self) -> None:
        result = assess_custom_training(custom_config(algorithm="transformer"))

        self.assertTrue(result.configuration_allowed)
        self.assertFalse(result.training_allowed)
        self.assertIn("manifest_missing", result.targets[0].blockers)

    def test_frozen_v11_and_five_exact_matr_cells_block_rul(self) -> None:
        result = assess_custom_training(
            custom_config(
                targets=("rul_cycles",),
                algorithm="xgboost",
                roles=(
                    ("cell_id", "cell"),
                    ("condition_id", "condition"),
                    ("cycle_id", "cycle"),
                    ("rul_observed", "observed"),
                    ("eol_provenance", "provenance"),
                ),
            ),
            manifest={
                "valid_for_training": False,
                "training_authorized": False,
                "targets": {"rul_cycles": {"causal_label_audit_passed": True}},
                "rul": {
                    "exact_observed_cells": 5,
                    "grid_cycles": 1,
                    "task": "point",
                    "censored_rows_are_exact_supervision": False,
                },
            },
        )

        self.assertFalse(result.training_allowed)
        self.assertIn("dataset_frozen", result.targets[0].blockers)
        self.assertIn("insufficient_exact_rul_cells", result.targets[0].blockers)

    def test_oxford_grid_is_not_one_cycle_point_supervision(self) -> None:
        result = assess_custom_training(
            custom_config(
                targets=("rul_cycles",),
                algorithm="xgboost",
                roles=(
                    ("cell_id", "cell"),
                    ("condition_id", "condition"),
                    ("cycle_id", "cycle"),
                    ("rul_observed", "observed"),
                    ("eol_provenance", "provenance"),
                ),
            ),
            manifest={
                "valid_for_training": True,
                "training_authorized": True,
                "targets": {"rul_cycles": {"causal_label_audit_passed": True}},
                "rul": {
                    "exact_observed_cells": 8,
                    "grid_cycles": 100,
                    "task": "interval",
                    "censored_rows_are_exact_supervision": False,
                },
            },
        )

        self.assertFalse(result.training_allowed)
        self.assertIn("rul_grid_not_one_cycle", result.targets[0].blockers)
        self.assertIn("rul_not_exact_point_task", result.targets[0].blockers)

    def test_malformed_rul_manifest_is_blocked_instead_of_raising(self) -> None:
        result = assess_custom_training(
            custom_config(
                targets=("rul_cycles",),
                algorithm="xgboost",
                roles=(
                    ("cell_id", "cell"),
                    ("condition_id", "condition"),
                    ("cycle_id", "cycle"),
                    ("rul_observed", "observed"),
                    ("eol_provenance", "provenance"),
                ),
            ),
            manifest={
                "valid_for_training": True,
                "training_authorized": True,
                "targets": {"rul_cycles": {"causal_label_audit_passed": True}},
                "rul": {
                    "exact_observed_cells": "not-an-integer",
                    "grid_cycles": None,
                    "task": "point",
                    "censored_rows_are_exact_supervision": False,
                },
            },
        )

        self.assertFalse(result.training_allowed)
        self.assertIn("invalid_manifest:rul.exact_observed_cells", result.targets[0].blockers)
        self.assertIn("invalid_manifest:rul.grid_cycles", result.targets[0].blockers)

    def test_fractional_rul_counts_are_never_truncated_into_authorization(self) -> None:
        result = assess_custom_training(
            custom_config(
                targets=("rul_cycles",),
                algorithm="xgboost",
                roles=(
                    ("cell_id", "cell"),
                    ("condition_id", "condition"),
                    ("cycle_id", "cycle"),
                    ("rul_observed", "observed"),
                    ("eol_provenance", "provenance"),
                ),
            ),
            manifest={
                "valid_for_training": True,
                "training_authorized": True,
                "targets": {"rul_cycles": {"causal_label_audit_passed": True}},
                "rul": {
                    "exact_observed_cells": 6.9,
                    "grid_cycles": 1.9,
                    "task": "point",
                    "censored_rows_are_exact_supervision": False,
                },
            },
        )

        self.assertFalse(result.training_allowed)
        self.assertIn("invalid_manifest:rul.exact_observed_cells", result.targets[0].blockers)
        self.assertIn("invalid_manifest:rul.grid_cycles", result.targets[0].blockers)

    def test_non_mapping_manifest_is_a_serializable_blocker(self) -> None:
        for malformed in (["bad"], "bad"):
            with self.subTest(malformed=malformed):
                result = assess_custom_training(custom_config(), manifest=malformed)  # type: ignore[arg-type]
                self.assertFalse(result.training_allowed)
                self.assertIn("invalid_manifest", result.targets[0].blockers)


if __name__ == "__main__":
    unittest.main()
