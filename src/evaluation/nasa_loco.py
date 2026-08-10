"""Deterministic leave-one-cell-out splits for the NASA RW cell set."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class LocoFold:
    """One leakage-safe train/validation/test assignment at cell level."""

    name: str
    train_cells: tuple[str, str]
    validation_cell: str
    test_cell: str


def assert_no_fold_leakage(fold: LocoFold) -> None:
    """Reject any split where a cell appears in more than one role."""
    roles = [*fold.train_cells, fold.validation_cell, fold.test_cell]
    if len(set(roles)) != 4:
        raise ValueError(f"Fold {fold.name} has overlapping cell roles: {roles}")


def make_loco_folds(cells: Sequence[str]) -> tuple[LocoFold, ...]:
    """Return four reproducible folds: one test, one validation, two training cells."""
    ordered = tuple(sorted(cells))
    if len(ordered) != 4 or len(set(ordered)) != 4:
        raise ValueError("NASA LOCO evaluation requires exactly four unique cells.")
    folds: list[LocoFold] = []
    for index, test_cell in enumerate(ordered):
        validation_cell = ordered[(index + 1) % len(ordered)]
        train_cells = tuple(cell for cell in ordered if cell not in {test_cell, validation_cell})
        fold = LocoFold(f"test_{test_cell}", train_cells, validation_cell, test_cell)
        assert_no_fold_leakage(fold)
        folds.append(fold)
    return tuple(folds)
