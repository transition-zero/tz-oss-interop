from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import polars as pl

from interop.plugins.shared.pypsa_constants import (
    DEFAULT_SNAPSHOT_MINUTES,
    DEFAULT_SNAPSHOT_RESOLUTION,
    PyPSATimeSeriesCol,
)

# ISO 8601 duration strings for common snapshot intervals (seconds -> string).
_RESOLUTION_MAP: dict[int, str] = {
    900: "PT15M",
    1800: "PT30M",
    3600: "PT1H",
    86400: "P1D",
}


@dataclass
class TimeSeriesInfo:
    """Snapshot metadata aggregated by ``collect_ts_info`` from a time-series LazyFrame."""

    length: int
    resolution: str
    initial_timestamp: datetime | None
    resolution_minutes: float


def collect_ts_info(ts_p: pl.LazyFrame | None) -> TimeSeriesInfo:
    """Aggregate snapshot metadata from any time-series LazyFrame.

    Accepts any frame with columns (snapshot, component, value). Always returns
    a ``TimeSeriesInfo``; when ``ts_p`` is ``None`` the default snapshot resolution is
    used and ``length`` is 0.
    """
    if ts_p is None:
        return TimeSeriesInfo(
            length=0,
            resolution=DEFAULT_SNAPSHOT_RESOLUTION,
            initial_timestamp=None,
            resolution_minutes=DEFAULT_SNAPSHOT_MINUTES,
        )

    ts_length = int(ts_p.select(pl.col(PyPSATimeSeriesCol.SNAPSHOT).n_unique()).collect().item())

    first_two = (
        ts_p.select(pl.col(PyPSATimeSeriesCol.SNAPSHOT))
        .unique()
        .sort(PyPSATimeSeriesCol.SNAPSHOT)
        .limit(2)
        .collect()[PyPSATimeSeriesCol.SNAPSHOT]
    )
    if len(first_two) >= 2:
        delta_s = int(first_two.diff().drop_nulls().dt.total_seconds()[0])
        resolution = _RESOLUTION_MAP.get(delta_s, f"PT{delta_s}S")
        resolution_minutes = delta_s / 60.0
    else:
        resolution = DEFAULT_SNAPSHOT_RESOLUTION
        resolution_minutes = DEFAULT_SNAPSHOT_MINUTES

    initial_timestamp = ts_p.select(pl.col(PyPSATimeSeriesCol.SNAPSHOT).min()).collect().item()

    return TimeSeriesInfo(
        length=ts_length,
        resolution=resolution,
        initial_timestamp=initial_timestamp,
        resolution_minutes=resolution_minutes,
    )
