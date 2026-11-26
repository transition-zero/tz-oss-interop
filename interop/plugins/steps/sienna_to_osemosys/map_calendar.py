"""The OSeMOSYS calendar and the years of the model, from the sidecar and the series.

One timeslice covers one hour of one representative period. With no representative period the
leg invents one timeslice for each hour of the series, which is what lets a system from PLEXOS
or from PyPSA reach OSeMOSYS.
"""

from __future__ import annotations

from interop.core.extensions import ExtensionReader, RepresentativePeriodExtension
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.sienna_osemosys_translations import (
    build_calendar,
    build_model_years,
    find_series_window,
    set_calendar_tables,
)


def map_calendar(state: State, recorder: ScopedRecorder, extensions: ExtensionReader) -> list[int]:
    """Write the calendar tables, and give back the years that the written model holds."""
    records = extensions.read(RepresentativePeriodExtension).read_all()
    window = find_series_window(state)
    years = build_model_years(extensions, records, window, recorder)
    set_calendar_tables(state, build_calendar(records, window, recorder), years, recorder)
    return years
