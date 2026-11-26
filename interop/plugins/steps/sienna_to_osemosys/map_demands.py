"""Sienna load -> the OSeMOSYS demand parameter tables.

A Sienna load states the megawatts of each hour, and OSeMOSYS states the energy of a whole
year and the share of that year that falls in each timeslice. A demand for a fuel that is not
electricity has no Sienna component, so it comes from a `load` record of the sidecar.
"""

from __future__ import annotations

from collections.abc import Sequence

import polars as pl

from interop.core.extensions import ExtensionReader, LoadExtension
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.sienna_osemosys_translations import (
    build_demand_sources,
    set_demand_tables,
)


def map_demands(
    state: State,
    recorder: ScopedRecorder,
    extensions: ExtensionReader,
    hours: pl.DataFrame,
    years: Sequence[int],
) -> None:
    """Write the demand of each fuel, from the loads of the system and the hours of its series."""
    sources = build_demand_sources(state, extensions.read(LoadExtension), recorder)
    set_demand_tables(state, sources, hours, years, recorder)
