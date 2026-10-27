"""Turn a staged PowerSystemsInvestments.jl solve into the long-format results table.

Each annual row takes the timestamp of 1 January of its year. A component keeps the name of
its technology in the portfolio, so the rows join the rows of the model the portfolio came
from. The solve states no category, so each row leaves it null.
"""

from __future__ import annotations

import math
from typing import Any, ClassVar, NamedTuple

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.annual_results import build_annual_rows, build_results_destination
from interop.plugins.shared.constants import Framework
from interop.plugins.shared.power_systems_investments_results_constants import (
    HOUR_WEIGHTS_KEY,
    INVESTMENT_RESULT_CSVS,
    INVESTMENT_RESULTS_KEY,
    OBJECTIVE_KEY,
    OBJECTIVE_VALUE_COLUMN,
    OPERATIONS_RESULT_CSVS,
    OPERATIONS_RESULTS_KEY,
    OPTIMIZER_STATS_CSV,
    PERIOD_YEARS_KEY,
    InvestmentsResult,
    ResultsCsvCol,
    StagedResultCol,
)
from interop.plugins.shared.power_systems_investments_schema import SeriesDocument
from interop.plugins.shared.representative_periods import Period
from interop.plugins.shared.results_constants import (
    RESULTS_SCHEMA,
    RESULTS_TABLE_KEY,
    ResultsCol,
    ResultsVariable,
)
from interop.plugins.shared.sienna_results_constants import AnnualCol
from interop.plugins.shared.translation_runner import (
    DROPPED_NAMES_LABEL,
    SkippedNames,
    SkipReport,
    filter_component,
    report_not_mapped,
)
from interop.ports.outbound.reporting import EventKind, SourceField, TranslationEvent

POWER_SYSTEMS_INVESTMENTS_TO_RESULTS = "power-systems-investments-to-results"

_RESULTS_COMPONENT = "results"
_SLICE_KEYS = [StagedResultCol.YEAR, StagedResultCol.REPRESENTATIVE_DAY]
_HOUR_ROW_KEYS = [
    StagedResultCol.RESULT,
    StagedResultCol.TECHNOLOGY,
    StagedResultCol.COMPONENT,
    StagedResultCol.SNAPSHOT,
]

# Working columns of the slices and hours that the reports name.
_SLICE_NAME = "slice"
_FIRST_HOUR = "first_hour"
_EARLIER_SLICE = "earlier_slice"
_HOUR_NAME = "hour"
_HOUR_FORMAT = "%Y-%m-%dT%H:%M:%S"
_VARIABLE = "variable"
_RESULT_NAMES = "results"
_PLACE = "place"
_LISTED_VARIABLE = "listed_variable"
_HAS_ROWS = "has_rows"

# The folder that holds the files of each result, as the solve writes them.
_RESULT_FOLDERS: dict[str, str] = {
    str(csvs.result): csvs.folder for csvs in (*INVESTMENT_RESULT_CSVS, *OPERATIONS_RESULT_CSVS)
}


def _note_shared_name(row: dict[str, Any]) -> str:
    technologies = " and ".join(row[StagedResultCol.TECHNOLOGY])
    return (
        f"the name belongs to the technology types {technologies}, and the results name a "
        "component by its name alone, so each row of the name is left out"
    )


def _note_overlapping_slice(row: dict[str, Any]) -> str:
    return (
        f"the slice holds an hour that the slice {row[_EARLIER_SLICE]} also holds, so it is left "
        "out, and production leaves out each of its hours that no other slice holds"
    )


def _note_unknown_period(row: dict[str, Any]) -> str:
    return (
        f"the investment period is not a period of the series document, so the "
        f"{row[StagedResultCol.RESULT]} row has no year, and the results leave it out"
    )


def _note_missing_variable(row: dict[str, Any]) -> str:
    return (
        f"the directory that the solve wrote holds no file of {row[_RESULT_NAMES]} under "
        f"{row[_PLACE]}, so the results have no {row[_VARIABLE]}"
    )


_MISSING_VARIABLE_REPORT = SkipReport(
    pipeline=POWER_SYSTEMS_INVESTMENTS_TO_RESULTS,
    framework=Framework.POWER_SYSTEMS_INVESTMENTS,
    component=_RESULTS_COMPONENT,
    name_col=_RESULT_NAMES,
    reason="have no file in the directory that the solve wrote",
    counted_noun="result variable(s)",
    note=_note_missing_variable,
    listed=SkippedNames(column=_LISTED_VARIABLE, label=DROPPED_NAMES_LABEL),
)
_SHARED_NAME_REPORT = SkipReport(
    pipeline=POWER_SYSTEMS_INVESTMENTS_TO_RESULTS,
    framework=Framework.POWER_SYSTEMS_INVESTMENTS,
    component=_RESULTS_COMPONENT,
    name_col=StagedResultCol.COMPONENT,
    reason="belong to more than one technology type of the solve",
    counted_noun="component name(s)",
    note=_note_shared_name,
    attribute_col=StagedResultCol.COMPONENT,
    attribute_name=ResultsCsvCol.NAME,
)
_OVERLAPPING_SLICE_REPORT = SkipReport(
    pipeline=POWER_SYSTEMS_INVESTMENTS_TO_RESULTS,
    framework=Framework.POWER_SYSTEMS_INVESTMENTS,
    component=SeriesDocument.REPRESENTATIVE_DAY,
    name_col=_SLICE_NAME,
    reason="of the series document hold an hour that an earlier slice holds",
    counted_noun="slice(s)",
    note=_note_overlapping_slice,
    attribute_col=StagedResultCol.WEIGHT,
    attribute_name=SeriesDocument.WEIGHT,
)
_UNKNOWN_PERIOD_REPORT = SkipReport(
    pipeline=POWER_SYSTEMS_INVESTMENTS_TO_RESULTS,
    framework=Framework.POWER_SYSTEMS_INVESTMENTS,
    component=_RESULTS_COMPONENT,
    name_col=StagedResultCol.COMPONENT,
    reason="fall in an investment period that is not a period of the series document",
    counted_noun="capacity row(s)",
    note=_note_unknown_period,
    listed=SkippedNames(column=StagedResultCol.PERIOD, label="Periods"),
    attribute_col=StagedResultCol.PERIOD,
    attribute_name=ResultsCsvCol.TIME_INDEX,
)
_UNWEIGHTED_HOUR_REPORT = SkipReport(
    pipeline=POWER_SYSTEMS_INVESTMENTS_TO_RESULTS,
    framework=Framework.POWER_SYSTEMS_INVESTMENTS,
    component=ResultsCsvCol.DATE_TIME,
    name_col=_HOUR_NAME,
    reason="fall in no slice of the series document and take no weight in production",
    counted_noun="hour(s) of the solve",
    note="the hour falls in no slice of the series document, so production leaves it out",
    listed=SkippedNames(column=_HOUR_NAME, label="Hours"),
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
        operations = state.source_time_series[OPERATIONS_RESULTS_KEY]
        self._report_missing_variables(state, investment, operations)
        shared = self._choose_shared_names(investment, operations)
        is_unshared = ~pl.col(StagedResultCol.COMPONENT).is_in(shared)
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
        dated, _unknown = report_not_mapped(
            rows.join(period_years, on=StagedResultCol.PERIOD, how="left"),
            pl.col(StagedResultCol.YEAR).is_not_null(),
            _UNKNOWN_PERIOD_REPORT,
            self._recorder,
        )
        self._record(derivation)
        return _build_annual_results(dated, derivation)

    def _report_missing_variables(
        self, state: State, investment: pl.DataFrame, operations: pl.LazyFrame
    ) -> None:
        """Record each variable that no file of the solve states, and warn once for the lot."""
        staged = _list_staged_results(investment, operations)
        rows = [
            _build_variable_row(derivation, staged)
            for derivation in (_NEW_CAPACITY, _INSTALLED_CAPACITY, _PRODUCTION)
        ]
        rows.append(_build_objective_row(OBJECTIVE_KEY in state.source_topology))
        report_not_mapped(
            pl.DataFrame(rows), pl.col(_HAS_ROWS), _MISSING_VARIABLE_REPORT, self._recorder
        )

    def _choose_shared_names(self, investment: pl.DataFrame, operations: pl.LazyFrame) -> list[str]:
        """The component names that more than one technology type states; it reports each."""
        _unshared, shared = filter_component(
            _list_technologies_by_name(investment, operations),
            pl.col(StagedResultCol.TECHNOLOGY).list.len() == 1,
            _SHARED_NAME_REPORT,
            self._recorder,
        )
        return list(shared[StagedResultCol.COMPONENT])

    def _choose_hour_weights(self, weights: pl.DataFrame) -> pl.DataFrame:
        """The hours of each slice that overlaps no earlier slice; it reports the rest."""
        slices = _list_slices(weights)
        _kept, left_out = filter_component(
            slices.with_columns(
                pl.Series(_EARLIER_SLICE, _list_earlier_slices(slices), dtype=pl.Utf8)
            ),
            pl.col(_EARLIER_SLICE).is_null(),
            _OVERLAPPING_SLICE_REPORT,
            self._recorder,
        )
        return weights.join(left_out.select(_SLICE_KEYS), on=_SLICE_KEYS, how="anti")

    def _map_production(self, operations: pl.LazyFrame, weights: pl.DataFrame) -> pl.LazyFrame:
        # The solve writes a row for each hour of each slice, so an hour two slices hold has two.
        first_rows = operations.filter(pl.struct(_HOUR_ROW_KEYS).is_first_distinct())
        weighted = first_rows.join(weights.lazy(), on=StagedResultCol.SNAPSHOT, how="left")
        report_not_mapped(
            _list_solve_hours(weighted),
            pl.col(StagedResultCol.WEIGHT).is_not_null(),
            _UNWEIGHTED_HOUR_REPORT,
            self._recorder,
        )
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


def _list_staged_results(investment: pl.DataFrame, operations: pl.LazyFrame) -> set[str]:
    """Each result of the solve that the staged tables hold a row of."""
    results = pl.concat(
        [
            investment.lazy().select(StagedResultCol.RESULT),
            operations.select(StagedResultCol.RESULT),
        ]
    )
    return set(results.unique().collect()[StagedResultCol.RESULT])


def _build_variable_row(derivation: Derivation, staged: set[str]) -> dict[str, Any]:
    sources = [str(source) for source in derivation.sources]
    return _build_missing_row(
        derivation.destination,
        _join_names(sources),
        _RESULT_FOLDERS[sources[0]],
        has_rows=not staged.isdisjoint(sources),
    )


def _build_objective_row(has_rows: bool) -> dict[str, Any]:
    return _build_missing_row(
        ResultsVariable.OBJECTIVE, OBJECTIVE_VALUE_COLUMN, OPTIMIZER_STATS_CSV, has_rows=has_rows
    )


def _build_missing_row(
    variable: ResultsVariable, results: str, place: str, *, has_rows: bool
) -> dict[str, Any]:
    return {
        _VARIABLE: str(variable),
        _RESULT_NAMES: results,
        _PLACE: place,
        _LISTED_VARIABLE: f"{variable} ({place})",
        _HAS_ROWS: has_rows,
    }


def _join_names(names: list[str]) -> str:
    """The names in a sentence: "a", "a or b", or "a, b or c"."""
    if len(names) == 1:
        return names[0]
    return f"{', '.join(names[:-1])} or {names[-1]}"


def _list_technologies_by_name(investment: pl.DataFrame, operations: pl.LazyFrame) -> pl.DataFrame:
    """Each component name of the solve, with the technology types that state it."""
    columns = [StagedResultCol.COMPONENT, StagedResultCol.TECHNOLOGY]
    return (
        pl.concat([investment.lazy().select(columns), operations.select(columns)])
        .unique()
        .group_by(StagedResultCol.COMPONENT)
        .agg(pl.col(StagedResultCol.TECHNOLOGY).sort())
        .sort(StagedResultCol.COMPONENT)
        .collect()
    )


def _list_slices(weights: pl.DataFrame) -> pl.DataFrame:
    """Each slice of the series document, in the order the solve reads them, with its span."""
    return weights.group_by(_SLICE_KEYS, maintain_order=True).agg(
        pl.format(
            "{} of {}", pl.col(StagedResultCol.REPRESENTATIVE_DAY), pl.col(StagedResultCol.YEAR)
        )
        .first()
        .alias(_SLICE_NAME),
        pl.col(StagedResultCol.SNAPSHOT).min().alias(_FIRST_HOUR),
        pl.col(StagedResultCol.HOURS).sum(),
        pl.col(StagedResultCol.WEIGHT).first(),
    )


def _list_earlier_slices(slices: pl.DataFrame) -> list[str | None]:
    """For each slice, an earlier slice that it overlaps, or None where it overlaps none kept."""
    kept: list[Period] = []
    earlier_names: list[str | None] = []
    for row in slices.iter_rows(named=True):
        period = _build_period(row)
        earlier = next((other for other in kept if period.is_overlapping(other)), None)
        if earlier is None:
            kept.append(period)
        earlier_names.append(None if earlier is None else earlier.name)
    return earlier_names


def _build_period(row: dict[str, Any]) -> Period:
    """The span of a slice as a representative period, whose overlap rule the slices share."""
    return Period(
        name=row[_SLICE_NAME],
        first_hour=row[_FIRST_HOUR],
        hours=math.ceil(row[StagedResultCol.HOURS]),
        weight=row[StagedResultCol.WEIGHT],
    )


def _list_solve_hours(weighted: pl.LazyFrame) -> pl.DataFrame:
    """Each hour of the solve once, with its weight and the name a report gives it."""
    return (
        weighted.select(StagedResultCol.SNAPSHOT, StagedResultCol.WEIGHT)
        .unique(StagedResultCol.SNAPSHOT)
        .sort(StagedResultCol.SNAPSHOT)
        .with_columns(pl.col(StagedResultCol.SNAPSHOT).dt.strftime(_HOUR_FORMAT).alias(_HOUR_NAME))
        .collect()
    )


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
