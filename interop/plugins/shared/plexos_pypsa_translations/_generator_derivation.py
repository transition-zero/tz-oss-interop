"""Deriving one PyPSA generator's values from one staged PLEXOS Generator.

PLEXOS carries every technology in one Generator class, so what a generator *is* comes
from what it carries: a named fuel burnt at a heat rate makes it thermal, which fixes
its carrier, its marginal cost, and whether it is unit-committed. Everything else takes
its carrier from its category and its cost from VO&M alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from interop.plugins.shared.plexos_constants import (
    PlexosObjectCol,
    PlexosProperty,
)
from interop.plugins.shared.plexos_pypsa_translations._generator_lookups import Lookups
from interop.plugins.shared.plexos_pypsa_translations.constants import (
    DEFAULT_P_MIN_PU,
    DEFAULT_SHUT_DOWN_COST,
    DEFAULT_UNITS,
    DEFAULT_UP_TIME_BEFORE,
    FULL_AVAILABILITY,
    MAX_RAMP_LIMIT_PU,
    NEGLIGIBLE_P_MIN_PU,
    PERCENT,
)


@dataclass(frozen=True)
class CarbonTerm:
    """The priced Emission of a thermal generator's fuel, and the $/MWh it adds."""

    emission_name: str
    price: float
    production_rate: float
    adder: float


@dataclass(frozen=True)
class ThermalCostTerms:
    """Every term behind one thermal generator's marginal cost, and the total they make.

    ``carbon`` is null where the fuel carries no priced Emission.
    """

    fuel_name: str
    fuel_price: float
    is_priced_by_date: bool
    heat_rate: float
    heat_rate_property: str
    vom: float
    carbon: CarbonTerm | None
    marginal_cost: float

    @property
    def cost_without_fuel(self) -> float:
        """What the generator costs per MWh before its fuel: operation, and any carbon."""
        return self.marginal_cost - self.fuel_price * self.heat_rate


# The carbon adder is per tonne but the emission rate is per kilogram.
_KG_PER_TONNE = 1000.0
# PLEXOS ramps are MW per minute; PyPSA wants per unit of p_nom per hour.
_MINUTES_PER_HOUR = 60.0
# 1 MWh is 3.6 GJ, converting a heat rate (GJ/MWh) into a dimensionless efficiency.
_GJ_PER_MWH = 3.6

# The heat rates that drive marginal cost, in preference order.
_HEAT_RATE_PROPERTIES = (PlexosProperty.HEAT_RATE_INCR, PlexosProperty.HEAT_RATE)

# The minimum-generation properties, in preference order. Min Stable Factor is a
# percentage; the other two are MW.
_MIN_STABLE_MEGAWATT_PROPERTIES = (PlexosProperty.MIN_STABLE_LEVEL, PlexosProperty.MIN_PUMP_LOAD)


@dataclass(frozen=True)
class SourceGenerator:
    """One staged PLEXOS Generator: what its object row and its properties hold."""

    name: str
    category: str
    units: float
    props: dict[str, float]
    max_capacity: float

    @property
    def nameplate(self) -> float:
        return self.max_capacity * self.units

    @property
    def rating_as_capacity(self) -> float | None:
        """A Rating above the nameplate replaces Max Capacity rather than derating it."""
        rating = _optional(self.props, PlexosProperty.RATING)
        return rating if rating is not None and rating > self.nameplate else None

    @property
    def p_nom(self) -> float:
        capacity = self.rating_as_capacity
        return self.nameplate if capacity is None else capacity


def read_source(generator: dict[str, Any], name: str, lookups: Lookups) -> SourceGenerator:
    props = lookups.gen_props.get(name, {})
    return SourceGenerator(
        name=name,
        category=generator.get(PlexosObjectCol.CATEGORY) or "",
        units=_value(props, PlexosProperty.UNITS, DEFAULT_UNITS),
        props=props,
        max_capacity=_rated_capacity(name, props, lookups),
    )


def _rated_capacity(name: str, props: dict[str, float], lookups: Lookups) -> float:
    """A Max Capacity written as a share of a shared profile has no meaningful static value,
    and a generator whose capacity is carried entirely by its Rating profile has none at all.
    """
    peak = lookups.capacity_peaks.get(name)
    if peak is not None:
        return peak
    static = _value(props, PlexosProperty.MAX_CAPACITY, 0.0)
    if static:
        return static
    return lookups.profile_peaks[PlexosProperty.RATING].get(name, static)


@dataclass(frozen=True)
class GeneratorMapping:
    """Values derived from one PLEXOS Generator, before events and the output row.

    ``fuel`` is the thermal/non-thermal distinction: a generator burning a named fuel at
    a heat rate is thermal, is unit-committed, and prices that fuel into its marginal
    cost. Everything else takes its carrier from its category and its cost from VO&M.
    """

    name: str
    bus_name: str
    category: str
    carrier: str
    fuel: FuelUse | None
    discarded_fuels: tuple[str, ...]
    max_capacity: float
    units: float
    p_nom: float
    rating_as_capacity: float | None
    minimum: MinimumGeneration
    availability: Availability
    cost: Cost
    efficiency: float | None
    unit_commitment: UnitCommitment | None

    @property
    def is_committable(self) -> bool:
        return self.unit_commitment is not None


def has_infeasible_dispatch_range(mapping: GeneratorMapping) -> bool:
    """Whether the minimum output sits above the ceiling, which PyPSA cannot dispatch.

    A profile-backed ceiling varies over the horizon, so only a static one can be judged
    here.
    """
    return (
        mapping.availability.profile is None
        and mapping.minimum.p_min_pu > mapping.availability.static_p_max_pu
    )


def derive_generator(source: SourceGenerator, node: str, lookups: Lookups) -> GeneratorMapping:
    fuels = lookups.gen_fuels.get(source.name, [])
    fuel = _fuel_use(source, fuels[0] if fuels else None, lookups)
    availability = _availability(source, lookups.availability_profiles.get(source.name))
    minimum = _floor_negligible(
        _cap_at_availability(_minimum_generation(source), availability, source, lookups)
    )
    return GeneratorMapping(
        name=source.name,
        bus_name=node,
        category=source.category,
        carrier=_classify(fuel, source),
        fuel=fuel,
        discarded_fuels=tuple(fuels[1:]),
        max_capacity=source.max_capacity,
        units=source.units,
        p_nom=source.p_nom,
        rating_as_capacity=source.rating_as_capacity,
        minimum=minimum,
        availability=availability,
        cost=_assemble_cost(source.props, fuel),
        efficiency=_efficiency(fuel, source.p_nom),
        unit_commitment=_derive_unit_commitment(source, _start_fuel(source, fuel, lookups), lookups)
        if _commits(fuel, minimum)
        else None,
    )


def _commits(fuel: FuelUse | None, minimum: MinimumGeneration) -> bool:
    """Whether PyPSA has to unit-commit this generator to read the source the way PLEXOS does.

    PLEXOS holds a unit to its minimum stable level only while it is committed, so a
    generator carrying one has to commit or PyPSA binds that minimum in every hour. A
    generator burning a fuel commits whether or not it states a minimum.
    """
    return fuel is not None or minimum.p_min_pu > DEFAULT_P_MIN_PU


@dataclass(frozen=True)
class PricedEmission:
    """The Emission a fuel releases, and the price PLEXOS puts on it."""

    name: str
    price: float


@dataclass(frozen=True)
class FuelUse:
    """The fuel a thermal generator burns and the rate it burns it at.

    A generator has one of these only when it both names a fuel and carries a heat rate;
    that pairing is what makes it thermal. ``price`` is the mean of the fuel's own dated
    series where it has one, so the one number the network carries and the series the sink
    writes beside it say the same thing.
    """

    name: str
    price: float
    is_priced_by_date: bool
    heat_rate: float
    heat_rate_property: str
    heat_rate_base: float
    emission: PricedEmission | None
    production_rate: float | None


@dataclass(frozen=True)
class _FuelPrice:
    """A fuel's price, and whether the model states it as a series of dated bands."""

    value: float
    is_dated: bool


def _read_fuel_price(fuel_name: str, lookups: Lookups) -> _FuelPrice:
    """The mean of a fuel's dated price series, or the one scalar the model states."""
    dated = lookups.dated_fuel_prices.get(fuel_name)
    if dated is not None:
        return _FuelPrice(dated, is_dated=True)
    props = lookups.fuel_props.get(fuel_name, {})
    return _FuelPrice(_value(props, PlexosProperty.PRICE, 0.0), is_dated=False)


def _fuel_use(source: SourceGenerator, fuel_name: str | None, lookups: Lookups) -> FuelUse | None:
    heat_rate = _read_heat_rate(source.props)
    if fuel_name is None or heat_rate is None:
        return None
    fuel_props = lookups.fuel_props.get(fuel_name, {})
    price = _read_fuel_price(fuel_name, lookups)
    return FuelUse(
        name=fuel_name,
        price=price.value,
        is_priced_by_date=price.is_dated,
        heat_rate=heat_rate.value,
        heat_rate_property=heat_rate.property_name,
        heat_rate_base=_value(source.props, PlexosProperty.HEAT_RATE_BASE, 0.0),
        emission=_priced_emission(fuel_name, lookups),
        production_rate=_optional(fuel_props, PlexosProperty.PRODUCTION_RATE),
    )


@dataclass(frozen=True)
class _HeatRate:
    """The heat rate driving marginal cost, and which PLEXOS property supplied it."""

    value: float
    property_name: str


def _read_heat_rate(props: dict[str, float]) -> _HeatRate | None:
    for property_name in _HEAT_RATE_PROPERTIES:
        value = _optional(props, property_name)
        if value is not None:
            return _HeatRate(value, property_name)
    return None


def _priced_emission(fuel_name: str, lookups: Lookups) -> PricedEmission | None:
    emission_name = lookups.fuel_to_emission.get(fuel_name)
    if emission_name is None:
        return None
    price = _optional(lookups.emission_props.get(emission_name, {}), PlexosProperty.PRICE)
    if price is None:
        return None
    return PricedEmission(name=emission_name, price=price)


def _classify(fuel: FuelUse | None, source: SourceGenerator) -> str:
    """The PyPSA carrier, as the model words it: its fuel, or its category where it burns none.

    PyPSA's carrier is free text, so the model's own word for the technology is carried
    across rather than classified onto a vocabulary of ours.
    """
    return fuel.name if fuel is not None else source.category


@dataclass(frozen=True)
class MinimumGeneration:
    """p_min_pu and the PLEXOS property it came from, null where the default applied."""

    p_min_pu: float
    source_property: str | None
    source_value: float | None
    is_negligible: bool = False


def _minimum_generation(source: SourceGenerator) -> MinimumGeneration:
    """p_min_pu from the first present of Min Stable Factor, Level, or Pump Load; else 0."""
    factor = _optional(source.props, PlexosProperty.MIN_STABLE_FACTOR)
    if factor is not None:
        return MinimumGeneration(factor / PERCENT, PlexosProperty.MIN_STABLE_FACTOR, factor)
    for property_name in _MIN_STABLE_MEGAWATT_PROPERTIES:
        megawatts = _optional(source.props, property_name)
        if megawatts is not None and source.p_nom:
            return MinimumGeneration(megawatts / source.p_nom, property_name, megawatts)
    return MinimumGeneration(DEFAULT_P_MIN_PU, None, None)


def _floor_negligible(minimum: MinimumGeneration) -> MinimumGeneration:
    """Runs after the availability cap, which can itself leave a minimum this small."""
    if not 0.0 < minimum.p_min_pu < NEGLIGIBLE_P_MIN_PU:
        return minimum
    return MinimumGeneration(
        DEFAULT_P_MIN_PU, minimum.source_property, minimum.source_value, is_negligible=True
    )


@dataclass(frozen=True)
class AvailabilityProfile:
    """A file-backed availability series and the factor turning its values into per unit."""

    property_name: str
    scale: float


@dataclass(frozen=True)
class Availability:
    """What a generator can produce: a static ceiling, and a profile where one exists."""

    static_p_max_pu: float
    profile: AvailabilityProfile | None


def _cap_at_availability(
    minimum: MinimumGeneration,
    availability: Availability,
    source: SourceGenerator,
    lookups: Lookups,
) -> MinimumGeneration:
    """PLEXOS applies Min Stable Level only while a unit is committed, so without this cap
    an hour of no availability forces output PyPSA cannot meet.
    """
    ceiling = _availability_floor(availability, source.name, lookups)
    if ceiling is None or minimum.p_min_pu <= ceiling:
        return minimum
    return MinimumGeneration(ceiling, minimum.source_property, minimum.source_value)


def _availability_floor(availability: Availability, name: str, lookups: Lookups) -> float | None:
    """The lowest p_max_pu a profile ever reaches, or None where no profile bounds it.

    A generator with no profile is left alone so a minimum above its static ceiling is
    rejected rather than quietly lowered: that is a contradiction in the model, not an
    hour the unit happens to be unavailable.
    """
    if availability.profile is None:
        return None
    trough = lookups.profile_troughs[availability.profile.property_name].get(name)
    return None if trough is None else trough * availability.profile.scale


def _availability(source: SourceGenerator, profile: str | None) -> Availability:
    """Static p_max_pu plus the profile scaling; an outage derates whichever the sink uses."""
    outage = _outage_derate(source)
    if profile is None:
        return Availability(outage * _static_rating_derate(source), None)
    scale = outage * profile_scale(profile, source.p_nom)
    return Availability(outage, AvailabilityProfile(profile, scale))


def profile_scale(profile: str, p_nom: float) -> float:
    """Per unit of p_nom: a Rating profile is MW, a Rating Factor profile a percentage."""
    if profile != PlexosProperty.RATING:
        return 1.0 / PERCENT
    if not p_nom:
        # A generator with no capacity produces nothing, so its MW profile scales to zero.
        return 0.0
    return 1.0 / p_nom


def _outage_derate(source: SourceGenerator) -> float:
    """PLEXOS states Outage Factor as a percentage of the capacity, as it does Rating Factor."""
    factor = _optional(source.props, PlexosProperty.OUTAGE_FACTOR)
    if factor is not None:
        return factor / PERCENT
    rating = _optional(source.props, PlexosProperty.OUTAGE_RATING)
    if rating is not None and source.p_nom:
        return (source.p_nom - rating) / source.p_nom
    return FULL_AVAILABILITY


def _static_rating_derate(source: SourceGenerator) -> float:
    if source.rating_as_capacity is not None:
        return FULL_AVAILABILITY
    rating = _optional(source.props, PlexosProperty.RATING)
    if rating is not None and source.p_nom:
        return rating / source.p_nom
    factor = _optional(source.props, PlexosProperty.RATING_FACTOR)
    if factor is not None:
        return factor / PERCENT
    return FULL_AVAILABILITY


@dataclass(frozen=True)
class Cost:
    """Marginal cost, and the thermal terms behind it where a generator burns fuel."""

    vom: float
    marginal_cost: float
    thermal_terms: ThermalCostTerms | None


def _assemble_cost(props: dict[str, float], fuel: FuelUse | None) -> Cost:
    vom = _value(props, PlexosProperty.VOM_CHARGE, 0.0)
    if fuel is None:
        return Cost(vom=vom, marginal_cost=vom, thermal_terms=None)
    terms = _thermal_cost_terms(fuel, vom)
    return Cost(vom=vom, marginal_cost=terms.marginal_cost, thermal_terms=terms)


def _thermal_cost_terms(fuel: FuelUse, vom: float) -> ThermalCostTerms:
    carbon = _carbon_term(fuel)
    return ThermalCostTerms(
        fuel_name=fuel.name,
        fuel_price=fuel.price,
        is_priced_by_date=fuel.is_priced_by_date,
        heat_rate=fuel.heat_rate,
        heat_rate_property=fuel.heat_rate_property,
        vom=vom,
        carbon=carbon,
        marginal_cost=fuel.price * fuel.heat_rate + vom + (carbon.adder if carbon else 0.0),
    )


def _carbon_term(fuel: FuelUse) -> CarbonTerm | None:
    emission = fuel.emission
    if emission is None or fuel.production_rate is None:
        return None
    adder = emission.price * fuel.production_rate * fuel.heat_rate / _KG_PER_TONNE
    return CarbonTerm(
        emission_name=emission.name,
        price=emission.price,
        production_rate=fuel.production_rate,
        adder=adder,
    )


def _efficiency(fuel: FuelUse | None, p_nom: float) -> float | None:
    if fuel is None or not p_nom:
        return None
    fuel_input = fuel.heat_rate_base + fuel.heat_rate * p_nom
    if not fuel_input:
        return None
    return (p_nom / fuel_input) * _GJ_PER_MWH


@dataclass(frozen=True)
class StartFuel:
    """The fuel a generator burns to start: the gigajoules it takes, and what they cost.

    The fuel is the one the heat rate already uses, so a start is priced the same way the
    generator's own output is.
    """

    name: str
    offtake: float
    price: float

    @property
    def cost(self) -> float:
        return self.offtake * self.price


def _start_fuel(
    source: SourceGenerator, fuel: FuelUse | None, lookups: Lookups
) -> StartFuel | None:
    """What a start burns, priced by the fuel the Start Fuels membership itself names.

    A generator may start on a fuel it does not run on, so the run fuel's price is not
    always the price of a start.
    """
    offtakes = lookups.start_fuel_offtake.get(source.name, {})
    if not offtakes:
        return None
    name = _choose_start_fuel(offtakes, fuel)
    return StartFuel(name, offtakes[name], _read_fuel_price(name, lookups).value)


def _choose_start_fuel(offtakes: dict[str, float], fuel: FuelUse | None) -> str:
    """The fuel the heat rate already uses, or where none of them is it, the hungriest start."""
    if fuel is not None and fuel.name in offtakes:
        return fuel.name
    return max(offtakes, key=lambda name: offtakes[name])


@dataclass(frozen=True)
class UnitCommitment:
    """The commitment limits of a committed generator, each null where PLEXOS set none.

    PLEXOS prices a start in one of two ways, and a model stating both has already priced
    the fuel inside its own ``Start Cost``, so ``start_up_cost`` takes one or the other and
    never their sum.
    """

    max_ramp_up: float | None
    max_ramp_down: float | None
    ramp_limit_up: float | None
    ramp_limit_down: float | None
    min_up_hours: float | None
    min_down_hours: float | None
    min_up_time: float | None
    min_down_time: float | None
    stated_start_cost: float | None
    start_fuel: StartFuel | None
    start_up_cost: float | None
    up_time_before: float
    shut_down_cost: float


def _derive_unit_commitment(
    source: SourceGenerator, start_fuel: StartFuel | None, lookups: Lookups
) -> UnitCommitment:
    minutes = lookups.minutes_per_snapshot
    max_ramp_up = _optional(source.props, PlexosProperty.MAX_RAMP_UP)
    max_ramp_down = _optional(source.props, PlexosProperty.MAX_RAMP_DOWN)
    min_up_hours = _optional(source.props, PlexosProperty.MIN_UP_TIME)
    min_down_hours = _optional(source.props, PlexosProperty.MIN_DOWN_TIME)
    stated_start_cost = _optional(source.props, PlexosProperty.START_COST)
    return UnitCommitment(
        max_ramp_up=max_ramp_up,
        max_ramp_down=max_ramp_down,
        ramp_limit_up=_ramp_limit(max_ramp_up, source.p_nom, minutes),
        ramp_limit_down=_ramp_limit(max_ramp_down, source.p_nom, minutes),
        min_up_hours=min_up_hours,
        min_down_hours=min_down_hours,
        min_up_time=_hours_to_snapshots(min_up_hours, minutes),
        min_down_time=_hours_to_snapshots(min_down_hours, minutes),
        stated_start_cost=stated_start_cost,
        start_fuel=start_fuel,
        start_up_cost=_start_up_cost(stated_start_cost, start_fuel),
        up_time_before=DEFAULT_UP_TIME_BEFORE,
        shut_down_cost=DEFAULT_SHUT_DOWN_COST,
    )


def _start_up_cost(stated: float | None, start_fuel: StartFuel | None) -> float | None:
    if stated is not None:
        return stated
    return start_fuel.cost if start_fuel is not None else None


def _ramp_limit(value_mw_per_min: float | None, p_nom: float, minutes: float) -> float | None:
    """PyPSA holds a ramp as a fraction of p_nom over one snapshot, so it stops at 1."""
    if value_mw_per_min is None or not p_nom:
        return None
    return min(value_mw_per_min * minutes / p_nom, MAX_RAMP_LIMIT_PU)


def _hours_to_snapshots(hours: float | None, minutes: float) -> float | None:
    if hours is None:
        return None
    return float(round(hours * _MINUTES_PER_HOUR / minutes))


def _value(props: dict[str, float], key: str, default: float) -> float:
    value = props.get(key)
    return float(value) if value is not None else default


def _optional(props: dict[str, float], key: str) -> float | None:
    value = props.get(key)
    return float(value) if value is not None else None
