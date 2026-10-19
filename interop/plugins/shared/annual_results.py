"""The annual rows that every results step writes for a solve over representative periods.

Production, installed capacity and emissions each take one row for each component, or for
each pollutant, in each year of the solve, at 1 January of the year. The rows of every
framework share these definitions, so two solves of one model compare row by row.
"""

from __future__ import annotations

from collections.abc import Callable

import polars as pl

from interop.plugins.shared.results_constants import (
    RESULTS_SCHEMA,
    ResultsCol,
    ResultsVariable,
)
from interop.plugins.shared.sienna_results_constants import AnnualCol

_FIRST_MONTH = 1
_FIRST_DAY = 1

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
