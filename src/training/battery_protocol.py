"""Strict split, preprocessing, leakage-audit and acceptance primitives."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.base import clone


@dataclass(frozen=True)
class NestedGroupFold:
    fold_id: str
    test_group: str
    test_condition: str
    validation_group: str
    train_indices: np.ndarray
    validation_indices: np.ndarray
    test_indices: np.ndarray


@dataclass(frozen=True)
class LeakageAudit:
    passed: bool
    train_count: int
    validation_count: int
    test_count: int
    violations: tuple[str, ...]


@dataclass(frozen=True)
class TransformedPartitions:
    fitted: object
    train: np.ndarray
    validation: np.ndarray
    test: np.ndarray


def fit_normalizer(train: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    train = np.asarray(train, dtype=float)
    mean = train.mean(axis=tuple(range(train.ndim - 1)))
    std = train.std(axis=tuple(range(train.ndim - 1)))
    return mean, np.where(std < 1e-8, 1.0, std)


def nested_group_folds(groups: np.ndarray, conditions: np.ndarray, seed: int = 43) -> tuple[NestedGroupFold, ...]:
    """Hold out one complete cell and one complete operating condition per outer fold."""

    groups = np.asarray(groups).astype(str)
    conditions = np.asarray(conditions).astype(str)
    if groups.ndim != 1 or conditions.ndim != 1 or len(groups) != len(conditions):
        raise ValueError("groups and conditions must be equal-length one-dimensional arrays")
    unique_groups = np.unique(groups)
    unique_conditions = np.unique(conditions)
    if len(unique_groups) < 3:
        raise ValueError("At least three cell groups are required")
    if len(unique_conditions) < 2:
        raise ValueError("At least two operating conditions are required")
    random = np.random.default_rng(seed)
    ordered_groups = unique_groups[random.permutation(len(unique_groups))]
    ordered_conditions = unique_conditions[random.permutation(len(unique_conditions))]
    folds: list[NestedGroupFold] = []
    for fold_number, test_group in enumerate(ordered_groups, start=1):
        test_condition = ordered_conditions[(fold_number - 1) % len(ordered_conditions)]
        test_mask = (groups == test_group) | (conditions == test_condition)
        validation_candidates = [group for group in ordered_groups if group != test_group]
        validation_group = validation_candidates[(fold_number - 1) % len(validation_candidates)]
        validation_mask = (~test_mask) & (groups == validation_group)
        train_mask = (~test_mask) & (~validation_mask)
        if not train_mask.any() or not validation_mask.any() or not test_mask.any():
            continue
        folds.append(NestedGroupFold(
            fold_id=f"outer-{fold_number:02d}",
            test_group=str(test_group),
            test_condition=str(test_condition),
            validation_group=str(validation_group),
            train_indices=np.flatnonzero(train_mask),
            validation_indices=np.flatnonzero(validation_mask),
            test_indices=np.flatnonzero(test_mask),
        ))
    if len(folds) < 3:
        raise ValueError("Group/condition layout cannot produce three non-empty strict folds")
    return tuple(folds)


def audit_split(groups: np.ndarray, conditions: np.ndarray, fold: NestedGroupFold) -> LeakageAudit:
    groups = np.asarray(groups).astype(str)
    conditions = np.asarray(conditions).astype(str)
    train = set(map(int, fold.train_indices))
    validation = set(map(int, fold.validation_indices))
    test = set(map(int, fold.test_indices))
    violations: list[str] = []
    if train & validation or train & test or validation & test:
        violations.append("partition_index_overlap")
    if fold.test_group in set(groups[fold.train_indices]):
        violations.append("test_group_in_train")
    if fold.test_condition in set(conditions[fold.train_indices]):
        violations.append("test_condition_in_train")
    if fold.validation_group in set(groups[fold.train_indices]):
        violations.append("validation_group_in_train")
    return LeakageAudit(
        passed=not violations,
        train_count=len(train),
        validation_count=len(validation),
        test_count=len(test),
        violations=tuple(violations),
    )


def fit_transform_train_only(transformer: object, train: np.ndarray, validation: np.ndarray, test: np.ndarray) -> TransformedPartitions:
    """Clone and fit preprocessing exclusively on the training partition."""

    fitted = clone(transformer)
    fitted.fit(train)
    return TransformedPartitions(
        fitted=fitted,
        train=np.asarray(fitted.transform(train)),
        validation=np.asarray(fitted.transform(validation)),
        test=np.asarray(fitted.transform(test)),
    )


def validate_windows(group_keys: np.ndarray, windows: list[tuple[int, int]]) -> None:
    group_keys = np.asarray(group_keys).astype(str)
    for start, stop in windows:
        if start < 0 or stop > len(group_keys) or start >= stop:
            raise ValueError("Invalid window bounds")
        if len(set(group_keys[start:stop])) != 1:
            raise ValueError("Window crosses a cell/session/cycle boundary")


def target_acceptance(
    target: str,
    reference: np.ndarray,
    prediction: np.ndarray,
    minimum_coverage: float = 0.95,
) -> dict[str, object]:
    reference = np.asarray(reference, dtype=float)
    prediction = np.asarray(prediction, dtype=float)
    if reference.shape != prediction.shape or reference.size == 0:
        raise ValueError("reference and prediction must have the same non-empty shape")
    finite = np.isfinite(reference) & np.isfinite(prediction)
    if not finite.any():
        raise ValueError("No finite reference/prediction pairs")
    reference = reference[finite]
    prediction = prediction[finite]
    errors = np.abs(reference - prediction)
    key = target.lower()
    if key in {"rul", "rul_cycles"}:
        sample_limits = np.ones_like(reference)
        mae_limit = 1.0
    elif key in {"sot", "sot_c", "sot_5min_c"}:
        sample_limits = 0.10 * np.abs(reference)
        mae_limit = float(0.10 * np.mean(np.abs(reference)))
    elif key in {"soc", "soe", "soh"}:
        sample_limits = np.full_like(reference, 0.01)
        mae_limit = 0.01
    else:
        raise ValueError(f"Unsupported battery target: {target}")
    mae = float(np.mean(errors))
    rmse = float(np.sqrt(np.mean(np.square(errors))))
    coverage = float(np.mean(errors <= sample_limits + 1e-12))
    passed_mae = mae <= mae_limit + 1e-12
    passed_coverage = coverage >= minimum_coverage - 1e-12
    return {
        "target": target,
        "sample_count": int(len(errors)),
        "mae": mae,
        "rmse": rmse,
        "mae_limit": mae_limit,
        "coverage": coverage,
        "minimum_coverage": float(minimum_coverage),
        "passed_mae": bool(passed_mae),
        "passed_coverage": bool(passed_coverage),
        "passed": bool(passed_mae and passed_coverage),
    }


def acceptance(target: str, mae: float, label_values: np.ndarray) -> dict[str, object]:
    """Backward-compatible MAE-only acceptance helper used by legacy trainers."""

    key = target.lower()
    limit = 1.0 if key in {"rul", "rul_cycles"} else (
        0.10 * float(np.mean(np.abs(label_values))) if key in {"sot", "sot_5min_c", "sot_c"} else 0.01
    )
    return {"target": target, "mae": float(mae), "limit": limit, "passed": bool(mae <= limit)}
