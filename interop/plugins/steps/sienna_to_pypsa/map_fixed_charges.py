"""The yearly fixed charge of a component, as the `fom_cost` of its PyPSA component.

The sidecar states `fom_charge_per_mw_year` in $/MW for each year. PyPSA adds `fom_cost` once
to the build cost of the whole horizon, after it multiplies the annuity by the years that the
snapshots count for. The two agree only where the snapshots count for one whole year, so the
charge maps only there. The record keeps the charge either way, because the steps that write
the components relay it.
"""

from __future__ import annotations

import logging
from typing import ClassVar, NamedTuple

import polars as pl
from pydantic import BaseModel

from interop.core.extensions import (
    ConversionExtension,
    ExpansionExtension,
    ExtensionReader,
    GeneratorExtension,
    StorageExtension,
    get_record_kind,
)
from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.pypsa_constants import (
    PyPSADestinationTable,
    PyPSAGeneratorCol,
    PyPSALinkCol,
    PyPSAStorageUnitCol,
)
from interop.plugins.shared.sienna_constants import SiennaTable
from interop.plugins.shared.sienna_pypsa_translations.mapping import find_source_types
from interop.plugins.shared.sienna_pypsa_translations.reporters import (
    ConversionReporter,
    GeneratorReporter,
    StorageUnitReporter,
)
from interop.plugins.shared.sienna_pypsa_translations.reporters._base import (
    SiennaToPypsaReporter,
)
from interop.plugins.shared.warning_text import name_a_few
from interop.plugins.steps.sienna_to_pypsa.map_snapshot_weightings import (
    SnapshotSpan,
    build_snapshot_span,
)

log = logging.getLogger(__name__)

# Generator, StorageUnit and Link each name the fixed charge fom_cost.
_FOM_COST = PyPSAGeneratorCol.FOM_COST

_MAPPED_DERIVATION = (
    "the yearly charge, because the snapshots count for {hours:.1f} h, one whole year, so PyPSA "
    "adds fom_cost to one year of the annuity"
)
_PART_YEAR_NOTE = (
    "the snapshots count for {hours:.1f} h, not one whole year, and PyPSA adds fom_cost once "
    "over them, so the network charges no fixed cost; extensions.json keeps it"
)
_NO_SNAPSHOTS_NOTE = (
    "the network has no snapshots, so it charges no fixed cost; extensions.json keeps it"
)
_PART_YEAR_WARNING = (
    "%d yearly fixed charge(s) stay in extensions.json and PyPSA charges none of them, because "
    "the snapshots count for %.1f h, not one whole year: %s"
)
_NO_SNAPSHOTS_WARNING = (
    "%d yearly fixed charge(s) stay in extensions.json and PyPSA charges none of them, because "
    "the network has no snapshots: %s"
)


class ChargeOwner(NamedTuple):
    """A record model, the PyPSA table that holds its components, and how to report them."""

    model: type[ExpansionExtension]
    table: str
    name_col: str
    source_table: str | None
    reporter: type[SiennaToPypsaReporter]


_OWNERS = (
    ChargeOwner(
        GeneratorExtension,
        PyPSADestinationTable.GENERATORS,
        PyPSAGeneratorCol.NAME,
        SiennaTable.GENERATORS,
        GeneratorReporter,
    ),
    ChargeOwner(
        StorageExtension,
        PyPSADestinationTable.STORAGE_UNITS,
        PyPSAStorageUnitCol.NAME,
        SiennaTable.STORAGE,
        StorageUnitReporter,
    ),
    ChargeOwner(
        ConversionExtension,
        PyPSADestinationTable.LINKS,
        PyPSALinkCol.NAME,
        None,
        ConversionReporter,
    ),
)


class FixedCharge(NamedTuple):
    """The yearly fixed charge that the record of one written component states."""

    owner: ChargeOwner
    name: str
    sienna_type: str
    value: float


class SiennaToPypsaMapFixedCharges(TranslationStep):
    """Charges each component its yearly fixed cost where the snapshots count for one year."""

    name: ClassVar[str] = "sienna_to_pypsa_map_fixed_charges"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def run(self, state: State, params: BaseModel | None) -> State:
        reader = state.extension_reader(self._recorder)
        FixedChargeMapper(self._recorder).map_fixed_charges(
            state, reader, build_snapshot_span(state)
        )
        return state


class FixedChargeMapper:
    """Writes the yearly fixed charge of each component to `fom_cost`, or reports why not."""

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def map_fixed_charges(self, state: State, reader: ExtensionReader, span: SnapshotSpan) -> None:
        charges = _list_charges(state, reader)
        if not charges:
            return
        if span.is_whole_year:
            self._map_year(state, charges, span)
        elif span.has_snapshots:
            self._report_part_year(charges, span)
        else:
            self._report_no_snapshots(charges)

    def _map_year(self, state: State, charges: list[FixedCharge], span: SnapshotSpan) -> None:
        derivation = _MAPPED_DERIVATION.format(hours=span.represented_hours)
        for charge in charges:
            reporter = charge.owner.reporter(self._recorder)
            reporter.record_fixed_charge(charge.sienna_type, charge.name, charge.value, derivation)
        for owner in _OWNERS:
            values = {charge.name: charge.value for charge in charges if charge.owner is owner}
            if values:
                table = state.destination_tables[owner.table]
                state.destination_tables[owner.table] = _set_charges(table, owner, values)

    def _report_part_year(self, charges: list[FixedCharge], span: SnapshotSpan) -> None:
        self._record_unmapped(charges, _PART_YEAR_NOTE.format(hours=span.represented_hours))
        names = name_a_few([charge.name for charge in charges])
        log.warning(_PART_YEAR_WARNING, len(charges), span.represented_hours, names)

    def _report_no_snapshots(self, charges: list[FixedCharge]) -> None:
        self._record_unmapped(charges, _NO_SNAPSHOTS_NOTE)
        names = name_a_few([charge.name for charge in charges])
        log.warning(_NO_SNAPSHOTS_WARNING, len(charges), names)

    def _record_unmapped(self, charges: list[FixedCharge], note: str) -> None:
        for charge in charges:
            reporter = charge.owner.reporter(self._recorder)
            reporter.record_fixed_charge_unapplied(
                charge.sienna_type, charge.name, charge.value, note
            )


def _list_charges(state: State, reader: ExtensionReader) -> list[FixedCharge]:
    """Each yearly fixed charge that the record of a written component states."""
    charges: list[FixedCharge] = []
    for owner in _OWNERS:
        table = state.destination_tables.get(owner.table)
        if table is not None:
            charges.extend(_list_owner_charges(state, reader, owner, table))
    return charges


def _list_owner_charges(
    state: State, reader: ExtensionReader, owner: ChargeOwner, table: pl.DataFrame
) -> list[FixedCharge]:
    types = find_source_types(state, owner.source_table) if owner.source_table else None
    lookup = reader.read(owner.model)
    charges: list[FixedCharge] = []
    for name in table[owner.name_col].to_list():
        value = lookup.get_fields(name, ()).fom_charge_per_mw_year
        if value is not None:
            sienna_type = (types or {}).get(name, get_record_kind(owner.model))
            charges.append(FixedCharge(owner, name, sienna_type, value))
    return charges


def _set_charges(table: pl.DataFrame, owner: ChargeOwner, values: dict[str, float]) -> pl.DataFrame:
    """The table, with the charge of each named component in `fom_cost`."""
    charged = pl.col(owner.name_col).replace_strict(
        values, default=pl.col(_FOM_COST), return_dtype=pl.Float64
    )
    return table.with_columns(charged.alias(_FOM_COST))
