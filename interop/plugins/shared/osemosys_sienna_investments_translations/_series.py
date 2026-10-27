"""The hourly series of the portfolio: one for each owner and each year of the plan.

A series covers the representative days of the base year, from 1 January of its own year, as
the expansion weights every year by the representative periods of the base year. Its feature
`year` names the year, as PowerSystemsInvestments.jl reads a series of an investment period. The
values are in natural units: MW of demand, or the per-unit availability of a technology. The
portfolio sink writes them to an HDF5 companion of its own.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.constants import UNSCALED, StagedTimeSeriesCol
from interop.plugins.shared.osemosys_sienna_constants import (
    OSEMOSYS_PORTFOLIO_SERIES,
    SERIES_KEY_SEPARATOR,
    SERIES_YEAR_SEPARATOR,
    YEAR_FEATURE,
)
from interop.plugins.shared.osemosys_sienna_translations._events import build_sienna_field
from interop.plugins.shared.sienna_constants import (
    SiennaSeriesName,
    SiennaTimeSeriesAssociationCol,
    time_series_uuid,
)
from interop.plugins.shared.sienna_investments_constants import (
    PORTFOLIO_TIME_SERIES_ASSOCIATION_SCHEMA,
    PORTFOLIO_TIME_SERIES_ASSOCIATIONS_TABLE,
)
from interop.plugins.shared.sienna_time_series import collect_ts_info, ts_association_row
from interop.ports.outbound.reporting import EventKind, SourceField, TranslationEvent

# The series name of each series of the portfolio.
PORTFOLIO_SERIES_NAME = SiennaSeriesName.MAX_ACTIVE_POWER
# The field of an owner that its series of every year fill, as the report names it.
SERIES_FIELD = f"{PORTFOLIO_SERIES_NAME} time series, one for each year"


@dataclass(frozen=True)
class PortfolioSeries:
    """The series of one year, for each owner of one type that the table names."""

    owner_type: str
    year: int
    table: pl.LazyFrame

    @property
    def attribute(self) -> str:
        return f"{PORTFOLIO_SERIES_NAME}{SERIES_YEAR_SEPARATOR}{self.year}"

    @property
    def key(self) -> tuple[str, str]:
        """The `State.source_time_series` key, which is also the source of each association."""
        return (
            OSEMOSYS_PORTFOLIO_SERIES,
            f"{self.owner_type}{SERIES_KEY_SEPARATOR}{self.attribute}",
        )


def build_series_event(
    owner: str,
    name: str,
    sources: Sequence[SourceField],
    derivation: str,
    unit: str | None = None,
) -> TranslationEvent:
    """The one event of the series of every year of one owner, in `unit`."""
    return TranslationEvent(
        kind=EventKind.VALUE_DERIVED,
        sources=list(sources),
        destinations=[build_sienna_field(owner, name, SERIES_FIELD, None, unit)],
        derivation=derivation,
    )


def list_series_components(table: pl.LazyFrame) -> list[str]:
    """The component that each series of `table` belongs to, once each."""
    components = table.select(pl.col(StagedTimeSeriesCol.COMPONENT).unique()).collect()
    return components[StagedTimeSeriesCol.COMPONENT].to_list()


def set_portfolio_series(
    state: State, series: Iterable[PortfolioSeries], owner_ids: Mapping[str, int]
) -> None:
    """Stage each series and add one association row for each owner that it names."""
    for one in series:
        state.source_time_series[one.key] = one.table
        _add_associations(state, _build_associations(one, owner_ids))


def _add_associations(state: State, rows: pl.DataFrame) -> None:
    existing = state.destination_tables.get(PORTFOLIO_TIME_SERIES_ASSOCIATIONS_TABLE)
    state.destination_tables[PORTFOLIO_TIME_SERIES_ASSOCIATIONS_TABLE] = (
        rows if existing is None else pl.concat([existing, rows])
    )


def _build_associations(series: PortfolioSeries, owner_ids: Mapping[str, int]) -> pl.DataFrame:
    col = SiennaTimeSeriesAssociationCol
    ts_info = collect_ts_info(series.table)
    source_table, source_attribute = series.key
    features = json.dumps({YEAR_FEATURE: str(series.year)})
    names = sorted(list_series_components(series.table))
    rows = [
        {
            **ts_association_row(
                owner_type=series.owner_type,
                owner_id=owner_ids[name],
                component_name=name,
                series_name=PORTFOLIO_SERIES_NAME,
                ts_info=ts_info,
                source_table=source_table,
                source_attribute=source_attribute,
                scaling_factor=UNSCALED,
            ),
            col.TIME_SERIES_UUID: time_series_uuid(series.owner_type, name, series.attribute),
            col.FEATURES: features,
            col.SCALING_FACTOR_MULTIPLIER: None,
        }
        for name in names
        if name in owner_ids
    ]
    return pl.DataFrame(rows, schema=PORTFOLIO_TIME_SERIES_ASSOCIATION_SCHEMA)
