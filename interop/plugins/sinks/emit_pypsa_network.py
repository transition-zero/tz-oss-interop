from __future__ import annotations

import logging
from typing import Any, ClassVar

import numpy as np
import pandas as pd
import polars as pl
import pypsa
from pydantic import BaseModel, Field

from interop.core.pipeline import Sink, State
from interop.plugins.shared.pypsa_constants import (
    LINK_FURTHER_PORTS,
    PYPSA_OUTPUT_DECIMAL_PLACES,
    UNROUNDED_OUTPUT_COLUMNS,
    PyPSABusCol,
    PyPSAComponent,
    PyPSADestinationTable,
    PyPSAGeneratorCol,
    PyPSALineCol,
    PyPSALinkCol,
    PyPSALoadCol,
    PyPSASnapshotWeightingCol,
    PyPSAStorageUnitCol,
    ReverseTimeSeriesMetadataCol,
)
from interop.plugins.shared.pypsa_time_series import find_snapshot_window
from interop.plugins.shared.series_batches import (
    FloatArray,
    list_component_batches,
    read_batch_by_component,
)
from interop.plugins.shared.staged_samples import filter_to_sample
from interop.plugins.shared.warning_text import name_a_few
from interop.ports.outbound.filesystem import FilesystemPort, Location

log = logging.getLogger(__name__)


# What a component with no staged values scales and compounds as.
_NO_VALUES: FloatArray = np.empty(0, dtype=np.float64)


class EmitPypsaNetworkParams(BaseModel):
    output_path: Location = Field(description="the PyPSA network to write, as netCDF (.nc)")


class EmitPypsaNetwork(Sink):
    name: ClassVar[str] = "emit_pypsa_network"
    params_schema: ClassVar[type[BaseModel] | None] = EmitPypsaNetworkParams

    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def write(self, state: State, params: BaseModel | None) -> None:
        if not isinstance(params, EmitPypsaNetworkParams):
            raise TypeError(
                f"{type(self).__name__} requires {EmitPypsaNetworkParams.__name__}, "
                f"got {type(params).__name__}"
            )
        network = build_network(state, None)
        dataset = network.export_to_netcdf(None)
        with self._fs.open_write(params.output_path) as f:
            # scipy is the only xarray engine that writes to a file object (xarray's
            # type stubs only admit paths, hence the ignore); it emits NETCDF3, which
            # xarray's netcdf4 engine and pypsa.Network read back.
            dataset.to_netcdf(f, engine="scipy")  # type: ignore[call-overload]


def build_network(
    state: State,
    sample: str | None,
    series_cache: dict[tuple[str, str, str | None], dict[str, FloatArray]] | None = None,
) -> pypsa.Network:
    """Assemble one PyPSA network from the destination tables, reading one sample's series.

    A single-network write passes ``sample=None``: every series a ``StagePlexosXml`` source
    stages already holds at most one sample's rows (it keeps only the lowest replication), so
    nothing is left to choose and ``filter_to_sample`` passes such a series through unfiltered.
    An ensemble write passes the sample it wants; ``series_cache`` then holds that sample's
    values, already filtered and grouped by component, keyed by (owner type, series name,
    sample), so the several metadata rows one network's components read from the same series
    share one collect instead of each re-scanning it. The caller (the ensemble sink) evicts a
    sample's entries once its network is written, so the cache never holds more than one
    sample's data even across many networks.
    """
    network = pypsa.Network()
    metadata = state.destination_tables.get(PyPSADestinationTable.TIME_SERIES_METADATA)
    window = find_snapshot_window(state)
    if window is not None:
        network.set_snapshots(window.list_snapshots())
    buses = state.destination_tables.get(PyPSADestinationTable.BUSES)
    generators = state.destination_tables.get(PyPSADestinationTable.GENERATORS)
    storage_units = state.destination_tables.get(PyPSADestinationTable.STORAGE_UNITS)
    loads = state.destination_tables.get(PyPSADestinationTable.LOADS)
    lines = state.destination_tables.get(PyPSADestinationTable.LINES)
    links = state.destination_tables.get(PyPSADestinationTable.LINKS)
    referenced = _referenced_bus_names(
        [
            (generators, [PyPSAGeneratorCol.BUS]),
            (storage_units, [PyPSAStorageUnitCol.BUS]),
            (loads, [PyPSALoadCol.BUS]),
            (lines, [PyPSALineCol.BUS0, PyPSALineCol.BUS1]),
            (links, [PyPSALinkCol.BUS0, PyPSALinkCol.BUS1]),
            (links, _list_named_ports(links)),
        ]
    )
    _add_buses(network, buses, referenced)
    _add_generators(network, generators)
    _add_storage_units(network, storage_units)
    _add_loads(network, loads)
    _add_lines(network, lines)
    _add_links(network, links)
    cache = series_cache if series_cache is not None else {}
    if metadata is not None and metadata.height > 0:
        _attach_time_series(network, metadata, state, sample, cache)
    _set_snapshot_weightings(network, state.destination_time_series)
    return network


def _set_snapshot_weightings(network: pypsa.Network, tables: dict[str, pl.LazyFrame]) -> None:
    """Write the hours each snapshot counts for, where a mapping derived them."""
    weightings = tables.get(PyPSADestinationTable.SNAPSHOT_WEIGHTINGS)
    if weightings is None:
        return
    table = weightings.collect().to_pandas().set_index(PyPSASnapshotWeightingCol.SNAPSHOT)
    columns = [
        PyPSASnapshotWeightingCol.OBJECTIVE,
        PyPSASnapshotWeightingCol.STORES,
        PyPSASnapshotWeightingCol.GENERATORS,
    ]
    network.snapshot_weightings = table[columns]


def _list_named_ports(links: pl.DataFrame | None) -> list[str]:
    """The further bus columns of the links, so a bus that only they name is still checked."""
    if links is None:
        return []
    return [bus for bus, _ in _list_extra_ports(links)]


def _referenced_bus_names(tables: list[tuple[pl.DataFrame | None, list[str]]]) -> set[str]:
    """Collect bus names referenced by component tables, one (table, bus columns) per entry."""
    names: set[str] = set()
    for frame, columns in tables:
        if frame is None:
            continue
        for column in columns:
            names.update(frame[column].drop_nulls().to_list())
    return names


def _add_in_bulk(
    network: pypsa.Network,
    component: str,
    frame: pl.DataFrame,
    name_column: str,
    required: tuple[str, ...],
    optional: tuple[str, ...] = (),
) -> None:
    """Add every row of a component table in one call.

    PyPSA rebuilds a component's frame on each ``add``, so adding a few hundred components
    one at a time is what dominates writing a network, and an ensemble writes one network
    per replication. Optional columns are applied afterwards over the rows that carry a
    value, leaving PyPSA's own default in place for the rest.
    """
    if frame.height == 0:
        return
    frame = frame.with_columns(
        pl.col(pl.Float32, pl.Float64)
        .exclude(UNROUNDED_OUTPUT_COLUMNS)
        .round(PYPSA_OUTPUT_DECIMAL_PLACES)
    )
    names = frame[name_column].to_list()
    columns = {column: frame[column].to_list() for column in required}
    # PyPSA's third positional is a name suffix, so mypy cannot check the attribute kwargs.
    network.add(component, names, **columns)  # type: ignore[arg-type]
    static = network.components[component].static
    for column in optional:
        carried = frame.filter(pl.col(column).is_not_null())
        if carried.height:
            rows = carried[name_column].to_list()
            # PyPSA types each attribute, and a per-row add coerced to that type; keep it.
            static.loc[rows, column] = pd.Series(
                carried[column].to_list(), index=rows, dtype=static[column].dtype
            )


def _add_buses(network: pypsa.Network, buses: pl.DataFrame | None, referenced: set[str]) -> None:
    added: set[str] = set()
    if buses is not None:
        _add_in_bulk(
            network,
            PyPSAComponent.BUS,
            buses,
            PyPSABusCol.NAME,
            required=(
                PyPSABusCol.V_NOM,
                PyPSABusCol.CARRIER,
                PyPSABusCol.CONTROL,
                PyPSABusCol.LOCATION,
            ),
        )
        added = set(buses[PyPSABusCol.NAME].to_list())
    missing = sorted(referenced - added)
    if missing:
        _warn_about_invented_buses(missing)
        network.add(PyPSAComponent.BUS, missing)


def _warn_about_invented_buses(missing: list[str]) -> None:
    """A component naming a bus no mapping built gets a bare one, which is a mapping gap.

    Left silent it makes an island: the bus carries no voltage and no line reaches it.
    """
    log.warning(
        "pypsa: %d bus(es) are referenced by a component but were never mapped, so each gets "
        "a bare bus nothing connects to: %s",
        len(missing),
        name_a_few(missing),
    )


def _add_loads(network: pypsa.Network, loads: pl.DataFrame | None) -> None:
    if loads is None:
        return
    _add_in_bulk(
        network,
        PyPSAComponent.LOAD,
        loads,
        PyPSALoadCol.NAME,
        required=(PyPSALoadCol.BUS, PyPSALoadCol.P_SET),
        optional=(PyPSALoadCol.CARRIER, PyPSALoadCol.TYPE, PyPSALoadCol.SIGN),
    )


def _add_lines(network: pypsa.Network, lines: pl.DataFrame | None) -> None:
    if lines is None:
        return
    _add_in_bulk(
        network,
        PyPSAComponent.LINE,
        lines,
        PyPSALineCol.NAME,
        required=(
            PyPSALineCol.BUS0,
            PyPSALineCol.BUS1,
            PyPSALineCol.R,
            PyPSALineCol.X,
            PyPSALineCol.B,
            PyPSALineCol.G,
            PyPSALineCol.S_NOM,
            PyPSALineCol.LENGTH,
            PyPSALineCol.NUM_PARALLEL,
            PyPSALineCol.ACTIVE,
        ),
        # Null round-trip fields are absent from the Sienna source; let PyPSA default them.
        optional=(
            PyPSALineCol.CARRIER,
            PyPSALineCol.V_ANG_MIN,
            PyPSALineCol.V_ANG_MAX,
            PyPSALineCol.S_NOM_EXTENDABLE,
            PyPSALineCol.S_NOM_MIN,
        ),
    )


def _add_links(network: pypsa.Network, links: pl.DataFrame | None) -> None:
    if links is None:
        return
    ports = _list_extra_ports(links)
    _add_in_bulk(
        network,
        PyPSAComponent.LINK,
        _fill_extra_ports(links, ports),
        PyPSALinkCol.NAME,
        required=(
            PyPSALinkCol.BUS0,
            PyPSALinkCol.BUS1,
            PyPSALinkCol.P_NOM,
            PyPSALinkCol.P_MIN_PU,
            PyPSALinkCol.EFFICIENCY,
            PyPSALinkCol.ACTIVE,
            *[column for port in ports for column in port],
        ),
        # Null round-trip fields are absent from the Sienna source; let PyPSA default them.
        optional=(
            PyPSALinkCol.CARRIER,
            PyPSALinkCol.P_NOM_EXTENDABLE,
            PyPSALinkCol.P_MAX_PU,
            PyPSALinkCol.MARGINAL_COST,
            PyPSALinkCol.P_NOM_MIN,
            PyPSALinkCol.P_NOM_MAX,
            PyPSALinkCol.COMMITTABLE,
            PyPSALinkCol.START_UP_COST,
            PyPSALinkCol.SHUT_DOWN_COST,
            PyPSALinkCol.MIN_UP_TIME,
            PyPSALinkCol.MIN_DOWN_TIME,
            PyPSALinkCol.UP_TIME_BEFORE,
            PyPSALinkCol.RAMP_LIMIT_UP,
            PyPSALinkCol.RAMP_LIMIT_DOWN,
        ),
    )


# PyPSA's own value for a link that names no further bus: no bus, and an efficiency of 1.
_NO_BUS = ""
_NO_LOSS = 1.0


def _list_extra_ports(links: pl.DataFrame) -> list[tuple[str, str]]:
    return [
        port
        for port in LINK_FURTHER_PORTS
        if port[0] in links.columns and links[port[0]].is_not_null().any()
    ]


def _fill_extra_ports(links: pl.DataFrame, ports: list[tuple[str, str]]) -> pl.DataFrame:
    return links.with_columns(
        *[pl.col(bus).fill_null(_NO_BUS) for bus, _ in ports],
        *[pl.col(efficiency).fill_null(_NO_LOSS) for _, efficiency in ports],
    )


def _add_generators(network: pypsa.Network, generators: pl.DataFrame | None) -> None:
    if generators is None:
        return
    _add_in_bulk(
        network,
        PyPSAComponent.GENERATOR,
        generators,
        PyPSAGeneratorCol.NAME,
        required=(
            PyPSAGeneratorCol.BUS,
            PyPSAGeneratorCol.CARRIER,
            PyPSAGeneratorCol.P_NOM,
            PyPSAGeneratorCol.P_MIN_PU,
            PyPSAGeneratorCol.P_MAX_PU,
            PyPSAGeneratorCol.MARGINAL_COST,
            PyPSAGeneratorCol.COMMITTABLE,
            PyPSAGeneratorCol.P_NOM_EXTENDABLE,
        ),
        # Efficiency and the unit-commitment fields are null for renewables and unset
        # thermals, and the expansion fields are null for a generator the source fixes;
        # let PyPSA default them.
        optional=(
            PyPSAGeneratorCol.EFFICIENCY,
            PyPSAGeneratorCol.RAMP_LIMIT_UP,
            PyPSAGeneratorCol.RAMP_LIMIT_DOWN,
            PyPSAGeneratorCol.MIN_UP_TIME,
            PyPSAGeneratorCol.MIN_DOWN_TIME,
            PyPSAGeneratorCol.UP_TIME_BEFORE,
            PyPSAGeneratorCol.START_UP_COST,
            PyPSAGeneratorCol.SHUT_DOWN_COST,
            PyPSAGeneratorCol.P_NOM_MIN,
            PyPSAGeneratorCol.P_NOM_MAX,
            PyPSAGeneratorCol.OVERNIGHT_COST,
            PyPSAGeneratorCol.DISCOUNT_RATE,
            PyPSAGeneratorCol.LIFETIME,
            PyPSAGeneratorCol.BUILD_YEAR,
            PyPSAGeneratorCol.E_SUM_MIN,
            PyPSAGeneratorCol.E_SUM_MAX,
        ),
    )


def _add_storage_units(network: pypsa.Network, storage_units: pl.DataFrame | None) -> None:
    if storage_units is None:
        return
    _add_in_bulk(
        network,
        PyPSAComponent.STORAGE_UNIT,
        storage_units,
        PyPSAStorageUnitCol.NAME,
        required=(
            PyPSAStorageUnitCol.BUS,
            PyPSAStorageUnitCol.CARRIER,
            PyPSAStorageUnitCol.P_NOM,
            PyPSAStorageUnitCol.P_MIN_PU,
            PyPSAStorageUnitCol.P_MAX_PU,
            PyPSAStorageUnitCol.MAX_HOURS,
            PyPSAStorageUnitCol.EFFICIENCY_STORE,
            PyPSAStorageUnitCol.EFFICIENCY_DISPATCH,
            PyPSAStorageUnitCol.MARGINAL_COST,
            PyPSAStorageUnitCol.STATE_OF_CHARGE_INITIAL,
            PyPSAStorageUnitCol.CYCLIC_STATE_OF_CHARGE,
            PyPSAStorageUnitCol.P_NOM_EXTENDABLE,
            PyPSAStorageUnitCol.INFLOW,
        ),
        # The expansion fields are null for a storage unit the source fixes; let PyPSA
        # default them.
        optional=(
            PyPSAStorageUnitCol.P_NOM_MIN,
            PyPSAStorageUnitCol.P_NOM_MAX,
            PyPSAStorageUnitCol.OVERNIGHT_COST,
            PyPSAStorageUnitCol.DISCOUNT_RATE,
            PyPSAStorageUnitCol.LIFETIME,
            PyPSAStorageUnitCol.BUILD_YEAR,
            PyPSAStorageUnitCol.CYCLIC_STATE_OF_CHARGE_PER_PERIOD,
        ),
    )


def _attach_time_series(
    network: pypsa.Network,
    metadata: pl.DataFrame,
    state: State,
    sample: str | None,
    series_cache: dict[tuple[str, str, str | None], dict[str, FloatArray]],
) -> None:
    accessor = {
        PyPSADestinationTable.GENERATORS: network.generators_t,
        PyPSADestinationTable.STORAGE_UNITS: network.storage_units_t,
        PyPSADestinationTable.LOADS: network.loads_t,
        PyPSADestinationTable.LINKS: network.links_t,
    }
    for (table, attribute), by_component in _columns_by_attribute(
        metadata, state, sample, series_cache
    ).items():
        target: dict[str, Any] = accessor[table]
        target[attribute] = _joined(target[attribute], by_component, network.snapshots, attribute)


def _columns_by_attribute(
    metadata: pl.DataFrame,
    state: State,
    sample: str | None,
    series_cache: dict[tuple[str, str, str | None], dict[str, FloatArray]],
) -> dict[tuple[str, str], dict[str, FloatArray]]:
    """Every component's column, gathered per (table, attribute) before any frame is touched.

    Derates compound: a second series for the same attribute narrows the first rather than
    replacing it (an outage on top of a rating).
    """
    columns: dict[tuple[str, str], dict[str, FloatArray]] = {}
    for row in metadata.iter_rows(named=True):
        owner_type = row[ReverseTimeSeriesMetadataCol.SOURCE_OWNER_TYPE]
        series_name = row[ReverseTimeSeriesMetadataCol.SOURCE_SERIES_NAME]
        source_component = row[ReverseTimeSeriesMetadataCol.SOURCE_COMPONENT_NAME]
        component = row[ReverseTimeSeriesMetadataCol.COMPONENT_NAME]
        cache_key = (owner_type, series_name, sample)
        if cache_key not in series_cache:
            series_cache[cache_key] = _collect_series_by_component(
                state.source_time_series[(owner_type, series_name)], sample
            )
        scaling = row[ReverseTimeSeriesMetadataCol.SCALING_FACTOR]
        offset = row[ReverseTimeSeriesMetadataCol.OFFSET]
        staged = series_cache[cache_key].get(source_component, _NO_VALUES)
        scaled = staged * scaling + offset
        key = (
            row[ReverseTimeSeriesMetadataCol.COMPONENT_TABLE],
            row[ReverseTimeSeriesMetadataCol.ATTRIBUTE],
        )
        held = columns.setdefault(key, {}).get(component)
        columns[key][component] = scaled if held is None else _compound(held, scaled)
    return columns


def _joined(
    frame: pd.DataFrame,
    by_component: dict[str, FloatArray],
    snapshots: pd.Index,
    attribute: str,
) -> pd.DataFrame:
    """Add every component's column in one concat.

    Inserting them one at a time leaves pandas re-blocking the frame per column, which on a
    model of a few hundred components dominates the time spent writing a network.

    Every column here holds one attribute, one component to a column, so the attribute alone
    decides whether the numbers round.
    """
    compounded = {
        name: _compound(frame[name].to_numpy(), values) if name in frame.columns else values
        for name, values in by_component.items()
    }
    added = pd.DataFrame(compounded, index=snapshots)
    if attribute not in UNROUNDED_OUTPUT_COLUMNS:
        added = added.round(PYPSA_OUTPUT_DECIMAL_PLACES)
    kept = frame.drop(columns=[name for name in added.columns if name in frame.columns])
    return added if kept.columns.empty else pd.concat([kept, added], axis=1)


def _compound(held: FloatArray, scaled: FloatArray) -> FloatArray:
    if held.shape != scaled.shape:
        raise ValueError(f"cannot compound series of lengths {held.size} and {scaled.size}")
    return held * scaled


def _collect_series_by_component(frame: pl.LazyFrame, sample: str | None) -> dict[str, FloatArray]:
    """One sample's values of a staged series, one array per component, in snapshot order.

    Filtering to the sample first reads only the rows one network needs off disk, never the
    whole staged series (an ensemble's may hold every replication). Reading a batch of
    components at a time keeps one batch in memory, not the series.
    """
    sampled = filter_to_sample(frame, sample)
    by_component: dict[str, FloatArray] = {}
    for batch in list_component_batches(sampled):
        by_component.update(read_batch_by_component(sampled, batch))
    return by_component
