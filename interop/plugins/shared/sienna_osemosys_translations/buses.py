"""Sienna bus -> the OSeMOSYS region and fuel that the bus stands for.

A bus is named `<region>/<fuel>`, because each fuel balances in its region. A bus whose name
states no fuel is one region that balances electricity, so two buses never merge into one
balance. The `bus` record of a fuel that is not electricity states the region as its location,
which is exact where a fuel name holds the separator too.
"""

from __future__ import annotations

from typing import NamedTuple

import polars as pl

from interop.core.extensions import BusExtension, ExtensionLookup
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.osemosys_canonical.constants import ELECTRICITY_CARRIER, FUEL, REGION
from interop.plugins.shared.sienna_constants import SiennaACBusCol, SiennaComponent, SiennaTable
from interop.plugins.shared.sienna_osemosys_translations.constants import NAME_SEPARATOR
from interop.plugins.shared.sienna_osemosys_translations.events import (
    build_derived,
    build_osemosys_member,
    build_sienna_source,
)

BUS_MEMBERS_TABLE = "bus_members"
# The one record field that the region of a bus of a fuel that is not electricity comes from.
# The `carrier` of the record is the carrier annotation of the fuel and not the name of the
# fuel, so the fuel still comes from the name of the bus.
BUS_MAPPED_FIELDS = ("location",)

_NAMED_DERIVATION = "the part of the name of the bus before and after the last {separator}"
_LOCATED_DERIVATION = "the location of the record, and the rest of the name of the bus"
_WHOLE_DERIVATION = (
    "the name of the bus states no fuel, so the bus is one region that balances {fuel}"
)

# The integer id that a Sienna component names its bus under.
BUS_ID = "bus_id"

BUS_IDS_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    BUS_ID: pl.Int64,
    SiennaACBusCol.NAME: pl.Utf8,
}

BUS_MEMBERS_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    SiennaACBusCol.NAME: pl.Utf8,
    REGION: pl.Utf8,
    FUEL: pl.Utf8,
}


class BusMembers(NamedTuple):
    """One bus, and the OSeMOSYS region and fuel that its name states."""

    bus: str
    region: str
    fuel: str
    derivation: str


def list_bus_members(
    state: State, records: ExtensionLookup[BusExtension], recorder: ScopedRecorder
) -> list[BusMembers]:
    """One entry for each Sienna bus and for each bus that only a `bus` record holds."""
    buses = _list_bus_names(state)
    members = [_build_members(name, None) for name in buses]
    members += [
        _build_members(record.name, records.get_fields(record.name, BUS_MAPPED_FIELDS).location)
        for record in records.list_records()
        if record.name not in buses
    ]
    _record_members(members, recorder)
    return members


def set_bus_members_table(state: State, members: list[BusMembers]) -> None:
    """The region and the fuel of each bus, which every later component group reads."""
    rows = [
        {SiennaACBusCol.NAME: member.bus, REGION: member.region, FUEL: member.fuel}
        for member in members
    ]
    state.destination_tables[BUS_MEMBERS_TABLE] = pl.DataFrame(rows, schema=BUS_MEMBERS_SCHEMA)


def _list_bus_names(state: State) -> list[str]:
    table = state.source_topology.get(SiennaTable.BUSES)
    if table is None:
        return []
    names = table.select(SiennaACBusCol.NAME).collect()
    return names[SiennaACBusCol.NAME].to_list()


def _build_members(name: str, location: str | None) -> BusMembers:
    if location and name.startswith(f"{location}{NAME_SEPARATOR}"):
        fuel = name[len(location) + len(NAME_SEPARATOR) :]
        return BusMembers(name, location, fuel, _LOCATED_DERIVATION)
    region, separator, fuel = name.rpartition(NAME_SEPARATOR)
    if separator:
        return BusMembers(name, region, fuel, _NAMED_DERIVATION.format(separator=NAME_SEPARATOR))
    return BusMembers(
        name, name, ELECTRICITY_CARRIER, _WHOLE_DERIVATION.format(fuel=ELECTRICITY_CARRIER)
    )


def _record_members(members: list[BusMembers], recorder: ScopedRecorder) -> None:
    for member in members:
        source = build_sienna_source(SiennaComponent.AC_BUS, member.bus, SiennaACBusCol.NAME)
        destinations = [
            build_osemosys_member(REGION, member.region),
            build_osemosys_member(FUEL, member.fuel),
        ]
        recorder.append(build_derived([source], destinations, member.derivation))


def find_bus_members(state: State) -> pl.DataFrame | None:
    """The region and the fuel of each bus, as the bus group wrote them; None where it wrote
    none."""
    return state.destination_tables.get(BUS_MEMBERS_TABLE)


def build_bus_ids(state: State) -> pl.DataFrame:
    """The name of each Sienna bus, by the integer id that a component names it under."""
    table = state.source_topology.get(SiennaTable.BUSES)
    if table is None:
        return pl.DataFrame(schema=BUS_IDS_SCHEMA)
    ids = table.select(SiennaACBusCol.ID, SiennaACBusCol.NAME).collect()
    return ids.rename({SiennaACBusCol.ID: BUS_ID}).cast(pl.Schema(BUS_IDS_SCHEMA))
