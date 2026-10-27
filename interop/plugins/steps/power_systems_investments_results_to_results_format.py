"""Turn a staged PowerSystemsInvestments.jl solve into the long-format results table.

Each annual row takes the timestamp of 1 January of its year. A component keeps the name of
its technology in the portfolio, so the rows join the rows of the model the portfolio came
from. The solve states no category, so each row leaves it null.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import ClassVar, NamedTuple

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.annual_results import build_annual_rows, build_results_destination
from interop.plugins.shared.constants import Framework
from interop.plugins.shared.power_systems_investments_results_constants import (
    HOUR_WEIGHTS_KEY,
    INVESTMENT_RESULTS_KEY,
    OBJECTIVE_KEY,
    OBJECTIVE_VALUE_COLUMN,
    OPERATIONS_RESULTS_KEY,
    PERIOD_YEARS_KEY,
    InvestmentsResult,
    ResultsCsvCol,
    StagedResultCol,
)
from interop.plugins.shared.power_systems_investments_schema import SeriesDocument
from interop.plugins.shared.results_constants import (
    RESULTS_SCHEMA,
    RESULTS_TABLE_KEY,
    ResultsCol,
    ResultsVariable,
)
from interop.plugins.shared.sienna_results_constants import AnnualCol
from interop.plugins.shared.warning_text import name_a_few
from interop.ports.outbound.reporting import EventKind, SourceField, TranslationEvent

log = logging.getLogger(__name__)

POWER_SYSTEMS_INVESTMENTS_TO_RESULTS = "power-systems-investments-to-results"

_RESULTS_COMPONENT = "results"
_SLICE_KEYS = [StagedResultCol.YEAR, StagedResultCol.REPRESENTATIVE_DAY]
_HOUR_ROW_KEYS = [
    StagedResultCol.RESULT,
    StagedResultCol.TECHNOLOGY,
    StagedResultCol.COMPONENT,
    StagedResultCol.SNAPSHOT,
]

_UNWEIGHTED_WARNING = (
    "%d hour(s) of the solve fall in no slice of the series document, so production leaves "
    "them out: %s"
)
_OVERLAPPING_SLICE_NOTE = (
    "the slice holds an hour that the slice {earlier} also holds, so it is left out, and "
    "production leaves out each of its hours that no other slice holds"
)
_OVERLAPPING_SLICE_WARNING = (
    "%d slice(s) of the series document hold an hour that an earlier slice holds, so each is "
    "left out: %s"
)
_SHARED_NAME_NOTE = (
    "the name belongs to the technology types {technologies}, and the results name a component "
    "by its name alone, so each row of the name is left out"
)
_SHARED_NAME_WARNING = (
    "%d component name(s) belong to more than one technology type of the solve, so the rows of "
    "each are left out: %s"
)
_UNKNOWN_PERIOD_WARNING = (
    "%d investment period(s) of the solve are not periods of the series document, so their "
    "capacity rows are left out: %s"
)


class Slice(NamedTuple):
    """One slice of the series document, which its year and its number name together."""

    year: int
    representative_day: int

    @property
    def name(self) -> str:
        return f"{self.representative_day} of {self.year}"


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
        operations = state.source_time_series[OPERATIONS_RESULTS_KEY]
        shared = _list_shared_names(investment, operations)
        self._report_shared_names(shared)
        is_unshared = _express_unshared(list(shared))
        investment = investment.filter(is_unshared)
        weights = self._choose_hour_weights(state.source_topology[HOUR_WEIGHTS_KEY].collect())
        pieces = [
            self._map_capacity(investment, period_years, _NEW_CAPACITY),
            self._map_capacity(investment, period_years, _INSTALLED_CAPACITY),
            self._map_production(operations.filter(is_unshared), weights),
            self._map_objective(state),
        ]
        state.destination_tables[RESULTS_TABLE_KEY] = _build_results_table(pieces)
        return state

    def _map_capacity(
        self, investment: pl.DataFrame, period_years: pl.DataFrame, derivation: Derivation
    ) -> pl.LazyFrame:
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

    def _choose_hour_weights(self, weights: pl.DataFrame) -> pl.DataFrame:
        """The hours of each slice that holds no hour of an earlier slice; it reports the rest."""
        holders: dict[datetime, Slice] = {}
        left_out: dict[Slice, Slice] = {}
        for (year, representative_day), hours in weights.group_by(_SLICE_KEYS, maintain_order=True):
            one = Slice(int(year), int(representative_day))
            snapshots = hours[StagedResultCol.SNAPSHOT].to_list()
            earlier = next((holders[hour] for hour in snapshots if hour in holders), None)
            if earlier is None:
                holders.update(dict.fromkeys(snapshots, one))
            else:
                left_out[one] = earlier
        self._report_overlapping_slices(left_out)
        return weights.join(_build_slice_keys(list(left_out)), on=_SLICE_KEYS, how="anti")

    def _map_production(self, operations: pl.LazyFrame, weights: pl.DataFrame) -> pl.LazyFrame:
        # The solve writes a row for each hour of each slice, so an hour two slices hold has two.
        first_rows = operations.unique(_HOUR_ROW_KEYS, keep="first", maintain_order=True)
        weighted = first_rows.join(weights.lazy(), on=StagedResultCol.SNAPSHOT, how="left")
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

    def _map_objective(self, state: State) -> pl.LazyFrame:
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
                destinations=[build_results_destination(ResultsVariable.OBJECTIVE)],
                derivation=_OBJECTIVE_DERIVATION,
            )
        )
        return objective.lazy().select(
            pl.lit(str(ResultsVariable.OBJECTIVE)).alias(ResultsCol.VARIABLE),
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
                destinations=[build_results_destination(derivation.destination)],
                derivation=derivation.text,
            )
        )

    def _report_shared_names(self, shared: dict[str, list[str]]) -> None:
        for name, technologies in shared.items():
            self._recorder.append(
                TranslationEvent(
                    kind=EventKind.COMPONENT_SKIPPED,
                    sources=[
                        SourceField(
                            framework=Framework.POWER_SYSTEMS_INVESTMENTS,
                            component=_RESULTS_COMPONENT,
                            name=name,
                            attribute=ResultsCsvCol.NAME,
                            value=name,
                        )
                    ],
                    note=_SHARED_NAME_NOTE.format(technologies=" and ".join(technologies)),
                )
            )
        if shared:
            _warn(_SHARED_NAME_WARNING, len(shared), name_a_few(shared))

    def _report_overlapping_slices(self, left_out: dict[Slice, Slice]) -> None:
        for one, earlier in left_out.items():
            self._recorder.append(
                TranslationEvent(
                    kind=EventKind.COMPONENT_SKIPPED,
                    sources=[
                        SourceField(
                            framework=Framework.POWER_SYSTEMS_INVESTMENTS,
                            component=SeriesDocument.REPRESENTATIVE_DAY,
                            name=one.name,
                        )
                    ],
                    note=_OVERLAPPING_SLICE_NOTE.format(earlier=earlier.name),
                )
            )
        if left_out:
            _warn(
                _OVERLAPPING_SLICE_WARNING, len(left_out), name_a_few(one.name for one in left_out)
            )

    def _warn_unknown_periods(self, dated: pl.DataFrame) -> None:
        unknown = (
            dated.filter(pl.col(StagedResultCol.YEAR).is_null())[StagedResultCol.PERIOD]
            .unique()
            .sort()
            .to_list()
        )
        if unknown:
            _warn(_UNKNOWN_PERIOD_WARNING, len(unknown), name_a_few(str(one) for one in unknown))

    def _warn_unweighted(self, unweighted: pl.DataFrame) -> None:
        if unweighted.is_empty():
            return
        hours = [stamp.isoformat() for stamp in unweighted[StagedResultCol.SNAPSHOT].to_list()]
        _warn(_UNWEIGHTED_WARNING, len(hours), name_a_few(hours))


def _list_shared_names(investment: pl.DataFrame, operations: pl.LazyFrame) -> dict[str, list[str]]:
    """Each component name that more than one technology type states, with those types."""
    columns = [StagedResultCol.COMPONENT, StagedResultCol.TECHNOLOGY]
    shared = (
        pl.concat([investment.lazy().select(columns), operations.select(columns)])
        .unique()
        .group_by(StagedResultCol.COMPONENT)
        .agg(pl.col(StagedResultCol.TECHNOLOGY).sort())
        .filter(pl.col(StagedResultCol.TECHNOLOGY).list.len() > 1)
        .sort(StagedResultCol.COMPONENT)
        .collect()
    )
    return {
        row[StagedResultCol.COMPONENT]: row[StagedResultCol.TECHNOLOGY]
        for row in shared.iter_rows(named=True)
    }


def _build_slice_keys(slices: list[Slice]) -> pl.DataFrame:
    return pl.DataFrame(
        slices,
        schema={StagedResultCol.YEAR: pl.Int32, StagedResultCol.REPRESENTATIVE_DAY: pl.Int64},
        orient="row",
    )


def _express_unshared(shared: list[str]) -> pl.Expr:
    return ~pl.col(StagedResultCol.COMPONENT).is_in(shared)


def _express_output() -> pl.Expr:
    """The MW that a value puts out: |flow| for a transport technology, else the value."""
    value = pl.col(StagedResultCol.VALUE)
    is_flow = pl.col(StagedResultCol.RESULT) == str(InvestmentsResult.FLOW_ACTIVE_POWER)
    return pl.when(is_flow).then(value.abs()).otherwise(value)


def _build_annual_results(rows: pl.DataFrame, derivation: Derivation) -> pl.LazyFrame:
    annual = rows.select(
        pl.col(StagedResultCol.COMPONENT).alias(ResultsCol.COMPONENT),
        pl.lit(None, dtype=pl.Utf8).alias(ResultsCol.CATEGORY),
        pl.col(StagedResultCol.YEAR).alias(AnnualCol.YEAR),
        pl.col(StagedResultCol.VALUE).alias(ResultsCol.VALUE),
    )
    return build_annual_rows(annual, derivation.destination)


def _build_empty_results() -> pl.LazyFrame:
    return pl.LazyFrame(schema=RESULTS_SCHEMA)


def _build_results_table(pieces: list[pl.LazyFrame]) -> pl.DataFrame:
    combined = pl.concat(
        [piece.cast(RESULTS_SCHEMA) for piece in pieces],  # type: ignore[arg-type]
        how="vertical",
    )
    return combined.collect()


def _warn(template: str, *args: object) -> None:
    """Write one warning of the step, after the name of its pipeline."""
    log.warning(f"%s: {template}", POWER_SYSTEMS_INVESTMENTS_TO_RESULTS, *args)
