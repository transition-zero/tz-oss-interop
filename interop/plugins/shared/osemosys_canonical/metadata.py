"""The metadata of the canonical stage: the default of each parameter, the units and the schema
version."""

from __future__ import annotations

import polars as pl

from interop.plugins.shared.osemosys_canonical.constants import MetadataCol, MetadataTable
from interop.plugins.shared.osemosys_canonical.mappings import Units
from interop.plugins.shared.osemosys_canonical.schema import CanonicalSchema

_DEFAULTS_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    MetadataCol.PARAMETER: pl.Utf8,
    MetadataCol.DEFAULT: pl.Float64,
}
_UNITS_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    MetadataCol.QUANTITY: pl.Utf8,
    MetadataCol.UNIT: pl.Utf8,
}
_SCHEMA_VERSION_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    MetadataCol.SCHEMA_VERSION: pl.Int64,
}


def build_metadata_tables(
    schema: CanonicalSchema, declared_defaults: dict[str, float | None], units: Units
) -> dict[str, pl.LazyFrame]:
    return {
        MetadataTable.DEFAULTS: _build_defaults_table(schema, declared_defaults).lazy(),
        MetadataTable.UNITS: _build_units_table(units).lazy(),
        MetadataTable.SCHEMA: _build_schema_table(schema).lazy(),
    }


def _build_defaults_table(
    schema: CanonicalSchema, declared_defaults: dict[str, float | None]
) -> pl.DataFrame:
    """One row for each canonical parameter, with the default that applies to this model."""
    rows = [
        {
            MetadataCol.PARAMETER: name,
            MetadataCol.DEFAULT: _choose_default(name, schema, declared_defaults),
        }
        for name in schema.parameters
    ]
    return pl.DataFrame(rows, schema=_DEFAULTS_SCHEMA)


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
        {MetadataCol.QUANTITY: quantity, MetadataCol.UNIT: str(unit)}
        for quantity, unit in units.model_dump(exclude_none=True).items()
    ]
    return pl.DataFrame(rows, schema=_UNITS_SCHEMA)


def _build_schema_table(schema: CanonicalSchema) -> pl.DataFrame:
    row = {MetadataCol.SCHEMA_VERSION: schema.schema_version}
    return pl.DataFrame([row], schema=_SCHEMA_VERSION_SCHEMA)
