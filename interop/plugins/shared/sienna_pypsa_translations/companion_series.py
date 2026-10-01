"""Reading a companion parquet back onto the PyPSA components it describes.

A value a Sienna component has no field for travels in the extensions sidecar. Where that
value changes from snapshot to snapshot it travels in a parquet beside the sidecar instead,
one column per field. This is how a hop into PyPSA reads such a column: it stages the
column like any source series, so the sink streams it the way it streams every profile.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import polars as pl

from interop.core.extensions import CompanionSeriesCol, ExtensionKind
from interop.core.pipeline import State
from interop.plugins.shared.constants import StagedTimeSeriesCol
from interop.plugins.shared.pypsa_time_series import (
    append_metadata,
    metadata_row,
    series_components,
    series_timing,
)

# The owner every staged companion column takes. No Sienna component names these values, so
# the key is the reading hop's own.
COMPANION_OWNER = "extensions_companion"

# A companion states its values in the unit PyPSA reads, so a column rides with no scaling.
_COMPANION_SCALING = 1.0


@dataclass(frozen=True)
class CompanionColumn:
    """One column of a companion parquet, and the PyPSA attribute it fills."""

    column: str
    component_table: str
    attribute: str

    @property
    def key(self) -> tuple[str, str]:
        """The key the column takes in ``State.source_time_series`` once staged."""
        return (COMPANION_OWNER, self.column)


def stage_companion_columns(
    state: State,
    kind: ExtensionKind,
    columns: tuple[CompanionColumn, ...],
    written: set[str],
) -> None:
    """Stage each column the companion holds, and point the components it names at it.

    ``written`` is the components the hop wrote, so a column naming one it left out reaches
    no metadata row.
    """
    frame = state.source_extension_series.get(kind)
    if frame is None:
        return
    held = set(frame.collect_schema().names())
    for one in columns:
        if one.column not in held:
            continue
        staged = _staged_column(frame, one.column)
        state.source_time_series[one.key] = staged
        append_metadata(state, _companion_metadata(staged, one, written))


def _staged_column(frame: pl.LazyFrame, column: str) -> pl.LazyFrame:
    """One companion column, in the shape every staged source series takes."""
    return (
        frame.filter(pl.col(column).is_not_null())
        .select(
            pl.col(CompanionSeriesCol.SNAPSHOT).alias(StagedTimeSeriesCol.SNAPSHOT),
            pl.col(CompanionSeriesCol.NAME).alias(StagedTimeSeriesCol.COMPONENT),
            pl.col(column).alias(StagedTimeSeriesCol.VALUE),
        )
        .sort(StagedTimeSeriesCol.COMPONENT, StagedTimeSeriesCol.SNAPSHOT)
    )


def _companion_metadata(
    staged: pl.LazyFrame, one: CompanionColumn, written: set[str]
) -> list[dict[str, Any]]:
    """One metadata row for each component the column names that the hop wrote."""
    named = [name for name in series_components(staged) if name in written]
    if not named:
        return []
    timing = series_timing(staged)
    return [
        metadata_row(
            component_table=one.component_table,
            component_name=name,
            attribute=one.attribute,
            source_owner_type=COMPANION_OWNER,
            source_series_name=one.column,
            scaling_factor=_COMPANION_SCALING,
            timing=timing,
        )
        for name in named
    ]
