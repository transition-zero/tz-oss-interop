"""The fields of a TZ-format OSeMOSYS model.json, and the raw table of each field.

The table follows the field documentation of tz-osemosys v0.4.1. Each field gives the
OSeMOSYS-style name of its raw table, the set of each nested key level, outermost first, and
the default value that the documentation states.
"""

from __future__ import annotations

from enum import StrEnum
from typing import NamedTuple

from interop.plugins.shared.osemosys_canonical.constants import (
    DAILYTIMEBRACKET,
    DAYTYPE,
    EMISSION,
    FUEL,
    MODE_OF_OPERATION,
    REGION,
    REGIONGROUP,
    SEASON,
    SECOND_REGION,
    STORAGE,
    TECHNOLOGY,
    TIMESLICE,
    YEAR,
)


class TzOwner(StrEnum):
    """The object of a model.json that holds a field; each value is its key in the document."""

    MODEL = "model"
    TIME_DEFINITION = "time_definition"
    REGIONS = "regions"
    REGION_GROUPS = "regionsgroup"
    COMMODITIES = "commodities"
    IMPACTS = "impacts"
    TECHNOLOGIES = "technologies"
    OPERATING_MODES = "operating_modes"
    STORAGE = "storage"
    TRADE = "trade"


class TzField(NamedTuple):
    """One field of an owner; `value_set` names the set whose member the value states, if any."""

    owner: TzOwner
    field: str
    table: str
    nesting: tuple[str, ...]
    default: float | None = None
    value_set: str | None = None


_BY_REGION = (REGION,)
_BY_REGION_YEAR = (REGION, YEAR)
_BY_REGION_YEAR_TIMESLICE = (REGION, YEAR, TIMESLICE)
_BY_REGION_FUEL_YEAR = (REGION, FUEL, YEAR)
_BY_REGION_EMISSION_YEAR = (REGION, EMISSION, YEAR)
_BY_REGION_STORAGE = (REGION, STORAGE)
_BY_REGION_PAIR = (REGION, SECOND_REGION)
_BY_REGION_PAIR_YEAR = (REGION, SECOND_REGION, YEAR)
_BY_REGIONGROUP_YEAR = (REGIONGROUP, YEAR)

# The default that the documentation states for a capital cost and a fixed cost.
_SMALL_COST_DEFAULT = 0.00001

TZ_FIELDS: tuple[TzField, ...] = (
    TzField(TzOwner.MODEL, "depreciation_method", "DepreciationMethod", _BY_REGION, 1.0),
    TzField(TzOwner.MODEL, "discount_rate", "DiscountRate", _BY_REGION, 0.05),
    TzField(TzOwner.MODEL, "cost_of_capital", "DiscountRateIdv", (REGION, TECHNOLOGY)),
    TzField(TzOwner.MODEL, "cost_of_capital_storage", "DiscountRateStorage", _BY_REGION_STORAGE),
    TzField(TzOwner.MODEL, "reserve_margin", "ReserveMargin", _BY_REGION_YEAR, 1.0),
    TzField(TzOwner.MODEL, "renewable_production_target", "REMinProductionTarget", _BY_REGION_YEAR),
    TzField(
        TzOwner.MODEL,
        "region_group_renewable_production_target",
        "RegionGroupREMinProductionTarget",
        _BY_REGIONGROUP_YEAR,
    ),
    TzField(TzOwner.TIME_DEFINITION, "year_split", "YearSplit", (TIMESLICE, YEAR)),
    TzField(TzOwner.TIME_DEFINITION, "day_split", "DaySplit", (DAILYTIMEBRACKET, YEAR)),
    TzField(TzOwner.TIME_DEFINITION, "days_in_day_type", "DaysInDayType", (SEASON, DAYTYPE, YEAR)),
    TzField(
        TzOwner.TIME_DEFINITION,
        "timeslice_in_timebracket",
        "Conversionlh",
        (TIMESLICE,),
        value_set=DAILYTIMEBRACKET,
    ),
    TzField(
        TzOwner.TIME_DEFINITION,
        "timeslice_in_daytype",
        "Conversionld",
        (TIMESLICE,),
        value_set=DAYTYPE,
    ),
    TzField(
        TzOwner.TIME_DEFINITION,
        "timeslice_in_season",
        "Conversionls",
        (TIMESLICE,),
        value_set=SEASON,
    ),
    TzField(
        TzOwner.REGION_GROUPS, "include_in_region_group", "RegionGroupTagRegion", _BY_REGION_YEAR
    ),
    TzField(TzOwner.COMMODITIES, "demand_annual", "SpecifiedAnnualDemand", _BY_REGION_YEAR),
    TzField(
        TzOwner.COMMODITIES, "demand_profile", "SpecifiedDemandProfile", _BY_REGION_YEAR_TIMESLICE
    ),
    TzField(TzOwner.COMMODITIES, "include_in_joint_renewable_target", "RETagFuel", _BY_REGION_YEAR),
    TzField(
        TzOwner.COMMODITIES,
        "include_in_joint_reserve_margin",
        "ReserveMarginTagFuel",
        _BY_REGION_YEAR,
    ),
    TzField(TzOwner.IMPACTS, "constraint_annual", "AnnualEmissionLimit", _BY_REGION_YEAR),
    TzField(
        TzOwner.IMPACTS,
        "constraint_annual_region_group",
        "AnnualEmissionLimitRegionGroup",
        _BY_REGIONGROUP_YEAR,
    ),
    TzField(TzOwner.IMPACTS, "constraint_total", "ModelPeriodEmissionLimit", _BY_REGION),
    TzField(TzOwner.IMPACTS, "exogenous_annual", "AnnualExogenousEmission", _BY_REGION_YEAR),
    TzField(
        TzOwner.IMPACTS,
        "exogenous_annual_region_group",
        "AnnualExogenousEmissionRegionGroup",
        _BY_REGIONGROUP_YEAR,
    ),
    TzField(TzOwner.IMPACTS, "exogenous_total", "ModelPeriodExogenousEmission", _BY_REGION),
    TzField(TzOwner.IMPACTS, "penalty", "EmissionsPenalty", _BY_REGION_YEAR),
    TzField(TzOwner.TECHNOLOGIES, "operating_life", "OperationalLife", _BY_REGION, 1.0),
    TzField(TzOwner.TECHNOLOGIES, "capex", "CapitalCost", _BY_REGION_YEAR, _SMALL_COST_DEFAULT),
    TzField(TzOwner.TECHNOLOGIES, "opex_fixed", "FixedCost", _BY_REGION_YEAR, _SMALL_COST_DEFAULT),
    TzField(TzOwner.TECHNOLOGIES, "residual_capacity", "ResidualCapacity", _BY_REGION_YEAR, 0.0),
    TzField(
        TzOwner.TECHNOLOGIES,
        "capacity_activity_unit_ratio",
        "CapacityToActivityUnit",
        _BY_REGION,
        1.0,
    ),
    TzField(
        TzOwner.TECHNOLOGIES, "availability_factor", "AvailabilityFactor", _BY_REGION_YEAR, 1.0
    ),
    TzField(
        TzOwner.TECHNOLOGIES, "capacity_factor", "CapacityFactor", _BY_REGION_YEAR_TIMESLICE, 1.0
    ),
    TzField(
        TzOwner.TECHNOLOGIES,
        "capacity_factor_annual_min",
        "TotalAnnualMinCapacityFactor",
        _BY_REGION_YEAR,
    ),
    TzField(
        TzOwner.TECHNOLOGIES,
        "capacity_one_tech_unit",
        "CapacityOfOneTechnologyUnit",
        _BY_REGION_YEAR,
    ),
    TzField(
        TzOwner.TECHNOLOGIES,
        "include_in_joint_renewable_target",
        "RETagTechnology",
        _BY_REGION_YEAR,
    ),
    TzField(
        TzOwner.TECHNOLOGIES,
        "include_in_joint_reserve_margin",
        "ReserveMarginTagTechnology",
        _BY_REGION_YEAR,
    ),
    TzField(TzOwner.TECHNOLOGIES, "capacity_gross_max", "TotalAnnualMaxCapacity", _BY_REGION_YEAR),
    TzField(TzOwner.TECHNOLOGIES, "capacity_gross_min", "TotalAnnualMinCapacity", _BY_REGION_YEAR),
    TzField(
        TzOwner.TECHNOLOGIES,
        "capacity_additional_max",
        "TotalAnnualMaxCapacityInvestment",
        _BY_REGION_YEAR,
    ),
    TzField(
        TzOwner.TECHNOLOGIES,
        "capacity_additional_max_growth_rate",
        "CapacityAdditionalMaxGrowthRate",
        _BY_REGION_YEAR,
    ),
    TzField(
        TzOwner.TECHNOLOGIES,
        "capacity_additional_max_floor",
        "CapacityAdditionalMaxFloor",
        _BY_REGION_YEAR,
    ),
    TzField(
        TzOwner.TECHNOLOGIES,
        "capacity_additional_min",
        "TotalAnnualMinCapacityInvestment",
        _BY_REGION_YEAR,
    ),
    TzField(
        TzOwner.TECHNOLOGIES,
        "capacity_additional_min_growth_rate",
        "CapacityAdditionalMinGrowthRate",
        _BY_REGION_YEAR,
    ),
    TzField(
        TzOwner.TECHNOLOGIES,
        "activity_annual_max",
        "TotalTechnologyAnnualActivityUpperLimit",
        _BY_REGION_YEAR,
    ),
    TzField(
        TzOwner.TECHNOLOGIES,
        "activity_annual_min",
        "TotalTechnologyAnnualActivityLowerLimit",
        _BY_REGION_YEAR,
    ),
    TzField(
        TzOwner.TECHNOLOGIES,
        "activity_total_max",
        "TotalTechnologyModelPeriodActivityUpperLimit",
        _BY_REGION,
    ),
    TzField(
        TzOwner.TECHNOLOGIES,
        "activity_total_min",
        "TotalTechnologyModelPeriodActivityLowerLimit",
        _BY_REGION,
    ),
    TzField(
        TzOwner.TECHNOLOGIES,
        "production_target_min",
        "TechnologyMinProductionTarget",
        _BY_REGION_FUEL_YEAR,
    ),
    TzField(
        TzOwner.TECHNOLOGIES,
        "production_target_max",
        "TechnologyMaxProductionTarget",
        _BY_REGION_FUEL_YEAR,
    ),
    TzField(TzOwner.OPERATING_MODES, "opex_variable", "VariableCost", _BY_REGION_YEAR),
    TzField(
        TzOwner.OPERATING_MODES,
        "emission_activity_ratio",
        "EmissionActivityRatio",
        _BY_REGION_EMISSION_YEAR,
    ),
    TzField(
        TzOwner.OPERATING_MODES, "input_activity_ratio", "InputActivityRatio", _BY_REGION_FUEL_YEAR
    ),
    TzField(
        TzOwner.OPERATING_MODES,
        "output_activity_ratio",
        "OutputActivityRatio",
        _BY_REGION_FUEL_YEAR,
    ),
    TzField(TzOwner.OPERATING_MODES, "to_storage", "TechnologyToStorage", _BY_REGION_STORAGE),
    TzField(TzOwner.OPERATING_MODES, "from_storage", "TechnologyFromStorage", _BY_REGION_STORAGE),
    TzField(TzOwner.STORAGE, "capex", "CapitalCostStorage", _BY_REGION_YEAR),
    TzField(TzOwner.STORAGE, "operating_life", "OperationalLifeStorage", _BY_REGION),
    TzField(TzOwner.STORAGE, "minimum_charge", "MinStorageCharge", _BY_REGION_YEAR, 0.0),
    TzField(TzOwner.STORAGE, "initial_level", "StorageLevelStart", _BY_REGION, 0.0),
    TzField(TzOwner.STORAGE, "residual_capacity", "ResidualStorageCapacity", _BY_REGION_YEAR, 0.0),
    TzField(TzOwner.STORAGE, "max_discharge_rate", "StorageMaxDischargeRate", _BY_REGION),
    TzField(TzOwner.STORAGE, "max_charge_rate", "StorageMaxChargeRate", _BY_REGION),
    TzField(TzOwner.STORAGE, "storage_balance_day", "StorageBalanceDay", _BY_REGION, 0.0),
    TzField(TzOwner.STORAGE, "storage_balance_season", "StorageBalanceSeason", _BY_REGION, 0.0),
    TzField(TzOwner.STORAGE, "storage_balance_year", "StorageBalanceYear", _BY_REGION, 0.0),
    TzField(TzOwner.STORAGE, "max_hours", "StorageMaxHours", _BY_REGION),
    TzField(TzOwner.TRADE, "trade_routes", "TradeRoute", _BY_REGION_PAIR_YEAR, 0.0),
    TzField(TzOwner.TRADE, "trade_loss", "TradeLossBetweenRegions", _BY_REGION_PAIR_YEAR, 0.0),
    TzField(TzOwner.TRADE, "residual_capacity", "ResidualTradeCapacity", _BY_REGION_PAIR_YEAR, 0.0),
    TzField(TzOwner.TRADE, "capex", "CapitalCostTrade", _BY_REGION_PAIR_YEAR, _SMALL_COST_DEFAULT),
    TzField(
        TzOwner.TRADE,
        "capacity_additional_max",
        "TotalAnnualMaxTradeInvestment",
        _BY_REGION_PAIR_YEAR,
    ),
    TzField(TzOwner.TRADE, "operating_life", "OperationalLifeTrade", _BY_REGION_PAIR_YEAR, 1.0),
    TzField(TzOwner.TRADE, "cost_of_capital", "DiscountRateTrade", _BY_REGION_PAIR, 0.1),
    TzField(
        TzOwner.TRADE,
        "capacity_activity_unit_ratio",
        "TradeCapacityToActivityUnit",
        _BY_REGION_PAIR,
        1.0,
    ),
    TzField(
        TzOwner.TRADE,
        "activity_annual_max",
        "TotalTradeAnnualActivityUpperLimit",
        _BY_REGION_PAIR_YEAR,
    ),
    TzField(
        TzOwner.TRADE,
        "activity_annual_min",
        "TotalTradeAnnualActivityLowerLimit",
        _BY_REGION_PAIR_YEAR,
    ),
    TzField(TzOwner.TRADE, "availability_factor", "AvailabilityFactorTrade", _BY_REGION_PAIR_YEAR),
    TzField(
        TzOwner.TRADE,
        "capacity_factor_annual_min",
        "TotalAnnualMinCapacityFactorTrade",
        _BY_REGION_PAIR_YEAR,
    ),
)

# The key columns that each owner adds to the rows of its fields.
OWNER_COLUMNS: dict[TzOwner, tuple[str, ...]] = {
    TzOwner.MODEL: (),
    TzOwner.TIME_DEFINITION: (),
    TzOwner.REGIONS: (REGION,),
    TzOwner.REGION_GROUPS: (REGIONGROUP,),
    TzOwner.COMMODITIES: (FUEL,),
    TzOwner.IMPACTS: (EMISSION,),
    TzOwner.TECHNOLOGIES: (TECHNOLOGY,),
    TzOwner.OPERATING_MODES: (TECHNOLOGY, MODE_OF_OPERATION),
    TzOwner.STORAGE: (STORAGE,),
    TzOwner.TRADE: (FUEL,),
}

# The owners whose objects each add one member, their `id`, to a set.
OBJECT_SETS: dict[TzOwner, str] = {
    TzOwner.REGIONS: REGION,
    TzOwner.REGION_GROUPS: REGIONGROUP,
    TzOwner.COMMODITIES: FUEL,
    TzOwner.IMPACTS: EMISSION,
    TzOwner.TECHNOLOGIES: TECHNOLOGY,
    TzOwner.STORAGE: STORAGE,
    TzOwner.OPERATING_MODES: MODE_OF_OPERATION,
}

# The fields of the time definition that list the members of a set.
TIME_SETS: dict[str, str] = {
    "years": YEAR,
    "timeslices": TIMESLICE,
    "seasons": SEASON,
    "day_types": DAYTYPE,
    "daily_time_brackets": DAILYTIMEBRACKET,
}

# The key and the value of the wrapper that holds a composed value.
COMPOSED_FLAG = "is_composed"
COMPOSED_DATA = "data"

# The key of a nested level that stands for every member of its set.
WILDCARD = "*"

# The words that a TZ-format value can state, and the number that the OSeMOSYS model file uses
# for each in DepreciationMethod.
VALUE_WORDS: dict[str, float] = {"sinking-fund": 1.0, "straight-line": 2.0}


class DemandSplit(NamedTuple):
    """An annual demand with no profile for its region, fuel and year is an accumulated demand."""

    profile_table: str
    specified_table: str
    accumulated_table: str


ANNUAL_DEMAND_SPLIT = DemandSplit(
    profile_table="SpecifiedDemandProfile",
    specified_table="SpecifiedAnnualDemand",
    accumulated_table="AccumulatedAnnualDemand",
)
