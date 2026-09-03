"""The per-class lookups the generator mapping reads while it walks the Generator class.

Each is built once from the two long staged tables, so mapping a generator is dictionary
reads rather than a scan per generator.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.constants import StagedTimeSeriesCol
from interop.plugins.shared.plexos_constants import (
    PlexosClass,
    PlexosCollection,
    PlexosProperty,
    PlexosResolvedTable,
)
from interop.plugins.shared.plexos_pypsa_translations._shared import (
    ObjectProperties,
    built_bus_names,
    collapse_properties_by_object,
    read_file_backed_properties,
    relate_child,
    relate_children,
    relate_parent,
)
from interop.plugins.shared.pypsa_constants import DEFAULT_SNAPSHOT_MINUTES
from interop.plugins.shared.pypsa_time_series import resolution_minutes
from interop.plugins.shared.staged_samples import choose_reference_sample, filter_to_sample

# The staged availability profiles a generator may carry, in preference order: a
# generator carrying both keeps Rating (MW), the more direct of the two.
_PROFILE_PROPERTIES = (PlexosProperty.RATING, PlexosProperty.RATING_FACTOR)


@dataclass(frozen=True)
class Lookups:
    """Per-class property values and membership resolutions the generator loop reads."""

    gen_props: ObjectProperties
    fuel_props: ObjectProperties
    emission_props: ObjectProperties
    bus_names: set[str]
    gen_to_node: dict[str, str]
    gen_fuels: dict[str, list[str]]
    fuel_to_emission: dict[str, str]
    file_backed_properties: dict[str, list[str]]
    availability_profiles: dict[str, str]
    profile_troughs: dict[str, dict[str, float]]
    profile_peaks: dict[str, dict[str, float]]
    capacity_peaks: dict[str, float]
    minutes_per_snapshot: float


def build_lookups(state: State) -> Lookups:
    properties = state.source_topology[PlexosResolvedTable.PROPERTIES]
    memberships = state.source_topology[PlexosResolvedTable.MEMBERSHIPS]
    file_backed = read_file_backed_properties(properties, PlexosClass.GENERATOR)
    return Lookups(
        gen_props=collapse_properties_by_object(properties, PlexosClass.GENERATOR),
        fuel_props=collapse_properties_by_object(properties, PlexosClass.FUEL),
        emission_props=collapse_properties_by_object(properties, PlexosClass.EMISSION),
        bus_names=built_bus_names(state),
        gen_to_node=relate_child(memberships, PlexosClass.GENERATOR, PlexosCollection.NODES),
        gen_fuels=relate_children(memberships, PlexosClass.GENERATOR, PlexosCollection.FUELS),
        fuel_to_emission=relate_parent(memberships, PlexosClass.EMISSION, PlexosCollection.FUELS),
        file_backed_properties=file_backed,
        availability_profiles=_availability_profiles(file_backed),
        profile_troughs={prop: _series_troughs(state, prop) for prop in _PROFILE_PROPERTIES},
        profile_peaks={prop: _series_peaks(state, prop) for prop in _PROFILE_PROPERTIES},
        capacity_peaks=_series_peaks(state, PlexosProperty.MAX_CAPACITY),
        # Every staged series shares the network's snapshots, so any of them fixes the
        # resolution the hour-based generator properties convert against.
        minutes_per_snapshot=resolution_minutes(
            state, tuple(sorted(state.source_time_series)), DEFAULT_SNAPSHOT_MINUTES
        ),
    )


def _availability_profiles(file_backed: dict[str, list[str]]) -> dict[str, str]:
    """Generator name -> the file-backed availability property it carries, if any."""
    profiles: dict[str, str] = {}
    for name, present in file_backed.items():
        preferred = [prop for prop in _PROFILE_PROPERTIES if prop in present]
        if preferred:
            profiles[name] = preferred[0]
    return profiles


def _series_peaks(state: State, plexos_property: str) -> dict[str, float]:
    """Each generator's highest value in one staged series."""
    return _series_extremes(state, plexos_property, pl.col(StagedTimeSeriesCol.VALUE).max())


def _series_troughs(state: State, plexos_property: str) -> dict[str, float]:
    """Each generator's lowest value in one staged availability series."""
    return _series_extremes(state, plexos_property, pl.col(StagedTimeSeriesCol.VALUE).min())


def _series_extremes(state: State, plexos_property: str, extreme: pl.Expr) -> dict[str, float]:
    frame = state.source_time_series.get((PlexosClass.GENERATOR, plexos_property))
    if frame is None:
        return {}
    sampled = filter_to_sample(frame, choose_reference_sample(frame))
    aggregated = sampled.group_by(StagedTimeSeriesCol.COMPONENT).agg(extreme).collect()
    return {
        row[StagedTimeSeriesCol.COMPONENT]: row[StagedTimeSeriesCol.VALUE]
        for row in aggregated.iter_rows(named=True)
        if row[StagedTimeSeriesCol.VALUE] is not None
    }
