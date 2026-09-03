"""How a mapping writes into ``State.destination_tables``.

The table keys and their column schemas are PyPSA vocabulary and live in
``pypsa_constants``; this is the one way to add rows to them. Several mappings write
the same table, so every write appends rather than assigns.
"""

from __future__ import annotations

from typing import Any

import polars as pl

from interop.core.pipeline import State


def append_destination_rows(
    state: State,
    table: str,
    rows: list[dict[str, Any]],
    schema: dict[str, pl.DataType | type[pl.DataType]],
) -> None:
    """Add rows to a destination table, keeping whatever an earlier mapping wrote."""
    if not rows:
        return
    new = pl.DataFrame(rows, schema=schema)
    existing = state.destination_tables.get(table)
    state.destination_tables[table] = pl.concat([existing, new]) if existing is not None else new
