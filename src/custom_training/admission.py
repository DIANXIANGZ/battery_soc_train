"""Fail-closed configuration and training admission for custom battery targets."""

from __future__ import annotations

from dataclasses import dataclass

from src.custom_training.algorithms import ALGORITHM_REGISTRY
from src.custom_training.dataset import CustomDatasetConfig


BATTERY_TARGETS = frozenset({
    "soc", "soe", "soh", "sot", "sot_c", "sot_5min_c", "rul", "rul_cycles",
})
MINIMUM_EXACT_RUL_CELLS = 6


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
