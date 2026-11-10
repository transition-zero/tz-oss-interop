"""PLEXOS Reserve -> Sienna OnlineReserve or OfflineReserve, and one association per unit.

The PLEXOS reading is the one the extensions sidecar record already holds, so the sidecar
and the service always agree. A replacement reserve, which units that are off can supply
once they start, becomes an OfflineReserve. Every other product that states a direction
becomes an OnlineReserve. Each unit the reserve names joins the service through one row of
the document's ``service_associations`` list.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any, NamedTuple

import polars as pl

from interop.core.extensions import (
    CompanionSeriesCol,
    ExtensionKind,
    ReserveCompanionCol,
    ReserveDirection,
    ReserveExtension,
    ReserveKind,
)
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import UNIT_MINUTES, UNIT_MW, UNIT_SECONDS
from interop.plugins.shared.plexos_constants import (
    PlexosClass,
    PlexosCollection,
    PlexosProperty,
    PlexosResolvedTable,
)
from interop.plugins.shared.plexos_pypsa_translations._shared import (
    collapse_properties_by_object,
    relate_children,
)
from interop.plugins.shared.plexos_pypsa_translations.decisions import (
    Decision,
    MappedColumns,
    SkipGroup,
    SkippedComponent,
    SourceValue,
    destination_row,
    maps_to,
    warn_about_groups,
    warn_about_skips,
)
from interop.plugins.shared.plexos_sienna_translations._shared import (
    SiennaComponentReporter,
    TranslatedUnit,
    build_translated_units,
)
from interop.plugins.shared.sienna_constants import (
    SiennaComponent,
    SiennaReserveCol,
    SiennaReserveDirection,
    SiennaSchemasSystem,
    SiennaServiceAssociationCol,
)
from interop.plugins.shared.sienna_time_series import (
    DEFAULT_RESOLUTION_MINUTES,
    TimeSeriesInfo,
    build_ts_info,
    build_ts_info_by_component,
    ts_association_row,
)
from interop.plugins.shared.translation_runner import build_first_free_id

# PLEXOS states no reserve time frame, so a unit may take one hourly snapshot to respond.
DEFAULT_TIME_FRAME_MINUTES: float = DEFAULT_RESOLUTION_MINUTES
# The SiennaSchemas 0.2 default of OnlineReserve.sustained_time.
DEFAULT_SUSTAINED_TIME_MINUTES: float = 60.0
FULL_OUTPUT_FRACTION: float = 1.0
FULL_PARTICIPATION: float = 1.0
NOTHING_DEPLOYED: float = 0.0
SECONDS_PER_MINUTE: float = 60.0

_REQUIREMENT_KEY = (str(PlexosClass.RESERVE), str(PlexosProperty.MIN_PROVISION))
_NO_SERIES = build_ts_info(0, None, None)
_ASSOCIATIONS_COLUMNS = MappedColumns((SiennaSchemasSystem.SERVICE_ASSOCIATIONS,))

_DIRECTIONS: dict[ReserveDirection, SiennaReserveDirection] = {
    ReserveDirection.UP: SiennaReserveDirection.UP,
    ReserveDirection.DOWN: SiennaReserveDirection.DOWN,
    ReserveDirection.SYMMETRIC: SiennaReserveDirection.SYMMETRIC,
}

_ID_NOTE = "assigned by row position in the component's table, after the ids of earlier components"
_AVAILABLE_NOTE = "the Reserve states no Is Enabled, so the service is available"
_AVAILABLE_DERIVATION = "Is Enabled -> available"
_TIME_FRAME_NOTE = "PLEXOS states no reserve time frame; a unit may take one hourly snapshot"
_SUSTAINED_NOTE = "the Reserve states no Duration; the SiennaSchemas default of 60 minutes"
_SUSTAINED_DERIVATION = "Duration in seconds / 60"
_OUTPUT_FRACTION_NOTE = "PLEXOS caps no unit's share of its output; every unit may give it all"
_PARTICIPATION_NOTE = "PLEXOS caps no unit's share of the requirement"
_DEPLOYED_NOTE = "PLEXOS states no deployed share; the service is held, not deployed"
_REQUIREMENT_DERIVATION = "Min Provision in MW"
_PEAK_DERIVATION = "the peak of the requirement series; the series holds every snapshot"
_DIRECTION_DERIVATION = "the PLEXOS Type code -> the direction it names"
_ASSOCIATION_DERIVATION = "one service association for each unit the Reserve names"
_SHORTAGE_NOTE = (
    "the translation writes no reserve demand curve to the service's variable field, so VoRS "
    "stays in the sidecar"
)
_EXCLUSIVE_NOTE = (
    "Sienna holds no exclusion between two services, so Mutually Exclusive stays in the sidecar"
)

_NO_DIRECTION_NOTE = (
    "the PLEXOS Type names no direction, and an OnlineReserve must state one, so the reserve "
    "becomes no Sienna service"
)
_INERTIA_NOTE = "an inertia reserve is not a quantity of MW, so it becomes no Sienna service"
_NO_REQUIREMENT_NOTE = "the reserve states no requirement in MW, so it becomes no Sienna service"
_NO_DIRECTION = SkipGroup("Reserve(s)", "state no direction an OnlineReserve can take")
_INERTIA = SkipGroup("Reserve(s)", "are inertia reserves, which no Sienna service holds")
_NO_REQUIREMENT = SkipGroup("Reserve(s)", "state no requirement in MW")
_ABSENT_CONTRIBUTOR = SkipGroup(
    "reserve contributor(s)", "are not in the Sienna system", "so each joins no service"
)


@dataclass(frozen=True)
class _OfflineMapping:
    """One Sienna OfflineReserve: each destination value and where it came from."""

    name: str
    available: Decision = maps_to(SiennaReserveCol.AVAILABLE)
    time_frame: Decision = maps_to(SiennaReserveCol.TIME_FRAME, unit=UNIT_MINUTES)
    requirement: Decision = maps_to(SiennaReserveCol.REQUIREMENT, unit=UNIT_MW)
    sustained_time: Decision = maps_to(SiennaReserveCol.SUSTAINED_TIME, unit=UNIT_MINUTES)
    max_output_fraction: Decision = maps_to(SiennaReserveCol.MAX_OUTPUT_FRACTION)
    max_participation_factor: Decision = maps_to(SiennaReserveCol.MAX_PARTICIPATION_FACTOR)
    deployed_fraction: Decision = maps_to(SiennaReserveCol.DEPLOYED_FRACTION)


@dataclass(frozen=True)
class _OnlineMapping(_OfflineMapping):
    """One Sienna OnlineReserve, which also states the direction it moves output."""

    reserve_direction: Decision = maps_to(SiennaReserveCol.RESERVE_DIRECTION)


@dataclass(frozen=True)
class _ReserveSource:
    """One reserve as the sidecar record states it, with what the service needs beside it."""

    record: ReserveExtension
    type_code: Any
    batteries: list[str]
    peak: float | None


@dataclass(frozen=True)
class _Contributor:
    """One unit a reserve names, and the PLEXOS collection that names it."""

    name: str
    collection: str


_SERVICE_TYPES: tuple[SiennaComponent, ...] = (
    SiennaComponent.ONLINE_RESERVE,
    SiennaComponent.OFFLINE_RESERVE,
)


@dataclass
class TranslatedServices:
    """The rows each Sienna service type takes, the associations, and the requirement series."""

    rows: dict[SiennaComponent, list[dict[str, Any]]] = field(
        default_factory=lambda: {service_type: [] for service_type in _SERVICE_TYPES}
    )
    associations: list[dict[str, Any]] = field(default_factory=list)
    series: list[dict[str, Any]] = field(default_factory=list)

    @property
    def count(self) -> int:
        return sum(len(rows) for rows in self.rows.values())


_Reporters = dict[SiennaComponent, SiennaComponentReporter]


def map_reserve_services(state: State, recorder: ScopedRecorder) -> TranslatedServices:
    """Translate every reserve the sidecar carries into the Sienna service it names."""
    reporters = {
        service_type: SiennaComponentReporter(recorder, service_type)
        for service_type in _SERVICE_TYPES
    }
    translated = TranslatedServices()
    skipped: list[SkippedComponent] = []
    absent: set[str] = set()
    context = _build_context(state)
    for source in _build_reserve_sources(state):
        _add_service(translated, source, reporters, context, skipped, absent)
    warn_about_skips(skipped)
    warn_about_groups((_ABSENT_CONTRIBUTOR, name) for name in absent)
    return translated


@dataclass(frozen=True)
class _ServiceContext:
    """What every service in one run reads: the first free id, the units and the series timing."""

    first_id: int
    units: dict[str, list[TranslatedUnit]]
    ts_info_by_reserve: dict[str, TimeSeriesInfo]


def _build_context(state: State) -> _ServiceContext:
    return _ServiceContext(
        first_id=build_first_free_id(state),
        units=build_translated_units(state),
        ts_info_by_reserve=build_ts_info_by_component(
            state.source_time_series.get(_REQUIREMENT_KEY)
        ),
    )


# --- Reading the source ---


def _build_reserve_sources(state: State) -> list[_ReserveSource]:
    records = [
        record
        for record in state.destination_extensions.get(ExtensionKind.RESERVE, [])
        if isinstance(record, ReserveExtension)
    ]
    scalars = collapse_properties_by_object(
        state.source_topology[PlexosResolvedTable.PROPERTIES], PlexosClass.RESERVE
    )
    batteries = relate_children(
        state.source_topology[PlexosResolvedTable.MEMBERSHIPS],
        PlexosClass.RESERVE,
        PlexosCollection.BATTERIES,
    )
    peaks = _build_requirement_peaks(state)
    return [
        _ReserveSource(
            record=record,
            type_code=scalars.get(record.name, {}).get(PlexosProperty.RESERVE_TYPE),
            batteries=batteries.get(record.name, []),
            peak=peaks.get(record.name),
        )
        for record in records
    ]


def _build_requirement_peaks(state: State) -> dict[str, float]:
    """The highest requirement each varying reserve asks for. An aggregate, so safe to collect."""
    series = state.destination_extension_series.get(ExtensionKind.RESERVE)
    if series is None:
        return {}
    peaks = (
        series.group_by(CompanionSeriesCol.NAME)
        .agg(pl.col(ReserveCompanionCol.REQUIREMENT_MW).max())
        .collect()
    )
    return dict(
        zip(
            peaks[CompanionSeriesCol.NAME].to_list(),
            peaks[ReserveCompanionCol.REQUIREMENT_MW].to_list(),
            strict=True,
        )
    )


# --- Building one service ---


def _add_service(
    translated: TranslatedServices,
    source: _ReserveSource,
    reporters: _Reporters,
    context: _ServiceContext,
    skipped: list[SkippedComponent],
    absent: set[str],
) -> None:
    service_type = _choose_service_type(source.record)
    reporter = reporters[service_type]
    skip = _choose_kind_skip(source.record)
    requirement = None if skip else _derive_requirement(source)
    if requirement is None:
        _record_skip(reporter, skip or _build_no_requirement_skip(source.record), skipped)
        return
    service = _Service(service_type, context.first_id + translated.count)
    _add_service_row(translated, source, reporter, service, requirement)
    _add_requirement_series(translated, source, context.ts_info_by_reserve, service)
    _add_associations(
        translated, source, reporter, _ServiceUnits(service.id, context.units), absent
    )
    _record_sidecar_only(reporter, source.record)


@dataclass(frozen=True)
class _Service:
    """The Sienna type one reserve becomes, and the id it takes."""

    type: SiennaComponent
    id: int


class _ServiceUnits(NamedTuple):
    """One service's id, and the Sienna components of each unit able to join it, by name."""

    service_id: int
    units: dict[str, list[TranslatedUnit]]


def _choose_service_type(record: ReserveExtension) -> SiennaComponent:
    """A replacement reserve is one that units which are off can supply once they start."""
    if record.kind is ReserveKind.REPLACEMENT:
        return SiennaComponent.OFFLINE_RESERVE
    return SiennaComponent.ONLINE_RESERVE


def _record_skip(
    reporter: SiennaComponentReporter, skip: SkippedComponent, skipped: list[SkippedComponent]
) -> None:
    reporter.record_skipped(skip.source, skip.note)
    skipped.append(skip)


def _choose_kind_skip(record: ReserveExtension) -> SkippedComponent | None:
    """Why the kind of this reserve gives no service, or None where it can give one."""
    value = _build_reserve_value(record.name)
    if record.kind is ReserveKind.INERTIA:
        return SkippedComponent(value, _INERTIA_NOTE, _INERTIA)
    if not _has_direction(record):
        return SkippedComponent(value, _NO_DIRECTION_NOTE, _NO_DIRECTION)
    return None


def _build_no_requirement_skip(record: ReserveExtension) -> SkippedComponent:
    return SkippedComponent(
        _build_reserve_value(record.name), _NO_REQUIREMENT_NOTE, _NO_REQUIREMENT
    )


def _has_direction(record: ReserveExtension) -> bool:
    """An OfflineReserve states no direction, so only an online product needs one."""
    return record.kind is ReserveKind.REPLACEMENT or record.direction in _DIRECTIONS


def _add_service_row(
    translated: TranslatedServices,
    source: _ReserveSource,
    reporter: SiennaComponentReporter,
    service: _Service,
    requirement: Decision,
) -> None:
    mapping = _derive_mapping(source, service.type, requirement)
    reporter.record_mapping(source.record.name, mapping)
    row = destination_row(mapping, SiennaReserveCol.NAME, source.record.name)
    row[SiennaReserveCol.ID] = service.id
    reporter.record_id(source.record.name, SiennaReserveCol.ID, service.id, _ID_NOTE)
    translated.rows[service.type].append(row)


def _derive_mapping(
    source: _ReserveSource, service_type: SiennaComponent, requirement: Decision
) -> _OfflineMapping:
    offline = _derive_offline(source, requirement)
    if service_type is SiennaComponent.OFFLINE_RESERVE:
        return offline
    return _derive_online(source, offline)


def _derive_offline(source: _ReserveSource, requirement: Decision) -> _OfflineMapping:
    return _OfflineMapping(
        name=source.record.name,
        available=_derive_available(source.record),
        time_frame=Decision.default(DEFAULT_TIME_FRAME_MINUTES, _TIME_FRAME_NOTE),
        requirement=requirement,
        sustained_time=_derive_sustained_time(source.record),
        max_output_fraction=Decision.default(FULL_OUTPUT_FRACTION, _OUTPUT_FRACTION_NOTE),
        max_participation_factor=Decision.default(FULL_PARTICIPATION, _PARTICIPATION_NOTE),
        deployed_fraction=Decision.default(NOTHING_DEPLOYED, _DEPLOYED_NOTE),
    )


def _derive_online(source: _ReserveSource, offline: _OfflineMapping) -> _OnlineMapping:
    return _OnlineMapping(
        **{one.name: getattr(offline, one.name) for one in fields(offline)},
        reserve_direction=Decision.derived(
            _DIRECTIONS[source.record.direction].value,
            [
                _build_reserve_value(
                    source.record.name, PlexosProperty.RESERVE_TYPE, source.type_code
                )
            ],
            _DIRECTION_DERIVATION,
        ),
    )


def _derive_requirement(source: _ReserveSource) -> Decision | None:
    """The requirement in MW: the stated value, or the peak of a varying one."""
    record = source.record
    if record.requirement_mw is not None and record.requirement_mw > 0:
        stated = _build_reserve_value(
            record.name, PlexosProperty.MIN_PROVISION, record.requirement_mw, UNIT_MW
        )
        return Decision.derived(record.requirement_mw, [stated], _REQUIREMENT_DERIVATION)
    if record.requirement_series is not None and source.peak is not None and source.peak > 0:
        series = _build_reserve_value(
            record.name, PlexosProperty.MIN_PROVISION, record.requirement_series, UNIT_MW
        )
        return Decision.derived(source.peak, [series], _PEAK_DERIVATION)
    return None


def _derive_available(record: ReserveExtension) -> Decision:
    if record.is_available is None:
        return Decision.default(True, _AVAILABLE_NOTE)
    stated = _build_reserve_value(record.name, PlexosProperty.IS_ENABLED, record.is_available)
    return Decision.derived(record.is_available, [stated], _AVAILABLE_DERIVATION)


def _derive_sustained_time(record: ReserveExtension) -> Decision:
    seconds = record.sustained_time_seconds
    if seconds is None:
        return Decision.default(DEFAULT_SUSTAINED_TIME_MINUTES, _SUSTAINED_NOTE)
    stated = _build_reserve_value(record.name, PlexosProperty.DURATION, seconds, UNIT_SECONDS)
    return Decision.derived(seconds / SECONDS_PER_MINUTE, [stated], _SUSTAINED_DERIVATION)


def _add_requirement_series(
    translated: TranslatedServices,
    source: _ReserveSource,
    ts_info_by_reserve: dict[str, TimeSeriesInfo],
    service: _Service,
) -> None:
    """A varying requirement is stored as its shape over the peak the service states.

    Each series takes the start, step and length of its own reserve, since two data files can
    start on different days.
    """
    if source.record.requirement_series is None or source.peak is None:
        return
    translated.series.append(
        ts_association_row(
            owner_type=service.type,
            owner_id=service.id,
            component_name=source.record.name,
            series_name=SiennaReserveCol.REQUIREMENT,
            ts_info=ts_info_by_reserve.get(source.record.name, _NO_SERIES),
            source_table=_REQUIREMENT_KEY[0],
            source_attribute=_REQUIREMENT_KEY[1],
            scaling_factor=source.peak,
        )
    )


def _add_associations(
    translated: TranslatedServices,
    source: _ReserveSource,
    reporter: SiennaComponentReporter,
    service: _ServiceUnits,
    absent: set[str],
) -> None:
    """One association for each named unit the system holds; the rest are recorded."""
    for contributor in _list_contributors(source):
        units = service.units.get(contributor.name)
        if units is None:
            _record_absent(reporter, source.record.name, contributor)
            absent.add(contributor.name)
            continue
        for unit in units:
            translated.associations.append(
                {
                    SiennaServiceAssociationCol.SERVICE_ID: service.service_id,
                    SiennaServiceAssociationCol.ENTITY_ID: unit.sienna_id,
                }
            )
        _record_association(reporter, source.record.name, contributor)


def _list_contributors(source: _ReserveSource) -> list[_Contributor]:
    return [
        *(
            _Contributor(name, PlexosCollection.GENERATORS)
            for name in source.record.contributing_generators
        ),
        *(_Contributor(name, PlexosCollection.BATTERIES) for name in source.batteries),
    ]


# --- Reporting ---


def _build_reserve_value(
    name: str, attribute: str | None = None, value: Any = None, unit: str | None = None
) -> SourceValue:
    return SourceValue(PlexosClass.RESERVE, name, attribute, value, unit)


def _record_association(
    reporter: SiennaComponentReporter, reserve: str, contributor: _Contributor
) -> None:
    member = _build_reserve_value(reserve, contributor.collection, contributor.name)
    decision = Decision.derived(contributor.name, [member], _ASSOCIATION_DERIVATION)
    reporter.record(reserve, _ASSOCIATIONS_COLUMNS, decision)


def _record_absent(
    reporter: SiennaComponentReporter, reserve: str, contributor: _Contributor
) -> None:
    note = f"the Sienna system holds no unit named {contributor.name}, so it joins no service"
    reporter.record_dropped(
        _build_reserve_value(reserve, contributor.collection, contributor.name), note
    )


def _record_sidecar_only(reporter: SiennaComponentReporter, record: ReserveExtension) -> None:
    """The values the service has no field for, which only the sidecar keeps."""
    if record.shortage_price is not None:
        shortage = _build_reserve_value(
            record.name, PlexosProperty.VALUE_OF_RESERVE_SHORTAGE, record.shortage_price
        )
        reporter.record_dropped(shortage, _SHORTAGE_NOTE)
    if record.is_mutually_exclusive is not None:
        exclusive = _build_reserve_value(
            record.name, PlexosProperty.MUTUALLY_EXCLUSIVE, record.is_mutually_exclusive
        )
        reporter.record_dropped(exclusive, _EXCLUSIVE_NOTE)
