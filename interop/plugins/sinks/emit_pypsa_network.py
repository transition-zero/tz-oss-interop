from __future__ import annotations

import logging
from typing import Any, ClassVar

import pandas as pd
import polars as pl
import pypsa
from pydantic import BaseModel, Field

from interop.core.pipeline import Sink, State
from interop.plugins.shared.constants import StagedTimeSeriesCol
from interop.plugins.shared.pypsa_constants import (
    PYPSA_OUTPUT_DECIMAL_PLACES,
    PyPSABusCol,
    PyPSAComponent,
    PyPSADestinationTable,
    PyPSAGeneratorCol,
    PyPSALineCol,
    PyPSALinkCol,
    PyPSALoadCol,
    PyPSAStorageUnitCol,
    ReverseTimeSeriesMetadataCol,
)
from interop.plugins.shared.staged_samples import filter_to_sample
from interop.plugins.shared.warning_text import name_a_few
from interop.ports.outbound.filesystem import FilesystemPort, Location

log = logging.getLogger(__name__)


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
    series_cache: dict[tuple[str, str, str | None], dict[str, list[float]]] | None = None,
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
    if metadata is not None and metadata.height > 0:
        network.set_snapshots(list(_snapshots(metadata)))
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
    return network


def _snapshots(metadata: pl.DataFrame) -> pd.DatetimeIndex:
    first = metadata.row(0, named=True)
    return pd.date_range(
        start=pd.Timestamp(first[ReverseTimeSeriesMetadataCol.INITIAL_TIMESTAMP]),
        periods=first[ReverseTimeSeriesMetadataCol.LENGTH],
        freq=pd.Timedelta(seconds=first[ReverseTimeSeriesMetadataCol.RESOLUTION_SECONDS]),
    )


def _referenced_bus_names(tables: list[tuple[pl.DataFrame | None, list[str]]]) -> set[str]:
    """Collect bus names referenced by component tables, one (table, bus columns) per entry."""
    names: set[str] = set()
    for frame, columns in tables:
        if frame is None:
            continue
        for column in columns:
            names.update(frame[column].to_list())
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
    frame = _rounded(frame)
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


def _rounded(frame: pl.DataFrame) -> pl.DataFrame:
    """Every float column held to the places the sink writes."""
    return frame.with_columns(pl.col(pl.Float32, pl.Float64).round(PYPSA_OUTPUT_DECIMAL_PLACES))


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
        optional=(PyPSALoadCol.CARRIER, PyPSALoadCol.TYPE),
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
        ),
    )


def _add_links(network: pypsa.Network, links: pl.DataFrame | None) -> None:
    if links is None:
        return
    _add_in_bulk(
        network,
        PyPSAComponent.LINK,
        links,
        PyPSALinkCol.NAME,
        required=(
            PyPSALinkCol.BUS0,
            PyPSALinkCol.BUS1,
            PyPSALinkCol.P_NOM,
            PyPSALinkCol.P_MIN_PU,
            PyPSALinkCol.EFFICIENCY,
            PyPSALinkCol.ACTIVE,
        ),
        # Null round-trip fields are absent from the Sienna source; let PyPSA default them.
        optional=(
            PyPSALinkCol.CARRIER,
            PyPSALinkCol.P_NOM_EXTENDABLE,
            PyPSALinkCol.P_MAX_PU,
            PyPSALinkCol.MARGINAL_COST,
        ),
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
        # thermals; let PyPSA default them.
        optional=(
            PyPSAGeneratorCol.EFFICIENCY,
            PyPSAGeneratorCol.RAMP_LIMIT_UP,
            PyPSAGeneratorCol.RAMP_LIMIT_DOWN,
            PyPSAGeneratorCol.MIN_UP_TIME,
            PyPSAGeneratorCol.MIN_DOWN_TIME,
            PyPSAGeneratorCol.UP_TIME_BEFORE,
            PyPSAGeneratorCol.START_UP_COST,
            PyPSAGeneratorCol.SHUT_DOWN_COST,
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
    )


def _attach_time_series(
    network: pypsa.Network,
    metadata: pl.DataFrame,
    state: State,
    sample: str | None,
    series_cache: dict[tuple[str, str, str | None], dict[str, list[float]]],
) -> None:
    accessor = {
        PyPSADestinationTable.GENERATORS: network.generators_t,
        PyPSADestinationTable.STORAGE_UNITS: network.storage_units_t,
        PyPSADestinationTable.LOADS: network.loads_t,
    }
    for (table, attribute), by_component in _columns_by_attribute(
        metadata, state, sample, series_cache
    ).items():
        target: dict[str, Any] = accessor[table]
        target[attribute] = _joined(target[attribute], by_component, network.snapshots)


def _columns_by_attribute(
    metadata: pl.DataFrame,
    state: State,
    sample: str | None,
    series_cache: dict[tuple[str, str, str | None], dict[str, list[float]]],
) -> dict[tuple[str, str], dict[str, list[float]]]:
    """Every component's column, gathered per (table, attribute) before any frame is touched.

    Derates compound: a second series for the same attribute narrows the first rather than
    replacing it (an outage on top of a rating).
    """
    columns: dict[tuple[str, str], dict[str, list[float]]] = {}
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
        staged = series_cache[cache_key].get(source_component, [])
        scaled = [value * scaling + offset for value in staged]
        key = (
            row[ReverseTimeSeriesMetadataCol.COMPONENT_TABLE],
            row[ReverseTimeSeriesMetadataCol.ATTRIBUTE],
        )
        held = columns.setdefault(key, {}).get(component)
        columns[key][component] = scaled if held is None else _compound(held, scaled)
    return columns


def _joined(
    frame: pd.DataFrame, by_component: dict[str, list[float]], snapshots: pd.Index
) -> pd.DataFrame:
    """Add every component's column in one concat.

    Inserting them one at a time leaves pandas re-blocking the frame per column, which on a
    model of a few hundred components dominates the time spent writing a network.
    """
    compounded = {
        name: _round_all(
            _compound(frame[name].tolist(), values) if name in frame.columns else values
        )
        for name, values in by_component.items()
    }
    added = pd.DataFrame(compounded, index=snapshots)
    kept = frame.drop(columns=[name for name in added.columns if name in frame.columns])
    return added if kept.columns.empty else pd.concat([kept, added], axis=1)


def _compound(held: list[float], scaled: list[float]) -> list[float]:
    return [first * second for first, second in zip(held, scaled, strict=True)]


def _round_all(values: list[float]) -> list[float]:
    """Held to the places the sink writes, once every derate has been compounded in."""
    return [round(value, PYPSA_OUTPUT_DECIMAL_PLACES) for value in values]


def _collect_series_by_component(frame: pl.LazyFrame, sample: str | None) -> dict[str, list[float]]:
    """One sample's rows of a staged series, grouped by component, in snapshot order.

    Filtering to the sample before collecting reads only the rows one network needs off
    disk, never the whole staged series (an ensemble's may hold every replication);
    partitioning by component once turns each metadata row's lookup into a dict access
    rather than a fresh scan-and-filter.
    """
    collected = (
        filter_to_sample(frame, sample)
        .sort(StagedTimeSeriesCol.SNAPSHOT)
        .select(StagedTimeSeriesCol.COMPONENT, StagedTimeSeriesCol.VALUE)
        .collect()
    )
    return {
        str(component): part[StagedTimeSeriesCol.VALUE].to_list()
        for (component,), part in collected.partition_by(
            StagedTimeSeriesCol.COMPONENT, as_dict=True, include_key=False
        ).items()
    }
