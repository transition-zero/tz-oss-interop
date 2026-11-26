"""The hours that every series of a Sienna system covers.

Each TimeSeriesAssociation of one system covers the same snapshots, so one staged series
states the window of the whole system. The reader aggregates the snapshot column rather than
collecting it, because a real system holds billions of rows.
"""

from __future__ import annotations

from datetime import datetime
from typing import NamedTuple

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.constants import StagedTimeSeriesCol

_FIRST_COL = "first"
_HOURS_COL = "hours"


class SeriesWindow(NamedTuple):
    """The first snapshot of the series, and how many snapshots it holds."""

    first_timestamp: datetime
    hours: int


def find_series_window(state: State) -> SeriesWindow | None:
    """The window of the staged series; None for a system that states no series."""
    staged = next(iter(state.source_time_series.values()), None)
    if staged is None:
        return None
    summary = staged.select(
        pl.col(StagedTimeSeriesCol.SNAPSHOT).min().alias(_FIRST_COL),
        pl.col(StagedTimeSeriesCol.SNAPSHOT).n_unique().alias(_HOURS_COL),
    ).collect()
    return _find_window(summary)


def _find_window(summary: pl.DataFrame) -> SeriesWindow | None:
    first = summary.item(0, _FIRST_COL)
    hours = summary.item(0, _HOURS_COL)
    if first is None or not hours:
        return None
    return SeriesWindow(first, int(hours))
