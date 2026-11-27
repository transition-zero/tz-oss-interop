"""A `generator` record of a fuel that is not electricity -> one OSeMOSYS technology.

Sienna holds electricity only, so a technology that supplies another fuel has no Sienna
component. It travels as a `generator` record of the sidecar, which states the bus of the fuel
that it puts out, the megawatts of that fuel that already run, what one megawatt hour of it
costs and the share of a year that it can run.

A record that states no `bus`, and a record whose name is a Sienna generator, each belong to a
component that the system holds, so neither gives a technology of its own.
"""

from __future__ import annotations

from collections.abc import Sequence

import polars as pl

from interop.core.extensions import ExtensionKind, ExtensionLookup, GeneratorExtension
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import UNIT_MW, Framework
from interop.plugins.shared.osemosys_canonical.constants import FUEL, REGION, TECHNOLOGY
from interop.plugins.shared.sienna_constants import SiennaACBusCol
from interop.plugins.shared.sienna_osemosys_translations.buses import (
    BusMembers,
    build_bus_members,
)
from interop.plugins.shared.sienna_osemosys_translations.constants import (
    SIENNA_TO_OSEMOSYS_PIPELINE,
)
from interop.plugins.shared.sienna_osemosys_translations.generator_columns import (
    AVAILABILITY,
    BASE_POWER_ATTRIBUTE,
    BASE_POWER_MW,
    CAPACITY_ATTRIBUTE,
    CAPACITY_MW,
    COST_ATTRIBUTE,
    GENERATOR_COUNTED_NOUN,
    GENERATORS_SCHEMA,
    HELD_MODE,
    NO_CAPACITY_NOTE,
    NO_CAPACITY_REASON,
    RECORD_CAPACITY_ATTRIBUTE,
    RECORD_COST_ATTRIBUTE,
    SOURCE_COMPONENT,
    VARIABLE_COST_MWH,
)
from interop.plugins.shared.sienna_osemosys_translations.generator_modes import (
    MODE_MAPPED_FIELDS,
    build_held_mode,
    list_mode_records,
)
from interop.plugins.shared.translation_runner import SkipReport, SkipRule, drop_skipped

# The record fields that the key and the ratings of such a technology come from.
RECORD_MAPPED_FIELDS = ("bus", "p_nom", "marginal_cost", "p_max_pu", *MODE_MAPPED_FIELDS)

# How the bus group read a bus that it placed, which the bus group has already recorded.
_PLACED_DERIVATION = "the region and the fuel of the bus, as the bus group read them"


def build_record_generators(
    records: ExtensionLookup[GeneratorExtension],
    held: Sequence[str],
    members: pl.DataFrame,
    recorder: ScopedRecorder,
) -> pl.DataFrame:
    """Each technology that only a `generator` record holds, keyed by the fuel of its bus."""
    placed = _build_members_by_bus(members)
    staged = set(held)
    rows = [
        _build_row(records.get_fields(record.name, RECORD_MAPPED_FIELDS), placed)
        for record in records.list_records()
        if record.bus is not None and record.name not in staged
    ]
    table = pl.DataFrame(rows, schema=GENERATORS_SCHEMA)
    return drop_skipped(table, [_build_capacity_rule()], recorder)


def _build_members_by_bus(members: pl.DataFrame) -> dict[str, BusMembers]:
    """The region and the fuel of each bus that the bus group placed."""
    return {
        row[SiennaACBusCol.NAME]: BusMembers(
            row[SiennaACBusCol.NAME], row[REGION], row[FUEL], _PLACED_DERIVATION
        )
        for row in members.iter_rows(named=True)
    }


def _build_row(record: GeneratorExtension, placed: dict[str, BusMembers]) -> dict[str, object]:
    bus = _build_bus_members(str(record.bus), placed)
    return {
        TECHNOLOGY: record.name,
        REGION: bus.region,
        FUEL: bus.fuel,
        HELD_MODE: build_held_mode(list_mode_records(record)),
        BASE_POWER_MW: record.p_nom,
        BASE_POWER_ATTRIBUTE: RECORD_CAPACITY_ATTRIBUTE,
        CAPACITY_MW: record.p_nom,
        CAPACITY_ATTRIBUTE: RECORD_CAPACITY_ATTRIBUTE,
        VARIABLE_COST_MWH: record.marginal_cost,
        COST_ATTRIBUTE: RECORD_COST_ATTRIBUTE,
        AVAILABILITY: record.p_max_pu,
        SOURCE_COMPONENT: ExtensionKind.GENERATOR.value,
    }


def _build_bus_members(bus: str, placed: dict[str, BusMembers]) -> BusMembers:
    """The bus group's own reading of the bus, or the same rule over the name alone."""
    return placed.get(bus) or build_bus_members(bus)


def _build_capacity_rule() -> SkipRule:
    """A record states its capacity as `p_nom`, so the report names that field and not the
    Sienna one."""
    report = SkipReport(
        pipeline=SIENNA_TO_OSEMOSYS_PIPELINE,
        framework=Framework.SIENNA,
        component=ExtensionKind.GENERATOR.value,
        name_col=TECHNOLOGY,
        reason=NO_CAPACITY_REASON,
        counted_noun=GENERATOR_COUNTED_NOUN,
        note=NO_CAPACITY_NOTE,
        attribute_col=BASE_POWER_MW,
        attribute_name=RECORD_CAPACITY_ATTRIBUTE,
        attribute_unit=UNIT_MW,
    )
    return SkipRule(pl.col(BASE_POWER_MW) > 0, report)
