import csv
from collections.abc import Mapping
import hashlib
import importlib
import json
from pathlib import Path
from types import MappingProxyType

import pytest

from src.data_processing.non_rul_baseline import CanonicalRow, DatasetContract
from src.data_processing.non_rul_baseline.build import (
    DatasetBuildError,
    build_version,
    verify_version,
)


def _contract() -> DatasetContract:
    return DatasetContract(target="soc", source_id="official-soc-v1", feature_names=("voltage", "current"))


def _energy_proxy_contract() -> DatasetContract:
    return DatasetContract(
        target="energy_proxy",
        source_id="zenodo-19487496-v1",
        feature_names=("time_s", "voltage_v", "current_a"),
    )


def _rows() -> list[CanonicalRow]:
    return [
        CanonicalRow("soc", "official-soc-v1", "cell-1", "session-1", "25c", 0, 0.0,
                     {"voltage": 4.2, "current": -1.0}, 1.0),
        CanonicalRow("soc", "official-soc-v1", "cell-1", "session-1", "25c", 0, 1.0,
                     {"voltage": 4.1, "current": -1.0}, 0.99),
    ]


def _source(tmp_path: Path) -> Path:
    source = tmp_path / "official.zip"
    source.write_bytes(b"official-source")
    return source


def test_build_version_is_atomic_and_can_be_verified(tmp_path: Path) -> None:
    source = tmp_path / "official.zip"
    source.write_bytes(b"official-source")

    version = build_version("soc", _rows(), _contract(), tmp_path, source_files=[source])

    assert version == tmp_path / "soc-baseline-v1"
    assert {path.name for path in version.iterdir()} == {
        "samples.csv", "manifest.json", "source_files.csv", "READY.json"
    }
    assert verify_version(version) == []
    manifest = json.loads((version / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["row_count"] == 2
    assert manifest["target"] == "soc"
    with (version / "source_files.csv").open(newline="", encoding="utf-8") as handle:
        records = list(csv.DictReader(handle))
    assert records[0]["path"] == str(source.resolve())
    assert records[0]["size_bytes"] == str(len(b"official-source"))


def test_energy_proxy_build_uses_its_own_version_namespace(tmp_path: Path) -> None:
    rows = [
        CanonicalRow("energy_proxy", "zenodo-19487496-v1", "UNVERIFIED", "sheet-a", "cond-a", 0, 0.0,
                     {"time_s": 0.0, "voltage_v": 4.2, "current_a": -1.0}, 0.0),
        CanonicalRow("energy_proxy", "zenodo-19487496-v1", "UNVERIFIED", "sheet-a", "cond-a", 1, 60.0,
                     {"time_s": 60.0, "voltage_v": 4.1, "current_a": -1.0}, 0.02),
    ]
    version = build_version("energy_proxy", rows, _energy_proxy_contract(), tmp_path, source_files=[_source(tmp_path)])
    assert version == tmp_path / "energy_proxy-baseline-v1"
    assert json.loads((version / "manifest.json").read_text(encoding="utf-8"))["target"] == "energy_proxy"


def test_existing_version_is_never_overwritten(tmp_path: Path) -> None:
    source = _source(tmp_path)
    version = build_version("soc", _rows(), _contract(), tmp_path, source_files=[source])
    original = (version / "samples.csv").read_bytes()

    with pytest.raises(FileExistsError):
        build_version("soc", _rows(), _contract(), tmp_path, source_files=[source])

    assert (version / "samples.csv").read_bytes() == original


def test_hash_mismatch_is_fail_closed(tmp_path: Path) -> None:
    version = build_version("soc", _rows(), _contract(), tmp_path, source_files=[_source(tmp_path)])
    with (version / "samples.csv").open("a", encoding="utf-8") as handle:
        handle.write("tampered\n")

    assert any("samples.csv哈希不一致" in error for error in verify_version(version))


def test_failed_build_leaves_only_diagnostic_record(tmp_path: Path) -> None:
    invalid_rows = _rows()
    invalid_rows[0] = CanonicalRow(
        "soc", "official-soc-v1", "cell-1", "session-1", "25c", 0, 0.0,
        {"voltage": 4.2, "current": -1.0}, None,
    )

    with pytest.raises(DatasetBuildError) as caught:
        build_version("soc", invalid_rows, _contract(), tmp_path, source_files=[_source(tmp_path)])

    invalidated = caught.value.diagnostic_path
    assert invalidated == tmp_path / "soc-baseline-v1"
    assert {path.name for path in invalidated.iterdir()} == {"INVALIDATED.json"}
    payload = json.loads((invalidated / "INVALIDATED.json").read_text(encoding="utf-8"))
    assert any("缺少目标标签" in error for error in payload["errors"])


def test_target_mismatch_fails_without_ready_marker(tmp_path: Path) -> None:
    with pytest.raises(DatasetBuildError):
        build_version("soe", _rows(), _contract(), tmp_path, source_files=[_source(tmp_path)])

    assert not list(tmp_path.rglob("READY.json"))


def test_verify_rejects_semantic_manifest_tampering_even_with_refreshed_ready_hash(
    tmp_path: Path,
) -> None:
    version = build_version("soc", _rows(), _contract(), tmp_path, source_files=[_source(tmp_path)])
    manifest_path = version / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["target"] = "soe"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    ready_path = version / "READY.json"
    ready = json.loads(ready_path.read_text(encoding="utf-8"))
    ready["manifest_sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    ready_path.write_text(
        json.dumps(ready, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    assert any("清单目标与版本目录不一致" in error for error in verify_version(version))


def test_verify_rejects_ready_and_invalidated_markers_together(tmp_path: Path) -> None:
    version = build_version("soc", _rows(), _contract(), tmp_path, source_files=[_source(tmp_path)])
    (version / "INVALIDATED.json").write_text("{}\n", encoding="utf-8")

    assert "READY.json与INVALIDATED.json不能同时存在" in verify_version(version)


def test_readback_failure_rolls_back_to_only_invalidated_marker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build_module = importlib.import_module("src.data_processing.non_rul_baseline.build")
    monkeypatch.setattr(build_module, "verify_version", lambda _path: ["回读核验失败"])

    with pytest.raises(DatasetBuildError) as caught:
        build_version("soc", _rows(), _contract(), tmp_path, source_files=[_source(tmp_path)])

    assert caught.value.diagnostic_path == tmp_path / "soc-baseline-v1"
    assert {path.name for path in caught.value.diagnostic_path.iterdir()} == {"INVALIDATED.json"}


def test_verify_rejects_manifest_row_count_that_does_not_match_samples(
    tmp_path: Path,
) -> None:
    version = build_version("soc", _rows(), _contract(), tmp_path, source_files=[_source(tmp_path)])
    manifest_path = version / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["row_count"] = 3
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    ready_path = version / "READY.json"
    ready = json.loads(ready_path.read_text(encoding="utf-8"))
    ready["manifest_sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    ready_path.write_text(
        json.dumps(ready, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    assert "samples.csv行数与清单不一致" in verify_version(version)


def test_verify_rejects_unexpected_files_in_ready_version(tmp_path: Path) -> None:
    version = build_version("soc", _rows(), _contract(), tmp_path, source_files=[_source(tmp_path)])
    (version / "unexpected.txt").write_text("not declared\n", encoding="utf-8")

    assert "成功版本包含未声明文件：unexpected.txt" in verify_version(version)


def test_verify_returns_stable_error_for_malformed_source_manifest(tmp_path: Path) -> None:
    source = tmp_path / "official.zip"
    source.write_bytes(b"official-source")
    version = build_version("soc", _rows(), _contract(), tmp_path, source_files=[source])
    sources_path = version / "source_files.csv"
    sources_path.write_text("path,size_bytes,sha256\n,,\n", encoding="utf-8")

    manifest_path = version / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"]["source_files.csv"] = hashlib.sha256(sources_path.read_bytes()).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    ready_path = version / "READY.json"
    ready = json.loads(ready_path.read_text(encoding="utf-8"))
    ready["manifest_sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    ready_path.write_text(
        json.dumps(ready, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    assert any("来源清单无法读取" in error for error in verify_version(version))


def test_verify_rejects_source_file_changed_after_publication(tmp_path: Path) -> None:
    source = tmp_path / "official.zip"
    source.write_bytes(b"official-source")
    version = build_version("soc", _rows(), _contract(), tmp_path, source_files=[source])

    source.write_bytes(b"changed-source")

    errors = verify_version(version)
    assert any("来源文件大小不一致" in error for error in errors)
    assert any("来源文件哈希不一致" in error for error in errors)


def test_build_requires_at_least_one_source_file(tmp_path: Path) -> None:
    with pytest.raises(DatasetBuildError) as caught:
        build_version("soc", _rows(), _contract(), tmp_path)

    assert "来源文件清单为空" in caught.value.errors
    assert {path.name for path in caught.value.diagnostic_path.iterdir()} == {"INVALIDATED.json"}


def test_duplicate_source_files_are_rejected(tmp_path: Path) -> None:
    source = _source(tmp_path)

    with pytest.raises(DatasetBuildError) as caught:
        build_version("soc", _rows(), _contract(), tmp_path, source_files=[source, source])

    assert "来源文件重复" in caught.value.errors


def test_invalid_target_is_rejected_before_output_root_is_touched(tmp_path: Path) -> None:
    output_root = tmp_path / "versions"

    with pytest.raises(ValueError, match="不支持的目标"):
        build_version("../rul", _rows(), _contract(), output_root, source_files=[_source(tmp_path)])

    assert not output_root.exists()


def test_publish_race_does_not_replace_new_empty_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build_module = importlib.import_module("src.data_processing.non_rul_baseline.build")
    real_rename = build_module._rename_no_replace

    def create_competing_destination(source: Path, destination: Path) -> None:
        destination.mkdir()
        real_rename(source, destination)

    monkeypatch.setattr(build_module, "_rename_no_replace", create_competing_destination)

    with pytest.raises(FileExistsError):
        build_version("soc", _rows(), _contract(), tmp_path, source_files=[_source(tmp_path)])

    destination = tmp_path / "soc-baseline-v1"
    assert destination.is_dir()
    assert list(destination.iterdir()) == []


def test_publish_fails_closed_when_atomic_no_replace_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build_module = importlib.import_module("src.data_processing.non_rul_baseline.build")
    monkeypatch.setattr(build_module.sys, "platform", "unsupported-platform")

    def forbidden_rename(_source: Path, _destination: Path) -> None:
        pytest.fail("原子no-replace不可用时不得回退到os.rename")

    monkeypatch.setattr(build_module.os, "rename", forbidden_rename)

    with pytest.raises(DatasetBuildError) as caught:
        build_version("soc", _rows(), _contract(), tmp_path, source_files=[_source(tmp_path)])

    destination = caught.value.diagnostic_path
    assert destination == tmp_path / "soc-baseline-v1"
    assert {path.name for path in destination.iterdir()} == {"INVALIDATED.json"}
    assert not list(tmp_path.rglob("READY.json"))


def test_unsupported_atomic_publish_does_not_overwrite_existing_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build_module = importlib.import_module("src.data_processing.non_rul_baseline.build")
    monkeypatch.setattr(build_module.sys, "platform", "unsupported-platform")
    destination = tmp_path / "soc-baseline-v1"
    destination.mkdir()
    marker = destination / "existing.txt"
    marker.write_text("historical\n", encoding="utf-8")

    with pytest.raises(FileExistsError):
        build_version("soc", _rows(), _contract(), tmp_path, source_files=[_source(tmp_path)])

    assert marker.read_text(encoding="utf-8") == "historical\n"
    assert {path.name for path in destination.iterdir()} == {"existing.txt"}
    assert not list(destination.rglob("READY.json"))


def test_verify_rejects_version_directory_renamed_to_another_target(tmp_path: Path) -> None:
    version = build_version(
        "soc", _rows(), _contract(), tmp_path, source_files=[_source(tmp_path)],
    )
    renamed = tmp_path / "soe-baseline-v1"
    version.rename(renamed)

    assert "清单目标与版本目录不一致" in verify_version(renamed)


def _sot_contract() -> DatasetContract:
    return DatasetContract(
        target="sot",
        source_id="native-temperature-v1",
        feature_names=("temperature", "current"),
    )


def _sot_rows() -> list[CanonicalRow]:
    return [
        CanonicalRow("sot", "native-temperature-v1", "cell-a", "session-a", "25c", 0, 0.0,
                     {"temperature": 25.0, "current": -1.0}, 25.1),
        CanonicalRow("sot", "native-temperature-v1", "cell-b", "session-b", "25c", 0, 0.0,
                     {"temperature": 25.1, "current": -1.0}, 25.2),
        CanonicalRow("sot", "native-temperature-v1", "cell-c", "session-c", "35c", 0, 0.0,
                     {"temperature": 35.0, "current": -2.0}, 35.1),
        CanonicalRow("sot", "native-temperature-v1", "cell-c", "session-d", "45c", 0, 0.0,
                     {"temperature": 45.0, "current": -2.0}, 45.1),
    ]


def _track_manifest(
    *,
    a_groups: list[str] | None = None,
    b_groups: list[str] | None = None,
    a_status: str = "AVAILABLE",
    b_status: str = "AVAILABLE",
) -> dict[str, object]:
    def track(
        status: str,
        groups: list[str],
        prefix: str,
    ) -> dict[str, object]:
        return {
            "status": status,
            "scope_statement": f"{prefix} source-native scope",
            "groups": groups,
            "fold_ids": [f"{prefix}-fold-1", f"{prefix}-fold-2"] if status == "AVAILABLE" else [],
            "split_namespace": f"{prefix}-split",
            "preprocessing_namespace": f"{prefix}-preprocess",
            "metrics_namespace": f"{prefix}-metrics",
            "configuration_sha256": prefix * 64 if status == "AVAILABLE" else None,
            "validation": None,
            "early_stopping": False,
            "reason_codes": [] if status == "AVAILABLE" else ["SOURCE_UNAVAILABLE"],
            "folds": (
                {
                    f"{prefix}-fold-1": {
                        "fold_id": f"{prefix}-fold-1",
                        "train_groups": groups[:1],
                        "test_groups": groups[1:],
                        "validation": None,
                        "train_row_count": 1,
                        "test_row_count": 1,
                    },
                    f"{prefix}-fold-2": {
                        "fold_id": f"{prefix}-fold-2",
                        "train_groups": groups[1:],
                        "test_groups": groups[:1],
                        "validation": None,
                        "train_row_count": 1,
                        "test_row_count": 1,
                    },
                }
                if status == "AVAILABLE" else {}
            ),
        }

    return {
        "A": track(a_status, a_groups if a_groups is not None else ["cell-a|25c", "cell-b|25c"], "a"),
        "B": track(b_status, b_groups if b_groups is not None else ["cell-c|35c", "cell-c|45c"], "b"),
    }


def _refresh_manifest_and_ready(version: Path) -> None:
    manifest_path = version / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    ready_path = version / "READY.json"
    ready = json.loads(ready_path.read_text(encoding="utf-8"))
    ready["manifest_sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    ready_path.write_text(
        json.dumps(ready, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def _rewrite_samples_and_refresh(
    version: Path,
    mutate_records: object,
    mutate_tracks: object,
) -> None:
    samples_path = version / "samples.csv"
    with samples_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        records = list(reader)
        assert reader.fieldnames is not None
        fieldnames = reader.fieldnames
    mutate_records(records)  # type: ignore[operator]
    with samples_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
    manifest_path = version / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"]["samples.csv"] = hashlib.sha256(samples_path.read_bytes()).hexdigest()
    mutate_tracks(manifest["tracks"])  # type: ignore[operator]
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    _refresh_manifest_and_ready(version)


def _build_dual_track(tmp_path: Path, **kwargs: object) -> Path:
    options: dict[str, object] = {
        "source_files": [_source(tmp_path)],
        "row_track_ids": ["A", "A", "B", "B"],
        "track_manifest": _track_manifest(),
    }
    options.update(kwargs)
    return build_version("sot", _sot_rows(), _sot_contract(), tmp_path, **options)


@pytest.mark.parametrize("argument", ["row_track_ids", "track_manifest"])
def test_dual_track_rejects_one_sided_arguments(tmp_path: Path, argument: str) -> None:
    kwargs: dict[str, object] = {argument: ["A", "A", "B"] if argument == "row_track_ids" else _track_manifest()}

    with pytest.raises(DatasetBuildError):
        build_version("sot", _sot_rows(), _sot_contract(), tmp_path, source_files=[_source(tmp_path)], **kwargs)


@pytest.mark.parametrize("track_ids", [["A", "A", "B"], ["A", "A", "B", "B", "B"], ["A", "A", "C", "B"]])
def test_dual_track_rejects_wrong_or_unknown_row_track_ids(
    tmp_path: Path,
    track_ids: list[str],
) -> None:
    with pytest.raises(DatasetBuildError):
        build_version(
            "sot", _sot_rows(), _sot_contract(), tmp_path,
            source_files=[_source(tmp_path)], row_track_ids=iter(track_ids), track_manifest=_track_manifest(),
        )


@pytest.mark.parametrize(
    "manifest",
    [
        {"A": _track_manifest()["A"]},
        {**_track_manifest(), "C": _track_manifest()["A"]},
    ],
)
def test_dual_track_rejects_missing_or_unknown_declared_track(
    tmp_path: Path,
    manifest: dict[str, object],
) -> None:
    with pytest.raises(DatasetBuildError):
        _build_dual_track(tmp_path, track_manifest=manifest)


def test_dual_track_writes_track_id_after_target_without_promoting_it_to_feature(tmp_path: Path) -> None:
    version = _build_dual_track(tmp_path)

    with (version / "samples.csv").open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        records = list(reader)
    manifest = json.loads((version / "manifest.json").read_text(encoding="utf-8"))
    assert reader.fieldnames == [
        "target", "track_id", "source_id", "cell_id", "session_id", "condition_id",
        "cycle_index", "time_s", "temperature", "current", "label",
    ]
    assert [record["track_id"] for record in records] == ["A", "A", "B", "B"]
    assert "track_id" not in manifest["feature_names"]
    assert manifest["row_metadata_fields"] == ["track_id"]
    assert manifest["label"] == {
        "name": "sot_source_native_temperature", "unit": "source-native-temperature",
    }


@pytest.mark.parametrize(
    "manifest",
    [
        _track_manifest(a_groups=["cell-z|25c"]),
        _track_manifest(a_groups=["cell-a|25c"], b_groups=["cell-a|25c"]),
    ],
)
def test_dual_track_rejects_row_group_mismatch_and_cross_track_group_reuse(
    tmp_path: Path,
    manifest: dict[str, object],
) -> None:
    with pytest.raises(DatasetBuildError):
        _build_dual_track(tmp_path, track_manifest=manifest)


@pytest.mark.parametrize(
    "manifest,track_ids",
    [
        (_track_manifest(a_groups=["cell-a|25c", "cell-x|45c"]), ["A", "A", "B"]),
        (_track_manifest(b_status="UNAVAILABLE", b_groups=[]), ["A", "A", "B"]),
    ],
)
def test_dual_track_rejects_unrepresented_available_groups_and_unavailable_rows(
    tmp_path: Path,
    manifest: dict[str, object],
    track_ids: list[str],
) -> None:
    with pytest.raises(DatasetBuildError):
        _build_dual_track(tmp_path, track_manifest=manifest, row_track_ids=track_ids)


def test_dual_track_rejects_namespace_collisions(tmp_path: Path) -> None:
    manifest = _track_manifest()
    tracks = manifest
    tracks["B"]["split_namespace"] = tracks["A"]["split_namespace"]  # type: ignore[index]

    with pytest.raises(DatasetBuildError):
        _build_dual_track(tmp_path, track_manifest=manifest)


@pytest.mark.parametrize("tamper", ["row", "track", "group"])
def test_verify_dual_track_rejects_semantic_tampering_after_hash_refresh(
    tmp_path: Path,
    tamper: str,
) -> None:
    version = _build_dual_track(tmp_path)
    if tamper == "row":
        samples_path = version / "samples.csv"
        records = list(csv.DictReader(samples_path.open(newline="", encoding="utf-8")))
        records[0]["track_id"] = "B"
        with samples_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)
        manifest_path = version / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["files"]["samples.csv"] = hashlib.sha256(samples_path.read_bytes()).hexdigest()
        manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    else:
        manifest_path = version / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if tamper == "track":
            manifest["tracks"]["B"]["status"] = "UNAVAILABLE"
            manifest["tracks"]["B"]["groups"] = []
            manifest["tracks"]["B"]["fold_ids"] = []
        else:
            manifest["tracks"]["B"]["groups"] = ["cell-a|25c"]
        manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    _refresh_manifest_and_ready(version)

    assert verify_version(version)


def test_dual_track_rejects_all_unavailable_before_ready(tmp_path: Path) -> None:
    with pytest.raises(DatasetBuildError) as caught:
        _build_dual_track(
            tmp_path,
            track_manifest=_track_manifest(a_status="UNAVAILABLE", b_status="UNAVAILABLE", a_groups=[], b_groups=[]),
            row_track_ids=[],
        )

    assert not list(caught.value.diagnostic_path.rglob("READY.json"))


def test_verify_rejects_ready_hash_that_does_not_cover_tracks(tmp_path: Path) -> None:
    version = _build_dual_track(tmp_path)
    manifest_path = version / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["tracks"]["A"]["scope_statement"] = "tampered track scope"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")

    assert "manifest.json哈希不一致" in verify_version(version)


def test_old_call_keeps_exact_historical_samples_header_and_manifest_keys(tmp_path: Path) -> None:
    version = build_version("soc", _rows(), _contract(), tmp_path, source_files=[_source(tmp_path)])
    source = tmp_path / "official.zip"
    expected_samples = (
        "target,source_id,cell_id,session_id,condition_id,cycle_index,time_s,voltage,current,label\n"
        "soc,official-soc-v1,cell-1,session-1,25c,0,0.0,4.2,-1.0,1.0\n"
        "soc,official-soc-v1,cell-1,session-1,25c,0,1.0,4.1,-1.0,0.99\n"
    )
    expected_source_files = (
        "path,size_bytes,sha256\n"
        f"{source.resolve()},15,{hashlib.sha256(b'official-source').hexdigest()}\n"
    )
    expected_manifest = {
        "schema_version": 1,
        "version": "soc-baseline-v1",
        "target": "soc",
        "source_id": "official-soc-v1",
        "feature_names": ["voltage", "current"],
        "row_count": 2,
        "files": {
            "samples.csv": hashlib.sha256(expected_samples.replace("\n", "\r\n").encode()).hexdigest(),
            "source_files.csv": hashlib.sha256(expected_source_files.replace("\n", "\r\n").encode()).hexdigest(),
        },
    }
    expected_manifest_bytes = (
        json.dumps(expected_manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    assert (version / "samples.csv").read_bytes() == expected_samples.replace("\n", "\r\n").encode()
    assert (version / "source_files.csv").read_bytes() == expected_source_files.replace("\n", "\r\n").encode()
    assert (version / "manifest.json").read_bytes() == expected_manifest_bytes
    assert (version / "READY.json").read_bytes() == (
        json.dumps(
            {"schema_version": 1, "manifest_sha256": hashlib.sha256(expected_manifest_bytes).hexdigest()},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def test_old_failure_path_keeps_exact_invalidated_golden(tmp_path: Path) -> None:
    with pytest.raises(DatasetBuildError) as caught:
        build_version("soc", _rows(), _contract(), tmp_path)

    assert caught.value.errors == ("来源文件清单为空",)
    assert {path.name for path in caught.value.diagnostic_path.iterdir()} == {"INVALIDATED.json"}
    assert (caught.value.diagnostic_path / "INVALIDATED.json").read_bytes() == (
        b'{"errors":["\xe6\x9d\xa5\xe6\xba\x90\xe6\x96\x87\xe4\xbb\xb6\xe6\xb8\x85\xe5\x8d\x95\xe4\xb8\xba\xe7\xa9\xba"],"schema_version":1,"target":"soc"}\n'
    )


def _assert_dual_track_invalidated(
    caught: pytest.ExceptionInfo[DatasetBuildError],
    expected_error: str,
) -> None:
    assert expected_error in caught.value.errors
    assert {path.name for path in caught.value.diagnostic_path.iterdir()} == {"INVALIDATED.json"}
    payload = json.loads((caught.value.diagnostic_path / "INVALIDATED.json").read_text(encoding="utf-8"))
    assert payload["errors"] == list(caught.value.errors)


def _contractual_sot_rows() -> list[CanonicalRow]:
    identities = [
        ("cell_280ah_1", "280Ah|0.5C|100%DOD"),
        ("cell_280ah_2", "280Ah|0.5C|100%DOD"),
        ("cell_40ah_1", "40Ah|0.3C|100%DOD"),
        ("cell_40ah_1", "40Ah|1C|100%DOD"),
        ("cell_40ah_1", "40Ah|2C|100%DOD"),
    ]
    return [
        CanonicalRow(
            "sot", "native-temperature-v1", cell_id, f"session-{index}", condition_id, 0, 0.0,
            {"temperature": 20.0 + index, "current": -1.0}, 20.1 + index,
        )
        for index, (cell_id, condition_id) in enumerate(identities)
    ]


def _contractual_track_manifest() -> dict[str, object]:
    return {
        "A": {
            "status": "AVAILABLE",
            "scope_statement": "same-condition held-out physical-cell evaluation only",
            "groups": [
                "cell_280ah_1|280Ah|0.5C|100%DOD",
                "cell_280ah_2|280Ah|0.5C|100%DOD",
            ],
            "fold_ids": ["A-cell-1-to-2", "A-cell-2-to-1"],
            "folds": {
                "A-cell-1-to-2": {
                    "fold_id": "A-cell-1-to-2",
                    "train_groups": ["cell_280ah_1|280Ah|0.5C|100%DOD"],
                    "test_groups": ["cell_280ah_2|280Ah|0.5C|100%DOD"],
                    "validation": None,
                    "train_row_count": 1,
                    "test_row_count": 1,
                },
                "A-cell-2-to-1": {
                    "fold_id": "A-cell-2-to-1",
                    "train_groups": ["cell_280ah_2|280Ah|0.5C|100%DOD"],
                    "test_groups": ["cell_280ah_1|280Ah|0.5C|100%DOD"],
                    "validation": None,
                    "train_row_count": 1,
                    "test_row_count": 1,
                },
            },
            "split_namespace": "sot/A",
            "preprocessing_namespace": "sot/A/preprocessing",
            "metrics_namespace": "sot/A/metrics",
            "configuration_sha256": "a" * 64,
            "validation": None,
            "early_stopping": False,
        },
        "B": {
            "status": "AVAILABLE",
            "scope_statement": "same-cell held-out condition evaluation only",
            "groups": [
                "cell_40ah_1|40Ah|0.3C|100%DOD",
                "cell_40ah_1|40Ah|1C|100%DOD",
                "cell_40ah_1|40Ah|2C|100%DOD",
            ],
            "fold_ids": ["B-holdout-0.3C", "B-holdout-1C", "B-holdout-2C"],
            "folds": {
                "B-holdout-0.3C": {
                    "fold_id": "B-holdout-0.3C",
                    "train_groups": ["cell_40ah_1|40Ah|1C|100%DOD", "cell_40ah_1|40Ah|2C|100%DOD"],
                    "test_groups": ["cell_40ah_1|40Ah|0.3C|100%DOD"],
                    "validation": None,
                    "train_row_count": 2,
                    "test_row_count": 1,
                },
                "B-holdout-1C": {
                    "fold_id": "B-holdout-1C",
                    "train_groups": ["cell_40ah_1|40Ah|0.3C|100%DOD", "cell_40ah_1|40Ah|2C|100%DOD"],
                    "test_groups": ["cell_40ah_1|40Ah|1C|100%DOD"],
                    "validation": None,
                    "train_row_count": 2,
                    "test_row_count": 1,
                },
                "B-holdout-2C": {
                    "fold_id": "B-holdout-2C",
                    "train_groups": ["cell_40ah_1|40Ah|0.3C|100%DOD", "cell_40ah_1|40Ah|1C|100%DOD"],
                    "test_groups": ["cell_40ah_1|40Ah|2C|100%DOD"],
                    "validation": None,
                    "train_row_count": 2,
                    "test_row_count": 1,
                },
            },
            "split_namespace": "sot/B",
            "preprocessing_namespace": "sot/B/preprocessing",
            "metrics_namespace": "sot/B/metrics",
            "configuration_sha256": "b" * 64,
            "validation": None,
            "early_stopping": False,
        },
    }


def _build_contractual_dual_track(tmp_path: Path, **kwargs: object) -> Path:
    options: dict[str, object] = {
        "source_files": [_source(tmp_path)],
        "row_track_ids": ["A", "A", "B", "B", "B"],
        "track_manifest": _contractual_track_manifest(),
    }
    options.update(kwargs)
    return build_version("sot", _contractual_sot_rows(), _sot_contract(), tmp_path, **options)


def test_dual_track_accepts_exact_contractual_pipe_containing_group_keys(tmp_path: Path) -> None:
    version = _build_contractual_dual_track(tmp_path)

    assert verify_version(version) == []


class _BrokenIterable:
    def __iter__(self) -> object:
        raise RuntimeError("broken iterable")


@pytest.mark.parametrize(
    "row_track_ids,manifest,expected_error",
    [
        (_BrokenIterable(), _track_manifest(), "row_track_ids无法物化"),
        (["A", [], "B"], _track_manifest(), "样本轨道标识无效"),
        (["A", "A", "B"], {"A": {**_track_manifest()["A"], "status": []}, "B": _track_manifest()["B"]}, "轨道A状态无效"),
        (["A", "A", "B"], {"A": {**_track_manifest()["A"], "groups": {"cell-a|25c"}}, "B": _track_manifest()["B"]}, "双轨清单JSON不兼容"),
    ],
)
def test_dual_track_malformed_input_is_a_stable_invalidated_build(
    tmp_path: Path,
    row_track_ids: object,
    manifest: object,
    expected_error: str,
) -> None:
    with pytest.raises(DatasetBuildError) as caught:
        build_version(
            "sot", _sot_rows(), _sot_contract(), tmp_path,
            source_files=[_source(tmp_path)], row_track_ids=row_track_ids, track_manifest=manifest,
        )

    _assert_dual_track_invalidated(caught, expected_error)


@pytest.mark.parametrize(
    "mutate,expected_error",
    [
        (lambda manifest: manifest["A"].pop("status"), "轨道A状态无效"),
        (lambda manifest: manifest["A"].__setitem__("scope_statement", ""), "轨道A范围声明无效"),
        (lambda manifest: manifest["A"].__setitem__("groups", []), "可用轨道A缺少分组"),
        (lambda manifest: manifest["A"].__setitem__("fold_ids", []), "可用轨道A缺少折叠"),
        (lambda manifest: manifest["A"].pop("split_namespace"), "轨道Asplit_namespace无效"),
        (lambda manifest: manifest["A"].pop("preprocessing_namespace"), "轨道Apreprocessing_namespace无效"),
        (lambda manifest: manifest["A"].pop("metrics_namespace"), "轨道Ametrics_namespace无效"),
        (lambda manifest: manifest["A"].__setitem__("configuration_sha256", "A" * 64), "轨道A配置哈希无效"),
        (lambda manifest: manifest["A"].__setitem__("validation", "not-null"), "轨道Avalidation必须为null"),
        (lambda manifest: manifest["A"].__setitem__("early_stopping", True), "轨道Aearly_stopping必须为false"),
        (
            lambda manifest: manifest["B"].update(
                {"status": "UNAVAILABLE", "groups": [], "fold_ids": [], "reason_codes": []},
            ),
            "不可用轨道B原因码无效",
        ),
    ],
)
def test_dual_track_required_fields_fail_in_build_and_refreshed_verify(
    tmp_path: Path,
    mutate: object,
    expected_error: str,
) -> None:
    invalid_manifest = _track_manifest()
    mutate(invalid_manifest)  # type: ignore[operator]
    with pytest.raises(DatasetBuildError) as caught:
        _build_dual_track(tmp_path, track_manifest=invalid_manifest)
    _assert_dual_track_invalidated(caught, expected_error)

    verify_root = tmp_path / "verify"
    verify_root.mkdir()
    version = _build_dual_track(verify_root)
    manifest_path = version / "manifest.json"
    refreshed_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mutate(refreshed_manifest["tracks"])  # type: ignore[operator]
    manifest_path.write_text(json.dumps(refreshed_manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    _refresh_manifest_and_ready(version)
    assert expected_error in verify_version(version)


@pytest.mark.parametrize("namespace", ["split_namespace", "preprocessing_namespace", "metrics_namespace"])
def test_dual_track_namespace_collisions_fail_in_build_and_refreshed_verify(
    tmp_path: Path,
    namespace: str,
) -> None:
    manifest = _track_manifest()
    manifest["B"][namespace] = manifest["A"][namespace]  # type: ignore[index]
    with pytest.raises(DatasetBuildError) as caught:
        _build_dual_track(tmp_path, track_manifest=manifest)
    expected_error = f"双轨{namespace}不得重复"
    _assert_dual_track_invalidated(caught, expected_error)

    verify_root = tmp_path / "verify"
    verify_root.mkdir()
    version = _build_dual_track(verify_root)
    manifest_path = version / "manifest.json"
    refreshed_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    refreshed_manifest["tracks"]["B"][namespace] = refreshed_manifest["tracks"]["A"][namespace]
    manifest_path.write_text(json.dumps(refreshed_manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    _refresh_manifest_and_ready(version)
    assert expected_error in verify_version(version)


def test_verify_dual_track_rejects_missing_track_id_column_after_hash_refresh(tmp_path: Path) -> None:
    version = _build_dual_track(tmp_path)
    samples_path = version / "samples.csv"
    records = list(csv.DictReader(samples_path.open(newline="", encoding="utf-8")))
    fieldnames = [name for name in records[0] if name != "track_id"]
    with samples_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows([{name: record[name] for name in fieldnames} for record in records])
    manifest_path = version / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"]["samples.csv"] = hashlib.sha256(samples_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    _refresh_manifest_and_ready(version)

    errors = verify_version(version)
    assert "samples.csv表头与清单不一致" in errors
    assert "样本轨道标识无效" in errors


def test_dual_track_rejects_all_unavailable_with_zero_rows_and_only_invalidated(tmp_path: Path) -> None:
    with pytest.raises(DatasetBuildError) as caught:
        build_version(
            "sot", [], _sot_contract(), tmp_path, source_files=[_source(tmp_path)], row_track_ids=[],
            track_manifest=_track_manifest(a_status="UNAVAILABLE", b_status="UNAVAILABLE", a_groups=[], b_groups=[]),
        )

    _assert_dual_track_invalidated(caught, "双轨不得同时不可用")


def test_dual_track_accepts_mapping_proxy_and_publishes_a_json_snapshot(tmp_path: Path) -> None:
    raw_manifest = _track_manifest()
    manifest = MappingProxyType({track_id: MappingProxyType(track) for track_id, track in raw_manifest.items()})

    version = _build_dual_track(tmp_path, track_manifest=manifest)

    assert verify_version(version) == []
    assert json.loads((version / "manifest.json").read_text(encoding="utf-8"))["tracks"] == raw_manifest


def test_verify_returns_errors_for_malicious_dual_track_json_types(tmp_path: Path) -> None:
    version = _build_dual_track(tmp_path)
    manifest_path = version / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["tracks"]["A"]["status"] = []
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    _refresh_manifest_and_ready(version)

    assert "轨道A状态无效" in verify_version(version)


def test_verify_returns_errors_for_unhashable_manifest_target(tmp_path: Path) -> None:
    version = _build_dual_track(tmp_path)
    manifest_path = version / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["target"] = []
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    _refresh_manifest_and_ready(version)

    assert "清单目标与版本目录不一致" in verify_version(version)


@pytest.mark.parametrize(
    "row_track_ids,track_manifest,expected_error",
    [
        (["A", "A", "B"], None, "row_track_ids与track_manifest必须同时提供"),
        (None, _track_manifest(), "row_track_ids与track_manifest必须同时提供"),
        (["A", "A", "B"], _track_manifest(), "样本轨道标识数量与数据行不一致"),
        (["A", "A", "B", "B", "B"], _track_manifest(), "样本轨道标识数量与数据行不一致"),
        (["A", "A", "C", "B"], _track_manifest(), "样本轨道标识无效"),
        (["A", "A", "B"], {"A": _track_manifest()["A"]}, "双轨清单必须且只能声明A和B"),
        (["A", "A", "B"], {**_track_manifest(), "C": _track_manifest()["A"]}, "双轨清单必须且只能声明A和B"),
        (42, _track_manifest(), "row_track_ids无法物化"),
    ],
)
def test_dual_track_red19_inputs_have_exact_fail_closed_diagnostics(
    tmp_path: Path,
    row_track_ids: object,
    track_manifest: object,
    expected_error: str,
) -> None:
    with pytest.raises(DatasetBuildError) as caught:
        build_version(
            "sot", _sot_rows(), _sot_contract(), tmp_path, source_files=[_source(tmp_path)],
            row_track_ids=row_track_ids, track_manifest=track_manifest,
        )

    _assert_dual_track_invalidated(caught, expected_error)


@pytest.mark.parametrize(
    "manifest,track_ids,expected_error",
    [
        (_track_manifest(a_groups=["cell-z|25c"]), ["A", "A", "B"], "样本分组未声明给轨道A"),
        (_track_manifest(a_groups=["cell-a|25c"], b_groups=["cell-a|25c"]), ["A", "A", "B"], "分组不得跨轨道复用"),
        (_track_manifest(a_groups=["cell-a|25c", "cell-x|45c"]), ["A", "A", "B"], "可用轨道A存在无样本分组"),
        (_track_manifest(b_status="UNAVAILABLE", b_groups=[]), ["A", "A", "B"], "不可用轨道B不得包含样本"),
    ],
)
def test_dual_track_red20_group_and_row_rules_have_exact_diagnostics(
    tmp_path: Path,
    manifest: dict[str, object],
    track_ids: list[str],
    expected_error: str,
) -> None:
    with pytest.raises(DatasetBuildError) as caught:
        _build_dual_track(tmp_path, track_manifest=manifest, row_track_ids=track_ids)

    _assert_dual_track_invalidated(caught, expected_error)


@pytest.mark.parametrize(
    "tamper,expected_error",
    [
        ("row", "样本分组未声明给轨道B"),
        ("group", "分组不得跨轨道复用"),
        ("manifest", "轨道A范围声明无效"),
    ],
)
def test_verify_red23_rejects_single_side_and_refreshed_semantic_tampering(
    tmp_path: Path,
    tamper: str,
    expected_error: str,
) -> None:
    version = _build_dual_track(tmp_path)
    manifest_path = version / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if tamper == "row":
        samples_path = version / "samples.csv"
        records = list(csv.DictReader(samples_path.open(newline="", encoding="utf-8")))
        records[0]["track_id"] = "B"
        with samples_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)
        manifest["files"]["samples.csv"] = hashlib.sha256(samples_path.read_bytes()).hexdigest()
    elif tamper == "group":
        manifest["tracks"]["B"]["groups"] = ["cell-a|25c"]
    else:
        manifest["tracks"]["A"]["scope_statement"] = ""
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    if tamper != "manifest":
        _refresh_manifest_and_ready(version)

    errors = verify_version(version)
    assert expected_error in errors
    if tamper == "manifest":
        assert "manifest.json哈希不一致" in errors


def test_verify_rejects_wrong_dual_track_label_after_hash_refresh(tmp_path: Path) -> None:
    version = _build_dual_track(tmp_path)
    manifest_path = version / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["label"]["unit"] = "degC"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    _refresh_manifest_and_ready(version)

    assert "双轨标签声明无效" in verify_version(version)


def test_contractual_dual_track_publishes_real_a_two_fold_and_b_three_fold_mappings(tmp_path: Path) -> None:
    version = _build_contractual_dual_track(tmp_path)
    tracks = json.loads((version / "manifest.json").read_text(encoding="utf-8"))["tracks"]

    assert list(tracks["A"]["folds"]) == ["A-cell-1-to-2", "A-cell-2-to-1"]
    assert list(tracks["B"]["folds"]) == ["B-holdout-0.3C", "B-holdout-1C", "B-holdout-2C"]
    assert tracks["A"]["folds"]["A-cell-1-to-2"]["test_row_count"] == 1
    assert tracks["B"]["folds"]["B-holdout-0.3C"]["train_row_count"] == 2
    assert verify_version(version) == []


@pytest.mark.parametrize(
    "mutate,expected_error",
    [
        (lambda tracks: tracks["A"].pop("folds"), "可用轨道A缺少folds"),
        (
            lambda tracks: tracks["A"].__setitem__(
                "folds", {"wrong-fold": tracks["A"]["folds"].pop("A-cell-1-to-2"), **tracks["A"]["folds"]},
            ),
            "轨道A折叠键与fold_ids不一致",
        ),
        (lambda tracks: tracks["A"].__setitem__("fold_ids", ["A-cell-1-to-2"]), "轨道A折叠键与fold_ids不一致"),
        (
            lambda tracks: tracks["A"]["folds"]["A-cell-1-to-2"].update({"fold_id": "other-fold"}),
            "轨道A折叠fold_id无效",
        ),
        (
            lambda tracks: tracks["A"]["folds"]["A-cell-1-to-2"].update({"validation": "not-null"}),
            "轨道A折叠validation必须为null",
        ),
        (
            lambda tracks: tracks["A"]["folds"]["A-cell-1-to-2"].pop("validation"),
            "轨道A折叠validation必须为null",
        ),
        (
            lambda tracks: tracks["A"]["folds"]["A-cell-1-to-2"].update({"train_groups": []}),
            "轨道A折叠train_groups无效",
        ),
        (
            lambda tracks: tracks["A"]["folds"]["A-cell-1-to-2"].update({"test_groups": []}),
            "轨道A折叠test_groups无效",
        ),
        (
            lambda tracks: tracks["B"]["folds"]["B-holdout-0.3C"].update(
                {
                    "train_groups": ["cell_40ah_1|40Ah|0.3C|100%DOD"],
                    "test_groups": ["cell_40ah_1|40Ah|1C|100%DOD"],
                },
            ),
            "轨道B折叠训练测试分组不完整",
        ),
        (
            lambda tracks: tracks["A"]["folds"]["A-cell-1-to-2"].update(
                {"train_groups": ["cell_280ah_2|280Ah|0.5C|100%DOD"]},
            ),
            "轨道A折叠训练测试分组重叠",
        ),
        (
            lambda tracks: tracks["A"]["folds"]["A-cell-1-to-2"].update(
                {"train_groups": ["unknown-cell|280Ah|0.5C|100%DOD"]},
            ),
            "轨道A折叠包含未知分组",
        ),
        (
            lambda tracks: tracks["A"]["folds"]["A-cell-1-to-2"].update(
                {"test_groups": ["cell_280ah_2|280Ah|0.5C|100%DOD", "cell_280ah_2|280Ah|0.5C|100%DOD"]},
            ),
            "轨道A折叠分组重复",
        ),
        (
            lambda tracks: tracks["A"]["folds"]["A-cell-2-to-1"].update(
                {"test_groups": ["cell_280ah_2|280Ah|0.5C|100%DOD"]},
            ),
            "轨道A分组测试次数无效",
        ),
        (
            lambda tracks: tracks["B"]["folds"]["B-holdout-0.3C"].update({"train_row_count": 1}),
            "轨道B折叠train_row_count无效",
        ),
        (
            lambda tracks: tracks["B"]["folds"]["B-holdout-0.3C"].update({"test_row_count": 2}),
            "轨道B折叠test_row_count无效",
        ),
        (
            lambda tracks: tracks["B"].update(
                {"status": "UNAVAILABLE", "groups": [], "fold_ids": [], "reason_codes": ["NO_SOURCE"]},
            ),
            "不可用轨道Bfolds必须为空mapping",
        ),
    ],
)
def test_contractual_fold_contract_fails_in_build_and_refreshed_verify(
    tmp_path: Path,
    mutate: object,
    expected_error: str,
) -> None:
    manifest = _contractual_track_manifest()
    mutate(manifest)  # type: ignore[operator]
    with pytest.raises(DatasetBuildError) as caught:
        _build_contractual_dual_track(tmp_path, track_manifest=manifest)
    _assert_dual_track_invalidated(caught, expected_error)

    verify_root = tmp_path / "verify"
    verify_root.mkdir()
    version = _build_contractual_dual_track(verify_root)
    manifest_path = version / "manifest.json"
    refreshed_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mutate(refreshed_manifest["tracks"])  # type: ignore[operator]
    manifest_path.write_text(json.dumps(refreshed_manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    _refresh_manifest_and_ready(version)
    assert expected_error in verify_version(version)


def test_fold_contract_rejects_a_train_test_same_cell_with_distinct_groups(tmp_path: Path) -> None:
    rows = _contractual_sot_rows()
    rows[1] = CanonicalRow(
        "sot", "native-temperature-v1", "cell_280ah_1", "session-1", "280Ah|0.5C|90%DOD", 0, 0.0,
        {"temperature": 21.0, "current": -1.0}, 21.1,
    )
    manifest = _contractual_track_manifest()
    manifest["A"]["groups"] = [
        "cell_280ah_1|280Ah|0.5C|100%DOD",
        "cell_280ah_1|280Ah|0.5C|90%DOD",
    ]
    manifest["A"]["folds"]["A-cell-1-to-2"]["test_groups"] = ["cell_280ah_1|280Ah|0.5C|90%DOD"]
    manifest["A"]["folds"]["A-cell-2-to-1"]["train_groups"] = ["cell_280ah_1|280Ah|0.5C|90%DOD"]

    with pytest.raises(DatasetBuildError) as caught:
        build_version(
            "sot", rows, _sot_contract(), tmp_path, source_files=[_source(tmp_path)],
            row_track_ids=["A", "A", "B", "B", "B"], track_manifest=manifest,
        )

    _assert_dual_track_invalidated(caught, "轨道A折叠训练测试cell_id不互斥")

    verify_root = tmp_path / "verify"
    verify_root.mkdir()
    version = _build_contractual_dual_track(verify_root)
    _rewrite_samples_and_refresh(
        version,
        lambda records: records[1].update({"cell_id": "cell_280ah_1", "condition_id": "280Ah|0.5C|90%DOD"}),
        lambda tracks: (
            tracks["A"].__setitem__(
                "groups", ["cell_280ah_1|280Ah|0.5C|100%DOD", "cell_280ah_1|280Ah|0.5C|90%DOD"],
            ),
            tracks["A"]["folds"]["A-cell-1-to-2"].__setitem__(
                "test_groups", ["cell_280ah_1|280Ah|0.5C|90%DOD"],
            ),
            tracks["A"]["folds"]["A-cell-2-to-1"].__setitem__(
                "train_groups", ["cell_280ah_1|280Ah|0.5C|90%DOD"],
            ),
        ),
    )
    assert "轨道A折叠训练测试cell_id不互斥" in verify_version(version)


def test_fold_contract_rejects_b_train_test_same_condition_with_distinct_groups(tmp_path: Path) -> None:
    rows = _contractual_sot_rows()
    rows[3] = CanonicalRow(
        "sot", "native-temperature-v1", "cell_40ah_2", "session-3", "40Ah|0.3C|100%DOD", 0, 0.0,
        {"temperature": 23.0, "current": -1.0}, 23.1,
    )
    manifest = _contractual_track_manifest()
    manifest["B"]["groups"] = [
        "cell_40ah_1|40Ah|0.3C|100%DOD",
        "cell_40ah_2|40Ah|0.3C|100%DOD",
        "cell_40ah_1|40Ah|2C|100%DOD",
    ]
    manifest["B"]["folds"]["B-holdout-0.3C"]["train_groups"] = [
        "cell_40ah_2|40Ah|0.3C|100%DOD", "cell_40ah_1|40Ah|2C|100%DOD",
    ]
    manifest["B"]["folds"]["B-holdout-1C"]["test_groups"] = ["cell_40ah_2|40Ah|0.3C|100%DOD"]
    manifest["B"]["folds"]["B-holdout-2C"]["train_groups"] = [
        "cell_40ah_1|40Ah|0.3C|100%DOD", "cell_40ah_2|40Ah|0.3C|100%DOD",
    ]

    with pytest.raises(DatasetBuildError) as caught:
        build_version(
            "sot", rows, _sot_contract(), tmp_path, source_files=[_source(tmp_path)],
            row_track_ids=["A", "A", "B", "B", "B"], track_manifest=manifest,
        )

    _assert_dual_track_invalidated(caught, "轨道B折叠训练测试condition_id不互斥")

    verify_root = tmp_path / "verify"
    verify_root.mkdir()
    version = _build_contractual_dual_track(verify_root)
    _rewrite_samples_and_refresh(
        version,
        lambda records: records[3].update({"cell_id": "cell_40ah_2", "condition_id": "40Ah|0.3C|100%DOD"}),
        lambda tracks: (
            tracks["B"].__setitem__(
                "groups",
                [
                    "cell_40ah_1|40Ah|0.3C|100%DOD",
                    "cell_40ah_2|40Ah|0.3C|100%DOD",
                    "cell_40ah_1|40Ah|2C|100%DOD",
                ],
            ),
            tracks["B"]["folds"]["B-holdout-0.3C"].__setitem__(
                "train_groups", ["cell_40ah_2|40Ah|0.3C|100%DOD", "cell_40ah_1|40Ah|2C|100%DOD"],
            ),
            tracks["B"]["folds"]["B-holdout-1C"].update(
                {
                    "train_groups": ["cell_40ah_1|40Ah|0.3C|100%DOD", "cell_40ah_1|40Ah|2C|100%DOD"],
                    "test_groups": ["cell_40ah_2|40Ah|0.3C|100%DOD"],
                },
            ),
            tracks["B"]["folds"]["B-holdout-2C"].__setitem__(
                "train_groups", ["cell_40ah_1|40Ah|0.3C|100%DOD", "cell_40ah_2|40Ah|0.3C|100%DOD"],
            ),
        ),
    )
    assert "轨道B折叠训练测试condition_id不互斥" in verify_version(version)
