"""Sandia cell cycle-testing adapter."""

from __future__ import annotations
import pandas as pd
from .common import canonicalize_samples

ALIASES = {"Test_Time_s": "timestamp_s", "Voltage_V": "voltage_v", "Current_A": "current_a", "Temperature_C": "temperature_c"}


def adapt_samples(frame: pd.DataFrame, source_hash: str) -> pd.DataFrame:
    return canonicalize_samples(frame, source_id="sandia_cell_cycle_testing", chemistry="mixed", aliases=ALIASES, source_hash=source_hash)
