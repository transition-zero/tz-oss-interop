"""The annual energy bounds of a generator, for the year of the snapshots.

The sidecar states `e_sum_min` and `e_sum_max` in MWh for each year in scope. PyPSA states one
bound over all the snapshots, weighted by the `generators` snapshot weighting. The value of the
year maps only where the snapshots count for that whole year; a bound for less than a year
would ask a part of the year for the energy of all of it. The record keeps every year either
way, because the generator step relays both fields.
"""

from __future__ import annotations

import logging
from typing import NamedTuple

import polars as pl

from interop.core.extensions import ExtensionKind, ExtensionReader
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.pypsa_constants import PyPSADestinationTable, PyPSAGeneratorCol
from interop.plugins.shared.sienna_constants import SiennaGeneratorCol, SiennaTable
from interop.plugins.shared.sienna_pypsa_translations.reporters import GeneratorReporter
from interop.plugins.shared.warning_text import name_a_few
from interop.plugins.steps.sienna_to_pypsa.map_snapshot_weightings import SnapshotSpan

log = logging.getLogger(__name__)

_EXTENSIONS = "extensions"
# Each annual bound of a record, and the PyPSA column that holds it.
_BOUNDS: tuple[tuple[str, str], ...] = (
    ("e_sum_min", PyPSAGeneratorCol.E_SUM_MIN),
    ("e_sum_max", PyPSAGeneratorCol.E_SUM_MAX),
)

_MAPPED_DERIVATION = (
    "the value of {year}, the year of the snapshots, which count for {hours:.1f} h, the whole "
    "year; PyPSA weighs the bound by the generators snapshot weighting"
)
_PART_YEAR_NOTE = (
    "the snapshots count for {hours:.1f} h of {year}, not the whole year, so the annual bound "
    "does not apply to them; extensions.json keeps it"
)
_NO_YEAR_NOTE = "the record states no bound for {year}, the year of the snapshots"
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
    by_year: dict[str, float]


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
        if not span.is_whole_year:
            self._report_part_year(state, bounds, span)
            return
        year = str(span.year)
        held = [bound for bound in bounds if year in bound.by_year]
        self._report_no_year(state, [bound for bound in bounds if year not in bound.by_year], year)
        self._record_mapped(state, held, span)
        state.destination_tables[PyPSADestinationTable.GENERATORS] = _set_bounds(
            generators, held, year
        )

    def _record_mapped(self, state: State, held: list[EnergyBound], span: SnapshotSpan) -> None:
        reporter = GeneratorReporter(self._recorder)
        types = _find_sienna_types(state)
        derivation = _MAPPED_DERIVATION.format(year=span.year, hours=span.represented_hours)
        for bound in held:
            value = bound.by_year[str(span.year)]
            reporter.record_energy_bound(
                types.get(bound.name, ExtensionKind.GENERATOR),
                bound.name,
                f"{_EXTENSIONS}.{bound.field_name}",
                bound.column,
                value,
                derivation,
            )

    def _report_part_year(
        self, state: State, bounds: list[EnergyBound], span: SnapshotSpan
    ) -> None:
        year = _MORE_THAN_ONE_YEAR if span.year is None else str(span.year)
        note = _PART_YEAR_NOTE.format(hours=span.represented_hours, year=year)
        self._report_unmapped(state, bounds, note)
        labels = [f"{bound.name}.{bound.field_name}" for bound in bounds]
        log.warning(_PART_YEAR_WARNING, len(bounds), span.represented_hours, name_a_few(labels))

    def _report_no_year(self, state: State, bounds: list[EnergyBound], year: str) -> None:
        if not bounds:
            return
        self._report_unmapped(state, bounds, _NO_YEAR_NOTE.format(year=year))
        labels = [f"{bound.name}.{bound.field_name}" for bound in bounds]
        log.warning(_NO_YEAR_WARNING, len(bounds), year, name_a_few(labels))

    def _report_unmapped(self, state: State, bounds: list[EnergyBound], note: str) -> None:
        reporter = GeneratorReporter(self._recorder)
        types = _find_sienna_types(state)
        for bound in bounds:
            reporter.record_energy_bound_unmapped(
                types.get(bound.name, ExtensionKind.GENERATOR),
                bound.name,
                f"{_EXTENSIONS}.{bound.field_name}",
                note,
            )


def _list_bounds(reader: ExtensionReader, names: list[str]) -> list[EnergyBound]:
    """Each annual bound that a written generator's record states."""
    lookup = reader.read(ExtensionKind.GENERATOR)
    bounds: list[EnergyBound] = []
    for name in names:
        record = lookup.get_fields(name, ())
        for field_name, column in _BOUNDS:
            by_year = getattr(record, field_name)
            if by_year:
                bounds.append(EnergyBound(name, field_name, column, by_year))
    return bounds


def _set_bounds(generators: pl.DataFrame, held: list[EnergyBound], year: str) -> pl.DataFrame:
    """The generators table, with the bound of the year in each column that a bound names."""
    columns = []
    for _, column in _BOUNDS:
        values = {bound.name: bound.by_year[year] for bound in held if bound.column == column}
        columns.append(
            pl.col(PyPSAGeneratorCol.NAME)
            .replace_strict(values, default=None, return_dtype=pl.Float64)
            .alias(column)
        )
    return generators.with_columns(columns)


def _find_sienna_types(state: State) -> dict[str, str]:
    """The Sienna type of each generator, which the report names as the source."""
    source = state.source_topology.get(SiennaTable.GENERATORS)
    if source is None:
        return {}
    rows = source.select(SiennaGeneratorCol.NAME, SiennaGeneratorCol.SIENNA_TYPE).collect()
    return dict(rows.iter_rows())
