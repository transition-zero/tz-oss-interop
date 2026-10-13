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
    PLANNED_DIRECTORY,
    TABLE_DIRECTORIES,
    TABLE_KEY_SEPARATOR,
    TableKind,
)
from interop.plugins.shared.osemosys_canonical.mapping_inputs import MappingInputs
from interop.plugins.shared.osemosys_canonical.mappings import OsemosysMappings
from interop.plugins.shared.osemosys_canonical.metadata import map_metadata
from interop.plugins.shared.osemosys_canonical.parameter_mapping import (
    ParameterPlan,
    build_parameter_plan,
    map_parameters,
)
from interop.plugins.shared.osemosys_canonical.raw_stage import RawStage
from interop.plugins.shared.osemosys_canonical.schema import load_canonical_schema
from interop.plugins.shared.osemosys_canonical.set_mapping import map_sets

# A parameter or an extension table can hold billions of rows, so `State` keeps it as a time
# series, which no reader collects in full.
_TIME_SERIES_KINDS = frozenset({TableKind.PARAMETER, TableKind.EXTENSION})
# The annotations read the written sets and parameters, so no parameter plan computes twice.
_ANNOTATED_KINDS = frozenset({TableKind.SET, TableKind.PARAMETER})


class CanonicalTable(NamedTuple):
    kind: TableKind
    name: str
    table: pl.LazyFrame


def build_canonical_stage(
    raw: RawStage, mappings: OsemosysMappings, recorder: EventRecorder, staging_dir: Path
) -> State:
    inputs = MappingInputs(raw, mappings, load_canonical_schema())
    mapped = _write_canonical_tables(_map_raw_stage(inputs, recorder, staging_dir), staging_dir)
    annotated = {table.name: table.table for table in mapped if table.kind in _ANNOTATED_KINDS}
    annotations = map_annotations(annotated, mappings.objects, recorder)
    tables = _build_canonical_tables(
        TableKind.ANNOTATION, {name: table.lazy() for name, table in annotations.items()}
    )
    return _build_state([*mapped, *_write_canonical_tables(tables, staging_dir)], staging_dir)


def _map_raw_stage(
    inputs: MappingInputs, recorder: EventRecorder, staging_dir: Path
) -> list[CanonicalTable]:
    sets = map_sets(inputs, recorder)
    plan = _write_planned_tables(build_parameter_plan(inputs, sets.sets, recorder), staging_dir)
    parameters = map_parameters(inputs, plan, recorder)
    return [
        *_build_canonical_tables(TableKind.SET, sets.sets),
        *_build_canonical_tables(TableKind.EXTENSION, sets.extensions),
        *_build_canonical_tables(TableKind.PARAMETER, parameters.parameters),
        *_build_canonical_tables(TableKind.EXTENSION, parameters.extensions),
        *_build_canonical_tables(TableKind.METADATA, map_metadata(inputs, parameters, recorder)),
    ]


def _write_planned_tables(plan: ParameterPlan, staging_dir: Path) -> ParameterPlan:
    """A table that a row maps can join and aggregate, so it computes once here; an automatic
    match only renames the raw scan."""
    directory = staging_dir / PLANNED_DIRECTORY
    grouped = {group.canonical for group in plan.row_groups}
    planned = {
        name: _write_table(table, directory / f"{name}{PARQUET_SUFFIX}")
        if name in grouped
        else table
        for name, table in plan.planned.items()
    }
    return plan._replace(planned=planned)


def _build_canonical_tables(
    kind: TableKind, tables: dict[str, pl.LazyFrame]
) -> list[CanonicalTable]:
    return [CanonicalTable(kind, name, table) for name, table in tables.items()]


def _write_canonical_tables(
    tables: list[CanonicalTable], staging_dir: Path
) -> list[CanonicalTable]:
    directory = staging_dir / CANONICAL_DIRECTORY
    return [
        canonical._replace(
            table=_write_table(canonical.table, directory / build_table_path(canonical))
        )
        for canonical in tables
    ]


def _write_table(table: pl.LazyFrame, path: Path) -> pl.LazyFrame:
    path.parent.mkdir(parents=True, exist_ok=True)
    table.sink_parquet(path)
    return pl.scan_parquet(path)


def build_table_path(canonical: CanonicalTable) -> Path:
    return Path(TABLE_DIRECTORIES[canonical.kind], f"{canonical.name}{PARQUET_SUFFIX}")


def _build_state(tables: list[CanonicalTable], staging_dir: Path) -> State:
    state = State(staging_dir=staging_dir)
    for canonical in tables:
        if canonical.kind in _TIME_SERIES_KINDS:
            state.source_time_series[(canonical.kind, canonical.name)] = canonical.table
        else:
            state.source_topology[build_table_key(canonical.kind, canonical.name)] = canonical.table
    return state


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
