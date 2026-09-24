"""A profile that does not fit the snapshot window is left off the system, and said so.

The HDF5 sink writes every association against one snapshot window, so a profile carrying a
different number of values has nowhere to go. Its component keeps the static value it
already holds.
"""

from __future__ import annotations

import logging
from typing import NamedTuple

import polars as pl

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import StagedTimeSeriesCol
from interop.plugins.shared.plexos_horizon import horizon_advice
from interop.plugins.shared.plexos_sienna_translations._shared import (
    dropped,
    plexos_field,
    record,
)
from interop.plugins.shared.pypsa_time_series import (
    OffWindowProfile,
    summarise_off_window,
)
from interop.plugins.shared.sienna_constants import (
    SiennaComponent,
    SiennaTimeSeriesAssociationCol,
)

log = logging.getLogger(__name__)

# Stands in for a file-backed property's value, which PLEXOS states as a path.
PROFILE = "profile"


class OffWindowAssociation(NamedTuple):
    """One association whose series holds a different number of values from the window."""

    component: str
    plexos_class: str
    plexos_property: str
    held: int


def drop_profiles_off_the_window(state: State, recorder: ScopedRecorder) -> None:
    """Leave every association whose series does not fit the window off the system."""
    associations = state.destination_tables.get(SiennaComponent.TIME_SERIES_ASSOCIATION)
    if associations is None or associations.height == 0:
        return
    # The window is the one the first association states, as the chain reads it: every
    # association in one system is meant to cover the same snapshots.
    lengths = associations[SiennaTimeSeriesAssociationCol.LENGTH].to_list()
    window = int(lengths[0] or 0)
    off_window = _off_the_window(state, associations, window)
    if not off_window:
        return
    _warn(off_window, window, horizon_advice(state))
    _record(recorder, off_window, window)
    state.destination_tables[SiennaComponent.TIME_SERIES_ASSOCIATION] = associations.filter(
        ~pl.col(SiennaTimeSeriesAssociationCol.COMPONENT_NAME).is_in(
            [one.component for one in off_window]
        )
    )


def _off_the_window(
    state: State, associations: pl.DataFrame, window: int
) -> list[OffWindowAssociation]:
    """Each association whose staged series holds a different number of values, fewest first."""
    off_window: list[OffWindowAssociation] = []
    for row in associations.iter_rows(named=True):
        plexos_class = row[SiennaTimeSeriesAssociationCol.SOURCE_TABLE]
        plexos_property = row[SiennaTimeSeriesAssociationCol.SOURCE_ATTRIBUTE]
        component = row[SiennaTimeSeriesAssociationCol.COMPONENT_NAME]
        held = _values_held(state, (plexos_class, plexos_property), component)
        if held != window:
            off_window.append(OffWindowAssociation(component, plexos_class, plexos_property, held))
    return sorted(off_window, key=lambda one: (one.held, one.component))


def _values_held(state: State, key: tuple[str, str], component: str) -> int:
    """How many values one component's staged series holds, counting an absent series as none."""
    frame = state.source_time_series.get(key)
    if frame is None:
        return 0
    counted = (
        frame.filter(pl.col(StagedTimeSeriesCol.COMPONENT) == component).select(pl.len()).collect()
    )
    return int(counted.item()) if counted.height else 0


def _warn(off_window: list[OffWindowAssociation], window: int, advice: str) -> None:
    log.warning(
        "the snapshot window holds %s steps but %s mapped profiles carry a different "
        "number, so they are left off the system: %s. %s",
        window,
        len(off_window),
        summarise_off_window(
            [
                OffWindowProfile(one.plexos_class, one.plexos_property, one.component, one.held)
                for one in off_window
            ]
        ),
        advice,
    )


def _record(recorder: ScopedRecorder, off_window: list[OffWindowAssociation], window: int) -> None:
    for one in off_window:
        record(
            recorder,
            dropped(
                [plexos_field(one.plexos_class, one.component, one.plexos_property, PROFILE)],
                f"the profile carries {one.held} values but the snapshot window holds "
                f"{window}, so the component keeps its static value instead",
            ),
        )
