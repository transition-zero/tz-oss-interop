"""The annual rows that every results step writes for a solve over representative periods.

Production, installed capacity and emissions each take one row for each component, or for
each pollutant, in each year of the solve, at 1 January of the year. The rows of every
framework share these definitions, so two solves of one model compare row by row.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import NamedTuple, TypeVar

import polars as pl

from interop.core.extensions import ControllableLineExtension
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import Framework, require_extension_attribute
from interop.plugins.shared.results_constants import (
    RESULTS_SCHEMA,
    RESULTS_TABLE_KEY,
    VARIABLE_UNIT,
    ResultsCol,
    ResultsVariable,
)
from interop.plugins.shared.sienna_results_constants import AnnualCol
from interop.plugins.shared.translation_runner import SkipReport, report_not_mapped
from interop.ports.outbound.reporting import (
    DestinationField,
    EventKind,
    SourceField,
    TranslationEvent,
)

_FIRST_MONTH = 1
_FIRST_DAY = 1
_MARK = "is_conversion"
_MARK_NAME = require_extension_attribute(ControllableLineExtension, _MARK)
_PLACE0 = "place0"
_PLACE1 = "place1"

_UNPRODUCED_NOTE = (
    "the solve states no output for the component, so it has installed_capacity and no production"
)
_CONVERSION_NOTE = (
    "the extensions record marks the line as a conversion between two electricity fuels of one "
    "location, which is neither production nor trade, so it has no production or "
    "installed_capacity row"
)
_CONVERSION_REASON = (
    "convert electricity at one location, so they have no production or installed_capacity row"
)
_UNMARKED_NOTE = (
    "the line joins two buses of one area or one location, and its extensions record states no "
    "is_conversion, so the results count it as production and trade; a conversion between two "
    "electricity fuels is neither"
)
_UNMARKED_REASON = (
    "join two buses of one area or one location and state no is_conversion mark, so they count "
    "as production and trade; mark each conversion in extensions.json"
)
_UNPRODUCED_REASON = (
    "have a rating, but the solve states no output for them, so they have no production"
)
_LINES = "line(s)"
_COMPONENTS = "component(s)"

AnnualSchema = dict[str, pl.DataType | type[pl.DataType]]
PRODUCTION_SCHEMA: AnnualSchema = {
    ResultsCol.COMPONENT: pl.Utf8,
    ResultsCol.CATEGORY: pl.Utf8,
    AnnualCol.YEAR: pl.Int32,
    ResultsCol.VALUE: pl.Float64,
}
CAPACITY_SCHEMA: AnnualSchema = {
    ResultsCol.COMPONENT: pl.Utf8,
    AnnualCol.COMPONENT_TYPE: pl.Utf8,
    ResultsCol.VALUE: pl.Float64,
    ResultsCol.CATEGORY: pl.Utf8,
    AnnualCol.YEAR: pl.Int32,
}
_RATES_SCHEMA: AnnualSchema = {
    ResultsCol.COMPONENT: pl.Utf8,
    AnnualCol.POLLUTANT: pl.Utf8,
    AnnualCol.RATE: pl.Float64,
}

_Table = TypeVar("_Table", pl.DataFrame, pl.LazyFrame)
# The t/MWh of each pollutant that one component emits, or None where it states no rate.
RateFinder = Callable[[str], dict[str, float] | None]


class ResultsLeg(NamedTuple):
    """The framework of a solve, and the pipeline that writes its results."""

    framework: Framework
    pipeline: str


class AnnualDerivation(NamedTuple):
    """The sources of one annual variable, and how its rows derive from them."""

    sources: list[SourceField]
    derivation: str


class LineEnds(NamedTuple):
    """The columns that name a line and its two ends, and the columns of the place table."""

    name: str
    end0: str
    end1: str
    place_key: str
    place: str


class Production(NamedTuple):
    """MWh in each year, by component, for each kind of component that produces."""

    generators: pl.DataFrame
    storage: pl.DataFrame
    links: pl.DataFrame

    def build_table(self) -> pl.DataFrame:
        return pl.concat([self.generators, self.storage, self.links])

    def drop_links(self, names: frozenset[str]) -> Production:
        """The production without the links of `names`."""
        return self._replace(links=drop_components(self.links, names))


def drop_components(
    table: _Table, names: frozenset[str], column: str = ResultsCol.COMPONENT
) -> _Table:
    """The table without the rows of the components of `names`."""
    if not names:
        return table
    return table.filter(~pl.col(column).is_in(list(names)))


def build_one_place_lines(
    ends: pl.LazyFrame, places: pl.LazyFrame, columns: LineEnds
) -> frozenset[str]:
    """The name of each line whose two ends have the same place."""
    for end, alias in ((columns.end0, _PLACE0), (columns.end1, _PLACE1)):
        renamed = places.rename({columns.place_key: end, columns.place: alias})
        ends = ends.join(renamed, on=end, how="inner")
    inside = ends.filter(pl.col(_PLACE0) == pl.col(_PLACE1)).select(columns.name).collect()
    return frozenset(inside[columns.name].to_list())


def build_annual_rows(
    rows: pl.DataFrame | pl.LazyFrame,
    variable: ResultsVariable,
    value: pl.Expr | None = None,
) -> pl.LazyFrame:
    """The results rows of one annual variable, each at 1 January of its year."""
    january_first = pl.datetime(pl.col(AnnualCol.YEAR), _FIRST_MONTH, _FIRST_DAY)
    stated = pl.col(ResultsCol.VALUE) if value is None else value
    return rows.lazy().select(
        pl.lit(variable.value).alias(ResultsCol.VARIABLE),
        pl.col(ResultsCol.COMPONENT),
        pl.col(ResultsCol.CATEGORY),
        january_first.cast(RESULTS_SCHEMA[ResultsCol.TIMESTAMP]).alias(ResultsCol.TIMESTAMP),
        stated.cast(pl.Float64).alias(ResultsCol.VALUE),
    )


class AnnualRowsMapper:
    """Maps the annual rows of one framework's solve, and records their events."""

    def __init__(self, recorder: ScopedRecorder, leg: ResultsLeg) -> None:
        self._recorder = recorder
        self._leg = leg

    def map_production(
        self, production: pl.DataFrame, derivation: AnnualDerivation
    ) -> list[pl.LazyFrame]:
        if production.is_empty():
            return []
        self._record_derivation(ResultsVariable.PRODUCTION, derivation)
        return [build_annual_rows(production, ResultsVariable.PRODUCTION)]

    def map_installed_capacity(
        self, capacity: pl.DataFrame, production: pl.DataFrame, derivation: AnnualDerivation
    ) -> list[pl.LazyFrame]:
        """The rating of each component; it reports each one that the solve gives no output."""
        if capacity.is_empty():
            return []
        self._record_derivation(ResultsVariable.INSTALLED_CAPACITY, derivation)
        self._report_unproduced(capacity.join(production, on=ResultsCol.COMPONENT, how="anti"))
        return [build_annual_rows(capacity, ResultsVariable.INSTALLED_CAPACITY)]

    def map_emissions(
        self, energy: pl.DataFrame, find_rates: RateFinder, derivation: AnnualDerivation
    ) -> list[pl.LazyFrame]:
        """t in each year, by pollutant, from the energy of each component that states a rate."""
        rates = _build_emission_rates(energy, find_rates)
        if rates.is_empty():
            return []
        self._record_derivation(ResultsVariable.EMISSIONS, derivation)
        return [build_annual_rows(_build_emissions(energy, rates), ResultsVariable.EMISSIONS)]

    def report_conversions(self, component_type: str, names: frozenset[str]) -> None:
        """Record each conversion line, which has no annual row, and name a few."""
        report = self._build_report(component_type, _LINES, _CONVERSION_REASON, _CONVERSION_NOTE)
        self._report_names(names, report)

    def report_unmarked(self, component_type: str, names: frozenset[str]) -> None:
        """Record each line that joins two buses of one place and states no conversion mark."""
        report = self._build_report(component_type, _LINES, _UNMARKED_REASON, _UNMARKED_NOTE)
        self._report_names(names, replace(report, attribute_col=_MARK, attribute_name=_MARK_NAME))

    def _report_unproduced(self, capacity: pl.DataFrame) -> None:
        rows = capacity.unique(ResultsCol.COMPONENT, maintain_order=True)
        for (component_type,), table in rows.group_by(
            AnnualCol.COMPONENT_TYPE, maintain_order=True
        ):
            report = self._build_report(
                str(component_type), _COMPONENTS, _UNPRODUCED_REASON, _UNPRODUCED_NOTE
            )
            report_not_mapped(table, pl.lit(False), report, self._recorder)  # noqa: FBT003

    def _report_names(self, names: frozenset[str], report: SkipReport) -> None:
        table = pl.DataFrame(
            {ResultsCol.COMPONENT: sorted(names), _MARK: None},
            schema={ResultsCol.COMPONENT: pl.Utf8, _MARK: pl.Boolean},
        )
        report_not_mapped(table, pl.lit(False), report, self._recorder)  # noqa: FBT003

    def _build_report(self, component_type: str, noun: str, reason: str, note: str) -> SkipReport:
        return SkipReport(
            pipeline=self._leg.pipeline,
            framework=self._leg.framework,
            component=component_type,
            name_col=ResultsCol.COMPONENT,
            reason=reason,
            counted_noun=noun,
            note=note,
        )

    def _record_derivation(self, variable: ResultsVariable, derivation: AnnualDerivation) -> None:
        self._recorder.append(
            TranslationEvent(
                kind=EventKind.VALUE_DERIVED,
                sources=list(derivation.sources),
                destinations=[build_results_destination(variable)],
                derivation=derivation.derivation,
            )
        )


def build_results_destination(variable: ResultsVariable) -> DestinationField:
    return DestinationField(
        framework=Framework.RESULTS,
        component=RESULTS_TABLE_KEY,
        name=str(variable),
        attribute=ResultsCol.VARIABLE,
        unit=VARIABLE_UNIT[variable],
    )


def build_results_source(variable: ResultsVariable) -> SourceField:
    """A results row that the step already wrote, as the source of a row derived from it."""
    return SourceField(
        framework=Framework.RESULTS,
        component=RESULTS_TABLE_KEY,
        name=str(variable),
        attribute=ResultsCol.VARIABLE,
        unit=VARIABLE_UNIT[variable],
    )


def _build_emission_rates(production: pl.DataFrame, find_rates: RateFinder) -> pl.DataFrame:
    """The t/MWh of each pollutant, for each component of the solve that states a rate."""
    rows = [
        (name, pollutant, rate)
        for name in production[ResultsCol.COMPONENT].unique().sort().to_list()
        for pollutant, rate in (find_rates(name) or {}).items()
    ]
    return pl.DataFrame(rows, schema=_RATES_SCHEMA, orient="row")


def _build_emissions(production: pl.DataFrame, rates: pl.DataFrame) -> pl.DataFrame:
    """t in each year, by pollutant: the production of each component × its rate, summed."""
    emitted = (pl.col(ResultsCol.VALUE) * pl.col(AnnualCol.RATE)).sum().alias(ResultsCol.VALUE)
    return (
        production.join(rates, on=ResultsCol.COMPONENT, how="inner")
        .group_by(AnnualCol.POLLUTANT, AnnualCol.YEAR, maintain_order=True)
        .agg(emitted)
        .select(
            pl.col(AnnualCol.POLLUTANT).alias(ResultsCol.COMPONENT),
            pl.lit(None, dtype=pl.Utf8).alias(ResultsCol.CATEGORY),
            AnnualCol.YEAR,
            ResultsCol.VALUE,
        )
    )
