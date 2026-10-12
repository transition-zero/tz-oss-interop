from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

import polars as pl

from interop.core.pipeline import State
from interop.core.reporting import EventRecorder
from interop.plugins.shared.osemosys_canonical.annotations import map_annotations
from interop.plugins.shared.osemosys_canonical.constants import (
    CANONICAL_DIRECTORY,
    PARQUET_SUFFIX,
    TABLE_DIRECTORIES,
    TABLE_KEY_SEPARATOR,
    TIMESLICE,
    TableKind,
)
from interop.plugins.shared.osemosys_canonical.mapping_inputs import MappingInputs
from interop.plugins.shared.osemosys_canonical.mappings import OsemosysMappings
from interop.plugins.shared.osemosys_canonical.metadata import build_metadata_tables
from interop.plugins.shared.osemosys_canonical.parameter_mapping import map_parameters
from interop.plugins.shared.osemosys_canonical.raw_stage import RawStage
from interop.plugins.shared.osemosys_canonical.schema import load_canonical_schema
from interop.plugins.shared.osemosys_canonical.set_mapping import map_sets

_TIME_SERIES_KINDS = frozenset({TableKind.PARAMETER, TableKind.EXTENSION})


class CanonicalTable(NamedTuple):
    kind: TableKind
    name: str
    table: pl.LazyFrame


def build_canonical_stage(
    raw: RawStage, mappings: OsemosysMappings, recorder: EventRecorder, staging_dir: Path
) -> State:
    tables = _map_raw_stage(raw, mappings, recorder)
    written = [_write_canonical_table(table, staging_dir) for table in tables]
    return _build_state(written, staging_dir)


def _map_raw_stage(
    raw: RawStage, mappings: OsemosysMappings, recorder: EventRecorder
) -> list[CanonicalTable]:
    inputs = MappingInputs(raw, mappings, load_canonical_schema())
    sets = map_sets(inputs, recorder)
    parameters = map_parameters(inputs, sets.sets, recorder)
    metadata = build_metadata_tables(inputs.schema, parameters, mappings.units)
    canonical = {**sets.sets, **parameters.parameters}
    annotations = map_annotations(canonical, mappings.objects, recorder)
    return [
        *_build_canonical_tables(TableKind.SET, sets.sets),
        *_build_canonical_tables(TableKind.EXTENSION, sets.extensions),
        *_build_canonical_tables(TableKind.PARAMETER, parameters.parameters),
        *_build_canonical_tables(TableKind.EXTENSION, parameters.extensions),
        *_build_canonical_tables(TableKind.METADATA, metadata),
        *_build_canonical_tables(
            TableKind.ANNOTATION, {name: table.lazy() for name, table in annotations.items()}
        ),
    ]


def _build_canonical_tables(
    kind: TableKind, tables: dict[str, pl.LazyFrame]
) -> list[CanonicalTable]:
    return [CanonicalTable(kind, name, table) for name, table in tables.items()]


def _write_canonical_table(canonical: CanonicalTable, staging_dir: Path) -> CanonicalTable:
    path = staging_dir / CANONICAL_DIRECTORY / build_table_path(canonical)
    path.parent.mkdir(parents=True, exist_ok=True)
    canonical.table.sink_parquet(path)
    return canonical._replace(table=pl.scan_parquet(path))


def build_table_path(canonical: CanonicalTable) -> Path:
    return Path(TABLE_DIRECTORIES[canonical.kind], f"{canonical.name}{PARQUET_SUFFIX}")


def _build_state(tables: list[CanonicalTable], staging_dir: Path) -> State:
    state = State(staging_dir=staging_dir)
    for canonical in tables:
        if _is_time_series(canonical):
            state.source_time_series[(canonical.kind, canonical.name)] = canonical.table
        else:
            state.source_topology[build_table_key(canonical.kind, canonical.name)] = canonical.table
    return state


def _is_time_series(canonical: CanonicalTable) -> bool:
    columns = canonical.table.collect_schema().names()
    return canonical.kind in _TIME_SERIES_KINDS and TIMESLICE in columns


def build_table_key(kind: TableKind, name: str) -> str:
    return f"{kind}{TABLE_KEY_SEPARATOR}{name}"


def list_canonical_tables(state: State) -> list[CanonicalTable]:
    topology = [
        CanonicalTable(*_parse_table_key(key), table)
        for key, table in state.source_topology.items()
    ]
    time_series = [
        CanonicalTable(TableKind(kind), name, table)
        for (kind, name), table in state.source_time_series.items()
    ]
    return [*topology, *time_series]


def _parse_table_key(key: str) -> tuple[TableKind, str]:
    kind, name = key.split(TABLE_KEY_SEPARATOR, maxsplit=1)
    return TableKind(kind), name
