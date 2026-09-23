"""Atomic, hash-bound dataset versions for the non-RUL baselines."""

from __future__ import annotations

import csv
import ctypes
import errno
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from typing import Iterable, Mapping, Sequence

from src.data_processing.non_rul_baseline.common import (
    CanonicalRow,
    DatasetContract,
    SUPPORTED_TARGETS,
    validate_contract,
)


SCHEMA_VERSION = 1


class DatasetBuildError(ValueError):
    """A rejected build with a durable, non-ready diagnostic path."""

    def __init__(self, errors: Sequence[str], diagnostic_path: Path):
        super().__init__("；".join(errors))
        self.errors = tuple(errors)
        self.diagnostic_path = diagnostic_path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def _publish_directory(temporary: Path, destination: Path) -> None:
    if destination.exists():
        raise FileExistsError(f"数据版本已存在，禁止覆盖：{destination}")
    try:
        _rename_no_replace(temporary, destination)
    except FileExistsError:
        raise FileExistsError(f"数据版本已存在，禁止覆盖：{destination}") from None


def _rename_no_replace(source: Path, destination: Path) -> None:
    """Atomically rename a directory without replacing an existing path."""

    libc = ctypes.CDLL(None, use_errno=True)
    source_bytes = os.fsencode(source)
    destination_bytes = os.fsencode(destination)
    if sys.platform == "darwin":
        rename = libc.renamex_np
        rename.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint)
        rename.restype = ctypes.c_int
        result = rename(source_bytes, destination_bytes, 0x00000004)  # RENAME_EXCL
    elif sys.platform.startswith("linux") and hasattr(libc, "renameat2"):
        rename = libc.renameat2
        rename.argtypes = (
            ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint,
        )
        rename.restype = ctypes.c_int
        result = rename(-100, source_bytes, -100, destination_bytes, 0x00000001)  # RENAME_NOREPLACE
    else:
        raise OSError(errno.ENOTSUP, "当前平台不支持原子no-replace发布", destination)
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number in (errno.EEXIST, errno.ENOTEMPTY):
        raise FileExistsError(destination)
    raise OSError(error_number, os.strerror(error_number), destination)


def _record_invalidated(output_root: Path, target: str, errors: Sequence[str]) -> Path:
    destination = output_root / f"{target}-baseline-v1"
    try:
        destination.mkdir(mode=0o700)
    except FileExistsError:
        raise FileExistsError(f"失败诊断已存在，禁止覆盖：{destination}") from None
    invalidated_path = destination / "INVALIDATED.json"
    payload = (
        json.dumps(
            {"schema_version": SCHEMA_VERSION, "target": target, "errors": list(errors)},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    descriptor: int | None = None
    try:
        descriptor = os.open(invalidated_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        if descriptor is not None:
            os.close(descriptor)
        invalidated_path.unlink(missing_ok=True)
        try:
            destination.rmdir()
        except OSError:
            pass
        raise
    return destination


def _is_nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _parse_group_key(value: object) -> tuple[str, str] | None:
    if not _is_nonempty_string(value):
        return None
    cell_id, separator, condition_id = value.partition("|")
    if not separator or not cell_id.strip() or not condition_id.strip():
        return None
    return cell_id, condition_id


def _snapshot_json(value: object) -> object:
    """Copy only JSON-compatible data so validation and serialization share bytes."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError("non-finite number")
        return value
    if isinstance(value, Mapping):
        snapshot: dict[str, object] = {}
        for key, nested_value in value.items():
            if not isinstance(key, str):
                raise TypeError("non-string mapping key")
            snapshot[key] = _snapshot_json(nested_value)
        return snapshot
    if isinstance(value, (list, tuple)):
        return [_snapshot_json(item) for item in value]
    raise TypeError("unsupported JSON value")


def _snapshot_track_manifest(value: object) -> tuple[dict[str, object] | None, str | None]:
    if not isinstance(value, Mapping):
        return None, "track_manifest必须为Mapping"
    try:
        snapshot = _snapshot_json(value)
    except Exception:
        return None, "双轨清单JSON不兼容"
    if not isinstance(snapshot, dict):
        return None, "track_manifest必须为Mapping"
    return snapshot, None


def _validate_track_folds(
    track_id: str,
    track: Mapping[str, object],
    status: str,
    declared_groups: set[tuple[str, str]],
    fold_ids: list[str],
    row_counts: Mapping[tuple[str, str], int],
) -> list[str]:
    """Validate one track's fold mapping against its declared groups and samples."""

    errors: list[str] = []
    folds = track.get("folds")
    if status == "UNAVAILABLE":
        if not isinstance(folds, Mapping) or folds:
            errors.append(f"不可用轨道{track_id}folds必须为空mapping")
        return errors
    if not isinstance(folds, Mapping):
        return [f"可用轨道{track_id}缺少folds"]
    if set(folds) != set(fold_ids):
        errors.append(f"轨道{track_id}折叠键与fold_ids不一致")

    test_counts = {group: 0 for group in declared_groups}
    for fold_key in fold_ids:
        fold = folds.get(fold_key)
        if not isinstance(fold, Mapping):
            errors.append(f"轨道{track_id}折叠{fold_key}无效")
            continue
        fold_id = fold.get("fold_id")
        if fold_id is not None and fold_id != fold_key:
            errors.append(f"轨道{track_id}折叠fold_id无效")
        if "validation" not in fold or fold["validation"] is not None:
            errors.append(f"轨道{track_id}折叠validation必须为null")

        parsed_sets: dict[str, set[tuple[str, str]]] = {}
        malformed = False
        for field_name in ("train_groups", "test_groups"):
            group_values = fold.get(field_name)
            parsed_values = [
                _parse_group_key(value) for value in group_values
            ] if isinstance(group_values, list) else []
            if not isinstance(group_values, list) or not parsed_values or any(value is None for value in parsed_values):
                errors.append(f"轨道{track_id}折叠{field_name}无效")
                malformed = True
                continue
            if len(parsed_values) != len(set(parsed_values)):
                errors.append(f"轨道{track_id}折叠分组重复")
            parsed_sets[field_name] = set(parsed_values)
            if not parsed_sets[field_name] <= declared_groups:
                errors.append(f"轨道{track_id}折叠包含未知分组")
        if malformed or set(parsed_sets) != {"train_groups", "test_groups"}:
            continue
        train_groups = parsed_sets["train_groups"]
        test_groups = parsed_sets["test_groups"]
        if train_groups & test_groups:
            errors.append(f"轨道{track_id}折叠训练测试分组重叠")
        if train_groups | test_groups != declared_groups:
            errors.append(f"轨道{track_id}折叠训练测试分组不完整")
        if track_id == "A":
            if {group[0] for group in train_groups} & {group[0] for group in test_groups}:
                errors.append("轨道A折叠训练测试cell_id不互斥")
        if track_id == "B":
            if {group[1] for group in train_groups} & {group[1] for group in test_groups}:
                errors.append("轨道B折叠训练测试condition_id不互斥")
        for group in test_groups:
            if group in test_counts:
                test_counts[group] += 1
        for field_name, groups in (("train_row_count", train_groups), ("test_row_count", test_groups)):
            declared_count = fold.get(field_name)
            expected_count = sum(row_counts.get(group, 0) for group in groups)
            if (
                not isinstance(declared_count, int)
                or isinstance(declared_count, bool)
                or declared_count != expected_count
            ):
                errors.append(f"轨道{track_id}折叠{field_name}无效")
    if any(count != 1 for count in test_counts.values()):
        errors.append(f"轨道{track_id}分组测试次数无效")
    return errors


def _validate_track_envelope(
    tracks: object,
    row_groups_and_tracks: Sequence[tuple[tuple[str, str], object]],
) -> list[str]:
    """Validate the dual-track manifest and its one-to-one row assignment."""

    errors: list[str] = []
    if not isinstance(tracks, Mapping) or set(tracks) != {"A", "B"}:
        return ["双轨清单必须且只能声明A和B"]

    declared_groups: dict[str, set[tuple[str, str]]] = {}
    statuses: dict[str, str] = {}
    namespace_values: dict[str, list[str]] = {
        "split_namespace": [],
        "preprocessing_namespace": [],
        "metrics_namespace": [],
    }
    for track_id in ("A", "B"):
        track = tracks[track_id]
        if not isinstance(track, Mapping):
            errors.append(f"轨道{track_id}声明无效")
            continue
        status = track.get("status")
        if not isinstance(status, str) or status not in {"AVAILABLE", "UNAVAILABLE"}:
            errors.append(f"轨道{track_id}状态无效")
            continue
        statuses[track_id] = status
        if not _is_nonempty_string(track.get("scope_statement")):
            errors.append(f"轨道{track_id}范围声明无效")
        groups = track.get("groups")
        parsed_groups = [
            _parse_group_key(group) for group in groups
        ] if isinstance(groups, list) else []
        if not isinstance(groups, list) or any(group is None for group in parsed_groups):
            errors.append(f"轨道{track_id}分组无效")
            parsed_groups = []
        elif len(parsed_groups) != len(set(parsed_groups)):
            errors.append(f"轨道{track_id}分组重复")
        declared_groups[track_id] = set(parsed_groups)
        fold_ids = track.get("fold_ids")
        if (
            not isinstance(fold_ids, list)
            or any(not _is_nonempty_string(fold_id) for fold_id in fold_ids)
            or len(fold_ids) != len(set(fold_ids))
        ):
            errors.append(f"轨道{track_id}折叠无效")
            fold_ids = []
        for namespace in namespace_values:
            value = track.get(namespace)
            if not _is_nonempty_string(value):
                errors.append(f"轨道{track_id}{namespace}无效")
            else:
                namespace_values[namespace].append(value)
        if track.get("validation") is not None:
            errors.append(f"轨道{track_id}validation必须为null")
        if track.get("early_stopping") is not False:
            errors.append(f"轨道{track_id}early_stopping必须为false")
        if status == "AVAILABLE":
            configuration_sha256 = track.get("configuration_sha256")
            if (
                not isinstance(configuration_sha256, str)
                or re.fullmatch(r"[0-9a-f]{64}", configuration_sha256) is None
            ):
                errors.append(f"轨道{track_id}配置哈希无效")
            if not parsed_groups:
                errors.append(f"可用轨道{track_id}缺少分组")
            if not fold_ids:
                errors.append(f"可用轨道{track_id}缺少折叠")
        else:
            reason_codes = track.get("reason_codes")
            if (
                not isinstance(reason_codes, list)
                or not reason_codes
                or any(not _is_nonempty_string(code) for code in reason_codes)
                or len(reason_codes) != len(set(reason_codes))
            ):
                errors.append(f"不可用轨道{track_id}原因码无效")
            if parsed_groups:
                errors.append(f"不可用轨道{track_id}不得声明分组")
            if fold_ids:
                errors.append(f"不可用轨道{track_id}不得声明折叠")

    for namespace, values in namespace_values.items():
        if len(values) == 2 and len(set(values)) != 2:
            errors.append(f"双轨{namespace}不得重复")
    if declared_groups.get("A", set()) & declared_groups.get("B", set()):
        errors.append("分组不得跨轨道复用")
    if statuses and all(status == "UNAVAILABLE" for status in statuses.values()):
        errors.append("双轨不得同时不可用")

    groups_with_rows: dict[str, set[tuple[str, str]]] = {"A": set(), "B": set()}
    row_counts: dict[str, dict[tuple[str, str], int]] = {"A": {}, "B": {}}
    for row_group, track_id in row_groups_and_tracks:
        if not isinstance(track_id, str) or track_id not in {"A", "B"}:
            errors.append("样本轨道标识无效")
            continue
        if (
            not isinstance(row_group, tuple)
            or len(row_group) != 2
            or not _is_nonempty_string(row_group[0])
            or not _is_nonempty_string(row_group[1])
            or "|" in row_group[0]
        ):
            errors.append("样本分组键无效")
            continue
        if statuses.get(track_id) != "AVAILABLE":
            errors.append(f"不可用轨道{track_id}不得包含样本")
            continue
        if row_group not in declared_groups.get(track_id, set()):
            errors.append(f"样本分组未声明给轨道{track_id}")
            continue
        groups_with_rows[track_id].add(row_group)
        row_counts[track_id][row_group] = row_counts[track_id].get(row_group, 0) + 1
    for track_id, status in statuses.items():
        if status == "AVAILABLE":
            missing = declared_groups.get(track_id, set()) - groups_with_rows[track_id]
            if missing:
                errors.append(f"可用轨道{track_id}存在无样本分组")
        track = tracks.get(track_id) if isinstance(tracks, Mapping) else None
        if isinstance(track, Mapping):
            errors.extend(
                _validate_track_folds(
                    track_id,
                    track,
                    status,
                    declared_groups.get(track_id, set()),
                    track.get("fold_ids") if isinstance(track.get("fold_ids"), list) and all(
                        isinstance(fold_id, str) for fold_id in track["fold_ids"]
                    ) else [],
                    row_counts[track_id],
                ),
            )
    return errors


def _parse_system_soe_utc(value: object) -> float | None:
    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return None
    if parsed.tzinfo != timezone.utc:
        return None
    return parsed.timestamp()


def _validate_system_soe_metadata(
    metadata: object,
    *,
    feature_names: Sequence[str],
    row_groups: Sequence[str],
    cell_ids: Sequence[str],
    group_times: Mapping[str, Sequence[float]],
    row_labels: Sequence[float],
) -> list[str]:
    """Validate the system-level request-group split embedded in the version."""

    errors: list[str] = []
    if not isinstance(metadata, Mapping):
        return ["system_soe缺少目标元数据"]
    expected_identity = {
        "group_field": "RequID",
        "cell_id_semantics": "constant system marker; not a physical cell ID",
        "session_id_semantics": "source RequID group; not a time-series session",
        "cycle_index_semantics": "zero-based source data-row ordinal; not a cycle",
    }
    expected_label = {
        "name": "soe_source_value",
        "source_field": "SoE",
        "unit": "unspecified_source_unit",
    }
    expected_features = {
        "source_fields": ["SoC", "Ptcb", "Ptei"],
        "time_field": "Submission",
        "time_is_feature": False,
    }
    expected_rollback = {
        "policy": "immutable atomic no-replace publication; preserve all prior versions; failure produces only INVALIDATED",
        "previous_versions_modified": False,
        "existing_target_overwritten": False,
    }
    expected_metadata_fields = {
        "schema_version", "scope", "configuration_path", "configuration_sha256",
        "source_audit", "identity", "label", "features", "rollback", "split",
    }
    if set(metadata) != expected_metadata_fields:
        errors.append("system_soe目标元数据字段集合无效")
    if metadata.get("schema_version") != 1:
        errors.append("system_soe元数据版本无效")
    if metadata.get("scope") != "community_storage_system_only_not_cell_level":
        errors.append("system_soe范围必须限定为系统级")
    configuration_path = metadata.get("configuration_path")
    if not isinstance(configuration_path, str) or not Path(configuration_path).is_absolute():
        errors.append("system_soe配置路径必须为绝对路径")
    configuration_sha = metadata.get("configuration_sha256")
    if not isinstance(configuration_sha, str) or re.fullmatch(r"[0-9a-f]{64}", configuration_sha) is None:
        errors.append("system_soe配置SHA-256无效")
    source_audit = metadata.get("source_audit")
    expected_audit_fields = {
        "raw_data_row_count", "accepted_row_count", "rejected_row_count",
        "unique_requid_count", "accepted_group_count", "soe_missing_count",
        "soe_non_numeric_count", "soe_min", "soe_max",
    }
    if not isinstance(source_audit, Mapping) or set(source_audit) != expected_audit_fields:
        errors.append("system_soe来源统计结构无效")
    else:
        integer_names = (
            "raw_data_row_count", "accepted_row_count", "rejected_row_count",
            "unique_requid_count", "accepted_group_count", "soe_missing_count",
            "soe_non_numeric_count",
        )
        if any(type(source_audit.get(name)) is not int or source_audit[name] < 0 for name in integer_names):
            errors.append("system_soe来源行数统计无效")
        else:
            if source_audit["raw_data_row_count"] != source_audit["accepted_row_count"] + source_audit["rejected_row_count"]:
                errors.append("system_soe来源行数分解不一致")
            if source_audit["accepted_row_count"] != len(row_groups):
                errors.append("system_soe有效行数与samples不一致")
            if source_audit["unique_requid_count"] < source_audit["accepted_group_count"]:
                errors.append("system_soe来源RequID计数无效")
            if source_audit["accepted_group_count"] != len(set(row_groups)):
                errors.append("system_soe有效组数与samples不一致")
            if source_audit["soe_missing_count"] != 0 or source_audit["soe_non_numeric_count"] != 0:
                errors.append("system_soe SoE标签存在缺失或非数值")
        try:
            declared_min = float(source_audit["soe_min"])
            declared_max = float(source_audit["soe_max"])
        except (TypeError, ValueError):
            declared_min = declared_max = math.nan
        if (
            not row_labels
            or not math.isfinite(declared_min)
            or not math.isfinite(declared_max)
            or abs(min(row_labels) - declared_min) > 1e-9
            or abs(max(row_labels) - declared_max) > 1e-9
        ):
            errors.append("system_soe SoE范围与samples不一致")
    if metadata.get("identity") != expected_identity:
        errors.append("system_soe身份语义无效")
    if metadata.get("label") != expected_label:
        errors.append("system_soe标签或单位声明无效")
    if metadata.get("features") != expected_features or list(feature_names) != ["SoC", "Ptcb", "Ptei"]:
        errors.append("system_soe特征声明无效")
    if metadata.get("rollback") != expected_rollback:
        errors.append("system_soe回滚声明无效")

    split = metadata.get("split")
    expected_split_keys = {
        "axis", "policy", "train_fraction", "ordered_group_ids",
        "earliest_submission_utc", "train_group_ids", "test_group_ids",
        "train_row_count", "test_row_count", "validation", "early_stopping",
    }
    if not isinstance(split, Mapping) or set(split) != expected_split_keys:
        return errors + ["system_soe分组切分结构无效"]
    if (
        split.get("axis") != "RequID"
        or split.get("policy") != "earliest_submission_utc_then_requid; train=floor(0.8*n); remainder=test"
        or type(split.get("train_fraction")) is not float
        or split.get("train_fraction") != 0.8
        or split.get("validation", "missing") is not None
        or split.get("early_stopping") is not False
    ):
        errors.append("system_soe分组切分策略无效")

    ordered = split.get("ordered_group_ids")
    train = split.get("train_group_ids")
    test = split.get("test_group_ids")
    earliest = split.get("earliest_submission_utc")
    if (
        not isinstance(ordered, list)
        or not ordered
        or any(not isinstance(group, str) or not group.strip() for group in ordered)
        or len(ordered) != len(set(ordered))
        or not isinstance(train, list)
        or not isinstance(test, list)
        or not isinstance(earliest, Mapping)
    ):
        errors.append("system_soe分组切分列表无效")
        return errors
    if set(earliest) != set(ordered) or any(not isinstance(key, str) for key in earliest):
        errors.append("system_soe分组最早提交时间映射无效")
        return errors
    parsed_times = {group: _parse_system_soe_utc(earliest[group]) for group in ordered}
    if any(value is None for value in parsed_times.values()):
        errors.append("system_soe最早提交时间必须为UTC Z时间")
        return errors
    expected_order = sorted(ordered, key=lambda group: (parsed_times[group], group))
    if ordered != expected_order:
        errors.append("system_soe分组顺序与最早Submission不一致")
    train_count = math.floor(len(ordered) * 0.8)
    if train_count < 1 or train_count >= len(ordered):
        errors.append("system_soe分组数量无法形成非空80/20切分")
    if train != ordered[:train_count] or test != ordered[train_count:]:
        errors.append("system_soe分组切分与80/20时间顺序不一致")
    if set(train) & set(test) or set(train) | set(test) != set(ordered):
        errors.append("system_soe训练与测试RequID不互斥或未覆盖")

    actual_groups = set(row_groups)
    if actual_groups != set(ordered):
        errors.append("system_soe样本RequID与manifest分组不一致")
    if len(cell_ids) != len(row_groups) or set(cell_ids) != {"CBES_SYSTEM_NOT_CELL"}:
        errors.append("system_soe样本必须使用明确的非电芯系统标记")
    if set(group_times) != actual_groups:
        errors.append("system_soe样本时间分组不完整")
    else:
        for group in ordered:
            times = group_times[group]
            if not times or any(not math.isfinite(value) for value in times):
                errors.append("system_soe样本时间无效")
                break
            earliest_value = parsed_times[group]
            if abs(min(times) - earliest_value) > 1e-6:
                errors.append("system_soe最早Submission与样本时间不一致")
                break

    train_rows = sum(len(group_times.get(group, ())) for group in train)
    test_rows = sum(len(group_times.get(group, ())) for group in test)
    if type(split.get("train_row_count")) is not int or split.get("train_row_count") != train_rows:
        errors.append("system_soe训练样本行数不一致")
    if type(split.get("test_row_count")) is not int or split.get("test_row_count") != test_rows:
        errors.append("system_soe测试样本行数不一致")
    return errors


def build_version(
    target: str,
    rows: Iterable[CanonicalRow],
    contract: DatasetContract,
    output_root: str | Path,
    *,
    source_files: Iterable[str | Path] = (),
    row_track_ids: Iterable[str] | None = None,
    track_manifest: Mapping[str, object] | None = None,
    target_metadata: Mapping[str, object] | None = None,
) -> Path:
    """Validate and atomically publish one immutable baseline dataset version."""

    if target not in SUPPORTED_TARGETS:
        raise ValueError(f"不支持的目标：{target}")
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    destination = root / f"{target}-baseline-v1"
    if destination.exists():
        raise FileExistsError(f"数据版本已存在，禁止覆盖：{destination}")

    materialized_rows = list(rows)
    errors: list[str] = []
    dual_track_enabled = row_track_ids is not None or track_manifest is not None
    materialized_track_ids: list[object] | None = None
    track_snapshot: dict[str, object] | None = None
    target_snapshot: dict[str, object] | None = None
    if target == "system_soe":
        if target_metadata is None:
            errors.append("system_soe必须提供目标元数据")
        else:
            target_snapshot, snapshot_error = _snapshot_track_manifest(target_metadata)
            if snapshot_error is not None:
                errors.append(snapshot_error)
    elif target_metadata is not None:
        errors.append("目标元数据扩展仅支持system_soe")
    if dual_track_enabled:
        if row_track_ids is None or track_manifest is None:
            errors.append("row_track_ids与track_manifest必须同时提供")
        else:
            try:
                materialized_track_ids = list(row_track_ids)
            except Exception:
                errors.append("row_track_ids无法物化")
            track_snapshot, snapshot_error = _snapshot_track_manifest(track_manifest)
            if snapshot_error is not None:
                errors.append(snapshot_error)
            if target != "sot":
                errors.append("双轨构建仅支持sot")
            if materialized_track_ids is not None and track_snapshot is not None:
                if len(materialized_track_ids) != len(materialized_rows):
                    errors.append("样本轨道标识数量与数据行不一致")
                row_groups_and_tracks = [
                    ((row.cell_id, row.condition_id), track_id)
                    for row, track_id in zip(materialized_rows, materialized_track_ids)
                ]
                errors.extend(_validate_track_envelope(track_snapshot, row_groups_and_tracks))
    if target == "system_soe" and target_snapshot is not None:
        group_times: dict[str, list[float]] = {}
        for row in materialized_rows:
            group_times.setdefault(row.session_id, []).append(float(row.time_s))
        errors.extend(
            _validate_system_soe_metadata(
                target_snapshot,
                feature_names=contract.feature_names,
                row_groups=[row.session_id for row in materialized_rows],
                cell_ids=[row.cell_id for row in materialized_rows],
                group_times=group_times,
                row_labels=[float(row.label) for row in materialized_rows if row.label is not None],
            ),
        )
    if target != contract.target:
        errors.append("构建目标与合同不一致")
    errors.extend(validate_contract(contract, materialized_rows))
    resolved_sources = [Path(path).resolve() for path in source_files]
    if not resolved_sources:
        errors.append("来源文件清单为空")
    if len(resolved_sources) != len(set(resolved_sources)):
        errors.append("来源文件重复")
    for path in resolved_sources:
        if not path.is_file():
            errors.append(f"来源文件不存在：{path}")
    if errors:
        diagnostic = _record_invalidated(root, target, errors)
        raise DatasetBuildError(errors, diagnostic)

    temporary = Path(tempfile.mkdtemp(prefix=f".{target}-baseline-v1-", dir=root))
    try:
        samples_path = temporary / "samples.csv"
        fieldnames = [
            "target", *(["track_id"] if dual_track_enabled else []), "source_id", "cell_id", "session_id", "condition_id",
            "cycle_index", "time_s", *contract.feature_names, "label",
        ]
        with samples_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for index, row in enumerate(materialized_rows):
                record = {
                    "target": row.target,
                    "source_id": row.source_id,
                    "cell_id": row.cell_id,
                    "session_id": row.session_id,
                    "condition_id": row.condition_id,
                    "cycle_index": row.cycle_index,
                    "time_s": row.time_s,
                    "label": row.label,
                }
                if dual_track_enabled:
                    record["track_id"] = materialized_track_ids[index]
                record.update({name: row.features[name] for name in contract.feature_names})
                writer.writerow(record)

        sources_path = temporary / "source_files.csv"
        with sources_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["path", "size_bytes", "sha256"])
            writer.writeheader()
            for path in resolved_sources:
                writer.writerow({"path": str(path), "size_bytes": path.stat().st_size, "sha256": _sha256(path)})

        manifest_path = temporary / "manifest.json"
        manifest: dict[str, object] = {
            "schema_version": SCHEMA_VERSION,
            "version": f"{target}-baseline-v1",
            "target": target,
            "source_id": contract.source_id,
            "feature_names": list(contract.feature_names),
            "row_count": len(materialized_rows),
            "files": {
                "samples.csv": _sha256(samples_path),
                "source_files.csv": _sha256(sources_path),
            },
        }
        if dual_track_enabled:
            manifest.update(
                {
                    "row_metadata_fields": ["track_id"],
                    "label": {
                        "name": "sot_source_native_temperature",
                        "unit": "source-native-temperature",
                    },
                    "tracks": track_snapshot,
                },
            )
        if target == "system_soe" and target_snapshot is not None:
            manifest["target_metadata"] = target_snapshot
        _write_json(manifest_path, manifest)
        _write_json(
            temporary / "READY.json",
            {"schema_version": SCHEMA_VERSION, "manifest_sha256": _sha256(manifest_path)},
        )
        errors = verify_version(temporary, expected_version=f"{target}-baseline-v1")
        if errors:
            raise DatasetBuildError(errors, temporary)
        _publish_directory(temporary, destination)
    except FileExistsError:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(temporary, ignore_errors=True)
        errors = list(exc.errors) if isinstance(exc, DatasetBuildError) else [f"构建失败：{exc}"]
        diagnostic = _record_invalidated(root, target, errors)
        raise DatasetBuildError(errors, diagnostic) from exc
    return destination


def verify_version(
    version_dir: str | Path,
    *,
    expected_version: str | None = None,
) -> list[str]:
    """Read back a version and report every integrity error without repairing it."""

    version = Path(version_dir)
    errors: list[str] = []
    allowed_files = {"samples.csv", "manifest.json", "source_files.csv", "READY.json"}
    try:
        unexpected = sorted(path.name for path in version.iterdir() if path.name not in allowed_files)
    except OSError as exc:
        return [f"版本目录无法读取：{exc}"]
    for name in unexpected:
        errors.append(f"成功版本包含未声明文件：{name}")
    if (version / "READY.json").exists() and (version / "INVALIDATED.json").exists():
        errors.append("READY.json与INVALIDATED.json不能同时存在")
    required = ("samples.csv", "manifest.json", "source_files.csv", "READY.json")
    for name in required:
        if not (version / name).is_file():
            errors.append(f"缺少文件：{name}")
    if errors:
        return errors

    try:
        manifest = json.loads((version / "manifest.json").read_text(encoding="utf-8"))
        ready = json.loads((version / "READY.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"清单无法读取：{exc}"]
    if not isinstance(manifest, dict) or not isinstance(ready, dict):
        return ["清单格式无效"]
    target = manifest.get("target")
    version_name = manifest.get("version")
    directory_version = expected_version if expected_version is not None else version.name
    if (
        not isinstance(target, str)
        or target not in SUPPORTED_TARGETS
        or version_name != f"{target}-baseline-v1"
        or directory_version != version_name
    ):
        errors.append("清单目标与版本目录不一致")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append("manifest.json版本无效")
    if ready.get("schema_version") != SCHEMA_VERSION:
        errors.append("READY.json版本无效")
    if not isinstance(manifest.get("source_id"), str) or not manifest["source_id"].strip():
        errors.append("manifest.json来源无效")
    feature_names = manifest.get("feature_names")
    if (
        not isinstance(feature_names, list)
        or not feature_names
        or any(not isinstance(name, str) or not name for name in feature_names)
    ):
        errors.append("manifest.json特征无效")
    row_count = manifest.get("row_count")
    if not isinstance(row_count, int) or isinstance(row_count, bool) or row_count < 1:
        errors.append("manifest.json行数无效")
    dual_track_enabled = any(
        name in manifest for name in ("row_metadata_fields", "label", "tracks")
    )
    tracks = manifest.get("tracks")
    if dual_track_enabled:
        if target != "sot":
            errors.append("双轨构建仅支持sot")
        if manifest.get("row_metadata_fields") != ["track_id"]:
            errors.append("双轨行元数据声明无效")
        if manifest.get("label") != {
            "name": "sot_source_native_temperature",
            "unit": "source-native-temperature",
        }:
            errors.append("双轨标签声明无效")
    target_metadata = manifest.get("target_metadata")
    if target == "system_soe" and target_metadata is None:
        errors.append("system_soe版本缺少目标元数据")
    if target != "system_soe" and target_metadata is not None:
        errors.append("非system_soe版本不得含system_soe目标元数据")
    if ready.get("manifest_sha256") != _sha256(version / "manifest.json"):
        errors.append("manifest.json哈希不一致")
    declared_files = manifest.get("files")
    if not isinstance(declared_files, dict):
        errors.append("manifest.json缺少文件哈希")
    else:
        for name in ("samples.csv", "source_files.csv"):
            if declared_files.get(name) != _sha256(version / name):
                errors.append(f"{name}哈希不一致")

    try:
        with (version / "samples.csv").open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            records = list(reader)
        if isinstance(feature_names, list) and all(isinstance(name, str) for name in feature_names):
            expected_fields = [
                "target", *(["track_id"] if dual_track_enabled else []), "source_id", "cell_id", "session_id", "condition_id",
                "cycle_index", "time_s", *feature_names, "label",
            ]
            if reader.fieldnames != expected_fields:
                errors.append("samples.csv表头与清单不一致")
        if isinstance(row_count, int) and not isinstance(row_count, bool) and len(records) != row_count:
            errors.append("samples.csv行数与清单不一致")
        if isinstance(target, str) and any(record.get("target") != target for record in records):
            errors.append("samples.csv目标与清单不一致")
        source_id = manifest.get("source_id")
        if isinstance(source_id, str) and any(record.get("source_id") != source_id for record in records):
            errors.append("samples.csv来源与清单不一致")
        if target == "system_soe":
            parsed_group_times: dict[str, list[float]] = {}
            system_groups: list[str] = []
            system_cells: list[str] = []
            for record in records:
                group = record.get("session_id", "")
                try:
                    time_value = float(record.get("time_s", "nan"))
                except (TypeError, ValueError):
                    time_value = math.nan
                parsed_group_times.setdefault(group, []).append(time_value)
                system_groups.append(group)
                system_cells.append(record.get("cell_id", ""))
            errors.extend(
                _validate_system_soe_metadata(
                    target_metadata,
                    feature_names=feature_names if isinstance(feature_names, list) else [],
                    row_groups=system_groups,
                    cell_ids=system_cells,
                    group_times=parsed_group_times,
                    row_labels=[
                        float(record["label"])
                        for record in records
                        if record.get("label") not in (None, "")
                    ],
                ),
            )
            split = target_metadata.get("split") if isinstance(target_metadata, Mapping) else None
            ordered = split.get("ordered_group_ids") if isinstance(split, Mapping) else None
            if isinstance(ordered, list):
                seen_blocks: list[str] = []
                for group in system_groups:
                    if not seen_blocks or seen_blocks[-1] != group:
                        seen_blocks.append(group)
                if seen_blocks != ordered:
                    errors.append("system_soe样本行未按分组时间顺序连续排列")
        if dual_track_enabled:
            errors.extend(
                _validate_track_envelope(
                    tracks,
                    [
                        ((record.get("cell_id", ""), record.get("condition_id", "")), record.get("track_id"))
                        for record in records
                    ],
                ),
            )
    except (OSError, csv.Error) as exc:
        errors.append(f"samples.csv无法读取：{exc}")

    try:
        with (version / "source_files.csv").open(newline="", encoding="utf-8") as handle:
            source_reader = csv.DictReader(handle)
            if source_reader.fieldnames != ["path", "size_bytes", "sha256"]:
                errors.append("来源清单表头无效")
            source_records = list(source_reader)
            if not source_records:
                errors.append("来源文件清单为空")
            seen_sources: set[str] = set()
            for record in source_records:
                source_value = record.get("path")
                if not isinstance(source_value, str) or not source_value.strip():
                    errors.append("来源清单无法读取：path无效")
                    continue
                if source_value in seen_sources:
                    errors.append("来源文件重复")
                    continue
                seen_sources.add(source_value)
                source = Path(source_value)
                if not source.is_file():
                    errors.append(f"来源文件不存在：{source}")
                    continue
                if record.get("size_bytes") != str(source.stat().st_size):
                    errors.append(f"来源文件大小不一致：{source}")
                if record.get("sha256") != _sha256(source):
                    errors.append(f"来源文件哈希不一致：{source}")
    except (OSError, KeyError, csv.Error) as exc:
        errors.append(f"来源清单无法读取：{exc}")
    return errors
