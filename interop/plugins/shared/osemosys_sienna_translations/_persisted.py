"""The rows of a parameter that a component applies or whose values extensions.json holds.

A step that applies the values of a parameter, or writes them to an extension record, notes the
members whose rows it read, so the report of the parameters that no step applies leaves those
rows out and names only what still has no home.
"""

from __future__ import annotations

from collections.abc import Sequence

import polars as pl

from interop.core.extensions import ExtensionKind
from interop.core.pipeline import State
from interop.plugins.shared.osemosys_canonical.constants import (
    END_REGION,
    FUEL,
    POLLUTANT,
    REGION,
    REGION_GROUP,
    START_REGION,
    STORAGE,
    TECHNOLOGY,
)
from interop.plugins.shared.osemosys_sienna_constants import (
    OSEMOSYS_SIENNA_PERSISTED,
    REGION_NAME_SEPARATOR,
    SERIES_KEY_SEPARATOR,
)

MEMBER_KEY = "member_key"
# The key of a row with no region and no member, which stands for every row of its parameter.
_ALL_ROWS = "all"

# The columns that place a row, in the order that its key names them.
_PLACE_COLUMNS = (REGION_GROUP, REGION, START_REGION, END_REGION)
# The columns that name the member of a row, in the order that the report prefers them.
MEMBER_COLUMNS = (TECHNOLOGY, STORAGE, FUEL, POLLUTANT)


def express_member_key(columns: Sequence[str]) -> pl.Expr:
    """The region group and the region of a row, then its first member column, joined by `/`."""
    parts = [column for column in _PLACE_COLUMNS if column in columns]
    member = next((column for column in MEMBER_COLUMNS if column in columns), None)
    if member is not None:
        parts.append(member)
    if not parts:
        return pl.lit(_ALL_ROWS)
    return pl.concat_str(parts, separator=REGION_NAME_SEPARATOR)


def set_persisted_rows(
    state: State,
    kind: ExtensionKind,
    parameter: str,
    tables: Sequence[pl.DataFrame],
    scope: str = "",
) -> None:
    """Note the members of each table, whose values the records of `kind` hold or apply.

    Each table keys its members by its own columns, so tables of two key sets can be noted at
    once. `scope` keeps apart two notes of one kind and parameter, so neither replaces the other.
    """
    keys = pl.concat(
        [table.select(express_member_key(table.columns).alias(MEMBER_KEY)) for table in tables]
    )
    state.source_time_series[_build_key(kind, scope, parameter)] = keys.unique().lazy()


def drop_persisted_rows(state: State, parameter: str, rows: pl.DataFrame) -> pl.DataFrame:
    """The rows of `parameter` whose member no extension record holds."""
    tables = [
        table
        for (owner, name), table in state.source_time_series.items()
        if owner == OSEMOSYS_SIENNA_PERSISTED
        and name.rpartition(SERIES_KEY_SEPARATOR)[2] == parameter
    ]
    if not tables or rows.height == 0:
        return rows
    held = pl.concat(tables).collect()
    keyed = rows.with_columns(express_member_key(rows.columns).alias(MEMBER_KEY))
    return keyed.join(held, on=MEMBER_KEY, how="anti").drop(MEMBER_KEY)


def _build_key(kind: ExtensionKind, scope: str, parameter: str) -> tuple[str, str]:
    name = SERIES_KEY_SEPARATOR.join((kind, scope, parameter))
    return (OSEMOSYS_SIENNA_PERSISTED, name)
