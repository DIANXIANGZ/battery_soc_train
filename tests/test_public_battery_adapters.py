from __future__ import annotations

import json
import hashlib
import inspect
from pathlib import Path
import tempfile
import unittest

import h5py
import numpy as np
import pandas as pd

from src.data_processing.adapters import calce, common, nasa_alt, oxford, sandia, stanford
from src.data_processing import build_public_battery_corpus as corpus_builder
from src.data_processing.build_public_battery_corpus import (
    add_causal_sample_features,
    build_cycle_table_from_samples,
    build_experiment_table,
    build_public_battery_corpus,
)
from src.research.battery_schema import (
    CYCLE_REQUIRED_COLUMNS,
    SAMPLE_REQUIRED_COLUMNS,
    derive_cycle_targets,
    derive_state_targets,
    validate_canonical_samples,
)


class PublicBatteryAdapterTests(unittest.TestCase):
    @staticmethod
    def _write_stanford_cells(
        path: Path,
        *,
        cell_count: int,
        target_index: int,
        target_cycle_count: int,
        target_cycle_life: int,
        target_capacity_ah: float,
    ) -> None:
        with h5py.File(path, "w") as handle:
            batch = handle.create_group("batch")
            for field in ("summary", "cycles", "policy_readable", "cycle_life"):
                batch.create_dataset(field, shape=(cell_count, 1), dtype=h5py.ref_dtype)
            for cell_index in range(cell_count):
                cycle_count = target_cycle_count if cell_index == target_index else 1
                summary = handle.create_group(f"summary_{cell_index}")
                summary.create_dataset("cycle", data=np.arange(1, cycle_count + 1, dtype=float)[None, :])
                cycles = handle.create_group(f"cycles_{cell_index}")
                vectors = {
                    "I": np.array([1.0, -1.0, -1.0]),
                    "V": np.array([3.3, 3.2, 3.0]),
                    "T": np.array([25.0, 25.1, 25.2]),
                    "t": np.array([0.0, 1.0, 2.0]),
                    "Qd": np.array([0.0, 0.0, target_capacity_ah]),
                    "Qc": np.array([0.0, 0.5, 0.5]),
                }
                for field, values in vectors.items():
                    dataset = handle.create_dataset(f"{field}_{cell_index}", data=values)
                    refs = np.asarray([dataset.ref] * cycle_count, dtype=h5py.ref_dtype)[:, None]
                    cycles.create_dataset(field, data=refs)
                policy = handle.create_dataset(
                    f"policy_{cell_index}", data=np.asarray([ord(char) for char in "4C(80%)-4C"]),
                )
                cycle_life = handle.create_dataset(
                    f"cycle_life_{cell_index}",
                    data=np.asarray([[target_cycle_life if cell_index == target_index else 2]], dtype=float),
                )
                batch["summary"][cell_index, 0] = summary.ref
                batch["cycles"][cell_index, 0] = cycles.ref
                batch["policy_readable"][cell_index, 0] = policy.ref
                batch["cycle_life"][cell_index, 0] = cycle_life.ref

    def test_matr_official_continuation_mapping_is_exact_and_guess_is_rejected(self) -> None:
        validator = getattr(stanford, "validate_official_continuation_mapping", None)
        self.assertIsNotNone(validator, "MATR official continuation mapping validator is required")
        official = [
            {"batch1_cell_id": "b1c0", "batch2_index_zero_based": 7, "batch2_index_one_based": 8, "add_len": 661, "expected_cycle_count": 662, "cycle_life": 663},
            {"batch1_cell_id": "b1c1", "batch2_index_zero_based": 8, "batch2_index_one_based": 9, "add_len": 980, "expected_cycle_count": 981, "cycle_life": 982},
            {"batch1_cell_id": "b1c2", "batch2_index_zero_based": 9, "batch2_index_one_based": 10, "add_len": 1059, "expected_cycle_count": 1060, "cycle_life": 1061},
            {"batch1_cell_id": "b1c3", "batch2_index_zero_based": 15, "batch2_index_one_based": 16, "add_len": 207, "expected_cycle_count": 208, "cycle_life": 209},
            {"batch1_cell_id": "b1c4", "batch2_index_zero_based": 16, "batch2_index_one_based": 17, "add_len": 481, "expected_cycle_count": 482, "cycle_life": 483},
        ]
        self.assertEqual(validator(official), official)
        guessed = [dict(item) for item in official]
        guessed[0]["batch2_index_zero_based"] = 6
        with self.assertRaisesRegex(ValueError, "official MATR continuation mapping"):
            validator(guessed)

    def test_matr_eol_classification_distinguishes_continuation_censoring_and_crossing(self) -> None:
        classifier = getattr(stanford, "classify_eol", None)
        self.assertIsNotNone(classifier, "MATR EOL classifier is required")
        continued = classifier(
            "b1c0",
            cycle_ids=np.array([1188, 1189, 1190, 1851]),
            capacities_ah=np.array([1.03, 1.02, 1.01, 0.8828]),
            continuation={
                "batch2_index_zero_based": 7,
                "batch1_end_cycle": 1189,
                "first_appended_cycle": 1190,
                "last_appended_cycle": 1851,
                "appended_cycle_count": 662,
                "batch2_cycle_life": 663,
            },
        )
        self.assertEqual(continued, {
            "eol_cycle": 1852.0,
            "eol_cycle_observed": 1,
            "eol_provenance": "official_continuation",
        })
        for cell_id in ("b1c8", "b1c10", "b1c12", "b1c13", "b1c22"):
            with self.subTest(cell_id=cell_id):
                censored = classifier(
                    cell_id,
                    cycle_ids=np.array([1, 2]),
                    capacities_ah=np.array([1.05, 0.87]),
                )
                self.assertTrue(np.isnan(censored["eol_cycle"]))
                self.assertEqual(censored["eol_cycle_observed"], 0)
                self.assertEqual(censored["eol_provenance"], "right_censored")
        crossing = classifier(
            "b1c5",
            cycle_ids=np.array([10, 11, 12]),
            capacities_ah=np.array([0.92, 0.879, 0.86]),
        )
        self.assertEqual(crossing, {
            "eol_cycle": 11.0,
            "eol_cycle_observed": 1,
            "eol_provenance": "observed_eol_crossing",
        })

    def test_matr_continuation_requires_contiguous_length_and_authoritative_cycle_life(self) -> None:
        classifier = getattr(stanford, "classify_eol", None)
        self.assertIsNotNone(classifier, "MATR EOL classifier is required")
        inconsistent = {
            "batch2_index_zero_based": 7,
            "batch1_end_cycle": 1189,
            "first_appended_cycle": 1190,
            "last_appended_cycle": 1850,
            "appended_cycle_count": 661,
            "batch2_cycle_life": 663,
        }
        with self.assertRaisesRegex(ValueError, "continuation structure"):
            classifier(
                "b1c0",
                cycle_ids=np.array([1189, 1190, 1850]),
                capacities_ah=np.array([1.02, 1.01, 0.89]),
                continuation=inconsistent,
            )

    def test_stanford_loader_appends_only_official_continuation_with_observed_provenance(self) -> None:
        self.assertIn("continuation_path", inspect.signature(stanford.load_samples).parameters)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            batch1 = root / "batch1.mat"
            batch2 = root / "batch2.mat"
            self._write_stanford_cells(
                batch1,
                cell_count=1,
                target_index=0,
                target_cycle_count=1,
                target_cycle_life=2,
                target_capacity_ah=1.0,
            )
            self._write_stanford_cells(
                batch2,
                cell_count=17,
                target_index=7,
                target_cycle_count=662,
                target_cycle_life=663,
                target_capacity_ah=0.8828,
            )
            result = stanford.load_samples(
                batch1,
                "a" * 64,
                stride=2,
                continuation_path=batch2,
                continuation_hash="b" * 64,
                continuation_mapping=[dict(item) for item in stanford.OFFICIAL_CONTINUATION_MAPPING],
            )
        self.assertEqual(result["cell_id"].unique().tolist(), ["b1c0"])
        self.assertEqual(result["session_id"].drop_duplicates().tolist(), ["2017-05-12", "2017-06-30"])
        self.assertEqual(result["cycle_id"].drop_duplicates().iloc[[0, -1]].tolist(), [1, 663])
        self.assertEqual(result["eol_cycle"].unique().tolist(), [664.0])
        self.assertEqual(result["eol_cycle_observed"].unique().tolist(), [1])
        self.assertEqual(result["eol_provenance"].unique().tolist(), ["official_continuation"])

    def test_cycle_table_preserves_eol_observation_and_provenance(self) -> None:
        samples = pd.DataFrame({
            "source_id": ["mit_stanford_fast_charge"] * 4,
            "chemistry": ["LFP"] * 4,
            "cell_id": ["continued", "continued", "censored", "censored"],
            "session_id": ["s", "s", "s", "s"],
            "cycle_id": [1, 1, 1, 1],
            "timestamp_s": [0.0, 3600.0, 0.0, 3600.0],
            "voltage_v": [3.3, 3.2, 3.3, 3.2],
            "current_a": [-1.0, -1.0, -1.0, -1.0],
            "temperature_c": [25.0] * 4,
            "cycle_capacity_ah": [1.0, 1.0, 1.0, 1.0],
            "cycle_energy_wh": [3.2, 3.2, 3.2, 3.2],
            "eol_cycle": [2.0, 2.0, np.nan, np.nan],
            "eol_cycle_observed": [1, 1, 0, 0],
            "eol_provenance": ["official_continuation", "official_continuation", "right_censored", "right_censored"],
            "source_hash": ["a" * 64] * 4,
        })
        result = build_cycle_table_from_samples(samples)
        continued = result[result["cell_id"].eq("continued")].iloc[0]
        censored = result[result["cell_id"].eq("censored")].iloc[0]
        self.assertEqual(int(continued["rul_observed"]), 1)
        self.assertEqual(continued["eol_provenance"], "official_continuation")
        self.assertEqual(int(censored["rul_observed"]), 0)
        self.assertEqual(censored["eol_provenance"], "right_censored")
        self.assertTrue(pd.isna(censored["rul_cycles"]))

    def test_experiment_table_exposes_only_observed_rows_as_precise_rul_supervision(self) -> None:
        samples = pd.DataFrame({
            "source_id": ["matr", "matr"],
            "cell_id": ["observed", "censored"],
            "condition_id": ["p", "p"],
            "cycle_id": [1, 1],
            "timestamp_s": [1.0, 1.0],
            "voltage_v": [3.2, 3.2],
            "current_a": [-1.0, -1.0],
            "temperature_c": [25.0, 25.0],
            "soc": [0.9, 0.9],
            "soe": [0.9, 0.9],
            "sot_c": [np.nan, np.nan],
        })
        cycles = pd.DataFrame({
            "source_id": ["matr", "matr"],
            "cell_id": ["observed", "censored"],
            "cycle_id": [1, 1],
            "soh": [0.9, 0.9],
            "rul_cycles": [10.0, np.nan],
            "rul_observed": [1, 0],
            "eol_provenance": ["official_continuation", "right_censored"],
        })
        result = build_experiment_table(samples, cycles)
        precise = result[result["rul_cycles"].notna()]
        self.assertEqual(precise["cell_id"].tolist(), ["observed"])
        self.assertEqual(precise["rul_observed"].tolist(), [1])
        self.assertEqual(precise["eol_provenance"].tolist(), ["official_continuation"])

    def test_v11_gate_counts_three_rul_provenance_classes_and_rejects_censored_supervision(self) -> None:
        summarizer = getattr(corpus_builder, "summarize_rul_provenance", None)
        self.assertIsNotNone(summarizer, "v11 RUL provenance gate is required")
        samples = pd.DataFrame({
            "cell_id": ["cross", "cross", "continued", "censored"],
            "eol_provenance": [
                "observed_eol_crossing", "observed_eol_crossing",
                "official_continuation", "right_censored",
            ],
        })
        cycles = pd.DataFrame({
            "cell_id": ["cross", "continued", "continued", "censored"],
            "eol_provenance": [
                "observed_eol_crossing", "official_continuation",
                "official_continuation", "right_censored",
            ],
            "rul_observed": [1, 1, 1, 0],
            "rul_cycles": [3.0, 2.0, 1.0, np.nan],
        })
        self.assertEqual(summarizer(samples, cycles), {
            "observed_eol_crossing": {"cell_count": 1, "sample_rows": 2, "cycle_rows": 1},
            "official_continuation": {"cell_count": 1, "sample_rows": 1, "cycle_rows": 2},
            "right_censored": {"cell_count": 1, "sample_rows": 1, "cycle_rows": 1},
        })
        invalid = cycles.copy()
        invalid.loc[invalid["cell_id"].eq("censored"), "rul_cycles"] = 7.0
        with self.assertRaisesRegex(ValueError, "observed labels"):
            summarizer(samples, invalid)

    def test_v11_batch2_manifest_requires_exact_official_evidence_and_archive_identity(self) -> None:
        manifest_validator = getattr(stanford, "validate_official_batch2_manifest", None)
        archive_validator = getattr(stanford, "verify_archive_identity", None)
        self.assertIsNotNone(manifest_validator, "official Batch 2 manifest validator is required")
        self.assertIsNotNone(archive_validator, "archive identity verifier is required")
        mapping = [
            {"batch1_cell_id": "b1c0", "batch2_index_zero_based": 7, "batch2_index_one_based": 8, "add_len": 661, "expected_cycle_count": 662, "cycle_life": 663},
            {"batch1_cell_id": "b1c1", "batch2_index_zero_based": 8, "batch2_index_one_based": 9, "add_len": 980, "expected_cycle_count": 981, "cycle_life": 982},
            {"batch1_cell_id": "b1c2", "batch2_index_zero_based": 9, "batch2_index_one_based": 10, "add_len": 1059, "expected_cycle_count": 1060, "cycle_life": 1061},
            {"batch1_cell_id": "b1c3", "batch2_index_zero_based": 15, "batch2_index_one_based": 16, "add_len": 207, "expected_cycle_count": 208, "cycle_life": 209},
            {"batch1_cell_id": "b1c4", "batch2_index_zero_based": 16, "batch2_index_one_based": 17, "add_len": 481, "expected_cycle_count": 482, "cycle_life": 483},
        ]
        evidence = {
            "project_id": "5c48dd2bc625d700019f3204",
            "batch_id": "5c86bf14fa2ede00015ddd83",
            "file_id": "5c86bf13fa2ede00015ddd82",
            "source_url": "https://data.matr.io/1/api/v1/file/5c86bf13fa2ede00015ddd82/download",
            "license": {"label": "CC BY 4", "url": "https://creativecommons.org/licenses/by/4.0/"},
            "byte_count": 2007331155,
            "sha256": "63ab200d09ecb237fee5ef3a5c5db76e3212e3206a0bd92f769e1427fed338b8",
            "mapping_repository": "https://github.com/rdbraatz/data-driven-prediction-of-battery-cycle-life-before-capacity-degradation",
            "mapping_repo_commit": "1ef13d27c66dc3d73affdaa008fbeba5687b2ea4",
            "mapping_file": "LoadData.m",
            "mapping_file_sha256": "7914333f0a963a0742d9fff340f1d4bc2ad912f1b04a236b3ae6c39fedd3623d",
            "official_continuation_mapping": mapping,
        }
        self.assertEqual(manifest_validator(evidence), evidence)
        wrong = dict(evidence, file_id="guessed")
        with self.assertRaisesRegex(ValueError, "official MATR Batch 2 evidence"):
            manifest_validator(wrong)
        with tempfile.TemporaryDirectory() as temp_dir:
            archive = Path(temp_dir) / "batch2.mat"
            archive.write_bytes(b"official-batch2-test")
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            self.assertEqual(archive_validator(archive, archive.stat().st_size, digest), digest)
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                archive_validator(archive, archive.stat().st_size, "0" * 64)

    @staticmethod
    def _first_cycle_feature_references(source_id: str, energy_reference_wh: float) -> pd.DataFrame:
        samples = pd.DataFrame({
            "source_id": [source_id, source_id],
            "chemistry": ["LFP", "LFP"],
            "cell_id": ["cell-1", "cell-1"],
            "session_id": ["session-1", "session-1"],
            "cycle_id": [1, 1],
            "timestamp_s": [0.0, 1.0],
            "voltage_v": [3.3, 3.2],
            "current_a": [-1.0, -1.0],
            "temperature_c": [25.0, 25.1],
            "capacity_reference_ah": [1.1, 1.1],
            "energy_reference_wh": [energy_reference_wh, energy_reference_wh],
            "initial_soc": [1.0, 1.0],
            "initial_soe": [1.0, 1.0],
            "source_hash": ["a" * 64, "a" * 64],
        })
        cycles = pd.DataFrame({
            "source_id": [source_id],
            "cell_id": ["cell-1"],
            "cycle_id": [1],
            "capacity_ah": [1.0],
            "energy_wh": [3.2],
        })
        return add_causal_sample_features(samples, cycles)

    def test_calce_first_cycle_feature_energy_reference_matches_label_reference(self) -> None:
        result = self._first_cycle_feature_references("calce_a123_dynamic_25c", 3.63)
        self.assertTrue(np.allclose(result["previous_energy_wh"], result["energy_reference_wh"]))

    def test_oxford_first_cycle_feature_energy_reference_matches_label_reference(self) -> None:
        result = self._first_cycle_feature_references("oxford_battery_degradation_1", 2.738)
        self.assertTrue(np.allclose(result["previous_energy_wh"], result["energy_reference_wh"]))

    def test_matr_first_cycle_feature_energy_reference_matches_label_reference(self) -> None:
        result = self._first_cycle_feature_references("mit_stanford_fast_charge", 3.63)
        self.assertTrue(np.allclose(result["previous_energy_wh"], result["energy_reference_wh"]))

    @staticmethod
    def _write_minimal_stanford_batch(path: Path) -> None:
        with h5py.File(path, "w") as handle:
            batch = handle.create_group("batch")
            summary = handle.create_group("summary_0")
            summary.create_dataset("cycle", data=np.array([[2.0, 3.0]]))
            cycles = handle.create_group("cycles_0")
            values = {
                "I": ([1.0, -1.0, -1.0], [1.0, -1.0, -1.0]),
                "V": ([3.2, 3.5, 3.0], [3.1, 3.4, 2.9]),
                "T": ([25.0, 25.5, 26.0], [26.0, 26.5, 27.0]),
                "t": ([0.0, 300.0, 600.0], [0.0, 300.0, 600.0]),
                "Qd": ([0.0, 0.0, 1.0], [0.0, 0.0, 0.8]),
                "Qc": ([0.0, 0.5, 0.5], [0.0, 0.4, 0.4]),
            }
            for field, per_cycle in values.items():
                references = []
                for cycle_index, vector in enumerate(per_cycle):
                    dataset = handle.create_dataset(f"{field}_{cycle_index}", data=np.asarray(vector))
                    references.append(dataset.ref)
                cycles.create_dataset(field, data=np.asarray(references, dtype=h5py.ref_dtype)[:, None])
            summary_refs = batch.create_dataset("summary", shape=(1, 1), dtype=h5py.ref_dtype)
            summary_refs[0, 0] = summary.ref
            cycle_refs = batch.create_dataset("cycles", shape=(1, 1), dtype=h5py.ref_dtype)
            cycle_refs[0, 0] = cycles.ref
            policy = handle.create_dataset("policy_0", data=np.asarray([ord(char) for char in "4C(80%)-1C"]))
            policy_refs = batch.create_dataset("policy_readable", shape=(1, 1), dtype=h5py.ref_dtype)
            policy_refs[0, 0] = policy.ref

    def test_stanford_hdf5_loader_preserves_real_cycle_ids_and_charge_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "batch.mat"
            with h5py.File(path, "w") as handle:
                batch = handle.create_group("batch")
                summary = handle.create_group("summary_0")
                summary.create_dataset("cycle", data=np.array([[2.0, 3.0]]))
                cycles = handle.create_group("cycles_0")
                references: dict[str, list[h5py.Reference]] = {
                    key: [] for key in ("I", "V", "T", "t", "Qd", "Qc")
                }
                values = {
                    "I": ([1.0, -1.0, -1.0], [1.0, -1.0, -1.0]),
                    "V": ([3.2, 3.5, 3.0], [3.1, 3.4, 2.9]),
                    "T": ([25.0, 25.5, 26.0], [26.0, 26.5, 27.0]),
                    "t": ([0.0, 10.0, 20.0], [0.0, 12.0, 24.0]),
                    "Qd": ([0.0, 0.0, 1.0], [0.0, 0.0, 0.8]),
                    "Qc": ([0.0, 0.5, 0.5], [0.0, 0.4, 0.4]),
                }
                for field, per_cycle in values.items():
                    for cycle_index, vector in enumerate(per_cycle):
                        dataset = handle.create_dataset(f"{field}_{cycle_index}", data=np.asarray(vector))
                        references[field].append(dataset.ref)
                    cycles.create_dataset(field, data=np.asarray(references[field], dtype=h5py.ref_dtype)[:, None])
                summary_refs = batch.create_dataset("summary", shape=(1, 1), dtype=h5py.ref_dtype)
                summary_refs[0, 0] = summary.ref
                cycle_refs = batch.create_dataset("cycles", shape=(1, 1), dtype=h5py.ref_dtype)
                cycle_refs[0, 0] = cycles.ref
                policy = handle.create_dataset("policy_0", data=np.asarray([ord(char) for char in "4C(80%)-1C"]))
                policy_refs = batch.create_dataset("policy_readable", shape=(1, 1), dtype=h5py.ref_dtype)
                policy_refs[0, 0] = policy.ref

            result = stanford.load_samples(path, "b" * 64, stride=2)
            self.assertEqual(result["cell_id"].unique().tolist(), ["b1c0"])
            self.assertEqual(result["cycle_id"].drop_duplicates().tolist(), [2, 3])
            self.assertEqual(result["condition_id"].unique().tolist(), ["4C(80%)-1C"])
            self.assertEqual(result.groupby("cycle_id")["Discharge_Capacity(Ah)"].max().tolist(), [1.0, 0.8])
            self.assertEqual(result.groupby("cycle_id")["cycle_capacity_ah"].first().tolist(), [1.0, 0.8])
            self.assertEqual(result.groupby("cycle_id")["capacity_reference_ah"].first().tolist(), [1.1, 1.0])
            self.assertEqual(result.groupby("cycle_id")["timestamp_s"].first().tolist(), [600.0, 720.0])
            self.assertEqual(result.groupby("cycle_id")["timestamp_s"].last().tolist(), [1200.0, 1440.0])
            self.assertEqual(result.groupby("cycle_id")["native_cumulative_charge_ah"].last().tolist(), [1.0, 0.8])
            self.assertAlmostEqual(result.groupby("cycle_id")["cycle_energy_wh"].first().iloc[0], 3.0)
            self.assertAlmostEqual(result.groupby("cycle_id")["energy_reference_wh"].first().iloc[1], 3.0)
            self.assertTrue((result["current_a"] <= 0).all())
            validate_canonical_samples(result)

    def test_stanford_capacity_gate_rejects_known_gross_cycle_outliers(self) -> None:
        self.assertTrue(stanford.capacity_is_plausible(1.10))
        self.assertTrue(stanford.capacity_is_plausible(0.88))
        self.assertFalse(stanford.capacity_is_plausible(1.539054))
        self.assertFalse(stanford.capacity_is_plausible(2.884083))

    def test_stanford_native_energy_is_computed_before_stride_subsampling(self) -> None:
        charge, energy = stanford.causal_qd_state(
            np.array([0.0, 0.25, 0.50, 0.75, 1.0]),
            np.array([4.0, 3.75, 3.50, 3.25, 3.0]),
        )
        selected = np.array([0, 2, 4])
        self.assertEqual(charge[selected].tolist(), [0.0, 0.5, 1.0])
        self.assertAlmostEqual(energy[-1], 3.375)
        self.assertAlmostEqual(energy[selected][-1], 3.375)

    def test_corpus_builder_admits_downloaded_stanford_batch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_dir = root / "raw" / "mit_stanford_fast_charge"
            source_dir.mkdir(parents=True)
            archive = source_dir / "batch.mat"
            self._write_minimal_stanford_batch(archive)
            (source_dir / "download_manifest.json").write_text(json.dumps({
                "archive_path": str(archive),
                "sha256": "b" * 64,
            }), encoding="utf-8")

            manifest = build_public_battery_corpus(
                root / "raw", root / "canonical", root / "reports", stride=2,
            )
            stanford_source = next(
                source for source in manifest["sources"]
                if source["source_id"] == "mit_stanford_fast_charge"
            )
            self.assertEqual(manifest["state_label_protocol"], "causal_precycle_reference_v2")
            self.assertTrue(stanford_source["admitted"])
            self.assertEqual(stanford_source["cell_count"], 1)
            samples = pd.read_csv(root / "canonical" / "public_battery_samples.csv")
            self.assertIn("capacity_reference_ah", samples.columns)
            cycles = pd.read_csv(root / "canonical" / "public_battery_cycles.csv")
            self.assertEqual(cycles["cycle_id"].tolist(), [2, 3])
            self.assertEqual(cycles["capacity_ah"].tolist(), [1.0, 0.8])

    def test_all_adapters_emit_stable_canonical_identity_and_units(self) -> None:
        cases = [
            (nasa_alt, {"Time": [1, 0], "Voltage": [3.5, 3.6], "Current": [1, 1], "Temperature": [26, 25]}),
            (oxford, {"t": [1, 0], "V": [3.5, 3.6], "I": [1, 1], "T": [26, 25]}),
            (calce, {"Test_Time(s)": [1, 0], "Voltage(V)": [3.5, 3.6], "Current(A)": [1, 1], "Temperature(C)": [26, 25]}),
            (stanford, {"t": [1, 0], "V": [3.5, 3.6], "I": [1, 1], "T": [26, 25]}),
            (sandia, {"Test_Time_s": [1, 0], "Voltage_V": [3.5, 3.6], "Current_A": [1, 1], "Temperature_C": [26, 25]}),
        ]
        for adapter, columns in cases:
            with self.subTest(adapter=adapter.__name__):
                frame = pd.DataFrame(columns)
                frame["cell_id"] = "cell-01"
                frame["session_id"] = "session-01"
                frame["cycle_id"] = 2
                result = adapter.adapt_samples(frame, source_hash="a" * 64)
                self.assertTrue(set(SAMPLE_REQUIRED_COLUMNS).issubset(result.columns))
                self.assertEqual(result["source_hash"].unique().tolist(), ["a" * 64])
                self.assertTrue(result["timestamp_s"].is_monotonic_increasing)
                validate_canonical_samples(result)

    def test_cycle_reference_attachment_uses_only_previous_completed_cycle(self) -> None:
        frame = pd.DataFrame({
            "source_id": ["x"] * 4,
            "chemistry": ["LFP"] * 4,
            "cell_id": ["c1"] * 4,
            "session_id": ["s1"] * 4,
            "cycle_id": [1, 1, 2, 2],
            "timestamp_s": [0.0, 3600.0, 0.0, 3600.0],
            "voltage_v": [4.0, 4.0, 4.0, 4.0],
            "current_a": [-1.0, -1.0, -1.0, -1.0],
            "temperature_c": [25.0] * 4,
            "Discharge_Capacity(Ah)": [0.0, 0.9, 0.0, 0.8],
            "source_hash": ["a" * 64] * 4,
        })
        result = common.attach_causal_cycle_references(
            frame, nominal_capacity_ah=1.0, nominal_voltage_v=4.0,
        )
        references = result.groupby("cycle_id")["capacity_reference_ah"].first().tolist()
        self.assertEqual(references, [1.0, 0.9])
        self.assertEqual(result.groupby("cycle_id")["energy_reference_wh"].first().tolist(), [4.0, 4.0])

    def test_state_targets_are_group_local_and_future_temperature_does_not_cross_cycle(self) -> None:
        frame = pd.DataFrame({
            "source_id": ["x"] * 6,
            "chemistry": ["LFP"] * 6,
            "cell_id": ["c1"] * 6,
            "session_id": ["s1"] * 6,
            "cycle_id": [1, 1, 1, 2, 2, 2],
            "timestamp_s": [0, 300, 600, 0, 300, 600],
            "voltage_v": [4, 3.8, 3.5, 4, 3.8, 3.5],
            "current_a": [1, 1, 1, 1, 1, 1],
            "temperature_c": [20, 21, 22, 40, 41, 42],
            "capacity_reference_ah": [1.0] * 6,
            "energy_reference_wh": [4.0] * 6,
            "initial_soc": [1.0] * 6,
            "initial_soe": [1.0] * 6,
            "source_hash": ["a" * 64] * 6,
        })
        result = derive_state_targets(frame, horizon_s=300)
        first_cycle = result[result["cycle_id"] == 1]
        self.assertEqual(first_cycle["sot_c"].dropna().tolist(), [21.0, 22.0])
        self.assertNotIn(40.0, first_cycle["sot_c"].dropna().tolist())
        self.assertTrue(result["soc"].dropna().between(0, 1).all())
        self.assertTrue(result["soe"].dropna().between(0, 1).all())

    def test_state_labels_do_not_change_when_only_future_tail_changes(self) -> None:
        frame = pd.DataFrame({
            "source_id": ["x"] * 6,
            "chemistry": ["LFP"] * 6,
            "cell_id": ["short"] * 3 + ["long"] * 3,
            "session_id": ["s"] * 6,
            "cycle_id": [1] * 6,
            "timestamp_s": [0, 3600, 7200, 0, 3600, 7200],
            "voltage_v": [4.0] * 6,
            "current_a": [1.0, 1.0, 1.0, 1.0, 1.0, 4.0],
            "temperature_c": [25.0] * 6,
            "capacity_reference_ah": [4.0] * 6,
            "energy_reference_wh": [16.0] * 6,
            "initial_soc": [1.0] * 6,
            "initial_soe": [1.0] * 6,
            "source_hash": ["a" * 64] * 6,
        })
        result = derive_state_targets(frame, horizon_s=300)
        short = result[result["cell_id"] == "short"].reset_index(drop=True)
        long = result[result["cell_id"] == "long"].reset_index(drop=True)
        self.assertEqual(short.loc[:1, "soc"].tolist(), [1.0, 0.75])
        self.assertEqual(long.loc[:1, "soc"].tolist(), [1.0, 0.75])
        self.assertEqual(short.loc[:1, "soe"].tolist(), long.loc[:1, "soe"].tolist())

    def test_native_cumulative_state_is_preferred_and_remains_causal(self) -> None:
        frame = pd.DataFrame({
            "source_id": ["x"] * 6,
            "chemistry": ["LFP"] * 6,
            "cell_id": ["short"] * 3 + ["long"] * 3,
            "session_id": ["s"] * 6,
            "cycle_id": [1] * 6,
            "timestamp_s": [0, 300, 600, 0, 300, 600],
            "voltage_v": [4.0] * 6,
            "current_a": [100.0] * 6,
            "temperature_c": [25.0] * 6,
            "capacity_reference_ah": [1.0] * 6,
            "energy_reference_wh": [4.0] * 6,
            "initial_soc": [1.0] * 6,
            "initial_soe": [1.0] * 6,
            "native_cumulative_charge_ah": [0.0, 0.25, 0.5, 0.0, 0.25, 1.0],
            "native_cumulative_energy_wh": [0.0, 1.0, 2.0, 0.0, 1.0, 4.0],
            "source_hash": ["a" * 64] * 6,
        })
        result = derive_state_targets(frame, horizon_s=300)
        short = result[result["cell_id"] == "short"].reset_index(drop=True)
        long = result[result["cell_id"] == "long"].reset_index(drop=True)
        self.assertEqual(short.loc[:1, "soc"].tolist(), [1.0, 0.75])
        self.assertEqual(long.loc[:1, "soc"].tolist(), [1.0, 0.75])
        self.assertEqual(short.loc[:1, "soe"].tolist(), [1.0, 0.75])
        self.assertEqual(long.loc[:1, "soe"].tolist(), [1.0, 0.75])

    def test_cycle_targets_use_first_eol_crossing_and_mark_censoring(self) -> None:
        cycles = pd.DataFrame({
            "source_id": ["x"] * 5,
            "chemistry": ["LFP"] * 5,
            "cell_id": ["c1"] * 3 + ["c2"] * 2,
            "cycle_id": [0, 1, 2, 0, 1],
            "capacity_ah": [2.0, 1.8, 1.5, 2.0, 1.9],
            "energy_wh": [7.0, 6.3, 5.2, 7.0, 6.7],
            "source_hash": ["a" * 64] * 5,
        })
        result = derive_cycle_targets(cycles, eol_soh=0.8)
        self.assertTrue(set(CYCLE_REQUIRED_COLUMNS).issubset(result.columns))
        c1 = result[result["cell_id"] == "c1"]
        self.assertEqual(c1["rul_cycles"].tolist(), [2.0, 1.0, 0.0])
        self.assertEqual(c1["rul_observed"].tolist(), [1, 1, 1])
        c2 = result[result["cell_id"] == "c2"]
        self.assertTrue(np.isnan(c2["rul_cycles"]).all())
        self.assertEqual(c2["rul_observed"].tolist(), [0, 0])

    def test_cycle_targets_use_official_observed_eol_cycle_when_available(self) -> None:
        cycles = pd.DataFrame({
            "source_id": ["matr"] * 2,
            "chemistry": ["LFP"] * 2,
            "cell_id": ["c1"] * 2,
            "cycle_id": [2, 3],
            "capacity_ah": [1.07, 1.06],
            "energy_wh": [3.5, 3.4],
            "eol_cycle": [5.0, 5.0],
            "eol_cycle_observed": [1, 1],
            "source_hash": ["a" * 64] * 2,
        })
        result = derive_cycle_targets(cycles, eol_soh=0.8)
        self.assertEqual(result["rul_cycles"].tolist(), [3.0, 2.0])
        self.assertEqual(result["rul_observed"].tolist(), [1, 1])

    def test_file_end_plus_one_is_not_automatically_an_observed_eol(self) -> None:
        cycles = pd.DataFrame({
            "source_id": ["matr"] * 2,
            "chemistry": ["LFP"] * 2,
            "cell_id": ["continued"] * 2,
            "cycle_id": [2, 3],
            "capacity_ah": [1.07, 1.03],
            "energy_wh": [3.5, 3.3],
            "eol_cycle": [4.0, 4.0],
            "eol_cycle_observed": [0, 0],
            "eol_provenance": ["batch_file_end", "batch_file_end"],
            "source_hash": ["a" * 64] * 2,
        })
        result = derive_cycle_targets(cycles, eol_soh=0.8)
        self.assertTrue(result["rul_cycles"].isna().all())
        self.assertEqual(result["rul_observed"].tolist(), [0, 0])

    def test_irregular_cycle_ids_preserve_real_cycle_distance_for_rul(self) -> None:
        cycles = pd.DataFrame({
            "source_id": ["x"] * 3, "chemistry": ["LFP"] * 3, "cell_id": ["c1"] * 3,
            "cycle_id": [0, 100, 300], "capacity_ah": [2.0, 1.9, 1.5],
            "energy_wh": [7.0, 6.5, 5.0], "source_hash": ["a" * 64] * 3,
        })
        result = derive_cycle_targets(cycles, eol_soh=0.8)
        self.assertEqual(result["rul_cycles"].tolist(), [300.0, 200.0, 0.0])

    def test_experiment_table_does_not_repeat_cycle_targets_on_every_sample(self) -> None:
        samples = pd.DataFrame({
            "source_id": ["x", "x"], "cell_id": ["c1", "c1"], "condition_id": ["warm", "warm"],
            "cycle_id": [1, 1], "timestamp_s": [0.0, 1.0], "voltage_v": [4.0, 3.9],
            "current_a": [1.0, 1.0], "temperature_c": [25.0, 25.1],
            "soc": [1.0, 0.9], "soe": [1.0, 0.9], "sot_c": [25.1, np.nan],
        })
        cycles = pd.DataFrame({
            "source_id": ["x"], "cell_id": ["c1"], "cycle_id": [1], "soh": [0.9], "rul_cycles": [5.0],
        })
        result = build_experiment_table(samples, cycles)
        self.assertEqual(int(result["soh"].notna().sum()), 1)
        self.assertEqual(int(result["rul_cycles"].notna().sum()), 1)
        self.assertEqual(int(result["soc"].notna().sum()), 2)


if __name__ == "__main__":
    unittest.main()
