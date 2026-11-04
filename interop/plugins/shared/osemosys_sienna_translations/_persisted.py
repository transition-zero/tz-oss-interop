"""The rows of a parameter that a component applies or whose values extensions.json holds.

A step that applies the values of a parameter, or writes them to an extension record, notes the
members whose rows it read, so the report of the parameters that no step applies leaves those
rows out and names only what still has no home.
"""

from __future__ import annotations

from collections.abc import Sequence

import polars as pl

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
from interop.plugins.shared.osemosys_sienna_constants import REGION_NAME_SEPARATOR

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


def set_persisted_rows(state: State, parameter: str, tables: Sequence[pl.DataFrame]) -> None:
    """Note the members of each table, whose values a component or an extension record holds.

    Each table keys its members by its own columns, so tables of two key sets can be noted at
    once. A later note of the same parameter adds to the earlier ones.
    """
    keys = pl.concat(
        [table.select(express_member_key(table.columns).alias(MEMBER_KEY)) for table in tables]
    )
    state.applied_source_rows.setdefault(parameter, set()).update(keys[MEMBER_KEY].to_list())


def drop_persisted_rows(state: State, parameter: str, rows: pl.DataFrame) -> pl.DataFrame:
    """The rows of `parameter` whose member no component and no extension record holds."""
    held = state.applied_source_rows.get(parameter)
    if not held or rows.height == 0:
        return rows
    keyed = rows.with_columns(express_member_key(rows.columns).alias(MEMBER_KEY))
    return keyed.filter(~pl.col(MEMBER_KEY).is_in(sorted(held))).drop(MEMBER_KEY)
