"""The hourly series that the translation stages for the HDF5 sink.

A series is a long table `(snapshot, component, value)` in Sienna units. The sink finds it by
the `source_table` and `source_attribute` of each association row, and divides each value by
the `scaling_factor` of the row.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.constants import StagedTimeSeriesCol
from interop.plugins.shared.osemosys_sienna_constants import (
    OSEMOSYS_SIENNA_SERIES,
    SERIES_KEY_SEPARATOR,
)
from interop.plugins.shared.sienna_constants import (
    SIENNA_ID_COLUMN,
    SIENNA_NAME_COLUMN,
    TIME_SERIES_ASSOCIATION_SCHEMA,
    SiennaComponent,
)
from interop.plugins.shared.sienna_time_series import collect_ts_info, ts_association_row

# The divisor of a series whose peak is zero, which keeps its stored zeros.
_ZERO_PEAK_SCALE = 1.0


@dataclass(frozen=True)
class StagedSeries:
    """One attribute of one Sienna type, for each component that has a series of it."""

    owner_type: SiennaComponent
    attribute: str
    table: pl.DataFrame

    @property
    def key(self) -> tuple[str, str]:
        """The `State.source_time_series` key, which is also the source of each association row."""
        return (
            OSEMOSYS_SIENNA_SERIES,
            f"{self.owner_type}{SERIES_KEY_SEPARATOR}{self.attribute}",
        )


def build_series_peaks(table: pl.DataFrame) -> dict[str, float]:
    """The highest value of the series of each component."""
    peaks = table.group_by(StagedTimeSeriesCol.COMPONENT).agg(
        pl.col(StagedTimeSeriesCol.VALUE).max()
    )
    return dict(peaks.iter_rows())


def build_series_firsts(table: pl.DataFrame) -> dict[str, float]:
    """The value of the series of each component at its first snapshot."""
    firsts = (
        table.sort(StagedTimeSeriesCol.SNAPSHOT)
        .group_by(StagedTimeSeriesCol.COMPONENT, maintain_order=True)
        .agg(pl.col(StagedTimeSeriesCol.VALUE).first())
    )
    return dict(firsts.iter_rows())


def add_series(state: State, series: StagedSeries, owners: pl.DataFrame) -> None:
    """Stage a series and add one association row for each owner that it names.

    `owners` is the destination table of the owner type, with its `name` and `id`.
    """
    if series.key in state.source_time_series:
        raise ValueError(f"the series {series.key} is already staged")
    state.source_time_series[series.key] = series.table.lazy()
    associations = _build_associations(series, owners)
    existing = state.destination_tables.get(SiennaComponent.TIME_SERIES_ASSOCIATION)
    state.destination_tables[SiennaComponent.TIME_SERIES_ASSOCIATION] = (
        associations if existing is None else pl.concat([existing, associations])
    )


def _build_associations(series: StagedSeries, owners: pl.DataFrame) -> pl.DataFrame:
    ts_info = collect_ts_info(series.table.lazy())
    peaks = build_series_peaks(series.table)
    source_table, source_attribute = series.key
    rows = [
        ts_association_row(
            owner_type=series.owner_type,
            owner_id=owner_id,
            component_name=name,
            series_name=series.attribute,
            ts_info=ts_info,
            source_table=source_table,
            source_attribute=source_attribute,
            scaling_factor=peaks[name] or _ZERO_PEAK_SCALE,
        )
        for name, owner_id in owners.select(SIENNA_NAME_COLUMN, SIENNA_ID_COLUMN).iter_rows()
        if name in peaks
    ]
    return pl.DataFrame(rows, schema=TIME_SERIES_ASSOCIATION_SCHEMA)
