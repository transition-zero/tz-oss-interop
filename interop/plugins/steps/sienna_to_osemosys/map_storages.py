"""Sienna storage -> the OSeMOSYS storage and technology parameter tables.

A Sienna storage holds its energy, its power and its two efficiencies on one component.
OSeMOSYS holds the energy on a member of the `STORAGE` set and the power on one technology that
charges that member and one that discharges it, so the group writes all three.
"""

from __future__ import annotations

from collections.abc import Sequence

from interop.core.extensions import ExtensionReader, StorageExtension
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.sienna_osemosys_translations import (
    build_storage_sources,
    set_storage_tables,
)


def map_storages(
    state: State,
    recorder: ScopedRecorder,
    extensions: ExtensionReader,
    years: Sequence[int],
) -> None:
    """Write the energy of each storage of the system and the technologies that move it."""
    sources = build_storage_sources(state, extensions.read(StorageExtension), recorder)
    set_storage_tables(state, sources, years, recorder)
