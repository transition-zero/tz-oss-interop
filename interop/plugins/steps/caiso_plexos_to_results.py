"""Turn CAISO's staged stack-model CSV into the long-format results table."""

from __future__ import annotations

from typing import ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.caiso_plexos_constants import (
    APPENDIX_FUEL_TO_CATEGORY,
    APPENDIX_MONTH_COLUMNS,
    AVAILABILITY_CATEGORIES,
    CAISO_APPENDIX_TABLE,
    CAISO_STACK_TABLE,
    CHARGING_LOAD_YES,
    DISPATCH_CATEGORIES,
    IN_SCOPE_MONTHS,
    STACK_MODEL_YEAR,
    CaisoAppendixCol,
    CaisoStackCol,
)
from interop.plugins.shared.constants import Framework
from interop.plugins.shared.results_constants import (
    RESULTS_SCHEMA,
    RESULTS_TABLE_KEY,
    VARIABLE_DTYPE,
    VARIABLE_UNIT,
    ResultsCol,
    ResultsUnit,
    ResultsVariable,
)
from interop.ports.outbound.reporting import (
    DestinationField,
    EventKind,
    SourceField,
    TranslationEvent,
)

_RESULTS_TIMESTAMP_DTYPE = RESULTS_SCHEMA[ResultsCol.TIMESTAMP]
_NULL_UTF8 = pl.lit(None, dtype=pl.Utf8)

# Working column names for the computed timestamp and the unpivoted pairs.
_TIMESTAMP = "timestamp"
_CATEGORY = "category"
_VALUE = "value"
_MONTH_HEADER = "month_header"


class CaisoPlexosToResults(TranslationStep):
    name: ClassVar[str] = "caiso_plexos_to_results"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def run(self, state: State, params: BaseModel | None) -> State:
        pieces: list[pl.DataFrame] = []
        stack = state.source_topology.get(CAISO_STACK_TABLE)
        if stack is not None:
            pieces += self._map_stack(stack.collect())
        appendix = state.source_topology.get(CAISO_APPENDIX_TABLE)
        if appendix is not None:
            pieces += self._map_appendix(appendix.collect())
        state.destination_tables[RESULTS_TABLE_KEY] = _assemble_results(pieces)
        return state

    def _map_stack(self, stack: pl.DataFrame) -> list[pl.DataFrame]:
        """Record and build available_capacity, dispatch, load and surplus (with-charging)."""
        self._record_stack_mappings()
        charging = _with_hour_ending_timestamp(
            stack.filter(pl.col(CaisoStackCol.CHARGING_LOAD) == CHARGING_LOAD_YES)
        )
        return _stack_rows(charging)

    def _map_appendix(self, appendix: pl.DataFrame) -> list[pl.DataFrame]:
        """Record and build the appendix's monthly NQC capacity by fuel, May to September only."""
        self._emit(
            ResultsVariable.AVAILABLE_CAPACITY,
            CAISO_APPENDIX_TABLE,
            [CaisoAppendixCol.FUEL_TYPE],
            "appendix monthly NQC capacity by fuel -> available_capacity at month start; "
            "May to September only; Biogas + Biomass + Geothermal -> Other Renewables, "
            "Hybrid -> Other, Net Import Limit -> Imports, Total dropped",
        )
        return [_appendix_rows(appendix)]

    def _record_stack_mappings(self) -> None:
        self._emit(
            ResultsVariable.AVAILABLE_CAPACITY,
            CAISO_STACK_TABLE,
            list(AVAILABILITY_CATEGORIES),
            "eight NQC availability columns -> available_capacity; category = column name; "
            "with-charging scenario; hour-ending PDT -> naive start-of-interval timestamp "
            "(day + HE - 1 hours), aligned to PyPSA snapshots",
        )
        self._emit(
            ResultsVariable.DISPATCH,
            CAISO_STACK_TABLE,
            list(DISPATCH_CATEGORIES),
            "Battery Storage and Demand Response optimised dispatch -> dispatch; "
            "component = category = column name",
        )
        for variable, column in (
            (ResultsVariable.LOAD, CaisoStackCol.LOAD),
            (ResultsVariable.SURPLUS, CaisoStackCol.SURPLUS),
        ):
            self._emit(
                variable,
                CAISO_STACK_TABLE,
                [column],
                f"{column!r} -> {variable} (system total; component and category null)",
            )

    def _emit(
        self,
        variable: ResultsVariable,
        source_table: str,
        source_columns: list[str],
        derivation: str,
    ) -> None:
        self._recorder.append(
            TranslationEvent(
                kind=EventKind.VALUE_DERIVED,
                sources=[
                    SourceField(
                        framework=Framework.CAISO_PLEXOS,
                        component=source_table,
                        name=column,
                        unit=ResultsUnit.MEGAWATT,
                    )
                    for column in source_columns
                ],
                destinations=[
                    DestinationField(
                        framework=Framework.RESULTS,
                        component=RESULTS_TABLE_KEY,
                        name=str(variable),
                        attribute=ResultsCol.VARIABLE,
                        unit=VARIABLE_UNIT[variable],
                    )
                ],
                derivation=derivation,
            )
        )


def _assemble_results(pieces: list[pl.DataFrame]) -> pl.DataFrame:
    if not pieces:
        return pl.DataFrame(schema=RESULTS_SCHEMA)
    return (
        pl.concat(pieces, how="vertical")
        .with_columns(pl.col(ResultsCol.VARIABLE).cast(VARIABLE_DTYPE))
        .select(list(RESULTS_SCHEMA))
    )


def _stack_rows(charging: pl.DataFrame) -> list[pl.DataFrame]:
    return [
        _availability_rows(charging),
        _dispatch_rows(charging),
        _system_rows(charging, ResultsVariable.LOAD, CaisoStackCol.LOAD),
        _system_rows(charging, ResultsVariable.SURPLUS, CaisoStackCol.SURPLUS),
    ]


def _availability_rows(charging: pl.DataFrame) -> pl.DataFrame:
    long = charging.select([_TIMESTAMP, *AVAILABILITY_CATEGORIES]).unpivot(
        index=_TIMESTAMP, variable_name=_CATEGORY, value_name=_VALUE
    )
    return _project_to_results_columns(
        long,
        variable=ResultsVariable.AVAILABLE_CAPACITY,
        component=_NULL_UTF8,
        category=pl.col(_CATEGORY),
    )


def _dispatch_rows(charging: pl.DataFrame) -> pl.DataFrame:
    # CAISO names dispatch by category, so it never matches PyPSA's per-generator
    # component: in v1 dispatch surfaces as a coverage gap, not a value diff.
    long = charging.select([_TIMESTAMP, *DISPATCH_CATEGORIES]).unpivot(
        index=_TIMESTAMP, variable_name=_CATEGORY, value_name=_VALUE
    )
    return _project_to_results_columns(
        long,
        variable=ResultsVariable.DISPATCH,
        component=pl.col(_CATEGORY),
        category=pl.col(_CATEGORY),
    )


def _system_rows(charging: pl.DataFrame, variable: ResultsVariable, column: str) -> pl.DataFrame:
    frame = charging.select([_TIMESTAMP, pl.col(column).alias(_VALUE)])
    return _project_to_results_columns(
        frame, variable=variable, component=_NULL_UTF8, category=_NULL_UTF8
    )


def _appendix_rows(appendix: pl.DataFrame) -> pl.DataFrame:
    return _project_to_results_columns(
        _appendix_capacity_by_month(appendix),
        variable=ResultsVariable.AVAILABLE_CAPACITY,
        component=_NULL_UTF8,
        category=pl.col(_CATEGORY),
    )


def _appendix_capacity_by_month(appendix: pl.DataFrame) -> pl.DataFrame:
    """Roll finer appendix fuels up to categories and stamp each in-scope month's first day."""
    in_scope_headers = [APPENDIX_MONTH_COLUMNS[month] for month in IN_SCOPE_MONTHS]
    header_to_month = {APPENDIX_MONTH_COLUMNS[month]: month for month in IN_SCOPE_MONTHS}
    return (
        appendix.unpivot(
            index=CaisoAppendixCol.FUEL_TYPE,
            on=in_scope_headers,
            variable_name=_MONTH_HEADER,
            value_name=_VALUE,
        )
        .with_columns(
            pl.col(CaisoAppendixCol.FUEL_TYPE)
            .replace_strict(APPENDIX_FUEL_TO_CATEGORY, default=None)
            .alias(_CATEGORY),
            pl.col(_MONTH_HEADER).replace_strict(header_to_month, return_dtype=pl.Int8),
        )
        .filter(pl.col(_CATEGORY).is_not_null())
        .group_by([_CATEGORY, _MONTH_HEADER])
        .agg(pl.col(_VALUE).sum())
        .with_columns(pl.datetime(STACK_MODEL_YEAR, pl.col(_MONTH_HEADER), 1).alias(_TIMESTAMP))
    )


def _with_hour_ending_timestamp(charging: pl.DataFrame) -> pl.DataFrame:
    # Subtract one hour so CAISO's hour-ending label becomes a start-of-interval
    # timestamp that lines up with PyPSA's start-of-interval snapshots.
    start_of_interval = pl.datetime(
        year=STACK_MODEL_YEAR,
        month=pl.col(CaisoStackCol.MONTH),
        day=pl.col(CaisoStackCol.DAY),
    ) + pl.duration(hours=pl.col(CaisoStackCol.HOUR_ENDING) - 1)
    return charging.with_columns(start_of_interval.alias(_TIMESTAMP))


def _project_to_results_columns(
    frame: pl.DataFrame,
    *,
    variable: ResultsVariable,
    component: pl.Expr,
    category: pl.Expr,
) -> pl.DataFrame:
    """Project a frame carrying a timestamp and a value column onto the pre-Enum results columns."""
    return frame.select(
        [
            pl.lit(str(variable)).alias(ResultsCol.VARIABLE),
            component.alias(ResultsCol.COMPONENT),
            category.alias(ResultsCol.CATEGORY),
            pl.col(_TIMESTAMP).cast(_RESULTS_TIMESTAMP_DTYPE).alias(ResultsCol.TIMESTAMP),
            pl.col(_VALUE).cast(pl.Float64).alias(ResultsCol.VALUE),
        ]
    )
