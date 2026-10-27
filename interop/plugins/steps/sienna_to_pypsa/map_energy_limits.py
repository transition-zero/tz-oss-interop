"""The annual energy bounds of a generator, for the year of the snapshots.

The sidecar states `e_sum_min` and `e_sum_max` in MWh for each year in scope. PyPSA states one
bound over all the snapshots, weighted by the `generators` snapshot weighting. The value of the
year maps only where the snapshots count for that whole year; a bound for less than a year
would ask a part of the year for the energy of all of it. The record keeps every year either
way, because the generator step relays both fields.
"""

from __future__ import annotations

import logging
from typing import ClassVar, NamedTuple

import polars as pl
from pydantic import BaseModel

from interop.core.extensions import ByYear, ExtensionKind, ExtensionReader
from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import EXTENSIONS_PREFIX
from interop.plugins.shared.pypsa_constants import PyPSADestinationTable, PyPSAGeneratorCol
from interop.plugins.shared.sienna_constants import SiennaTable
from interop.plugins.shared.sienna_pypsa_translations.mapped_fields import ANNUAL_BOUNDS
from interop.plugins.shared.sienna_pypsa_translations.mapping import find_source_types
from interop.plugins.shared.sienna_pypsa_translations.reporters import GeneratorReporter
from interop.plugins.shared.warning_text import name_a_few
from interop.plugins.steps.sienna_to_pypsa.map_snapshot_weightings import (
    SnapshotSpan,
    find_snapshot_span,
)

log = logging.getLogger(__name__)

_MAPPED_DERIVATION = (
    "the value of {year}, the year of the snapshots, which count for {hours:.1f} h, the whole "
    "year; PyPSA weighs the bound by the generators snapshot weighting"
)
_PART_YEAR_NOTE = (
    "the snapshots count for {hours:.1f} h of {year}, not the whole year, so the annual bound "
    "does not apply to them; extensions.json keeps it"
)
_NO_YEAR_NOTE = "the record states no bound for {year}, the year of the snapshots"
_NO_SNAPSHOTS_NOTE = (
    "the network has no snapshots, so the bound binds nothing; extensions.json keeps it"
)
_NO_SNAPSHOTS_WARNING = (
    "%d annual energy bound(s) stay in extensions.json and bind nothing, because the network "
    "has no snapshots: %s"
)
_PART_YEAR_WARNING = (
    "%d annual energy bound(s) stay in extensions.json and bind nothing, because the "
    "snapshots count for %.1f h, not one whole year: %s"
)
_NO_YEAR_WARNING = "%d annual energy bound(s) state no value for %s, so they bind nothing: %s"
_MORE_THAN_ONE_YEAR = "more than one year"


class EnergyBound(NamedTuple):
    """One annual bound that a generator's record states, by year."""

    name: str
    field_name: str
    column: str
    by_year: ByYear


class SiennaToPypsaMapEnergyLimits(TranslationStep):
    """Bounds each generator's energy over the year that the weighted snapshots span."""

    name: ClassVar[str] = "sienna_to_pypsa_map_energy_limits"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def run(self, state: State, params: BaseModel | None) -> State:
        reader = state.extension_reader(self._recorder)
        EnergyLimitMapper(self._recorder).map_energy_limits(
            state, reader, find_snapshot_span(state)
        )
        return state


class EnergyLimitMapper:
    """Writes `e_sum_min` and `e_sum_max` of each generator for the year of the snapshots."""

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def map_energy_limits(self, state: State, reader: ExtensionReader, span: SnapshotSpan) -> None:
        generators = state.destination_tables.get(PyPSADestinationTable.GENERATORS)
        if generators is None:
            return
        bounds = _list_bounds(reader, generators[PyPSAGeneratorCol.NAME].to_list())
        if not bounds:
            return
        if not span.has_snapshots:
            self._report_no_snapshots(state, bounds)
        elif span.is_whole_year:
            self._map_year(state, bounds, span)
        else:
            self._report_part_year(state, bounds, span)

    def _map_year(self, state: State, bounds: list[EnergyBound], span: SnapshotSpan) -> None:
        """Write the bound of the year of the snapshots, and report each bound that has none."""
        year = span.require_year()
        held = [bound for bound in bounds if year in bound.by_year]
        self._report_no_year(state, [bound for bound in bounds if year not in bound.by_year], year)
        self._record_mapped(state, held, span)
        generators = state.destination_tables[PyPSADestinationTable.GENERATORS]
        state.destination_tables[PyPSADestinationTable.GENERATORS] = _set_bounds(
            generators, held, year
        )

    def _record_mapped(self, state: State, held: list[EnergyBound], span: SnapshotSpan) -> None:
        reporter = GeneratorReporter(self._recorder)
        types = find_source_types(state, SiennaTable.GENERATORS) or {}
        derivation = _MAPPED_DERIVATION.format(year=span.year, hours=span.represented_hours)
        for bound in held:
            value = bound.by_year[span.require_year()]
            reporter.record_energy_bound(
                types.get(bound.name, ExtensionKind.GENERATOR),
                bound.name,
                f"{EXTENSIONS_PREFIX}{bound.field_name}",
                bound.column,
                value,
                derivation,
            )

    def _report_part_year(
        self, state: State, bounds: list[EnergyBound], span: SnapshotSpan
    ) -> None:
        year = _MORE_THAN_ONE_YEAR if span.year is None else str(span.year)
        note = _PART_YEAR_NOTE.format(hours=span.represented_hours, year=year)
        self._record_unmapped(state, bounds, note)
        labels = [f"{bound.name}.{bound.field_name}" for bound in bounds]
        log.warning(_PART_YEAR_WARNING, len(bounds), span.represented_hours, name_a_few(labels))

    def _report_no_snapshots(self, state: State, bounds: list[EnergyBound]) -> None:
        self._record_unmapped(state, bounds, _NO_SNAPSHOTS_NOTE)
        labels = [f"{bound.name}.{bound.field_name}" for bound in bounds]
        log.warning(_NO_SNAPSHOTS_WARNING, len(bounds), name_a_few(labels))

    def _report_no_year(self, state: State, bounds: list[EnergyBound], year: int) -> None:
        if not bounds:
            return
        self._record_unmapped(state, bounds, _NO_YEAR_NOTE.format(year=year))
        labels = [f"{bound.name}.{bound.field_name}" for bound in bounds]
        log.warning(_NO_YEAR_WARNING, len(bounds), year, name_a_few(labels))

    def _record_unmapped(self, state: State, bounds: list[EnergyBound], note: str) -> None:
        reporter = GeneratorReporter(self._recorder)
        types = find_source_types(state, SiennaTable.GENERATORS) or {}
        for bound in bounds:
            reporter.record_bound_unapplied(
                types.get(bound.name, ExtensionKind.GENERATOR), bound.name, bound.field_name, note
            )


def _list_bounds(reader: ExtensionReader, names: list[str]) -> list[EnergyBound]:
    """Each annual bound that a written generator's record states."""
    lookup = reader.read(ExtensionKind.GENERATOR)
    bounds: list[EnergyBound] = []
    for name in names:
        record = lookup.get_fields(name, ())
        for mapped in ANNUAL_BOUNDS:
            by_year = getattr(record, mapped.field_name)
            if by_year:
                bounds.append(EnergyBound(name, mapped.field_name, mapped.column, by_year))
    return bounds


def _set_bounds(generators: pl.DataFrame, held: list[EnergyBound], year: int) -> pl.DataFrame:
    """The generators table, with the bound of the year in each column that a bound names."""
    columns = []
    for mapped in ANNUAL_BOUNDS:
        values = {
            bound.name: bound.by_year[year] for bound in held if bound.column == mapped.column
        }
        columns.append(
            pl.col(PyPSAGeneratorCol.NAME)
            .replace_strict(values, default=None, return_dtype=pl.Float64)
            .alias(mapped.column)
        )
    return generators.with_columns(columns)
