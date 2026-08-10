"""Oxford battery degradation adapter."""

from __future__ import annotations
from pathlib import Path
import re
import numpy as np
import pandas as pd
from scipy.io import loadmat
from .common import attach_causal_cycle_references, canonicalize_samples

ALIASES = {"t": "timestamp_s", "V": "voltage_v", "I": "current_a", "T": "temperature_c"}


def adapt_samples(frame: pd.DataFrame, source_hash: str) -> pd.DataFrame:
    return canonicalize_samples(frame, source_id="oxford_battery_degradation_1", chemistry="LCO", aliases=ALIASES, source_hash=source_hash)


def load_samples(path: Path, source_hash: str, phase: str = "C1dc", stride: int = 10) -> pd.DataFrame:
    """Read Oxford reference-cycle traces and derive current from recorded charge."""

    payload = loadmat(path, simplify_cells=True)
    frames = []
    for cell_id in sorted(key for key in payload if re.fullmatch(r"Cell\d+", key)):
        for cycle_name, cycle in payload[cell_id].items():
            if phase not in cycle:
                continue
            trace = cycle[phase]
            time_days = np.asarray(trace["t"], dtype=float).reshape(-1)
            voltage = np.asarray(trace["v"], dtype=float).reshape(-1)
            charge_ah = np.asarray(trace["q"], dtype=float).reshape(-1) / 1000.0
            temperature = np.asarray(trace["T"], dtype=float).reshape(-1)
            time_s = (time_days - time_days[0]) * 86400.0
            current = np.gradient(charge_ah, time_s) * 3600.0
            selected = np.arange(0, len(time_s), stride)
            raw = pd.DataFrame({
                "t": time_s[selected], "V": voltage[selected], "I": current[selected], "T": temperature[selected],
                "cell_id": cell_id, "session_id": f"{cell_id}_{phase}",
                "cycle_id": int(cycle_name.removeprefix("cyc")),
                "condition_id": f"temperature_{round(float(np.nanmean(temperature)) / 5) * 5:.0f}c",
                "charge_ah": charge_ah[selected],
            })
            frames.append(adapt_samples(raw, source_hash))
    if not frames:
        raise ValueError(f"No Oxford {phase} traces found in {path}")
    return attach_causal_cycle_references(
        pd.concat(frames, ignore_index=True), nominal_capacity_ah=0.74, nominal_voltage_v=3.7,
    )
