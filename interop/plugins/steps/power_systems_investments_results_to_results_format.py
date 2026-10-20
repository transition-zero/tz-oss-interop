"""Turn a staged PowerSystemsInvestments.jl solve into the long-format results table.

Each annual row takes the timestamp of 1 January of its year. A component keeps the name of
its technology in the portfolio, so the rows join the rows of the model the portfolio came
from. The solve states no category, so each row leaves it null.
"""

from __future__ import annotations

import logging
from typing import ClassVar, NamedTuple

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import Framework
from interop.plugins.shared.power_systems_investments_results_constants import (
    HOUR_WEIGHTS_KEY,
    INVESTMENT_RESULTS_KEY,
    OBJECTIVE_KEY,
    OBJECTIVE_VALUE_COLUMN,
    OPERATIONS_RESULTS_KEY,
    PERIOD_YEARS_KEY,
    InvestmentsResult,
    StagedResultCol,
)
from interop.plugins.shared.results_constants import (
    RESULTS_SCHEMA,
    RESULTS_TABLE_KEY,
    VARIABLE_DTYPE,
    VARIABLE_UNIT,
    ResultsCol,
    ResultsVariable,
)
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
_RESULTS_COMPONENT = "results"
_SIGNED_VALUE = "signed_value"

_UNWEIGHTED_WARNING = (
    "power-systems-investments-to-results: %d hour(s) of the solve fall in no slice of the "
    "series document, so production leaves them out: %s"
)
_UNKNOWN_PERIOD_WARNING = (
    "power-systems-investments-to-results: %d investment period(s) of the solve are not "
    "periods of the series document, so their capacity rows are left out: %s"
)


class Derivation(NamedTuple):
    """How one result of the solve becomes one variable of the results table."""

    sources: tuple[InvestmentsResult, ...]
    destination: ResultsVariable
    text: str


_NEW_CAPACITY = Derivation(
    (InvestmentsResult.BUILD_CAPACITY, InvestmentsResult.BUILD_POWER_CAPACITY),
    ResultsVariable.NEW_CAPACITY,
    "the MW that the plan builds in an investment period → new_capacity at 1 January of the "
    "year of the period; a storage technology gives its power, and its energy is left out",
)
_INSTALLED_CAPACITY = Derivation(
    (InvestmentsResult.CUMULATIVE_CAPACITY, InvestmentsResult.CUMULATIVE_POWER_CAPACITY),
    ResultsVariable.INSTALLED_CAPACITY,
    "the existing MW that the model counts plus the MW built in this and every earlier period → "
    "installed_capacity at 1 January of the year of the period",
)
_PRODUCTION = Derivation(
    (
        InvestmentsResult.ACTIVE_POWER,
        InvestmentsResult.ACTIVE_OUT_POWER,
        InvestmentsResult.FLOW_ACTIVE_POWER,
    ),
    ResultsVariable.PRODUCTION,
    "Σ over the hours of the solve of the output in MW × the hours of a value × the weight of "
    "the representative day that holds the hour → production at 1 January of the year; a "
    "storage technology gives its discharge, and a transport technology the |flow| it carries",
)
_OBJECTIVE_DERIVATION = "objective_value of the solve → objective"


class PowerSystemsInvestmentsResultsToResultsFormat(TranslationStep):
    name: ClassVar[str] = "power_systems_investments_results_to_results_format"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def run(self, state: State, params: BaseModel | None) -> State:
        period_years = state.source_topology[PERIOD_YEARS_KEY].collect()
        investment = state.source_topology[INVESTMENT_RESULTS_KEY].collect()
        pieces = [
            self._map_capacity(investment, period_years, _NEW_CAPACITY),
            self._map_capacity(investment, period_years, _INSTALLED_CAPACITY),
            self._map_production(state),
            self._map_objective(state),
        ]
        state.destination_tables[RESULTS_TABLE_KEY] = pl.concat(pieces, how="vertical")
        return state

    def _map_capacity(
        self, investment: pl.DataFrame, period_years: pl.DataFrame, derivation: Derivation
    ) -> pl.DataFrame:
        rows = investment.filter(
            pl.col(StagedResultCol.RESULT).is_in([str(one) for one in derivation.sources])
        )
        if rows.is_empty():
            return _build_empty_results()
        dated = rows.join(period_years, on=StagedResultCol.PERIOD, how="left")
        self._warn_unknown_periods(dated)
        self._record(derivation)
        return _build_annual_results(
            dated.filter(pl.col(StagedResultCol.YEAR).is_not_null()), derivation
        )

    def _map_production(self, state: State) -> pl.DataFrame:
        operations = state.source_time_series[OPERATIONS_RESULTS_KEY]
        weights = state.source_topology[HOUR_WEIGHTS_KEY]
        weighted = operations.join(weights, on=StagedResultCol.SNAPSHOT, how="left")
        unweighted = (
            weighted.filter(pl.col(StagedResultCol.WEIGHT).is_null())
            .select(pl.col(StagedResultCol.SNAPSHOT).unique().sort())
            .collect()
        )
        self._warn_unweighted(unweighted)
        production = (
            weighted.filter(pl.col(StagedResultCol.WEIGHT).is_not_null())
            .group_by(StagedResultCol.COMPONENT, StagedResultCol.YEAR)
            .agg(
                (_express_output() * pl.col(StagedResultCol.HOURS) * pl.col(StagedResultCol.WEIGHT))
                .sum()
                .alias(StagedResultCol.VALUE)
            )
            .sort(StagedResultCol.COMPONENT, StagedResultCol.YEAR)
            .collect()
        )
        if production.is_empty():
            return _build_empty_results()
        self._record(_PRODUCTION)
        return _build_annual_results(production, _PRODUCTION)

    def _map_objective(self, state: State) -> pl.DataFrame:
        source = state.source_topology.get(OBJECTIVE_KEY)
        if source is None:
            return _build_empty_results()
        objective = source.collect()
        self._recorder.append(
            TranslationEvent(
                kind=EventKind.VALUE_DERIVED,
                sources=[
                    SourceField(
                        Framework.POWER_SYSTEMS_INVESTMENTS,
                        _RESULTS_COMPONENT,
                        OBJECTIVE_VALUE_COLUMN,
                        OBJECTIVE_VALUE_COLUMN,
                        objective[OBJECTIVE_VALUE_COLUMN][0],
                    )
                ],
                destinations=[_build_destination(ResultsVariable.OBJECTIVE)],
                derivation=_OBJECTIVE_DERIVATION,
            )
        )
        return objective.select(
            pl.lit(str(ResultsVariable.OBJECTIVE)).cast(VARIABLE_DTYPE).alias(ResultsCol.VARIABLE),
            pl.lit(None, dtype=pl.Utf8).alias(ResultsCol.COMPONENT),
            pl.lit(None, dtype=pl.Utf8).alias(ResultsCol.CATEGORY),
            pl.lit(None, dtype=RESULTS_SCHEMA[ResultsCol.TIMESTAMP]).alias(ResultsCol.TIMESTAMP),
            pl.col(OBJECTIVE_VALUE_COLUMN).cast(pl.Float64).alias(ResultsCol.VALUE),
        )

    def _record(self, derivation: Derivation) -> None:
        self._recorder.append(
            TranslationEvent(
                kind=EventKind.VALUE_DERIVED,
                sources=[
                    SourceField(
                        Framework.POWER_SYSTEMS_INVESTMENTS,
                        _RESULTS_COMPONENT,
                        str(source),
                        str(source),
                    )
                    for source in derivation.sources
                ],
                destinations=[_build_destination(derivation.destination)],
                derivation=derivation.text,
            )
        )

    def _warn_unknown_periods(self, dated: pl.DataFrame) -> None:
        unknown = (
            dated.filter(pl.col(StagedResultCol.YEAR).is_null())[StagedResultCol.PERIOD]
            .unique()
            .sort()
            .to_list()
        )
        if unknown:
            log.warning(
                _UNKNOWN_PERIOD_WARNING, len(unknown), name_a_few(str(one) for one in unknown)
            )

    def _warn_unweighted(self, unweighted: pl.DataFrame) -> None:
        if unweighted.is_empty():
            return
        hours = [stamp.isoformat() for stamp in unweighted[StagedResultCol.SNAPSHOT].to_list()]
        log.warning(_UNWEIGHTED_WARNING, len(hours), name_a_few(hours))


def _express_output() -> pl.Expr:
    """The MW that a value puts out: |flow| for a transport technology, else the value."""
    value = pl.col(StagedResultCol.VALUE)
    is_flow = pl.col(StagedResultCol.RESULT) == str(InvestmentsResult.FLOW_ACTIVE_POWER)
    return pl.when(is_flow).then(value.abs()).otherwise(value).alias(_SIGNED_VALUE)


def _build_annual_results(rows: pl.DataFrame, derivation: Derivation) -> pl.DataFrame:
    return rows.select(
        pl.lit(str(derivation.destination)).cast(VARIABLE_DTYPE).alias(ResultsCol.VARIABLE),
        pl.col(StagedResultCol.COMPONENT).alias(ResultsCol.COMPONENT),
        pl.lit(None, dtype=pl.Utf8).alias(ResultsCol.CATEGORY),
        pl.datetime(pl.col(StagedResultCol.YEAR), _FIRST_MONTH, _FIRST_DAY)
        .cast(RESULTS_SCHEMA[ResultsCol.TIMESTAMP])
        .alias(ResultsCol.TIMESTAMP),
        pl.col(StagedResultCol.VALUE).cast(pl.Float64).alias(ResultsCol.VALUE),
    )


def _build_empty_results() -> pl.DataFrame:
    return pl.DataFrame(schema=RESULTS_SCHEMA)


def _build_destination(variable: ResultsVariable) -> DestinationField:
    return DestinationField(
        Framework.RESULTS,
        str(variable),
        str(variable),
        str(variable),
        unit=str(VARIABLE_UNIT[variable]),
    )
