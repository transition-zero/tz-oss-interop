"""Turning a derived generator mapping into destination values with their provenance.

Every value the mapping writes into the destination row gets an event, so a reader can
trace each PyPSA field back to the PLEXOS properties it came from. The two exceptions are
the carbon part of marginal_cost, which is an event on no column, and a p_max_pu that
arrives as a profile, which is a second event on a column already written.
"""

from __future__ import annotations

from dataclasses import dataclass

from interop.plugins.shared.constants import (
    UNIT_DOLLARS,
    UNIT_DOLLARS_PER_GJ,
    UNIT_DOLLARS_PER_MWH,
    UNIT_DOLLARS_PER_TONNE,
    UNIT_GJ,
    UNIT_GJ_PER_MWH,
    UNIT_HOURS,
    UNIT_KG_PER_GJ,
    UNIT_MW,
    UNIT_MW_PER_MINUTE,
    UNIT_PER_UNIT_PER_HOUR,
    UNIT_SNAPSHOTS,
)
from interop.plugins.shared.plexos_constants import (
    PlexosClass,
    PlexosCollection,
    PlexosObjectCol,
    PlexosProperty,
)
from interop.plugins.shared.plexos_pypsa_translations._generator_derivation import (
    CarbonTerm,
    GeneratorMapping,
    StartFuel,
    ThermalCostTerms,
    UnitCommitment,
)
from interop.plugins.shared.plexos_pypsa_translations.constants import (
    FULL_AVAILABILITY,
    MARGINAL_COST_CARBON_TERM,
    START_UP_COST_FUEL_TERM,
)
from interop.plugins.shared.plexos_pypsa_translations.decisions import (
    ComponentReporter,
    Decision,
    MappedColumns,
    SourceValue,
    declares,
    maps_to,
)
from interop.plugins.shared.pypsa_constants import PyPSAComponent, PyPSAGeneratorCol

_BUS_DERIVATION = "the Nodes membership names the bus"
_P_NOM_DERIVATION = "Max Capacity x Units"
_P_NOM_RATING_DERIVATION = "Rating above Max Capacity x Units, so the Rating is the capacity"
_THERMAL_CARRIER_DERIVATION = "the fuel names the carrier"
_CATEGORY_CARRIER_DERIVATION = "the category names the carrier"
_P_MIN_PU_DERIVATION = "the first available minimum-generation property, converted to per unit"
_P_MIN_PU_NEGLIGIBLE_DERIVATION = (
    "a minimum below 0.001 of the unit's own capacity constrains no dispatch, so it is "
    "written as zero"
)
_P_MIN_PU_NOTE = "no Min Stable Level, so the generator can turn down to zero"
_THERMAL_COST_DERIVATION = "fuel price x heat rate + VO&M charge + the carbon term"
_DATED_COST_DERIVATION = (
    "fuel price x heat rate + VO&M charge + the carbon term, where the price is the mean "
    "of the fuel's own dated price series"
)
_FLAT_COST_DERIVATION = "a non-fuel generator carries only its VO&M charge"
_CARBON_DERIVATION = "carbon price x production rate x heat rate / 1000"
_COMMITTABLE_DERIVATION = (
    "a generator burning a fuel or holding a minimum output is unit-committed; others are not"
)
_RAMP_DERIVATION = "Max Ramp x snapshot minutes / p_nom, capped at 1"
_TIME_LIMIT_DERIVATION = "hours -> snapshots at the network resolution"
_START_FUEL_DERIVATION = "Offtake at Start x the fuel's price"
_START_UP_STATED_DERIVATION = "the cold-start band of Start Cost"
_START_UP_FUEL_DERIVATION = (
    "the start fuel prices the start, since the generator states no Start Cost"
)
_START_UP_UNPRICED_NOTE = (
    "the generator states neither a Start Cost nor a start fuel, so nothing prices its "
    "starts and PyPSA reads a start as free"
)
_DISCARDED_START_FUEL_NOTE = (
    "the generator states its own Start Cost, which has already priced whatever fuel a "
    "start burns, so the two are not added together"
)
_P_MAX_PU_DERATE_DERIVATION = "an outage or static rating derate"
_P_MAX_PU_NOTE = "no rating or outage derate, so the generator can run at full output"
_UP_TIME_BEFORE_NOTE = (
    "PLEXOS carries no prior on-time, so the generator starts the horizon just off"
)
_SHUT_DOWN_NOTE = "PLEXOS prices only starts, so shutting down is free"
_EFFICIENCY_DERIVATION = "p_nom / (Heat Rate Base + Heat Rate Incr x p_nom) x 3.6"
_DISCARDED_FUEL_NOTE = "a multi-fuel generator keeps its first fuel; this one is discarded"
_EXTENDABLE_NOTE = "v1 translates a dispatch model, so capacity is fixed"
_NOT_EXTENDABLE = False

# The value a p_max_pu event carries when the ceiling varies over the horizon.
_PROFILE = "profile"

_P_MAX_PU_COLUMN = MappedColumns((PyPSAGeneratorCol.P_MAX_PU,))
# The carbon adder is an event on no destination column: marginal_cost cites it as a
# source, so it is named here rather than left implicit inside that one derivation.
_CARBON_TERM_COLUMN = MappedColumns((MARGINAL_COST_CARBON_TERM,), UNIT_DOLLARS_PER_MWH)
# What a start's fuel costs, on no destination column for the same reason.
_START_FUEL_TERM_COLUMN = MappedColumns((START_UP_COST_FUEL_TERM,), UNIT_DOLLARS)


@dataclass(frozen=True)
class GeneratorDecisions:
    """One PyPSA Generator: each destination value, where it came from, and what it fills."""

    name: str
    profile: Decision | None
    carbon: Decision | None
    start_fuel: Decision | None
    unpriced_start: bool
    discarded_start_fuel: bool
    discarded_fuels: tuple[str, ...]
    bus: Decision = maps_to(PyPSAGeneratorCol.BUS)
    carrier: Decision = maps_to(PyPSAGeneratorCol.CARRIER)
    p_nom: Decision = maps_to(PyPSAGeneratorCol.P_NOM, unit=UNIT_MW)
    p_min_pu: Decision = maps_to(PyPSAGeneratorCol.P_MIN_PU)
    p_max_pu: Decision = declares(_P_MAX_PU_COLUMN)
    marginal_cost: Decision = maps_to(PyPSAGeneratorCol.MARGINAL_COST, unit=UNIT_DOLLARS_PER_MWH)
    efficiency: Decision = maps_to(PyPSAGeneratorCol.EFFICIENCY)
    committable: Decision = maps_to(PyPSAGeneratorCol.COMMITTABLE)
    ramp_limit_up: Decision = maps_to(PyPSAGeneratorCol.RAMP_LIMIT_UP, unit=UNIT_PER_UNIT_PER_HOUR)
    ramp_limit_down: Decision = maps_to(
        PyPSAGeneratorCol.RAMP_LIMIT_DOWN, unit=UNIT_PER_UNIT_PER_HOUR
    )
    min_up_time: Decision = maps_to(PyPSAGeneratorCol.MIN_UP_TIME, unit=UNIT_SNAPSHOTS)
    min_down_time: Decision = maps_to(PyPSAGeneratorCol.MIN_DOWN_TIME, unit=UNIT_SNAPSHOTS)
    up_time_before: Decision = maps_to(PyPSAGeneratorCol.UP_TIME_BEFORE, unit=UNIT_SNAPSHOTS)
    start_up_cost: Decision = maps_to(PyPSAGeneratorCol.START_UP_COST, unit=UNIT_DOLLARS)
    shut_down_cost: Decision = maps_to(PyPSAGeneratorCol.SHUT_DOWN_COST, unit=UNIT_DOLLARS)
    p_nom_extendable: Decision = maps_to(PyPSAGeneratorCol.P_NOM_EXTENDABLE)


def decide_generator(mapping: GeneratorMapping) -> GeneratorDecisions:
    """State every destination value of one generator together with its provenance."""
    commitment = _commitment_decisions(mapping)
    return GeneratorDecisions(
        name=mapping.name,
        profile=_profile(mapping),
        carbon=_carbon(mapping),
        start_fuel=_start_fuel(mapping),
        unpriced_start=_has_unpriced_start(mapping),
        discarded_start_fuel=_has_discarded_start_fuel(mapping),
        discarded_fuels=mapping.discarded_fuels,
        bus=_bus(mapping),
        carrier=_carrier(mapping),
        p_nom=_p_nom(mapping),
        p_min_pu=_p_min_pu(mapping),
        p_max_pu=_p_max_pu(mapping),
        marginal_cost=_marginal_cost(mapping),
        efficiency=_efficiency(mapping),
        committable=Decision.computed(mapping.is_committable, _COMMITTABLE_DERIVATION),
        ramp_limit_up=commitment.ramp_up,
        ramp_limit_down=commitment.ramp_down,
        min_up_time=commitment.min_up_time,
        min_down_time=commitment.min_down_time,
        up_time_before=commitment.up_time_before,
        start_up_cost=commitment.start_up_cost,
        shut_down_cost=commitment.shut_down_cost,
        p_nom_extendable=Decision.default(_NOT_EXTENDABLE, _EXTENDABLE_NOTE),
    )


def record_generator(reporter: ComponentReporter, decisions: GeneratorDecisions) -> None:
    """The carbon and start-fuel terms precede the values that cite them as sources."""
    name = decisions.name
    if decisions.carbon is not None:
        reporter.record(name, _CARBON_TERM_COLUMN, decisions.carbon)
    if decisions.start_fuel is not None:
        reporter.record(name, _START_FUEL_TERM_COLUMN, decisions.start_fuel)
    reporter.record_mapping(name, decisions)
    if decisions.profile is not None:
        reporter.record(name, _P_MAX_PU_COLUMN, decisions.profile)
    if decisions.unpriced_start:
        reporter.record_dropped(
            _source(name, PlexosProperty.START_COST, None, UNIT_DOLLARS), _START_UP_UNPRICED_NOTE
        )
    if decisions.discarded_start_fuel:
        reporter.record_dropped(
            _source(name, PlexosProperty.OFFTAKE_AT_START, None, UNIT_GJ),
            _DISCARDED_START_FUEL_NOTE,
        )
    for fuel_name in decisions.discarded_fuels:
        reporter.record_skipped(
            _source(name, PlexosCollection.FUELS, fuel_name), _DISCARDED_FUEL_NOTE
        )


def _source(name: str, attribute: str, value: object, unit: str | None = None) -> SourceValue:
    return SourceValue(PlexosClass.GENERATOR, name, attribute, value, unit)


def _bus(mapping: GeneratorMapping) -> Decision:
    source = _source(mapping.name, PlexosCollection.NODES, mapping.bus_name)
    return Decision.derived(mapping.bus_name, [source], _BUS_DERIVATION)


def _carrier(mapping: GeneratorMapping) -> Decision:
    if mapping.fuel is None:
        source = _source(mapping.name, PlexosObjectCol.CATEGORY, mapping.category)
        return Decision.derived(mapping.carrier, [source], _CATEGORY_CARRIER_DERIVATION)
    source = _source(mapping.name, PlexosCollection.FUELS, mapping.fuel.name)
    return Decision.derived(mapping.carrier, [source], _THERMAL_CARRIER_DERIVATION)


def _p_nom(mapping: GeneratorMapping) -> Decision:
    nameplate = [
        _source(mapping.name, PlexosProperty.MAX_CAPACITY, mapping.max_capacity, UNIT_MW),
        _source(mapping.name, PlexosProperty.UNITS, mapping.units),
    ]
    capacity = mapping.rating_as_capacity
    if capacity is None:
        return Decision.derived(mapping.p_nom, nameplate, _P_NOM_DERIVATION)
    rating = _source(mapping.name, PlexosProperty.RATING, capacity, UNIT_MW)
    return Decision.derived(mapping.p_nom, [rating, *nameplate], _P_NOM_RATING_DERIVATION)


def _p_min_pu(mapping: GeneratorMapping) -> Decision:
    minimum = mapping.minimum
    if minimum.source_property is None or minimum.source_value is None:
        return Decision.default(minimum.p_min_pu, _P_MIN_PU_NOTE)
    source = _source(mapping.name, minimum.source_property, minimum.source_value)
    derivation = _P_MIN_PU_NEGLIGIBLE_DERIVATION if minimum.is_negligible else _P_MIN_PU_DERIVATION
    return Decision.derived(minimum.p_min_pu, [source], derivation)


def _p_max_pu(mapping: GeneratorMapping) -> Decision:
    """The static ceiling the row carries; a profile is reported on top of it."""
    static = mapping.availability.static_p_max_pu
    if mapping.availability.profile is not None:
        return Decision.unreported(static)
    if static != FULL_AVAILABILITY:
        return Decision.computed(static, _P_MAX_PU_DERATE_DERIVATION)
    return Decision.default(static, _P_MAX_PU_NOTE)


def _profile(mapping: GeneratorMapping) -> Decision | None:
    """A ceiling that varies over the horizon, so the row's value is not what it reports."""
    profile = mapping.availability.profile
    if profile is None:
        return None
    source = _source(mapping.name, profile.property_name, _PROFILE)
    return Decision.derived(
        _PROFILE,
        [source],
        f"the file-backed availability profile x {profile.scale}, converting it to per unit "
        "and applying any outage derate",
    )


def _marginal_cost(mapping: GeneratorMapping) -> Decision:
    terms = mapping.cost.thermal_terms
    if terms is None:
        source = _source(
            mapping.name, PlexosProperty.VOM_CHARGE, mapping.cost.vom, UNIT_DOLLARS_PER_MWH
        )
        return Decision.derived(mapping.cost.marginal_cost, [source], _FLAT_COST_DERIVATION)
    derivation = _DATED_COST_DERIVATION if terms.is_priced_by_date else _THERMAL_COST_DERIVATION
    return Decision.derived(
        terms.marginal_cost, _thermal_cost_sources(mapping.name, terms), derivation
    )


def _thermal_cost_sources(name: str, terms: ThermalCostTerms) -> list[SourceValue]:
    sources = [
        SourceValue(
            PlexosClass.FUEL,
            terms.fuel_name,
            PlexosProperty.PRICE,
            terms.fuel_price,
            UNIT_DOLLARS_PER_GJ,
        ),
        _source(name, terms.heat_rate_property, terms.heat_rate, UNIT_GJ_PER_MWH),
        _source(name, PlexosProperty.VOM_CHARGE, terms.vom, UNIT_DOLLARS_PER_MWH),
    ]
    if terms.carbon is not None:
        sources.append(
            SourceValue.derived_earlier(
                PyPSAComponent.GENERATOR,
                name,
                MARGINAL_COST_CARBON_TERM,
                terms.carbon.adder,
                UNIT_DOLLARS_PER_MWH,
            )
        )
    return sources


def _carbon(mapping: GeneratorMapping) -> Decision | None:
    """The carbon part of marginal_cost, recorded as the value the total derives from."""
    terms = mapping.cost.thermal_terms
    if terms is None or terms.carbon is None:
        return None
    return Decision.derived(
        terms.carbon.adder,
        [*_emission_sources(terms.carbon), _heat_rate_source(mapping.name, terms)],
        _CARBON_DERIVATION,
    )


def _emission_sources(carbon: CarbonTerm) -> list[SourceValue]:
    return [
        SourceValue(
            PlexosClass.EMISSION,
            carbon.emission_name,
            PlexosProperty.PRICE,
            carbon.price,
            UNIT_DOLLARS_PER_TONNE,
        ),
        SourceValue(
            PlexosClass.EMISSION,
            carbon.emission_name,
            PlexosProperty.PRODUCTION_RATE,
            carbon.production_rate,
            UNIT_KG_PER_GJ,
        ),
    ]


def _heat_rate_source(name: str, terms: ThermalCostTerms) -> SourceValue:
    return _source(name, terms.heat_rate_property, terms.heat_rate, UNIT_GJ_PER_MWH)


def _efficiency(mapping: GeneratorMapping) -> Decision:
    if mapping.cost.thermal_terms is None or mapping.efficiency is None:
        return Decision.unreported(mapping.efficiency)
    return Decision.computed(mapping.efficiency, _EFFICIENCY_DERIVATION)


@dataclass(frozen=True)
class _CommitmentDecisions:
    """The seven columns only a unit-committed generator fills."""

    ramp_up: Decision
    ramp_down: Decision
    min_up_time: Decision
    min_down_time: Decision
    up_time_before: Decision
    start_up_cost: Decision
    shut_down_cost: Decision


def _commitment_decisions(mapping: GeneratorMapping) -> _CommitmentDecisions:
    commitment = mapping.unit_commitment
    if commitment is None:
        return _CommitmentDecisions(*(Decision.unreported(None) for _ in range(7)))
    name = mapping.name
    return _CommitmentDecisions(
        ramp_up=_ramp_limit(
            name, PlexosProperty.MAX_RAMP_UP, commitment.max_ramp_up, commitment.ramp_limit_up
        ),
        ramp_down=_ramp_limit(
            name, PlexosProperty.MAX_RAMP_DOWN, commitment.max_ramp_down, commitment.ramp_limit_down
        ),
        min_up_time=_time_limit(
            name, PlexosProperty.MIN_UP_TIME, commitment.min_up_hours, commitment.min_up_time
        ),
        min_down_time=_time_limit(
            name, PlexosProperty.MIN_DOWN_TIME, commitment.min_down_hours, commitment.min_down_time
        ),
        up_time_before=Decision.default(commitment.up_time_before, _UP_TIME_BEFORE_NOTE),
        start_up_cost=_start_up_cost(name, commitment),
        shut_down_cost=Decision.default(commitment.shut_down_cost, _SHUT_DOWN_NOTE),
    )


def _ramp_limit(
    name: str, plexos_property: str, max_ramp: float | None, ramp_limit: float | None
) -> Decision:
    """PLEXOS may set one direction and not the other, so each is its own decision."""
    if max_ramp is None or ramp_limit is None:
        return Decision.unreported(ramp_limit)
    source = _source(name, plexos_property, max_ramp, UNIT_MW_PER_MINUTE)
    return Decision.derived(ramp_limit, [source], _RAMP_DERIVATION)


def _time_limit(
    name: str, plexos_property: str, hours: float | None, snapshots: float | None
) -> Decision:
    if hours is None or snapshots is None:
        return Decision.unreported(snapshots)
    source = _source(name, plexos_property, hours, UNIT_HOURS)
    return Decision.derived(snapshots, [source], _TIME_LIMIT_DERIVATION)


def _start_up_cost(name: str, commitment: UnitCommitment) -> Decision:
    """PLEXOS prices a start as money on the generator, or as the fuel a start burns."""
    stated = commitment.stated_start_cost
    if stated is not None:
        source = _source(name, PlexosProperty.START_COST, stated, UNIT_DOLLARS)
        return Decision.derived(stated, [source], _START_UP_STATED_DERIVATION)
    start_fuel = commitment.start_fuel
    if start_fuel is None:
        return Decision.unreported(None)
    source = SourceValue.derived_earlier(
        PyPSAComponent.GENERATOR, name, START_UP_COST_FUEL_TERM, start_fuel.cost, UNIT_DOLLARS
    )
    return Decision.derived(start_fuel.cost, [source], _START_UP_FUEL_DERIVATION)


def _start_fuel(mapping: GeneratorMapping) -> Decision | None:
    """What a start's fuel costs, recorded as the value start_up_cost derives from."""
    start_fuel = _priced_start_fuel(mapping)
    if start_fuel is None:
        return None
    return Decision.derived(
        start_fuel.cost,
        [
            _source(mapping.name, PlexosProperty.OFFTAKE_AT_START, start_fuel.offtake, UNIT_GJ),
            SourceValue(
                PlexosClass.FUEL,
                start_fuel.name,
                PlexosProperty.PRICE,
                start_fuel.price,
                UNIT_DOLLARS_PER_GJ,
            ),
        ],
        _START_FUEL_DERIVATION,
    )


def _priced_start_fuel(mapping: GeneratorMapping) -> StartFuel | None:
    """The start fuel where it is what prices the start, rather than a Start Cost."""
    commitment = mapping.unit_commitment
    if commitment is None or commitment.stated_start_cost is not None:
        return None
    return commitment.start_fuel


def _has_unpriced_start(mapping: GeneratorMapping) -> bool:
    commitment = mapping.unit_commitment
    return commitment is not None and commitment.start_up_cost is None


def _has_discarded_start_fuel(mapping: GeneratorMapping) -> bool:
    commitment = mapping.unit_commitment
    return (
        commitment is not None
        and commitment.stated_start_cost is not None
        and commitment.start_fuel is not None
    )
