"""Every PLEXOS storage object -> the PyPSA storage_units table.

Batteries, pumped storage and reservoir hydro each map in their own module; this reads the
staged tables once, runs all three, and records what each decided, skipped or dropped.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Iterable
from dataclasses import dataclass
from typing import NamedTuple

from interop.core.extensions import ExtensionKind, StorageExtension, append_extensions
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import (
    UNIT_MW,
    UNIT_MWH,
    UNIT_PERCENT,
)
from interop.plugins.shared.plexos_constants import (
    PlexosClass,
    PlexosCollection,
    PlexosProperty,
    PlexosResolvedTable,
)
from interop.plugins.shared.plexos_pypsa_translations._batteries import (
    map_battery,
    record_battery_outages,
)
from interop.plugins.shared.plexos_pypsa_translations._expansion import (
    read_sidecar_value,
    record_expansion,
    warn_about_dropped_builds,
)
from interop.plugins.shared.plexos_pypsa_translations._lifespan import (
    read_year,
    record_lifespan,
)
from interop.plugins.shared.plexos_pypsa_translations._shared import (
    ObjectProperties,
    relate_children,
)
from interop.plugins.shared.plexos_pypsa_translations._storage_hydro import (
    map_turbine,
    record_reservoir_inflows,
)
from interop.plugins.shared.plexos_pypsa_translations._storage_shared import (
    MappedOrSkipped,
    StorageLookups,
    StorageUnitMapping,
    build_lookups,
    orphan_storage_skips,
    read_object_names,
)
from interop.plugins.shared.plexos_pypsa_translations._storage_turbines import (
    can_pump,
    storage_turbine_names,
)
from interop.plugins.shared.plexos_pypsa_translations.decisions import (
    ComponentReporter,
    SkipGroup,
    SkippedComponent,
    SourceValue,
    destination_row,
    warn_about_groups,
    warn_about_skips,
)
from interop.plugins.shared.pypsa_constants import (
    STORAGE_UNITS_DESTINATION_SCHEMA,
    PyPSACarrier,
    PyPSAComponent,
    PyPSADestinationTable,
    PyPSAStorageUnitCol,
)
from interop.plugins.shared.pypsa_destination import append_destination_rows


def write_storage_units(state: State, mappings: list[StorageUnitMapping]) -> None:
    append_destination_rows(
        state,
        PyPSADestinationTable.STORAGE_UNITS,
        [destination_row(mapping, PyPSAStorageUnitCol.NAME, mapping.name) for mapping in mappings],
        STORAGE_UNITS_DESTINATION_SCHEMA,
    )


# --- reading the staged PLEXOS tables -----------------------------------------


@dataclass(frozen=True)
class DerivedStorageUnits:
    """Every storage unit, each unit the mapping skips, and what the mapping read."""

    mappings: list[StorageUnitMapping]
    skipped: list[SkippedComponent]
    lookups: StorageLookups
    # The Generators the storage mapping claims, and the units it leaves to the generators.
    turbines: frozenset[str]
    thermal_store_users: frozenset[str]


@dataclass(frozen=True)
class StorageSkips:
    """What the mapping leaves out of the Storages: a whole Storage, or one value it states."""

    skipped: list[SkippedComponent]
    dropped: list[DroppedValue]


# A Storage that only thermal units draw on holds their fuel, not water.
FUEL_STORE_NOTE = (
    "only thermal units draw on this Storage, so it holds fuel, and Sienna states no fuel store"
)
_FUEL_STORE_GROUP = SkipGroup(
    "Storage(s)", "hold fuel that only thermal units draw on, and Sienna states no fuel store"
)


def derive_storage_units(
    state: State, thermal_store_users: frozenset[str] = frozenset()
) -> DerivedStorageUnits:
    """Every storage unit, leaving to the generator mapping each thermal unit that draws on a
    Storage of fuel.
    """
    lookups = build_lookups(state)
    claimed = storage_turbine_names(state) - thermal_store_users
    turbines = [name for name in read_object_names(state, PlexosClass.GENERATOR) if name in claimed]
    batteries = _map_each(read_object_names(state, PlexosClass.BATTERY), map_battery, lookups)
    turbine_units = _map_each(turbines, map_turbine, lookups)
    return DerivedStorageUnits(
        mappings=[*batteries.mappings, *turbine_units.mappings],
        skipped=[*batteries.skipped, *turbine_units.skipped],
        lookups=lookups,
        turbines=claimed,
        thermal_store_users=thermal_store_users,
    )


def build_storage_skips(
    state: State, units: DerivedStorageUnits, held_storages: Collection[str] = frozenset()
) -> StorageSkips:
    """What the mapping leaves out of each Storage, except a Storage that another component
    holds and reports itself.
    """
    storages = [
        name for name in read_object_names(state, PlexosClass.STORAGE) if name not in held_storages
    ]
    return StorageSkips(
        skipped=[
            *orphan_storage_skips(storages, units.lookups),
            *_list_fuel_store_skips(state, units, storages),
        ],
        dropped=[
            *_dropped_values(state, units.lookups, held_storages),
            *_list_unused_pumps(units),
        ],
    )


def _list_fuel_store_skips(
    state: State, units: DerivedStorageUnits, storages: list[str]
) -> list[SkippedComponent]:
    """Each Storage that only thermal units draw on, so it holds fuel that Sienna cannot store."""
    memberships = state.source_topology[PlexosResolvedTable.MEMBERSHIPS]
    heads = relate_children(memberships, PlexosClass.GENERATOR, PlexosCollection.HEAD_STORAGE)
    fuel_stores = {store for name in units.thermal_store_users for store in heads.get(name, [])}
    water_stores = {store for name in units.turbines for store in heads.get(name, [])}
    return [
        SkippedComponent(
            SourceValue(PlexosClass.STORAGE, store, PlexosCollection.HEAD_STORAGE, None),
            FUEL_STORE_NOTE,
            _FUEL_STORE_GROUP,
        )
        for store in sorted(fuel_stores - water_stores)
        if store in storages
    ]


class _MappedUnits(NamedTuple):
    mappings: list[StorageUnitMapping]
    skipped: list[SkippedComponent]


def _map_each(
    names: list[str],
    map_one: Callable[[str, StorageLookups], MappedOrSkipped],
    lookups: StorageLookups,
) -> _MappedUnits:
    outcomes = [map_one(name, lookups) for name in names]
    return _MappedUnits(
        mappings=[out for out in outcomes if isinstance(out, StorageUnitMapping)],
        skipped=[out for out in outcomes if isinstance(out, SkippedComponent)],
    )


# --- the properties PyPSA has no home for -------------------------------------


@dataclass(frozen=True)
class DroppedValue:
    """A PLEXOS value the mapping read nothing from, recorded so the gap is not silent.

    ``warn_with`` is set where one warning names each object that drops a value this way.
    """

    source: SourceValue
    note: str
    warn_with: SkipGroup | None = None


def warn_about_dropped(dropped: Iterable[DroppedValue]) -> None:
    """One warning for each reason that warns, which names each object once."""
    warn_about_groups(
        {(one.warn_with, one.source.name) for one in dropped if one.warn_with is not None}
    )


@dataclass(frozen=True)
class _DroppedProperty:
    """Why PyPSA has no home for one PLEXOS property, and the unit its event carries."""

    note: str
    unit: str | None = None


_USABLE_IN_FULL = "the storage level limits are left at the full range, so {property} is dropped"
_ONE_ROUND_TRIP = (
    "the round-trip efficiency is split evenly across charge and discharge, "
    "so {property} is dropped"
)
_NO_INFLOW_READ = "no turbine draws from this reservoir, so its {property} is dropped"
_CYCLIC_PER_CLASS = (
    "v1 defaults cyclic_state_of_charge per class rather than reading {property}, so it is dropped"
)
_TAIL_ABSORBED = (
    "the tail reservoir is absorbed into the head's storage unit, so its {property} is dropped"
)

_BATTERY_DROPPED: dict[str, _DroppedProperty] = {
    PlexosProperty.MIN_SOC: _DroppedProperty(_USABLE_IN_FULL, UNIT_PERCENT),
    PlexosProperty.MAX_SOC: _DroppedProperty(_USABLE_IN_FULL, UNIT_PERCENT),
    PlexosProperty.DISCHARGE_EFFICIENCY: _DroppedProperty(_ONE_ROUND_TRIP, UNIT_PERCENT),
}

_STORAGE_DROPPED: dict[str, _DroppedProperty] = {
    PlexosProperty.END_EFFECTS_METHOD: _DroppedProperty(_CYCLIC_PER_CLASS),
}

# A head reservoir's inflow refills the storage unit its turbine becomes, so only a
# Storage no turbine draws from has an inflow with nowhere to go.
_HEADLESS_STORAGE_DROPPED: dict[str, _DroppedProperty] = {
    PlexosProperty.NATURAL_INFLOW: _DroppedProperty(_NO_INFLOW_READ, UNIT_MW),
}

_TAIL_DROPPED: dict[str, _DroppedProperty] = {
    PlexosProperty.MAX_VOLUME: _DroppedProperty(_TAIL_ABSORBED, UNIT_MWH),
    PlexosProperty.INITIAL_VOLUME: _DroppedProperty(_TAIL_ABSORBED, UNIT_MWH),
}


class _UnusedPump(NamedTuple):
    """Why a turbine on a head Storage does not pump, and the pump properties it drops."""

    units_by_property: dict[str, str]
    note: str
    group: SkipGroup


_GENERATES_ONLY = "so each one generates and does not pump"

_NO_PUMP_LOAD = _UnusedPump(
    {PlexosProperty.PUMP_EFFICIENCY: UNIT_PERCENT},
    "this Generator states no Pump Load above 0 MW, so it does not pump, and its "
    "{property} is dropped",
    SkipGroup("Generator(s)", "state a Pump Efficiency but no Pump Load", _GENERATES_ONLY),
)

_NO_TAIL = _UnusedPump(
    {PlexosProperty.PUMP_LOAD: UNIT_MW, PlexosProperty.PUMP_EFFICIENCY: UNIT_PERCENT},
    "this Generator has no Tail Storage to pump from, so it does not pump, and its "
    "{property} is dropped",
    SkipGroup("Generator(s)", "state a Pump Load but have no Tail Storage", _GENERATES_ONLY),
)


def _list_unused_pumps(units: DerivedStorageUnits) -> list[DroppedValue]:
    """Each pump property of a turbine that the mapping makes reservoir hydro."""
    properties = units.lookups.read_properties_of(PlexosClass.GENERATOR)
    return [
        dropped
        for mapping in units.mappings
        if mapping.carrier.value is PyPSACarrier.HYDRO
        for dropped in _drop_pump_properties(mapping.name, properties.get(mapping.name, {}))
    ]


def _drop_pump_properties(name: str, stated: dict[str, float]) -> list[DroppedValue]:
    """A reservoir-hydro turbine that can pump has no tail, so that is why it does not pump."""
    reason = _NO_TAIL if can_pump(stated) else _NO_PUMP_LOAD
    return [
        DroppedValue(
            SourceValue(PlexosClass.GENERATOR, name, property_name, stated[property_name], unit),
            reason.note.format(property=property_name),
            reason.group,
        )
        for property_name, unit in reason.units_by_property.items()
        if property_name in stated
    ]


def _dropped_values(
    state: State, lookups: StorageLookups, held_storages: Collection[str]
) -> list[DroppedValue]:
    """Every stated property the mapping reads nothing from, whatever became of its object.

    A Storage in ``held_storages`` keeps its volumes and its inflow, so only the properties
    that no component reads are dropped from it.
    """
    tails = sorted(set(lookups.tail_by_generator.values()) - set(held_storages))
    heads = set(lookups.head_by_generator.values())
    storages = read_object_names(state, PlexosClass.STORAGE)
    return [
        *_dropped_from(
            read_object_names(state, PlexosClass.BATTERY),
            PlexosClass.BATTERY,
            lookups.read_properties_of(PlexosClass.BATTERY),
            _BATTERY_DROPPED,
        ),
        *_dropped_from(storages, PlexosClass.STORAGE, lookups.storage_properties, _STORAGE_DROPPED),
        *_dropped_from(
            [name for name in storages if name not in heads and name not in held_storages],
            PlexosClass.STORAGE,
            lookups.storage_properties,
            _HEADLESS_STORAGE_DROPPED,
        ),
        *_dropped_from(tails, PlexosClass.STORAGE, lookups.storage_properties, _TAIL_DROPPED),
    ]


def _dropped_from(
    names: list[str],
    plexos_class: PlexosClass,
    properties: ObjectProperties,
    dropped: dict[str, _DroppedProperty],
) -> list[DroppedValue]:
    return [
        DroppedValue(
            SourceValue(plexos_class, name, property_name, value, dropped[property_name].unit),
            dropped[property_name].note.format(property=property_name),
        )
        for name in names
        for property_name, value in properties.get(name, {}).items()
        if property_name in dropped
    ]


def map_storage_units(state: State, recorder: ScopedRecorder) -> None:
    """Translate every PLEXOS battery, pumped-storage and reservoir-hydro object at once."""
    storage_units = derive_storage_units(state)
    _record(storage_units, build_storage_skips(state, storage_units), recorder)
    write_storage_units(state, storage_units.mappings)
    _carry_to_extensions(state, storage_units.mappings)
    record_battery_outages(state, storage_units.mappings)
    record_reservoir_inflows(state, storage_units.mappings)


def _record(
    storage_units: DerivedStorageUnits, skips: StorageSkips, recorder: ScopedRecorder
) -> None:
    reporter = ComponentReporter(recorder, PyPSAComponent.STORAGE_UNIT)
    for mapping in storage_units.mappings:
        reporter.record_mapping(mapping.name, mapping)
        record_expansion(mapping.name, mapping.expansion, reporter)
        record_lifespan(mapping.name, mapping.lifespan, reporter)
    warn_about_dropped_builds(mapping.expansion for mapping in storage_units.mappings)
    skipped = [*storage_units.skipped, *skips.skipped]
    for one in skipped:
        reporter.record_skipped(one.source, one.note)
    warn_about_skips(skipped)
    for dropped in skips.dropped:
        reporter.record_dropped(dropped.source, dropped.note)
    warn_about_dropped(skips.dropped)


def _carry_to_extensions(state: State, mappings: list[StorageUnitMapping]) -> None:
    """A storage unit stating none of these carries nothing, so it gets no record.

    A record the next hop has no reader for becomes one NOT_MAPPED event there, and a unit
    the model never offers to build states none of these fields.
    """
    built = (_build_extension_record(mapping) for mapping in mappings)
    records = [record for record in built if record.has_any_value()]
    append_extensions(state.destination_extensions, ExtensionKind.STORAGE, records)


def _build_extension_record(mapping: StorageUnitMapping) -> StorageExtension:
    return StorageExtension(
        name=mapping.name,
        unit_size_mw=read_sidecar_value(mapping.expansion.unit_size),
        technical_life_years=read_sidecar_value(mapping.expansion.technical_life),
        retirement_year=read_year(mapping.lifespan.retirement_year),
        fom_charge_per_mw_year=read_sidecar_value(mapping.expansion.fom_charge),
    )
