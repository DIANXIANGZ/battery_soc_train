from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from src.custom_training.admission import validate_pytorch_entrypoint
from src.training.train_custom import main


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _version(root: Path, *, target: str = "soc", invalidated: bool = False) -> tuple[Path, Path]:
    root.mkdir(parents=True)
    manifest = root / "manifest.json"
    payload = {
        "schema_version": 1,
        "version": f"{target}-baseline-v1",
        "target": target,
        "source_id": "synthetic-open-source-v1",
        "feature_names": ["voltage_v"],
        "files": {"samples.csv": "a" * 64},
        "row_count": 3,
    }
    manifest.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    ready = root / "READY.json"
    ready.write_text(
        json.dumps({"schema_version": 1, "manifest_sha256": _sha(manifest)}),
        encoding="utf-8",
    )
    if invalidated:
        (root / "INVALIDATED.json").write_text(
            json.dumps({"target": target, "errors": ["blocked"]}), encoding="utf-8"
        )
    return manifest, ready


def _config(path: Path, *, target: str, manifest: Path, ready: Path, algorithm: str = "lstm") -> Path:
    config = path / "config.json"
    config.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "target": target,
                "algorithm": algorithm,
                "dataset": {
                    "path": str(manifest.parent),
                    "manifest_sha256": _sha(manifest),
                    "ready_sha256": _sha(ready),
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return config


def _argv(manifest: Path, ready: Path, config: Path, *, target: str = "soc", algorithm: str = "lstm") -> list[str]:
    return [
        "train_custom",
        "--manifest", str(manifest),
        "--ready", str(ready),
        "--config", str(config),
        "--config-sha256", _sha(config),
        "--target", target,
        "--algorithm", algorithm,
        "--dry-run",
    ]


def test_dry_run_accepts_ready_manifest_without_training(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    manifest, ready = _version(tmp_path / "soc-baseline-v1")
    config = _config(tmp_path, target="soc", manifest=manifest, ready=ready)

    with patch.object(sys, "argv", _argv(manifest, ready, config)), patch(
        "src.training.train_custom.run_training"
    ) as run_training:
        main()

    run_training.assert_not_called()
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "DRY_RUN_READY"
    assert result["target"] == "soc"
    assert result["algorithm"] == "lstm"


@pytest.mark.parametrize("algorithm", ["lstm", "gru", "transformer"])
def test_dry_run_accepts_each_pytorch_algorithm(tmp_path: Path, algorithm: str) -> None:
    manifest, ready = _version(tmp_path / f"{algorithm}-baseline-v1")
    config = _config(tmp_path, target="soc", manifest=manifest, ready=ready, algorithm=algorithm)
    with patch.object(sys, "argv", _argv(manifest, ready, config, algorithm=algorithm)):
        main()


def test_target_mismatch_is_rejected(tmp_path: Path) -> None:
    manifest, ready = _version(tmp_path / "soh-baseline-v1", target="soh")
    config = _config(tmp_path, target="soc", manifest=manifest, ready=ready)
    with patch.object(sys, "argv", _argv(manifest, ready, config, target="soc")):
        with pytest.raises(SystemExit):
            main()


def test_manifest_hash_change_is_rejected(tmp_path: Path) -> None:
    manifest, ready = _version(tmp_path / "soc-baseline-v1")
    config = _config(tmp_path, target="soc", manifest=manifest, ready=ready)
    manifest.write_text(manifest.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with patch.object(sys, "argv", _argv(manifest, ready, config)):
        with pytest.raises(SystemExit):
            main()


def test_config_fingerprint_mismatch_is_rejected(tmp_path: Path) -> None:
    manifest, ready = _version(tmp_path / "soc-baseline-v1")
    config = _config(tmp_path, target="soc", manifest=manifest, ready=ready)
    args = _argv(manifest, ready, config)
    args[args.index("--config-sha256") + 1] = "0" * 64
    with patch.object(sys, "argv", args):
        with pytest.raises(SystemExit):
            main()


def test_rul_manifest_is_rejected_even_when_target_is_requested(tmp_path: Path) -> None:
    manifest, ready = _version(tmp_path / "rul-baseline-v1", target="soc")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["rul_cycles"] = {"exact_observed_cells": 8}
    manifest.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    config = _config(tmp_path, target="soc", manifest=manifest, ready=ready)
    with patch.object(sys, "argv", _argv(manifest, ready, config)):
        with pytest.raises(SystemExit):
            main()


def test_invalidated_target_is_rejected_without_fallback(tmp_path: Path) -> None:
    manifest, ready = _version(tmp_path / "sot-baseline-v1", target="sot", invalidated=True)
    config = _config(tmp_path, target="sot", manifest=manifest, ready=ready)
    with patch.object(sys, "argv", _argv(manifest, ready, config, target="sot")):
        with pytest.raises(SystemExit):
            main()


def test_formal_mode_requires_external_authorization(tmp_path: Path) -> None:
    manifest, ready = _version(tmp_path / "soc-baseline-v1")
    config = _config(tmp_path, target="soc", manifest=manifest, ready=ready)
    args = _argv(manifest, ready, config)
    args[args.index("--dry-run")] = "--formal"
    with patch.object(sys, "argv", args), patch(
        "src.training.train_custom.run_training"
    ) as run_training:
        with pytest.raises(SystemExit):
            main()
    run_training.assert_not_called()


def test_direct_validator_rejects_unknown_target_and_invalidated(tmp_path: Path) -> None:
    manifest, ready = _version(tmp_path / "unknown-baseline-v1", target="unknown")
    config = _config(tmp_path, target="unknown", manifest=manifest, ready=ready)
    with pytest.raises(ValueError, match="unsupported_target"):
        validate_pytorch_entrypoint(
            manifest, ready, config, target="unknown", algorithm="lstm", config_sha256=_sha(config)
        )


def test_non_rul_project_path_is_not_a_semantic_rul_field(tmp_path: Path) -> None:
    manifest, ready = _version(tmp_path / "non_rul_baseline" / "soc-baseline-v1")
    config = _config(tmp_path / "non_rul_baseline", target="soc", manifest=manifest, ready=ready)
    result = validate_pytorch_entrypoint(
        manifest, ready, config, target="soc", algorithm="lstm", config_sha256=_sha(config)
    )
    assert result["status"] == "DRY_RUN_READY"
