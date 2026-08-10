"""Causal SOH-trajectory plus learned-residual RUL specialist."""

from __future__ import annotations

import numpy as np
from sklearn.linear_model import LinearRegression

from .common import SpecialistDataset, ValidationSelectedSpecialist


class RULSpecialist(ValidationSelectedSpecialist):
    target_name = "rul_cycles"

    def __init__(
        self,
        current_soh_index: int | None = None,
        slope_index: int | None = None,
        *,
        eol_soh: float = 0.8,
        seed: int = 43,
    ) -> None:
        super().__init__(seed=seed)
        self.current_soh_index = current_soh_index
        self.slope_index = slope_index
        self.eol_soh = eol_soh
        self.fallback_slope = -1e-4
        self.prediction_mode = "trajectory_residual" if self.trajectory_enabled else "direct"

    @property
    def trajectory_enabled(self) -> bool:
        return self.current_soh_index is not None and self.slope_index is not None

    def candidates(self):
        if self.trajectory_enabled:
            return super().candidates()
        return (("unbounded_linear_trajectory", LinearRegression),)

    def fit(self, train: SpecialistDataset, validation: SpecialistDataset) -> "RULSpecialist":
        if self.trajectory_enabled:
            train_x, train_y = train.arrays()
            slopes = train_x[:, int(self.slope_index)]
            negative = slopes[np.isfinite(slopes) & (slopes < -1e-9)]
            if negative.size:
                self.fallback_slope = float(np.median(negative))
            else:
                soh = train_x[:, int(self.current_soh_index)]
                inferred = (self.eol_soh - soh) / np.maximum(train_y, 1.0)
                inferred = inferred[np.isfinite(inferred) & (inferred < -1e-9)]
                if inferred.size:
                    self.fallback_slope = float(np.median(inferred))
        super().fit(train, validation)
        if self.trajectory_enabled:
            trajectory_model = self.model
            trajectory_name = self.candidate_name
            trajectory_mae = float(self.validation_mae)
            train_x, train_y = train.arrays()
            validation_x, validation_y = validation.arrays()
            best_direct = None
            for name, factory in super().candidates():
                model = factory()
                model.fit(train_x, train_y)
                prediction = np.asarray(model.predict(validation_x), dtype=float)
                mae = float(np.mean(np.abs(validation_y - prediction)))
                if best_direct is None or mae < best_direct[0]:
                    best_direct = (mae, f"direct_{name}", model)
            if best_direct is not None and best_direct[0] < trajectory_mae:
                self.validation_mae, self.candidate_name, self.model = best_direct
                self.prediction_mode = "direct"
            else:
                self.model = trajectory_model
                self.candidate_name = trajectory_name
                self.validation_mae = trajectory_mae
                self.prediction_mode = "trajectory_residual"
        return self

    def _trajectory(self, features: np.ndarray) -> np.ndarray:
        if not self.trajectory_enabled:
            return np.zeros(len(features), dtype=float)
        soh = features[:, int(self.current_soh_index)]
        slope = features[:, int(self.slope_index)]
        usable_slope = np.where(np.isfinite(slope) & (slope < -1e-9), slope, self.fallback_slope)
        return np.maximum((soh - self.eol_soh) / np.maximum(-usable_slope, 1e-9), 0.0)

    def training_target(self, features: np.ndarray, target: np.ndarray) -> np.ndarray:
        return target - self._trajectory(features)

    def validation_prediction(self, features: np.ndarray, prediction: np.ndarray) -> np.ndarray:
        return self._trajectory(features) + prediction

    def postprocess(self, features: np.ndarray, prediction: np.ndarray) -> np.ndarray:
        if self.prediction_mode == "direct":
            return np.maximum(prediction, 0.0)
        return np.maximum(self._trajectory(features) + prediction, 0.0)

    def artifact_manifest(self) -> dict[str, object]:
        payload = super().artifact_manifest()
        payload.update({
            "prediction_form": self.prediction_mode,
            "eol_soh": self.eol_soh,
            "fallback_slope": self.fallback_slope,
            "upper_label_clip": False,
        })
        return payload
