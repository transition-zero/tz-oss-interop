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
    MultiValueRule,
    ObjectProperties,
    built_bus_names,
    collapse_membership_properties,
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

# PLEXOS bands what a start costs by how long the unit has been off, hot band first. PyPSA
# holds one number, and the cold start is the one a commitment decision has to clear.
_COLD_START_BAND = MultiValueRule.HIGHEST
_GENERATOR_RULES: dict[str, MultiValueRule] = {PlexosProperty.START_COST: _COLD_START_BAND}


@dataclass(frozen=True)
class Lookups:
    """Per-class property values and membership resolutions the generator loop reads."""

    gen_props: ObjectProperties
    fuel_props: ObjectProperties
    emission_props: ObjectProperties
    bus_names: set[str]
    gen_to_node: dict[str, str]
    gen_fuels: dict[str, list[str]]
    start_fuel_offtake: dict[str, dict[str, float]]
    fuel_to_emission: dict[str, str]
    file_backed_properties: dict[str, list[str]]
    availability_profiles: dict[str, str]
    profile_troughs: dict[str, dict[str, float]]
    profile_peaks: dict[str, dict[str, float]]
    capacity_peaks: dict[str, float]
    dated_fuel_prices: dict[str, float]
    minutes_per_snapshot: float


def build_lookups(state: State) -> Lookups:
    properties = state.source_topology[PlexosResolvedTable.PROPERTIES]
    memberships = state.source_topology[PlexosResolvedTable.MEMBERSHIPS]
    file_backed = read_file_backed_properties(properties, PlexosClass.GENERATOR)
    return Lookups(
        gen_props=collapse_properties_by_object(
            properties, PlexosClass.GENERATOR, _GENERATOR_RULES
        ),
        fuel_props=collapse_properties_by_object(properties, PlexosClass.FUEL),
        emission_props=collapse_properties_by_object(properties, PlexosClass.EMISSION),
        bus_names=built_bus_names(state),
        gen_to_node=relate_child(memberships, PlexosClass.GENERATOR, PlexosCollection.NODES),
        gen_fuels=relate_children(memberships, PlexosClass.GENERATOR, PlexosCollection.FUELS),
        start_fuel_offtake=_read_start_fuel_offtake(properties),
        fuel_to_emission=relate_parent(memberships, PlexosClass.EMISSION, PlexosCollection.FUELS),
        file_backed_properties=file_backed,
        availability_profiles=_availability_profiles(file_backed),
        profile_troughs={prop: _series_troughs(state, prop) for prop in _PROFILE_PROPERTIES},
        profile_peaks={prop: _series_peaks(state, prop) for prop in _PROFILE_PROPERTIES},
        capacity_peaks=_series_peaks(state, PlexosProperty.MAX_CAPACITY),
        dated_fuel_prices=_mean_fuel_prices(state),
        # Every staged series shares the network's snapshots, so any of them fixes the
        # resolution the hour-based generator properties convert against.
        minutes_per_snapshot=resolution_minutes(
            state, tuple(sorted(state.source_time_series)), DEFAULT_SNAPSHOT_MINUTES
        ),
    )


def _read_start_fuel_offtake(properties: pl.LazyFrame) -> dict[str, dict[str, float]]:
    """Each generator's start fuels, and the gigajoules of each a cold start takes.

    The offtake is stated on the Generator to Fuel membership, so both ends matter: a
    generator may start on a fuel other than the one it runs on, and that fuel's own price
    is what the start costs.
    """
    start_fuels = collapse_membership_properties(
        properties, PlexosClass.GENERATOR, PlexosCollection.START_FUELS, _COLD_START_BAND
    )
    offtakes = {
        name: {
            fuel: properties_of_fuel[PlexosProperty.OFFTAKE_AT_START]
            for fuel, properties_of_fuel in by_fuel.items()
            if PlexosProperty.OFFTAKE_AT_START in properties_of_fuel
        }
        for name, by_fuel in start_fuels.items()
    }
    return {name: by_fuel for name, by_fuel in offtakes.items() if by_fuel}


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
    return _aggregate_series(
        state, PlexosClass.GENERATOR, plexos_property, pl.col(StagedTimeSeriesCol.VALUE).max()
    )


def _series_troughs(state: State, plexos_property: str) -> dict[str, float]:
    """Each generator's lowest value in one staged availability series."""
    return _aggregate_series(
        state, PlexosClass.GENERATOR, plexos_property, pl.col(StagedTimeSeriesCol.VALUE).min()
    )


def _mean_fuel_prices(state: State) -> dict[str, float]:
    """Each fuel's mean price over the horizon, for the fuels priced by date.

    A fuel priced by date carries its real price in the series, and the scalar the model
    states beside it is whatever the first date band happened to hold. The mean is what a
    reader sampling one number off the network should see.
    """
    return _aggregate_series(
        state, PlexosClass.FUEL, PlexosProperty.PRICE, pl.col(StagedTimeSeriesCol.VALUE).mean()
    )


def _aggregate_series(
    state: State, plexos_class: PlexosClass, plexos_property: str, aggregate: pl.Expr
) -> dict[str, float]:
    frame = state.source_time_series.get((plexos_class, plexos_property))
    if frame is None:
        return {}
    sampled = filter_to_sample(frame, choose_reference_sample(frame))
    aggregated = sampled.group_by(StagedTimeSeriesCol.COMPONENT).agg(aggregate).collect()
    return {
        row[StagedTimeSeriesCol.COMPONENT]: row[StagedTimeSeriesCol.VALUE]
        for row in aggregated.iter_rows(named=True)
        if row[StagedTimeSeriesCol.VALUE] is not None
    }
