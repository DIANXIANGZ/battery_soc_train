"""NASA accelerated-life-test adapter."""

from __future__ import annotations
import pandas as pd
from .common import canonicalize_samples

ALIASES = {"Time": "timestamp_s", "Voltage": "voltage_v", "Current": "current_a", "Temperature": "temperature_c"}


def adapt_samples(frame: pd.DataFrame, source_hash: str) -> pd.DataFrame:
    return canonicalize_samples(frame, source_id="nasa_randomized_recommissioned", chemistry="NCA", aliases=ALIASES, source_hash=source_hash)
