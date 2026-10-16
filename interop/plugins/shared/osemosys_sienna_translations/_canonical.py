"""Reads of the canonical OSeMOSYS stage, for one operations year.

A parameter table is sparse: a key that the model does not state takes the default in
`metadata/defaults`. Each read of a parameter filters on the year before it collects, so a
read stays small on a model with millions of parameter rows.
"""

from __future__ import annotations

from collections.abc import Sequence

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.osemosys_canonical.canonical_stage import build_table_key
from interop.plugins.shared.osemosys_canonical.constants import (
    OPERATING_MODE,
    VALUE_COL,
    YEAR,
    MetadataColumn,
    MetadataTable,
    TableKind,
)
from interop.plugins.shared.osemosys_canonical.schema import load_canonical_schema
from interop.plugins.shared.osemosys_sienna_constants import OPERATIONS_MODE


def list_set_members(state: State, set_name: str) -> list[str]:
    """The members of a canonical set, in the order of the set. A set with no table has none."""
    table = state.source_topology.get(build_table_key(TableKind.SET, set_name))
    if table is None:
        return []
    return [str(member) for member in table.select(VALUE_COL).collect()[VALUE_COL].to_list()]


def read_operations_mode(state: State) -> str:
    """Mode `1` when the model holds it, else the first member of the operating mode set."""
    modes = list_set_members(state, OPERATING_MODE)
    if OPERATIONS_MODE in modes or not modes:
        return OPERATIONS_MODE
    return modes[0]


def list_model_years(state: State) -> list[int]:
    """The members of the `year` set that are whole numbers, in ascending order."""
    return sorted(int(member) for member in list_set_members(state, YEAR) if member.isdigit())


def read_annotations(state: State, set_name: str) -> pl.DataFrame:
    """The annotation table of a set: one row for each region and member."""
    return state.source_topology[build_table_key(TableKind.ANNOTATION, set_name)].collect()


def read_parameter(state: State, name: str, year: int) -> pl.DataFrame:
    """The rows that the model states for a parameter, at one year when it has a year column."""
    table = state.source_time_series.get((TableKind.PARAMETER, name))
    if table is None:
        return _build_empty_parameter(name)
    if YEAR in table.collect_schema().names():
        table = table.filter(pl.col(YEAR) == str(year))
    return table.collect()


def read_parameter_for_years(state: State, name: str, years: Sequence[int]) -> pl.DataFrame:
    """The rows that the model states for a parameter keyed by year, in the given years."""
    table = state.source_time_series.get((TableKind.PARAMETER, name))
    if table is None:
        return _build_empty_parameter(name)
    return table.filter(pl.col(YEAR).is_in([str(year) for year in years])).collect()


def read_mode_parameter(state: State, name: str, year: int, mode: str) -> pl.DataFrame:
    """The rows that the model states for a parameter keyed by operating mode, at one mode."""
    return read_parameter(state, name, year).filter(pl.col(OPERATING_MODE) == mode)


def read_parameter_with_defaults(
    state: State, name: str, year: int, keys: pl.DataFrame
) -> pl.DataFrame:
    """One row for each row of `keys`, with the stated value or else the default.

    `keys` holds key columns of the parameter other than `year`. A parameter whose default
    comes from another parameter keeps a null where the model states no value.
    """
    stated = read_parameter(state, name, year)
    stated = stated.drop(YEAR) if YEAR in stated.columns else stated
    joined = keys.join(stated, on=keys.columns, how="left")
    default = find_parameter_default(state, name)
    return joined if default is None else joined.with_columns(pl.col(VALUE_COL).fill_null(default))


def find_parameter_default(state: State, name: str) -> float | None:
    """The default of a parameter, or None when it has none or takes it from another parameter."""
    defaults = state.source_topology.get(
        build_table_key(TableKind.METADATA, MetadataTable.DEFAULTS)
    )
    if defaults is None:
        return None
    found = (
        defaults.filter(
            (pl.col(MetadataColumn.KIND) == TableKind.PARAMETER)
            & (pl.col(MetadataColumn.PARAMETER) == name)
        )
        .select(MetadataColumn.DEFAULT)
        .collect()
    )
    return None if found.height == 0 else found.item(0, 0)


def _build_empty_parameter(name: str) -> pl.DataFrame:
    columns = load_canonical_schema().parameters[name].column_names
    return pl.DataFrame(schema={**dict.fromkeys(columns, pl.Utf8), VALUE_COL: pl.Float64})
