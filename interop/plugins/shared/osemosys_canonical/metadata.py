"""The metadata of the canonical stage: the default of each parameter, the units and the schema
version."""

from __future__ import annotations

import polars as pl

from interop.plugins.shared.osemosys_canonical.constants import (
    MetadataColumn,
    MetadataTable,
    TableKind,
)
from interop.plugins.shared.osemosys_canonical.mappings import Units
from interop.plugins.shared.osemosys_canonical.parameter_mapping import MappedParameters
from interop.plugins.shared.osemosys_canonical.schema import CanonicalSchema

_DEFAULTS_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    MetadataColumn.KIND: pl.Utf8,
    MetadataColumn.PARAMETER: pl.Utf8,
    MetadataColumn.DEFAULT: pl.Float64,
}
_UNITS_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    MetadataColumn.QUANTITY: pl.Utf8,
    MetadataColumn.UNIT: pl.Utf8,
}
_SCHEMA_VERSION_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    MetadataColumn.SCHEMA_VERSION: pl.Int64,
}


def build_metadata_tables(
    schema: CanonicalSchema, parameters: MappedParameters, units: Units
) -> dict[str, pl.LazyFrame]:
    return {
        MetadataTable.DEFAULTS: _build_defaults_table(schema, parameters).lazy(),
        MetadataTable.UNITS: _build_units_table(units).lazy(),
        MetadataTable.SCHEMA: _build_schema_table(schema).lazy(),
    }


def _build_defaults_table(schema: CanonicalSchema, parameters: MappedParameters) -> pl.DataFrame:
    """One row for each canonical parameter and each extension table, with the default that
    applies to this model."""
    canonical_defaults = {
        name: _choose_default(name, schema, parameters.parameter_defaults)
        for name in schema.parameters
    }
    rows = [
        *_build_default_rows(TableKind.PARAMETER, canonical_defaults),
        *_build_default_rows(TableKind.EXTENSION, parameters.extension_defaults),
    ]
    return pl.DataFrame(rows, schema=_DEFAULTS_SCHEMA)


def _build_default_rows(
    kind: TableKind, defaults: dict[str, float | None]
) -> list[dict[str, object]]:
    return [
        {MetadataColumn.KIND: kind, MetadataColumn.PARAMETER: name, MetadataColumn.DEFAULT: default}
        for name, default in defaults.items()
    ]


def _choose_default(
    name: str, schema: CanonicalSchema, declared_defaults: dict[str, float | None]
) -> float | None:
    """The model's declared default, else the schema's default, else that of `default_from`."""
    declared = declared_defaults.get(name)
    if declared is not None:
        return declared
    entry = schema.parameters[name]
    if entry.default is not None or entry.default_from is None:
        return entry.default
    return _choose_default(entry.default_from, schema, declared_defaults)


def _build_units_table(units: Units) -> pl.DataFrame:
    """One row for each unit that the user mappings file states."""
    rows = [
        {MetadataColumn.QUANTITY: quantity, MetadataColumn.UNIT: str(unit)}
        for quantity, unit in units.model_dump(exclude_none=True).items()
    ]
    return pl.DataFrame(rows, schema=_UNITS_SCHEMA)


def _build_schema_table(schema: CanonicalSchema) -> pl.DataFrame:
    row = {MetadataColumn.SCHEMA_VERSION: schema.schema_version}
    return pl.DataFrame([row], schema=_SCHEMA_VERSION_SCHEMA)
