"""MIT/Stanford fast-charge dataset adapter."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
from pathlib import Path

import h5py
import numpy as np
import pandas as pd

from .common import canonicalize_samples

ALIASES = {"t": "timestamp_s", "V": "voltage_v", "I": "current_a", "T": "temperature_c"}
NOMINAL_CAPACITY_AH = 1.1
MIN_CAPACITY_AH = 0.5 * NOMINAL_CAPACITY_AH
MAX_CAPACITY_AH = 1.3 * NOMINAL_CAPACITY_AH
EOL_CAPACITY_AH = 0.88
EARLY_TERMINATED_CELLS = frozenset({"b1c8", "b1c10", "b1c12", "b1c13", "b1c22"})
OFFICIAL_CONTINUATION_MAPPING = (
    {"batch1_cell_id": "b1c0", "batch2_index_zero_based": 7, "batch2_index_one_based": 8, "add_len": 661, "expected_cycle_count": 662, "cycle_life": 663},
    {"batch1_cell_id": "b1c1", "batch2_index_zero_based": 8, "batch2_index_one_based": 9, "add_len": 980, "expected_cycle_count": 981, "cycle_life": 982},
    {"batch1_cell_id": "b1c2", "batch2_index_zero_based": 9, "batch2_index_one_based": 10, "add_len": 1059, "expected_cycle_count": 1060, "cycle_life": 1061},
    {"batch1_cell_id": "b1c3", "batch2_index_zero_based": 15, "batch2_index_one_based": 16, "add_len": 207, "expected_cycle_count": 208, "cycle_life": 209},
    {"batch1_cell_id": "b1c4", "batch2_index_zero_based": 16, "batch2_index_one_based": 17, "add_len": 481, "expected_cycle_count": 482, "cycle_life": 483},
)
OFFICIAL_BATCH2_EVIDENCE = {
    "project_id": "5c48dd2bc625d700019f3204",
    "batch_id": "5c86bf14fa2ede00015ddd83",
    "file_id": "5c86bf13fa2ede00015ddd82",
    "source_url": "https://data.matr.io/1/api/v1/file/5c86bf13fa2ede00015ddd82/download",
    "license": {"label": "CC BY 4", "url": "https://creativecommons.org/licenses/by/4.0/"},
    "byte_count": 2007331155,
    "sha256": "63ab200d09ecb237fee5ef3a5c5db76e3212e3206a0bd92f769e1427fed338b8",
    "mapping_repository": "https://github.com/rdbraatz/data-driven-prediction-of-battery-cycle-life-before-capacity-degradation",
    "mapping_repo_commit": "1ef13d27c66dc3d73affdaa008fbeba5687b2ea4",
    "mapping_file": "LoadData.m",
    "mapping_file_sha256": "7914333f0a963a0742d9fff340f1d4bc2ad912f1b04a236b3ae6c39fedd3623d",
}


def validate_official_continuation_mapping(
    mapping: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    normalized = [dict(item) for item in mapping]
    expected = [dict(item) for item in OFFICIAL_CONTINUATION_MAPPING]
    if normalized != expected:
        raise ValueError("Only the official MATR continuation mapping is accepted")
    return normalized


def validate_official_batch2_manifest(manifest: Mapping[str, object]) -> Mapping[str, object]:
    expected = {
        **OFFICIAL_BATCH2_EVIDENCE,
        "official_continuation_mapping": [dict(item) for item in OFFICIAL_CONTINUATION_MAPPING],
    }
    observed = {key: manifest.get(key) for key in expected}
    if observed != expected:
        raise ValueError("Manifest does not contain exact official MATR Batch 2 evidence")
    validate_official_continuation_mapping(manifest["official_continuation_mapping"])  # type: ignore[arg-type]
    return manifest


def verify_archive_identity(path: Path, expected_bytes: int, expected_sha256: str) -> str:
    if path.stat().st_size != expected_bytes:
        raise ValueError("MATR Batch 2 byte count does not match the official manifest")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    actual = digest.hexdigest()
    if actual != expected_sha256:
        raise ValueError("MATR Batch 2 SHA-256 does not match the official manifest")
    return actual


def classify_eol(
    cell_id: str,
    *,
    cycle_ids: np.ndarray,
    capacities_ah: np.ndarray,
    continuation: Mapping[str, object] | None = None,
) -> dict[str, object]:
    cycles = np.asarray(cycle_ids, dtype=float).reshape(-1)
    capacities = np.asarray(capacities_ah, dtype=float).reshape(-1)
    if len(cycles) != len(capacities) or not len(cycles):
        raise ValueError("MATR cycle ids and capacities must be aligned and non-empty")
    if cell_id in EARLY_TERMINATED_CELLS:
        return {
            "eol_cycle": np.nan,
            "eol_cycle_observed": 0,
            "eol_provenance": "right_censored",
        }
    expected_by_cell = {str(item["batch1_cell_id"]): item for item in OFFICIAL_CONTINUATION_MAPPING}
    if continuation is not None:
        expected = expected_by_cell.get(cell_id)
        if expected is None:
            raise ValueError("Official continuation cannot be attached to this MATR cell")
        batch1_end = int(continuation.get("batch1_end_cycle", -1))
        first_appended = int(continuation.get("first_appended_cycle", -1))
        last_appended = int(continuation.get("last_appended_cycle", -1))
        appended_count = int(continuation.get("appended_cycle_count", -1))
        batch2_cycle_life = int(continuation.get("batch2_cycle_life", -1))
        structure_valid = (
            int(continuation.get("batch2_index_zero_based", -1)) == expected["batch2_index_zero_based"]
            and appended_count == expected["expected_cycle_count"]
            and batch2_cycle_life == expected["cycle_life"]
            and first_appended == batch1_end + 1
            and last_appended == first_appended + appended_count - 1
            and np.any(cycles == first_appended)
            and np.any(cycles == last_appended)
        )
        if not structure_valid:
            raise ValueError("MATR official continuation structure is inconsistent")
        return {
            "eol_cycle": float(batch1_end + batch2_cycle_life),
            "eol_cycle_observed": 1,
            "eol_provenance": "official_continuation",
        }
    if cell_id in expected_by_cell:
        return {
            "eol_cycle": np.nan,
            "eol_cycle_observed": 0,
            "eol_provenance": "right_censored",
        }
    crossings = np.flatnonzero(np.isfinite(capacities) & (capacities <= EOL_CAPACITY_AH))
    if crossings.size:
        return {
            "eol_cycle": float(cycles[int(crossings[0])]),
            "eol_cycle_observed": 1,
            "eol_provenance": "observed_eol_crossing",
        }
    return {
        "eol_cycle": np.nan,
        "eol_cycle_observed": 0,
        "eol_provenance": "right_censored",
    }


def adapt_samples(frame: pd.DataFrame, source_hash: str) -> pd.DataFrame:
    converted = frame.copy()
    converted["t"] = pd.to_numeric(converted["t"], errors="raise") * 60.0
    return canonicalize_samples(converted, source_id="mit_stanford_fast_charge", chemistry="LFP", aliases=ALIASES, source_hash=source_hash)


def capacity_is_plausible(capacity_ah: float) -> bool:
    """Reject gross MATR cycle artifacts outside the physical A123 cell range."""

    return bool(np.isfinite(capacity_ah) and MIN_CAPACITY_AH <= capacity_ah <= MAX_CAPACITY_AH)


def causal_qd_state(qd_ah: np.ndarray, voltage_v: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Build causal charge/energy counters from native per-sample MATR Qd."""

    qd = np.asarray(qd_ah, dtype=float).reshape(-1)
    voltage = np.asarray(voltage_v, dtype=float).reshape(-1)
    if not len(qd) or len(qd) != len(voltage):
        raise ValueError("MATR Qd and voltage must be aligned and non-empty")
    if not np.isfinite(qd).all() or not np.isfinite(voltage).all():
        raise ValueError("MATR Qd and voltage must be finite")
    cumulative_charge = np.maximum.accumulate(np.maximum(qd, 0.0))
    charge_increment = np.diff(cumulative_charge, prepend=0.0)
    cumulative_energy = np.cumsum(charge_increment * np.abs(voltage))
    return cumulative_charge, cumulative_energy


def _read_vector(handle: h5py.File, dataset: h5py.Dataset) -> np.ndarray:
    values = np.asarray(dataset)
    if h5py.check_dtype(ref=values.dtype) is not None:
        return np.hstack([np.asarray(handle[reference]).reshape(-1) for reference in values.reshape(-1)])
    return values.reshape(-1)


def _decode_policy(handle: h5py.File, reference: h5py.Reference) -> str:
    values = np.asarray(handle[reference]).reshape(-1)
    return "".join(chr(int(value)) for value in values if int(value)).strip()


def _read_cycle_life(handle: h5py.File, batch: h5py.Group, cell_index: int) -> int | None:
    if "cycle_life" not in batch:
        return None
    values = np.asarray(handle[batch["cycle_life"][cell_index, 0]]).reshape(-1)
    if not values.size or not np.isfinite(values[0]):
        return None
    return int(values[0])


def _load_cell_frames(
    handle: h5py.File,
    batch: h5py.Group,
    cell_index: int,
    *,
    cell_id: str,
    session_id: str,
    cycle_offset: int,
    source_hash: str,
    stride: int,
    previous_capacity_ah: float,
    previous_energy_wh: float,
) -> tuple[list[pd.DataFrame], list[dict[str, object]], list[int], list[float], float, float]:
    frames: list[pd.DataFrame] = []
    excluded_cycles: list[dict[str, object]] = []
    accepted_cycle_ids: list[int] = []
    accepted_capacities: list[float] = []
    summary = handle[batch["summary"][cell_index, 0]]
    cycle_ids = _read_vector(handle, summary["cycle"]).astype(int)
    cycles = handle[batch["cycles"][cell_index, 0]]
    policy = _decode_policy(handle, batch["policy_readable"][cell_index, 0])
    cycle_count = min(cycles[field].shape[0] for field in ("I", "V", "T", "t", "Qd", "Qc"))
    for cycle_index in range(cycle_count):
        vectors = {
            field: np.asarray(handle[cycles[field][cycle_index, 0]]).reshape(-1)
            for field in ("I", "V", "T", "t", "Qd", "Qc")
        }
        length = min(len(vector) for vector in vectors.values())
        discharge_positions = np.flatnonzero(vectors["I"][:length] < -1e-8)
        if discharge_positions.size < 2:
            continue
        discharge_slice = slice(int(discharge_positions[0]), int(discharge_positions[-1]) + 1)
        vectors = {field: vector[discharge_slice] for field, vector in vectors.items()}
        length = min(len(vector) for vector in vectors.values())
        native_charge_ah, native_energy_wh = causal_qd_state(vectors["Qd"], vectors["V"])
        current_capacity_ah = float(native_charge_ah[-1])
        raw_cycle_id = int(cycle_ids[cycle_index]) if cycle_index < len(cycle_ids) else cycle_index + 1
        cycle_id = cycle_offset + raw_cycle_id
        if not capacity_is_plausible(current_capacity_ah):
            excluded_cycles.append({
                "cell_id": cell_id,
                "cycle_id": cycle_id,
                "capacity_ah": current_capacity_ah,
                "reason": "gross_capacity_outlier",
            })
            continue
        current_energy_wh = float(native_energy_wh[-1])
        selected = np.unique(np.append(np.arange(0, length, stride), length - 1))
        raw = pd.DataFrame({
            "I": vectors["I"][selected],
            "V": vectors["V"][selected],
            "T": vectors["T"][selected],
            "t": vectors["t"][selected],
            "Discharge_Capacity(Ah)": vectors["Qd"][selected],
            "Charge_Capacity(Ah)": vectors["Qc"][selected],
            "native_cumulative_charge_ah": native_charge_ah[selected],
            "native_cumulative_energy_wh": native_energy_wh[selected],
            "cell_id": cell_id,
            "session_id": session_id,
            "cycle_id": cycle_id,
            "condition_id": policy or "charge_policy_unknown",
            "capacity_reference_ah": previous_capacity_ah,
            "energy_reference_wh": previous_energy_wh,
            "initial_soc": 1.0,
            "initial_soe": 1.0,
            "cycle_capacity_ah": current_capacity_ah,
            "cycle_energy_wh": current_energy_wh,
        })
        frames.append(adapt_samples(raw, source_hash))
        accepted_cycle_ids.append(cycle_id)
        accepted_capacities.append(current_capacity_ah)
        if np.isfinite(current_capacity_ah) and current_capacity_ah > 0:
            previous_capacity_ah = current_capacity_ah
        if np.isfinite(current_energy_wh) and current_energy_wh > 0:
            previous_energy_wh = current_energy_wh
    return (
        frames,
        excluded_cycles,
        accepted_cycle_ids,
        accepted_capacities,
        previous_capacity_ah,
        previous_energy_wh,
    )


def load_samples(
    path: Path,
    source_hash: str,
    stride: int = 20,
    *,
    continuation_path: Path | None = None,
    continuation_hash: str | None = None,
    continuation_mapping: Sequence[Mapping[str, object]] | None = None,
) -> pd.DataFrame:
    """Read the official MATLAB-v7.3 MATR batch without loading it fully into memory."""

    if stride < 1:
        raise ValueError("stride must be positive")
    if any(value is not None for value in (continuation_path, continuation_hash, continuation_mapping)):
        if continuation_path is None or continuation_hash is None or continuation_mapping is None:
            raise ValueError("Official MATR continuation path, hash, and mapping must be supplied together")
        validated_mapping = validate_official_continuation_mapping(continuation_mapping)
        canonical_hash = hashlib.sha256(f"{source_hash}:{continuation_hash}".encode("ascii")).hexdigest()
    else:
        validated_mapping = []
        canonical_hash = source_hash
    mapping_by_cell = {str(item["batch1_cell_id"]): item for item in validated_mapping}
    frames: list[pd.DataFrame] = []
    excluded_cycles: list[dict[str, object]] = []
    continuation_handle = h5py.File(continuation_path, "r") if continuation_path is not None else None
    try:
        with h5py.File(path, "r") as handle:
            batch = handle["batch"]
            continuation_batch = continuation_handle["batch"] if continuation_handle is not None else None
            cell_count = batch["summary"].shape[0]
            if continuation_batch is not None:
                max_index = max(int(item["batch2_index_zero_based"]) for item in validated_mapping)
                if continuation_batch["summary"].shape[0] <= max_index:
                    raise ValueError("Official MATR Batch 2 structure does not contain every mapped cell")
            for cell_index in range(cell_count):
                cell_id = f"b1c{cell_index}"
                previous_capacity_ah = NOMINAL_CAPACITY_AH
                previous_energy_wh = NOMINAL_CAPACITY_AH * 3.3
                (
                    cell_frames,
                    cell_excluded,
                    cell_cycle_ids,
                    cell_capacities,
                    previous_capacity_ah,
                    previous_energy_wh,
                ) = _load_cell_frames(
                    handle,
                    batch,
                    cell_index,
                    cell_id=cell_id,
                    session_id="2017-05-12",
                    cycle_offset=0,
                    source_hash=canonical_hash,
                    stride=stride,
                    previous_capacity_ah=previous_capacity_ah,
                    previous_energy_wh=previous_energy_wh,
                )
                excluded_cycles.extend(cell_excluded)
                continuation_record: dict[str, object] | None = None
                mapping = mapping_by_cell.get(cell_id)
                if mapping is not None and continuation_batch is not None and continuation_handle is not None:
                    batch2_index = int(mapping["batch2_index_zero_based"])
                    batch2_summary = continuation_handle[continuation_batch["summary"][batch2_index, 0]]
                    batch2_cycle_ids = _read_vector(continuation_handle, batch2_summary["cycle"]).astype(int)
                    batch2_cycles = continuation_handle[continuation_batch["cycles"][batch2_index, 0]]
                    batch2_count = min(
                        batch2_cycles[field].shape[0] for field in ("I", "V", "T", "t", "Qd", "Qc")
                    )
                    authoritative_cycle_life = _read_cycle_life(
                        continuation_handle, continuation_batch, batch2_index,
                    )
                    expected_count = int(mapping["expected_cycle_count"])
                    if (
                        batch2_count != expected_count
                        or len(batch2_cycle_ids) != expected_count
                        or not np.array_equal(batch2_cycle_ids, np.arange(1, expected_count + 1))
                        or authoritative_cycle_life != int(mapping["cycle_life"])
                    ):
                        raise ValueError("Official MATR continuation structure is inconsistent")
                    batch1_end_cycle = max(cell_cycle_ids)
                    (
                        batch2_frames,
                        batch2_excluded,
                        batch2_accepted_ids,
                        batch2_capacities,
                        previous_capacity_ah,
                        previous_energy_wh,
                    ) = _load_cell_frames(
                        continuation_handle,
                        continuation_batch,
                        batch2_index,
                        cell_id=cell_id,
                        session_id="2017-06-30",
                        cycle_offset=batch1_end_cycle,
                        source_hash=canonical_hash,
                        stride=stride,
                        previous_capacity_ah=previous_capacity_ah,
                        previous_energy_wh=previous_energy_wh,
                    )
                    cell_frames.extend(batch2_frames)
                    excluded_cycles.extend(batch2_excluded)
                    cell_cycle_ids.extend(batch2_accepted_ids)
                    cell_capacities.extend(batch2_capacities)
                    continuation_record = {
                        "batch2_index_zero_based": batch2_index,
                        "batch1_end_cycle": batch1_end_cycle,
                        "first_appended_cycle": batch1_end_cycle + 1,
                        "last_appended_cycle": batch1_end_cycle + expected_count,
                        "appended_cycle_count": expected_count,
                        "batch2_cycle_life": authoritative_cycle_life,
                    }
                if not cell_frames:
                    continue
                status = classify_eol(
                    cell_id,
                    cycle_ids=np.asarray(cell_cycle_ids),
                    capacities_ah=np.asarray(cell_capacities),
                    continuation=continuation_record,
                )
                for frame in cell_frames:
                    for key, value in status.items():
                        frame[key] = value
                frames.extend(cell_frames)
    finally:
        if continuation_handle is not None:
            continuation_handle.close()
    if not frames:
        raise ValueError(f"No MATR cycle traces found in {path}")
    result = pd.concat(frames, ignore_index=True)
    result.attrs["excluded_cycles"] = excluded_cycles
    return result
