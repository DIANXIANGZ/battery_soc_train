from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRAINER_PATH = PROJECT_ROOT / "src/training/non_rul_baseline/sot_lightweight_pytorch.py"
CONFIG_PATH = PROJECT_ROOT / "configs/training/non_rul_baseline/sot-lightweight-pytorch-linear.json"
HEADER = (
    "target", "source_id", "physical_cell_id", "condition_id",
    "member_relative_path", "source_row_index", "time_s", "voltage", "current", "label",
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _trainer():
    assert TRAINER_PATH.is_file(), "SOT轻量PyTorch入口尚未实现"
    spec = importlib.util.spec_from_file_location("sot_lightweight_pytorch_under_test", TRAINER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _synthetic(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    trainer = _trainer()
    monkeypatch.setattr(trainer, "EXPECTED_SOURCE_ID", "synthetic-sot-v1")
    version = tmp_path / "sot-baseline-v1"
    version.mkdir(parents=True)
    samples = version / "samples.csv"
    rows = []
    groups = [
        ("cell_a", "condition_a", "train-a"),
        ("cell_b", "condition_b", "train-b"),
        ("cell_c", "condition_c", "test-c"),
    ]
    for group_index, (cell, condition, member) in enumerate(groups):
        for row_index in range(4):
            voltage = float(group_index + row_index + 1)
            current = float(-row_index - 1)
            rows.append((
                "sot", "synthetic-sot-v1", cell, condition, member,
                row_index + 2, row_index + 2, voltage, current,
                2.0 * voltage - 0.5 * current,
            ))
    with samples.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        writer.writerows(rows)
    source = tmp_path / "source.zip"
    source.write_bytes(b"synthetic source")
    source_files = version / "source_files.csv"
    source_files.write_text(
        f"path,size_bytes,sha256\n{source},{source.stat().st_size},{_sha(source)}\n",
        encoding="utf-8",
    )
    split = {
        "axis": ["physical_cell_id", "condition_id"],
        "policy": "whole_group_train_test",
        "train_groups": ["cell_a|condition_a", "cell_b|condition_b"],
        "test_groups": ["cell_c|condition_c"],
        "validation": None,
        "early_stopping": False,
        "group_row_counts": {
            "cell_a|condition_a": 4,
            "cell_b|condition_b": 4,
            "cell_c|condition_c": 4,
        },
    }
    manifest_payload = {
        "schema_version": 1,
        "version": "sot-baseline-v1",
        "target": "sot",
        "source_id": "synthetic-sot-v1",
        "feature_names": ["voltage", "current"],
        "row_count": 12,
        "files": {"samples.csv": _sha(samples), "source_files.csv": _sha(source_files)},
        "scope": "source_native_temperature_seen_cells_conditions_only",
        "label": {"name": "sot_source_native_temperature", "unit": "source-native-temperature", "source_field": "temp1_1"},
        "features": {"source_fields": ["电压(V)", "电流(A)"], "current_row_only": True},
        "split": split,
        "source_audit": {"csv_member_count": 3, "accepted_member_count": 3, "rejected_member_count": 0, "rejected_members": []},
        "training": {"formal_training_authorized": False},
    }
    manifest = version / "manifest.json"
    manifest.write_bytes(trainer.json_bytes(manifest_payload))
    ready = version / "READY.json"
    ready.write_bytes(trainer.json_bytes({"schema_version": 1, "manifest_sha256": _sha(manifest)}))

    config = tmp_path / "config.json"
    config_payload = trainer.expected_config_payload(
        version_path=version,
        ready_sha256=_sha(ready),
        manifest_sha256=_sha(manifest),
        samples_sha256=_sha(samples),
        source_files_sha256=_sha(source_files),
        split=split,
    )
    config.write_bytes(trainer.json_bytes(config_payload))
    monkeypatch.setattr(trainer, "CONFIG_PATH", config)
    monkeypatch.setattr(trainer, "EXPECTED_CONFIG_SHA256", _sha(config))
    return trainer, version, config


def test_missing_authorization_is_rejected(tmp_path: Path) -> None:
    trainer = _trainer()
    with pytest.raises(ValueError, match="authorization_required"):
        trainer.run_training(tmp_path / "smoke", stage="smoke", smoke_authorized=False)
    with pytest.raises(ValueError, match="authorization_required"):
        trainer.run_training(tmp_path / "formal", stage="formal", formal_authorized=False)


def test_group_overlap_is_rejected() -> None:
    trainer = _trainer()
    with pytest.raises(ValueError, match="GROUP_LEAKAGE"):
        trainer.validate_split(["cell_a|condition_a"], ["cell_a|condition_a"])


def test_fit_standardization_uses_training_rows_only() -> None:
    trainer = _trainer()
    import torch

    x = torch.tensor([[1.0, -1.0], [3.0, -3.0]], dtype=torch.float64)
    y = torch.tensor([1.0, 2.0], dtype=torch.float64)
    model, mean, scale = trainer.fit_linear(x, y)
    assert torch.equal(mean, x.mean(dim=0))
    assert torch.all(scale > 0)
    assert isinstance(model, torch.nn.Linear)


def test_synthetic_formal_writes_exact_artifacts_and_reload_matches(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    trainer, version, config = _synthetic(monkeypatch, tmp_path)
    output = tmp_path / "formal-output"
    result = trainer.run_training(output, stage="formal", formal_authorized=True)
    assert result["status"] == "SOT_LIGHTWEIGHT_FORMAL_PASS"
    assert {path.name for path in output.iterdir()} == {
        "model_state.pt", "metrics.json", "predictions.csv", "training.log", "run_manifest.json",
    }
    predictions = list(csv.DictReader((output / "predictions.csv").open(encoding="utf-8", newline="")))
    assert len(predictions) == 4
    assert {row["condition_id"] for row in predictions} == {"condition_c"}
    bundle = trainer.load_model(output / "model_state.pt")
    first = predictions[0]
    assert trainer.predict(bundle, [float(first["voltage"]), float(first["current"])]) == pytest.approx(
        float(first["prediction"]), abs=1e-10
    )
    run_manifest = json.loads((output / "run_manifest.json").read_text(encoding="utf-8"))
    assert run_manifest["dataset"]["manifest_sha256"] == _sha(version / "manifest.json")
    assert run_manifest["config_sha256"] == _sha(config)


def test_existing_output_and_staging_failure_are_fail_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    trainer, _version, _config = _synthetic(monkeypatch, tmp_path)
    output = tmp_path / "existing"
    output.mkdir()
    (output / "keep.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError, match="output_exists"):
        trainer.run_training(output, stage="formal", formal_authorized=True)
    assert (output / "keep.txt").read_text(encoding="utf-8") == "keep"


def test_manifest_tamper_is_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    trainer, version, _config = _synthetic(monkeypatch, tmp_path)
    (version / "manifest.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="MANIFEST_HASH_MISMATCH"):
        trainer.run_training(tmp_path / "tamper", stage="smoke", smoke_authorized=True, max_rows=4)


def test_direct_cli_without_authorization_fails() -> None:
    trainer = _trainer()
    with pytest.raises(SystemExit) as error:
        trainer.main([])
    assert error.value.code != 0
