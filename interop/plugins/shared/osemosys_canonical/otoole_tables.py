"""Turn the canonical OSeMOSYS tables back into the files of an otoole model.

The canonical schema states the OSeMOSYS name and the column order of each parameter, so each
rename here is the rename of the reader, read the other way. An extension table keeps the raw
name it came in under, and each of its columns takes the OSeMOSYS name of the set that the
reader matched it to.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import NamedTuple

import polars as pl

from interop.plugins.shared.osemosys_canonical.canonical_stage import CanonicalTable
from interop.plugins.shared.osemosys_canonical.constants import (
    CORE_OSEMOSYS_ORIGIN,
    END_REGION,
    OSEMOSYS_SECOND_REGION,
    RAW_VALUE_COL,
    REGION,
    START_REGION,
    VALUE_COL,
    MetadataColumn,
    MetadataTable,
    TableKind,
)
from interop.plugins.shared.osemosys_canonical.mappings import Units
from interop.plugins.shared.osemosys_canonical.otoole_config import (
    OtooleEntryType,
    OtooleTableEntry,
)
from interop.plugins.shared.osemosys_canonical.schema import (
    CanonicalParameter,
    CanonicalSchema,
    load_canonical_schema,
)

CORE_ORIGINS = frozenset({CORE_OSEMOSYS_ORIGIN})

HeldTables = dict[TableKind, dict[str, pl.LazyFrame]]


class OtooleFile(NamedTuple):
    """One CSV file of an otoole model: `stem` names it, and `entry` declares it."""

    stem: str
    table: pl.LazyFrame
    entry: OtooleTableEntry


class TableDefaults(NamedTuple):
    """The default of each parameter and of each extension table, by canonical name."""

    parameters: dict[str, float | None]
    extensions: dict[str, float | None]


class OtooleModel(NamedTuple):
    """`left_out` names the parameter set that the model does not declare, by its origin."""

    files: list[OtooleFile]
    units: Units
    left_out: dict[str, str]


def build_schema_origins() -> frozenset[str]:
    """Every origin that the canonical schema states, which asks for every parameter."""
    return frozenset(entry.origin for entry in load_canonical_schema().parameters.values())


def build_otoole_model(tables: Sequence[CanonicalTable], origins: frozenset[str]) -> OtooleModel:
    schema = load_canonical_schema()
    held = _build_tables_by_kind(tables)
    defaults = _build_table_defaults(held)
    parameters = held[TableKind.PARAMETER]
    files = [
        *_build_set_files(schema, held[TableKind.SET]),
        *_build_parameter_files(schema, defaults, parameters, origins),
        *_build_extension_files(schema, defaults, held[TableKind.EXTENSION]),
    ]
    return OtooleModel(files, _build_units(held), _build_left_out(schema, parameters, origins))


def _build_tables_by_kind(tables: Sequence[CanonicalTable]) -> HeldTables:
    held: HeldTables = {kind: {} for kind in TableKind}
    for canonical in tables:
        held[canonical.kind][canonical.name] = canonical.table
    return held


def _build_table_defaults(held: HeldTables) -> TableDefaults:
    table = held[TableKind.METADATA].get(MetadataTable.DEFAULTS)
    if table is None:
        return TableDefaults({}, {})
    rows = table.collect()
    return TableDefaults(
        parameters=_build_defaults_of_kind(rows, TableKind.PARAMETER),
        extensions=_build_defaults_of_kind(rows, TableKind.EXTENSION),
    )


def _build_defaults_of_kind(rows: pl.DataFrame, kind: TableKind) -> dict[str, float | None]:
    matching = rows.filter(pl.col(MetadataColumn.KIND) == kind)
    names = matching[MetadataColumn.PARAMETER]
    return dict(zip(names, matching[MetadataColumn.DEFAULT], strict=True))


def _build_units(held: HeldTables) -> Units:
    """A stage with no units table states no units, which a Sienna leg fills before this runs."""
    table = held[TableKind.METADATA].get(MetadataTable.UNITS)
    if table is None:
        return Units()
    rows = table.collect()
    quantities = rows[MetadataColumn.QUANTITY]
    return Units.model_validate(dict(zip(quantities, rows[MetadataColumn.UNIT], strict=True)))


def _build_set_files(schema: CanonicalSchema, sets: dict[str, pl.LazyFrame]) -> list[OtooleFile]:
    return [_build_set_file(schema, name, table) for name, table in sets.items()]


def _build_set_file(schema: CanonicalSchema, name: str, table: pl.LazyFrame) -> OtooleFile:
    stem = schema.get_osemosys_set_name(name)
    members = table.rename({VALUE_COL: RAW_VALUE_COL}).select(RAW_VALUE_COL)
    return OtooleFile(stem, members, OtooleTableEntry(stem, OtooleEntryType.SET, [], None))


def _build_parameter_files(
    schema: CanonicalSchema,
    defaults: TableDefaults,
    parameters: dict[str, pl.LazyFrame],
    origins: frozenset[str],
) -> list[OtooleFile]:
    return [
        _build_parameter_file(schema, defaults, name, table)
        for name, table in parameters.items()
        if _is_written_parameter(schema, name, origins)
    ]


def _build_parameter_file(
    schema: CanonicalSchema, defaults: TableDefaults, name: str, table: pl.LazyFrame
) -> OtooleFile:
    parameter = schema.parameters[name]
    stem = parameter.osemosys_name
    rows = table.rename(_build_parameter_column_names(parameter)).select(
        [*parameter.osemosys_columns, RAW_VALUE_COL]
    )
    entry = OtooleTableEntry(
        stem, OtooleEntryType.PARAM, parameter.osemosys_columns, defaults.parameters.get(name)
    )
    return OtooleFile(stem, rows, entry)


def _build_parameter_column_names(parameter: CanonicalParameter) -> dict[str, str]:
    names = dict(zip(parameter.column_names, parameter.osemosys_columns, strict=True))
    return {**names, VALUE_COL: RAW_VALUE_COL}


def _build_extension_files(
    schema: CanonicalSchema, defaults: TableDefaults, extensions: dict[str, pl.LazyFrame]
) -> list[OtooleFile]:
    return [
        _build_extension_file(schema, defaults, name, table) for name, table in extensions.items()
    ]


def _build_extension_file(
    schema: CanonicalSchema, defaults: TableDefaults, name: str, table: pl.LazyFrame
) -> OtooleFile:
    columns = _build_extension_column_names(schema, table.collect_schema().names())
    entry = _build_extension_entry(name, list(columns.values()), defaults)
    return OtooleFile(name, table.rename(columns), entry)


def _build_extension_entry(
    name: str, columns: list[str], defaults: TableDefaults
) -> OtooleTableEntry:
    """A raw set that no canonical set matches holds its members alone, so it stays a set."""
    if name not in defaults.extensions:
        return OtooleTableEntry(name, OtooleEntryType.SET, [], None)
    indices = [column for column in columns if column != RAW_VALUE_COL]
    return OtooleTableEntry(name, OtooleEntryType.PARAM, indices, defaults.extensions[name])


def _build_extension_column_names(schema: CanonicalSchema, columns: list[str]) -> dict[str, str]:
    names = _build_osemosys_column_names(schema)
    return {column: names.get(column, column) for column in columns}


def _build_osemosys_column_names(schema: CanonicalSchema) -> dict[str, str]:
    """`start_region` and `end_region` both come from the region set, under its two names."""
    names = {canonical: osemosys for osemosys, canonical in schema.osemosys_set_columns.items()}
    return {
        **names,
        START_REGION: schema.get_osemosys_set_name(REGION),
        END_REGION: OSEMOSYS_SECOND_REGION,
        VALUE_COL: RAW_VALUE_COL,
    }


def _is_written_parameter(schema: CanonicalSchema, name: str, origins: frozenset[str]) -> bool:
    return schema.parameters[name].origin in origins


def _build_left_out(
    schema: CanonicalSchema, parameters: dict[str, pl.LazyFrame], origins: frozenset[str]
) -> dict[str, str]:
    return {
        schema.parameters[name].osemosys_name: schema.parameters[name].origin
        for name in parameters
        if not _is_written_parameter(schema, name, origins)
    }
