"""Causal LSTM/GRU/TCN/Transformer regression candidates for battery windows."""

from __future__ import annotations

import random

import numpy as np
from sklearn.base import BaseEstimator, RegressorMixin
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset


class _SequenceNetwork(nn.Module):
    def __init__(self, kind: str, features: int, hidden: int) -> None:
        super().__init__()
        self.kind = kind
        if kind in {"lstm", "gru"}:
            self.core = (nn.LSTM if kind == "lstm" else nn.GRU)(features, hidden, batch_first=True)
        elif kind == "tcn":
            self.core = nn.Sequential(
                nn.Conv1d(features, hidden, kernel_size=3, padding=1, dilation=1), nn.ReLU(),
                nn.Conv1d(hidden, hidden, kernel_size=3, padding=2, dilation=2), nn.ReLU(),
            )
        elif kind == "transformer":
            self.input = nn.Linear(features, hidden)
            layer = nn.TransformerEncoderLayer(hidden, nhead=2, dim_feedforward=hidden * 2, batch_first=True)
            self.core = nn.TransformerEncoder(layer, num_layers=1)
        else:
            raise ValueError(f"Unsupported sequence model: {kind}")
        self.head = nn.Linear(hidden, 1)

    def forward(self, values: torch.Tensor) -> torch.Tensor:
        if self.kind in {"lstm", "gru"}:
            hidden = self.core(values)[0][:, -1]
        elif self.kind == "tcn":
            encoded = self.core(values.transpose(1, 2))
            hidden = encoded[:, :, -1]
        else:
            hidden = self.core(self.input(values))[:, -1]
        return self.head(hidden).squeeze(-1)


class TorchSequenceRegressor(RegressorMixin, BaseEstimator):
    def __init__(
        self,
        *,
        kind: str,
        window: int,
        features: int,
        hidden: int = 24,
        epochs: int = 5,
        batch_size: int = 256,
        learning_rate: float = 1e-3,
        seed: int = 43,
    ) -> None:
        self.kind = kind
        self.window = window
        self.features = features
        self.hidden = hidden
        self.epochs = epochs
        self.batch_size = batch_size
        self.learning_rate = learning_rate
        self.seed = seed

    def _reshape(self, values: np.ndarray) -> np.ndarray:
        values = np.asarray(values, dtype=np.float32)
        expected = self.window * self.features
        if values.ndim != 2 or values.shape[1] != expected:
            raise ValueError(f"Expected flattened windows with {expected} features")
        return values.reshape(len(values), self.window, self.features)

    def fit(self, features: np.ndarray, target: np.ndarray):
        random.seed(self.seed)
        np.random.seed(self.seed)
        torch.manual_seed(self.seed)
        torch.set_num_threads(1)
        values = self._reshape(features)
        target = np.asarray(target, dtype=np.float32).reshape(-1)
        self.feature_mean_ = values.mean(axis=(0, 1), keepdims=True)
        self.feature_std_ = values.std(axis=(0, 1), keepdims=True)
        self.feature_std_[self.feature_std_ < 1e-8] = 1.0
        self.target_mean_ = float(target.mean())
        self.target_std_ = float(target.std()) or 1.0
        normalized_x = (values - self.feature_mean_) / self.feature_std_
        normalized_y = (target - self.target_mean_) / self.target_std_
        self.model_ = _SequenceNetwork(self.kind, self.features, self.hidden)
        optimizer = torch.optim.Adam(self.model_.parameters(), lr=self.learning_rate)
        loss_function = nn.SmoothL1Loss()
        loader = DataLoader(
            TensorDataset(torch.from_numpy(normalized_x), torch.from_numpy(normalized_y)),
            batch_size=min(self.batch_size, len(normalized_x)), shuffle=True,
        )
        for _ in range(self.epochs):
            self.model_.train()
            for batch_x, batch_y in loader:
                optimizer.zero_grad()
                loss = loss_function(self.model_(batch_x), batch_y)
                loss.backward()
                optimizer.step()
        return self

    def predict(self, features: np.ndarray) -> np.ndarray:
        values = self._reshape(features)
        normalized = (values - self.feature_mean_) / self.feature_std_
        self.model_.eval()
        with torch.no_grad():
            prediction = self.model_(torch.from_numpy(normalized)).numpy()
        return prediction * self.target_std_ + self.target_mean_
