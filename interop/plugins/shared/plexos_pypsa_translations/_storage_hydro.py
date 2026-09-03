"""PLEXOS pumped storage and reservoir hydro -> PyPSA StorageUnit.

Both are a turbine ``Generator`` linked to a head ``Storage``; pumped storage also has a
tail. The head reservoir says how much energy the unit holds and what refills it, so the
two paths differ only in whether the unit can pump and whether its level has to cycle.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from interop.core.pipeline import State
from interop.plugins.shared.constants import (
    UNIT_DOLLARS_PER_MWH,
    UNIT_MW,
    UNIT_MWH,
    UNIT_PERCENT,
)
from interop.plugins.shared.plexos_constants import (
    PlexosClass,
    PlexosCollection,
    PlexosProperty,
)
from interop.plugins.shared.plexos_pypsa_translations._storage_shared import (
    CARRIER_NOTE,
    CHARGE_NOTE,
    EFFICIENCY_NOTE,
    EXTENDABLE_NOTE,
    FULL_DISCHARGE_NOTE,
    MAX_HOURS_NOTE,
    NO_RESERVOIR_INFLOW_NOTE,
    HeadReservoir,
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
    skip_object,
)
from interop.plugins.shared.plexos_pypsa_translations.constants import (
    DEFAULT_INFLOW,
    DEFAULT_ROUND_TRIP_EFFICIENCY,
    DEFAULT_UNITS,
    HYDRO_CYCLIC,
    PUMPED_STORAGE_CYCLIC,
    STORAGE_FULL_CHARGE_PU,
    STORAGE_FULL_DISCHARGE_PU,
    STORAGE_GENERATE_ONLY_PU,
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
from interop.plugins.shared.pypsa_time_series import (
    append_metadata,
    metadata_row,
    series_components,
    series_timing,
)

log = logging.getLogger(__name__)


def record_reservoir_inflows(state: State, mappings: list[StorageUnitMapping]) -> None:
    """Point each unit whose head Storage carries a Natural Inflow profile at that series.

    The series is keyed by the Storage's name and the StorageUnit takes the turbine's name,
    so each row names both. A unit whose inflow is not power has no ``inflow_storage``, so it
    keeps the static default that ``_reservoir_inflow`` already recorded.
    """
    frame = state.source_time_series.get((PlexosClass.STORAGE, PlexosProperty.NATURAL_INFLOW))
    if frame is None:
        return
    timing = series_timing(frame)
    present = set(series_components(frame))
    append_metadata(
        state,
        [
            metadata_row(
                component_table=PyPSADestinationTable.STORAGE_UNITS,
                component_name=mapping.name,
                attribute=PyPSAStorageUnitCol.INFLOW,
                source_owner_type=PlexosClass.STORAGE,
                source_series_name=PlexosProperty.NATURAL_INFLOW,
                source_component_name=mapping.inflow_storage,
                scaling_factor=1.0,
                timing=timing,
            )
            for mapping in mappings
            if mapping.inflow_storage is not None and mapping.inflow_storage in present
        ],
    )


_GENERATE_ONLY_NOTE = "conventional hydro generates but does not pump"
_HEADLESS_TURBINE_NOTE = (
    "this Generator has a Tail Storage but no Head Storage and no Pump Efficiency, "
    "so it has no reservoir to draw from"
)
_HYDRO_CYCLIC_NOTE = "hydro follows inflow, so the level need not cycle"
_HYDRO_EFFICIENCY_NOTE = "conventional hydro has no charge side; efficiency is unity"
_INFLOW_DERIVATION = "head Storage.Natural Inflow"
_INFLOW_FROM_PROFILE_NOTE = (
    "the head Storage states its Natural Inflow as a time series, so the static column "
    "stays at the default and the profile refills the reservoir hour by hour"
)
_INFLOW_NOT_POWER_NOTE = (
    "the head Storage names an inflow unit that is not megawatts, so how much power the "
    "reservoir receives is not something this mapping can read"
)
_MAX_VOLUME_DERIVATION = "head Storage.Max Volume"
_NO_INFLOW_STATED_NOTE = "the head Storage states no Natural Inflow; the reservoir does not refill"
_NO_VOM_NOTE = "the PLEXOS Generator states no VO&M Charge"
_PUMPED_STORAGE_CYCLIC_NOTE = "a pumped-storage plant returns to its starting level"
_P_NOM_FROM_UNITS_DERIVATION = "Max Capacity * Units"
_SOC_FROM_VOLUME_DERIVATION = "head Storage.Initial Volume"
_VOLUME_NOT_ENERGY_NOTE = (
    "the head Storage names a volume unit that is not megawatt-hours, so how much energy "
    "the reservoir holds is not something this mapping can read"
)
_VOM_DERIVATION = "VO&M Charge (no fuel, so VO&M only)"

# --- pumped storage and reservoir hydro (Generator-backed) -------------------


@dataclass(frozen=True)
class _GeneratorStorageVariant:
    """What separates a pumped-storage turbine from a reservoir-hydro one."""

    carrier: PyPSACarrier
    p_min_pu: float
    p_min_pu_note: str
    cyclic: bool
    cyclic_note: str
    efficiency_note: str


_PUMPED_STORAGE = _GeneratorStorageVariant(
    carrier=PyPSACarrier.PHS,
    p_min_pu=STORAGE_FULL_CHARGE_PU,
    p_min_pu_note=CHARGE_NOTE,
    cyclic=PUMPED_STORAGE_CYCLIC,
    cyclic_note=_PUMPED_STORAGE_CYCLIC_NOTE,
    efficiency_note=EFFICIENCY_NOTE,
)

_RESERVOIR_HYDRO = _GeneratorStorageVariant(
    carrier=PyPSACarrier.HYDRO,
    p_min_pu=STORAGE_GENERATE_ONLY_PU,
    p_min_pu_note=_GENERATE_ONLY_NOTE,
    cyclic=HYDRO_CYCLIC,
    cyclic_note=_HYDRO_CYCLIC_NOTE,
    efficiency_note=_HYDRO_EFFICIENCY_NOTE,
)


def map_turbine(name: str, lookups: StorageLookups) -> MappedOrSkipped:
    staged = lookups.generator(name)
    variant = _classify_turbine(staged, lookups)
    if variant is None:
        return skip_object(
            PlexosClass.GENERATOR, name, PlexosCollection.HEAD_STORAGE, _HEADLESS_TURBINE_NOTE
        )
    rated = rate_object(staged, _GENERATOR_POWER)
    if isinstance(rated, SkippedComponent):
        return rated
    return _derive_turbine(rated, variant, lookups.head_of(name))


def _classify_turbine(
    staged: StagedObject, lookups: StorageLookups
) -> _GeneratorStorageVariant | None:
    """Which storage variant a Generator is, or None when it has no reservoir to draw from."""
    pumps = PlexosProperty.PUMP_EFFICIENCY in staged.properties
    if lookups.has_head_and_tail(staged.name) or pumps:
        return _PUMPED_STORAGE
    if lookups.has_head(staged.name):
        return _RESERVOIR_HYDRO
    return None


def _generator_p_nom(staged: StagedObject) -> Decision:
    max_capacity = staged.properties[PlexosProperty.MAX_CAPACITY]
    stated_units = staged.properties.get(PlexosProperty.UNITS)
    units = DEFAULT_UNITS if stated_units is None else stated_units
    return Decision.derived(
        max_capacity * units,
        [
            SourceValue(
                PlexosClass.GENERATOR,
                staged.name,
                PlexosProperty.MAX_CAPACITY,
                max_capacity,
                UNIT_MW,
            ),
            SourceValue(PlexosClass.GENERATOR, staged.name, PlexosProperty.UNITS, units),
        ],
        _P_NOM_FROM_UNITS_DERIVATION,
    )


_GENERATOR_POWER = RatedPower(PlexosClass.GENERATOR, PlexosProperty.MAX_CAPACITY, _generator_p_nom)


def _derive_turbine(
    rated: RatedObject, variant: _GeneratorStorageVariant, head: HeadReservoir | None
) -> StorageUnitMapping:
    unreadable = head is not None and head.states_volume_in_other_units
    max_hours = derive_max_hours(
        _reservoir_energy_capacity(head),
        rated.p_nom.value,
        _VOLUME_NOT_ENERGY_NOTE if unreadable else MAX_HOURS_NOTE,
    )
    return StorageUnitMapping(
        name=rated.name,
        bus=derive_bus(PlexosClass.GENERATOR, rated.name, rated.node),
        carrier=Decision.default(variant.carrier, CARRIER_NOTE),
        p_nom=rated.p_nom,
        p_min_pu=Decision.default(variant.p_min_pu, variant.p_min_pu_note),
        p_max_pu=Decision.default(STORAGE_FULL_DISCHARGE_PU, FULL_DISCHARGE_NOTE),
        max_hours=max_hours,
        efficiency=_turbine_efficiency(rated, variant),
        marginal_cost=_marginal_cost(rated),
        state_of_charge_initial=derive_state_of_charge_initial(
            _reservoir_initial_level(head), rated.p_nom.value * max_hours.value
        ),
        inflow=_reservoir_inflow(head),
        cyclic=Decision.default(variant.cyclic, variant.cyclic_note),
        p_nom_extendable=Decision.default(STORAGE_P_NOM_EXTENDABLE, EXTENDABLE_NOTE),
        inflow_storage=_inflow_storage(head),
    )


def _reservoir_inflow(head: HeadReservoir | None) -> Decision:
    """The power flowing into the head reservoir, which PyPSA refills the unit with."""
    if head is None:
        return Decision.default(DEFAULT_INFLOW, NO_RESERVOIR_INFLOW_NOTE)
    if head.states_inflow_in_other_units:
        return Decision.default(DEFAULT_INFLOW, _INFLOW_NOT_POWER_NOTE)
    if head.has_inflow_profile:
        return Decision.default(DEFAULT_INFLOW, _INFLOW_FROM_PROFILE_NOTE)
    if head.inflow is None:
        return Decision.default(DEFAULT_INFLOW, _NO_INFLOW_STATED_NOTE)
    source = SourceValue(
        PlexosClass.STORAGE, head.name, PlexosProperty.NATURAL_INFLOW, head.inflow, UNIT_MW
    )
    return Decision.derived(head.inflow, [source], _INFLOW_DERIVATION)


def _inflow_storage(head: HeadReservoir | None) -> str | None:
    """The Storage whose Natural Inflow series this unit reads, where that inflow is power."""
    if head is None or head.states_inflow_in_other_units:
        return None
    return head.name


def _reservoir_energy_capacity(head: HeadReservoir | None) -> Decision | None:
    """The MWh a turbine's head reservoir holds when full."""
    if head is None or head.max_volume is None:
        return None
    source = SourceValue(
        PlexosClass.STORAGE, head.name, PlexosProperty.MAX_VOLUME, head.max_volume, UNIT_MWH
    )
    return Decision.derived(head.max_volume, [source], _MAX_VOLUME_DERIVATION)


def _reservoir_initial_level(head: HeadReservoir | None) -> Decision | None:
    """Where a turbine's head reservoir starts, as MWh."""
    if head is None or head.initial_volume is None:
        return None
    source = SourceValue(
        PlexosClass.STORAGE, head.name, PlexosProperty.INITIAL_VOLUME, head.initial_volume, UNIT_MWH
    )
    return Decision.derived(head.initial_volume, [source], _SOC_FROM_VOLUME_DERIVATION)


def _turbine_efficiency(rated: RatedObject, variant: _GeneratorStorageVariant) -> Decision:
    pump_efficiency = rated.properties.get(PlexosProperty.PUMP_EFFICIENCY)
    if pump_efficiency is None:
        return Decision.default(DEFAULT_ROUND_TRIP_EFFICIENCY, variant.efficiency_note)
    source = SourceValue(
        PlexosClass.GENERATOR,
        rated.name,
        PlexosProperty.PUMP_EFFICIENCY,
        pump_efficiency,
        UNIT_PERCENT,
    )
    return derive_round_trip_efficiency(source)


def _marginal_cost(rated: RatedObject) -> Decision:
    """A no-fuel unit (pumped storage, hydro) prices only its VO&M charge."""
    vom_charge = rated.properties.get(PlexosProperty.VOM_CHARGE)
    if vom_charge is None:
        return Decision.default(STORAGE_MARGINAL_COST, _NO_VOM_NOTE)
    source = SourceValue(
        PlexosClass.GENERATOR,
        rated.name,
        PlexosProperty.VOM_CHARGE,
        vom_charge,
        UNIT_DOLLARS_PER_MWH,
    )
    return Decision.derived(vom_charge, [source], _VOM_DERIVATION)
