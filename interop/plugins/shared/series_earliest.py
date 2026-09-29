"""The value each component states at its earliest snapshot, read without a sort.

A sort inside an aggregate cannot stream, so it loads the whole series to answer one row
per component. Finding the earliest snapshot first, then joining back to it, streams.
"""

from __future__ import annotations

import polars as pl


def build_earliest_values(
    frame: pl.LazyFrame, *, component: str, snapshot: str, value: str
) -> pl.DataFrame:
    """One row per component, holding ``component`` and ``value`` at the earliest ``snapshot``."""
    earliest = frame.group_by(component).agg(pl.col(snapshot).min())
    return (
        frame.join(earliest, on=[component, snapshot], how="semi")
        .group_by(component)
        .agg(pl.col(value).first())
        .collect(engine="streaming")
    )
