"""Single registry for user-selectable battery training algorithms."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AlgorithmSpec:
    key: str
    label: str
    family: str
    isolated_worker: bool
    recommended_targets: tuple[str, ...]


ALGORITHM_REGISTRY = {
    "lstm": AlgorithmSpec("lstm", "LSTM", "sequence", False, ("soc", "soe", "sot")),
    "gru": AlgorithmSpec("gru", "GRU", "sequence", False, ("soc", "soe", "sot")),
    "xgboost": AlgorithmSpec("xgboost", "XGBoost", "tabular_window", True, ("soh", "rul")),
    "transformer": AlgorithmSpec(
        "transformer", "Transformer", "sequence", False, ("soc", "soe", "sot", "soh")
    ),
}


def algorithm_keys() -> tuple[str, ...]:
    return tuple(ALGORITHM_REGISTRY)


def recommend_algorithm(targets: tuple[str, ...]) -> str:
    normalized = tuple(target.strip().lower() for target in targets)
    if normalized and all("rul" in target or "soh" in target for target in normalized):
        return "xgboost"
    return "lstm"
