"""Put a canonical OSeMOSYS table on the destination side of `State`.

The canonical schema states the key columns of each parameter, so a step hands over rows and
the schema of the table follows. The `year` column holds an integer, as a year read from an
otoole CSV file does; every other key column holds the name of a set member.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.osemosys_canonical.canonical_stage import (
    CanonicalTable,
    list_destination_canonical_tables,
    set_destination_canonical_table,
)
from interop.plugins.shared.osemosys_canonical.constants import (
    VALUE_COL,
    YEAR,
    TableKind,
)
from interop.plugins.shared.osemosys_canonical.schema import load_canonical_schema

ParameterRows = Sequence[dict[str, Any]]

_SET_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {VALUE_COL: pl.Utf8}


def build_parameter_schema(parameter: str) -> dict[str, pl.DataType | type[pl.DataType]]:
    """The columns of one canonical parameter table, in the order the schema states them."""
    entry = load_canonical_schema().parameters[parameter]
    columns: dict[str, pl.DataType | type[pl.DataType]] = {
        column: pl.Int64 if entry.get_column_set(column) == YEAR else pl.Utf8
        for column in entry.column_names
    }
    return {**columns, VALUE_COL: pl.Float64}


def build_rows_over_years(
    parameter: str, keys: Mapping[str, Any], value: float, years: Sequence[int]
) -> ParameterRows:
    """One row of `parameter` for each year in `years`, or one row where it takes no year."""
    if YEAR not in load_canonical_schema().parameters[parameter].column_names:
        return [{**keys, VALUE_COL: value}]
    return [{**keys, YEAR: year, VALUE_COL: value} for year in years]


def set_parameter_table(state: State, parameter: str, rows: ParameterRows) -> None:
    """Write one canonical parameter table, which has no rows where the leg built none."""
    table = pl.DataFrame(list(rows), schema=build_parameter_schema(parameter))
    set_destination_canonical_table(
        state, CanonicalTable(TableKind.PARAMETER, parameter, table.lazy())
    )


def append_parameter_rows(state: State, parameter: str, rows: ParameterRows) -> None:
    """Add rows to one canonical parameter table, and keep the rows another group wrote.

    Two component groups can fill one parameter: a Sienna generator and the technology that
    discharges a Sienna storage both state a `ResidualCapacity`.
    """
    written = list_destination_parameter_tables(state).get(parameter)
    table = pl.DataFrame(list(rows), schema=build_parameter_schema(parameter))
    whole = table if written is None else pl.concat([written.collect(), table])
    set_destination_canonical_table(
        state, CanonicalTable(TableKind.PARAMETER, parameter, whole.lazy())
    )


def set_set_table(state: State, set_name: str, members: Sequence[str]) -> None:
    """Write one canonical set table, whose members keep the order they were built in."""
    table = pl.DataFrame({VALUE_COL: list(members)}, schema=_SET_SCHEMA)
    set_destination_canonical_table(state, CanonicalTable(TableKind.SET, set_name, table.lazy()))


def set_metadata_table(state: State, name: str, table: pl.DataFrame) -> None:
    set_destination_canonical_table(state, CanonicalTable(TableKind.METADATA, name, table.lazy()))


def list_destination_parameter_tables(state: State) -> dict[str, pl.LazyFrame]:
    """The canonical parameter tables that the steps of this hop have written, by name."""
    return {
        canonical.name: canonical.table
        for canonical in list_destination_canonical_tables(state)
        if canonical.kind is TableKind.PARAMETER
    }
