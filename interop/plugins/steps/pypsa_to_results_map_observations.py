"""Turn a solved PyPSA network's outputs into the long-format results table.

The values it reads (dispatch, flow, load) are the results table itself, so this
step makes the one full read the pipeline rules otherwise forbid: it builds every
contribution as ``LazyFrame`` operations and does a single ``collect`` of the
bounded solved output. That is the documented exception to "never collect a
``source_time_series`` in full" (see ``docs/results-format.md``). The rule exists
for the pypsa-to-sienna path, where the values stream to an H5 sidecar and never
enter ``destination_tables``.
"""

from __future__ import annotations

from typing import ClassVar, NamedTuple

import polars as pl
from pydantic import BaseModel

from interop.core.extensions import (
    NETWORK_RECORD_NAME,
    ExtensionKind,
    record_for,
)
from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import ALL_COMPONENTS, Framework
from interop.plugins.shared.pypsa_constants import (
    PyPSAComponent,
    PyPSAGeneratorCol,
    PyPSALoadCol,
    PyPSASolvedAttr,
    PyPSAStorageUnitCol,
    PyPSATable,
    PyPSATimeSeriesCol,
)
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

# Timestamps land in the results schema's microsecond resolution; every piece
# casts to it so the vertical concat sees one uniform column type.
_RESULTS_TIMESTAMP_DTYPE = RESULTS_SCHEMA[ResultsCol.TIMESTAMP]

# Null category or component for variables that do not carry that dimension.
_NULL_UTF8 = pl.lit(None, dtype=pl.Utf8)

# What names the load side of the surplus join, whose other side is the capacity.
_LOAD_SUFFIX = "_load"

# Names the sidecar field the objective came from; the network file has no results column.
_OBJECTIVE_ATTRIBUTE = "objective"


class _CapacitySpec(NamedTuple):
    """A component table stating rated power, and the columns capacity is read from."""

    table: str
    component: str
    carrier_col: str
    p_nom_col: str


# The component tables stating rated power, each with the columns surplus and available
# capacity read it from.
_CAPACITY_SPECS = (
    _CapacitySpec(
        PyPSATable.GENERATORS,
        PyPSAComponent.GENERATOR,
        PyPSAGeneratorCol.CARRIER,
        PyPSAGeneratorCol.P_NOM,
    ),
    _CapacitySpec(
        PyPSATable.STORAGE_UNITS,
        PyPSAComponent.STORAGE_UNIT,
        PyPSAStorageUnitCol.CARRIER,
        PyPSAStorageUnitCol.P_NOM,
    ),
)


class PypsaToResultsMapObservations(TranslationStep):
    name: ClassVar[str] = "pypsa_to_results_map_observations"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def run(self, state: State, params: BaseModel | None) -> State:
        capacity = _capacity_by_carrier(state)
        pieces: list[pl.LazyFrame] = []
        pieces += self._map_dispatch(state)
        pieces += self._map_available_capacity(capacity)
        # Load maps before surplus, which names the load row as one of its sources, but its
        # own rows keep their place so the results table reads in the same order as before.
        load_pieces = self._map_load(state)
        pieces += self._map_surplus(state, capacity)
        pieces += self._map_flow(state)
        pieces += load_pieces
        pieces += self._map_price(state)
        pieces += self._map_snapshot_weight(state)
        pieces += self._map_objective(state)

        if pieces:
            results = (
                pl.concat(pieces, how="vertical")
                .with_columns(pl.col(ResultsCol.VARIABLE).cast(VARIABLE_DTYPE))
                .select(list(RESULTS_SCHEMA))
                .collect()
            )
        else:
            results = pl.DataFrame(schema=RESULTS_SCHEMA)
        state.destination_tables[RESULTS_TABLE_KEY] = results
        return state

    def _map_dispatch(self, state: State) -> list[pl.LazyFrame]:
        """Generation and storage active power, category = carrier, positive = into the bus."""
        specs = [
            (PyPSATable.GENERATORS, PyPSAComponent.GENERATOR, PyPSAGeneratorCol.CARRIER),
            (PyPSATable.STORAGE_UNITS, PyPSAComponent.STORAGE_UNIT, PyPSAStorageUnitCol.CARRIER),
        ]
        pieces: list[pl.LazyFrame] = []
        sources: list[SourceField] = []
        for table, component, carrier_col in specs:
            ts = state.source_time_series.get((table, PyPSASolvedAttr.DISPATCH))
            topology = state.source_topology.get(table)
            if ts is None or topology is None:
                continue
            carriers = topology.select(
                [pl.col("name"), pl.col(carrier_col).alias(ResultsCol.CATEGORY)]
            )
            pieces.append(
                ts.join(
                    carriers,
                    left_on=PyPSATimeSeriesCol.COMPONENT,
                    right_on="name",
                    how="left",
                ).select(
                    _build_piece_columns(
                        ResultsVariable.DISPATCH,
                        category=pl.col(ResultsCol.CATEGORY),
                    )
                )
            )
            sources.append(
                SourceField(
                    framework=Framework.PYPSA,
                    component=component,
                    name=ALL_COMPONENTS,
                    attribute=PyPSASolvedAttr.DISPATCH,
                    unit=ResultsUnit.MEGAWATT,
                )
            )
        if pieces:
            self._emit(
                ResultsVariable.DISPATCH,
                sources,
                "generators_t.p and storage_units_t.p -> dispatch (MW into bus); "
                "category = carrier",
            )
        return pieces

    def _map_available_capacity(self, capacity: _CapacityByCarrier | None) -> list[pl.LazyFrame]:
        """Installed capacity by carrier, held flat across every snapshot, component null."""
        if capacity is None:
            return []
        piece = capacity.per_snapshot.select(
            [
                pl.lit(str(ResultsVariable.AVAILABLE_CAPACITY)).alias(ResultsCol.VARIABLE),
                _NULL_UTF8.alias(ResultsCol.COMPONENT),
                pl.col(ResultsCol.CATEGORY).alias(ResultsCol.CATEGORY),
                pl.col(PyPSATimeSeriesCol.SNAPSHOT)
                .cast(_RESULTS_TIMESTAMP_DTYPE)
                .alias(ResultsCol.TIMESTAMP),
                pl.col(ResultsCol.VALUE).cast(pl.Float64).alias(ResultsCol.VALUE),
            ]
        )
        self._emit(
            ResultsVariable.AVAILABLE_CAPACITY,
            capacity.sources,
            "sum of generators.p_nom and storage_units.p_nom by carrier, held flat across "
            "snapshots -> available_capacity; category = carrier (p_max_pu / p_nom_opt deferred)",
        )
        return [piece]

    def _map_surplus(self, state: State, capacity: _CapacityByCarrier | None) -> list[pl.LazyFrame]:
        """What the whole system could still cover: all its capacity less the load on it."""
        loads = state.source_time_series.get((PyPSATable.LOADS, PyPSALoadCol.P_SET))
        if capacity is None or loads is None:
            return []
        piece = capacity.total().join(_total_by_snapshot(loads), how="cross", suffix=_LOAD_SUFFIX)
        self._emit(
            ResultsVariable.SURPLUS,
            [
                _results_source(ResultsVariable.AVAILABLE_CAPACITY),
                _results_source(ResultsVariable.LOAD),
            ],
            "available_capacity summed across categories minus load at the same timestamp "
            "-> surplus (MW the system could still cover)",
        )
        return [piece.select(_surplus_columns())]

    def _map_flow(self, state: State) -> list[pl.LazyFrame]:
        """Line and link active power at bus0, category null, positive = bus0 -> bus1."""
        specs = [
            (PyPSATable.LINES, PyPSAComponent.LINE),
            (PyPSATable.LINKS, PyPSAComponent.LINK),
        ]
        pieces: list[pl.LazyFrame] = []
        sources: list[SourceField] = []
        for table, component in specs:
            ts = state.source_time_series.get((table, PyPSASolvedAttr.FLOW))
            if ts is None:
                continue
            pieces.append(
                ts.select(_build_piece_columns(ResultsVariable.FLOW, category=_NULL_UTF8))
            )
            sources.append(
                SourceField(
                    framework=Framework.PYPSA,
                    component=component,
                    name=ALL_COMPONENTS,
                    attribute=PyPSASolvedAttr.FLOW,
                    unit=ResultsUnit.MEGAWATT,
                )
            )
        if pieces:
            self._emit(
                ResultsVariable.FLOW,
                sources,
                "lines_t.p0 and links_t.p0 -> flow (MW from bus0 towards bus1)",
            )
        return pieces

    def _map_load(self, state: State) -> list[pl.LazyFrame]:
        """Load active power set point, category null, positive = consumption at the bus."""
        ts = state.source_time_series.get((PyPSATable.LOADS, PyPSALoadCol.P_SET))
        if ts is None:
            return []
        self._emit(
            ResultsVariable.LOAD,
            [_load_source()],
            "loads_t.p_set -> load (MW consumption at bus)",
        )
        return [ts.select(_build_piece_columns(ResultsVariable.LOAD, category=_NULL_UTF8))]

    def _map_price(self, state: State) -> list[pl.LazyFrame]:
        """Bus marginal price, category null, positive = cost of one more MWh at the bus."""
        ts = state.source_time_series.get((PyPSATable.BUSES, PyPSASolvedAttr.MARGINAL_PRICE))
        if ts is None:
            return []
        self._emit(
            ResultsVariable.PRICE,
            [
                SourceField(
                    framework=Framework.PYPSA,
                    component=PyPSAComponent.BUS,
                    name=ALL_COMPONENTS,
                    attribute=PyPSASolvedAttr.MARGINAL_PRICE,
                    unit=ResultsUnit.COST_PER_MEGAWATT_HOUR,
                )
            ],
            "buses_t.marginal_price -> price (cost per MWh at the bus)",
        )
        return [ts.select(_build_piece_columns(ResultsVariable.PRICE, category=_NULL_UTF8))]

    def _map_snapshot_weight(self, state: State) -> list[pl.LazyFrame]:
        """Per-snapshot weighting (hours represented), component and category null."""
        ts = state.source_time_series.get(
            (PyPSATable.SNAPSHOTS, PyPSASolvedAttr.SNAPSHOT_WEIGHTING)
        )
        if ts is None:
            return []
        self._emit(
            ResultsVariable.SNAPSHOT_WEIGHT,
            [
                SourceField(
                    framework=Framework.PYPSA,
                    component=PyPSATable.SNAPSHOTS,
                    name=ALL_COMPONENTS,
                    attribute=PyPSASolvedAttr.SNAPSHOT_WEIGHTING,
                    unit=ResultsUnit.HOUR,
                )
            ],
            "snapshot_weightings.objective -> snapshot_weight (hours the snapshot represents)",
        )
        return [
            ts.select(
                _build_piece_columns(
                    ResultsVariable.SNAPSHOT_WEIGHT,
                    category=_NULL_UTF8,
                    component=_NULL_UTF8,
                )
            )
        ]

    def _map_objective(self, state: State) -> list[pl.LazyFrame]:
        """Solve objective as a single scalar row, all dimensions null."""
        record = record_for(state.source_extensions, ExtensionKind.NETWORK, NETWORK_RECORD_NAME)
        # The record is there for an unsolved network too: only the objective field itself
        # says the network was solved.
        if record is None or record.objective is None:
            return []
        objective = record.objective
        self._emit(
            ResultsVariable.OBJECTIVE,
            [
                SourceField(
                    framework=Framework.PYPSA,
                    component=PyPSATable.NETWORK,
                    name=ALL_COMPONENTS,
                    attribute=_OBJECTIVE_ATTRIBUTE,
                    unit=ResultsUnit.COST,
                )
            ],
            "network objective -> objective (single scalar row, all dimensions null)",
        )
        return [
            pl.LazyFrame(
                {
                    ResultsCol.VARIABLE: [str(ResultsVariable.OBJECTIVE)],
                    ResultsCol.COMPONENT: [None],
                    ResultsCol.CATEGORY: [None],
                    ResultsCol.TIMESTAMP: [None],
                    ResultsCol.VALUE: [objective],
                },
                schema={
                    ResultsCol.VARIABLE: pl.Utf8,
                    ResultsCol.COMPONENT: pl.Utf8,
                    ResultsCol.CATEGORY: pl.Utf8,
                    ResultsCol.TIMESTAMP: _RESULTS_TIMESTAMP_DTYPE,
                    ResultsCol.VALUE: pl.Float64,
                },
            )
        ]

    def _emit(self, variable: ResultsVariable, sources: list[SourceField], derivation: str) -> None:
        self._recorder.append(
            TranslationEvent(
                kind=EventKind.VALUE_DERIVED,
                sources=sources,
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


def _results_source(variable: ResultsVariable) -> SourceField:
    """A results row this step already emitted, so a row derived from it names it directly.

    Mirrors what ``_emit`` writes as that row's destination, which is what keeps a value
    flowing X -> Y -> Z reported as two hops rather than one.
    """
    return SourceField(
        framework=Framework.RESULTS,
        component=RESULTS_TABLE_KEY,
        name=str(variable),
        attribute=ResultsCol.VARIABLE,
        unit=VARIABLE_UNIT[variable],
    )


class _CapacityByCarrier(NamedTuple):
    """Installed capacity by carrier, and where the numbers came from.

    ``by_carrier`` is one row per carrier; ``per_snapshot`` is that held flat across the
    horizon, which is the shape ``available_capacity`` reports. Capacity does not vary over
    the snapshots, so the system total is a sum over the carriers alone.
    """

    by_carrier: pl.LazyFrame
    per_snapshot: pl.LazyFrame
    sources: list[SourceField]

    def total(self) -> pl.LazyFrame:
        """The one number the whole fleet adds up to, in the results value column."""
        return self.by_carrier.select(
            pl.col(ResultsCol.VALUE).sum().alias(PyPSATimeSeriesCol.VALUE)
        )


def _capacity_by_carrier(state: State) -> _CapacityByCarrier | None:
    weightings = state.source_time_series.get(
        (PyPSATable.SNAPSHOTS, PyPSASolvedAttr.SNAPSHOT_WEIGHTING)
    )
    if weightings is None:
        return None
    capacities, sources = _installed_capacities(state)
    if not capacities:
        return None
    by_carrier = (
        pl.concat(capacities, how="vertical")
        .group_by(ResultsCol.CATEGORY)
        .agg(pl.col(ResultsCol.VALUE).sum())
    )
    snapshots = weightings.select(pl.col(PyPSATimeSeriesCol.SNAPSHOT)).unique()
    return _CapacityByCarrier(by_carrier, by_carrier.join(snapshots, how="cross"), sources)


def _installed_capacities(state: State) -> tuple[list[pl.LazyFrame], list[SourceField]]:
    """One (carrier, capacity) frame per component table that states rated power."""
    capacities: list[pl.LazyFrame] = []
    sources: list[SourceField] = []
    for spec in _CAPACITY_SPECS:
        topology = state.source_topology.get(spec.table)
        if topology is None:
            continue
        capacities.append(
            topology.select(
                [
                    pl.col(spec.carrier_col).alias(ResultsCol.CATEGORY),
                    pl.col(spec.p_nom_col).alias(ResultsCol.VALUE),
                ]
            )
        )
        sources.append(
            SourceField(
                framework=Framework.PYPSA,
                component=spec.component,
                name=ALL_COMPONENTS,
                attribute=spec.p_nom_col,
                unit=ResultsUnit.MEGAWATT,
            )
        )
    return capacities, sources


def _total_by_snapshot(frame: pl.LazyFrame) -> pl.LazyFrame:
    return frame.group_by(PyPSATimeSeriesCol.SNAPSHOT).agg(
        pl.col(PyPSATimeSeriesCol.VALUE).sum().alias(PyPSATimeSeriesCol.VALUE)
    )


def _load_source() -> SourceField:
    return SourceField(
        framework=Framework.PYPSA,
        component=PyPSAComponent.LOAD,
        name=ALL_COMPONENTS,
        attribute=PyPSALoadCol.P_SET,
        unit=ResultsUnit.MEGAWATT,
    )


def _surplus_columns() -> list[pl.Expr]:
    """A system-level row: both the component and the category it aggregates over are null."""
    headroom = pl.col(PyPSATimeSeriesCol.VALUE) - pl.col(PyPSATimeSeriesCol.VALUE + _LOAD_SUFFIX)
    return _build_piece_columns(
        ResultsVariable.SURPLUS,
        category=_NULL_UTF8,
        component=_NULL_UTF8,
        value=headroom,
    )


def _build_piece_columns(
    variable: ResultsVariable,
    *,
    category: pl.Expr,
    component: pl.Expr | None = None,
    value: pl.Expr | None = None,
) -> list[pl.Expr]:
    """Project a staged (snapshot, component, value) frame onto the pre-Enum results columns.

    Every piece shares one column set and dtype so the vertical concat is uniform;
    the ``variable`` column is cast to the results Enum once, after the concat.
    """
    component_expr = pl.col(PyPSATimeSeriesCol.COMPONENT) if component is None else component
    value_expr = pl.col(PyPSATimeSeriesCol.VALUE) if value is None else value
    return [
        pl.lit(str(variable)).alias(ResultsCol.VARIABLE),
        component_expr.alias(ResultsCol.COMPONENT),
        category.alias(ResultsCol.CATEGORY),
        pl.col(PyPSATimeSeriesCol.SNAPSHOT)
        .cast(_RESULTS_TIMESTAMP_DTYPE)
        .alias(ResultsCol.TIMESTAMP),
        value_expr.cast(pl.Float64).alias(ResultsCol.VALUE),
    ]
