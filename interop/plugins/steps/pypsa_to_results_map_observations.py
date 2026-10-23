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
from interop.plugins.shared.pypsa_annual_results import (
    PypsaAnnualResultsMapper,
    build_reverse_links,
    is_solved,
)
from interop.plugins.shared.pypsa_constants import (
    PYPSA_NAME_COLUMN,
    PyPSAComponent,
    PyPSAGeneratorCol,
    PyPSALinkCol,
    PyPSALoadCol,
    PyPSASolvedAttr,
    PyPSAStorageUnitCol,
    PyPSATable,
    PyPSATimeSeriesCol,
)
from interop.plugins.shared.pypsa_fuel_components import (
    FuelComponents,
    build_fuel_components,
    express_link_attribute,
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
_IDLE_VALUE = 0.0

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
        fuels = build_fuel_components(state)
        capacity = _capacity_by_carrier(state, fuels)
        pieces: list[pl.LazyFrame] = []
        pieces += self._map_dispatch(state, fuels)
        pieces += self._map_available_capacity(capacity)
        # Load maps before surplus, which names the load row as one of its sources, but its
        # own rows keep their place so the results table reads in the same order as before.
        load_pieces = self._map_load(state, fuels)
        pieces += self._map_surplus(state, capacity, fuels)
        pieces += self._map_flow(state, fuels)
        pieces += load_pieces
        pieces += self._map_price(state, fuels)
        pieces += self._map_snapshot_weight(state)
        pieces += self._map_objective(state)
        pieces += PypsaAnnualResultsMapper(self._recorder).map_annual(state)

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

    def _map_dispatch(self, state: State, fuels: FuelComponents) -> list[pl.LazyFrame]:
        """Generation and storage active power, category = carrier, positive = into the bus.

        A generator of a fuel puts out no electricity, so it has no row. A plant link puts out
        electricity at bus1, which its p1 states as a negative power.
        """
        specs = [
            (PyPSATable.GENERATORS, PyPSAComponent.GENERATOR, PyPSAGeneratorCol.CARRIER),
            (PyPSATable.STORAGE_UNITS, PyPSAComponent.STORAGE_UNIT, PyPSAStorageUnitCol.CARRIER),
        ]
        pieces: list[pl.LazyFrame] = []
        sources: list[SourceField] = []
        for table, component, carrier_col in specs:
            ts = _fill_idle_dispatch(state, table, fuels.generators)
            topology = state.source_topology.get(table)
            if ts is None or topology is None:
                continue
            pieces.append(_build_dispatch_piece(ts, topology, pl.col(carrier_col)))
            sources.append(_build_dispatch_source(component, PyPSASolvedAttr.DISPATCH))
        plants = _fill_idle_plant_dispatch(state, fuels.plant_links)
        links = state.source_topology.get(PyPSATable.LINKS)
        if plants is not None and links is not None:
            carrier = express_link_attribute(links, PyPSALinkCol.CARRIER)
            pieces.append(_build_dispatch_piece(plants, links, carrier))
            sources.append(
                _build_dispatch_source(PyPSAComponent.LINK, PyPSASolvedAttr.FAR_END_FLOW)
            )
        if pieces:
            self._emit(
                ResultsVariable.DISPATCH,
                sources,
                "generators_t.p and storage_units_t.p -> dispatch (MW into bus); "
                "category = carrier; 0 in each snapshot for a component of a solved network "
                "that states no p, as PyPSA's netCDF export leaves out a series of zeros; "
                "-links_t.p1 of a link that draws a fuel at bus0 and puts out electricity at "
                "bus1; a generator on the bus of a fuel puts out no electricity, so it has no row",
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

    def _map_surplus(
        self, state: State, capacity: _CapacityByCarrier | None, fuels: FuelComponents
    ) -> list[pl.LazyFrame]:
        """What the whole system could still cover: all its capacity less the load on it."""
        loads = _find_electricity_loads(state, fuels)
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

    def _map_flow(self, state: State, fuels: FuelComponents) -> list[pl.LazyFrame]:
        """Line and link active power at bus0, category null, positive = bus0 -> bus1.

        A link that touches the bus of a fuel moves no electricity between two buses, so it
        has no row.
        """
        specs = [
            (PyPSATable.LINES, PyPSAComponent.LINE),
            (PyPSATable.LINKS, PyPSAComponent.LINK),
        ]
        pieces: list[pl.LazyFrame] = []
        sources: list[SourceField] = []
        for table, component in specs:
            ts = (
                _fill_idle_link_flow(state, fuels.links)
                if table == PyPSATable.LINKS
                else state.source_time_series.get((table, PyPSASolvedAttr.FLOW))
            )
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
                "lines_t.p0 and links_t.p0 -> flow (MW from bus0 towards bus1); the flow of a "
                "two-way link is p0(<name>) - p0(<name> reverse), as the reverse link carries "
                "the flow back from bus1 to bus0; 0 in each snapshot for a link of a solved "
                "network whose two directions state no p0",
            )
        return pieces

    def _map_load(self, state: State, fuels: FuelComponents) -> list[pl.LazyFrame]:
        """Load active power set point, category null, positive = consumption at the bus.

        A load of a fuel takes no electricity, so it has no row.
        """
        ts = _find_electricity_loads(state, fuels)
        if ts is None:
            return []
        self._emit(
            ResultsVariable.LOAD,
            [_load_source()],
            "loads_t.p_set -> load (MW consumption at bus)",
        )
        return [ts.select(_build_piece_columns(ResultsVariable.LOAD, category=_NULL_UTF8))]

    def _map_price(self, state: State, fuels: FuelComponents) -> list[pl.LazyFrame]:
        """Bus marginal price, category null, positive = cost of one more MWh at the bus.

        A bus of a fuel prices a fuel, not electricity, so it has no row.
        """
        ts = state.source_time_series.get((PyPSATable.BUSES, PyPSASolvedAttr.MARGINAL_PRICE))
        if ts is None:
            return []
        ts = _drop_components(ts, fuels.buses)
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


def _capacity_by_carrier(state: State, fuels: FuelComponents) -> _CapacityByCarrier | None:
    weightings = state.source_time_series.get(
        (PyPSATable.SNAPSHOTS, PyPSASolvedAttr.SNAPSHOT_WEIGHTING)
    )
    if weightings is None:
        return None
    capacities, sources = _installed_capacities(state, fuels)
    if not capacities:
        return None
    by_carrier = (
        pl.concat(capacities, how="vertical")
        .group_by(ResultsCol.CATEGORY)
        .agg(pl.col(ResultsCol.VALUE).sum())
    )
    snapshots = weightings.select(pl.col(PyPSATimeSeriesCol.SNAPSHOT)).unique()
    return _CapacityByCarrier(by_carrier, by_carrier.join(snapshots, how="cross"), sources)


def _installed_capacities(
    state: State, fuels: FuelComponents
) -> tuple[list[pl.LazyFrame], list[SourceField]]:
    """One (carrier, capacity) frame per component table that states rated power.

    A generator of a fuel puts out no electricity; a plant link puts out p_nom × efficiency.
    """
    capacities: list[pl.LazyFrame] = []
    sources: list[SourceField] = []
    for spec in _CAPACITY_SPECS:
        topology = state.source_topology.get(spec.table)
        if topology is None:
            continue
        held = topology.filter(~pl.col(PYPSA_NAME_COLUMN).is_in(list(fuels.generators)))
        capacities.append(
            held.select(
                [
                    pl.col(spec.carrier_col).alias(ResultsCol.CATEGORY),
                    pl.col(spec.p_nom_col).alias(ResultsCol.VALUE),
                ]
            )
        )
        sources.append(_build_capacity_source(spec.component, spec.p_nom_col))
    plants = _find_plant_capacity(state, fuels)
    if plants is not None:
        capacities.append(plants)
        sources.append(_build_capacity_source(PyPSAComponent.LINK, PyPSALinkCol.P_NOM))
    return capacities, sources


def _build_capacity_source(component: str, attribute: str) -> SourceField:
    return SourceField(
        framework=Framework.PYPSA,
        component=component,
        name=ALL_COMPONENTS,
        attribute=attribute,
        unit=ResultsUnit.MEGAWATT,
    )


def _find_plant_capacity(state: State, fuels: FuelComponents) -> pl.LazyFrame | None:
    """The electricity that each plant link can put out, p_nom × efficiency, by carrier."""
    links = state.source_topology.get(PyPSATable.LINKS)
    if links is None or not fuels.plant_links:
        return None
    output = express_link_attribute(links, PyPSALinkCol.P_NOM) * express_link_attribute(
        links, PyPSALinkCol.EFFICIENCY
    )
    carrier = express_link_attribute(links, PyPSALinkCol.CARRIER)
    return links.filter(pl.col(PYPSA_NAME_COLUMN).is_in(list(fuels.plant_links))).select(
        carrier.alias(ResultsCol.CATEGORY), output.alias(ResultsCol.VALUE)
    )


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


def _merge_reverse_flow(state: State, flow: pl.LazyFrame) -> pl.LazyFrame:
    """The flow of each two-way link, less the p0 of its reverse link, positive from bus0 to
    bus1 of the two-way link."""
    reverses = build_reverse_links(state)
    if not reverses:
        return flow
    component = pl.col(PyPSATimeSeriesCol.COMPONENT)
    value = pl.col(PyPSATimeSeriesCol.VALUE)
    signed = pl.when(component.is_in(list(reverses))).then(-value).otherwise(value)
    return (
        flow.with_columns(signed.alias(PyPSATimeSeriesCol.VALUE), component.replace(reverses))
        .group_by(PyPSATimeSeriesCol.SNAPSHOT, PyPSATimeSeriesCol.COMPONENT, maintain_order=True)
        .agg(value.sum())
    )


def _fill_idle_dispatch(state: State, table: str, excluded: frozenset[str]) -> pl.LazyFrame | None:
    """The dispatch of a table, with 0 in each snapshot for each component that states no p,
    without the components of `excluded`."""
    dispatch = state.source_time_series.get((table, PyPSASolvedAttr.DISPATCH))
    dispatch = None if dispatch is None else _drop_components(dispatch, excluded)
    topology = state.source_topology.get(table)
    if topology is None:
        return dispatch
    names = topology.select(pl.col(PYPSA_NAME_COLUMN).alias(PyPSATimeSeriesCol.COMPONENT))
    return _fill_idle(state, dispatch, _drop_components(names, excluded))


def _fill_idle_plant_dispatch(state: State, plants: frozenset[str]) -> pl.LazyFrame | None:
    """The electricity that each plant link puts out at bus1, -p1, with 0 where it states none."""
    if not plants:
        return None
    output = state.source_time_series.get((PyPSATable.LINKS, PyPSASolvedAttr.FAR_END_FLOW))
    if output is not None:
        kept = output.filter(pl.col(PyPSATimeSeriesCol.COMPONENT).is_in(list(plants)))
        output = kept.with_columns(-pl.col(PyPSATimeSeriesCol.VALUE))
    names = pl.LazyFrame({PyPSATimeSeriesCol.COMPONENT: sorted(plants)})
    return _fill_idle(state, output, names)


def _find_electricity_loads(state: State, fuels: FuelComponents) -> pl.LazyFrame | None:
    loads = state.source_time_series.get((PyPSATable.LOADS, PyPSALoadCol.P_SET))
    return None if loads is None else _drop_components(loads, fuels.loads)


def _drop_components(frame: pl.LazyFrame, names: frozenset[str]) -> pl.LazyFrame:
    if not names:
        return frame
    return frame.filter(~pl.col(PyPSATimeSeriesCol.COMPONENT).is_in(list(names)))


def _build_dispatch_piece(
    dispatch: pl.LazyFrame, topology: pl.LazyFrame, carrier: pl.Expr
) -> pl.LazyFrame:
    carriers = topology.select([pl.col("name"), carrier.alias(ResultsCol.CATEGORY)])
    return dispatch.join(
        carriers, left_on=PyPSATimeSeriesCol.COMPONENT, right_on="name", how="left"
    ).select(_build_piece_columns(ResultsVariable.DISPATCH, category=pl.col(ResultsCol.CATEGORY)))


def _build_dispatch_source(component: str, attribute: str) -> SourceField:
    return SourceField(
        framework=Framework.PYPSA,
        component=component,
        name=ALL_COMPONENTS,
        attribute=attribute,
        unit=ResultsUnit.MEGAWATT,
    )


def _fill_idle_link_flow(state: State, excluded: frozenset[str]) -> pl.LazyFrame | None:
    """The flow of each link, merged with its reverse link, with 0 in each snapshot for each
    link whose two directions state no p0, without the links of `excluded`."""
    flow = state.source_time_series.get((PyPSATable.LINKS, PyPSASolvedAttr.FLOW))
    flow = None if flow is None else _drop_components(flow, excluded)
    merged = None if flow is None else _merge_reverse_flow(state, flow)
    topology = state.source_topology.get(PyPSATable.LINKS)
    if topology is None:
        return merged
    reverses = list(build_reverse_links(state))
    names = topology.select(pl.col(PYPSA_NAME_COLUMN).alias(PyPSATimeSeriesCol.COMPONENT)).filter(
        ~pl.col(PyPSATimeSeriesCol.COMPONENT).is_in(reverses)
    )
    return _fill_idle(state, merged, _drop_components(names, excluded))


def _fill_idle(
    state: State, series: pl.LazyFrame | None, names: pl.LazyFrame
) -> pl.LazyFrame | None:
    """A solved series with 0 in each snapshot for each of `names` that it holds no row for;
    PyPSA's netCDF export leaves out a series that is 0 in every snapshot."""
    snapshots = _find_snapshots(state)
    if snapshots is None or not is_solved(state):
        return series
    if series is not None:
        stated = series.select(PyPSATimeSeriesCol.COMPONENT).unique()
        names = names.join(stated, on=PyPSATimeSeriesCol.COMPONENT, how="anti")
    idle = snapshots.join(names, how="cross").with_columns(
        pl.lit(_IDLE_VALUE).alias(PyPSATimeSeriesCol.VALUE)
    )
    return idle if series is None else pl.concat([series, idle], how="vertical_relaxed")


def _find_snapshots(state: State) -> pl.LazyFrame | None:
    """Every snapshot of the network, read from a snapshot weighting."""
    for attribute in (PyPSASolvedAttr.SNAPSHOT_WEIGHTING, PyPSASolvedAttr.GENERATOR_WEIGHTING):
        frame = state.source_time_series.get((PyPSATable.SNAPSHOTS, attribute))
        if frame is not None:
            return frame.select(PyPSATimeSeriesCol.SNAPSHOT)
    return None


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
