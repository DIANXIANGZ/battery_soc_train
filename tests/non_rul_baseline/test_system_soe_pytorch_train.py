from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRAINER_PATH = (
    PROJECT_ROOT
    / ".superpowers/sdd/2026-09-22-system-soe-pytorch/system_soe_pytorch_train.py"
)
CONFIG_PATH = (
    PROJECT_ROOT
    / "configs/training/non_rul_baseline/system-soe-pytorch-linear-formal.json"
)
HEADER = (
    "target", "source_id", "cell_id", "session_id", "condition_id",
    "cycle_index", "time_s", "SoC", "Ptcb", "Ptei", "label",
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _trainer():
    assert TRAINER_PATH.is_file(), "system_soe PyTorch 入口尚未实现"
    spec = importlib.util.spec_from_file_location("system_soe_pytorch_train_under_test", TRAINER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _synthetic(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    trainer = _trainer()
    tmp_path.mkdir(parents=True, exist_ok=True)
    version = tmp_path / "system_soe-baseline-v1"
    version.mkdir()
    samples = version / "samples.csv"
    rows = []
    for group_index, group in enumerate(("train-a", "train-b", "test-a")):
        for row_index in range(6):
            value = float(group_index * 10 + row_index)
            rows.append((
                "system_soe", "synthetic-system-soe-v1", "CBES_SYSTEM_NOT_CELL",
                group, "Type=1|Subtype=0", row_index, 1_600_000_000.0 + value,
                30.0 + value, -10.0 + value, 5.0 - value, 100.0 + 2.0 * value,
            ))
    with samples.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        writer.writerows(rows)
    source_files = version / "source_files.csv"
    source_file = tmp_path / "source.csv"
    source_file.write_text("source", encoding="utf-8")
    source_files.write_text(
        f"path,size_bytes,sha256\n{source_file},{source_file.stat().st_size},{_sha(source_file)}\n",
        encoding="utf-8",
    )
    manifest_payload = {
        "schema_version": 1,
        "target": "system_soe",
        "source_id": "synthetic-system-soe-v1",
        "version": "system_soe-baseline-v1",
        "row_count": 18,
        "feature_names": ["SoC", "Ptcb", "Ptei"],
        "files": {"samples.csv": _sha(samples), "source_files.csv": _sha(source_files)},
        "target_metadata": {
            "scope": "community_storage_system_only_not_cell_level",
            "label": {"name": "soe_source_value", "source_field": "SoE", "unit": "unspecified_source_unit"},
            "split": {
                "axis": "RequID",
                "train_group_ids": ["train-a", "train-b"],
                "test_group_ids": ["test-a"],
                "train_row_count": 12,
                "test_row_count": 6,
                "validation": None,
            },
        },
    }
    manifest = version / "manifest.json"
    manifest.write_bytes(trainer.json_bytes(manifest_payload))
    ready = version / "READY.json"
    ready.write_bytes(trainer.json_bytes({"schema_version": 1, "manifest_sha256": _sha(manifest)}))

    monkeypatch.setattr(trainer, "VERSION_PATH", version)
    monkeypatch.setattr(trainer, "EXPECTED_SOURCE_ID", "synthetic-system-soe-v1")
    monkeypatch.setattr(trainer, "EXPECTED_ROW_COUNT", 18)
    monkeypatch.setattr(trainer, "EXPECTED_TRAIN_ROWS", 12)
    monkeypatch.setattr(trainer, "EXPECTED_TEST_ROWS", 6)
    monkeypatch.setattr(trainer, "EXPECTED_TRAIN_GROUPS", 2)
    monkeypatch.setattr(trainer, "EXPECTED_TEST_GROUPS", 1)
    monkeypatch.setattr(trainer, "EXPECTED_HASHES", {
        "READY.json": _sha(ready),
        "manifest.json": _sha(manifest),
        "samples.csv": _sha(samples),
        "source_files.csv": _sha(source_files),
    })
    monkeypatch.setattr(trainer, "verify_version", lambda *_args, **_kwargs: [])
    output = tmp_path / "output"
    monkeypatch.setattr(trainer, "OUTPUT_PATH", output)
    config = tmp_path / "config.json"
    config.write_bytes(trainer.json_bytes(trainer.expected_config_payload()))
    monkeypatch.setattr(trainer, "CONFIG_PATH", config)
    monkeypatch.setattr(trainer, "EXPECTED_CONFIG_SHA256", _sha(config))
    return trainer, output


def test_entrypoint_and_fixed_config_exist() -> None:
    trainer = _trainer()
    assert CONFIG_PATH.is_file()
    assert json.loads(CONFIG_PATH.read_text(encoding="utf-8")) == trainer.expected_config_payload()
    assert _sha(CONFIG_PATH) == trainer.EXPECTED_CONFIG_SHA256


def test_formal_and_smoke_require_explicit_authorization(tmp_path: Path) -> None:
    trainer = _trainer()
    with pytest.raises(ValueError, match="smoke_authorization_required"):
        trainer.run_training(tmp_path / "smoke", stage="smoke", smoke_authorized=False)
    with pytest.raises(ValueError, match="formal_authorization_required"):
        trainer.run_training(tmp_path / "formal", stage="formal", formal_authorized=False)


def test_fixed_split_rejects_group_overlap() -> None:
    trainer = _trainer()
    with pytest.raises(ValueError, match="group_leakage"):
        trainer.validate_split(["g1", "g2"], ["g2"])


def test_fit_uses_training_only_and_reload_matches() -> None:
    trainer = _trainer()
    import torch

    x_train = torch.tensor([[1.0, 2.0, 3.0], [3.0, 4.0, 5.0], [5.0, 8.0, 13.0]], dtype=torch.float64)
    y_train = torch.tensor([2.0, 4.0, 7.0], dtype=torch.float64)
    model, mean, scale = trainer.fit_linear(x_train, y_train)
    assert isinstance(model, torch.nn.Linear)
    assert torch.equal(mean, x_train.mean(dim=0))
    assert torch.all(scale > 0)
    assert torch.isfinite(model.weight).all() and torch.isfinite(model.bias).all()


def test_synthetic_formal_writes_exact_artifacts_and_preserves_group_split(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    trainer, output = _synthetic(monkeypatch, tmp_path)
    result = trainer.run_training(output, stage="formal", formal_authorized=True)
    assert result["status"] == "SYSTEM_SOE_PYTORCH_FORMAL_PASS"
    assert {path.name for path in output.iterdir()} == {
        "model_state.pt", "metrics.json", "predictions.csv", "training.log", "run_manifest.json",
    }
    predictions = list(csv.DictReader((output / "predictions.csv").open(encoding="utf-8", newline="")))
    assert len(predictions) == 6
    assert {row["session_id"] for row in predictions} == {"test-a"}
    manifest = json.loads((output / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["split"]["train_groups"] == 2
    assert manifest["split"]["test_groups"] == 1
    assert manifest["scope"] == "community_storage_system_only_not_cell_level"
    bundle = trainer.load_model(output / "model_state.pt")
    first = predictions[0]
    predicted = trainer.predict(bundle, [float(first[name]) for name in trainer.FEATURES])
    assert predicted == pytest.approx(float(first["prediction"]), abs=1e-10)


def test_existing_output_and_publish_failure_are_fail_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    trainer, output = _synthetic(monkeypatch, tmp_path)
    output.mkdir()
    (output / "keep.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError, match="output_exists"):
        trainer.run_training(output, stage="formal", formal_authorized=True)
    assert (output / "keep.txt").read_text(encoding="utf-8") == "keep"

    trainer, second = _synthetic(monkeypatch, tmp_path / "second")
    monkeypatch.setattr(trainer, "_rename_no_replace", lambda *_args: (_ for _ in ()).throw(OSError("forced")))
    with pytest.raises(OSError, match="forced"):
        trainer.run_training(second, stage="formal", formal_authorized=True)
    assert not second.exists()
    assert not list(second.parent.glob(f".{second.name}.staging-*"))


def test_direct_cli_without_authorization_fails() -> None:
    trainer = _trainer()
    with pytest.raises(SystemExit) as error:
        trainer.main([])
    assert error.value.code != 0
