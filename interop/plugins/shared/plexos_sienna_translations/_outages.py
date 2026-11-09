"""PLEXOS Forced Outage Rate and Mean Time to Repair -> a Sienna GeometricDistributionForcedOutage.

PLEXOS states the share of the time a unit is out, as a percentage, and the hours one repair
takes. Sienna states the minutes one recovery takes, and the chance in each minute that a
unit in service fails. In a two-state model the share of the time out is
``p / (p + 1 / T)`` for a chance ``p`` and a recovery time ``T``, so
``p = r / (1 - r) / T`` for a share ``r``.

The attribute describes a component that an earlier sub-step wrote, so this sub-step runs
after every unit has its Sienna id. A unit the translation left out takes no attribute.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field

import polars as pl

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import UNIT_HOURS, UNIT_MINUTES, UNIT_PERCENT
from interop.plugins.shared.plexos_constants import (
    PlexosClass,
    PlexosObjectCol,
    PlexosProperty,
    PlexosResolvedTable,
)
from interop.plugins.shared.plexos_pypsa_translations._shared import (
    collapse_properties_by_object,
    read_file_backed_properties,
)
from interop.plugins.shared.plexos_sienna_translations._shared import (
    dropped,
    plexos_field,
    record,
)
from interop.plugins.shared.sienna_constants import (
    FORCED_OUTAGES_DESTINATION_SCHEMA,
    SIENNA_ID_COLUMN,
    SIENNA_NAME_COLUMN,
    SiennaComponent,
    SiennaForcedOutageCol,
    SiennaSupplementalAttribute,
)
from interop.plugins.shared.sienna_events import (
    build_defaulted,
    build_derived,
    build_sienna_field,
    build_sienna_source,
)
from interop.plugins.shared.translation_runner import build_first_free_id
from interop.plugins.shared.warning_text import name_a_few
from interop.ports.outbound.reporting import DestinationField, SourceField, TranslationEvent

log = logging.getLogger(__name__)

_MINUTES_PER_HOUR = 60.0
_PERCENT = 100.0
_OUTAGE = SiennaSupplementalAttribute.GEOMETRIC_DISTRIBUTION_FORCED_OUTAGE

# The Sienna types each PLEXOS class that states a forced outage can become.
_SIENNA_TYPES: dict[PlexosClass, tuple[SiennaComponent, ...]] = {
    PlexosClass.GENERATOR: (
        SiennaComponent.THERMAL_STANDARD,
        SiennaComponent.RENEWABLE_DISPATCH,
        SiennaComponent.RENEWABLE_NON_DISPATCH,
        SiennaComponent.HYDRO_DISPATCH,
        SiennaComponent.HYDRO_TURBINE,
        SiennaComponent.ENERGY_RESERVOIR_STORAGE,
    ),
    PlexosClass.BATTERY: (SiennaComponent.ENERGY_RESERVOIR_STORAGE,),
}

_RECOVERY_DERIVATION = "Mean Time to Repair in hours x 60"
_PROBABILITY_DERIVATION = (
    "Forced Outage Rate / 100 / (1 - Forced Outage Rate / 100) / mean_time_to_recovery"
)
_ID_NOTE = (
    "assigned by row position in the forced outage table, after the ids of earlier components"
)
_MONITORED_NOTE = "PLEXOS names no component whose state an outage watches; the list is empty"
_IDENTIFIER_DERIVATION = "the PLEXOS name of the unit the outage describes"
_FULL_OUTAGE_NOTE = (
    "a Forced Outage Rate of 100 % or more leaves the unit no time in service to fail from, "
    "so no forced outage states it"
)
_NO_REPAIR_NOTE = (
    "the unit states no Mean Time to Repair above 0, so neither the recovery time nor the "
    "chance of failure can be stated, and no forced outage is written"
)
_FILE_BACKED_NOTE = (
    "Forced Outage Rate comes from a data file, and a forced outage states one rate, so no "
    "forced outage is written"
)
_UNUSED_REPAIR_NOTE = (
    "the unit states no Forced Outage Rate above 0, so it never fails and its Mean Time to "
    "Repair has no forced outage to belong to"
)


@dataclass(frozen=True)
class _Unit:
    """One translated unit, and the outage values its PLEXOS object states."""

    plexos_class: PlexosClass
    name: str
    sienna_type: SiennaComponent
    sienna_id: int
    rate: float | None
    repair_hours: float | None
    is_rate_file_backed: bool


@dataclass(frozen=True)
class _Reading:
    """What one unit becomes: an outage row or none, and the events behind it."""

    unit: _Unit
    events: Sequence[TranslationEvent] = field(default_factory=list)
    row: dict[str, object] | None = None
    is_left_out: bool = False


def map_forced_outages(state: State, recorder: ScopedRecorder) -> None:
    """Write one forced outage for each translated unit that states a usable one."""
    readings = [_read_unit(unit) for unit in _list_units(state)]
    rows = _number_rows(readings, build_first_free_id(state))
    for reading in readings:
        record(recorder, reading.events)
    for row in rows:
        record(recorder, _build_id_events(row))
    if rows:
        state.destination_tables[_OUTAGE] = pl.DataFrame(
            rows, schema=FORCED_OUTAGES_DESTINATION_SCHEMA
        )
    warn_left_out([reading.unit.name for reading in readings if reading.is_left_out])


def warn_left_out(names: list[str]) -> None:
    if names:
        log.warning(
            "plexos: %d unit(s) state a forced outage that Sienna cannot hold, so each keeps "
            "none: %s",
            len(names),
            name_a_few(sorted(names)),
        )


def _number_rows(readings: list[_Reading], first_id: int) -> list[dict[str, object]]:
    """Each outage row, with an id that counts on from the ids of earlier components."""
    rows = [reading.row for reading in readings if reading.row is not None]
    return [{SiennaForcedOutageCol.ID: first_id + index, **row} for index, row in enumerate(rows)]


def _list_units(state: State) -> list[_Unit]:
    properties = state.source_topology.get(PlexosResolvedTable.PROPERTIES)
    if properties is None:
        return []
    return [
        unit
        for plexos_class, sienna_types in _SIENNA_TYPES.items()
        for unit in _list_class_units(state, properties, plexos_class, sienna_types)
    ]


def _list_class_units(
    state: State,
    properties: pl.LazyFrame,
    plexos_class: PlexosClass,
    sienna_types: tuple[SiennaComponent, ...],
) -> list[_Unit]:
    """The objects of one PLEXOS class that a Sienna table holds, with their outage values."""
    scalars = collapse_properties_by_object(properties, plexos_class)
    file_backed = read_file_backed_properties(properties, plexos_class)
    translated = _find_translated(state, sienna_types)
    return [
        _Unit(
            plexos_class=plexos_class,
            name=name,
            sienna_type=translated[name][0],
            sienna_id=translated[name][1],
            rate=scalars.get(name, {}).get(PlexosProperty.FORCED_OUTAGE_RATE),
            repair_hours=scalars.get(name, {}).get(PlexosProperty.MEAN_TIME_TO_REPAIR),
            is_rate_file_backed=PlexosProperty.FORCED_OUTAGE_RATE in file_backed.get(name, []),
        )
        for name in _list_object_names(state, plexos_class)
        if name in translated
    ]


def _list_object_names(state: State, plexos_class: PlexosClass) -> list[str]:
    objects = state.source_topology.get(plexos_class)
    if objects is None:
        return []
    names: list[str] = (
        objects.select(PlexosObjectCol.NAME).collect()[PlexosObjectCol.NAME].to_list()
    )
    return sorted(names)


def _find_translated(
    state: State, sienna_types: tuple[SiennaComponent, ...]
) -> dict[str, tuple[SiennaComponent, int]]:
    """Each translated unit's Sienna type and id, by name. The first type that holds it wins."""
    found: dict[str, tuple[SiennaComponent, int]] = {}
    for sienna_type in sienna_types:
        table = state.destination_tables.get(sienna_type)
        if table is None:
            continue
        for name, sienna_id in table.select(SIENNA_NAME_COLUMN, SIENNA_ID_COLUMN).iter_rows():
            found.setdefault(name, (sienna_type, sienna_id))
    return found


def _read_unit(unit: _Unit) -> _Reading:
    """The outage one unit states, or the reason it states none."""
    if unit.is_rate_file_backed:
        return _Reading(unit, dropped([_rate_source(unit)], _FILE_BACKED_NOTE), is_left_out=True)
    if unit.rate is None or unit.rate <= 0:
        return _read_unused_repair(unit)
    if unit.rate >= _PERCENT:
        return _Reading(unit, dropped([_rate_source(unit)], _FULL_OUTAGE_NOTE), is_left_out=True)
    if unit.repair_hours is None or unit.repair_hours <= 0:
        return _Reading(unit, dropped([_rate_source(unit)], _NO_REPAIR_NOTE), is_left_out=True)
    return _read_outage(unit, unit.rate, unit.repair_hours)


def _read_unused_repair(unit: _Unit) -> _Reading:
    """A unit that never fails. A repair time it states has nothing to belong to."""
    if unit.repair_hours is None:
        return _Reading(unit)
    return _Reading(unit, dropped([_repair_source(unit)], _UNUSED_REPAIR_NOTE))


def _read_outage(unit: _Unit, rate: float, repair_hours: float) -> _Reading:
    recovery_minutes = convert_hours_to_minutes(repair_hours)
    row: dict[str, object] = {
        SiennaForcedOutageCol.MEAN_TIME_TO_RECOVERY: recovery_minutes,
        SiennaForcedOutageCol.OUTAGE_TRANSITION_PROBABILITY: derive_transition_probability(
            rate, recovery_minutes
        ),
        SiennaForcedOutageCol.MONITORED_COMPONENTS: [],
        SiennaForcedOutageCol.IDENTIFIER: unit.name,
        SiennaForcedOutageCol.COMPONENT_TYPE: unit.sienna_type.value,
        SiennaForcedOutageCol.COMPONENT_ID: unit.sienna_id,
    }
    return _Reading(unit, _build_outage_events(unit, row), row)


def convert_hours_to_minutes(hours: float) -> float:
    return hours * _MINUTES_PER_HOUR


def derive_transition_probability(rate_percent: float, recovery_minutes: float) -> float:
    """The chance in each minute of failure that gives this share of the time out."""
    share = rate_percent / _PERCENT
    return share / (1 - share) / recovery_minutes


def _build_outage_events(unit: _Unit, row: dict[str, object]) -> list[TranslationEvent]:
    """The full chain: the repair time becomes the recovery time, which the chance reads."""
    recovery = row[SiennaForcedOutageCol.MEAN_TIME_TO_RECOVERY]
    recovery_read = build_sienna_source(
        _OUTAGE, unit.name, SiennaForcedOutageCol.MEAN_TIME_TO_RECOVERY, recovery, UNIT_MINUTES
    )
    name_read = plexos_field(unit.plexos_class, unit.name, PlexosObjectCol.NAME, unit.name)
    return [
        *build_derived(
            [_repair_source(unit)],
            [_outage_field(unit, row, SiennaForcedOutageCol.MEAN_TIME_TO_RECOVERY, UNIT_MINUTES)],
            _RECOVERY_DERIVATION,
        ),
        *build_derived(
            [_rate_source(unit), recovery_read],
            [_outage_field(unit, row, SiennaForcedOutageCol.OUTAGE_TRANSITION_PROBABILITY)],
            _PROBABILITY_DERIVATION,
        ),
        *build_defaulted(
            [_outage_field(unit, row, SiennaForcedOutageCol.MONITORED_COMPONENTS)], _MONITORED_NOTE
        ),
        *build_derived(
            [name_read],
            [_outage_field(unit, row, SiennaForcedOutageCol.IDENTIFIER)],
            _IDENTIFIER_DERIVATION,
        ),
    ]


def _build_id_events(row: dict[str, object]) -> list[TranslationEvent]:
    name = str(row[SiennaForcedOutageCol.IDENTIFIER])
    id_field = build_sienna_field(
        _OUTAGE, name, SiennaForcedOutageCol.ID, row[SiennaForcedOutageCol.ID]
    )
    return build_defaulted([id_field], _ID_NOTE)


def _rate_source(unit: _Unit) -> SourceField:
    return plexos_field(
        unit.plexos_class, unit.name, PlexosProperty.FORCED_OUTAGE_RATE, unit.rate, UNIT_PERCENT
    )


def _repair_source(unit: _Unit) -> SourceField:
    return plexos_field(
        unit.plexos_class,
        unit.name,
        PlexosProperty.MEAN_TIME_TO_REPAIR,
        unit.repair_hours,
        UNIT_HOURS,
    )


def _outage_field(
    unit: _Unit, row: dict[str, object], column: str, unit_label: str | None = None
) -> DestinationField:
    return build_sienna_field(_OUTAGE, unit.name, column, row[column], unit_label)
