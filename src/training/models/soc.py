from __future__ import annotations
import numpy as np
from .common import ValidationSelectedSpecialist


class SOCSpecialist(ValidationSelectedSpecialist):
    target_name = "soc"

    def postprocess(self, features: np.ndarray, prediction: np.ndarray) -> np.ndarray:
        return np.clip(prediction, 0.0, 1.0)
