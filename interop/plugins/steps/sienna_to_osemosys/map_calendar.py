"""The OSeMOSYS calendar and the years of the model, from the sidecar and the series.

One timeslice covers one hour of one representative period. With no representative period the
leg invents one timeslice for each hour of the series, which is what lets a system from PLEXOS
or from PyPSA reach OSeMOSYS.
"""

from __future__ import annotations

from typing import NamedTuple

from interop.core.extensions import ExtensionReader, RepresentativePeriodExtension
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.sienna_osemosys_translations import (
    Calendar,
    build_calendar,
    build_model_years,
    find_series_window,
    set_calendar_tables,
)


class MappedCalendar(NamedTuple):
    """The calendar of the written model, and the years that the model holds."""

    calendar: Calendar
    years: list[int]


def map_calendar(
    state: State, recorder: ScopedRecorder, extensions: ExtensionReader
) -> MappedCalendar:
    """Write the calendar tables, and give back the calendar and the years of the model."""
    records = extensions.read(RepresentativePeriodExtension).read_all()
    window = find_series_window(state)
    years = build_model_years(extensions, records, window, recorder)
    calendar = build_calendar(records, window, recorder)
    set_calendar_tables(state, calendar, years, recorder)
    return MappedCalendar(calendar, years)
