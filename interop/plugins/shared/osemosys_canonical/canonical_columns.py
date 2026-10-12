from __future__ import annotations

from interop.plugins.shared.osemosys_canonical.constants import (
    END_REGION,
    RAW_VALUE_COL,
    REGION,
    START_REGION,
    VALUE_COL,
)
from interop.plugins.shared.osemosys_canonical.schema import CanonicalParameter, CanonicalSchema


def build_canonical_columns(schema: CanonicalSchema, raw_columns: list[str]) -> dict[str, str]:
    names = {**schema.osemosys_set_columns, RAW_VALUE_COL: VALUE_COL}
    return {column: names.get(column, column) for column in raw_columns}


def build_parameter_columns(
    schema: CanonicalSchema, parameter: CanonicalParameter, raw_columns: list[str]
) -> dict[str, str]:
    columns = build_canonical_columns(schema, raw_columns)
    return _build_start_region_columns(columns) if START_REGION in parameter.columns else columns


def build_extension_columns(schema: CanonicalSchema, raw_columns: list[str]) -> dict[str, str]:
    columns = build_canonical_columns(schema, raw_columns)
    return _build_start_region_columns(columns) if END_REGION in columns.values() else columns


def _build_start_region_columns(columns: dict[str, str]) -> dict[str, str]:
    return {raw: START_REGION if name == REGION else name for raw, name in columns.items()}
