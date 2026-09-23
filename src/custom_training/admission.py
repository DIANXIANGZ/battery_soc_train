"""Fail-closed configuration and training admission for custom battery targets."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re

from src.custom_training.algorithms import ALGORITHM_REGISTRY
from src.custom_training.dataset import CustomDatasetConfig


BATTERY_TARGETS = frozenset({
    "soc", "soe", "soh", "sot", "sot_c", "sot_5min_c", "rul", "rul_cycles",
})
MINIMUM_EXACT_RUL_CELLS = 6
PYTORCH_TARGETS = frozenset({"soc", "soe", "soh", "sot"})
PYTORCH_ALGORITHMS = frozenset({"lstm", "gru", "transformer"})
_FORBIDDEN_VERSION_TOKENS = ("rul", "eol", "trajectory", "lifecycle")


def _manifest_integer(
    evidence: dict[str, object],
    field: str,
    blockers: list[str],
) -> int:
    value = evidence.get(field)
    if type(value) is not int:
        blockers.append(f"invalid_manifest:rul.{field}")
        return 0
    return value


@dataclass(frozen=True)
class TargetAdmission:
    target: str
    configuration_allowed: bool
    training_allowed: bool
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class CustomTrainingAdmission:
    configuration_allowed: bool
    training_allowed: bool
    generalization_level: str
    targets: tuple[TargetAdmission, ...]


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-fA-F]{64}", value) is None:
        raise ValueError(f"{field}_fingerprint_invalid")
    return value.lower()


def _load_json(path: Path, field: str) -> dict[str, object]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{field}_invalid") from error
    if not isinstance(value, dict):
        raise ValueError(f"{field}_invalid")
    return value


def _forbidden_version_field(
    value: object,
    location: str = "manifest",
    field_name: str | None = None,
) -> str | None:
    """Return the first RUL/lifecycle semantic field found in version evidence."""
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key).lower()
            key_tokens = set(re.findall(r"[a-z]+", key_text))
            if key_tokens.intersection(_FORBIDDEN_VERSION_TOKENS):
                return f"{location}.{key}"
            found = _forbidden_version_field(item, f"{location}.{key}", key_text)
            if found:
                return found
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            found = _forbidden_version_field(item, f"{location}[{index}]", field_name)
            if found:
                return found
    elif isinstance(value, str):
        # Filesystem paths may contain the project directory name ``non_rul``;
        # only semantic values are scanned, never path-bearing fields.
        if field_name and "path" in field_name:
            return None
        semantic_value = re.sub(r"non[_-]?rul", "", value.lower())
        tokens = set(re.findall(r"[a-z]+", semantic_value))
        if tokens.intersection(_FORBIDDEN_VERSION_TOKENS):
            return location
    return None


def validate_pytorch_entrypoint(
    manifest_path: Path,
    ready_path: Path,
    config_path: Path,
    *,
    target: str,
    algorithm: str,
    config_sha256: str | None,
    formal: bool = False,
    formal_training_authorized: bool = False,
) -> dict[str, object]:
    """Validate a version-bound PyTorch dry-run without reading samples or training."""
    normalized_target = str(target).strip().lower()
    if normalized_target not in PYTORCH_TARGETS:
        raise ValueError("unsupported_target")
    normalized_algorithm = str(algorithm).strip().lower()
    if normalized_algorithm not in PYTORCH_ALGORITHMS:
        raise ValueError("pytorch_algorithm_required")
    if formal and not formal_training_authorized:
        raise ValueError("formal_training_not_authorized")

    manifest_file = Path(manifest_path).resolve()
    ready_file = Path(ready_path).resolve()
    config_file = Path(config_path).resolve()
    if ready_file.parent != manifest_file.parent:
        raise ValueError("version_evidence_directory_mismatch")
    if (manifest_file.parent / "INVALIDATED.json").exists():
        raise ValueError("dataset_invalidated")
    for path, field in ((manifest_file, "manifest"), (ready_file, "ready"), (config_file, "config")):
        if not path.is_file():
            raise ValueError(f"{field}_missing")

    manifest = _load_json(manifest_file, "manifest")
    ready = _load_json(ready_file, "ready")
    config = _load_json(config_file, "config")
    forbidden = _forbidden_version_field(manifest)
    if forbidden:
        raise ValueError(f"forbidden_version_field:{forbidden}")

    manifest_target = manifest.get("target")
    if not isinstance(manifest_target, str) or manifest_target.strip().lower() != normalized_target:
        raise ValueError("target_mismatch")
    version = manifest.get("version")
    if not isinstance(version, str) or not version.strip():
        raise ValueError("manifest_version_missing")
    manifest_sha = _require_sha256(ready.get("manifest_sha256"), "manifest")
    actual_manifest_sha = _sha256_file(manifest_file)
    if manifest_sha != actual_manifest_sha:
        raise ValueError("manifest_fingerprint_mismatch")

    ready_sha = _require_sha256(config.get("dataset", {}).get("ready_sha256") if isinstance(config.get("dataset"), dict) else None, "ready")
    actual_ready_sha = _sha256_file(ready_file)
    if ready_sha != actual_ready_sha:
        raise ValueError("ready_fingerprint_mismatch")
    requested_config_sha = _require_sha256(config_sha256, "config")
    actual_config_sha = _sha256_file(config_file)
    if requested_config_sha != actual_config_sha:
        raise ValueError("config_fingerprint_mismatch")

    config_target = config.get("target")
    if not isinstance(config_target, str) or config_target.strip().lower() != normalized_target:
        raise ValueError("config_target_mismatch")
    config_algorithm = config.get("algorithm")
    if config_algorithm is None and isinstance(config.get("model"), dict):
        config_algorithm = config["model"].get("algorithm")
    if not isinstance(config_algorithm, str) or config_algorithm.strip().lower() != normalized_algorithm:
        raise ValueError("config_algorithm_mismatch")
    dataset = config.get("dataset")
    if not isinstance(dataset, dict):
        raise ValueError("config_dataset_missing")
    configured_path = dataset.get("path")
    if not isinstance(configured_path, str) or Path(configured_path).resolve() != manifest_file.parent:
        raise ValueError("config_dataset_path_mismatch")
    configured_manifest_sha = _require_sha256(dataset.get("manifest_sha256"), "manifest")
    if configured_manifest_sha != actual_manifest_sha:
        raise ValueError("config_manifest_fingerprint_mismatch")
    forbidden_config = _forbidden_version_field(config)
    if forbidden_config:
        raise ValueError(f"forbidden_config_field:{forbidden_config}")
    return {
        "status": "DRY_RUN_READY",
        "target": normalized_target,
        "algorithm": normalized_algorithm,
        "version": version,
        "manifest_sha256": actual_manifest_sha,
        "ready_sha256": actual_ready_sha,
        "config_sha256": actual_config_sha,
        "formal_training_authorized": bool(formal_training_authorized),
    }


def assess_custom_training(
    config: CustomDatasetConfig,
    *,
    manifest: dict[str, object] | None = None,
) -> CustomTrainingAdmission:
    roles = dict(config.role_columns)
    global_blockers: list[str] = []
    if manifest is None:
        evidence: dict[str, object] = {}
        global_blockers.append("manifest_missing")
    elif isinstance(manifest, dict):
        evidence = manifest
    else:
        evidence = {}
        global_blockers.append("invalid_manifest")
    if evidence.get("valid_for_training") is not True or evidence.get("training_authorized") is not True:
        global_blockers.append("dataset_frozen")
    if "cell_id" not in roles or "condition_id" not in roles:
        global_blockers.append("strict_group_split_unavailable")
    generalization_level = (
        "unseen_cell_and_condition"
        if "strict_group_split_unavailable" not in global_blockers
        else "configuration_only"
    )

    manifest_targets = evidence.get("targets")
    target_evidence = manifest_targets if isinstance(manifest_targets, dict) else {}
    if manifest_targets is not None and not isinstance(manifest_targets, dict):
        global_blockers.append("invalid_manifest:targets")
    results: list[TargetAdmission] = []
    for original_target in config.target_columns:
        key = original_target.strip().lower()
        blockers = list(global_blockers)
        required_roles = {"cell_id", "condition_id"}
        if key in {"soc", "soe", "sot", "sot_c", "sot_5min_c"}:
            required_roles.update({"session_id", "cycle_id"})
        if key in {"soh", "rul", "rul_cycles"}:
            required_roles.add("cycle_id")
        if key in {"rul", "rul_cycles"}:
            required_roles.update({"rul_observed", "eol_provenance"})
        blockers.extend(
            f"missing_role:{role}" for role in sorted(required_roles - set(roles))
        )

        item = target_evidence.get(original_target)
        item_evidence = item if isinstance(item, dict) else {}
        if key in BATTERY_TARGETS and item_evidence.get("causal_label_audit_passed") is not True:
            blockers.append("causal_label_audit_missing")
        if key in {"rul", "rul_cycles"}:
            raw_rul = evidence.get("rul")
            rul = raw_rul if isinstance(raw_rul, dict) else {}
            if not isinstance(raw_rul, dict):
                blockers.append("invalid_manifest:rul")
            exact_observed_cells = _manifest_integer(rul, "exact_observed_cells", blockers)
            grid_cycles = _manifest_integer(rul, "grid_cycles", blockers)
            if exact_observed_cells < MINIMUM_EXACT_RUL_CELLS:
                blockers.append("insufficient_exact_rul_cells")
            if grid_cycles != 1:
                blockers.append("rul_grid_not_one_cycle")
            if rul.get("task") != "point":
                blockers.append("rul_not_exact_point_task")
            if rul.get("censored_rows_are_exact_supervision") is not False:
                blockers.append("rul_censoring_contract_missing")
        if key not in BATTERY_TARGETS:
            for field in ("unit", "prediction_time", "acceptance_rule"):
                if not item_evidence.get(field):
                    blockers.append(f"custom_target_missing:{field}")
        unique_blockers = tuple(dict.fromkeys(blockers))
        results.append(TargetAdmission(
            target=original_target,
            configuration_allowed=True,
            training_allowed=not unique_blockers,
            blockers=unique_blockers,
            warnings=(),
        ))

    configuration_allowed = config.algorithm in ALGORITHM_REGISTRY and bool(config.target_columns)
    return CustomTrainingAdmission(
        configuration_allowed=configuration_allowed,
        training_allowed=(
            configuration_allowed and bool(results) and all(result.training_allowed for result in results)
        ),
        generalization_level=generalization_level,
        targets=tuple(results),
    )
