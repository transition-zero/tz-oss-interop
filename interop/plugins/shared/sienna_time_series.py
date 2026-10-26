"""What every Sienna time series states about its snapshots, and the row that names it.

A staged time-series frame carries (snapshot, component, value) whichever framework staged
it, so nothing here reads a source framework.
"""

from __future__ import annotations

import uuid as _uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import polars as pl

from interop.plugins.shared.constants import Framework, StagedTimeSeriesCol
from interop.plugins.shared.sienna_constants import (
    SiennaComponent,
    SiennaTimeSeriesAssociationCol,
    time_series_uuid,
)
from interop.plugins.shared.translation_runner import Translation
from interop.ports.outbound.reporting import DestinationField, EventKind, TranslationEvent

# ISO 8601 duration strings for common snapshot intervals (seconds -> string).
_RESOLUTION_MAP: dict[int, str] = {
    900: "PT15M",
    1800: "PT30M",
    3600: "PT1H",
    86400: "P1D",
}

DEFAULT_RESOLUTION: str = "PT1H"
DEFAULT_RESOLUTION_MINUTES: float = 60.0


def _build_association_id_events(
    _old: dict[str, Any], new: dict[str, Any]
) -> list[TranslationEvent]:
    col = SiennaTimeSeriesAssociationCol
    return [
        TranslationEvent(
            kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
            destinations=[
                DestinationField(
                    framework=Framework.SIENNA,
                    component=SiennaComponent.TIME_SERIES_ASSOCIATION,
                    name=f"{new[col.COMPONENT_NAME]}.{new[col.NAME]}",
                    attribute=col.ASSOCIATION_ID,
                    value=new[col.ASSOCIATION_ID],
                )
            ],
            note="assigned by 1-based row position in the time-series association table",
        )
    ]


TIME_SERIES_ASSOCIATION_ID = Translation(
    exprs=[
        pl.int_range(1, pl.len() + 1, dtype=pl.Int64).alias(
            SiennaTimeSeriesAssociationCol.ASSOCIATION_ID
        )
    ],
    make_events=_build_association_id_events,
)


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
        col.TIME_SERIES_UUID: time_series_uuid(owner_type, component_name, series_name),
        col.TIME_SERIES_TYPE: "SingleTimeSeries",
        col.INITIAL_TIMESTAMP: (
            ts_info.initial_timestamp.isoformat() if ts_info.initial_timestamp is not None else None
        ),
        col.RESOLUTION: ts_info.resolution,
        col.LENGTH: ts_info.length,
        col.NAME: series_name,
        col.OWNER_ID: owner_id,
        col.OWNER_TYPE: owner_type,
        col.OWNER_CATEGORY: "Component",
        col.FEATURES: "[]",
        col.SCALING_FACTOR_MULTIPLIER: "PowerSystems.get_max_active_power",
        col.METADATA_UUID: str(_uuid.uuid4()),
        col.COMPONENT_NAME: component_name,
        col.SOURCE_TABLE: source_table,
        col.SOURCE_ATTRIBUTE: source_attribute,
        col.SCALING_FACTOR: scaling_factor,
    }
