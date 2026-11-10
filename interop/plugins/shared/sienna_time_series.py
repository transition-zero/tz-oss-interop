"""What every Sienna time series states about its snapshots, and the row that names it.

A staged time-series frame carries (snapshot, component, value) whichever framework staged
it, so nothing here reads a source framework.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, NamedTuple

import polars as pl

from interop.plugins.shared.constants import StagedTimeSeriesCol
from interop.plugins.shared.sienna_constants import (
    InfraStoreSeriesLabel,
    SiennaACBusCol,
    SiennaComponent,
    SiennaHydroGeneratorCol,
    SiennaHydroReservoirCol,
    SiennaLevelDataType,
    SiennaLoadCol,
    SiennaRenewableGeneratorCol,
    SiennaReserveCol,
    SiennaStructField,
    SiennaThermalGeneratorCol,
    SiennaTimeSeriesAssociationCol,
)
from interop.plugins.shared.warning_text import name_a_few

log = logging.getLogger(__name__)

# ISO 8601 duration strings for common snapshot intervals (seconds -> string).
_RESOLUTION_MAP: dict[int, str] = {
    900: "PT15M",
    1800: "PT30M",
    3600: "PT1H",
    86400: "P1D",
}

DEFAULT_RESOLUTION: str = "PT1H"
DEFAULT_RESOLUTION_MINUTES: float = 60.0

# The columns of the per-component aggregate that build_ts_info_by_component reads.
_LENGTH = "length"
_FIRST = "first_snapshot"
_SECOND = "second_snapshot"


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
        return build_ts_info(0, None, None)

    # A row with no snapshot is at no point in time and sorts first, so it would set the start.
    snapshots = (
        frame.select(pl.col(StagedTimeSeriesCol.SNAPSHOT))
        .drop_nulls()
        .unique()
        .sort(StagedTimeSeriesCol.SNAPSHOT)
        .collect(engine="streaming")[StagedTimeSeriesCol.SNAPSHOT]
    )
    length = snapshots.len()
    return build_ts_info(
        length, snapshots[0] if length else None, snapshots[1] if length >= 2 else None
    )


def build_ts_info_by_component(frame: pl.LazyFrame | None) -> dict[str, TimeSeriesInfo]:
    """The snapshot metadata of each component's own series, from one aggregate of the frame."""
    if frame is None:
        return {}
    snapshot = pl.col(StagedTimeSeriesCol.SNAPSHOT)
    per_component = (
        frame.select(StagedTimeSeriesCol.COMPONENT, StagedTimeSeriesCol.SNAPSHOT)
        .drop_nulls()
        .group_by(StagedTimeSeriesCol.COMPONENT)
        .agg(
            snapshot.n_unique().alias(_LENGTH),
            snapshot.min().alias(_FIRST),
            snapshot.filter(snapshot > snapshot.min()).min().alias(_SECOND),
        )
        .collect(engine="streaming")
    )
    return {
        row[StagedTimeSeriesCol.COMPONENT]: build_ts_info(row[_LENGTH], row[_FIRST], row[_SECOND])
        for row in per_component.iter_rows(named=True)
    }


def build_ts_info(length: int, first: datetime | None, second: datetime | None) -> TimeSeriesInfo:
    """The metadata of a series of ``length`` snapshots, stepped by its first two snapshots."""
    if first is None or second is None:
        resolution, resolution_minutes = DEFAULT_RESOLUTION, DEFAULT_RESOLUTION_MINUTES
    else:
        delta_seconds = int((second - first).total_seconds())
        resolution = _RESOLUTION_MAP.get(delta_seconds, f"PT{delta_seconds}S")
        resolution_minutes = delta_seconds / 60.0
    return TimeSeriesInfo(
        length=length,
        resolution=resolution,
        initial_timestamp=first,
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


def _reserve_capacity(component: Mapping[str, Any]) -> float:
    return float(component[SiennaReserveCol.REQUIREMENT])


def _build_unit_capacity(component: Mapping[str, Any]) -> float:
    """A reservoir inflow is stored as the model states it, not as a share of a capacity."""
    return 1.0


_CAPACITY_BY_OWNER_TYPE: dict[str, Callable[[Mapping[str, Any]], float]] = {
    SiennaComponent.THERMAL_STANDARD: _thermal_capacity,
    SiennaComponent.RENEWABLE_DISPATCH: _renewable_capacity,
    SiennaComponent.RENEWABLE_NON_DISPATCH: _renewable_capacity,
    SiennaComponent.POWER_LOAD: _load_capacity,
    SiennaComponent.INTERRUPTIBLE_POWER_LOAD: _load_capacity,
    SiennaComponent.HYDRO_DISPATCH: _hydro_capacity,
    SiennaComponent.ONLINE_RESERVE: _reserve_capacity,
    SiennaComponent.OFFLINE_RESERVE: _reserve_capacity,
    SiennaComponent.HYDRO_TURBINE: _hydro_capacity,
    SiennaComponent.HYDRO_RESERVOIR: _build_unit_capacity,
}


class SeriesLabels(NamedTuple):
    """What a stored series states about its values: their unit and what they measure."""

    units: str
    quantity_kind: str


POWER_LABELS = SeriesLabels(
    InfraStoreSeriesLabel.UNITS_POWER, InfraStoreSeriesLabel.QUANTITY_ACTIVE_POWER
)


def _read_reservoir_labels(component: Mapping[str, Any]) -> SeriesLabels:
    """An ENERGY reservoir refills in MW. Every other level type refills in m3/s."""
    if component.get(SiennaHydroReservoirCol.LEVEL_DATA_TYPE) == SiennaLevelDataType.ENERGY:
        return SeriesLabels(
            InfraStoreSeriesLabel.UNITS_POWER, InfraStoreSeriesLabel.QUANTITY_INFLOW
        )
    return SeriesLabels(InfraStoreSeriesLabel.UNITS_FLOW, InfraStoreSeriesLabel.QUANTITY_INFLOW)


_LABELS_BY_OWNER_TYPE: dict[str, Callable[[Mapping[str, Any]], SeriesLabels]] = {
    SiennaComponent.HYDRO_RESERVOIR: _read_reservoir_labels,
}


def build_labels_by_owner(
    owners: Iterable[tuple[str, int]],
    components_by_type: Mapping[str, Iterable[Mapping[str, Any]]],
) -> dict[tuple[str, int], SeriesLabels]:
    """The labels of each owner's series, by ``(type, id)``, for the owners that are not power."""
    wanted = set(owners)
    return {
        (owner_type, component[SiennaACBusCol.ID]): _LABELS_BY_OWNER_TYPE[owner_type](component)
        for owner_type in {owner_type for owner_type, _ in wanted}
        if owner_type in _LABELS_BY_OWNER_TYPE
        for component in components_by_type.get(owner_type, [])
        if (owner_type, component[SiennaACBusCol.ID]) in wanted
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


UNSCALABLE_LOAD_SERIES_NOTE = (
    "the profile peaks at 0 MW and falls below it, so its max_active_power of 0 scales "
    "nothing and the profile is left out"
)


def is_unscalable_load_series(peak: float, lowest: float) -> bool:
    """Whether a load profile peaks at zero yet falls below it, so its peak scales nothing back."""
    return peak == 0 and lowest < 0


def warn_unscalable_load_series(names: list[str]) -> None:
    """Name the loads whose profile is left out because its peak of zero scales nothing."""
    if names:
        log.warning(
            "%d load profile(s) peak at 0 MW and fall below it, so no max_active_power "
            "scales them and each is left out: %s",
            len(names),
            name_a_few(names),
        )


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
