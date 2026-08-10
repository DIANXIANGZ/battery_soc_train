"""Traceable offline-reference and causal online SOC labels."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class CapacityPoint:
    dataset_id: str; cell_id: str; session_id: str; cycle_id: str; timestamp_s: float; net_capacity_ah: float

@dataclass(frozen=True)
class CurrentPoint:
    dataset_id: str; cell_id: str; session_id: str; cycle_id: str; timestamp_s: float; current_a: float

@dataclass(frozen=True)
class LabelledPoint:
    timestamp_s: float; soc: float; label_method: str; reference_capacity_ah: float; initial_soc: float | None

def _boundary(point) -> tuple[str, str, str, str]:
    return point.dataset_id, point.cell_id, point.session_id, point.cycle_id

def _validate(points) -> tuple:
    rows = tuple(points)
    if not rows: raise ValueError("label generation requires at least one point")
    if len({_boundary(x) for x in rows}) != 1: raise ValueError("points must belong to a single boundary")
    if any(b.timestamp_s <= a.timestamp_s for a, b in zip(rows, rows[1:])): raise ValueError("timestamps must be strictly increasing")
    return rows

def offline_cycle_range_labels(points) -> tuple[LabelledPoint, ...]:
    rows = _validate(points); low = min(x.net_capacity_ah for x in rows); high = max(x.net_capacity_ah for x in rows); capacity = high - low
    if capacity <= 0: raise ValueError("cycle capacity range must be positive")
    return tuple(LabelledPoint(x.timestamp_s, (x.net_capacity_ah-low)/capacity, "offline_cycle_range", capacity, None) for x in rows)

def online_coulomb_labels(points, initial_soc: float, reference_capacity_ah: float) -> tuple[LabelledPoint, ...]:
    rows = _validate(points)
    if reference_capacity_ah <= 0: raise ValueError("reference capacity must be positive")
    if not 0 <= initial_soc <= 1: raise ValueError("initial_soc must be in [0, 1]")
    result = [LabelledPoint(rows[0].timestamp_s, initial_soc, "online_coulomb_history", reference_capacity_ah, initial_soc)]
    soc = initial_soc
    for previous, current in zip(rows, rows[1:]):
        delta_ah = .5 * (previous.current_a + current.current_a) * (current.timestamp_s-previous.timestamp_s) / 3600
        soc = min(1., max(0., soc + delta_ah/reference_capacity_ah))
        result.append(LabelledPoint(current.timestamp_s, soc, "online_coulomb_history", reference_capacity_ah, initial_soc))
    return tuple(result)
