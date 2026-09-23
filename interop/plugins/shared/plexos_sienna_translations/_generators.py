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
from dataclasses import dataclass
from typing import Any

import polars as pl

from interop.core.extensions import GeneratorExtension
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import (
    UNIT_DOLLARS_PER_MWH,
    UNIT_HOURS,
    UNIT_MVA,
    UNIT_MW,
    UNIT_MW_PER_MINUTE,
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
)
from interop.plugins.shared.plexos_pypsa_translations._generator_decisions import (
    decide_generator,
    record_generator_source_notes,
)
from interop.plugins.shared.plexos_pypsa_translations._generator_derivation import (
    GeneratorMapping,
    StartPricing,
    derive_generator,
    has_infeasible_dispatch_range,
    read_source,
)
from interop.plugins.shared.plexos_pypsa_translations._generator_lookups import (
    Lookups,
    build_lookups,
)
from interop.plugins.shared.plexos_pypsa_translations._storage_turbines import (
    storage_turbine_names,
)
from interop.plugins.shared.plexos_pypsa_translations.decisions import (
    Decision,
    DecisionKind,
    MappedColumns,
    SourceValue,
    destination_row,
    maps_to,
)
from interop.plugins.shared.plexos_sienna_translations._carriers import (
    CarrierTarget,
    CarrierTargets,
)
from interop.plugins.shared.plexos_sienna_translations._shared import SiennaComponentReporter
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
_BASE_POWER_DERIVATION = "Max Capacity x Units"
_ACTIVE_POWER_DERIVATION = "the minimum this generator can be held to"
_ACTIVE_POWER_NOTE = "the generator states no minimum; active_power defaults to 0.0"
_LIMITS_DERIVATION = "the minimum and the rated capacity, in MW"
_RAMP_DERIVATION = "Max Ramp, capped at the rate that covers base_power in one snapshot"
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
    "the minimum {minimum} MW sits above the available {ceiling} MW, which no dispatch can "
    "meet, so the generator is dropped"
)
_NO_CAPACITY_NOTE = "the rated capacity is {capacity} MW, so it can never dispatch"

# The Sienna types a generator may become. Every other target names a storage unit, which a
# different sub-step writes.
_GENERATOR_TYPES = (SiennaComponent.THERMAL_STANDARD, SiennaComponent.RENEWABLE_DISPATCH)


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
    active_power_limits: Decision = maps_to(
        SiennaThermalGeneratorCol.ACTIVE_POWER_LIMITS, unit=UNIT_MW
    )
    reactive_power_limits: Decision = maps_to(SiennaThermalGeneratorCol.REACTIVE_POWER_LIMITS)
    ramp_limits: Decision = maps_to(SiennaThermalGeneratorCol.RAMP_LIMITS, unit=UNIT_MW_PER_MINUTE)
    time_limits: Decision = maps_to(SiennaThermalGeneratorCol.TIME_LIMITS, unit=UNIT_HOURS)
    operation_cost: Decision = maps_to(SiennaThermalGeneratorCol.OPERATION_COST)
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
    operation_cost: Decision = maps_to(SiennaRenewableGeneratorCol.OPERATION_COST)
    prime_mover_type: Decision = maps_to(SiennaRenewableGeneratorCol.PRIME_MOVER_TYPE)


@dataclass(frozen=True)
class _Translated:
    """One generator's PLEXOS reading, the Sienna target it takes, and the snapshot length."""

    mapping: GeneratorMapping
    target: CarrierTarget
    sienna_type: str
    minutes_per_snapshot: float


@dataclass(frozen=True)
class _Availability:
    """One generator's staged availability profile, and what reads it back to per unit."""

    plexos_property: str
    scale: float
    sienna_type: str
    sienna_id: int


@dataclass(frozen=True)
class TranslatedGenerators:
    """What the generator mapping produced, keyed by the Sienna type each row belongs to."""

    rows_by_type: dict[str, list[dict[str, Any]]]
    extensions: list[GeneratorExtension]
    availability_by_name: dict[str, _Availability]
    sienna_type_by_name: dict[str, str]


def map_generators(
    state: State, recorder: ScopedRecorder, targets: CarrierTargets
) -> TranslatedGenerators:
    """Translate every staged PLEXOS Generator into the Sienna type its carrier names."""
    lookups = build_lookups(state)
    # build_lookups reads the bus names off the PyPSA table, which this hop never writes.
    bus_names = _bus_names(state)
    # A turbine drawing on a Storage becomes a storage unit, never also a generator.
    turbines = storage_turbine_names(state)
    rows_by_type: dict[str, list[dict[str, Any]]] = {}
    extensions: list[GeneratorExtension] = []
    availability: dict[str, _Availability] = {}
    sienna_type_by_name: dict[str, str] = {}
    for generator in _generator_rows(state):
        name = generator[PlexosObjectCol.NAME]
        if name in turbines:
            continue
        target = _target_for(name, generator, lookups, bus_names, targets, recorder)
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
    return TranslatedGenerators(
        rows_by_type=rows_by_type,
        extensions=extensions,
        availability_by_name=availability,
        sienna_type_by_name=sienna_type_by_name,
    )


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


def _bus_names(state: State) -> set[str]:
    table = state.destination_tables.get(SiennaComponent.AC_BUS)
    return set() if table is None else set(table[SiennaThermalGeneratorCol.NAME].to_list())


def _target_for(
    name: str,
    generator: dict[str, Any],
    lookups: Lookups,
    bus_names: set[str],
    targets: CarrierTargets,
    recorder: ScopedRecorder,
) -> _Translated | None:
    """One generator's mapping and its Sienna type, or None where it is left out.

    The order the readings run in is the order the PLEXOS to PyPSA hop runs them in, so a
    generator both hops leave out is left out for the same stated reason.
    """
    reporter = SiennaComponentReporter(recorder, SiennaComponent.THERMAL_STANDARD)
    node = lookups.gen_to_node.get(name)
    if node is None:
        _left_out(reporter, name, PlexosCollection.NODES, None, _NO_NODE_NOTE)
        return None
    if node not in bus_names:
        _left_out(reporter, name, PlexosCollection.NODES, node, _BUSLESS_NOTE)
        return None
    if PlexosProperty.MAX_CAPACITY in lookups.file_backed_properties.get(name, []):
        _left_out(
            reporter, name, PlexosProperty.MAX_CAPACITY, _DATA_FILE, _FILE_BACKED_NOTE, UNIT_MW
        )
        return None
    source = read_source(generator, name, lookups)
    if source.units == 0.0 and not source.is_candidate:
        _left_out(reporter, name, PlexosProperty.UNITS, source.units, _RETIRED_NOTE)
        return None
    if source.p_nom <= 0.0:
        _left_out(
            reporter,
            name,
            PlexosProperty.MAX_CAPACITY,
            None,
            _NO_CAPACITY_NOTE.format(capacity=source.p_nom),
            UNIT_MW,
        )
        return None
    blocked = find_blocked_candidate(source.candidate)
    if blocked is not None:
        reporter.record_skipped(blocked.source, blocked.note)
        return None
    mapping = derive_generator(source, node, lookups)
    target = targets.find(mapping.carrier)
    if target is None:
        reporter.record_skipped(
            SourceValue(PlexosClass.GENERATOR, name, None, None),
            _carrier_note(mapping.carrier, mapping.fuel is not None),
        )
        return None
    if target.sienna_type not in _GENERATOR_TYPES:
        return None
    if has_infeasible_dispatch_range(mapping):
        reporter.record_skipped(
            SourceValue(
                PlexosClass.GENERATOR,
                name,
                mapping.minimum.source_property,
                mapping.minimum.source_value,
            ),
            _INFEASIBLE_NOTE.format(
                minimum=_megawatts(mapping.minimum.p_min_pu, mapping.p_nom),
                ceiling=_megawatts(mapping.availability.static_p_max_pu, mapping.p_nom),
            ),
        )
        return None
    return _Translated(
        mapping=mapping,
        target=target,
        sienna_type=str(target.sienna_type),
        minutes_per_snapshot=lookups.minutes_per_snapshot,
    )


def _left_out(
    reporter: SiennaComponentReporter,
    name: str,
    attribute: str,
    value: Any,
    note: str,
    unit: str | None = None,
) -> None:
    """Record why one generator is left out."""
    reporter.record_skipped(SourceValue(PlexosClass.GENERATOR, name, attribute, value, unit), note)
    return None


def _carrier_note(carrier: str, burns_fuel: bool) -> str:
    concept = "fuel" if burns_fuel else "category"
    return f"{concept}={carrier!r}: {_UNMAPPED_CARRIER_NOTE}"


def _megawatts(per_unit: float, base_power: float) -> float:
    return round(per_unit * base_power, 6)


def _row_for(translated: _Translated, reporter: SiennaComponentReporter) -> dict[str, Any]:
    name = translated.mapping.name
    if translated.sienna_type == SiennaComponent.THERMAL_STANDARD:
        thermal = _derive_thermal(translated)
        reporter.record_mapping(name, thermal)
        return destination_row(thermal, SiennaThermalGeneratorCol.NAME, name)
    renewable = _derive_renewable(translated)
    reporter.record_mapping(name, renewable)
    return destination_row(renewable, SiennaRenewableGeneratorCol.NAME, name)


def _derive_thermal(translated: _Translated) -> _ThermalMapping:
    mapping, target = translated.mapping, translated.target
    return _ThermalMapping(
        name=mapping.name,
        base_power=_base_power(mapping),
        available=Decision.default(True, _AVAILABLE_NOTE),
        status=Decision.default(True, _STATUS_NOTE),
        bus_name=Decision.default(mapping.bus_name, _BUS_NAME_NOTE),
        active_power=_active_power(mapping),
        reactive_power=Decision.default(NO_REACTIVE_POWER, _REACTIVE_POWER_NOTE),
        rating=Decision.default(mapping.availability.static_p_max_pu, _RATING_NOTE),
        active_power_limits=_active_power_limits(mapping),
        reactive_power_limits=Decision.default(None, _REACTIVE_LIMITS_NOTE),
        ramp_limits=_ramp_limits(translated),
        time_limits=_time_limits(translated),
        operation_cost=_thermal_cost(mapping),
        prime_mover_type=_prime_mover(mapping, target),
        fuel_type=_fuel_type(mapping, target),
        must_run=Decision.default(False, _MUST_RUN_NOTE),
        time_at_status=Decision.default(TIME_AT_STATUS_SENTINEL, _TIME_AT_STATUS_NOTE),
    )


def _derive_renewable(translated: _Translated) -> _RenewableMapping:
    mapping, target = translated.mapping, translated.target
    return _RenewableMapping(
        name=mapping.name,
        base_power=_base_power(mapping),
        available=Decision.default(True, _AVAILABLE_NOTE),
        bus_name=Decision.default(mapping.bus_name, _BUS_NAME_NOTE),
        active_power=Decision.default(NO_COST, _ACTIVE_POWER_NOTE),
        reactive_power=Decision.default(NO_REACTIVE_POWER, _REACTIVE_POWER_NOTE),
        rating=Decision.default(mapping.availability.static_p_max_pu, _RATING_NOTE),
        reactive_power_limits=Decision.default(None, _REACTIVE_LIMITS_NOTE),
        power_factor=Decision.default(UNITY_POWER_FACTOR, _POWER_FACTOR_NOTE),
        operation_cost=_renewable_cost(mapping),
        prime_mover_type=_prime_mover(mapping, target),
    )


def _base_power(mapping: GeneratorMapping) -> Decision:
    sources = [
        SourceValue(
            PlexosClass.GENERATOR, mapping.name, PlexosProperty.MAX_CAPACITY, None, UNIT_MW
        ),
        SourceValue(PlexosClass.GENERATOR, mapping.name, PlexosProperty.UNITS, mapping.units),
    ]
    return Decision.derived(mapping.p_nom, sources, _BASE_POWER_DERIVATION)


def _active_power(mapping: GeneratorMapping) -> Decision:
    minimum = mapping.minimum
    megawatts = _megawatts(minimum.p_min_pu, mapping.p_nom)
    if minimum.source_property is None:
        return Decision.default(megawatts, _ACTIVE_POWER_NOTE)
    source = SourceValue(
        PlexosClass.GENERATOR, mapping.name, minimum.source_property, minimum.source_value
    )
    return Decision.derived(megawatts, [source], _ACTIVE_POWER_DERIVATION)


def _active_power_limits(mapping: GeneratorMapping) -> Decision:
    limits = {
        "min": _megawatts(mapping.minimum.p_min_pu, mapping.p_nom),
        "max": _megawatts(mapping.availability.static_p_max_pu, mapping.p_nom),
    }
    sources = [
        SourceValue(PlexosClass.GENERATOR, mapping.name, PlexosProperty.MAX_CAPACITY, None, UNIT_MW)
    ]
    return Decision.derived(limits, sources, _LIMITS_DERIVATION)


def _ramp_limits(translated: _Translated) -> Decision:
    mapping = translated.mapping
    commitment = mapping.unit_commitment
    if commitment is None or commitment.ramp_limit_up is None:
        return Decision.unreported(None)
    up = _rate_per_minute(commitment.ramp_limit_up, translated)
    down = _rate_per_minute(commitment.ramp_limit_down, translated)
    sources = [
        SourceValue(
            PlexosClass.GENERATOR,
            mapping.name,
            PlexosProperty.MAX_RAMP_UP,
            commitment.max_ramp_up,
            UNIT_MW_PER_MINUTE,
        )
    ]
    return Decision.derived({"up": up, "down": down}, sources, _RAMP_DERIVATION)


def _rate_per_minute(per_snapshot: float | None, translated: _Translated) -> float | None:
    """A per-unit-per-snapshot limit read back as the megawatts per minute Sienna states."""
    if per_snapshot is None:
        return None
    return per_snapshot * translated.mapping.p_nom / translated.minutes_per_snapshot


def _time_limits(translated: _Translated) -> Decision:
    mapping = translated.mapping
    commitment = mapping.unit_commitment
    if commitment is None or commitment.min_up_time is None:
        return Decision.unreported(None)
    limits = {
        "up": (commitment.min_up_time or 0.0) * translated.minutes_per_snapshot / _MINUTES_PER_HOUR,
        "down": (commitment.min_down_time or 0.0)
        * translated.minutes_per_snapshot
        / _MINUTES_PER_HOUR,
    }
    sources = [
        SourceValue(
            PlexosClass.GENERATOR,
            mapping.name,
            PlexosProperty.MIN_UP_TIME,
            commitment.min_up_hours,
            UNIT_HOURS,
        )
    ]
    return Decision.derived(limits, sources, _TIME_LIMITS_DERIVATION)


def _thermal_cost(mapping: GeneratorMapping) -> Decision:
    cost = thermal_cost_value(mapping.cost.marginal_cost, _start_up_cost(mapping))
    sources = [
        SourceValue(
            PlexosClass.GENERATOR,
            mapping.name,
            PlexosProperty.VOM_CHARGE,
            mapping.cost.vom,
            UNIT_DOLLARS_PER_MWH,
        )
    ]
    return Decision.derived(cost, sources, _COST_DERIVATION)


def _renewable_cost(mapping: GeneratorMapping) -> Decision:
    cost = renewable_cost_value(mapping.cost.marginal_cost)
    sources = [
        SourceValue(
            PlexosClass.GENERATOR,
            mapping.name,
            PlexosProperty.VOM_CHARGE,
            mapping.cost.vom,
            UNIT_DOLLARS_PER_MWH,
        )
    ]
    return Decision.derived(cost, sources, _COST_DERIVATION)


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


def _record_source_notes(reporter: SiennaComponentReporter, mapping: GeneratorMapping) -> None:
    """The notes that name only what the model states, which every hop out of PLEXOS records."""
    record_generator_source_notes(reporter, decide_generator(mapping))
    record_expansion_notes(reporter, mapping.name, mapping.expansion)


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
        p_nom_extendable=mapping.candidate.is_candidate,
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
    }


def _decided(decision: Decision) -> float | None:
    """A decision's number, or None where the mapping reported nothing for it."""
    if decision.kind is DecisionKind.UNREPORTED or decision.value is None:
        return None
    return float(decision.value)
