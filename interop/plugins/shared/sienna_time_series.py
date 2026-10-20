"""What every Sienna time series states about its snapshots, and the row that names it.

A staged time-series frame carries (snapshot, component, value) whichever framework staged
it, so nothing here reads a source framework.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import polars as pl

from interop.plugins.shared.constants import StagedTimeSeriesCol
from interop.plugins.shared.sienna_constants import (
    SiennaACBusCol,
    SiennaComponent,
    SiennaHydroGeneratorCol,
    SiennaLoadCol,
    SiennaRenewableGeneratorCol,
    SiennaStructField,
    SiennaThermalGeneratorCol,
    SiennaTimeSeriesAssociationCol,
)

# ISO 8601 duration strings for common snapshot intervals (seconds -> string).
_RESOLUTION_MAP: dict[int, str] = {
    900: "PT15M",
    1800: "PT30M",
    3600: "PT1H",
    86400: "P1D",
}

DEFAULT_RESOLUTION: str = "PT1H"
DEFAULT_RESOLUTION_MINUTES: float = 60.0


@dataclass
class TimeSeriesInfo:
    """Snapshot metadata aggregated by ``collect_ts_info`` from a time-series LazyFrame."""

    length: int
    resolution: str
    initial_timestamp: datetime | None
    resolution_minutes: float


def collect_ts_info(frame: pl.LazyFrame | None) -> TimeSeriesInfo:
    """Aggregate snapshot metadata from any time-series LazyFrame.

    Accepts any frame with columns (snapshot, component, value). Always returns a
    ``TimeSeriesInfo``; when ``frame`` is ``None`` the default resolution is used and
    ``length`` is 0.
    """
    if frame is None:
        return TimeSeriesInfo(
            length=0,
            resolution=DEFAULT_RESOLUTION,
            initial_timestamp=None,
            resolution_minutes=DEFAULT_RESOLUTION_MINUTES,
        )

    # A row with no snapshot is at no point in time and sorts first, so it would set the start.
    snapshots = (
        frame.select(pl.col(StagedTimeSeriesCol.SNAPSHOT))
        .drop_nulls()
        .unique()
        .sort(StagedTimeSeriesCol.SNAPSHOT)
        .collect(engine="streaming")[StagedTimeSeriesCol.SNAPSHOT]
    )
    length = snapshots.len()
    if length >= 2:
        delta_seconds = int(snapshots.head(2).diff().drop_nulls().dt.total_seconds()[0])
        resolution = _RESOLUTION_MAP.get(delta_seconds, f"PT{delta_seconds}S")
        resolution_minutes = delta_seconds / 60.0
    else:
        resolution = DEFAULT_RESOLUTION
        resolution_minutes = DEFAULT_RESOLUTION_MINUTES

    return TimeSeriesInfo(
        length=length,
        resolution=resolution,
        initial_timestamp=snapshots[0] if length else None,
        resolution_minutes=resolution_minutes,
    )


def _thermal_capacity(component: Mapping[str, Any]) -> float:
    limits = component[SiennaThermalGeneratorCol.ACTIVE_POWER_LIMITS]
    return float(limits[SiennaStructField.MAX])


def _renewable_capacity(component: Mapping[str, Any]) -> float:
    return float(component[SiennaRenewableGeneratorCol.RATING])


def _load_capacity(component: Mapping[str, Any]) -> float:
    return float(component[SiennaLoadCol.MAX_ACTIVE_POWER])


def _hydro_capacity(component: Mapping[str, Any]) -> float:
    return float(component[SiennaHydroGeneratorCol.BASE_POWER])


_CAPACITY_BY_OWNER_TYPE: dict[str, Callable[[Mapping[str, Any]], float]] = {
    SiennaComponent.THERMAL_STANDARD: _thermal_capacity,
    SiennaComponent.RENEWABLE_DISPATCH: _renewable_capacity,
    SiennaComponent.RENEWABLE_NON_DISPATCH: _renewable_capacity,
    SiennaComponent.POWER_LOAD: _load_capacity,
    SiennaComponent.INTERRUPTIBLE_POWER_LOAD: _load_capacity,
    SiennaComponent.HYDRO_DISPATCH: _hydro_capacity,
}


def has_series_capacity(owner_type: str) -> bool:
    """Whether a series capacity is defined for this owner type."""
    return owner_type in _CAPACITY_BY_OWNER_TYPE


def build_capacity_by_owner(
    owners: Iterable[tuple[str, int]],
    components_by_type: Mapping[str, Iterable[Mapping[str, Any]]],
) -> dict[tuple[str, int], float]:
    """The megawatts one per-unit value of each owner's series stands for, by ``(type, id)``."""
    wanted = set(owners)
    return {
        (owner_type, component[SiennaACBusCol.ID]): _CAPACITY_BY_OWNER_TYPE[owner_type](component)
        for owner_type in {owner_type for owner_type, _ in wanted}
        for component in components_by_type.get(owner_type, [])
        if (owner_type, component[SiennaACBusCol.ID]) in wanted
    }


def ts_association_row(
    *,
    owner_type: str,
    owner_id: int,
    component_name: str,
    series_name: str,
    ts_info: TimeSeriesInfo,
    source_table: str,
    source_attribute: str,
    scaling_factor: float,
) -> dict[str, Any]:
    """One SingleTimeSeries TimeSeriesAssociation row keyed for the h5 sink to resolve.

    ``source_table`` and ``source_attribute`` are the key the sink looks the staged frame up
    by, so they stay in the source framework's own words and never reach the emitted JSON.
    """
    col = SiennaTimeSeriesAssociationCol
    return {
        col.INITIAL_TIMESTAMP: (
            ts_info.initial_timestamp.isoformat() if ts_info.initial_timestamp is not None else None
        ),
        col.RESOLUTION: ts_info.resolution,
        col.LENGTH: ts_info.length,
        col.NAME: series_name,
        col.OWNER_ID: owner_id,
        col.OWNER_TYPE: owner_type,
        col.COMPONENT_NAME: component_name,
        col.SOURCE_TABLE: source_table,
        col.SOURCE_ATTRIBUTE: source_attribute,
        col.SCALING_FACTOR: scaling_factor,
    }
