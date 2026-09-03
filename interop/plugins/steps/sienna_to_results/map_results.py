"""Turn a Sienna solve output into the long-format results table.

An earlier step (the reused Sienna to PyPSA mapping) has already recovered the hub
names and carriers into the ``generators`` and ``storage_units`` tables. This step
reads the staged solve series, looks up each dispatch row's carrier from those tables,
and normalises every value to the results-format conventions: dispatch positive into
the bus, load positive for consumption, flow positive from bus0 to bus1, storage as
output minus input, and HVDC flow rescaled from per-unit. It builds one row per
observation and keeps the work lazy until a single collect of the finished table.

This step only adds the ``results`` table; it leaves the tables the earlier mapping
step produced untouched. The results sink writes just the ``results`` table, so the
output is ``results.parquet`` regardless of what else is staged.
"""

from __future__ import annotations

from typing import ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import Framework, StagedTimeSeriesCol
from interop.plugins.shared.pypsa_constants import (
    PyPSADestinationTable,
    PyPSAGeneratorCol,
    PyPSAStorageUnitCol,
)
from interop.plugins.shared.pypsa_time_series import series_components
from interop.plugins.shared.results_constants import (
    RESULTS_SCHEMA,
    RESULTS_TABLE_KEY,
    VARIABLE_UNIT,
    ResultsCol,
    ResultsUnit,
    ResultsVariable,
)
from interop.plugins.shared.sienna_results_constants import (
    HVDC_WIDE_SCALE,
    HYDRO_DISPATCH_KEY,
    LINE_FLOW_KEY,
    LINK_FLOW_KEY,
    LOAD_KEY,
    OBJECTIVE_VALUE_FIELD,
    RESULTS_OBJECTIVE_KEY,
    STORAGE_INPUT_KEY,
    STORAGE_OUTPUT_KEY,
    THERMAL_DISPATCH_KEY,
    ResultSeriesKey,
)
from interop.ports.outbound.reporting import (
    DestinationField,
    EventKind,
    SourceField,
    TranslationEvent,
)

_STORAGE_OUT_COL = "_storage_out"
_STORAGE_IN_COL = "_storage_in"

_DISPATCH_FROM_ACTIVE_POWER = "ActivePowerVariable -> dispatch"
_DISPATCH_FROM_STORAGE = "ActivePowerOutVariable - ActivePowerInVariable -> dispatch"
_FLOW_FROM_FLOW = "FlowActivePowerVariable -> flow"
_FLOW_FROM_SCALED_FLOW = "FlowActivePowerVariable / system base -> flow"
_LOAD_FROM_PARAMETER = "ActivePowerTimeSeriesParameter -> load (positive = consumption)"
_OBJECTIVE_FROM_STATS = "optimizer_stats.objective_value -> objective"

_RESULT_COLUMNS = [
    ResultsCol.VARIABLE,
    ResultsCol.COMPONENT,
    ResultsCol.CATEGORY,
    ResultsCol.TIMESTAMP,
    ResultsCol.VALUE,
]


class SiennaResultsToResultsFormat(TranslationStep):
    name: ClassVar[str] = "sienna_results_to_results_format"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def run(self, state: State, params: BaseModel | None) -> State:
        carrier_lookup = _build_carrier_lookup(state)
        frames: list[pl.LazyFrame] = []
        frames += self._map_dispatch(state, THERMAL_DISPATCH_KEY, carrier_lookup)
        frames += self._map_dispatch(state, HYDRO_DISPATCH_KEY, carrier_lookup)
        frames += self._map_storage_dispatch(state, carrier_lookup)
        frames += self._map_flow(state, LINE_FLOW_KEY, scale=1.0, derivation=_FLOW_FROM_FLOW)
        frames += self._map_flow(
            state, LINK_FLOW_KEY, scale=1.0 / HVDC_WIDE_SCALE, derivation=_FLOW_FROM_SCALED_FLOW
        )
        frames += self._map_load(state)
        frames += self._map_objective(state)

        state.destination_tables[RESULTS_TABLE_KEY] = _assemble_results_table(frames)
        return state

    def _map_dispatch(
        self,
        state: State,
        key: ResultSeriesKey,
        carrier_lookup: pl.LazyFrame | None,
    ) -> list[pl.LazyFrame]:
        frame = state.source_time_series.get(key)
        if frame is None or carrier_lookup is None:
            return []
        self._record(
            series_components(frame),
            sienna_type=key.owner_type,
            series=key.series_name,
            variable=ResultsVariable.DISPATCH,
            derivation=_DISPATCH_FROM_ACTIVE_POWER,
        )
        return [_build_dispatch_frame(frame, carrier_lookup, pl.col(StagedTimeSeriesCol.VALUE))]

    def _map_storage_dispatch(
        self, state: State, carrier_lookup: pl.LazyFrame | None
    ) -> list[pl.LazyFrame]:
        output = state.source_time_series.get(STORAGE_OUTPUT_KEY)
        if output is None or carrier_lookup is None:
            return []
        net = output.select(
            [
                StagedTimeSeriesCol.SNAPSHOT,
                StagedTimeSeriesCol.COMPONENT,
                pl.col(StagedTimeSeriesCol.VALUE).alias(_STORAGE_OUT_COL),
            ]
        )
        value_expr = pl.col(_STORAGE_OUT_COL)
        input_frame = state.source_time_series.get(STORAGE_INPUT_KEY)
        if input_frame is not None:
            net = net.join(
                input_frame.select(
                    [
                        StagedTimeSeriesCol.SNAPSHOT,
                        StagedTimeSeriesCol.COMPONENT,
                        pl.col(StagedTimeSeriesCol.VALUE).alias(_STORAGE_IN_COL),
                    ]
                ),
                on=[StagedTimeSeriesCol.SNAPSHOT, StagedTimeSeriesCol.COMPONENT],
                how="left",
            )
            value_expr = pl.col(_STORAGE_OUT_COL) - pl.col(_STORAGE_IN_COL).fill_null(0.0)
        self._record(
            series_components(output),
            sienna_type=STORAGE_OUTPUT_KEY.owner_type,
            series=STORAGE_OUTPUT_KEY.series_name,
            variable=ResultsVariable.DISPATCH,
            derivation=_DISPATCH_FROM_STORAGE,
        )
        return [_build_dispatch_frame(net, carrier_lookup, value_expr)]

    def _map_flow(
        self, state: State, key: ResultSeriesKey, *, scale: float, derivation: str
    ) -> list[pl.LazyFrame]:
        frame = state.source_time_series.get(key)
        if frame is None:
            return []
        self._record(
            series_components(frame),
            sienna_type=key.owner_type,
            series=key.series_name,
            variable=ResultsVariable.FLOW,
            derivation=derivation,
        )
        return [
            _build_frame_without_category(
                frame, ResultsVariable.FLOW, pl.col(StagedTimeSeriesCol.VALUE) * scale
            )
        ]

    def _map_load(self, state: State) -> list[pl.LazyFrame]:
        frame = state.source_time_series.get(LOAD_KEY)
        if frame is None:
            return []
        self._record(
            series_components(frame),
            sienna_type=LOAD_KEY.owner_type,
            series=LOAD_KEY.series_name,
            variable=ResultsVariable.LOAD,
            derivation=_LOAD_FROM_PARAMETER,
        )
        return [
            _build_frame_without_category(
                frame, ResultsVariable.LOAD, pl.col(StagedTimeSeriesCol.VALUE)
            )
        ]

    def _map_objective(self, state: State) -> list[pl.LazyFrame]:
        frame = state.source_topology.get(RESULTS_OBJECTIVE_KEY)
        if frame is None:
            return []
        self._recorder.append(
            TranslationEvent(
                kind=EventKind.VALUE_DERIVED,
                sources=[
                    SourceField(
                        framework=Framework.SIENNA,
                        component="optimizer_stats",
                        name="objective_value",
                    )
                ],
                destinations=[
                    DestinationField(
                        framework=Framework.PYPSA,
                        component=ResultsVariable.OBJECTIVE,
                        name=ResultsVariable.OBJECTIVE,
                        unit=ResultsUnit.COST,
                    )
                ],
                derivation=_OBJECTIVE_FROM_STATS,
            )
        )
        return [
            frame.select(
                [
                    pl.lit(ResultsVariable.OBJECTIVE.value).alias(ResultsCol.VARIABLE),
                    pl.lit(None, dtype=pl.Utf8).alias(ResultsCol.COMPONENT),
                    pl.lit(None, dtype=pl.Utf8).alias(ResultsCol.CATEGORY),
                    pl.lit(None, dtype=pl.Datetime("us")).alias(ResultsCol.TIMESTAMP),
                    pl.col(OBJECTIVE_VALUE_FIELD).cast(pl.Float64).alias(ResultsCol.VALUE),
                ]
            )
        ]

    def _record(
        self,
        components: list[str],
        *,
        sienna_type: str,
        series: str,
        variable: ResultsVariable,
        derivation: str,
    ) -> None:
        unit = VARIABLE_UNIT[variable]
        for component in components:
            self._recorder.append(
                TranslationEvent(
                    kind=EventKind.VALUE_DERIVED,
                    sources=[
                        SourceField(
                            framework=Framework.SIENNA,
                            component=sienna_type,
                            name=component,
                            attribute=series,
                        )
                    ],
                    destinations=[
                        DestinationField(
                            framework=Framework.PYPSA,
                            component=variable,
                            name=component,
                            attribute=ResultsCol.VALUE,
                            unit=unit,
                        )
                    ],
                    derivation=derivation,
                )
            )


def _build_carrier_lookup(state: State) -> pl.LazyFrame | None:
    frames: list[pl.LazyFrame] = []
    generators = state.destination_tables.get(PyPSADestinationTable.GENERATORS)
    if generators is not None:
        frames.append(
            generators.lazy().select(
                [
                    pl.col(PyPSAGeneratorCol.NAME).alias(StagedTimeSeriesCol.COMPONENT),
                    pl.col(PyPSAGeneratorCol.CARRIER).alias(ResultsCol.CATEGORY),
                ]
            )
        )
    storage_units = state.destination_tables.get(PyPSADestinationTable.STORAGE_UNITS)
    if storage_units is not None:
        frames.append(
            storage_units.lazy().select(
                [
                    pl.col(PyPSAStorageUnitCol.NAME).alias(StagedTimeSeriesCol.COMPONENT),
                    pl.col(PyPSAStorageUnitCol.CARRIER).alias(ResultsCol.CATEGORY),
                ]
            )
        )
    if not frames:
        return None
    return pl.concat(frames)


def _build_dispatch_frame(
    frame: pl.LazyFrame, carrier_lookup: pl.LazyFrame, value_expr: pl.Expr
) -> pl.LazyFrame:
    return frame.join(carrier_lookup, on=StagedTimeSeriesCol.COMPONENT, how="left").select(
        [
            pl.lit(ResultsVariable.DISPATCH.value).alias(ResultsCol.VARIABLE),
            pl.col(StagedTimeSeriesCol.COMPONENT).alias(ResultsCol.COMPONENT),
            pl.col(ResultsCol.CATEGORY),
            pl.col(StagedTimeSeriesCol.SNAPSHOT).alias(ResultsCol.TIMESTAMP),
            value_expr.cast(pl.Float64).alias(ResultsCol.VALUE),
        ]
    )


def _build_frame_without_category(
    frame: pl.LazyFrame, variable: ResultsVariable, value_expr: pl.Expr
) -> pl.LazyFrame:
    return frame.select(
        [
            pl.lit(variable.value).alias(ResultsCol.VARIABLE),
            pl.col(StagedTimeSeriesCol.COMPONENT).alias(ResultsCol.COMPONENT),
            pl.lit(None, dtype=pl.Utf8).alias(ResultsCol.CATEGORY),
            pl.col(StagedTimeSeriesCol.SNAPSHOT).alias(ResultsCol.TIMESTAMP),
            value_expr.cast(pl.Float64).alias(ResultsCol.VALUE),
        ]
    )


def _assemble_results_table(frames: list[pl.LazyFrame]) -> pl.DataFrame:
    if not frames:
        return pl.DataFrame(schema=RESULTS_SCHEMA)
    combined = pl.concat(frames, how="vertical").collect()
    return combined.select(_RESULT_COLUMNS).cast(RESULTS_SCHEMA)  # type: ignore[arg-type]
