"""PLEXOS Storage and Waterway -> Sienna HydroReservoir.

A reservoir-hydro turbine draws on its head Storage. That Storage becomes a HydroReservoir,
which names the turbine among its ``downstream_turbines``. A Waterway carries water out of
one Storage and into the next, so the lower reservoir names the upper one among its
``upstream_reservoirs``.

PLEXOS states a reservoir in energy or in water. Sienna states both, and ``level_data_type``
says which: ENERGY levels are MWh with an inflow in MW, USABLE_VOLUME levels are cubic
metres with an inflow in cubic metres per second.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, NamedTuple

import polars as pl

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import (
    UNIT_CUBIC_METRES,
    UNIT_CUBIC_METRES_PER_SECOND,
    UNIT_METRES,
    UNIT_MW,
    UNIT_MWH,
    StagedTimeSeriesCol,
)
from interop.plugins.shared.plexos_constants import (
    PlexosClass,
    PlexosCollection,
    PlexosProperty,
    PlexosResolvedTable,
)
from interop.plugins.shared.plexos_pypsa_translations._shared import (
    collapse_properties_by_object,
    collapse_units_by_object,
    read_file_backed_properties,
)
from interop.plugins.shared.plexos_pypsa_translations._storage_shared import Cascade
from interop.plugins.shared.plexos_pypsa_translations.decisions import (
    Decision,
    MappedColumns,
    SkipGroup,
    SourceValue,
    warn_about_groups,
)
from interop.plugins.shared.plexos_sienna_translations._shared import SiennaComponentReporter
from interop.plugins.shared.plexos_units import choose_canonical_unit, conversion_factor
from interop.plugins.shared.sienna_constants import (
    TIME_SERIES_ASSOCIATION_SCHEMA,
    InfraStoreSeriesLabel,
    SiennaComponent,
    SiennaCostType,
    SiennaFunctionType,
    SiennaHydroReservoirCol,
    SiennaLevelDataType,
    SiennaSeriesName,
    SiennaStructField,
    SiennaTimeSeriesAssociationCol,
    SiennaUnitSystem,
)
from interop.plugins.shared.sienna_time_series import (
    SeriesLabels,
    TimeSeriesInfo,
    build_ts_info,
    build_ts_info_by_component,
    ts_association_row,
)

ReservoirCol = SiennaHydroReservoirCol

_VOLUME_PROPERTIES = (
    PlexosProperty.MAX_VOLUME,
    PlexosProperty.MIN_VOLUME,
    PlexosProperty.INITIAL_VOLUME,
)
_NO_INFLOW = 0.0
_EMPTY = 0.0
_NO_OUTFLOW = 0.0
_SEA_LEVEL = 0.0

_AVAILABLE_NOTE = "PLEXOS states no reservoir availability; every reservoir is available"
_NAME_DERIVATION = "the Storage name"
_LEVEL_TYPE_DERIVATION = "the unit the Storage states its volumes in"
_NO_MIN_VOLUME_NOTE = "the Storage states no Min Volume, so the reservoir can empty"
_NO_INITIAL_VOLUME_NOTE = (
    "the Storage states no Initial Volume, so the reservoir starts at its floor"
)
_CLAMPED_DERIVATION = ", held between the Min Volume and the Max Volume"
_OUTFLOW_NOTE = "PLEXOS states no fixed outflow; the turbines draw the water the reservoir releases"
_ELEVATION_NOTE = "the Storage states no intake elevation"
_HEAD_NOTE = (
    "the Storage states no relation between head and volume; level_data_type says what the "
    "level measures"
)
_COST_NOTE = "the Storage states no level or spillage cost that Sienna reads"
_DOWNSTREAM_DERIVATION = "the HydroTurbines that name this Storage as their Head Storage"
_NO_UPSTREAM_TURBINE_NOTE = "no HydroTurbine names this Storage as its Tail Storage"
_UPSTREAM_TURBINE_DERIVATION = "the HydroTurbines that name this Storage as their Tail Storage"
_UPSTREAM_DERIVATION = "the Storage From of each Waterway whose Storage To is this Storage"
_NO_UPSTREAM_NOTE = "no Waterway carries water into this Storage from a reservoir the system holds"
_NO_INFLOW_NOTE = "the Storage states no Natural Inflow, so the reservoir does not refill"
_PROFILE_DERIVATION = "the peak of the Natural Inflow profile, which a time series follows"
_INFLOW_UNIT_NOTE = (
    "the Storage states its Natural Inflow in a unit that does not match its volumes, so the "
    "reservoir does not refill"
)
_UNKNOWN_UNIT_NOTE = (
    "the Storage names a volume unit that converts to neither MWh nor cubic metres, so the "
    "reservoir has no size it can state and is left out"
)
_FILE_BACKED_NOTE = (
    "Max Volume comes from a data file rather than a value, so the reservoir has no size it "
    "can state and is left out"
)
_NO_MAX_VOLUME_NOTE = (
    "the Storage states no Max Volume, so the reservoir has no size it can state and is left out"
)
_LOOSE_WATERWAY_NOTE = (
    "this Waterway joins no two reservoirs that the system holds, so no reservoir names it"
)
_STORAGE_UNIT_WATERWAY_NOTE = (
    "this Waterway joins a reservoir to a Storage that a pumped-storage unit holds, and the "
    "EnergyReservoirStorage of that unit holds its water, so no reservoir names it"
)
_ROUTE_NOTE = (
    "Sienna states no route between two reservoirs, so the Waterway's {property} has no field"
)

_UNKNOWN_UNIT_GROUP = SkipGroup(
    "Storage(s)",
    "state a volume in a unit that converts to neither MWh nor cubic metres",
    "so each reservoir is left out",
)
_FILE_BACKED_GROUP = SkipGroup(
    "Storage(s)", "read Max Volume from a data file", "so each reservoir is left out"
)
_NO_MAX_VOLUME_GROUP = SkipGroup(
    "Storage(s)", "state no Max Volume", "so each reservoir is left out"
)
_LOOSE_WATERWAY_GROUP = SkipGroup(
    "Waterway(s)", "join no two reservoirs that the system holds", "so no reservoir names them"
)
_STORAGE_UNIT_WATERWAY_GROUP = SkipGroup(
    "Waterway(s)",
    "join a reservoir to a Storage that a pumped-storage unit holds",
    "so no reservoir names them",
)


@dataclass(frozen=True)
class _LevelScale:
    """What one reservoir's levels measure, the units its levels and its inflow take, and the
    labels its stored inflow series takes.
    """

    level_data_type: SiennaLevelDataType
    volume_unit: str
    flow_unit: str
    inflow_labels: SeriesLabels


_ENERGY = _LevelScale(
    SiennaLevelDataType.ENERGY,
    UNIT_MWH,
    UNIT_MW,
    SeriesLabels(InfraStoreSeriesLabel.UNITS_POWER, InfraStoreSeriesLabel.QUANTITY_INFLOW),
)
_WATER = _LevelScale(
    SiennaLevelDataType.USABLE_VOLUME,
    UNIT_CUBIC_METRES,
    UNIT_CUBIC_METRES_PER_SECOND,
    SeriesLabels(InfraStoreSeriesLabel.UNITS_FLOW, InfraStoreSeriesLabel.QUANTITY_INFLOW),
)


@dataclass(frozen=True)
class _StorageReading:
    """What one PLEXOS Storage states, with the unit of each value."""

    name: str
    values: dict[str, float]
    units: dict[str, str | None]
    file_backed: list[str]
    inflow_peak: float | None


@dataclass(frozen=True)
class _Reservoir:
    """One Storage the system holds as a HydroReservoir: its id, its reading and its scale."""

    reservoir_id: int
    reading: _StorageReading
    scale: _LevelScale


@dataclass(frozen=True)
class _Field:
    """One destination value, the column it fills, and the unit it is stated in."""

    column: str
    decision: Decision
    unit: str | None = None


@dataclass
class TranslatedReservoirs:
    """The HydroReservoir rows, and the series their inflow follows."""

    rows: list[dict[str, Any]] = field(default_factory=list)
    associations: pl.DataFrame = field(
        default_factory=lambda: pl.DataFrame(schema=TIME_SERIES_ASSOCIATION_SCHEMA)
    )


class _Built(NamedTuple):
    """The Storages the system holds as reservoirs, and each Storage it leaves out, and why."""

    reservoirs: dict[str, _Reservoir]
    skipped: list[tuple[_SkipReason, str]]


def map_reservoirs(
    state: State, recorder: ScopedRecorder, cascade: Cascade, first_id: int
) -> TranslatedReservoirs:
    """One HydroReservoir for each Storage of the cascade whose size the system can state."""
    reporter = SiennaComponentReporter(recorder, SiennaComponent.HYDRO_RESERVOIR)
    built = _build_reservoirs(_read_storages(state, cascade.storages), first_id)
    _report_skipped_storages(built.skipped, reporter)
    reservoirs = built.reservoirs
    rows = [_build_row(one, reservoirs, cascade, reporter) for one in reservoirs.values()]
    _record_waterways(state, cascade, reservoirs, reporter)
    return TranslatedReservoirs(rows, _build_associations(state, reservoirs))


# --- the Storages ----------------------------------------------------------------


def _read_storages(state: State, names: list[str]) -> list[_StorageReading]:
    properties = state.source_topology[PlexosResolvedTable.PROPERTIES]
    values = collapse_properties_by_object(properties, PlexosClass.STORAGE)
    units = collapse_units_by_object(properties, PlexosClass.STORAGE)
    file_backed = read_file_backed_properties(properties, PlexosClass.STORAGE)
    peaks = _read_inflow_peaks(state)
    return [
        _StorageReading(
            name,
            values.get(name, {}),
            units.get(name, {}),
            file_backed.get(name, []),
            peaks.get(name),
        )
        for name in names
    ]


def _read_inflow_peaks(state: State) -> dict[str, float]:
    """The highest value of each Storage's Natural Inflow profile, an aggregate safe to collect."""
    frame = state.source_time_series.get((PlexosClass.STORAGE, PlexosProperty.NATURAL_INFLOW))
    if frame is None:
        return {}
    peaks = (
        frame.group_by(StagedTimeSeriesCol.COMPONENT)
        .agg(pl.col(StagedTimeSeriesCol.VALUE).max())
        .collect()
    )
    return dict(peaks.iter_rows())


def _build_reservoirs(readings: list[_StorageReading], first_id: int) -> _Built:
    """The Storages whose size the system can state, each with its id and its scale."""
    chosen: dict[str, _Reservoir] = {}
    skipped: list[tuple[_SkipReason, str]] = []
    for reading in readings:
        scale = _choose_scale(reading)
        reason = _find_skip_reason(reading, scale)
        if reason is None and scale is not None:
            chosen[reading.name] = _Reservoir(first_id + len(chosen), reading, scale)
        else:
            skipped.append((reason or _UNKNOWN_UNIT_REASON, reading.name))
    return _Built(chosen, skipped)


def _report_skipped_storages(
    skipped: list[tuple[_SkipReason, str]], reporter: SiennaComponentReporter
) -> None:
    for reason, name in skipped:
        reporter.record_skipped(SourceValue(PlexosClass.STORAGE, name, None, None), reason.note)
    warn_about_groups((reason.group, name) for reason, name in skipped)


def has_energy_volumes(values: Mapping[str, float], units: Mapping[str, str | None]) -> bool:
    """Whether every volume a Storage states is energy, so its reservoir levels are MWh."""
    stated = [units.get(name) for name in _VOLUME_PROPERTIES if name in values]
    return all(unit is None or conversion_factor(unit, UNIT_MWH) is not None for unit in stated)


def _choose_scale(reading: _StorageReading) -> _LevelScale | None:
    """ENERGY where every stated volume is energy, USABLE_VOLUME where every one is water."""
    if has_energy_volumes(reading.values, reading.units):
        return _ENERGY
    stated = [reading.units.get(name) for name in _VOLUME_PROPERTIES if name in reading.values]
    if all(unit is not None and conversion_factor(unit, UNIT_CUBIC_METRES) for unit in stated):
        return _WATER
    return None


class _SkipReason(NamedTuple):
    """Why a Storage is left out: the group its warning counts it in, and its note."""

    group: SkipGroup
    note: str


_UNKNOWN_UNIT_REASON = _SkipReason(_UNKNOWN_UNIT_GROUP, _UNKNOWN_UNIT_NOTE)
_FILE_BACKED_REASON = _SkipReason(_FILE_BACKED_GROUP, _FILE_BACKED_NOTE)
_NO_MAX_VOLUME_REASON = _SkipReason(_NO_MAX_VOLUME_GROUP, _NO_MAX_VOLUME_NOTE)
_LOOSE_WATERWAY_REASON = _SkipReason(_LOOSE_WATERWAY_GROUP, _LOOSE_WATERWAY_NOTE)
_STORAGE_UNIT_WATERWAY_REASON = _SkipReason(
    _STORAGE_UNIT_WATERWAY_GROUP, _STORAGE_UNIT_WATERWAY_NOTE
)


def _find_skip_reason(reading: _StorageReading, scale: _LevelScale | None) -> _SkipReason | None:
    if scale is None:
        return _UNKNOWN_UNIT_REASON
    if PlexosProperty.MAX_VOLUME in reading.file_backed:
        return _FILE_BACKED_REASON
    if PlexosProperty.MAX_VOLUME not in reading.values:
        return _NO_MAX_VOLUME_REASON
    return None


# --- one reservoir ---------------------------------------------------------------


def _build_row(
    reservoir: _Reservoir,
    reservoirs: dict[str, _Reservoir],
    cascade: Cascade,
    reporter: SiennaComponentReporter,
) -> dict[str, Any]:
    name = reservoir.reading.name
    reporter.record_id(name, ReservoirCol.ID, reservoir.reservoir_id)
    fields = [
        *_derive_identity(reservoir),
        *_derive_levels(reservoir),
        _derive_inflow(reservoir),
        *_derive_defaults(),
        *_derive_links(reservoir, reservoirs, cascade),
    ]
    row: dict[str, Any] = {ReservoirCol.ID: reservoir.reservoir_id}
    for one in fields:
        reporter.record(name, MappedColumns((one.column,), one.unit), one.decision)
        _set_nested(row, one.column, one.decision.value)
    return row


def _derive_identity(reservoir: _Reservoir) -> list[_Field]:
    reading = reservoir.reading
    stated = reading.units.get(PlexosProperty.MAX_VOLUME) or reservoir.scale.volume_unit
    unit_source = SourceValue(PlexosClass.STORAGE, reading.name, PlexosProperty.MAX_VOLUME, stated)
    return [
        _Field(
            ReservoirCol.NAME,
            Decision.derived(reading.name, [_build_storage_source(reading.name)], _NAME_DERIVATION),
        ),
        _Field(ReservoirCol.AVAILABLE, Decision.default(True, _AVAILABLE_NOTE)),
        _Field(
            ReservoirCol.LEVEL_DATA_TYPE,
            Decision.derived(
                str(reservoir.scale.level_data_type), [unit_source], _LEVEL_TYPE_DERIVATION
            ),
        ),
    ]


def _derive_levels(reservoir: _Reservoir) -> list[_Field]:
    """The floor, the ceiling and the starting level, each in the reservoir's own unit."""
    unit = reservoir.scale.volume_unit
    ceiling = _derive_volume(reservoir, PlexosProperty.MAX_VOLUME) or Decision.default(
        _EMPTY, _NO_MAX_VOLUME_NOTE
    )
    floor = _derive_volume(reservoir, PlexosProperty.MIN_VOLUME) or Decision.default(
        _EMPTY, _NO_MIN_VOLUME_NOTE
    )
    start = _derive_start_level(
        _derive_volume(reservoir, PlexosProperty.INITIAL_VOLUME), floor, ceiling
    )
    return [
        _Field(f"{ReservoirCol.STORAGE_LEVEL_LIMITS}.{SiennaStructField.MAX}", ceiling, unit),
        _Field(f"{ReservoirCol.STORAGE_LEVEL_LIMITS}.{SiennaStructField.MIN}", floor, unit),
        _Field(ReservoirCol.INITIAL_LEVEL, start, unit),
    ]


def _derive_volume(reservoir: _Reservoir, property_name: str) -> Decision | None:
    """One volume property in the reservoir's unit, or None where the Storage states none that
    converts into it.
    """
    reading = reservoir.reading
    value = reading.values.get(property_name)
    wanted = reservoir.scale.volume_unit
    staged = _find_staged_unit(reading, property_name)
    factor = _find_factor(staged, wanted)
    if value is None or factor is None:
        return None
    source = SourceValue(PlexosClass.STORAGE, reading.name, property_name, value, staged or wanted)
    return Decision.derived(
        value * factor, [source], _build_explanation(property_name, factor, f"{staged} to {wanted}")
    )


def _find_staged_unit(reading: _StorageReading, property_name: str) -> str | None:
    """The unit a stated value staged in, or None where the model states no unit.

    Staging converts a value into the canonical unit of its property where the stated unit
    converts into it, and leaves every other value as the model wrote it.
    """
    stated = reading.units.get(property_name)
    canonical = choose_canonical_unit(PlexosCollection.STORAGES, property_name)
    if stated is None or canonical is None or conversion_factor(stated, canonical) is None:
        return stated
    return canonical


def _find_factor(staged: str | None, wanted: str) -> float | None:
    """What one staged unit is worth in ``wanted``, or None where it does not convert into it.

    A model that names no unit is taken at its word.
    """
    if staged is None:
        return 1.0
    return conversion_factor(staged, wanted)


def _build_explanation(label: str, factor: float, conversion: str) -> str:
    if factor == 1.0:
        return label
    return f"{label} x {factor:g} ({conversion})"


def _derive_start_level(start: Decision | None, floor: Decision, ceiling: Decision) -> Decision:
    """Where the reservoir starts, held inside its limits, or its floor where nothing says."""
    if start is None:
        return Decision.default(floor.value, _NO_INITIAL_VOLUME_NOTE)
    held = min(max(start.value, floor.value), ceiling.value)
    if held == start.value:
        return start
    return Decision.derived(held, list(start.sources), f"{start.explanation}{_CLAMPED_DERIVATION}")


def _derive_inflow(reservoir: _Reservoir) -> _Field:
    """What refills the reservoir, in its flow unit, or nothing where the units disagree."""
    reading = reservoir.reading
    unit = reservoir.scale.flow_unit
    inflow = _find_inflow(reservoir)
    if inflow is None:
        return _Field(ReservoirCol.INFLOW, Decision.default(_NO_INFLOW, _NO_INFLOW_NOTE), unit)
    if inflow.factor is None:
        return _Field(ReservoirCol.INFLOW, Decision.default(_NO_INFLOW, _INFLOW_UNIT_NOTE), unit)
    source = _build_inflow_source(reading, inflow.value, inflow.staged or unit)
    explanation = _build_explanation(inflow.label, inflow.factor, f"{inflow.staged} to {unit}")
    return _Field(
        ReservoirCol.INFLOW,
        Decision.derived(inflow.value * inflow.factor, [source], explanation),
        unit,
    )


class _Inflow(NamedTuple):
    """The Natural Inflow a Storage states, where it comes from, the unit it staged in, and its
    factor to the flow unit.

    The factor is None where the staged unit does not match the reservoir.
    """

    value: float
    label: str
    staged: str | None
    factor: float | None


def _find_inflow(reservoir: _Reservoir) -> _Inflow | None:
    """The peak of the Natural Inflow profile, else the static Natural Inflow, else None.

    Staging converts no profile, so a profile stays in the unit the model states.
    """
    reading = reservoir.reading
    wanted = reservoir.scale.flow_unit
    if reading.inflow_peak is not None:
        stated = reading.units.get(PlexosProperty.NATURAL_INFLOW)
        return _Inflow(
            reading.inflow_peak, _PROFILE_DERIVATION, stated, _find_factor(stated, wanted)
        )
    value = reading.values.get(PlexosProperty.NATURAL_INFLOW)
    if value is None:
        return None
    staged = _find_staged_unit(reading, PlexosProperty.NATURAL_INFLOW)
    return _Inflow(value, PlexosProperty.NATURAL_INFLOW, staged, _find_factor(staged, wanted))


def _build_inflow_source(reading: _StorageReading, value: float, unit: str) -> SourceValue:
    return SourceValue(
        PlexosClass.STORAGE, reading.name, PlexosProperty.NATURAL_INFLOW, value, unit
    )


def _derive_defaults() -> list[_Field]:
    return [
        _Field(ReservoirCol.OUTFLOW, Decision.default(_NO_OUTFLOW, _OUTFLOW_NOTE)),
        _Field(
            ReservoirCol.INTAKE_ELEVATION,
            Decision.default(_SEA_LEVEL, _ELEVATION_NOTE),
            UNIT_METRES,
        ),
        _Field(
            ReservoirCol.HEAD_TO_VOLUME_FACTOR,
            Decision.default(
                {
                    SiennaStructField.FUNCTION_TYPE: str(SiennaFunctionType.LINEAR),
                    SiennaStructField.PROPORTIONAL_TERM: 0.0,
                    SiennaStructField.CONSTANT_TERM: 0.0,
                },
                _HEAD_NOTE,
            ),
        ),
        _Field(
            ReservoirCol.OPERATION_COST,
            Decision.default(
                {
                    SiennaStructField.COST_TYPE: str(SiennaCostType.HYDRO_RES),
                    SiennaStructField.LEVEL_SHORTAGE_COST: 0.0,
                    SiennaStructField.LEVEL_SURPLUS_COST: 0.0,
                    SiennaStructField.SPILLAGE_COST: 0.0,
                },
                _COST_NOTE,
            ),
        ),
    ]


def _derive_links(
    reservoir: _Reservoir, reservoirs: dict[str, _Reservoir], cascade: Cascade
) -> list[_Field]:
    name = reservoir.reading.name
    turbines = cascade.turbines_by_storage.get(name, [])
    head_sources = [
        SourceValue(PlexosClass.GENERATOR, turbine.name, PlexosCollection.HEAD_STORAGE, name)
        for turbine in turbines
    ]
    downstream = [turbine.turbine_id for turbine in turbines]
    return [
        _Field(
            ReservoirCol.DOWNSTREAM_TURBINES,
            Decision.derived(downstream, head_sources, _DOWNSTREAM_DERIVATION),
        ),
        _Field(ReservoirCol.UPSTREAM_TURBINES, _derive_upstream_turbines(name, cascade)),
        _Field(ReservoirCol.UPSTREAM_RESERVOIRS, _derive_upstream(name, reservoirs, cascade)),
    ]


def _derive_upstream_turbines(name: str, cascade: Cascade) -> Decision:
    """The turbines whose tail is this Storage, which release their water into it."""
    turbines = cascade.tail_turbines_by_storage.get(name, [])
    if not turbines:
        return Decision.default([], _NO_UPSTREAM_TURBINE_NOTE)
    sources = [
        SourceValue(PlexosClass.GENERATOR, turbine.name, PlexosCollection.TAIL_STORAGE, name)
        for turbine in turbines
    ]
    return Decision.derived(
        [turbine.turbine_id for turbine in turbines], sources, _UPSTREAM_TURBINE_DERIVATION
    )


def _derive_upstream(name: str, reservoirs: dict[str, _Reservoir], cascade: Cascade) -> Decision:
    routes = [
        (waterway, route.leaves)
        for waterway, route in sorted(cascade.routes.items())
        if route.reaches == name and route.leaves in reservoirs
    ]
    if not routes:
        return Decision.default([], _NO_UPSTREAM_NOTE)
    sources = [
        SourceValue(PlexosClass.WATERWAY, waterway, PlexosCollection.STORAGE_FROM, leaves)
        for waterway, leaves in routes
    ]
    upstream = [reservoirs[leaves].reservoir_id for _, leaves in routes if leaves is not None]
    return Decision.derived(upstream, sources, _UPSTREAM_DERIVATION)


def _build_storage_source(name: str) -> SourceValue:
    return SourceValue(PlexosClass.STORAGE, name, None, name)


def _set_nested(row: dict[str, Any], column: str, value: Any) -> None:
    """Set a value at a dotted path, so ``a.b`` fills the ``b`` field of the struct ``a``."""
    head, _, rest = column.partition(".")
    if not rest:
        row[head] = value
        return
    row.setdefault(head, {})[rest] = value


# --- the Waterways ---------------------------------------------------------------


def _record_waterways(
    state: State,
    cascade: Cascade,
    reservoirs: dict[str, _Reservoir],
    reporter: SiennaComponentReporter,
) -> None:
    """A Waterway outside the cascade, and every value a Waterway states, which Sienna has no
    field for."""
    to_storage_units = cascade.list_routes_to_storage_units()
    loose = [
        waterway
        for waterway, route in sorted(cascade.routes.items())
        if (route.leaves not in reservoirs or route.reaches not in reservoirs)
        and waterway not in to_storage_units
    ]
    groups = [
        *_record_dropped_waterways(to_storage_units, _STORAGE_UNIT_WATERWAY_REASON, reporter),
        *_record_dropped_waterways(loose, _LOOSE_WATERWAY_REASON, reporter),
    ]
    warn_about_groups(groups)
    _record_route_values(state, reporter)


def _record_dropped_waterways(
    waterways: list[str], reason: _SkipReason, reporter: SiennaComponentReporter
) -> list[tuple[SkipGroup, str]]:
    for waterway in waterways:
        reporter.record_dropped(
            SourceValue(PlexosClass.WATERWAY, waterway, None, None), reason.note
        )
    return [(reason.group, waterway) for waterway in waterways]


def _record_route_values(state: State, reporter: SiennaComponentReporter) -> None:
    properties = state.source_topology[PlexosResolvedTable.PROPERTIES]
    stated = collapse_properties_by_object(properties, PlexosClass.WATERWAY)
    groups: list[tuple[SkipGroup, str]] = []
    for waterway, values in sorted(stated.items()):
        for property_name, value in sorted(values.items()):
            note = _ROUTE_NOTE.format(property=property_name)
            reporter.record_dropped(
                SourceValue(PlexosClass.WATERWAY, waterway, property_name, value), note
            )
            groups.append((_build_route_group(property_name), waterway))
    warn_about_groups(groups)


def _build_route_group(property_name: str) -> SkipGroup:
    return SkipGroup(
        "Waterway(s)", f"state a {property_name}", "which Sienna states no route to hold"
    )


# --- the inflow series -----------------------------------------------------------


def _build_associations(state: State, reservoirs: dict[str, _Reservoir]) -> pl.DataFrame:
    """One series row for each reservoir whose Natural Inflow is a profile, in its own unit."""
    frame = state.source_time_series.get((PlexosClass.STORAGE, PlexosProperty.NATURAL_INFLOW))
    profiled = [
        _ProfiledReservoir(one, inflow.factor)
        for one in reservoirs.values()
        if one.reading.inflow_peak is not None
        and (inflow := _find_inflow(one)) is not None
        and inflow.factor is not None
    ]
    if frame is None or not profiled:
        return pl.DataFrame(schema=TIME_SERIES_ASSOCIATION_SCHEMA)
    info_by_name = build_ts_info_by_component(frame)
    no_series = build_ts_info(0, None, None)
    rows = [
        _build_association_row(one, info_by_name.get(one.reservoir.reading.name, no_series))
        for one in profiled
    ]
    return pl.DataFrame(rows, schema=TIME_SERIES_ASSOCIATION_SCHEMA)


class _ProfiledReservoir(NamedTuple):
    """A reservoir whose inflow is a profile, and the factor that brings it into the flow unit."""

    reservoir: _Reservoir
    factor: float


def _build_association_row(profiled: _ProfiledReservoir, info: TimeSeriesInfo) -> dict[str, Any]:
    """The inflow series of one reservoir, stored as the model states it, in its flow unit."""
    reservoir = profiled.reservoir
    labels = reservoir.scale.inflow_labels
    col = SiennaTimeSeriesAssociationCol
    return {
        **ts_association_row(
            owner_type=SiennaComponent.HYDRO_RESERVOIR,
            owner_id=reservoir.reservoir_id,
            component_name=reservoir.reading.name,
            series_name=SiennaSeriesName.INFLOW,
            ts_info=info,
            source_table=PlexosClass.STORAGE,
            source_attribute=PlexosProperty.NATURAL_INFLOW,
            # The sink divides each value by the scaling factor.
            scaling_factor=1.0 / profiled.factor,
        ),
        col.UNIT_SYSTEM: SiennaUnitSystem.NATURAL_UNITS,
        col.UNITS: labels.units,
        col.QUANTITY_KIND: labels.quantity_kind,
    }
