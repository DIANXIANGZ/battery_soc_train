"""Train/validation-only CORAL and MMD domain-alignment primitives."""

from __future__ import annotations

import numpy as np


def _matrix_power(matrix: np.ndarray, exponent: float, epsilon: float = 1e-6) -> np.ndarray:
    values, vectors = np.linalg.eigh(matrix)
    values = np.maximum(values, epsilon) ** exponent
    return (vectors * values) @ vectors.T


class CoralAdapter:
    def __init__(self) -> None:
        self.source_mean: np.ndarray | None = None
        self.target_mean: np.ndarray | None = None
        self.transform_matrix: np.ndarray | None = None
        self.source_keys: tuple[str, ...] = ()
        self.target_keys: tuple[str, ...] = ()

    def fit(
        self,
        source: np.ndarray,
        allowed_target: np.ndarray,
        *,
        source_keys: tuple[str, ...],
        target_keys: tuple[str, ...],
    ) -> "CoralAdapter":
        source = np.asarray(source, dtype=float)
        allowed_target = np.asarray(allowed_target, dtype=float)
        if source.ndim != 2 or allowed_target.ndim != 2 or source.shape[1] != allowed_target.shape[1]:
            raise ValueError("CORAL domains must be two-dimensional with matching features")
        self.source_mean = source.mean(axis=0)
        self.target_mean = allowed_target.mean(axis=0)
        source_covariance = np.atleast_2d(np.cov(source, rowvar=False))
        target_covariance = np.atleast_2d(np.cov(allowed_target, rowvar=False))
        self.transform_matrix = _matrix_power(source_covariance, -0.5) @ _matrix_power(target_covariance, 0.5)
        self.source_keys = tuple(source_keys)
        self.target_keys = tuple(target_keys)
        return self

    def transform(self, values: np.ndarray) -> np.ndarray:
        if self.transform_matrix is None or self.source_mean is None or self.target_mean is None:
            raise RuntimeError("CORAL adapter must be fitted before transform")
        values = np.asarray(values, dtype=float)
        return (values - self.source_mean) @ self.transform_matrix + self.target_mean

    def artifact_manifest(self) -> dict[str, object]:
        if self.transform_matrix is None:
            raise RuntimeError("CORAL adapter must be fitted before creating a manifest")
        return {
            "method": "CORAL",
            "source_keys": list(self.source_keys),
            "target_keys": list(self.target_keys),
            "test_domain_used": False,
        }


def mmd_rbf(source: np.ndarray, target: np.ndarray, gamma: float | None = None) -> float:
    source = np.asarray(source, dtype=float)
    target = np.asarray(target, dtype=float)
    combined = np.vstack([source, target])
    squared = np.sum((combined[:, None, :] - combined[None, :, :]) ** 2, axis=-1)
    if gamma is None:
        positive = squared[squared > 0]
        gamma = 1.0 / max(float(np.median(positive)) if positive.size else 1.0, 1e-12)
    kernel = np.exp(-gamma * squared)
    n_source = len(source)
    return float(
        kernel[:n_source, :n_source].mean()
        + kernel[n_source:, n_source:].mean()
        - 2.0 * kernel[:n_source, n_source:].mean()
    )
