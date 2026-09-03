"""PLEXOS Battery -> PyPSA StorageUnit.

A Battery states its own power and energy, so it needs no reservoir: the energy it holds
when full is its Capacity, or its Duration times its Max Power where it states no Capacity.
"""

from __future__ import annotations

import logging

from interop.core.pipeline import State
from interop.plugins.shared.constants import (
    UNIT_HOURS,
    UNIT_MW,
    UNIT_MWH,
    UNIT_PERCENT,
)
from interop.plugins.shared.plexos_constants import (
    PlexosClass,
    PlexosProperty,
)
from interop.plugins.shared.plexos_pypsa_translations._shared import outage_time_series
from interop.plugins.shared.plexos_pypsa_translations._storage_shared import (
    CARRIER_NOTE,
    CHARGE_NOTE,
    EFFICIENCY_NOTE,
    EXTENDABLE_NOTE,
    FULL_DISCHARGE_NOTE,
    NO_RESERVOIR_INFLOW_NOTE,
    MappedOrSkipped,
    RatedObject,
    RatedPower,
    SkippedComponent,
    StagedObject,
    StorageLookups,
    StorageUnitMapping,
    derive_bus,
    derive_max_hours,
    derive_round_trip_efficiency,
    derive_state_of_charge_initial,
    rate_object,
)
from interop.plugins.shared.plexos_pypsa_translations.constants import (
    BATTERY_CYCLIC,
    DEFAULT_INFLOW,
    DEFAULT_ROUND_TRIP_EFFICIENCY,
    DIRECT_DERIVATION,
    END_EFFECTS_RECYCLE,
    PERCENT,
    STORAGE_FULL_CHARGE_PU,
    STORAGE_FULL_DISCHARGE_PU,
    STORAGE_MARGINAL_COST,
    STORAGE_P_NOM_EXTENDABLE,
)
from interop.plugins.shared.plexos_pypsa_translations.decisions import (
    Decision,
    SourceValue,
)
from interop.plugins.shared.pypsa_constants import (
    PyPSACarrier,
    PyPSADestinationTable,
    PyPSAStorageUnitCol,
)
from interop.plugins.shared.pypsa_time_series import append_metadata

log = logging.getLogger(__name__)


def record_battery_outages(state: State, mappings: list[StorageUnitMapping]) -> None:
    """Derate each battery by its units-out trace, against the unit count it states."""
    units_by_battery = {m.name: m.units for m in mappings if m.units}
    append_metadata(
        state,
        outage_time_series(
            state,
            PlexosClass.BATTERY,
            PyPSADestinationTable.STORAGE_UNITS,
            PyPSAStorageUnitCol.P_MAX_PU,
            units_by_battery,
        ),
    )


_BATTERY_CYCLIC_NOTE = "an initial state of charge is given, so the level need not cycle"
_BATTERY_FREE_DERIVATION = "End Effects Method frees the end level"
_BATTERY_MARGINAL_COST_NOTE = "a PLEXOS Battery carries no per-MWh dispatch cost"
_BATTERY_NO_START_NOTE = (
    "no initial state of charge is given, so the level cycles rather than starting empty"
)
_BATTERY_RECYCLE_DERIVATION = "End Effects Method recycles the level"
_CAPACITY_DERIVATION = "Capacity"
_CAPACITY_FROM_DURATION_DERIVATION = "Duration * Max Power"
_SOC_FROM_PERCENT_DERIVATION = "Initial SoC / 100 * energy capacity"

# --- batteries ---------------------------------------------------------------


def map_battery(name: str, lookups: StorageLookups) -> MappedOrSkipped:
    rated = rate_object(lookups.battery(name), _BATTERY_POWER)
    if isinstance(rated, SkippedComponent):
        return rated
    return _derive_battery(rated)


def _battery_p_nom(staged: StagedObject) -> Decision:
    max_power = staged.properties[PlexosProperty.MAX_POWER]
    source = SourceValue(
        PlexosClass.BATTERY, staged.name, PlexosProperty.MAX_POWER, max_power, UNIT_MW
    )
    return Decision.derived(max_power, [source], DIRECT_DERIVATION)


_BATTERY_POWER = RatedPower(PlexosClass.BATTERY, PlexosProperty.MAX_POWER, _battery_p_nom)


def _derive_battery(rated: RatedObject) -> StorageUnitMapping:
    capacity = _battery_energy_capacity(rated)
    max_hours = derive_max_hours(capacity, rated.p_nom.value)
    return StorageUnitMapping(
        name=rated.name,
        bus=derive_bus(PlexosClass.BATTERY, rated.name, rated.node),
        carrier=Decision.default(PyPSACarrier.BATTERY, CARRIER_NOTE),
        p_nom=rated.p_nom,
        p_min_pu=Decision.default(STORAGE_FULL_CHARGE_PU, CHARGE_NOTE),
        p_max_pu=Decision.default(STORAGE_FULL_DISCHARGE_PU, FULL_DISCHARGE_NOTE),
        max_hours=max_hours,
        efficiency=_battery_efficiency(rated),
        marginal_cost=Decision.default(STORAGE_MARGINAL_COST, _BATTERY_MARGINAL_COST_NOTE),
        state_of_charge_initial=derive_state_of_charge_initial(
            _battery_initial_level(rated, capacity), rated.p_nom.value * max_hours.value
        ),
        inflow=Decision.default(DEFAULT_INFLOW, NO_RESERVOIR_INFLOW_NOTE),
        cyclic=_battery_cyclic(rated),
        p_nom_extendable=Decision.default(STORAGE_P_NOM_EXTENDABLE, EXTENDABLE_NOTE),
        units=rated.properties.get(PlexosProperty.UNITS),
    )


def _battery_cyclic(rated: RatedObject) -> Decision:
    """Whether the level must return to where it started at the end of the horizon.

    Starting a battery empty where the model states no initial charge invents a shortfall
    in the first hour of every horizon, so the level cycles instead.
    """
    end_effects = rated.properties.get(PlexosProperty.END_EFFECTS_METHOD)
    if end_effects is not None:
        source = SourceValue(
            PlexosClass.BATTERY, rated.name, PlexosProperty.END_EFFECTS_METHOD, end_effects
        )
        cyclic = end_effects == END_EFFECTS_RECYCLE
        note = _BATTERY_RECYCLE_DERIVATION if cyclic else _BATTERY_FREE_DERIVATION
        return Decision.derived(cyclic, [source], note)
    if rated.properties.get(PlexosProperty.INITIAL_SOC) is None:
        return Decision.default(not BATTERY_CYCLIC, _BATTERY_NO_START_NOTE)
    return Decision.default(BATTERY_CYCLIC, _BATTERY_CYCLIC_NOTE)


def _battery_energy_capacity(rated: RatedObject) -> Decision | None:
    """The MWh a battery holds when full, from Capacity or from Duration * Max Power."""
    capacity = rated.properties.get(PlexosProperty.CAPACITY)
    if capacity is not None:
        source = SourceValue(
            PlexosClass.BATTERY, rated.name, PlexosProperty.CAPACITY, capacity, UNIT_MWH
        )
        return Decision.derived(capacity, [source], _CAPACITY_DERIVATION)
    duration = rated.properties.get(PlexosProperty.DURATION)
    if duration is None:
        return None
    return _capacity_from_duration(rated.name, duration, rated.p_nom.value)


def _capacity_from_duration(name: str, duration: float, max_power: float) -> Decision:
    return Decision.derived(
        duration * max_power,
        [
            SourceValue(PlexosClass.BATTERY, name, PlexosProperty.DURATION, duration, UNIT_HOURS),
            SourceValue(PlexosClass.BATTERY, name, PlexosProperty.MAX_POWER, max_power, UNIT_MW),
        ],
        _CAPACITY_FROM_DURATION_DERIVATION,
    )


def _battery_initial_level(rated: RatedObject, capacity: Decision | None) -> Decision | None:
    """Where the battery starts, as MWh, from Initial SoC against its energy capacity."""
    initial_soc = rated.properties.get(PlexosProperty.INITIAL_SOC)
    if initial_soc is None or capacity is None:
        return None
    source = SourceValue(
        PlexosClass.BATTERY, rated.name, PlexosProperty.INITIAL_SOC, initial_soc, UNIT_PERCENT
    )
    return Decision.derived(
        initial_soc / PERCENT * capacity.value,
        [source, *capacity.sources],
        _SOC_FROM_PERCENT_DERIVATION,
    )


def _battery_efficiency(rated: RatedObject) -> Decision:
    charge_efficiency = rated.properties.get(PlexosProperty.CHARGE_EFFICIENCY)
    if charge_efficiency is None:
        return Decision.default(DEFAULT_ROUND_TRIP_EFFICIENCY, EFFICIENCY_NOTE)
    source = SourceValue(
        PlexosClass.BATTERY,
        rated.name,
        PlexosProperty.CHARGE_EFFICIENCY,
        charge_efficiency,
        UNIT_PERCENT,
    )
    return derive_round_trip_efficiency(source)
