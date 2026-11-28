"""Sienna reservoir -> the OSeMOSYS storage parameter tables.

A Sienna `HydroReservoir` holds the energy behind a `HydroTurbine`, and OSeMOSYS holds that
energy on a member of the `STORAGE` set. The turbine is already a technology of the generator
group, so this group writes the storage, the link of each turbine that spends it, and one
charging technology for the inflow.
"""

from __future__ import annotations

from collections.abc import Sequence

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.sienna_osemosys_translations import (
    GeneratorSources,
    build_reservoir_sources,
    set_storage_tables,
)


def map_reservoirs(
    state: State,
    recorder: ScopedRecorder,
    generators: GeneratorSources,
    years: Sequence[int],
) -> None:
    """Write the energy of each reservoir of the system and the links that move it."""
    sources = build_reservoir_sources(state, generators, recorder)
    set_storage_tables(state, sources, years, recorder)
