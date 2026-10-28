"""The hourly series that the translation stages for the HDF5 sink.

A series is a long table `(snapshot, component, value)`. The sink finds it by the
`source_table` and `source_attribute` of each association row, and divides each value by the
`scaling_factor` of the row. A series in MW takes its peak as that factor. A series per unit
of the base power of its owner takes 1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.constants import UNSCALED, StagedTimeSeriesCol
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

SERIES_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    StagedTimeSeriesCol.SNAPSHOT: pl.Datetime("us"),
    StagedTimeSeriesCol.COMPONENT: pl.Utf8,
    StagedTimeSeriesCol.VALUE: pl.Float64,
}


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


class _Staging(NamedTuple):
    """The table to stage under the key of a series, and the scaling factor of each owner."""

    table: pl.LazyFrame
    scales: dict[str, float]


def add_series(state: State, series: StagedSeries, owners: pl.DataFrame) -> None:
    """Stage a series in MW and add one association row for each owner that it names.

    `owners` is the destination table of the owner type, with its `name` and `id`.
    """
    _reject_staged(state, series)
    peaks = build_series_peaks(series.table)
    scales = {name: peak or UNSCALED for name, peak in peaks.items()}
    _add_scaled_series(state, series, owners, _Staging(series.table.lazy(), scales))


def add_per_unit_series(state: State, series: StagedSeries, owners: pl.DataFrame) -> None:
    """Stage a series per unit of the base power of each owner, and its association rows."""
    _reject_staged(state, series)
    staging = _Staging(series.table.lazy(), _build_unscaled(series))
    _add_scaled_series(state, series, owners, staging)


def add_to_per_unit_series(state: State, series: StagedSeries, owners: pl.DataFrame) -> None:
    """Stage a series per unit beside the series that an earlier step staged under its key."""
    earlier = state.source_time_series.get(series.key)
    table = series.table.lazy() if earlier is None else pl.concat([earlier, series.table.lazy()])
    _add_scaled_series(state, series, owners, _Staging(table, _build_unscaled(series)))


def _reject_staged(state: State, series: StagedSeries) -> None:
    if series.key in state.source_time_series:
        raise ValueError(f"the series {series.key} is already staged")


def _build_unscaled(series: StagedSeries) -> dict[str, float]:
    """A series per unit keeps its values, so each owner takes the factor 1."""
    names = series.table[StagedTimeSeriesCol.COMPONENT].unique().to_list()
    return dict.fromkeys(names, UNSCALED)


def _add_scaled_series(
    state: State, series: StagedSeries, owners: pl.DataFrame, staging: _Staging
) -> None:
    state.source_time_series[series.key] = staging.table
    associations = _build_associations(series, owners, staging.scales)
    existing = state.destination_tables.get(SiennaComponent.TIME_SERIES_ASSOCIATION)
    state.destination_tables[SiennaComponent.TIME_SERIES_ASSOCIATION] = (
        associations if existing is None else pl.concat([existing, associations])
    )


def _build_associations(
    series: StagedSeries, owners: pl.DataFrame, scales: dict[str, float]
) -> pl.DataFrame:
    ts_info = collect_ts_info(series.table.lazy())
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
            scaling_factor=scales[name],
        )
        for name, owner_id in owners.select(SIENNA_NAME_COLUMN, SIENNA_ID_COLUMN).iter_rows()
        if name in scales
    ]
    return pl.DataFrame(rows, schema=TIME_SERIES_ASSOCIATION_SCHEMA)
