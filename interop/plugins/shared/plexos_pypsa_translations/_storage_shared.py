"""What the three storage paths share: what a StorageUnit is, and the guards ahead of it.

A battery, a pumped-storage turbine and a reservoir-hydro turbine all collapse into one
PyPSA StorageUnit, so all three derive the same ``StorageUnitMapping`` and pass the same
guards on the way: an object with no bus, no rated power or a file-backed capacity is
recorded as skipped rather than written half-formed.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from math import sqrt

from interop.core.pipeline import State
from interop.plugins.shared.constants import (
    UNIT_DOLLARS_PER_MWH,
    UNIT_HOURS,
    UNIT_MW,
    UNIT_MWH,
)
from interop.plugins.shared.plexos_constants import (
    PlexosClass,
    PlexosCollection,
    PlexosObjectCol,
    PlexosProperty,
    PlexosResolvedTable,
)
from interop.plugins.shared.plexos_pypsa_translations._shared import (
    ObjectProperties,
    ObjectUnits,
    collapse_properties_by_object,
    collapse_units_by_object,
    read_file_backed_properties,
    relate_child,
)
from interop.plugins.shared.plexos_pypsa_translations.constants import (
    DEFAULT_STATE_OF_CHARGE_INITIAL,
    DEFAULT_STORAGE_MAX_HOURS,
    PERCENT,
)
from interop.plugins.shared.plexos_pypsa_translations.decisions import (
    Decision,
    SourceValue,
    maps_to,
)
from interop.plugins.shared.plexos_units import conversion_factor
from interop.plugins.shared.pypsa_constants import (
    PyPSAStorageUnitCol,
)
from interop.plugins.shared.pypsa_time_series import (
    series_components,
)

log = logging.getLogger(__name__)

NO_RESERVOIR_INFLOW_NOTE = "this unit has no reservoir, so nothing flows into it"

MAX_HOURS_NOTE = "PLEXOS states no reservoir capacity; max_hours uses the PyPSA default"

FULL_DISCHARGE_NOTE = "full rated power available for discharge"

EXTENDABLE_NOTE = "v1 translates a dispatch model; capacity is fixed"

EFFICIENCY_NOTE = "PLEXOS states no round-trip efficiency; storage is modelled lossless"

CHARGE_NOTE = "full rated power available for charging (negative dispatch is charging)"

CARRIER_NOTE = "PLEXOS carries no carrier; the object's class names it"

_SOC_NOTE = "PLEXOS states no initial level; state_of_charge_initial defaults to empty"
_ORPHAN_STORAGE_NOTE = "no Generator names this Storage as a head or tail, so it cannot dispatch"
_NO_NODE_NOTE = "this object is on no Node, so it has no bus to connect to"

# Stands in for the value of a file-backed property, which PLEXOS states as a path.
_DATA_FILE = "data file"

_BUS_DERIVATION = "Nodes membership -> bus"
_ROUND_TRIP_DERIVATION = "sqrt(round-trip / 100), split symmetrically"
# The Storage properties whose stated unit decides whether they are energy at all.
_VOLUME_PROPERTIES = (PlexosProperty.MAX_VOLUME, PlexosProperty.INITIAL_VOLUME)

_PER_P_NOM_DERIVATION = " / p_nom"
_CLAMPED_DERIVATION = ", clamped to 0..p_nom * max_hours"


@dataclass(frozen=True)
class StorageUnitMapping:
    """One PyPSA StorageUnit: each destination value, where it came from, and what it fills.

    Declaring the destination columns beside each decision is what lets the recorded events
    and the emitted row come from one list rather than three.
    """

    name: str
    bus: Decision = maps_to(PyPSAStorageUnitCol.BUS)
    carrier: Decision = maps_to(PyPSAStorageUnitCol.CARRIER)
    p_nom: Decision = maps_to(PyPSAStorageUnitCol.P_NOM, unit=UNIT_MW)
    p_min_pu: Decision = maps_to(PyPSAStorageUnitCol.P_MIN_PU)
    p_max_pu: Decision = maps_to(PyPSAStorageUnitCol.P_MAX_PU)
    max_hours: Decision = maps_to(PyPSAStorageUnitCol.MAX_HOURS, unit=UNIT_HOURS)
    efficiency: Decision = maps_to(
        PyPSAStorageUnitCol.EFFICIENCY_STORE, PyPSAStorageUnitCol.EFFICIENCY_DISPATCH
    )
    marginal_cost: Decision = maps_to(PyPSAStorageUnitCol.MARGINAL_COST, unit=UNIT_DOLLARS_PER_MWH)
    state_of_charge_initial: Decision = maps_to(
        PyPSAStorageUnitCol.STATE_OF_CHARGE_INITIAL, unit=UNIT_MWH
    )
    inflow: Decision = maps_to(PyPSAStorageUnitCol.INFLOW, unit=UNIT_MW)
    cyclic: Decision = maps_to(PyPSAStorageUnitCol.CYCLIC_STATE_OF_CHARGE)
    p_nom_extendable: Decision = maps_to(PyPSAStorageUnitCol.P_NOM_EXTENDABLE)
    # Units is a Battery-only reading; a units-out trace derates against it.
    units: float | None = None
    # The head Storage whose Natural Inflow this unit reads, where that inflow is power. An
    # inflow profile is keyed by the Storage's name, not by this unit's.
    inflow_storage: str | None = None


def warn_about_skipped(skipped: SkippedComponent) -> None:
    """A skip is recorded per component, and warned about, so neither view alone hides it."""
    log.warning(
        "plexos: dropping %s %r: %s",
        skipped.source.component,
        skipped.source.name,
        skipped.note,
    )


@dataclass(frozen=True)
class SkippedComponent:
    """A PLEXOS object the mapping deliberately did not translate, and why."""

    source: SourceValue
    note: str


# Every storage object ends as one or the other: a unit to write, or a recorded reason not to.
MappedOrSkipped = StorageUnitMapping | SkippedComponent


def read_object_names(state: State, plexos_class: PlexosClass) -> list[str]:
    """Every staged object of a class, whether or not it states any property.

    Walking the object frame rather than the property table is what makes the generator
    and storage mappings split the Generator class between them exactly.
    """
    objects = state.source_topology.get(plexos_class)
    if objects is None:
        return []
    names: list[str] = objects.collect()[PlexosObjectCol.NAME].to_list()
    return names


@dataclass(frozen=True)
class HeadReservoir:
    """The head ``Storage`` a turbine draws from, as energy and as power.

    PLEXOS measures a reservoir in whatever suits the model (megawatt-hours, cubic metres,
    acre-feet) and its inflow to match (megawatts, cumec), so each value is left out where
    the model names a unit that does not convert. A model naming no unit is taken at its
    word. The two ``states_*_in_other_units`` flags tell a value left out for that reason
    apart from one the model never stated.
    """

    name: str
    max_volume: float | None
    initial_volume: float | None
    inflow: float | None
    states_volume_in_other_units: bool
    states_inflow_in_other_units: bool
    # ``inflow`` holds the scalar reading only, so a file-backed Natural Inflow leaves it None.
    has_inflow_profile: bool


@dataclass(frozen=True)
class StagedObject:
    """One staged PLEXOS object as the shared guards read it, whatever its class."""

    name: str
    properties: dict[str, float]
    node: str | None
    file_backed: list[str]


@dataclass(frozen=True)
class StorageLookups:
    """The per-object properties and memberships the three storage paths read."""

    battery_properties: ObjectProperties
    generator_properties: ObjectProperties
    storage_properties: ObjectProperties
    node_by_battery: dict[str, str]
    node_by_generator: dict[str, str]
    head_by_generator: dict[str, str]
    tail_by_generator: dict[str, str]
    file_backed_by_battery: dict[str, list[str]]
    file_backed_by_generator: dict[str, list[str]]
    storage_units: ObjectUnits
    storages_with_inflow_profile: set[str]

    def battery(self, name: str) -> StagedObject:
        return StagedObject(
            name=name,
            properties=self.battery_properties.get(name, {}),
            node=self.node_by_battery.get(name),
            file_backed=self.file_backed_by_battery.get(name, []),
        )

    def generator(self, name: str) -> StagedObject:
        return StagedObject(
            name=name,
            properties=self.generator_properties.get(name, {}),
            node=self.node_by_generator.get(name),
            file_backed=self.file_backed_by_generator.get(name, []),
        )

    def has_head_and_tail(self, generator: str) -> bool:
        return self.has_head(generator) and self.has_tail(generator)

    def has_head(self, generator: str) -> bool:
        return generator in self.head_by_generator

    def has_tail(self, generator: str) -> bool:
        return generator in self.tail_by_generator

    def turbine_fed_storages(self) -> set[str]:
        """The Storages some Generator names as its head or its tail."""
        return set(self.head_by_generator.values()) | set(self.tail_by_generator.values())

    def head_of(self, generator: str) -> HeadReservoir | None:
        storage = self.head_by_generator.get(generator)
        if storage is None:
            return None
        volumes = self.storage_properties.get(storage, {})
        units = self.storage_units.get(storage, {})
        return HeadReservoir(
            name=storage,
            max_volume=_value_in_unit(volumes, units, PlexosProperty.MAX_VOLUME, UNIT_MWH),
            initial_volume=_value_in_unit(volumes, units, PlexosProperty.INITIAL_VOLUME, UNIT_MWH),
            inflow=_value_in_unit(volumes, units, PlexosProperty.NATURAL_INFLOW, UNIT_MW),
            states_volume_in_other_units=_states_volume_in_other_units(volumes, units),
            states_inflow_in_other_units=_states_inflow_in_other_units(volumes, units),
            has_inflow_profile=storage in self.storages_with_inflow_profile,
        )


def _value_in_unit(
    volumes: dict[str, float], units: dict[str, str | None], property_name: str, wanted: str
) -> float | None:
    """A stated property, unless the model names a unit that does not convert into ``wanted``.

    A model that names no unit is taken at its word, because a published export can leave
    the unit blank and its numbers are still the ones the modeller meant.
    """
    if _names_another_unit(units, property_name, wanted):
        return None
    return volumes.get(property_name)


def _names_another_unit(units: dict[str, str | None], property_name: str, wanted: str) -> bool:
    """Whether the model names a unit that does not convert into ``wanted``.

    A volume in GWh or an inflow in GW converts as it stages, so the value here already
    carries the unit the mapping reads. A volume in cubic metres and an inflow in cumec do
    not convert, because both are quantities of water.
    """
    stated = units.get(property_name)
    return stated is not None and conversion_factor(stated, wanted) is None


def _states_volume_in_other_units(volumes: dict[str, float], units: dict[str, str | None]) -> bool:
    return any(
        volumes.get(name) is not None and _names_another_unit(units, name, UNIT_MWH)
        for name in _VOLUME_PROPERTIES
    )


def _states_inflow_in_other_units(volumes: dict[str, float], units: dict[str, str | None]) -> bool:
    return volumes.get(PlexosProperty.NATURAL_INFLOW) is not None and _names_another_unit(
        units, PlexosProperty.NATURAL_INFLOW, UNIT_MW
    )


def build_lookups(state: State) -> StorageLookups:
    properties = state.source_topology[PlexosResolvedTable.PROPERTIES]
    memberships = state.source_topology[PlexosResolvedTable.MEMBERSHIPS]
    return StorageLookups(
        battery_properties=collapse_properties_by_object(properties, PlexosClass.BATTERY),
        generator_properties=collapse_properties_by_object(properties, PlexosClass.GENERATOR),
        storage_properties=collapse_properties_by_object(properties, PlexosClass.STORAGE),
        node_by_battery=relate_child(memberships, PlexosClass.BATTERY, PlexosCollection.NODES),
        node_by_generator=relate_child(memberships, PlexosClass.GENERATOR, PlexosCollection.NODES),
        head_by_generator=relate_child(
            memberships, PlexosClass.GENERATOR, PlexosCollection.HEAD_STORAGE
        ),
        tail_by_generator=relate_child(
            memberships, PlexosClass.GENERATOR, PlexosCollection.TAIL_STORAGE
        ),
        file_backed_by_battery=read_file_backed_properties(properties, PlexosClass.BATTERY),
        file_backed_by_generator=read_file_backed_properties(properties, PlexosClass.GENERATOR),
        storage_units=collapse_units_by_object(properties, PlexosClass.STORAGE),
        storages_with_inflow_profile=_storages_with_inflow_profile(state),
    )


def _storages_with_inflow_profile(state: State) -> set[str]:
    """The Storages whose Natural Inflow arrives as a staged time series."""
    frame = state.source_time_series.get((PlexosClass.STORAGE, PlexosProperty.NATURAL_INFLOW))
    return set() if frame is None else set(series_components(frame))


def orphan_storage_skips(names: list[str], lookups: StorageLookups) -> list[SkippedComponent]:
    turbine_fed = lookups.turbine_fed_storages()
    return [
        SkippedComponent(SourceValue(PlexosClass.STORAGE, name, None, None), _ORPHAN_STORAGE_NOTE)
        for name in names
        if name not in turbine_fed
    ]


# --- the guards every storage class shares ------------------------------------


@dataclass(frozen=True)
class RatedPower:
    """How one storage class states its rated power, so the guards read the same for all."""

    plexos_class: PlexosClass
    capacity_property: PlexosProperty
    derive: Callable[[StagedObject], Decision]


@dataclass(frozen=True)
class RatedObject:
    """A storage object that passed every guard: what it states, its bus, its rated power."""

    name: str
    properties: dict[str, float]
    node: str
    p_nom: Decision


def rate_object(staged: StagedObject, rating: RatedPower) -> RatedObject | SkippedComponent:
    """The object with its rated power, or the recorded reason it cannot become a unit."""
    if staged.node is None:
        return skip_object(rating.plexos_class, staged.name, PlexosCollection.NODES, _NO_NODE_NOTE)
    if rating.capacity_property in staged.file_backed:
        return _skipped_file_backed(rating, staged.name)
    if rating.capacity_property not in staged.properties:
        return _skipped_without_capacity(rating, staged.name)
    p_nom = rating.derive(staged)
    if p_nom.value <= 0.0:
        return _skipped_zero_p_nom(rating, staged.name, p_nom.value)
    return RatedObject(staged.name, staged.properties, staged.node, p_nom)


def skip_object(
    plexos_class: PlexosClass, name: str, attribute: str | None, note: str
) -> SkippedComponent:
    return SkippedComponent(SourceValue(plexos_class, name, attribute, None), note)


def _skipped_file_backed(rating: RatedPower, name: str) -> SkippedComponent:
    note = (
        f"{rating.capacity_property} comes from a data file rather than a value, so this "
        "unit has no rated power to size it"
    )
    source = SourceValue(rating.plexos_class, name, rating.capacity_property, _DATA_FILE, UNIT_MW)
    return SkippedComponent(source, note)


def _skipped_without_capacity(rating: RatedPower, name: str) -> SkippedComponent:
    note = (
        f"PLEXOS states no {rating.capacity_property}, so the object states no rated "
        "power, which the StorageUnit mapping cannot default"
    )
    return skip_object(rating.plexos_class, name, rating.capacity_property, note)


def _skipped_zero_p_nom(rating: RatedPower, name: str, p_nom: float) -> SkippedComponent:
    """The rated power goes in the note, not on the capacity property, which may be positive."""
    note = f"rated power works out to {p_nom} MW, so this unit cannot dispatch"
    return skip_object(rating.plexos_class, name, None, note)


# --- shared across every variant ---------------------------------------------


def derive_max_hours(
    capacity: Decision | None, p_nom: float, absent_note: str = MAX_HOURS_NOTE
) -> Decision:
    """Hours of storage at rated power, from whichever property stated the energy capacity."""
    if capacity is None:
        return Decision.default(DEFAULT_STORAGE_MAX_HOURS, absent_note)
    return Decision.derived(
        capacity.value / p_nom, capacity.sources, capacity.explanation + _PER_P_NOM_DERIVATION
    )


def derive_state_of_charge_initial(level: Decision | None, usable_mwh: float) -> Decision:
    """The starting level, held inside the capacity PyPSA enforces (``p_nom * max_hours``)."""
    if level is None:
        return Decision.default(DEFAULT_STATE_OF_CHARGE_INITIAL, _SOC_NOTE)
    held = min(max(level.value, 0.0), usable_mwh)
    if held == level.value:
        return level
    return Decision.derived(held, level.sources, level.explanation + _CLAMPED_DERIVATION)


def derive_bus(plexos_class: PlexosClass, name: str, node: str) -> Decision:
    source = SourceValue(plexos_class, name, PlexosCollection.NODES, node)
    return Decision.derived(node, [source], _BUS_DERIVATION)


def derive_round_trip_efficiency(source: SourceValue) -> Decision:
    """PLEXOS states a round-trip percentage; PyPSA wants it split across charge and discharge."""
    return Decision.derived(sqrt(float(source.value) / PERCENT), [source], _ROUND_TRIP_DERIVATION)
