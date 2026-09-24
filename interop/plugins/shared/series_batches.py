"""Read a staged time series a batch of components at a time.

A staged series can hold hundreds of millions of rows. A sink that needs the values of
every component reads them in batches, so one batch is all that sits in memory between
its read and its write.
"""

from __future__ import annotations

import numpy as np
import polars as pl
from numpy.typing import NDArray

from interop.plugins.shared.constants import StagedTimeSeriesCol

FloatArray = NDArray[np.float64]

# Rows one batch of components holds in memory between its read and its write.
ROWS_PER_BATCH = 4_000_000


def list_component_batches(frame: pl.LazyFrame) -> list[list[str]]:
    """The components of a series, in groups sized so one group holds about
    ``ROWS_PER_BATCH`` rows."""
    components = (
        frame.select(StagedTimeSeriesCol.COMPONENT)
        .unique()
        .sort(StagedTimeSeriesCol.COMPONENT)
        .collect(engine="streaming")[StagedTimeSeriesCol.COMPONENT]
        .to_list()
    )
    if not components:
        return []
    rows = frame.select(pl.len()).collect(engine="streaming").item()
    rows_per_component = max(rows // len(components), 1)
    size = max(ROWS_PER_BATCH // rows_per_component, 1)
    return [components[start : start + size] for start in range(0, len(components), size)]


def read_batch_by_component(frame: pl.LazyFrame, batch: list[str]) -> dict[str, FloatArray]:
    """The values of one batch of components, one array each, in snapshot order."""
    collected = (
        frame.filter(pl.col(StagedTimeSeriesCol.COMPONENT).is_in(batch))
        .sort(StagedTimeSeriesCol.COMPONENT, StagedTimeSeriesCol.SNAPSHOT)
        .select(StagedTimeSeriesCol.COMPONENT, StagedTimeSeriesCol.VALUE)
        .collect(engine="streaming")
    )
    return {
        str(component): part[StagedTimeSeriesCol.VALUE].to_numpy().astype(np.float64)
        for (component,), part in collected.partition_by(
            StagedTimeSeriesCol.COMPONENT, as_dict=True, include_key=False
        ).items()
    }
