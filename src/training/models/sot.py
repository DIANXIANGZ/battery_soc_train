from __future__ import annotations
import numpy as np
from .common import ValidationSelectedSpecialist


class SOTResidualSpecialist(ValidationSelectedSpecialist):
    target_name = "sot_c"

    def __init__(
        self,
        last_temperature_index: int,
        seed: int = 43,
        sequence_shape: tuple[int, int] | None = None,
        deep_kinds: tuple[str, ...] = (),
        deep_epochs: int = 5,
    ) -> None:
        super().__init__(seed=seed, sequence_shape=sequence_shape, deep_kinds=deep_kinds, deep_epochs=deep_epochs)
        self.last_temperature_index = last_temperature_index

    def training_target(self, features: np.ndarray, target: np.ndarray) -> np.ndarray:
        return target - features[:, self.last_temperature_index]

    def validation_prediction(self, features: np.ndarray, prediction: np.ndarray) -> np.ndarray:
        return features[:, self.last_temperature_index] + prediction

    def postprocess(self, features: np.ndarray, prediction: np.ndarray) -> np.ndarray:
        return features[:, self.last_temperature_index] + prediction

    def artifact_manifest(self) -> dict[str, object]:
        payload = super().artifact_manifest()
        payload.update({
            "prediction_form": "last_temperature_plus_residual",
            "last_temperature_index": self.last_temperature_index,
        })
        return payload
