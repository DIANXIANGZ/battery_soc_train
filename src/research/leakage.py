"""Guards against boundary, domain and fitted-statistic leakage."""
from __future__ import annotations
from dataclasses import dataclass
import statistics
from src.research.schema import SampleKey, SampleRecord

@dataclass(frozen=True)
class WindowSpec:
    start: int
    stop: int

@dataclass(frozen=True)
class FeatureStatistics:
    voltage_mean: float
    voltage_std: float
    current_mean: float
    current_std: float
    source_keys: frozenset[SampleKey]

def _boundary(r): return (r.key.dataset_id,r.key.cell_id,r.key.session_id,r.key.cycle_id)

def assert_window_boundaries(records, windows) -> None:
    rows=tuple(records)
    for window in windows:
        if window.start < 0 or window.stop > len(rows) or window.start >= window.stop: raise ValueError("invalid window bounds")
        if len({_boundary(x) for x in rows[window.start:window.stop]}) != 1: raise ValueError("window crosses dataset/cell/session/cycle boundary")

def assert_disjoint_domains(train, validation, test) -> None:
    groups=[{(r.key.dataset_id,r.key.cell_id) for r in rows} for rows in (train,validation,test)]
    if groups[0]&groups[1] or groups[0]&groups[2] or groups[1]&groups[2]: raise ValueError("train/validation/test cell overlap detected")

def fit_training_statistics(records) -> FeatureStatistics:
    rows=tuple(records)
    if not rows: raise ValueError("statistics require training records")
    volts=[x.voltage_v for x in rows]; currents=[x.current_a for x in rows]
    return FeatureStatistics(statistics.mean(volts),statistics.pstdev(volts),statistics.mean(currents),statistics.pstdev(currents),frozenset(x.key for x in rows))

def assert_statistics_provenance(statistics_: FeatureStatistics, allowed_keys) -> None:
    if not statistics_.source_keys <= set(allowed_keys): raise ValueError("statistics contain rows outside training domain")
