from __future__ import annotations
import numpy as np
from .common import ValidationSelectedSpecialist


class SOHSpecialist(ValidationSelectedSpecialist):
    target_name = "soh"

    def postprocess(self, features: np.ndarray, prediction: np.ndarray) -> np.ndarray:
        bounded = np.clip(prediction, 0.0, 1.1)
        return np.minimum.accumulate(bounded)
