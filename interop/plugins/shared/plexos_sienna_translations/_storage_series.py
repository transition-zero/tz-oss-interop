"""The per-snapshot storage values Sienna has no field for.

Sienna's EnergyReservoirStorage states one rating and names no inflow at all, so neither a
units-out derate nor an inflow that changes through the year has a field on the component.
Both ride the storage companion parquet beside the extensions sidecar, one column each, and
the hop that reads the sidecar writes them onto its own storage unit.

The frame stays lazy, so a series of any length crosses the hub without being read into
memory.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from interop.core.extensions import CompanionSeriesCol, StorageCompanionCol
from interop.core.pipeline import State
from interop.plugins.shared.constants import StagedTimeSeriesCol
from interop.plugins.shared.plexos_constants import PlexosClass, PlexosProperty
from interop.plugins.shared.plexos_pypsa_translations._storage_shared import StorageUnitMapping
from interop.plugins.shared.pypsa_time_series import series_components

FULLY_AVAILABLE = 1.0


@dataclass(frozen=True)
class StorageSeries:
    """The companion frame, and the units whose record names a column of it."""

    frame: pl.LazyFrame | None
    inflow_names: frozenset[str]
    rating_names: frozenset[str]


def build_storage_series(state: State, mappings: list[StorageUnitMapping]) -> StorageSeries:
    """The companion frame every varying storage value rides in, and who rides in it."""
    inflow = _inflow_pairs(state, mappings)
    rating = _rating_pairs(state, mappings)
    return StorageSeries(
        frame=_joined(_inflow_frame(state, inflow), _rating_frame(state, mappings, rating)),
        inflow_names=frozenset(name for _, name in inflow),
        rating_names=frozenset(name for _, name in rating),
    )


def _inflow_pairs(state: State, mappings: list[StorageUnitMapping]) -> list[tuple[str, str]]:
    """Each (head Storage, unit) pair whose inflow the source staged as a series.

    Two turbines can draw on one reservoir, so the pairs are a list rather than a mapping.
    """
    staged = state.source_time_series.get((PlexosClass.STORAGE, PlexosProperty.NATURAL_INFLOW))
    if staged is None:
        return []
    present = set(series_components(staged))
    return [
        (mapping.inflow_storage, mapping.name)
        for mapping in mappings
        if mapping.inflow_storage is not None and mapping.inflow_storage in present
    ]


def _rating_pairs(state: State, mappings: list[StorageUnitMapping]) -> list[tuple[str, str]]:
    """Each (Battery, unit) pair whose units-out trace the source staged."""
    staged = state.source_time_series.get((PlexosClass.BATTERY, PlexosProperty.UNITS_OUT))
    if staged is None:
        return []
    present = set(series_components(staged))
    return [
        (mapping.name, mapping.name)
        for mapping in mappings
        if mapping.units and mapping.name in present
    ]


def _inflow_frame(state: State, pairs: list[tuple[str, str]]) -> pl.LazyFrame | None:
    """The inflow each unit's reservoir receives, in megawatts, snapshot by snapshot."""
    if not pairs:
        return None
    staged = state.source_time_series[(PlexosClass.STORAGE, PlexosProperty.NATURAL_INFLOW)]
    return _renamed(staged, pairs).select(
        pl.col(CompanionSeriesCol.SNAPSHOT),
        pl.col(CompanionSeriesCol.NAME),
        pl.col(StagedTimeSeriesCol.VALUE).alias(StorageCompanionCol.INFLOW_MW),
    )


def _rating_frame(
    state: State, mappings: list[StorageUnitMapping], pairs: list[tuple[str, str]]
) -> pl.LazyFrame | None:
    """The share of its rating each unit reaches, which is one less the machines out."""
    if not pairs:
        return None
    units_by_name = {mapping.name: mapping.units for mapping in mappings if mapping.units}
    staged = state.source_time_series[(PlexosClass.BATTERY, PlexosProperty.UNITS_OUT)]
    counted = pl.LazyFrame(
        {
            CompanionSeriesCol.NAME: list(units_by_name),
            _UNITS_HELD: [float(units or 0.0) for units in units_by_name.values()],
        }
    )
    return (
        _renamed(staged, pairs)
        .join(counted, on=CompanionSeriesCol.NAME, how="inner")
        .select(
            pl.col(CompanionSeriesCol.SNAPSHOT),
            pl.col(CompanionSeriesCol.NAME),
            (FULLY_AVAILABLE - pl.col(StagedTimeSeriesCol.VALUE) / pl.col(_UNITS_HELD)).alias(
                StorageCompanionCol.RATING_PU
            ),
        )
    )


# The machines a unit holds, joined on so the derate divides by it inside the frame.
_UNITS_HELD = "units_held"


def _renamed(staged: pl.LazyFrame, pairs: list[tuple[str, str]]) -> pl.LazyFrame:
    """The staged rows of each named owner, under the storage unit that reads them."""
    owners = pl.LazyFrame(
        {
            StagedTimeSeriesCol.COMPONENT: [owner for owner, _ in pairs],
            CompanionSeriesCol.NAME: [name for _, name in pairs],
        }
    )
    return staged.join(owners, on=StagedTimeSeriesCol.COMPONENT, how="inner").rename(
        {StagedTimeSeriesCol.SNAPSHOT: CompanionSeriesCol.SNAPSHOT}
    )


def _joined(inflow: pl.LazyFrame | None, rating: pl.LazyFrame | None) -> pl.LazyFrame | None:
    """One frame holding both columns, with a null where a unit states only the other."""
    if inflow is None:
        return rating
    if rating is None:
        return inflow
    return inflow.join(
        rating, on=[CompanionSeriesCol.SNAPSHOT, CompanionSeriesCol.NAME], how="full", coalesce=True
    )
