"""The value each component states at its earliest snapshot, read without a sort.

A sort inside an aggregate cannot stream, so it loads the whole series to answer one row
per component. A staged series holds every snapshot for every component, so the earliest
snapshot is one value: a streaming min finds it, and a streaming filter reads the row.
"""

from __future__ import annotations

import polars as pl


def build_earliest_values(
    frame: pl.LazyFrame, *, component: str, snapshot: str, value: str
) -> pl.DataFrame:
    """One row per component, holding ``component`` and ``value`` at the earliest ``snapshot``."""
    earliest = frame.select(pl.col(snapshot).min()).collect(engine="streaming").item()
    if earliest is None:
        return pl.DataFrame(schema={component: pl.String, value: pl.Float64})
    at_earliest = _first_value_at(frame.filter(pl.col(snapshot) == earliest), component, value)
    named = frame.select(component).unique().collect(engine="streaming")[component]
    missing = [
        name for name in named.to_list() if name not in set(at_earliest[component].to_list())
    ]
    if not missing:
        return at_earliest
    rest = frame.filter(pl.col(component).is_in(missing))
    own_earliest = rest.group_by(component).agg(pl.col(snapshot).min())
    late = _first_value_at(
        rest.join(own_earliest, on=[component, snapshot], how="semi"), component, value
    )
    return pl.concat([at_earliest, late])


def _first_value_at(rows: pl.LazyFrame, component: str, value: str) -> pl.DataFrame:
    return rows.group_by(component).agg(pl.col(value).first()).collect(engine="streaming")
