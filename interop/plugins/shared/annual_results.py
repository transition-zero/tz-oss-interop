"""The annual rows that every results step writes for a solve over representative periods.

Production, installed capacity and emissions each take one row for each component, or for
each pollutant, in each year of the solve, at 1 January of the year. The rows of every
framework share these definitions, so two solves of one model compare row by row.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import NamedTuple

import polars as pl

from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import Framework
from interop.plugins.shared.pypsa_fuel_components import FuelComponents
from interop.plugins.shared.results_constants import (
    RESULTS_SCHEMA,
    RESULTS_TABLE_KEY,
    VARIABLE_UNIT,
    ResultsCol,
    ResultsVariable,
)
from interop.plugins.shared.sienna_results_constants import AnnualCol
from interop.plugins.shared.warning_text import name_a_few
from interop.ports.outbound.reporting import (
    DestinationField,
    EventKind,
    SourceField,
    TranslationEvent,
)

log = logging.getLogger(__name__)

_FIRST_MONTH = 1
_FIRST_DAY = 1

EMISSIONS_DERIVATION = (
    "Σ over generators of production × emission_rates_t_per_mwh of the pollutant → emissions "
    "at 1 January of the year"
)
_UNPRODUCED_NOTE = (
    "the solve states no output for the component, so it has installed_capacity and no production"
)
_UNPRODUCED_WARNING = (
    "%d component(s) have a rating, but the solve states no output for them, so they have no "
    "production: %s"
)

AnnualSchema = dict[str, pl.DataType | type[pl.DataType]]
PRODUCTION_SCHEMA: AnnualSchema = {
    ResultsCol.COMPONENT: pl.Utf8,
    ResultsCol.CATEGORY: pl.Utf8,
    AnnualCol.YEAR: pl.Int32,
    ResultsCol.VALUE: pl.Float64,
}
RATES_SCHEMA: AnnualSchema = {
    ResultsCol.COMPONENT: pl.Utf8,
    AnnualCol.POLLUTANT: pl.Utf8,
    AnnualCol.RATE: pl.Float64,
}


def build_emission_rates(
    production: pl.DataFrame, find_rates: Callable[[str], dict[str, float] | None]
) -> pl.DataFrame:
    """The t/MWh of each pollutant, for each component of the solve that states a rate."""
    rows = [
        (name, pollutant, rate)
        for name in production[ResultsCol.COMPONENT].unique().sort().to_list()
        for pollutant, rate in (find_rates(name) or {}).items()
    ]
    return pl.DataFrame(rows, schema=RATES_SCHEMA, orient="row")


def build_emissions(production: pl.DataFrame, rates: pl.DataFrame) -> pl.DataFrame:
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


def build_annual_rows(rows: pl.DataFrame, variable: ResultsVariable) -> pl.LazyFrame:
    """The results rows of one annual variable, each at 1 January of its year."""
    january_first = pl.datetime(pl.col(AnnualCol.YEAR), _FIRST_MONTH, _FIRST_DAY)
    return rows.lazy().select(
        pl.lit(variable.value).alias(ResultsCol.VARIABLE),
        pl.col(ResultsCol.COMPONENT),
        pl.col(ResultsCol.CATEGORY),
        january_first.cast(RESULTS_SCHEMA[ResultsCol.TIMESTAMP]).alias(ResultsCol.TIMESTAMP),
        pl.col(ResultsCol.VALUE).cast(pl.Float64),
    )


class Production(NamedTuple):
    """MWh in each year, by component, for each kind of component that produces."""

    generators: pl.DataFrame
    storage: pl.DataFrame
    links: pl.DataFrame

    def build_table(self) -> pl.DataFrame:
        return pl.concat([self.generators, self.storage, self.links])

    def drop_links(self, names: frozenset[str]) -> Production:
        """The production without the links of `names`."""
        return self._replace(
            links=self.links.filter(~pl.col(ResultsCol.COMPONENT).is_in(list(names)))
        )

    def drop_fuels(self, fuels: FuelComponents) -> Production:
        """The production of electricity: no generator and no link of a fuel."""
        component = pl.col(ResultsCol.COMPONENT)
        return Production(
            generators=self.generators.filter(~component.is_in(list(fuels.generators))),
            storage=self.storage,
            links=self.links.filter(~component.is_in(list(fuels.fuel_links))),
        )


class AnnualReporter:
    """Records the events of the annual rows of one framework's solve."""

    def __init__(self, recorder: ScopedRecorder, framework: Framework) -> None:
        self._recorder = recorder
        self._framework = framework

    def record_derivation(
        self, variable: ResultsVariable, sources: list[SourceField], derivation: str
    ) -> None:
        self._recorder.append(
            TranslationEvent(
                kind=EventKind.VALUE_DERIVED,
                sources=list(sources),
                destinations=[build_results_destination(variable)],
                derivation=derivation,
            )
        )

    def report_unproduced(self, capacity: pl.DataFrame) -> None:
        """Report each component that has a rating and no output in the solve."""
        rows = capacity.unique(ResultsCol.COMPONENT, maintain_order=True)
        names = rows[ResultsCol.COMPONENT].to_list()
        for row in rows.iter_rows(named=True):
            self._record_unproduced(row[AnnualCol.COMPONENT_TYPE], row[ResultsCol.COMPONENT])
        if names:
            log.warning(_UNPRODUCED_WARNING, len(names), name_a_few(names))

    def _record_unproduced(self, component_type: str, name: str) -> None:
        self._recorder.append(
            TranslationEvent(
                kind=EventKind.NOT_MAPPED,
                sources=[
                    SourceField(framework=self._framework, component=component_type, name=name)
                ],
                destinations=[build_results_destination(ResultsVariable.PRODUCTION)],
                note=_UNPRODUCED_NOTE,
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
