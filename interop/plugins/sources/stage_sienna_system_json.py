from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import IO, Any, ClassVar, NamedTuple

import numpy as np
import pandas as pd
import polars as pl
from infrastore import Store
from numpy.typing import NDArray
from pydantic import BaseModel

from interop.core.pipeline import StagedSource, State
from interop.plugins.shared.constants import StagedTimeSeriesCol
from interop.plugins.shared.extensions_sidecar import StagesExtensionsSidecar
from interop.plugins.shared.sienna_constants import (
    SIENNA_SOURCE_BUSES_SCHEMA,
    InfraStoreSidecar,
    SiennaACBusCol,
    SiennaArcCol,
    SiennaComponent,
    SiennaGeneratorCol,
    SiennaLineCol,
    SiennaSchemasSystem,
    SiennaTable,
    SiennaUnitSystem,
    TimeSeriesAssociationCol,
)
from interop.plugins.shared.sienna_time_series import build_capacity_by_owner, has_series_capacity
from interop.plugins.shared.warning_text import name_a_few
from interop.ports.errors import MissingInputError
from interop.ports.outbound.filesystem import FilesystemPort, InputFile

log = logging.getLogger(__name__)

# Rows of one series read and written per block, which bounds peak memory. One block is one
# parquet file, so a long series becomes a few files that are scanned back as one frame.
_TIME_SERIES_CHUNK_ROWS = 1_000_000

# SiennaSchemas types routed to each reverse intermediate table. Each is a key in the
# top-level type->list container.
_GENERATOR_TYPES = (
    SiennaComponent.THERMAL_STANDARD,
    SiennaComponent.RENEWABLE_DISPATCH,
    SiennaComponent.RENEWABLE_NON_DISPATCH,
    SiennaComponent.HYDRO_DISPATCH,
)
_STORAGE_TYPES = (SiennaComponent.ENERGY_RESERVOIR_STORAGE,)
_LOAD_TYPES = (SiennaComponent.POWER_LOAD, SiennaComponent.INTERRUPTIBLE_POWER_LOAD)
_LINE_TYPES = (SiennaComponent.LINE, SiennaComponent.MONITORED_LINE)
_LINK_TYPES = (SiennaComponent.TWO_TERMINAL_GENERIC_HVDC_LINE,)


class StageSiennaSystemJsonParams(BaseModel):
    system_json_path: InputFile
    time_series_h5_path: InputFile
    # What the hop before this one set aside. Only this translator writes a sidecar, so a
    # SiennaSchemas system from a partner is the system JSON and its HDF5 companion and
    # nothing more.
    extensions_json_path: InputFile | None = None


class StageSiennaSystemJson(StagesExtensionsSidecar, StagedSource):
    name: ClassVar[str] = "stage_sienna_system_json"
    params_schema: ClassVar[type[BaseModel] | None] = StageSiennaSystemJsonParams
    prefix: ClassVar[str] = "sienna"

    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def load_into_state(self, params: BaseModel | None, staging_dir: Path) -> State:
        if not isinstance(params, StageSiennaSystemJsonParams):
            raise TypeError(
                f"{type(self).__name__} requires {StageSiennaSystemJsonParams.__name__}, "
                f"got {type(params).__name__}"
            )
        if not self._fs.can_read(params.system_json_path):
            raise MissingInputError(self.name, "system JSON", f"{params.system_json_path}")
        if not self._fs.can_read(params.time_series_h5_path):
            raise MissingInputError(self.name, "HDF5 companion", f"{params.time_series_h5_path}")
        with self._fs.open_read(params.system_json_path) as system_file:
            system = json.load(system_file)
        with self._fs.open_read(params.time_series_h5_path) as h5_file:
            staged = stage_system(system, h5_file, staging_dir)
        extensions = self._stage_extensions_sidecar(params.extensions_json_path)
        return State(
            staging_dir=staging_dir,
            source_topology=staged.topology,
            source_time_series=staged.time_series,
            source_extensions=extensions,
            source_extension_series=self._stage_extension_companions(
                params.extensions_json_path, extensions
            ),
        )


class StagedSystem(NamedTuple):
    """One Sienna system staged onto disk: its tables, and its series by owner and name."""

    topology: dict[str, pl.LazyFrame]
    time_series: dict[tuple[str, str], pl.LazyFrame]


def stage_system(system: dict[str, Any], h5_file: IO[bytes], staging_dir: Path) -> StagedSystem:
    """Stage one system JSON and its HDF5 companion into lazy scans under ``staging_dir``.

    Every frame it returns scans a path under ``staging_dir``, so two systems staged into
    one directory would each read whichever wrote last. An ensemble gives each replication
    a directory of its own.
    """
    return StagedSystem(
        topology=stage_topology(system, staging_dir),
        time_series=_stage_time_series(system, h5_file, staging_dir),
    )


def stage_topology(system: dict[str, Any], staging_dir: Path) -> dict[str, pl.LazyFrame]:
    components = system.get(SiennaSchemasSystem.COMPONENTS, {})

    area_name_by_id = {
        area[SiennaACBusCol.ID]: area[SiennaACBusCol.NAME]
        for area in components.get(SiennaComponent.AREA, [])
    }

    frames: dict[str, pl.LazyFrame] = {}
    bus_rows = [_bus_row(c, area_name_by_id) for c in components.get(SiennaComponent.AC_BUS, [])]
    _stage_table(bus_rows, SIENNA_SOURCE_BUSES_SCHEMA, SiennaTable.BUSES, staging_dir, frames)

    generator_rows = [
        _component_row(c, sienna_type)
        for sienna_type in _GENERATOR_TYPES
        for c in components.get(sienna_type, [])
    ]
    _stage_table(generator_rows, None, SiennaTable.GENERATORS, staging_dir, frames)

    storage_rows = [
        _component_row(c, sienna_type)
        for sienna_type in _STORAGE_TYPES
        for c in components.get(sienna_type, [])
    ]
    _stage_table(storage_rows, None, SiennaTable.STORAGE, staging_dir, frames)

    load_rows = [
        _component_row(c, sienna_type)
        for sienna_type in _LOAD_TYPES
        for c in components.get(sienna_type, [])
    ]
    _stage_table(load_rows, None, SiennaTable.LOADS, staging_dir, frames)

    arc_endpoints = {
        arc[SiennaArcCol.ID]: (arc[SiennaArcCol.FROM], arc[SiennaArcCol.TO])
        for arc in components.get(SiennaComponent.ARC, [])
    }
    line_rows = [
        _line_row(c, sienna_type, arc_endpoints)
        for sienna_type in _LINE_TYPES
        for c in components.get(sienna_type, [])
    ]
    _stage_table(line_rows, None, SiennaTable.LINES, staging_dir, frames)

    link_rows = [
        _line_row(c, sienna_type, arc_endpoints)
        for sienna_type in _LINK_TYPES
        for c in components.get(sienna_type, [])
    ]
    _stage_table(link_rows, None, SiennaTable.LINKS, staging_dir, frames)
    return frames


def _line_row(
    component: dict[str, Any], sienna_type: str, arc_endpoints: dict[int, tuple[int, int]]
) -> dict[str, Any]:
    """Tag a Line/MonitoredLine with its type and denormalise its Arc to bus0/bus1 ids."""
    row = dict(component)
    row[SiennaLineCol.SIENNA_TYPE] = sienna_type
    bus0_id, bus1_id = arc_endpoints[component[SiennaLineCol.ARC]]
    row[SiennaLineCol.BUS0] = bus0_id
    row[SiennaLineCol.BUS1] = bus1_id
    return row


def _bus_row(component: dict[str, Any], area_name_by_id: dict[int, str]) -> dict[str, Any]:
    area_id = component.get(SiennaACBusCol.AREA)
    area_name = area_name_by_id.get(area_id) if area_id is not None else None
    return {
        SiennaACBusCol.ID: component[SiennaACBusCol.ID],
        SiennaACBusCol.NAME: component[SiennaACBusCol.NAME],
        SiennaACBusCol.NUMBER: component[SiennaACBusCol.NUMBER],
        SiennaACBusCol.AVAILABLE: component[SiennaACBusCol.AVAILABLE],
        SiennaACBusCol.BUSTYPE: component[SiennaACBusCol.BUSTYPE],
        SiennaACBusCol.ANGLE: component.get(SiennaACBusCol.ANGLE),
        SiennaACBusCol.MAGNITUDE: component.get(SiennaACBusCol.MAGNITUDE),
        SiennaACBusCol.VOLTAGE_LIMITS: component.get(SiennaACBusCol.VOLTAGE_LIMITS),
        SiennaACBusCol.BASE_VOLTAGE: float(component[SiennaACBusCol.BASE_VOLTAGE]),
        SiennaACBusCol.AREA: area_name,
        SiennaACBusCol.LOAD_ZONE: component.get(SiennaACBusCol.LOAD_ZONE),
    }


def _component_row(component: dict[str, Any], sienna_type: str) -> dict[str, Any]:
    """Tag one generator/storage object with its type.

    SiennaSchemas objects are already flat with an integer ``bus`` id, so the only thing
    to add is ``sienna_type`` (implied by the container key, not stored on the object), so
    the downstream steps dispatch on type the same way regardless of source serialisation.
    """
    row = dict(component)
    row[SiennaGeneratorCol.SIENNA_TYPE] = sienna_type
    return row


def _stage_table(
    rows: list[dict[str, Any]],
    schema: dict[str, pl.DataType | type[pl.DataType]] | None,
    name: str,
    staging_dir: Path,
    frames: dict[str, pl.LazyFrame],
) -> None:
    if not rows:
        return
    out = staging_dir / "topology" / f"{name}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows, schema=schema).write_parquet(out)
    frames[name] = pl.scan_parquet(out)


def _stage_time_series(
    system: dict[str, Any], h5_file: IO[bytes], staging_dir: Path
) -> dict[tuple[str, str], pl.LazyFrame]:
    """Read the JSON TimeSeriesAssociation records plus the InfraStore sidecar and stage one
    parquet per (owner type, series name).

    The associations are a sibling list in the system document. The values live in the
    InfraStore file beside it, and each association names its series by ``association_id``.
    Each association's integer ``owner_id`` is resolved back to its component name so
    downstream steps see the same ``(snapshot, component, value)`` contract regardless of
    where the values were stored.
    """
    associations = system.get(SiennaSchemasSystem.TIME_SERIES_ASSOCIATIONS, [])
    if not associations:
        return {}

    name_by_owner = _name_by_owner(system)
    associations = _drop_unconvertible(associations)
    capacity_by_owner = _capacity_by_owner(system, associations)
    key_dirs: dict[tuple[str, str], Path] = {}
    with _open_store(h5_file, associations, staging_dir) as store:
        for association in associations:
            length = association[TimeSeriesAssociationCol.LENGTH]
            if length == 0:
                continue
            key = (
                association[TimeSeriesAssociationCol.OWNER_TYPE],
                association[TimeSeriesAssociationCol.NAME],
            )
            owner = (
                association[TimeSeriesAssociationCol.OWNER_TYPE],
                association[TimeSeriesAssociationCol.OWNER_ID],
            )
            key_dir = staging_dir / "time_series" / key[0] / key[1]
            key_dir.mkdir(parents=True, exist_ok=True)
            _stream_series_to_parquet(
                store,
                association,
                capacity=capacity_by_owner.get(owner),
                component=name_by_owner[owner],
                key_dir=key_dir,
            )
            key_dirs[key] = key_dir

    return {key: pl.scan_parquet(key_dir / "*.parquet") for key, key_dir in key_dirs.items()}


def _is_natural_units(association: dict[str, Any]) -> bool:
    return association.get(TimeSeriesAssociationCol.UNIT_SYSTEM) == SiennaUnitSystem.NATURAL_UNITS


def _drop_unconvertible(associations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the rows that can be staged, and warn once about the natural-units rows that cannot.

    A natural-units row needs its owner's capacity to reach the per-unit shape. An owner type
    with no capacity rule leaves its series out.
    """
    kept: list[dict[str, Any]] = []
    left_out: list[str] = []
    for association in associations:
        owner_type = association[TimeSeriesAssociationCol.OWNER_TYPE]
        if _is_natural_units(association) and not has_series_capacity(owner_type):
            left_out.append(f"{owner_type} {association[TimeSeriesAssociationCol.NAME]}")
        else:
            kept.append(association)
    if left_out:
        log.warning(
            "%d series in natural units have an owner type with no capacity to convert by, "
            "so each is left out: %s",
            len(left_out),
            name_a_few(left_out),
        )
    return kept


def _convert_to_per_unit(values: NDArray[Any], capacity: float | None) -> NDArray[Any]:
    """A natural-units array divided by its owner's capacity; any other array as stored.

    A zero capacity gives no per-unit shape, so its series reads as zeros.
    """
    if capacity is None:
        return values
    return values / capacity if capacity else np.zeros_like(values)


def _capacity_by_owner(
    system: dict[str, Any], associations: list[dict[str, Any]]
) -> dict[tuple[str, int], float]:
    """The capacity that turns each owner's stored megawatts back into its per-unit shape."""
    owners = {
        (
            association[TimeSeriesAssociationCol.OWNER_TYPE],
            association[TimeSeriesAssociationCol.OWNER_ID],
        )
        for association in associations
        if _is_natural_units(association)
    }
    return build_capacity_by_owner(owners, system.get(SiennaSchemasSystem.COMPONENTS, {}))


def _open_store(h5_file: IO[bytes], associations: list[dict[str, Any]], staging_dir: Path) -> Store:
    """Open the sidecar as a store that holds the rows of the document.

    The file arrives as a stream and the store needs a path, so the bytes go to staging
    scratch first. The sidecar holds arrays only, and its catalog is the document's rows.
    """
    store_dir = staging_dir / InfraStoreSidecar.STAGING_DIRECTORY
    store_dir.mkdir(parents=True, exist_ok=True)
    path = store_dir / InfraStoreSidecar.SCRATCH_FILENAME
    with path.open("wb") as scratch:
        shutil.copyfileobj(h5_file, scratch)
    store = Store.open_without_catalog(str(path))
    store.import_time_series_associations_openapi(json.dumps(associations))
    return store


def _stream_series_to_parquet(
    store: Store,
    association: dict[str, Any],
    *,
    capacity: float | None,
    component: str,
    key_dir: Path,
) -> None:
    """Write one series to parquet a block at a time, one file per block.

    Only ``_TIME_SERIES_CHUNK_ROWS`` rows are read and converted at once. Each block becomes
    its own parquet file in the per-key directory, which is scanned back as one lazy frame.
    """
    series_id = association[TimeSeriesAssociationCol.ASSOCIATION_ID]
    length = association[TimeSeriesAssociationCol.LENGTH]
    initial_time = pd.Timestamp(
        association[TimeSeriesAssociationCol.INITIAL_TIMESTAMP]
    ).tz_localize(None)
    step = pd.Timedelta(association[TimeSeriesAssociationCol.RESOLUTION])
    for offset in range(0, length, _TIME_SERIES_CHUNK_ROWS):
        block_start = initial_time + step * offset
        block = _convert_to_per_unit(
            store.read_by_id(
                series_id,
                start_time=block_start.to_pydatetime(),
                len=min(_TIME_SERIES_CHUNK_ROWS, length - offset),
            ).data,
            capacity,
        )
        snapshots = pd.date_range(start=block_start, periods=len(block), freq=step)
        pl.DataFrame(
            {
                StagedTimeSeriesCol.SNAPSHOT: snapshots.to_numpy(),
                StagedTimeSeriesCol.VALUE: block,
            }
        ).with_columns(pl.lit(component).alias(StagedTimeSeriesCol.COMPONENT)).write_parquet(
            key_dir / f"{series_id}_{offset}.parquet"
        )


def _name_by_owner(system: dict[str, Any]) -> dict[tuple[str, int], str]:
    """Map each named component's ``(type, id)`` to its name, for resolving association owners.

    Nameless topology components (Arcs) are never time-series or extension owners, so they
    are skipped rather than indexed.
    """
    return {
        (sienna_type, component[SiennaACBusCol.ID]): component[SiennaACBusCol.NAME]
        for sienna_type, components in system.get(SiennaSchemasSystem.COMPONENTS, {}).items()
        for component in components
        if SiennaACBusCol.NAME in component
    }
