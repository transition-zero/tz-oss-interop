"""PLEXOS Generator -> Sienna ThermalStandard or RenewableDispatch.

A generator takes the name of its Fuel where it burns one, and its PLEXOS category where it
does not. The user's mappings file says what that carrier becomes: a thermal target names a
fuel and a prime mover, a renewable target names a prime mover alone.

The PLEXOS reading is shared with the PLEXOS to PyPSA hop, because the model says the same
thing whichever framework reads it. What this module states is the Sienna side: the limits,
the cost curve, the commitment and the sidecar record.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import Any

import polars as pl

from interop.core.extensions import ExtensionKind, GeneratorExtension, companion_filename
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import (
    UNIT_DOLLARS,
    UNIT_DOLLARS_PER_MW,
    UNIT_DOLLARS_PER_MW_YEAR,
    UNIT_DOLLARS_PER_MWH,
    UNIT_HOURS,
    UNIT_MVA,
    UNIT_MW,
    UNIT_MW_PER_MINUTE,
    UNIT_YEARS,
    Framework,
)
from interop.plugins.shared.plexos_constants import (
    PlexosClass,
    PlexosCollection,
    PlexosObjectCol,
    PlexosProperty,
)
from interop.plugins.shared.plexos_pypsa_translations._expansion import (
    find_blocked_candidate,
    record_expansion_notes,
    warn_about_dropped_builds,
)
from interop.plugins.shared.plexos_pypsa_translations._generator_decisions import (
    decide_generator,
    record_generator_source_notes,
)
from interop.plugins.shared.plexos_pypsa_translations._generator_derivation import (
    GeneratorMapping,
    SourceGenerator,
    StartPricing,
    derive_generator,
    has_infeasible_dispatch_range,
    read_source,
)
from interop.plugins.shared.plexos_pypsa_translations._generator_lookups import (
    Lookups,
    build_lookups,
)
from interop.plugins.shared.plexos_pypsa_translations._generators import (
    ProfileOwner,
    report_profile_not_staged,
)
from interop.plugins.shared.plexos_pypsa_translations._lifespan import derive_lifespan
from interop.plugins.shared.plexos_pypsa_translations._storage_turbines import (
    storage_turbine_names,
)
from interop.plugins.shared.plexos_pypsa_translations.constants import (
    MARGINAL_COST_CARBON_TERM,
    START_UP_COST_FUEL_TERM,
)
from interop.plugins.shared.plexos_pypsa_translations.decisions import (
    Decision,
    DecisionKind,
    MappedColumns,
    SkippedComponent,
    SourceValue,
    declares,
    destination_row,
    maps_to,
    warn_about_skips,
)
from interop.plugins.shared.plexos_sienna_translations._availability import (
    AVAILABILITY_SERIES,
    AvailabilityInputs,
    stage_availability,
)
from interop.plugins.shared.plexos_sienna_translations._carriers import (
    CarrierTarget,
    CarrierTargets,
)
from interop.plugins.shared.plexos_sienna_translations._fuel_prices import (
    build_fuel_price_series,
)
from interop.plugins.shared.plexos_sienna_translations._shared import SiennaComponentReporter
from interop.plugins.shared.pypsa_time_series import series_components
from interop.plugins.shared.sienna_constants import (
    RENEWABLE_DISPATCH_DESTINATION_SCHEMA,
    THERMAL_GENERATORS_DESTINATION_SCHEMA,
    TIME_SERIES_ASSOCIATION_SCHEMA,
    SiennaComponent,
    SiennaRenewableGeneratorCol,
    SiennaSeriesName,
    SiennaThermalGeneratorCol,
)
from interop.plugins.shared.sienna_cost_curves import (
    renewable_cost_value,
    thermal_cost_value,
)
from interop.plugins.shared.sienna_time_series import TimeSeriesInfo, ts_association_row

log = logging.getLogger(__name__)

# Sienna reads a unit that has never run as having run for this long, which is the schema's
# own way of saying the commitment history is unknown.
TIME_AT_STATUS_SENTINEL: float = 10000.0

# A Sienna generator rates itself per unit of its base power, and a generator with no
# availability cap runs at its whole rating.
FULL_RATING: float = 1.0
NO_REACTIVE_POWER: float = 0.0
UNITY_POWER_FACTOR: float = 1.0
NO_COST: float = 0.0

_MINUTES_PER_HOUR = 60.0

_ID_NOTE = "assigned by 1-based row position in the component's table"
_AVAILABLE_NOTE = "PLEXOS states no generator availability; every generator is available"
_STATUS_NOTE = "PLEXOS states no starting commitment; status defaults to on"
_REACTIVE_POWER_NOTE = "PLEXOS states no reactive output; reactive_power defaults to 0.0"
_REACTIVE_LIMITS_NOTE = "PLEXOS states no reactive limits; reactive_power_limits is left unset"
_MUST_RUN_NOTE = "PLEXOS commits a unit rather than forcing it on; must_run defaults to False"
_TIME_AT_STATUS_NOTE = (
    f"PLEXOS states no commitment history; time_at_status takes the {TIME_AT_STATUS_SENTINEL} "
    "sentinel"
)
_POWER_FACTOR_NOTE = "PLEXOS states no power factor; power_factor defaults to 1.0"
_BUS_NAME_NOTE = "bus string name; the sink resolves it to an ACBus id"
_RATING_NOTE = "the generator states no availability cap, so it runs at its whole rating"
_RATING_FROM_SERIES_NOTE = (
    "the generator follows an availability series, which carries every derate, so it rates "
    "at its whole capacity"
)
_BASE_POWER_DERIVATION = "Max Capacity x Units"
_ACTIVE_POWER_DERIVATION = "the minimum this generator can be held to"
_ACTIVE_POWER_NOTE = "the generator states no minimum; active_power defaults to 0.0"
_LIMITS_DERIVATION = "the minimum and the rated capacity, in MW"
_RAMP_DERIVATION = "Max Ramp Up, capped at the rate that covers p_nom in one snapshot"
_TIME_LIMITS_DERIVATION = "Min Up Time and Min Down Time, in hours"
_COST_DERIVATION = "the marginal cost, as the variable cost curve's proportional term"
_START_UP_DERIVATION = "what a start costs"
_PRIME_MOVER_DERIVATION = "the user mappings file names the carrier's prime mover"
_FUEL_TYPE_DERIVATION = "the user mappings file names the carrier's fuel"

_EXTENSIONS_CATEGORY = "extensions.category"
_CATEGORY_DERIVATION = (
    "a carrier is the Fuel or the category, never both, so the category travels beside it"
)

_UNMAPPED_CARRIER_NOTE = "the user mappings file names no such carrier"
_DATA_FILE = "data file"
_FILE_BACKED_NOTE = (
    "Max Capacity comes from a data file rather than a value, so the generator has no rated "
    "capacity to size it or to per-unitise its availability against"
)
_RETIRED_NOTE = "Units = 0 and no Max Units Built marks a retired generator"
_NO_NODE_NOTE = "this object is on no Node, so it has no bus to connect to"
_BUSLESS_NOTE = "the Node this object sits on was not translated to a bus"
_INFEASIBLE_NOTE = (
    "p_min_pu {minimum} sits above p_max_pu {ceiling}, which no dispatch can meet, so the "
    "generator is dropped"
)
_NO_CAPACITY_NOTE = "the rated capacity is {capacity} MW, so it can never dispatch"

# The Sienna types a generator may become. Every other target names a storage unit, which a
# different sub-step writes.
_GENERATOR_TYPES = (SiennaComponent.THERMAL_STANDARD, SiennaComponent.RENEWABLE_DISPATCH)

# An operation cost is a curve on the row and a price per megawatt hour in the report, so
# the event names the column and states the number the curve is built from.
_THERMAL_COST_COLUMN = MappedColumns(
    (SiennaThermalGeneratorCol.OPERATION_COST,), UNIT_DOLLARS_PER_MWH
)
_RENEWABLE_COST_COLUMN = MappedColumns(
    (SiennaRenewableGeneratorCol.OPERATION_COST,), UNIT_DOLLARS_PER_MWH
)
# What the carbon a fuel releases adds, and what a start's fuel costs. Neither is a column
# of its own; each is the source of the value that cites it.
_LIMITS_MIN_ATTRIBUTE = f"{SiennaThermalGeneratorCol.ACTIVE_POWER_LIMITS}.min"
_RAMP_UP_ATTRIBUTE = f"{SiennaThermalGeneratorCol.RAMP_LIMITS}.up"
_TIME_UP_ATTRIBUTE = f"{SiennaThermalGeneratorCol.TIME_LIMITS}.up"
_START_UP_ATTRIBUTE = f"{SiennaThermalGeneratorCol.OPERATION_COST}.start_up"
_LIMITS_MIN_COLUMN = MappedColumns((_LIMITS_MIN_ATTRIBUTE,), UNIT_MW)
_RAMP_UP_COLUMN = MappedColumns((_RAMP_UP_ATTRIBUTE,), UNIT_MW_PER_MINUTE)
_TIME_UP_COLUMN = MappedColumns((_TIME_UP_ATTRIBUTE,), UNIT_HOURS)
_START_UP_COLUMN = MappedColumns((_START_UP_ATTRIBUTE,), UNIT_DOLLARS)
_CARBON_TERM_ATTRIBUTE = f"{SiennaThermalGeneratorCol.OPERATION_COST} carbon term"
_START_FUEL_TERM_ATTRIBUTE = f"{SiennaThermalGeneratorCol.OPERATION_COST}.start_up fuel term"
_CARBON_TERM_COLUMN = MappedColumns((_CARBON_TERM_ATTRIBUTE,), UNIT_DOLLARS_PER_MWH)
_START_FUEL_TERM_COLUMN = MappedColumns((_START_FUEL_TERM_ATTRIBUTE,), UNIT_DOLLARS)


@dataclass(frozen=True)
class _ThermalMapping:
    """One Sienna ThermalStandard: each destination value and where it came from."""

    name: str
    base_power: Decision = maps_to(SiennaThermalGeneratorCol.BASE_POWER, unit=UNIT_MVA)
    available: Decision = maps_to(SiennaThermalGeneratorCol.AVAILABLE)
    status: Decision = maps_to(SiennaThermalGeneratorCol.STATUS)
    bus_name: Decision = maps_to(SiennaThermalGeneratorCol.BUS_NAME)
    active_power: Decision = maps_to(SiennaThermalGeneratorCol.ACTIVE_POWER, unit=UNIT_MW)
    reactive_power: Decision = maps_to(SiennaThermalGeneratorCol.REACTIVE_POWER, unit=UNIT_MW)
    rating: Decision = maps_to(SiennaThermalGeneratorCol.RATING)
    active_power_limits: Decision = declares(_LIMITS_MIN_COLUMN)
    reactive_power_limits: Decision = maps_to(SiennaThermalGeneratorCol.REACTIVE_POWER_LIMITS)
    ramp_limits: Decision = declares(_RAMP_UP_COLUMN)
    time_limits: Decision = declares(_TIME_UP_COLUMN)
    start_up: Decision = declares(_START_UP_COLUMN)
    operation_cost: Decision = declares(_THERMAL_COST_COLUMN)
    prime_mover_type: Decision = maps_to(SiennaThermalGeneratorCol.PRIME_MOVER_TYPE)
    fuel_type: Decision = maps_to(SiennaThermalGeneratorCol.FUEL_TYPE)
    must_run: Decision = maps_to(SiennaThermalGeneratorCol.MUST_RUN)
    time_at_status: Decision = maps_to(SiennaThermalGeneratorCol.TIME_AT_STATUS)


@dataclass(frozen=True)
class _RenewableMapping:
    """One Sienna RenewableDispatch: each destination value and where it came from."""

    name: str
    base_power: Decision = maps_to(SiennaRenewableGeneratorCol.BASE_POWER, unit=UNIT_MVA)
    available: Decision = maps_to(SiennaRenewableGeneratorCol.AVAILABLE)
    bus_name: Decision = maps_to(SiennaRenewableGeneratorCol.BUS_NAME)
    active_power: Decision = maps_to(SiennaRenewableGeneratorCol.ACTIVE_POWER, unit=UNIT_MW)
    reactive_power: Decision = maps_to(SiennaRenewableGeneratorCol.REACTIVE_POWER, unit=UNIT_MW)
    rating: Decision = maps_to(SiennaRenewableGeneratorCol.RATING)
    reactive_power_limits: Decision = maps_to(SiennaRenewableGeneratorCol.REACTIVE_POWER_LIMITS)
    power_factor: Decision = maps_to(SiennaRenewableGeneratorCol.POWER_FACTOR)
    operation_cost: Decision = declares(_RENEWABLE_COST_COLUMN)
    prime_mover_type: Decision = maps_to(SiennaRenewableGeneratorCol.PRIME_MOVER_TYPE)


@dataclass(frozen=True)
class _Translated:
    """One generator's PLEXOS reading, the Sienna target it takes, and the snapshot length."""

    mapping: GeneratorMapping
    target: CarrierTarget
    sienna_type: str
    minutes_per_snapshot: float
    follows_a_series: bool


@dataclass(frozen=True)
class _Availability:
    """One generator's staged availability profile, and what reads it back to per unit."""

    plexos_property: str
    scale: float
    sienna_type: str
    sienna_id: int


@dataclass(frozen=True)
class TranslatedGenerators:
    """What the generator mapping produced, keyed by the Sienna type each row belongs to.

    ``series`` is the companion parquet a cost that changes rides in, or None where every
    generator states one price.
    """

    rows_by_type: dict[str, list[dict[str, Any]]]
    extensions: list[GeneratorExtension]
    availability_by_name: dict[str, _Availability]
    sienna_type_by_name: dict[str, str]
    series: pl.LazyFrame | None = None


def map_generators(
    state: State, recorder: ScopedRecorder, targets: CarrierTargets
) -> TranslatedGenerators:
    """Translate every staged PLEXOS Generator into the Sienna type its carrier names."""
    lookups = build_lookups(state)
    # build_lookups reads the bus names off the PyPSA table, which this hop never writes.
    bus_names = _bus_names(state)
    with_a_series = _generators_with_a_series(state, lookups)
    # A turbine drawing on a Storage becomes a storage unit, never also a generator.
    turbines = storage_turbine_names(state)
    rows_by_type: dict[str, list[dict[str, Any]]] = {}
    extensions: list[GeneratorExtension] = []
    availability: dict[str, _Availability] = {}
    units_by_name: dict[str, float] = {}
    dated_scale_by_name: dict[str, float] = {}
    sienna_type_by_name: dict[str, str] = {}
    skipped: list[SkippedComponent] = []
    kept_expansions: list[Any] = []
    mapped: list[GeneratorMapping] = []
    for generator in _generator_rows(state):
        name = generator[PlexosObjectCol.NAME]
        if name in turbines:
            continue
        target = _target_for(name, generator, lookups, bus_names, targets, skipped, with_a_series)
        if target is None:
            continue
        reporter = SiennaComponentReporter(recorder, target.sienna_type)
        rows = rows_by_type.setdefault(target.sienna_type, [])
        row = _row_for(target, reporter)
        row[SiennaThermalGeneratorCol.ID] = _next_id(rows)
        reporter.record(
            target.mapping.name,
            MappedColumns((SiennaThermalGeneratorCol.ID,)),
            Decision.default(row[SiennaThermalGeneratorCol.ID], _ID_NOTE),
        )
        rows.append(row)
        _record_category(reporter, target.mapping)
        _record_source_notes(reporter, target.mapping)
        _record_lost_minimum(reporter, target)
        _record_lifespan(reporter, target.mapping)
        kept_expansions.append(target.mapping.expansion)
        mapped.append(target.mapping)
        units_by_name[target.mapping.name] = target.mapping.units
        dated_scale_by_name[target.mapping.name] = _dated_capacity_scale(target.mapping)
        extensions.append(_extension_for(target.mapping))
        sienna_type_by_name[target.mapping.name] = target.sienna_type
        profile = target.mapping.availability.profile
        if profile is not None:
            availability[target.mapping.name] = _Availability(
                plexos_property=profile.property_name,
                scale=profile.scale,
                sienna_type=target.sienna_type,
                sienna_id=row[SiennaThermalGeneratorCol.ID],
            )
    _report_unstaged_profiles(state, recorder, availability)
    _stage_availability(
        state,
        availability,
        rows_by_type,
        sienna_type_by_name,
        units_by_name,
        dated_scale_by_name,
    )
    _report_left_out(recorder, skipped)
    warn_about_dropped_builds(expansion for expansion in kept_expansions)
    fuel_prices = build_fuel_price_series(state, mapped)
    return TranslatedGenerators(
        rows_by_type=rows_by_type,
        extensions=[_priced_by_date(one, fuel_prices.names) for one in extensions],
        availability_by_name=availability,
        sienna_type_by_name=sienna_type_by_name,
        series=fuel_prices.frame,
    )


def _priced_by_date(
    extension: GeneratorExtension, priced_by_date: frozenset[str]
) -> GeneratorExtension:
    """Point a generator whose fuel the model prices by date at the companion holding it."""
    if extension.name not in priced_by_date:
        return extension
    companion = companion_filename(ExtensionKind.GENERATOR)
    return extension.model_copy(update={"marginal_cost_series": companion})


def build_generator_ts_associations(
    translated: TranslatedGenerators, ts_info: TimeSeriesInfo
) -> pl.DataFrame:
    """One association row per generator whose availability comes from a profile.

    The sink streams straight from the PLEXOS frame, so the row names the PLEXOS class and
    the PLEXOS property. ``scaling_factor`` is what divides the stated values back into the
    per-unit shape a Sienna rating multiplies.
    """
    rows = [
        ts_association_row(
            owner_type=availability.sienna_type,
            owner_id=availability.sienna_id,
            component_name=name,
            series_name=SiennaSeriesName.MAX_ACTIVE_POWER,
            ts_info=ts_info,
            source_table=PlexosClass.GENERATOR,
            source_attribute=availability.plexos_property,
            scaling_factor=(1.0 / availability.scale) if availability.scale else 1.0,
        )
        for name, availability in sorted(translated.availability_by_name.items())
    ]
    if not rows:
        return pl.DataFrame(schema=TIME_SERIES_ASSOCIATION_SCHEMA)
    return pl.DataFrame(rows, schema=TIME_SERIES_ASSOCIATION_SCHEMA)


def _next_id(rows: list[dict[str, Any]]) -> int:
    """One more than the rows already written for this Sienna type, counting from one."""
    return len(rows) + 1


def generator_schema(sienna_type: str) -> dict[str, Any]:
    """The destination schema the rows of one Sienna generator type fill."""
    return (
        THERMAL_GENERATORS_DESTINATION_SCHEMA
        if sienna_type == SiennaComponent.THERMAL_STANDARD
        else RENEWABLE_DISPATCH_DESTINATION_SCHEMA
    )


def generator_types() -> tuple[str, ...]:
    return _GENERATOR_TYPES


def _generator_rows(state: State) -> list[dict[str, Any]]:
    """Each staged Generator's object row, sorted by name so ids are stable."""
    frame = state.source_topology.get(PlexosClass.GENERATOR)
    if frame is None:
        return []
    table = frame.collect().sort(PlexosObjectCol.NAME)
    return table.to_dicts()


def _dated_capacity_scale(mapping: GeneratorMapping) -> float:
    """What a dated Max Capacity is a share of, or zero where the capacity is fixed."""
    if not mapping.p_nom:
        return 0.0
    return mapping.candidate.rated_unit_count / mapping.p_nom


def _generators_with_a_series(state: State, lookups: Lookups) -> set[str]:
    """Every generator whose availability comes from a series rather than one number.

    Its rating is then the whole of it, because the series carries every derate.
    """
    staged = {
        name
        for name, plexos_property in lookups.availability_profiles.items()
        if (str(PlexosClass.GENERATOR), plexos_property) in state.source_time_series
    }
    outages = state.source_time_series.get((str(PlexosClass.GENERATOR), PlexosProperty.UNITS_OUT))
    if outages is None:
        return staged
    return staged | set(series_components(outages))


def _bus_names(state: State) -> set[str]:
    table = state.destination_tables.get(SiennaComponent.AC_BUS)
    return set() if table is None else set(table[SiennaThermalGeneratorCol.NAME].to_list())


def _target_for(
    name: str,
    generator: dict[str, Any],
    lookups: Lookups,
    bus_names: set[str],
    targets: CarrierTargets,
    skipped: list[SkippedComponent],
    with_a_series: set[str],
) -> _Translated | None:
    """One generator's mapping and its Sienna type, or None where it is left out.

    The order the readings run in is the order the PLEXOS to PyPSA hop runs them in, so a
    generator both hops leave out is left out for the same stated reason.
    """
    left_out = _unreadable(name, generator, lookups, bus_names)
    if left_out is not None:
        skipped.append(left_out)
        return None
    source = read_source(generator, name, lookups)
    mapping = derive_generator(source, lookups.gen_to_node[name], lookups)
    target = targets.find(mapping.carrier)
    if target is None:
        skipped.append(_no_such_carrier(mapping))
        return None
    if target.sienna_type not in _GENERATOR_TYPES:
        return None
    if has_infeasible_dispatch_range(mapping):
        skipped.append(_infeasible(mapping))
        return None
    follows_a_series = name in with_a_series
    return _Translated(
        mapping=mapping,
        target=target,
        sienna_type=str(target.sienna_type),
        minutes_per_snapshot=lookups.minutes_per_snapshot,
        follows_a_series=follows_a_series,
    )


def _unreadable(
    name: str, generator: dict[str, Any], lookups: Lookups, bus_names: set[str]
) -> SkippedComponent | None:
    """Why the model leaves this generator with nothing to translate, or None where it does not."""
    node = lookups.gen_to_node.get(name)
    if node is None:
        return _skip(name, PlexosCollection.NODES, None, _NO_NODE_NOTE)
    if node not in bus_names:
        return _skip(name, PlexosCollection.NODES, node, _BUSLESS_NOTE)
    if PlexosProperty.MAX_CAPACITY in lookups.file_backed_properties.get(name, []):
        return _skip(name, PlexosProperty.MAX_CAPACITY, _DATA_FILE, _FILE_BACKED_NOTE, UNIT_MW)
    return _unrated(read_source(generator, name, lookups))


def _unrated(source: SourceGenerator) -> SkippedComponent | None:
    """Why the object has no capacity to dispatch, or None where it has one."""
    if source.units == 0.0 and not source.is_candidate:
        return _skip(source.name, PlexosProperty.UNITS, source.units, _RETIRED_NOTE)
    if source.p_nom <= 0.0:
        return _skip(
            source.name,
            PlexosProperty.MAX_CAPACITY,
            None,
            _NO_CAPACITY_NOTE.format(capacity=source.p_nom),
            UNIT_MW,
        )
    return find_blocked_candidate(source.candidate)


def _no_such_carrier(mapping: GeneratorMapping) -> SkippedComponent:
    return SkippedComponent(
        SourceValue(PlexosClass.GENERATOR, mapping.name, None, None),
        _carrier_note(mapping.carrier, mapping.fuel is not None),
    )


def _infeasible(mapping: GeneratorMapping) -> SkippedComponent:
    """The minimum sits above what the generator can reach, so no dispatch meets it."""
    return SkippedComponent(
        SourceValue(
            PlexosClass.GENERATOR,
            mapping.name,
            mapping.minimum.source_property,
            mapping.minimum.source_value,
        ),
        _INFEASIBLE_NOTE.format(
            minimum=mapping.minimum.p_min_pu,
            ceiling=mapping.availability.static_p_max_pu,
        ),
    )


def _skip(
    name: str, attribute: str, value: Any, note: str, unit: str | None = None
) -> SkippedComponent:
    """One generator left out, and the reading that left it out."""
    return SkippedComponent(SourceValue(PlexosClass.GENERATOR, name, attribute, value, unit), note)


def _stage_availability(
    state: State,
    availability: dict[str, _Availability],
    rows_by_type: dict[str, list[dict[str, Any]]],
    sienna_type_by_name: dict[str, str],
    units_by_name: dict[str, float],
    dated_scale_by_name: dict[str, float],
) -> None:
    """Build the series each generator follows, and keep only the ones that got one.

    A Sienna association names a staged frame and one scaling factor, so a profile and an
    outage that compound are multiplied here rather than stated as two rows.
    """
    staged = stage_availability(
        state,
        [
            AvailabilityInputs(
                name=name,
                plexos_property=None if one is None else one.plexos_property,
                profile_scale=1.0 if one is None else one.scale,
                units=units_by_name.get(name, 0.0),
                dated_capacity_scale=dated_scale_by_name.get(name, 0.0),
            )
            for name in sorted(units_by_name)
            for one in [availability.get(name)]
        ],
    )
    for name in list(availability):
        if name not in staged:
            del availability[name]
    for name in staged - set(availability):
        availability[name] = _Availability(
            plexos_property=AVAILABILITY_SERIES,
            scale=1.0,
            sienna_type=sienna_type_by_name[name],
            sienna_id=_id_of(rows_by_type, sienna_type_by_name, name),
        )


def _id_of(
    rows_by_type: dict[str, list[dict[str, Any]]],
    sienna_type_by_name: dict[str, str],
    name: str,
) -> int:
    for row in rows_by_type[sienna_type_by_name[name]]:
        if row[SiennaThermalGeneratorCol.NAME] == name:
            return int(row[SiennaThermalGeneratorCol.ID])
    raise KeyError(name)


def _report_unstaged_profiles(
    state: State, recorder: ScopedRecorder, availability: dict[str, _Availability]
) -> None:
    """An availability profile the source could not read leaves its owners on their static value.

    The generator keeps what it already holds, and the association is not written, so the
    sink asks the staged frames for nothing they do not hold.
    """
    reporter = SiennaComponentReporter(recorder, SiennaComponent.THERMAL_STANDARD)
    owners_by_property: dict[str, list[ProfileOwner]] = {}
    for name, one in sorted(availability.items()):
        if (PlexosClass.GENERATOR, one.plexos_property) in state.source_time_series:
            continue
        owners_by_property.setdefault(one.plexos_property, []).append(ProfileOwner(name, one.scale))
    for plexos_property, owners in owners_by_property.items():
        report_profile_not_staged(plexos_property, owners, reporter)
        for owner in owners:
            del availability[owner.name]


def _report_left_out(recorder: ScopedRecorder, skipped: list[SkippedComponent]) -> None:
    """Every generator left out reaches the report, and the console once per reading."""
    reporter = SiennaComponentReporter(recorder, SiennaComponent.THERMAL_STANDARD)
    for one in skipped:
        reporter.record_skipped(one.source, one.note)
    warn_about_skips(skipped)


def _carrier_note(carrier: str, burns_fuel: bool) -> str:
    concept = "fuel" if burns_fuel else "category"
    return f"{concept}={carrier!r}: {_UNMAPPED_CARRIER_NOTE}"


def _megawatts(per_unit: float, base_power: float) -> float:
    return round(per_unit * base_power, 6)


def _row_for(translated: _Translated, reporter: SiennaComponentReporter) -> dict[str, Any]:
    mapping = translated.mapping
    name = mapping.name
    _record_cost_terms(reporter, mapping)
    if translated.sienna_type == SiennaComponent.THERMAL_STANDARD:
        thermal = _derive_thermal(translated)
        reporter.record_mapping(name, thermal)
        row = destination_row(thermal, SiennaThermalGeneratorCol.NAME, name)
        row[SiennaThermalGeneratorCol.OPERATION_COST] = thermal_cost_value(
            mapping.cost.marginal_cost, _start_up_cost(mapping)
        )
        row[SiennaThermalGeneratorCol.ACTIVE_POWER_LIMITS] = _limits(mapping)
        row[SiennaThermalGeneratorCol.RAMP_LIMITS] = _ramp_struct(translated)
        row[SiennaThermalGeneratorCol.TIME_LIMITS] = _time_struct(translated)
        return row
    renewable = _derive_renewable(translated)
    reporter.record_mapping(name, renewable)
    row = destination_row(renewable, SiennaRenewableGeneratorCol.NAME, name)
    row[SiennaRenewableGeneratorCol.OPERATION_COST] = renewable_cost_value(
        mapping.cost.marginal_cost
    )
    return row


def _record_cost_terms(reporter: SiennaComponentReporter, mapping: GeneratorMapping) -> None:
    """The carbon and start-fuel terms precede the values that cite them as sources."""
    decisions = decide_generator(mapping)
    if decisions.carbon is not None:
        reporter.record(mapping.name, _CARBON_TERM_COLUMN, decisions.carbon)
    if decisions.start_fuel is not None:
        reporter.record(mapping.name, _START_FUEL_TERM_COLUMN, decisions.start_fuel)


def _start_up_decision(translated: _Translated) -> Decision:
    """What a start costs, with the fuel term named as this hop names it."""
    commitment = decide_generator(translated.mapping).start_up_cost
    return _in_sienna_words(commitment, translated)


def _derive_thermal(translated: _Translated) -> _ThermalMapping:
    mapping, target = translated.mapping, translated.target
    return _ThermalMapping(
        name=mapping.name,
        base_power=decide_generator(mapping).p_nom,
        available=Decision.default(True, _AVAILABLE_NOTE),
        status=Decision.default(True, _STATUS_NOTE),
        bus_name=Decision.default(mapping.bus_name, _BUS_NAME_NOTE),
        active_power=_active_power(mapping),
        reactive_power=Decision.default(NO_REACTIVE_POWER, _REACTIVE_POWER_NOTE),
        rating=_rating(translated),
        active_power_limits=_minimum_decision(translated),
        reactive_power_limits=Decision.default(None, _REACTIVE_LIMITS_NOTE),
        ramp_limits=_ramp_decision(translated),
        time_limits=_time_decision(translated),
        start_up=_start_up_decision(translated),
        operation_cost=_cost_decision(translated),
        prime_mover_type=_prime_mover(mapping, target),
        fuel_type=_fuel_type(mapping, target),
        must_run=Decision.default(False, _MUST_RUN_NOTE),
        time_at_status=Decision.default(TIME_AT_STATUS_SENTINEL, _TIME_AT_STATUS_NOTE),
    )


def _derive_renewable(translated: _Translated) -> _RenewableMapping:
    mapping, target = translated.mapping, translated.target
    return _RenewableMapping(
        name=mapping.name,
        base_power=decide_generator(mapping).p_nom,
        available=Decision.default(True, _AVAILABLE_NOTE),
        bus_name=Decision.default(mapping.bus_name, _BUS_NAME_NOTE),
        active_power=Decision.default(NO_COST, _ACTIVE_POWER_NOTE),
        reactive_power=Decision.default(NO_REACTIVE_POWER, _REACTIVE_POWER_NOTE),
        rating=_rating(translated),
        reactive_power_limits=Decision.default(None, _REACTIVE_LIMITS_NOTE),
        power_factor=Decision.default(UNITY_POWER_FACTOR, _POWER_FACTOR_NOTE),
        operation_cost=_cost_decision(translated),
        prime_mover_type=_prime_mover(mapping, target),
    )


def _active_power(mapping: GeneratorMapping) -> Decision:
    minimum = mapping.minimum
    megawatts = _megawatts(minimum.p_min_pu, mapping.p_nom)
    if minimum.source_property is None:
        return Decision.default(megawatts, _ACTIVE_POWER_NOTE)
    source = SourceValue(
        PlexosClass.GENERATOR, mapping.name, minimum.source_property, minimum.source_value
    )
    return Decision.derived(megawatts, [source], _ACTIVE_POWER_DERIVATION)


def _rating(translated: _Translated) -> Decision:
    """What the generator may reach, per unit of its base power.

    A generator following a series rates at its whole capacity, because the series already
    carries every derate. One with no series rates at the static ceiling it states.
    """
    if translated.follows_a_series:
        return Decision.default(FULL_RATING, _RATING_FROM_SERIES_NOTE)
    return Decision.default(translated.mapping.availability.static_p_max_pu, _RATING_NOTE)


def _limits(mapping: GeneratorMapping) -> dict[str, float]:
    """What the generator may produce, in megawatts."""
    return {
        "min": _megawatts(mapping.minimum.p_min_pu, mapping.p_nom),
        "max": _megawatts(mapping.availability.static_p_max_pu, mapping.p_nom),
    }


def _minimum_decision(translated: _Translated) -> Decision:
    """The floor the generator is held to, as the shared reading states it, in megawatts."""
    mapping = translated.mapping
    decision = decide_generator(mapping).p_min_pu
    return replace(decision, value=_megawatts(mapping.minimum.p_min_pu, mapping.p_nom))


def _ramp_struct(translated: _Translated) -> dict[str, float | None] | None:
    """The rates the unit may change output at, in megawatts per minute."""
    commitment = translated.mapping.unit_commitment
    if commitment is None or commitment.ramp_limit_up is None:
        return None
    return {
        "up": _rate_per_minute(commitment.ramp_limit_up, translated),
        "down": _rate_per_minute(commitment.ramp_limit_down, translated),
    }


def _ramp_decision(translated: _Translated) -> Decision:
    """The rate the unit may ramp up at, capped at one snapshot's worth of its capacity."""
    struct = _ramp_struct(translated)
    if struct is None:
        return Decision.unreported(None)
    commitment = translated.mapping.unit_commitment
    assert commitment is not None
    source = SourceValue(
        PlexosClass.GENERATOR,
        translated.mapping.name,
        PlexosProperty.MAX_RAMP_UP,
        commitment.max_ramp_up,
        UNIT_MW_PER_MINUTE,
    )
    return Decision.derived(struct["up"], [source], _RAMP_DERIVATION)


def _rate_per_minute(per_snapshot: float | None, translated: _Translated) -> float | None:
    """A per-unit-per-snapshot limit read back as the megawatts per minute Sienna states."""
    if per_snapshot is None:
        return None
    return per_snapshot * translated.mapping.p_nom / translated.minutes_per_snapshot


def _time_struct(translated: _Translated) -> dict[str, float] | None:
    """How long the unit must stay on or off once it changes state, in hours."""
    commitment = translated.mapping.unit_commitment
    if commitment is None or commitment.min_up_time is None:
        return None
    return {
        "up": (commitment.min_up_time or 0.0) * translated.minutes_per_snapshot / _MINUTES_PER_HOUR,
        "down": (commitment.min_down_time or 0.0)
        * translated.minutes_per_snapshot
        / _MINUTES_PER_HOUR,
    }


def _time_decision(translated: _Translated) -> Decision:
    """How long the unit must stay on once it starts, in hours."""
    struct = _time_struct(translated)
    if struct is None:
        return Decision.unreported(None)
    commitment = translated.mapping.unit_commitment
    assert commitment is not None
    source = SourceValue(
        PlexosClass.GENERATOR,
        translated.mapping.name,
        PlexosProperty.MIN_UP_TIME,
        commitment.min_up_hours,
        UNIT_HOURS,
    )
    return Decision.derived(struct["up"], [source], _TIME_LIMITS_DERIVATION)


def _cost_decision(translated: _Translated) -> Decision:
    """The price per megawatt hour, with every PLEXOS value behind it stated."""
    return _in_sienna_words(decide_generator(translated.mapping).marginal_cost, translated)


# What the shared reading calls a term it derived earlier, and what Sienna calls it here.
_TERM_IN_SIENNA_WORDS: dict[str, str] = {
    MARGINAL_COST_CARBON_TERM: _CARBON_TERM_ATTRIBUTE,
    START_UP_COST_FUEL_TERM: _START_FUEL_TERM_ATTRIBUTE,
}


def _in_sienna_words(decision: Decision, translated: _Translated) -> Decision:
    """The same decision, with each term it derived earlier named as this hop names it.

    The shared reading states a back-reference in PyPSA words, because the hop it was
    written for writes a PyPSA generator. This hop writes a Sienna one.
    """
    return replace(
        decision,
        sources=tuple(_source_in_sienna_words(source, translated) for source in decision.sources),
    )


def _source_in_sienna_words(source: SourceValue, translated: _Translated) -> SourceValue:
    renamed = _TERM_IN_SIENNA_WORDS.get(str(source.attribute))
    if renamed is None:
        return source
    return SourceValue(
        component=translated.sienna_type,
        name=source.name,
        attribute=renamed,
        value=source.value,
        unit=source.unit,
        framework=Framework.SIENNA,
    )


def _start_up_cost(mapping: GeneratorMapping) -> float:
    """What a start costs: the stated Start Cost, or the fuel a start burns.

    Never both. A model stating both has already priced the fuel inside its own Start Cost,
    so adding them would charge it twice.
    """
    commitment = mapping.unit_commitment
    if commitment is None:
        return NO_COST
    match commitment.start_pricing:
        case StartPricing.START_FUEL:
            fuel = commitment.start_fuel
            return NO_COST if fuel is None else fuel.offtake * fuel.price
        case StartPricing.STATED:
            return float(commitment.stated_start_cost or NO_COST)
        case _:
            return NO_COST


def _prime_mover(mapping: GeneratorMapping, target: CarrierTarget) -> Decision:
    source = SourceValue(PlexosClass.GENERATOR, mapping.name, "carrier", mapping.carrier)
    return Decision.derived(target.prime_mover, [source], _PRIME_MOVER_DERIVATION)


def _fuel_type(mapping: GeneratorMapping, target: CarrierTarget) -> Decision:
    source = SourceValue(PlexosClass.GENERATOR, mapping.name, "carrier", mapping.carrier)
    return Decision.derived(target.fuel_type, [source], _FUEL_TYPE_DERIVATION)


# Every expansion value, and the sidecar field that holds it. Sienna states none of them,
# so each one reaches PyPSA through extensions.json.
_EXPANSION_COLUMNS: tuple[tuple[str, str], ...] = (
    ("p_nom_extendable", "extensions.p_nom_extendable"),
    ("p_nom_max", "extensions.p_nom_max"),
    ("p_nom_min", "extensions.p_nom_min"),
    ("overnight_cost", "extensions.overnight_cost_per_mw"),
    ("discount_rate", "extensions.discount_rate"),
    ("lifetime", "extensions.lifetime_years"),
    ("unit_size", "extensions.unit_size_mw"),
    ("technical_life", "extensions.technical_life_years"),
    ("fom_charge", "extensions.fom_charge_per_mw_year"),
)


def _record_source_notes(reporter: SiennaComponentReporter, mapping: GeneratorMapping) -> None:
    """The notes that name only what the model states, which every hop out of PLEXOS records."""
    record_generator_source_notes(reporter, decide_generator(mapping))
    record_expansion_notes(reporter, mapping.name, mapping.expansion)
    _record_expansion(reporter, mapping)


def _record_lost_minimum(reporter: SiennaComponentReporter, translated: _Translated) -> None:
    """A RenewableDispatch holds no minimum, so the reading behind one reaches no field.

    A ThermalStandard states the minimum in active_power_limits, and its own event says so.
    """
    if translated.sienna_type != SiennaComponent.RENEWABLE_DISPATCH:
        return
    minimum = translated.mapping.minimum
    if minimum.source_property is None:
        return
    decision = decide_generator(translated.mapping).p_min_pu
    reporter.record_dropped(
        SourceValue(
            PlexosClass.GENERATOR,
            translated.mapping.name,
            minimum.source_property,
            minimum.source_value,
        ),
        decision.explanation,
    )


def _record_lifespan(reporter: SiennaComponentReporter, mapping: GeneratorMapping) -> None:
    """When the object enters and leaves service, against the sidecar field each one lands in."""
    lifespan = derive_lifespan(PlexosClass.GENERATOR, mapping.name, mapping.lifespan)
    reporter.record(mapping.name, MappedColumns(("extensions.build_year",)), lifespan.build_year)
    reporter.record(
        mapping.name, MappedColumns(("extensions.retirement_year",)), lifespan.retirement_year
    )


def _record_expansion(reporter: SiennaComponentReporter, mapping: GeneratorMapping) -> None:
    """What a candidate may build and what building it costs, against the sidecar field."""
    for field_name, column in _EXPANSION_COLUMNS:
        reporter.record(
            mapping.name,
            MappedColumns((column,), _EXPANSION_UNITS.get(column)),
            getattr(mapping.expansion, field_name),
        )


_EXPANSION_UNITS: dict[str, str] = {
    "extensions.p_nom_max": UNIT_MW,
    "extensions.p_nom_min": UNIT_MW,
    "extensions.overnight_cost_per_mw": UNIT_DOLLARS_PER_MW,
    "extensions.lifetime_years": UNIT_YEARS,
    "extensions.unit_size_mw": UNIT_MW,
    "extensions.technical_life_years": UNIT_YEARS,
    "extensions.fom_charge_per_mw_year": UNIT_DOLLARS_PER_MW_YEAR,
}


def _record_category(reporter: SiennaComponentReporter, mapping: GeneratorMapping) -> None:
    """A category that lost to a Fuel still travels, so a crosswalk downstream can key on it."""
    if mapping.carrier == mapping.category:
        return
    source = SourceValue(
        PlexosClass.GENERATOR, mapping.name, PlexosObjectCol.CATEGORY, mapping.category
    )
    reporter.record(
        mapping.name,
        MappedColumns((_EXTENSIONS_CATEGORY,)),
        Decision.derived(mapping.category, [source], _CATEGORY_DERIVATION),
    )


def _extension_for(mapping: GeneratorMapping) -> GeneratorExtension:
    """What the generator states that Sienna has no field for."""
    return GeneratorExtension(
        name=mapping.name,
        carrier=mapping.carrier,
        committable=mapping.is_committable or None,
        p_nom_extendable=bool(mapping.expansion.p_nom_extendable.value),
        category=mapping.category,
        efficiency=mapping.efficiency,
        **_expansion_fields(mapping),
    )


def _expansion_fields(mapping: GeneratorMapping) -> dict[str, Any]:
    """What a candidate states that Sienna has no field for, ready for its record.

    A fixed generator states none of it, and every field stays unset rather than defaulted.
    """
    expansion = mapping.expansion
    return {
        "p_nom_max": _decided(expansion.p_nom_max),
        "p_nom_min": _decided(expansion.p_nom_min),
        "overnight_cost_per_mw": _decided(expansion.overnight_cost),
        "discount_rate": _decided(expansion.discount_rate),
        "lifetime_years": _decided(expansion.lifetime),
        "unit_size_mw": _decided(expansion.unit_size),
        "technical_life_years": _decided(expansion.technical_life),
        "fom_charge_per_mw_year": _decided(expansion.fom_charge),
        **_lifespan_fields(mapping),
    }


def _lifespan_fields(mapping: GeneratorMapping) -> dict[str, Any]:
    """When the object enters and leaves service, neither of which Sienna holds."""
    lifespan = derive_lifespan(PlexosClass.GENERATOR, mapping.name, mapping.lifespan)
    build_year = _decided(lifespan.build_year)
    retirement_year = _decided(lifespan.retirement_year)
    return {
        "build_year": None if build_year is None else int(build_year),
        "retirement_year": None if retirement_year is None else int(retirement_year),
    }


def _decided(decision: Decision) -> float | None:
    """A decision's number, or None where the mapping reported nothing for it."""
    if decision.kind is DecisionKind.UNREPORTED or decision.value is None:
        return None
    return float(decision.value)
