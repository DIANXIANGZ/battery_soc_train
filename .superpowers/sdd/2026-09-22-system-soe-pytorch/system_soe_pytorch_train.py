#!/usr/bin/env python3
"""Fixed PyTorch linear baseline for the approved system-level SOE version."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any, Mapping, Sequence

import torch


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_processing.non_rul_baseline.build import _rename_no_replace, verify_version  # noqa: E402


VERSION_PATH = Path(
    "/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/02_训练数据/"
    "05_非RUL独立候选/system_soe-baseline-v1"
)
CONFIG_PATH = (
    PROJECT_ROOT
    / "configs/training/non_rul_baseline/system-soe-pytorch-linear-formal.json"
)
OUTPUT_PATH = Path(
    "/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/03_模型与实验结果/"
    "08_系统SOE轻量基线/system_soe-baseline-v1/pytorch-linear-formal-v1"
)
SMOKE_PATH = Path("/private/tmp/system-soe-pytorch-smoke-20260922-v1")
EXPECTED_CONFIG_SHA256 = "a8892c2cf159e88c2d2c9c6cf6ff45bb822eb84f24515234d7cc01443cf72e63"
EXPECTED_HASHES = {
    "READY.json": "c18455709c3c7977e2c81ebcca95bf4d4de427f117d820a5f515fe44d2c6d6cf",
    "manifest.json": "72c4cb27e018c8e6fc592fe924ef79316dd29b175a6f51c6d06bf39dc4570a90",
    "samples.csv": "d6abe22b5b3040bb39977263bfb40f1e2e77106f6e9ab7e600784513ee0b0e8e",
    "source_files.csv": "8e4ef51edcf3e74d1ab5cd2bc77a734b14335dd31b04f192a64995e3f35b1601",
}
EXPECTED_SOURCE_ID = "zenodo-8381142-v1.0"
EXPECTED_ROW_COUNT = 26_138
EXPECTED_TRAIN_ROWS = 21_205
EXPECTED_TEST_ROWS = 4_933
EXPECTED_TRAIN_GROUPS = 238
EXPECTED_TEST_GROUPS = 60
FEATURES = ("SoC", "Ptcb", "Ptei")
HEADER = (
    "target", "source_id", "cell_id", "session_id", "condition_id",
    "cycle_index", "time_s", *FEATURES, "label",
)
SYSTEM_MARKER = "CBES_SYSTEM_NOT_CELL"
SEED = 42


@dataclass(frozen=True)
class Sample:
    source_row_index: int
    session_id: str
    features: tuple[float, float, float]
    label: float


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def expected_config_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "FORMAL_FIXED_CONFIGURATION",
        "target": "system_soe",
        "scope": "community_storage_system_only_not_cell_level",
        "dataset": {
            "version": "system_soe-baseline-v1",
            "path": str(VERSION_PATH),
            "source_id": EXPECTED_SOURCE_ID,
            "row_count": EXPECTED_ROW_COUNT,
            "ready_sha256": EXPECTED_HASHES["READY.json"],
            "manifest_sha256": EXPECTED_HASHES["manifest.json"],
            "samples_sha256": EXPECTED_HASHES["samples.csv"],
            "source_files_sha256": EXPECTED_HASHES["source_files.csv"],
        },
        "features": {
            "names": list(FEATURES),
            "current_row_only": True,
            "label": "soe_source_value",
            "label_unit": "unspecified_source_unit",
        },
        "split": {
            "axis": "RequID",
            "source": "dataset_manifest",
            "train_groups": EXPECTED_TRAIN_GROUPS,
            "test_groups": EXPECTED_TEST_GROUPS,
            "train_rows": EXPECTED_TRAIN_ROWS,
            "test_rows": EXPECTED_TEST_ROWS,
            "validation": None,
            "early_stopping": False,
        },
        "preprocessing": {"standardize": True, "fit_scope": "training_groups_only"},
        "model": {
            "class": "torch.nn.Linear",
            "in_features": 3,
            "out_features": 1,
            "solver": "torch.linalg.lstsq",
            "dtype": "float64",
            "device": "cpu",
            "seed": SEED,
        },
        "authorization": {
            "smoke_flag": "--smoke-authorized",
            "formal_flag": "--formal-authorized",
        },
        "execution": {
            "smoke_path": str(SMOKE_PATH),
            "formal_path": str(OUTPUT_PATH),
            "xgboost": False,
            "dataset_modification": False,
            "git": False,
        },
    }


def _read_json(path: Path, reason: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(reason) from error
    if not isinstance(value, dict):
        raise ValueError(reason)
    return value


def _validate_config() -> dict[str, Any]:
    if not CONFIG_PATH.is_file() or sha256_file(CONFIG_PATH) != EXPECTED_CONFIG_SHA256:
        raise ValueError("config_fingerprint_mismatch")
    payload = _read_json(CONFIG_PATH, "config_invalid")
    if payload != expected_config_payload():
        raise ValueError("config_contract_mismatch")
    return payload


def validate_split(train_groups: Sequence[str], test_groups: Sequence[str]) -> None:
    train = set(train_groups)
    test = set(test_groups)
    if not train or not test or train & test:
        raise ValueError("group_leakage")
    if len(train) != len(train_groups) or len(test) != len(test_groups):
        raise ValueError("duplicate_group")


def _validate_dataset() -> tuple[dict[str, Any], tuple[str, ...], tuple[str, ...]]:
    expected_names = set(EXPECTED_HASHES)
    if not VERSION_PATH.is_dir() or {path.name for path in VERSION_PATH.iterdir()} != expected_names:
        raise ValueError("version_contents_mismatch")
    for name, expected in EXPECTED_HASHES.items():
        if sha256_file(VERSION_PATH / name) != expected:
            raise ValueError(f"{name}_fingerprint_mismatch")
    ready = _read_json(VERSION_PATH / "READY.json", "ready_invalid")
    manifest = _read_json(VERSION_PATH / "manifest.json", "manifest_invalid")
    if ready != {"manifest_sha256": EXPECTED_HASHES["manifest.json"], "schema_version": 1}:
        raise ValueError("ready_binding_mismatch")
    if verify_version(VERSION_PATH, expected_version="system_soe-baseline-v1"):
        raise ValueError("version_verification_failed")
    if (
        manifest.get("target") != "system_soe"
        or manifest.get("source_id") != EXPECTED_SOURCE_ID
        or manifest.get("version") != "system_soe-baseline-v1"
        or manifest.get("row_count") != EXPECTED_ROW_COUNT
        or manifest.get("feature_names") != list(FEATURES)
        or manifest.get("files") != {
            "samples.csv": EXPECTED_HASHES["samples.csv"],
            "source_files.csv": EXPECTED_HASHES["source_files.csv"],
        }
    ):
        raise ValueError("manifest_contract_mismatch")
    metadata = manifest.get("target_metadata")
    if not isinstance(metadata, Mapping) or metadata.get("scope") != "community_storage_system_only_not_cell_level":
        raise ValueError("scope_mismatch")
    label = metadata.get("label")
    if label != {"name": "soe_source_value", "source_field": "SoE", "unit": "unspecified_source_unit"}:
        raise ValueError("label_contract_mismatch")
    split = metadata.get("split")
    if not isinstance(split, Mapping):
        raise ValueError("split_contract_mismatch")
    train_groups = split.get("train_group_ids")
    test_groups = split.get("test_group_ids")
    if not isinstance(train_groups, list) or not isinstance(test_groups, list):
        raise ValueError("split_contract_mismatch")
    validate_split(train_groups, test_groups)
    if (
        len(train_groups) != EXPECTED_TRAIN_GROUPS
        or len(test_groups) != EXPECTED_TEST_GROUPS
        or split.get("train_row_count") != EXPECTED_TRAIN_ROWS
        or split.get("test_row_count") != EXPECTED_TEST_ROWS
        or split.get("validation", "missing") is not None
    ):
        raise ValueError("split_contract_mismatch")
    return manifest, tuple(train_groups), tuple(test_groups)


def _number(value: str, row_index: int) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"non_numeric_row:{row_index}") from error
    if not math.isfinite(result):
        raise ValueError(f"non_finite_row:{row_index}")
    return result


def _read_samples(train_groups: Sequence[str], test_groups: Sequence[str]) -> tuple[list[Sample], list[Sample]]:
    train_set = set(train_groups)
    test_set = set(test_groups)
    train_rows: list[Sample] = []
    test_rows: list[Sample] = []
    with (VERSION_PATH / "samples.csv").open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != HEADER:
            raise ValueError("samples_header_mismatch")
        for source_row_index, row in enumerate(reader):
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"samples_shape_invalid:{source_row_index}")
            if (
                row["target"] != "system_soe"
                or row["source_id"] != EXPECTED_SOURCE_ID
                or row["cell_id"] != SYSTEM_MARKER
            ):
                raise ValueError(f"sample_identity_mismatch:{source_row_index}")
            session = row["session_id"]
            if session in train_set:
                destination = train_rows
            elif session in test_set:
                destination = test_rows
            else:
                raise ValueError(f"unknown_group:{source_row_index}")
            features = tuple(_number(row[name], source_row_index) for name in FEATURES)
            destination.append(Sample(source_row_index, session, features, _number(row["label"], source_row_index)))
    if len(train_rows) != EXPECTED_TRAIN_ROWS or len(test_rows) != EXPECTED_TEST_ROWS:
        raise ValueError("split_row_count_mismatch")
    return train_rows, test_rows


def fit_linear(x_train: torch.Tensor, y_train: torch.Tensor) -> tuple[torch.nn.Linear, torch.Tensor, torch.Tensor]:
    if x_train.ndim != 2 or x_train.shape[1] != 3 or y_train.ndim != 1 or x_train.shape[0] != y_train.shape[0]:
        raise ValueError("training_shape_invalid")
    if x_train.shape[0] < 1 or not torch.isfinite(x_train).all() or not torch.isfinite(y_train).all():
        raise ValueError("training_values_invalid")
    mean = x_train.mean(dim=0)
    scale = x_train.std(dim=0, unbiased=False)
    scale = torch.where(scale > 0, scale, torch.ones_like(scale))
    standardized = (x_train - mean) / scale
    design = torch.cat((standardized, torch.ones((standardized.shape[0], 1), dtype=torch.float64)), dim=1)
    solution = torch.linalg.lstsq(design, y_train.reshape(-1, 1)).solution.reshape(-1)
    if solution.shape[0] != 4 or not torch.isfinite(solution).all():
        raise ValueError("linear_solution_invalid")
    model = torch.nn.Linear(3, 1, dtype=torch.float64)
    with torch.no_grad():
        model.weight.copy_(solution[:3].reshape(1, 3))
        model.bias.copy_(solution[3:].reshape(1))
    return model, mean, scale


def _predict_tensor(model: torch.nn.Linear, mean: torch.Tensor, scale: torch.Tensor, x: torch.Tensor) -> torch.Tensor:
    with torch.no_grad():
        result = model((x - mean) / scale).reshape(-1)
    if not torch.isfinite(result).all():
        raise ValueError("prediction_not_finite")
    return result


def load_model(path: Path) -> dict[str, Any]:
    payload = torch.load(Path(path), map_location="cpu", weights_only=False)
    if not isinstance(payload, dict) or payload.get("features") != list(FEATURES):
        raise ValueError("saved_model_invalid")
    model = torch.nn.Linear(3, 1, dtype=torch.float64)
    model.load_state_dict(payload["state_dict"])
    payload["model"] = model
    return payload


def predict(bundle: Mapping[str, Any], features: Sequence[float]) -> float:
    x = torch.tensor([list(features)], dtype=torch.float64)
    return float(_predict_tensor(bundle["model"], bundle["mean"], bundle["scale"], x)[0].item())


def _metrics(actual: torch.Tensor, predicted: torch.Tensor) -> tuple[float, float]:
    error = predicted - actual
    return float(error.abs().mean().item()), float(torch.sqrt((error * error).mean()).item())


def run_training(
    output_dir: str | Path,
    *,
    stage: str,
    smoke_authorized: bool = False,
    formal_authorized: bool = False,
) -> dict[str, Any]:
    if stage == "smoke":
        if not smoke_authorized:
            raise ValueError("smoke_authorization_required")
    elif stage == "formal":
        if not formal_authorized:
            raise ValueError("formal_authorization_required")
    else:
        raise ValueError("stage_invalid")
    output = Path(output_dir).resolve()
    expected_output = SMOKE_PATH.resolve() if stage == "smoke" else OUTPUT_PATH.resolve()
    if output != expected_output:
        raise ValueError("output_path_mismatch")
    if output.exists():
        raise FileExistsError("output_exists")

    config = _validate_config()
    _manifest, train_groups, test_groups = _validate_dataset()
    train_rows, test_rows = _read_samples(train_groups, test_groups)
    if stage == "smoke":
        train_rows = train_rows[:16]
        test_rows = test_rows[:16]

    torch.manual_seed(SEED)
    x_train = torch.tensor([row.features for row in train_rows], dtype=torch.float64)
    y_train = torch.tensor([row.label for row in train_rows], dtype=torch.float64)
    x_test = torch.tensor([row.features for row in test_rows], dtype=torch.float64)
    y_test = torch.tensor([row.label for row in test_rows], dtype=torch.float64)
    model, mean, scale = fit_linear(x_train, y_train)
    predicted = _predict_tensor(model, mean, scale, x_test)
    mae, rmse = _metrics(y_test, predicted)

    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.staging-", dir=output.parent))
    try:
        model_path = staging / "model_state.pt"
        torch.save({
            "state_dict": model.state_dict(),
            "mean": mean,
            "scale": scale,
            "features": list(FEATURES),
            "target": "system_soe",
            "label": "soe_source_value",
            "unit": "unspecified_source_unit",
        }, model_path)
        bundle = load_model(model_path)
        reloaded = torch.tensor(
            [predict(bundle, row.features) for row in test_rows], dtype=torch.float64
        )
        max_reload_diff = float((predicted - reloaded).abs().max().item())
        if max_reload_diff > 1e-10:
            raise ValueError("model_reload_prediction_mismatch")

        metrics = {
            "status": "SYSTEM_SOE_PYTORCH_SMOKE_PASS" if stage == "smoke" else "SYSTEM_SOE_PYTORCH_FORMAL_PASS",
            "stage": stage,
            "target": "system_soe",
            "scope": "community_storage_system_only_not_cell_level",
            "label": "soe_source_value",
            "unit": "unspecified_source_unit",
            "train_rows": len(train_rows),
            "test_rows": len(test_rows),
            "mae": mae,
            "rmse": rmse,
            "max_reload_prediction_diff": max_reload_diff,
        }
        (staging / "metrics.json").write_bytes(json_bytes(metrics))
        with (staging / "predictions.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=("source_row_index", "session_id", *FEATURES, "actual", "prediction"),
            )
            writer.writeheader()
            for row, value in zip(test_rows, predicted):
                writer.writerow({
                    "source_row_index": row.source_row_index,
                    "session_id": row.session_id,
                    **dict(zip(FEATURES, row.features)),
                    "actual": row.label,
                    "prediction": float(value.item()),
                })
        log = "\n".join((
            f"status={metrics['status']}", f"stage={stage}", "target=system_soe",
            f"train_rows={len(train_rows)}", f"test_rows={len(test_rows)}",
            f"mae={mae}", f"rmse={rmse}", "device=cpu", "xgboost=false",
            "scope=community_storage_system_only_not_cell_level",
        )) + "\n"
        (staging / "training.log").write_text(log, encoding="utf-8")
        artifacts = {
            name: {"bytes": (staging / name).stat().st_size, "sha256": sha256_file(staging / name)}
            for name in ("model_state.pt", "metrics.json", "predictions.csv", "training.log")
        }
        run_manifest = {
            "schema_version": 1,
            "status": metrics["status"],
            "stage": stage,
            "target": "system_soe",
            "scope": "community_storage_system_only_not_cell_level",
            "label": {"name": "soe_source_value", "unit": "unspecified_source_unit"},
            "features": list(FEATURES),
            "model": "torch.nn.Linear(3,1)",
            "solver": "torch.linalg.lstsq",
            "seed": SEED,
            "config_path": str(CONFIG_PATH.resolve()),
            "config_sha256": sha256_file(CONFIG_PATH),
            "runner_path": str(Path(__file__).resolve()),
            "runner_sha256": sha256_file(Path(__file__).resolve()),
            "dataset_path": str(VERSION_PATH.resolve()),
            "dataset_hashes": dict(EXPECTED_HASHES),
            "split": {
                "train_groups": len(set(row.session_id for row in train_rows)),
                "test_groups": len(set(row.session_id for row in test_rows)),
                "train_rows": len(train_rows),
                "test_rows": len(test_rows),
                "validation": None,
                "early_stopping": False,
            },
            "metrics": {"mae": mae, "rmse": rmse},
            "artifacts": artifacts,
            "safety": {
                "other_targets_read": False,
                "frozen_assets_read": False,
                "dataset_version_modified": False,
                "xgboost_imported": False,
                "git_action": False,
            },
            "configuration": config,
        }
        (staging / "run_manifest.json").write_bytes(json_bytes(run_manifest))
        _rename_no_replace(staging, output)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return {"status": metrics["status"], "metrics": metrics, "output_dir": str(output)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the fixed system-level SOE PyTorch baseline.")
    parser.add_argument("--stage", required=True, choices=("smoke", "formal"))
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--smoke-authorized", action="store_true")
    parser.add_argument("--formal-authorized", action="store_true")
    arguments = parser.parse_args(argv)
    result = run_training(
        arguments.output_dir,
        stage=arguments.stage,
        smoke_authorized=arguments.smoke_authorized,
        formal_authorized=arguments.formal_authorized,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
