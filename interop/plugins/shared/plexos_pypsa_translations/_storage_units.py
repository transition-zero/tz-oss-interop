"""Every PLEXOS storage object -> the PyPSA storage_units table.

Batteries, pumped storage and reservoir hydro each map in their own module; this reads the
staged tables once, runs all three, and records what each decided, skipped or dropped.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import field as dataclass_field

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import (
    UNIT_MW,
    UNIT_MWH,
    UNIT_PERCENT,
)
from interop.plugins.shared.plexos_constants import (
    PlexosClass,
    PlexosProperty,
)
from interop.plugins.shared.plexos_pypsa_translations._batteries import (
    map_battery,
    record_battery_outages,
)
from interop.plugins.shared.plexos_pypsa_translations._shared import (
    ObjectProperties,
)
from interop.plugins.shared.plexos_pypsa_translations._storage_hydro import (
    map_turbine,
    record_reservoir_inflows,
)
from interop.plugins.shared.plexos_pypsa_translations._storage_shared import (
    MappedOrSkipped,
    SkippedComponent,
    StorageLookups,
    StorageUnitMapping,
    build_lookups,
    orphan_storage_skips,
    read_object_names,
    warn_about_skipped,
)
from interop.plugins.shared.plexos_pypsa_translations._storage_turbines import (
    storage_turbine_names,
)
from interop.plugins.shared.plexos_pypsa_translations.decisions import (
    ComponentReporter,
    SourceValue,
    destination_row,
)
from interop.plugins.shared.pypsa_constants import (
    STORAGE_UNITS_DESTINATION_SCHEMA,
    PyPSAComponent,
    PyPSADestinationTable,
    PyPSAStorageUnitCol,
)
from interop.plugins.shared.pypsa_destination import append_destination_rows

log = logging.getLogger(__name__)


def write_storage_units(state: State, mappings: list[StorageUnitMapping]) -> None:
    append_destination_rows(
        state,
        PyPSADestinationTable.STORAGE_UNITS,
        [destination_row(mapping, PyPSAStorageUnitCol.NAME, mapping.name) for mapping in mappings],
        STORAGE_UNITS_DESTINATION_SCHEMA,
    )


# --- reading the staged PLEXOS tables -----------------------------------------


@dataclass(frozen=True)
class _DerivedStorageUnits:
    mappings: list[StorageUnitMapping]
    skipped: list[SkippedComponent]
    dropped: list[_DroppedValue] = dataclass_field(default_factory=list)


def derive_storage_units(state: State) -> _DerivedStorageUnits:
    lookups = build_lookups(state)
    claimed = storage_turbine_names(state)
    turbines = [name for name in read_object_names(state, PlexosClass.GENERATOR) if name in claimed]
    storages = read_object_names(state, PlexosClass.STORAGE)
    return _merge(
        _map_each(read_object_names(state, PlexosClass.BATTERY), map_battery, lookups),
        _map_each(turbines, map_turbine, lookups),
        _DerivedStorageUnits([], orphan_storage_skips(storages, lookups)),
        _DerivedStorageUnits([], [], _dropped_values(state, lookups)),
    )


def _merge(*parts: _DerivedStorageUnits) -> _DerivedStorageUnits:
    return _DerivedStorageUnits(
        mappings=[mapping for part in parts for mapping in part.mappings],
        skipped=[skipped for part in parts for skipped in part.skipped],
        dropped=[dropped for part in parts for dropped in part.dropped],
    )


def _map_each(
    names: list[str],
    map_one: Callable[[str, StorageLookups], MappedOrSkipped],
    lookups: StorageLookups,
) -> _DerivedStorageUnits:
    outcomes = [map_one(name, lookups) for name in names]
    return _DerivedStorageUnits(
        mappings=[out for out in outcomes if isinstance(out, StorageUnitMapping)],
        skipped=[out for out in outcomes if isinstance(out, SkippedComponent)],
    )


# --- the properties PyPSA has no home for -------------------------------------


@dataclass(frozen=True)
class _DroppedValue:
    """A PLEXOS value the mapping read nothing from, recorded so the gap is not silent."""

    source: SourceValue
    note: str


@dataclass(frozen=True)
class _DroppedProperty:
    """Why PyPSA has no home for one PLEXOS property, and the unit its event carries."""

    note: str
    unit: str | None = None


_USABLE_IN_FULL = "PyPSA treats the full energy capacity as usable, so {property} is dropped"
_ONE_ROUND_TRIP = (
    "PyPSA takes one round-trip efficiency, split evenly across charge and discharge, "
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


def _dropped_values(state: State, lookups: StorageLookups) -> list[_DroppedValue]:
    """Every stated property the mapping reads nothing from, whatever became of its object."""
    tails = sorted(set(lookups.tail_by_generator.values()))
    heads = set(lookups.head_by_generator.values())
    storages = read_object_names(state, PlexosClass.STORAGE)
    return [
        *_dropped_from(
            read_object_names(state, PlexosClass.BATTERY),
            PlexosClass.BATTERY,
            lookups.battery_properties,
            _BATTERY_DROPPED,
        ),
        *_dropped_from(storages, PlexosClass.STORAGE, lookups.storage_properties, _STORAGE_DROPPED),
        *_dropped_from(
            [name for name in storages if name not in heads],
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
) -> list[_DroppedValue]:
    return [
        _DroppedValue(
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
    _record(storage_units, recorder)
    write_storage_units(state, storage_units.mappings)
    record_battery_outages(state, storage_units.mappings)
    record_reservoir_inflows(state, storage_units.mappings)


def _record(storage_units: _DerivedStorageUnits, recorder: ScopedRecorder) -> None:
    reporter = ComponentReporter(recorder, PyPSAComponent.STORAGE_UNIT)
    for mapping in storage_units.mappings:
        reporter.record_mapping(mapping.name, mapping)
    for skipped in storage_units.skipped:
        reporter.record_skipped(skipped.source, skipped.note)
        warn_about_skipped(skipped)
    for dropped in storage_units.dropped:
        reporter.record_dropped(dropped.source, dropped.note)
