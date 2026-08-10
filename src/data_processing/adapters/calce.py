"""CALCE battery-data adapter."""

from __future__ import annotations
from io import BytesIO
from pathlib import Path
import re
from zipfile import ZipFile
import pandas as pd
from .common import attach_causal_cycle_references, canonicalize_samples

ALIASES = {
    "Test_Time(s)": "timestamp_s", "Voltage(V)": "voltage_v", "Current(A)": "current_a",
    "Temperature(C)": "temperature_c", "Temperature (C)_1": "temperature_c", "Cycle_Index": "cycle_id",
}


def adapt_samples(frame: pd.DataFrame, source_hash: str, source_id: str = "calce_a123_dynamic_temperature") -> pd.DataFrame:
    return canonicalize_samples(frame, source_id=source_id, chemistry="LFP", aliases=ALIASES, source_hash=source_hash)


def load_samples(archive: Path, source_hash: str, stride: int = 1, source_id: str = "calce_a123_dynamic_temperature") -> pd.DataFrame:
    """Read CALCE channel sheets directly from the immutable ZIP archive."""

    frames = []
    with ZipFile(archive) as bundle:
        for member in sorted(
            name for name in bundle.namelist()
            if name.lower().endswith(".xlsx") and not Path(name).name.startswith("~$")
        ):
            content = BytesIO(bundle.read(member))
            workbook = pd.ExcelFile(content, engine="openpyxl")
            channel = next((sheet for sheet in workbook.sheet_names if sheet.startswith("Channel_")), None)
            if channel is None:
                continue
            raw = pd.read_excel(workbook, sheet_name=channel)
            raw = raw.iloc[::stride].copy()
            cell_id = Path(member).stem.split("-2012")[0]
            raw["cell_id"] = cell_id
            raw["session_id"] = Path(member).stem
            temperature_match = re.search(r"FUDS-(N?)(\d+)", archive.name, flags=re.IGNORECASE)
            if temperature_match:
                sign = "-" if temperature_match.group(1).upper() == "N" else ""
                condition = f"ambient_{sign}{temperature_match.group(2)}c"
            else:
                condition = "ambient_unknown"
            raw["condition_id"] = condition
            frames.append(adapt_samples(raw, source_hash, source_id=source_id))
    if not frames:
        raise ValueError(f"No CALCE channel sheets found in {archive}")
    return attach_causal_cycle_references(
        pd.concat(frames, ignore_index=True), nominal_capacity_ah=1.1, nominal_voltage_v=3.3,
    )
