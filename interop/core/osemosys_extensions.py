"""The sidecar records of the concepts that OSeMOSYS states and no other framework holds.

``interop/core/extensions.py`` re-exports each model, so a reader imports every record model
from one place.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from interop.core.extension_records import (
    ByFuel,
    ByPollutant,
    ByYear,
    ExpansionExtension,
    ExtensionRecord,
    FlagByYear,
)


class OperatingMode(BaseModel):
    """One OSeMOSYS operating mode of a technology, for each MWh of the activity of the mode.

    A Sienna component and a PyPSA component each run one mode, so the values of every other
    mode, and the bounds of every mode, have no field there.
    """

    model_config = ConfigDict(extra="forbid")

    mode: str  # OSeMOSYS MODE_OF_OPERATION
    variable_cost: float | None = None  # $/MWh of activity; OSeMOSYS VariableCost.
    # MWh of each fuel for each MWh of activity; OSeMOSYS InputActivityRatio.
    input_ratios: ByFuel | None = None
    # MWh of each fuel for each MWh of activity; OSeMOSYS OutputActivityRatio.
    output_ratios: ByFuel | None = None
    # t for each MWh of activity; OSeMOSYS EmissionActivityRatio.
    emission_rates: ByPollutant | None = None
    # MWh of activity in each year; OSeMOSYS TechnologyActivityByModeUpperLimit.
    activity_max: ByYear | None = None
    # MWh of activity in each year; OSeMOSYS TechnologyActivityByModeLowerLimit.
    activity_min: ByYear | None = None
    # Per unit: the most the activity can fall from the year before; OSeMOSYS
    # TechnologyActivityDecreaseByModeLimit.
    activity_decrease_max: ByYear | None = None


class TechnologyLimits(BaseModel):
    """The yearly limits on the capacity and the activity of a technology.

    ``ActivityExtension`` and ``TechnologyExtension`` both state them, so each field has one
    shape whichever kind holds it.
    """

    model_config = ConfigDict(extra="forbid")

    # MWh in each year of electricity or of the fuel that rates the component; PyPSA
    # Generator.e_sum_min and e_sum_max, keyed by the investment period; OSeMOSYS
    # TotalTechnologyAnnualActivityLowerLimit and UpperLimit.
    e_sum_min: ByYear | None = None
    e_sum_max: ByYear | None = None
    # MWh of electricity over the model period; PyPSA Generator.e_sum_min and e_sum_max over
    # the horizon; OSeMOSYS TotalTechnologyModelPeriodActivityLowerLimit and UpperLimit.
    e_sum_min_horizon: float | None = None
    e_sum_max_horizon: float | None = None
    # MW of new capacity in a year; PyPSA states it as Carrier.max_growth; OSeMOSYS
    # TotalAnnualMaxCapacityInvestment.
    max_growth: ByYear | None = None
    # MW of new capacity in a year; no PyPSA field; OSeMOSYS TotalAnnualMinCapacityInvestment.
    min_growth: ByYear | None = None
    # Per unit of the total capacity of the year before; no PyPSA field, because
    # Carrier.max_relative_growth weighs the new capacity of the period before; OSeMOSYS
    # CapacityAdditionalMaxGrowthRate.
    max_growth_rate: ByYear | None = None
    # Per unit of the total capacity of the year before; no PyPSA field; OSeMOSYS
    # CapacityAdditionalMinGrowthRate.
    min_growth_rate: ByYear | None = None
    # MW that a year can add above its relative growth; no PyPSA field; OSeMOSYS
    # CapacityAdditionalMaxFloor.
    max_growth_floor: ByYear | None = None
    # MWh of activity that one MW runs in a year, 8760 where the units of the model agree.
    # No PyPSA field; OSeMOSYS CapacityToActivityUnit.
    capacity_to_activity_unit: float | None = None


class ActivityExtension(TechnologyLimits, ExpansionExtension):
    """What a technology states about its energy, its growth and its modes. OSeMOSYS only."""

    # Per unit of a whole year at full capacity; no PyPSA field; OSeMOSYS
    # TotalAnnualMinCapacityFactor.
    capacity_factor_min: float | None = None
    # Per unit of the production of each fuel; no PyPSA field; OSeMOSYS
    # TechnologyMinProductionTarget.
    production_share_min: ByFuel | None = None
    # Per unit of the production of each fuel; no PyPSA field; OSeMOSYS
    # TechnologyMaxProductionTarget.
    production_share_max: ByFuel | None = None
    # Each mode whose values the component does not run; no PyPSA field.
    operating_modes: list[OperatingMode] | None = None


class RepresentativePeriodExtension(ExtensionRecord):
    """A span of consecutive hours of the series, and how many times it occurs in the year.

    The first hour, the length and the weight are required, because a span means nothing
    without them. Their values can still be out of range, which the reader of the span checks.
    """

    # The timestamp of the first hour of the span, which the JSON states in ISO 8601.
    first_timestamp: datetime
    hours: int
    # How many times the span occurs in the year.
    weight: float
    # OSeMOSYS SEASON and DAYTYPE, absent for a span of one timeslice hour.
    season: str | None = None
    day_type: str | None = None
    # Days of the day type in one week of the season; OSeMOSYS DaysInDayType.
    days_in_day_type: float | None = None


class TechnologyExtension(TechnologyLimits, ExtensionRecord):
    """The values of a portfolio technology. A yearly value is keyed by the year.

    PyPSA keys a value of a multi-period network by its investment period, which is the year.
    The fields take the PyPSA names, such as overnight_cost and fom_cost, where the older
    fields of the other kinds keep the names that they had before, such as
    overnight_cost_per_mw.
    """

    # $/MW of electricity; PyPSA Generator.overnight_cost; OSeMOSYS CapitalCost.
    overnight_cost: ByYear | None = None
    # $/MWh of energy capacity; PyPSA states it as Store.overnight_cost; OSeMOSYS
    # CapitalCostStorage.
    energy_overnight_cost: ByYear | None = None
    # $/MW/yr; PyPSA Generator.fom_cost; OSeMOSYS FixedCost.
    fom_cost: ByYear | None = None
    # $/MWh, with the fuel cost and the emission penalty; PyPSA Generator.marginal_cost.
    marginal_cost: ByYear | None = None
    # MW that already runs; PyPSA Generator.p_nom; OSeMOSYS ResidualCapacity.
    p_nom: ByYear | None = None
    # MW of total capacity; PyPSA Generator.p_nom_min and p_nom_max; OSeMOSYS
    # TotalAnnualMinCapacity and TotalAnnualMaxCapacity.
    p_nom_min: ByYear | None = None
    p_nom_max: ByYear | None = None


class ConversionExtension(ActivityExtension):
    """A technology or a trade route that moves or converts energy, or takes it out of the model.

    A bus of electricity is its location. A bus of another fuel, and each end of an OSeMOSYS
    trade route, is `<region>/<fuel>`, because a fuel balances in a region.
    """

    carrier: str | None = None  # PyPSA Link.carrier; the OSeMOSYS category of the technology
    bus0: str | None = None  # PyPSA Link.bus0: the bus of the energy that goes in
    # PyPSA Link.bus1: the bus of the energy that comes out, absent for an export.
    bus1: str | None = None
    # PyPSA Link.bus2 and Link.efficiency2, Link.bus3 and Link.efficiency3: a third and a fourth
    # fuel, with a negative efficiency for a fuel that goes in.
    bus2: str | None = None
    efficiency2: float | None = None
    bus3: str | None = None
    efficiency3: float | None = None
    # MW in at bus0; PyPSA Link.p_nom; OSeMOSYS ResidualCapacity × the input ratio.
    p_nom: float | None = None
    # Per unit: energy out at bus1 for each MWh in at bus0; PyPSA Link.efficiency.
    efficiency: float | None = None
    # $/MWh in at bus0; PyPSA Link.marginal_cost; OSeMOSYS VariableCost.
    marginal_cost: float | None = None
    # PyPSA Link.p_nom_extendable: OSeMOSYS adds the capacity that the link needs at no cost.
    p_nom_extendable: bool | None = None
    # t for each MWh in at bus0, from OSeMOSYS EmissionActivityRatio, as PyPSA states
    # Carrier.co2_emissions instead.
    emission_rates_t_per_mwh: ByPollutant | None = None
    # Per unit of p_nom; PyPSA Link.p_max_pu; OSeMOSYS AvailabilityFactor.
    p_max_pu: float | None = None
    # The fuel that goes in and the fuel that comes out; no PyPSA field, as PyPSA states a fuel
    # by its bus.
    input_fuel: str | None = None
    output_fuel: str | None = None
    # PyPSA Link.active, keyed by the investment period; OSeMOSYS TradeRoute.
    active: FlagByYear | None = None
