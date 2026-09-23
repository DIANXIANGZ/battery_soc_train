"""CPU PyTorch linear baseline for the SOT lightweight dataset version."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
from typing import Iterable, Mapping, Sequence

import torch

from src.data_processing.non_rul_baseline.build import _rename_no_replace, verify_version


FEATURES = ("voltage", "current")
LABEL_UNIT = "source-native-temperature"
TARGET = "sot"
VERSION_PATH = Path(
    "/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/02_训练数据/05_非RUL独立候选/sot-lightweight-temperature-v1/sot-baseline-v1"
)
CONFIG_PATH = Path(__file__).resolve().parents[3] / "configs" / "training" / "non_rul_baseline" / "sot-lightweight-pytorch-linear.json"
OUTPUT_PATH = Path(
    "/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/03_模型与实验结果/07_SOT轻量基线/sot-lightweight-pytorch-v1/formal"
)
EXPECTED_CONFIG_SHA256 = ""
EXPECTED_SOURCE_ID = "zenodo-13759419-v1"


def json_bytes(payload: object) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def expected_config_payload(
    *,
    version_path: Path | None = None,
    ready_sha256: str = "0" * 64,
    manifest_sha256: str = "0" * 64,
    samples_sha256: str = "0" * 64,
    source_files_sha256: str = "0" * 64,
    split: Mapping[str, object] | None = None,
) -> dict[str, object]:
    dataset_path = version_path or VERSION_PATH
    split_payload = dict(split or {
        "axis": ["physical_cell_id", "condition_id"],
        "policy": "whole_group_train_test",
        "train_groups": [],
        "test_groups": [],
        "validation": None,
        "early_stopping": False,
        "group_row_counts": {},
    })
    return {
        "schema_version": 1,
        "target": TARGET,
        "scope": "source_native_temperature_seen_cells_conditions_only",
        "dataset": {
            "path": str(dataset_path),
            "version": "sot-baseline-v1",
            "source_id": EXPECTED_SOURCE_ID,
            "ready_sha256": ready_sha256,
            "manifest_sha256": manifest_sha256,
            "samples_sha256": samples_sha256,
            "source_files_sha256": source_files_sha256,
        },
        "features": {"names": list(FEATURES), "source_fields": ["电压(V)", "电流(A)"], "current_row_only": True},
        "label": {"name": "sot_source_native_temperature", "source_field": "temp1_1", "unit": LABEL_UNIT},
        "split": split_payload,
        "preprocessing": {"standardize": True, "fit_scope": "training_groups_only"},
        "model": {
            "class": "torch.nn.Linear", "in_features": 2, "out_features": 1,
            "solver": "torch.linalg.lstsq", "dtype": "float64", "device": "cpu", "seed": 42,
        },
        "authorization": {"smoke_flag": "--smoke-authorized", "formal_flag": "--formal-authorized"},
        "execution": {
            "validation": None, "early_stopping": False, "xgboost": False, "torch": True,
            "dataset_modification": False, "git": False,
        },
    }


def _contains_forbidden_semantics(value: object) -> bool:
    tokens = ("rul", "eol", "lifecycle", "trajectory", "cycle_life")
    if isinstance(value, str):
        normalized = value.casefold().replace("-", "_").replace(" ", "_")
        return any(token in normalized for token in tokens)
    if isinstance(value, Mapping):
        return any(_contains_forbidden_semantics(k) or _contains_forbidden_semantics(v) for k, v in value.items())
    if isinstance(value, list):
        return any(_contains_forbidden_semantics(item) for item in value)
    return False


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"CONFIGURATION_NOT_READABLE: {path}") from exc


def load_config(path: Path = CONFIG_PATH) -> dict[str, object]:
    payload = _read_json(Path(path))
    if not isinstance(payload, dict):
        raise ValueError("INVALID_CONFIGURATION_CONTRACT")
    semantic_payload = dict(payload)
    dataset_payload = payload.get("dataset")
    if isinstance(dataset_payload, Mapping):
        semantic_payload["dataset"] = {
            key: value for key, value in dataset_payload.items() if key not in {"path", "ready_sha256", "manifest_sha256", "samples_sha256", "source_files_sha256"}
        }
    if _contains_forbidden_semantics(semantic_payload):
        raise ValueError("INVALID_CONFIGURATION_CONTRACT")
    if payload.get("target") != TARGET or payload.get("schema_version") != 1:
        raise ValueError("INVALID_CONFIGURATION_CONTRACT")
    if payload.get("features") != {"names": list(FEATURES), "source_fields": ["电压(V)", "电流(A)"], "current_row_only": True}:
        raise ValueError("INVALID_CONFIGURATION_CONTRACT")
    if payload.get("label") != {"name": "sot_source_native_temperature", "source_field": "temp1_1", "unit": LABEL_UNIT}:
        raise ValueError("INVALID_CONFIGURATION_CONTRACT")
    dataset = payload.get("dataset")
    split = payload.get("split")
    if not isinstance(dataset, dict) or not isinstance(split, dict):
        raise ValueError("INVALID_CONFIGURATION_CONTRACT")
    for key in ("ready_sha256", "manifest_sha256", "samples_sha256", "source_files_sha256"):
        if not isinstance(dataset.get(key), str) or len(dataset[key]) != 64 or any(c not in "0123456789abcdef" for c in dataset[key]):
            raise ValueError("INVALID_CONFIGURATION_CONTRACT")
    if dataset.get("version") != "sot-baseline-v1" or dataset.get("source_id") != EXPECTED_SOURCE_ID:
        raise ValueError("INVALID_CONFIGURATION_CONTRACT")
    if split.get("validation") is not None or split.get("early_stopping") is not False:
        raise ValueError("INVALID_CONFIGURATION_CONTRACT")
    if payload.get("preprocessing") != {"standardize": True, "fit_scope": "training_groups_only"}:
        raise ValueError("INVALID_CONFIGURATION_CONTRACT")
    if payload.get("model") != {
        "class": "torch.nn.Linear", "in_features": 2, "out_features": 1,
        "solver": "torch.linalg.lstsq", "dtype": "float64", "device": "cpu", "seed": 42,
    }:
        raise ValueError("INVALID_CONFIGURATION_CONTRACT")
    return payload


def validate_split(train_groups: Sequence[str], test_groups: Sequence[str]) -> None:
    train = set(train_groups)
    test = set(test_groups)
    if not train or not test or train & test:
        raise ValueError("GROUP_LEAKAGE")
    if any("|" not in group or not group.split("|", 1)[0] or not group.split("|", 1)[1] for group in train | test):
        raise ValueError("INVALID_GROUP_ID")


def _manifest_and_rows(config: Mapping[str, object]) -> tuple[Path, dict[str, object], dict[str, object]]:
    dataset = config["dataset"]
    assert isinstance(dataset, Mapping)
    version = Path(str(dataset["path"])).resolve()
    if not version.is_dir():
        raise ValueError("DATASET_NOT_FOUND")
    required = {"READY.json", "manifest.json", "samples.csv", "source_files.csv"}
    if {path.name for path in version.iterdir()} != required:
        raise ValueError("DATASET_ARTIFACT_SET_INVALID")
    hashes = {
        "READY.json": _sha256(version / "READY.json"),
        "manifest.json": _sha256(version / "manifest.json"),
        "samples.csv": _sha256(version / "samples.csv"),
        "source_files.csv": _sha256(version / "source_files.csv"),
    }
    expected = {
        "READY.json": dataset["ready_sha256"],
        "manifest.json": dataset["manifest_sha256"],
        "samples.csv": dataset["samples_sha256"],
        "source_files.csv": dataset["source_files_sha256"],
    }
    for name, actual in hashes.items():
        if actual != expected[name]:
            stem = name.split(".", 1)[0].upper()
            raise ValueError(f"{stem}_HASH_MISMATCH")
    ready = _read_json(version / "READY.json")
    manifest = _read_json(version / "manifest.json")
    if not isinstance(ready, dict) or ready.get("manifest_sha256") != hashes["manifest.json"]:
        raise ValueError("READY_MANIFEST_MISMATCH")
    if not isinstance(manifest, dict):
        raise ValueError("MANIFEST_INVALID")
    if manifest.get("target") != TARGET or manifest.get("version") != "sot-baseline-v1":
        raise ValueError("MANIFEST_TARGET_MISMATCH")
    if manifest.get("source_id") != EXPECTED_SOURCE_ID or manifest.get("feature_names") != list(FEATURES):
        raise ValueError("MANIFEST_SOURCE_OR_FEATURE_MISMATCH")
    if manifest.get("label") != {"name": "sot_source_native_temperature", "unit": LABEL_UNIT, "source_field": "temp1_1"}:
        raise ValueError("MANIFEST_LABEL_MISMATCH")
    split = manifest.get("split")
    configured_split = config.get("split")
    if not isinstance(split, dict) or not isinstance(configured_split, dict) or split != configured_split:
        raise ValueError("SPLIT_BINDING_MISMATCH")
    train_groups = split.get("train_groups")
    test_groups = split.get("test_groups")
    if not isinstance(train_groups, list) or not isinstance(test_groups, list):
        raise ValueError("SPLIT_BINDING_MISMATCH")
    validate_split(train_groups, test_groups)
    return version, manifest, split


def _iter_rows(version: Path) -> Iterable[dict[str, str]]:
    with (version / "samples.csv").open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        expected = [
            "target", "source_id", "physical_cell_id", "condition_id", "member_relative_path",
            "source_row_index", "time_s", "voltage", "current", "label",
        ]
        if reader.fieldnames != expected:
            raise ValueError("SAMPLES_HEADER_MISMATCH")
        for row in reader:
            if row.get("target") != TARGET or row.get("source_id") != EXPECTED_SOURCE_ID:
                raise ValueError("SAMPLES_BINDING_MISMATCH")
            for key in ("physical_cell_id", "condition_id", "member_relative_path"):
                if not row.get(key):
                    raise ValueError("SAMPLES_LINEAGE_MISSING")
            try:
                voltage = float(row["voltage"])
                current = float(row["current"])
                label = float(row["label"])
            except (KeyError, TypeError, ValueError):
                raise ValueError("SAMPLES_NUMERIC_INVALID") from None
            if not all(math.isfinite(value) for value in (voltage, current, label)):
                raise ValueError("SAMPLES_NUMERIC_INVALID")
            yield row


def _group(row: Mapping[str, str]) -> str:
    return f"{row['physical_cell_id']}|{row['condition_id']}"


def fit_linear(x_train: torch.Tensor, y_train: torch.Tensor):
    if x_train.ndim != 2 or x_train.shape[1] != 2 or y_train.ndim != 1 or len(x_train) != len(y_train) or not len(x_train):
        raise ValueError("TRAINING_ROWS_INVALID")
    torch.manual_seed(42)
    x_train = x_train.to(dtype=torch.float64, device="cpu")
    y_train = y_train.to(dtype=torch.float64, device="cpu")
    mean = x_train.mean(dim=0)
    scale = x_train.std(dim=0, unbiased=False)
    scale = torch.where(scale > 0, scale, torch.ones_like(scale))
    design = torch.cat(((x_train - mean) / scale, torch.ones((len(x_train), 1), dtype=torch.float64)), dim=1)
    solution = torch.linalg.lstsq(design, y_train.unsqueeze(1)).solution.squeeze(1)
    model = torch.nn.Linear(2, 1, dtype=torch.float64)
    with torch.no_grad():
        model.weight.copy_(solution[:2].reshape(1, 2))
        model.bias.copy_(solution[2].reshape(1))
    return model, mean, scale


def predict(bundle: Mapping[str, object], features: Sequence[float]) -> float:
    model = bundle["model"]
    mean = bundle["mean"]
    scale = bundle["scale"]
    assert isinstance(model, torch.nn.Module)
    x = torch.tensor([list(features)], dtype=torch.float64)
    x = (x - mean) / scale
    with torch.no_grad():
        return float(model(x).reshape(-1)[0])


def load_model(path: Path) -> dict[str, object]:
    payload = torch.load(path, map_location="cpu", weights_only=False)
    model = torch.nn.Linear(2, 1, dtype=torch.float64)
    model.load_state_dict(payload["state_dict"])
    model.eval()
    return {"model": model, "mean": payload["mean"], "scale": payload["scale"], "feature_names": payload["feature_names"]}


def _collect_rows(version: Path, train_groups: set[str], test_groups: set[str], max_rows: int) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    train: list[dict[str, str]] = []
    test: list[dict[str, str]] = []
    train_limit = max(1, max_rows // 2)
    test_limit = max(1, max_rows - train_limit)
    for row in _iter_rows(version):
        group = _group(row)
        if group in train_groups and len(train) < train_limit:
            train.append(row)
        elif group in test_groups and len(test) < test_limit:
            test.append(row)
        if len(train) >= train_limit and len(test) >= test_limit:
            break
    if not train or not test:
        raise ValueError("SMOKE_SPLIT_EMPTY")
    return train, test


def _fit_rows(train_rows: Sequence[Mapping[str, str]]):
    x = torch.tensor([[float(row["voltage"]), float(row["current"])] for row in train_rows], dtype=torch.float64)
    y = torch.tensor([float(row["label"]) for row in train_rows], dtype=torch.float64)
    return fit_linear(x, y)


def _fit_streaming(version: Path, train_groups: set[str]):
    """Fit the same two-feature model without materialising the full CSV."""
    count = 0
    sum_v = sum_i = sum_v2 = sum_i2 = 0.0
    for row in _iter_rows(version):
        if _group(row) not in train_groups:
            continue
        voltage = float(row["voltage"])
        current = float(row["current"])
        count += 1
        sum_v += voltage
        sum_i += current
        sum_v2 += voltage * voltage
        sum_i2 += current * current
    if not count:
        raise ValueError("SPLIT_EMPTY")
    mean_v = sum_v / count
    mean_i = sum_i / count
    var_v = max(sum_v2 / count - mean_v * mean_v, 0.0)
    var_i = max(sum_i2 / count - mean_i * mean_i, 0.0)
    scale_v = math.sqrt(var_v) if var_v > 0 else 1.0
    scale_i = math.sqrt(var_i) if var_i > 0 else 1.0
    xtx = [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]
    xty = [0.0, 0.0, 0.0]
    for row in _iter_rows(version):
        if _group(row) not in train_groups:
            continue
        vector = (
            (float(row["voltage"]) - mean_v) / scale_v,
            (float(row["current"]) - mean_i) / scale_i,
            1.0,
        )
        label = float(row["label"])
        for i in range(3):
            xty[i] += vector[i] * label
            for j in range(3):
                xtx[i][j] += vector[i] * vector[j]
    solution = torch.linalg.lstsq(
        torch.tensor(xtx, dtype=torch.float64),
        torch.tensor(xty, dtype=torch.float64).unsqueeze(1),
    ).solution.squeeze(1)
    model = torch.nn.Linear(2, 1, dtype=torch.float64)
    with torch.no_grad():
        model.weight.copy_(solution[:2].reshape(1, 2))
        model.bias.copy_(solution[2].reshape(1))
    return model, torch.tensor([mean_v, mean_i], dtype=torch.float64), torch.tensor([scale_v, scale_i], dtype=torch.float64), count


def _write_artifacts(output: Path, model, mean, scale, train_rows, test_rows, config_sha: str, dataset_hashes: Mapping[str, str], stage: str, split: Mapping[str, object]) -> dict[str, object]:
    output.mkdir(parents=True, exist_ok=True)
    torch.save({"state_dict": model.state_dict(), "mean": mean, "scale": scale, "feature_names": list(FEATURES)}, output / "model_state.pt")
    predictions_path = output / "predictions.csv"
    absolute_errors: list[float] = []
    squared_errors: list[float] = []
    with predictions_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["physical_cell_id", "condition_id", "member_relative_path", "source_row_index", "voltage", "current", "label", "prediction"])
        writer.writeheader()
        for row in test_rows:
            prediction = predict({"model": model, "mean": mean, "scale": scale}, [float(row["voltage"]), float(row["current"])])
            label = float(row["label"])
            absolute_errors.append(abs(prediction - label))
            squared_errors.append((prediction - label) ** 2)
            writer.writerow({**{name: row[name] for name in ("physical_cell_id", "condition_id", "member_relative_path", "source_row_index", "voltage", "current", "label")}, "prediction": prediction})
    metrics = {
        "stage": stage, "target": TARGET, "scope": "source-native-temperature_seen_cells_conditions_only",
        "label_unit": LABEL_UNIT, "train_rows": len(train_rows), "test_rows": len(test_rows),
        "mae": sum(absolute_errors) / len(absolute_errors),
        "rmse": math.sqrt(sum(squared_errors) / len(squared_errors)),
        "validation": None, "early_stopping": False,
    }
    (output / "metrics.json").write_bytes(json_bytes(metrics))
    (output / "training.log").write_text(f"stage={stage}\nmodel=torch.nn.Linear(2,1)\nsolver=torch.linalg.lstsq\nrows_train={len(train_rows)}\nrows_test={len(test_rows)}\n", encoding="utf-8")
    run_manifest = {
        "schema_version": 1, "target": TARGET, "stage": stage, "scope": metrics["scope"],
        "label_unit": LABEL_UNIT, "features": list(FEATURES), "config_sha256": config_sha,
        "dataset": dataset_hashes, "split": dict(split), "artifacts": ["model_state.pt", "metrics.json", "predictions.csv", "training.log", "run_manifest.json"],
    }
    (output / "run_manifest.json").write_bytes(json_bytes(run_manifest))
    return metrics


def _write_streaming_artifacts(
    output: Path,
    version: Path,
    test_groups: set[str],
    model,
    mean,
    scale,
    train_count: int,
    config_sha: str,
    dataset_hashes: Mapping[str, str],
    stage: str,
    split: Mapping[str, object],
) -> tuple[dict[str, object], list[float], float]:
    """Write formal artifacts in one bounded-memory pass over test rows."""
    output.mkdir(parents=True, exist_ok=True)
    torch.save({"state_dict": model.state_dict(), "mean": mean, "scale": scale, "feature_names": list(FEATURES)}, output / "model_state.pt")
    predictions_path = output / "predictions.csv"
    test_count = 0
    absolute_error_sum = 0.0
    squared_error_sum = 0.0
    first_features: list[float] | None = None
    first_prediction = 0.0
    with predictions_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["physical_cell_id", "condition_id", "member_relative_path", "source_row_index", "voltage", "current", "label", "prediction"])
        writer.writeheader()
        for row in _iter_rows(version):
            if _group(row) not in test_groups:
                continue
            voltage = float(row["voltage"])
            current = float(row["current"])
            label = float(row["label"])
            prediction = predict({"model": model, "mean": mean, "scale": scale}, [voltage, current])
            error = prediction - label
            test_count += 1
            absolute_error_sum += abs(error)
            squared_error_sum += error * error
            if first_features is None:
                first_features = [voltage, current]
                first_prediction = prediction
            writer.writerow({
                **{name: row[name] for name in ("physical_cell_id", "condition_id", "member_relative_path", "source_row_index", "voltage", "current", "label")},
                "prediction": prediction,
            })
    if not test_count or first_features is None:
        raise ValueError("SPLIT_EMPTY")
    metrics = {
        "stage": stage, "target": TARGET, "scope": "source-native-temperature_seen_cells_conditions_only",
        "label_unit": LABEL_UNIT, "train_rows": train_count, "test_rows": test_count,
        "mae": absolute_error_sum / test_count,
        "rmse": math.sqrt(squared_error_sum / test_count),
        "validation": None, "early_stopping": False,
    }
    (output / "metrics.json").write_bytes(json_bytes(metrics))
    (output / "training.log").write_text(f"stage={stage}\nmodel=torch.nn.Linear(2,1)\nsolver=torch.linalg.lstsq\nrows_train={train_count}\nrows_test={test_count}\n", encoding="utf-8")
    run_manifest = {
        "schema_version": 1, "target": TARGET, "stage": stage, "scope": metrics["scope"],
        "label_unit": LABEL_UNIT, "features": list(FEATURES), "config_sha256": config_sha,
        "dataset": dataset_hashes, "split": dict(split), "artifacts": ["model_state.pt", "metrics.json", "predictions.csv", "training.log", "run_manifest.json"],
    }
    (output / "run_manifest.json").write_bytes(json_bytes(run_manifest))
    return metrics, first_features, first_prediction


def run_training(output_path: Path, *, stage: str, smoke_authorized: bool = False, formal_authorized: bool = False, max_rows: int | None = None) -> dict[str, object]:
    if stage == "smoke" and not smoke_authorized:
        raise ValueError("smoke_authorization_required")
    if stage == "formal" and not formal_authorized:
        raise ValueError("formal_authorization_required")
    if stage not in {"smoke", "formal"}:
        raise ValueError("INVALID_STAGE")
    config = load_config(CONFIG_PATH)
    config_sha = _sha256(CONFIG_PATH)
    if EXPECTED_CONFIG_SHA256 and config_sha != EXPECTED_CONFIG_SHA256:
        raise ValueError("CONFIG_HASH_MISMATCH")
    version, manifest, split = _manifest_and_rows(config)
    dataset = config["dataset"]
    assert isinstance(dataset, Mapping)
    output = Path(output_path).resolve()
    if output.exists():
        raise FileExistsError(f"output_exists: {output}")
    staging = output.parent / f".{output.name}.staging-{os.getpid()}"
    if staging.exists():
        raise FileExistsError(f"staging_exists: {staging}")
    train_groups = set(split["train_groups"])
    test_groups = set(split["test_groups"])
    try:
        dataset_hashes = {key: dataset[key] for key in ("ready_sha256", "manifest_sha256", "samples_sha256", "source_files_sha256")}
        if max_rows is not None:
            train_rows, test_rows = _collect_rows(version, train_groups, test_groups, max_rows)
            model, mean, scale = _fit_rows(train_rows)
            staging.mkdir(parents=True, exist_ok=False)
            metrics = _write_artifacts(staging, model, mean, scale, train_rows, test_rows, config_sha, dataset_hashes, stage, split)
            first_test_features = [float(test_rows[0]["voltage"]), float(test_rows[0]["current"])]
            expected_first_prediction = predict({"model": model, "mean": mean, "scale": scale}, first_test_features)
        else:
            model, mean, scale, train_count = _fit_streaming(version, train_groups)
            staging.mkdir(parents=True, exist_ok=False)
            metrics, first_test_features, expected_first_prediction = _write_streaming_artifacts(
                staging, version, test_groups, model, mean, scale, train_count,
                config_sha, dataset_hashes, stage, split,
            )
        reloaded = load_model(staging / "model_state.pt")
        if abs(predict(reloaded, first_test_features) - expected_first_prediction) > 1e-10:
            raise ValueError("MODEL_RELOAD_MISMATCH")
        _rename_no_replace(staging, output)
        return {"status": "SOT_LIGHTWEIGHT_SMOKE_PASS" if stage == "smoke" else "SOT_LIGHTWEIGHT_FORMAL_PASS", "metrics": metrics, "output": str(output)}
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def main(argv: Sequence[str] | None = None) -> int:
    global CONFIG_PATH
    parser = argparse.ArgumentParser(description="SOT lightweight PyTorch linear baseline")
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--stage", choices=("smoke", "formal"), required=True)
    parser.add_argument("--smoke-authorized", action="store_true")
    parser.add_argument("--formal-authorized", action="store_true")
    parser.add_argument("--max-rows", type=int)
    args = parser.parse_args(argv)
    CONFIG_PATH = args.config
    result = run_training(args.output, stage=args.stage, smoke_authorized=args.smoke_authorized, formal_authorized=args.formal_authorized, max_rows=args.max_rows)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


__all__ = [
    "CONFIG_PATH", "FEATURES", "EXPECTED_CONFIG_SHA256", "LABEL_UNIT", "OUTPUT_PATH", "TARGET", "VERSION_PATH",
    "expected_config_payload", "fit_linear", "json_bytes", "load_config", "load_model", "main", "predict",
    "run_training", "validate_split", "verify_version",
]


if __name__ == "__main__":
    raise SystemExit(main())
