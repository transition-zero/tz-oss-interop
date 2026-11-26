"""The hour of the series that each OSeMOSYS timeslice covers.

This is the forward leg's reshape read the other way. There the hours of each representative
period follow each other from the first timestamp of that period, so a timeslice of a period
states the one hour that it covers. An invented timeslice states none, so it takes the hour at
its own position in the series.

A row also states how many hours of the year its timeslice covers, which is the weight of its
period. The demand of one timeslice is the megawatts of its hour times that number.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.constants import StagedTimeSeriesCol
from interop.plugins.shared.osemosys_canonical.constants import TIMESLICE
from interop.plugins.shared.sienna_osemosys_translations.calendar import Calendar, Timeslice
from interop.plugins.shared.sienna_osemosys_translations.series import list_series_snapshots

# How many hours of the year the timeslice of the row covers.
TIMESLICE_HOURS = "timeslice_hours"

CALENDAR_HOURS_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    StagedTimeSeriesCol.SNAPSHOT: pl.Datetime("us"),
    TIMESLICE: pl.Utf8,
    TIMESLICE_HOURS: pl.Float64,
}


def build_calendar_hours(state: State, calendar: Calendar) -> pl.DataFrame:
    """One row for each hour of the model, with the timeslice that covers it."""
    stated = [timeslice for timeslice in calendar.timeslices if timeslice.timestamp is not None]
    if stated:
        return _build_table(stated, [timeslice.timestamp for timeslice in stated])
    held = list(calendar.timeslices)
    return _build_table(held, list_series_snapshots(state)[: len(held)])


def _build_table(
    timeslices: Sequence[Timeslice], snapshots: Sequence[datetime | None]
) -> pl.DataFrame:
    rows = [
        {
            StagedTimeSeriesCol.SNAPSHOT: snapshot,
            TIMESLICE: timeslice.name,
            TIMESLICE_HOURS: timeslice.weight,
        }
        for timeslice, snapshot in zip(timeslices, snapshots, strict=False)
    ]
    return pl.DataFrame(rows, schema=CALENDAR_HOURS_SCHEMA)
