"""Sienna generator -> the OSeMOSYS technology parameter tables.

A generator runs one operating mode and holds the flows of that mode itself, so the leg writes
the electricity output of the held mode as 1 and reads every other flow from the
`extensions.json` sidecar.
"""

from __future__ import annotations

from collections.abc import Sequence

import polars as pl

from interop.core.extensions import ExtensionReader, GeneratorExtension
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.sienna_osemosys_translations import (
    build_generator_sources,
    set_generator_tables,
)


def map_generators(
    state: State,
    recorder: ScopedRecorder,
    extensions: ExtensionReader,
    hours: pl.DataFrame,
    years: Sequence[int],
) -> None:
    """Write the fleet, the flows and the hourly share of each generator of the system."""
    sources = build_generator_sources(state, extensions.read(GeneratorExtension), recorder)
    set_generator_tables(state, sources, hours, years, recorder)
