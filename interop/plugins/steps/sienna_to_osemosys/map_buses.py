"""Sienna bus -> the OSeMOSYS region and fuel set tables.

A bus is named `<region>/<fuel>`, so the buses of a system state every region and every fuel
that the written model holds. The step also keeps the region and the fuel of each bus on the
destination side, because every later component group reads the bus of its component.
"""

from __future__ import annotations

from collections.abc import Iterable

from interop.core.extensions import BusExtension, ExtensionReader
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.osemosys_canonical.constants import FUEL, REGION
from interop.plugins.shared.sienna_osemosys_translations import (
    list_bus_members,
    set_bus_members_table,
    set_set_table,
)


def map_buses(state: State, recorder: ScopedRecorder, extensions: ExtensionReader) -> None:
    members = list_bus_members(state, extensions.read(BusExtension), recorder)
    if not members:
        return
    set_bus_members_table(state, members)
    set_set_table(state, REGION, _list_distinct(member.region for member in members))
    set_set_table(state, FUEL, _list_distinct(member.fuel for member in members))


def _list_distinct(values: Iterable[str]) -> list[str]:
    """The distinct values, in the order the buses state them."""
    return list(dict.fromkeys(values))
