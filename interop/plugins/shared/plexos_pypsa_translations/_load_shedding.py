"""Region ``VoLL`` -> load-shedding Generator translation.

A PyPSA load is a fixed ``p_set``: nothing sheds, so an hour without enough capacity
makes the solve infeasible rather than reporting unserved energy. This adds one
generator at every bus, priced at its containing Region's VoLL (or a documented
default where a Region states none), sized to the network's own total peak load so any
one of them alone could cover a system-wide shortfall. The optimiser only calls on one
once every real resource is exhausted; the megawatt-hours it produces are the unserved
energy and the hours it runs are the loss-of-load hours.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, NamedTuple

import polars as pl

from interop.core.extensions import BusExtension, ExtensionKind, append_extensions
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import UNIT_DOLLARS_PER_MWH, UNIT_MW, StagedTimeSeriesCol
from interop.plugins.shared.plexos_constants import PlexosClass, PlexosProperty, PlexosResolvedTable
from interop.plugins.shared.plexos_pypsa_translations._shared import collapse_properties_by_object
from interop.plugins.shared.plexos_pypsa_translations.constants import (
    DEFAULT_P_MIN_PU,
    DEFAULT_VOLL,
    FULL_AVAILABILITY,
    LOAD_SHEDDING_NAME_SUFFIX,
)
from interop.plugins.shared.plexos_pypsa_translations.decisions import (
    ComponentReporter,
    Decision,
    SourceValue,
    destination_row,
    maps_to,
)
from interop.plugins.shared.pypsa_constants import (
    GENERATORS_DESTINATION_SCHEMA,
    PyPSABusCol,
    PyPSACarrier,
    PyPSAComponent,
    PyPSADestinationTable,
    PyPSAGeneratorCol,
    PyPSALoadCol,
    ReverseTimeSeriesMetadataCol,
)

# A load-shedding generator has no unit-commitment behaviour and its capacity is fixed
# once at translation time, never optimised.
_NOT_COMMITTABLE = False
_NOT_EXTENDABLE = False

_CARRIER_NOTE = "the reliability pipeline adds a load-shedding generator at every bus"
_P_NOM_DERIVATION = (
    "the network's own total peak load, so one bus's shedding generator alone could "
    "cover the whole system"
)
_VOLL_DERIVATION = "the bus's containing Region VoLL"
_VOLL_NOTE = (
    "no Region carries a VoLL for this bus; load shedding is priced at the translator's "
    "documented default"
)
_P_MIN_PU_NOTE = "a load-shedding generator only ever sheds; it cannot be forced to run"
_P_MAX_PU_NOTE = "a load-shedding generator is available at its full sized capacity every hour"
_COMMITTABLE_NOTE = "a load-shedding generator has no unit-commitment behaviour of its own"
_EXTENDABLE_NOTE = "its capacity is sized once at translation time, not optimised"

# The columns a shedding generator leaves to PyPSA's own defaults, written unset.
_UNSET_COLUMNS = (
    PyPSAGeneratorCol.EFFICIENCY,
    PyPSAGeneratorCol.RAMP_LIMIT_UP,
    PyPSAGeneratorCol.RAMP_LIMIT_DOWN,
    PyPSAGeneratorCol.MIN_UP_TIME,
    PyPSAGeneratorCol.MIN_DOWN_TIME,
    PyPSAGeneratorCol.UP_TIME_BEFORE,
    PyPSAGeneratorCol.START_UP_COST,
    PyPSAGeneratorCol.SHUT_DOWN_COST,
)


@dataclass(frozen=True)
class _LoadSheddingMapping:
    """One load-shedding Generator: each destination value and where it came from."""

    name: str
    bus: Decision = maps_to(PyPSAGeneratorCol.BUS)
    carrier: Decision = maps_to(PyPSAGeneratorCol.CARRIER)
    p_nom: Decision = maps_to(PyPSAGeneratorCol.P_NOM, unit=UNIT_MW)
    p_min_pu: Decision = maps_to(PyPSAGeneratorCol.P_MIN_PU)
    p_max_pu: Decision = maps_to(PyPSAGeneratorCol.P_MAX_PU)
    marginal_cost: Decision = maps_to(PyPSAGeneratorCol.MARGINAL_COST, unit=UNIT_DOLLARS_PER_MWH)
    committable: Decision = maps_to(PyPSAGeneratorCol.COMMITTABLE)
    p_nom_extendable: Decision = maps_to(PyPSAGeneratorCol.P_NOM_EXTENDABLE)
    unset: Decision = maps_to(*_UNSET_COLUMNS)


def add_load_shedding_generators(state: State, recorder: ScopedRecorder) -> None:
    """Append one load-shedding generator per bus to the generators destination table."""
    buses = state.destination_tables.get(PyPSADestinationTable.BUSES)
    if buses is None or buses.is_empty():
        return
    reporter = ComponentReporter(recorder, PyPSAComponent.GENERATOR)
    p_nom = _total_peak_demand(state)
    region_voll = _region_voll(state)
    mappings = [
        _derive_generator(bus_row, p_nom, region_voll) for bus_row in buses.iter_rows(named=True)
    ]
    for mapping in mappings:
        reporter.record_mapping(mapping.name, mapping)
    rows = [destination_row(mapping, PyPSAGeneratorCol.NAME, mapping.name) for mapping in mappings]
    new = pl.DataFrame(rows, schema=GENERATORS_DESTINATION_SCHEMA)
    existing = state.destination_tables.get(PyPSADestinationTable.GENERATORS)
    state.destination_tables[PyPSADestinationTable.GENERATORS] = (
        pl.concat([existing, new]) if existing is not None else new
    )
    _carry_shedding_price_to_extensions(state, buses, mappings)


def _carry_shedding_price_to_extensions(
    state: State, buses: pl.DataFrame, mappings: list[_LoadSheddingMapping]
) -> None:
    """Put the price each bus sheds at in the sidecar, so a later hop sheds at the same price.

    PyPSA holds the price on the shedding generator, which is a component the next hop does
    not build, so the number would otherwise stop here. It is the price this pipeline decided
    on, whether the Region stated it or the default supplied it.
    """
    records = [
        BusExtension(
            name=bus_row[PyPSABusCol.NAME], value_of_lost_load=float(mapping.marginal_cost.value)
        )
        for bus_row, mapping in zip(buses.iter_rows(named=True), mappings, strict=True)
    ]
    append_extensions(state.destination_extensions, ExtensionKind.BUS, records)


def _derive_generator(
    bus_row: dict[str, Any], p_nom: float, region_voll: dict[str, float]
) -> _LoadSheddingMapping:
    bus = bus_row[PyPSABusCol.NAME]
    return _LoadSheddingMapping(
        name=f"{bus}{LOAD_SHEDDING_NAME_SUFFIX}",
        bus=Decision.unreported(bus),
        carrier=Decision.default(PyPSACarrier.LOAD_SHEDDING, _CARRIER_NOTE),
        p_nom=Decision.computed(p_nom, _P_NOM_DERIVATION),
        p_min_pu=Decision.default(DEFAULT_P_MIN_PU, _P_MIN_PU_NOTE),
        p_max_pu=Decision.default(FULL_AVAILABILITY, _P_MAX_PU_NOTE),
        marginal_cost=_marginal_cost(bus_row[PyPSABusCol.LOCATION], region_voll),
        committable=Decision.default(_NOT_COMMITTABLE, _COMMITTABLE_NOTE),
        p_nom_extendable=Decision.default(_NOT_EXTENDABLE, _EXTENDABLE_NOTE),
        unset=Decision.unreported(None),
    )


def _marginal_cost(region: str, region_voll: dict[str, float]) -> Decision:
    voll = region_voll.get(region)
    if voll is None:
        return Decision.default(DEFAULT_VOLL, _VOLL_NOTE)
    source = SourceValue(
        PlexosClass.REGION, region, PlexosProperty.VOLL, voll, UNIT_DOLLARS_PER_MWH
    )
    return Decision.derived(voll, [source], _VOLL_DERIVATION)


def _region_voll(state: State) -> dict[str, float]:
    """VoLL per Region name, for the Regions that state one."""
    properties = collapse_properties_by_object(
        state.source_topology[PlexosResolvedTable.PROPERTIES], PlexosClass.REGION
    )
    return {
        name: float(props[PlexosProperty.VOLL])
        for name, props in properties.items()
        if PlexosProperty.VOLL in props
    }


class _LoadProfile(NamedTuple):
    """One staged series feeding a PyPSA load's p_set, read the way the sink reads it."""

    owner_type: str
    owner: str
    scaling_factor: float
    offset: float


def _total_peak_demand(state: State) -> float:
    """An upper bound on total system demand: the sum of every load's own peak value.

    Overestimates the true coincident peak (not every load peaks at the same hour), which
    is the safe direction for sizing a generator that must never itself run short. Only
    the loads that reached the network are counted, and a load whose profile replaces its
    static value is counted once, so the bound is no higher than it has to be.
    """
    loads = state.destination_tables.get(PyPSADestinationTable.LOADS)
    if loads is None:
        return 0.0
    profile_by_load = _profiles_by_load(state)
    static = loads.filter(~pl.col(PyPSALoadCol.NAME).is_in(list(profile_by_load)))
    return float(static[PyPSALoadCol.P_SET].sum()) + _profile_peak_total(
        state, list(profile_by_load.values())
    )


def _profiles_by_load(state: State) -> dict[str, _LoadProfile]:
    """The staged series feeding each load's p_set, keyed by the load's own name.

    Read from the metadata the mapping step wrote, so a Region or Node the step left out
    contributes nothing, and neither does a profile that did not fit the snapshot window.
    """
    metadata = state.destination_tables.get(PyPSADestinationTable.TIME_SERIES_METADATA)
    if metadata is None:
        return {}
    rows = metadata.filter(
        (pl.col(ReverseTimeSeriesMetadataCol.COMPONENT_TABLE) == PyPSADestinationTable.LOADS)
        & (pl.col(ReverseTimeSeriesMetadataCol.ATTRIBUTE) == PyPSALoadCol.P_SET)
    )
    return {
        row[ReverseTimeSeriesMetadataCol.COMPONENT_NAME]: _read_profile(row)
        for row in rows.iter_rows(named=True)
    }


def _read_profile(row: dict[str, Any]) -> _LoadProfile:
    return _LoadProfile(
        owner_type=row[ReverseTimeSeriesMetadataCol.SOURCE_OWNER_TYPE],
        owner=row[ReverseTimeSeriesMetadataCol.SOURCE_COMPONENT_NAME],
        scaling_factor=row[ReverseTimeSeriesMetadataCol.SCALING_FACTOR],
        offset=row[ReverseTimeSeriesMetadataCol.OFFSET],
    )


def _profile_peak_total(state: State, profiles: list[_LoadProfile]) -> float:
    """Each profiled load's own peak, scaled the way the sink scales it, added up."""
    peaks = {
        owner_type: _peaks_by_owner(state, owner_type)
        for owner_type in {profile.owner_type for profile in profiles}
    }
    return float(
        sum(
            peaks[profile.owner_type][profile.owner] * profile.scaling_factor + profile.offset
            for profile in profiles
            if profile.owner in peaks[profile.owner_type]
        )
    )


def _peaks_by_owner(state: State, owner_type: str) -> dict[str, float]:
    """Each component's own peak in one staged Load series, across every replication."""
    frame = state.source_time_series.get((owner_type, PlexosProperty.LOAD))
    if frame is None:
        return {}
    aggregated = (
        frame.group_by(StagedTimeSeriesCol.COMPONENT)
        .agg(pl.col(StagedTimeSeriesCol.VALUE).max())
        .collect()
    )
    return dict(aggregated.iter_rows())
