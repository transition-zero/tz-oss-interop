"""The canonical name of each column of a raw table: its OSeMOSYS set columns and its value."""

from __future__ import annotations

from interop.plugins.shared.osemosys_canonical.constants import (
    RAW_VALUE_COL,
    REGION,
    START_REGION,
    VALUE_COL,
)
from interop.plugins.shared.osemosys_canonical.schema import CanonicalParameter, CanonicalSchema


def build_canonical_columns(schema: CanonicalSchema, raw_columns: list[str]) -> dict[str, str]:
    """`_REGION` becomes `end_region`, and a column that names no OSeMOSYS set keeps its name."""
    names = {**schema.osemosys_set_columns, RAW_VALUE_COL: VALUE_COL}
    return {column: names.get(column, column) for column in raw_columns}


def build_parameter_columns(
    schema: CanonicalSchema, parameter: CanonicalParameter, raw_columns: list[str]
) -> dict[str, str]:
    """The `region` column of a table whose canonical key holds `start_region` becomes
    `start_region`."""
    columns = build_canonical_columns(schema, raw_columns)
    if START_REGION not in parameter.key:
        return columns
    return {raw: START_REGION if name == REGION else name for raw, name in columns.items()}
