"""Validation-selected model interface shared by battery specialists."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
from sklearn.base import RegressorMixin
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge


@dataclass(frozen=True)
class SpecialistDataset:
    features: np.ndarray
    target: np.ndarray

    def arrays(self) -> tuple[np.ndarray, np.ndarray]:
        features = np.asarray(self.features, dtype=float)
        target = np.asarray(self.target, dtype=float).reshape(-1)
        if len(features) != len(target) or not len(target):
            raise ValueError("Specialist features and target must be aligned and non-empty")
        return flatten_features(features), target


def flatten_features(features: np.ndarray) -> np.ndarray:
    values = np.asarray(features, dtype=float)
    if values.ndim < 2:
        raise ValueError("Specialist features must have at least two dimensions")
    return values.reshape(len(values), -1)


class ValidationSelectedSpecialist:
    target_name = "unknown"

    def __init__(
        self,
        seed: int = 43,
        sequence_shape: tuple[int, int] | None = None,
        deep_kinds: tuple[str, ...] = (),
        deep_epochs: int = 5,
    ) -> None:
        self.seed = seed
        self.sequence_shape = sequence_shape
        self.deep_kinds = deep_kinds
        self.deep_epochs = deep_epochs
        self.model: RegressorMixin | None = None
        self.candidate_name: str | None = None
        self.validation_mae: float | None = None

    def candidates(self) -> tuple[tuple[str, Callable[[], RegressorMixin]], ...]:
        candidates: list[tuple[str, Callable[[], RegressorMixin]]] = [
            ("ridge", lambda: Ridge(alpha=1e-3)),
            ("hist_gradient_boosting", lambda: HistGradientBoostingRegressor(max_iter=100, random_state=self.seed)),
        ]
        if self.sequence_shape is not None:
            from .sequence import TorchSequenceRegressor

            window, features = self.sequence_shape
            candidates.extend(
                (
                    f"causal_{kind}",
                    lambda kind=kind: TorchSequenceRegressor(
                        kind=kind, window=window, features=features, epochs=self.deep_epochs, seed=self.seed,
                    ),
                )
                for kind in self.deep_kinds
            )
        return tuple(candidates)

    def training_target(self, features: np.ndarray, target: np.ndarray) -> np.ndarray:
        return target

    def validation_prediction(self, features: np.ndarray, prediction: np.ndarray) -> np.ndarray:
        return prediction

    def postprocess(self, features: np.ndarray, prediction: np.ndarray) -> np.ndarray:
        return prediction

    def fit(self, train: SpecialistDataset, validation: SpecialistDataset) -> "ValidationSelectedSpecialist":
        train_x, train_y = train.arrays()
        validation_x, validation_y = validation.arrays()
        transformed_train_y = self.training_target(train_x, train_y)
        best: tuple[float, str, RegressorMixin] | None = None
        for name, factory in self.candidates():
            model = factory()
            model.fit(train_x, transformed_train_y)
            prediction = self.validation_prediction(validation_x, np.asarray(model.predict(validation_x), dtype=float))
            mae = float(np.mean(np.abs(validation_y - prediction)))
            if best is None or mae < best[0]:
                best = (mae, name, model)
        if best is None:
            raise RuntimeError("No specialist model candidate was fitted")
        self.validation_mae, self.candidate_name, self.model = best
        return self

    def predict(self, features: np.ndarray) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("Specialist must be fitted before prediction")
        values = flatten_features(features)
        prediction = np.asarray(self.model.predict(values), dtype=float).reshape(-1)
        return self.postprocess(values, prediction)

    def artifact_manifest(self) -> dict[str, object]:
        if self.model is None:
            raise RuntimeError("Specialist must be fitted before creating a manifest")
        return {
            "target": self.target_name,
            "candidate": self.candidate_name,
            "selected_by": "validation_mae_only",
            "validation_mae": self.validation_mae,
            "seed": self.seed,
        }
