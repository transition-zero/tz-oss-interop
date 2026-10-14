"""The defaults in this table come from the field documentation of tz-osemosys v0.4.1."""

from __future__ import annotations

from enum import StrEnum
from typing import NamedTuple

from interop.plugins.shared.osemosys_canonical.constants import (
    DAILY_TIME_BRACKET,
    DAY_TYPE,
    FUEL,
    NAME_SEPARATOR,
    OPERATING_MODE,
    OSEMOSYS_SECOND_REGION,
    POLLUTANT,
    REGION,
    REGION_GROUP,
    SEASON,
    STORAGE,
    TECHNOLOGY,
    TIMESLICE,
    YEAR,
)
from interop.plugins.shared.osemosys_canonical.schema import load_canonical_schema


class TzOwner(StrEnum):
    """Each value is the key of the owner in a model.json, so a renamed value no longer finds it."""

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


def build_tz_name(*parts: str) -> str:
    return NAME_SEPARATOR.join(part for part in parts if part)


class TzField(NamedTuple):
    """`nesting` lists the set of each nested level, outermost first, and `value_set` names the
    set of a value that states a member."""

    owner: TzOwner
    field: str
    table: str
    nesting: tuple[str, ...]
    default: float | None = None
    value_set: str | None = None


# The TZ format keys its sets by their default names, which the canonical schema states.
_SCHEMA = load_canonical_schema()
OSEMOSYS_REGION = _SCHEMA.get_osemosys_set_name(REGION)
OSEMOSYS_TECHNOLOGY = _SCHEMA.get_osemosys_set_name(TECHNOLOGY)
OSEMOSYS_FUEL = _SCHEMA.get_osemosys_set_name(FUEL)
OSEMOSYS_EMISSION = _SCHEMA.get_osemosys_set_name(POLLUTANT)
OSEMOSYS_MODE_OF_OPERATION = _SCHEMA.get_osemosys_set_name(OPERATING_MODE)
OSEMOSYS_STORAGE = _SCHEMA.get_osemosys_set_name(STORAGE)
OSEMOSYS_YEAR = _SCHEMA.get_osemosys_set_name(YEAR)
OSEMOSYS_TIMESLICE = _SCHEMA.get_osemosys_set_name(TIMESLICE)
OSEMOSYS_SEASON = _SCHEMA.get_osemosys_set_name(SEASON)
OSEMOSYS_DAYTYPE = _SCHEMA.get_osemosys_set_name(DAY_TYPE)
OSEMOSYS_DAILYTIMEBRACKET = _SCHEMA.get_osemosys_set_name(DAILY_TIME_BRACKET)
OSEMOSYS_REGIONGROUP = _SCHEMA.get_osemosys_set_name(REGION_GROUP)

_BY_REGION = (OSEMOSYS_REGION,)
_BY_REGION_YEAR = (OSEMOSYS_REGION, OSEMOSYS_YEAR)
_BY_REGION_YEAR_TIMESLICE = (OSEMOSYS_REGION, OSEMOSYS_YEAR, OSEMOSYS_TIMESLICE)
_BY_REGION_FUEL_YEAR = (OSEMOSYS_REGION, OSEMOSYS_FUEL, OSEMOSYS_YEAR)
_BY_REGION_EMISSION_YEAR = (OSEMOSYS_REGION, OSEMOSYS_EMISSION, OSEMOSYS_YEAR)
_BY_REGION_STORAGE = (OSEMOSYS_REGION, OSEMOSYS_STORAGE)
_BY_REGION_PAIR = (OSEMOSYS_REGION, OSEMOSYS_SECOND_REGION)
_BY_REGION_PAIR_YEAR = (OSEMOSYS_REGION, OSEMOSYS_SECOND_REGION, OSEMOSYS_YEAR)
_BY_REGIONGROUP_YEAR = (OSEMOSYS_REGIONGROUP, OSEMOSYS_YEAR)

# The default that the documentation states for a capital cost and a fixed cost.
_SMALL_COST_DEFAULT = 0.00001

TZ_FIELDS: tuple[TzField, ...] = (
    TzField(TzOwner.MODEL, "depreciation_method", "DepreciationMethod", _BY_REGION, 1.0),
    TzField(TzOwner.MODEL, "discount_rate", "DiscountRate", _BY_REGION, 0.05),
    TzField(
        TzOwner.MODEL, "cost_of_capital", "DiscountRateIdv", (OSEMOSYS_REGION, OSEMOSYS_TECHNOLOGY)
    ),
    TzField(TzOwner.MODEL, "cost_of_capital_storage", "DiscountRateStorage", _BY_REGION_STORAGE),
    TzField(TzOwner.MODEL, "reserve_margin", "ReserveMargin", _BY_REGION_YEAR, 1.0),
    TzField(TzOwner.MODEL, "renewable_production_target", "REMinProductionTarget", _BY_REGION_YEAR),
    TzField(
        TzOwner.MODEL,
        "region_group_renewable_production_target",
        "RegionGroupREMinProductionTarget",
        _BY_REGIONGROUP_YEAR,
    ),
    TzField(
        TzOwner.TIME_DEFINITION, "year_split", "YearSplit", (OSEMOSYS_TIMESLICE, OSEMOSYS_YEAR)
    ),
    TzField(
        TzOwner.TIME_DEFINITION, "day_split", "DaySplit", (OSEMOSYS_DAILYTIMEBRACKET, OSEMOSYS_YEAR)
    ),
    TzField(
        TzOwner.TIME_DEFINITION,
        "days_in_day_type",
        "DaysInDayType",
        (OSEMOSYS_SEASON, OSEMOSYS_DAYTYPE, OSEMOSYS_YEAR),
    ),
    TzField(
        TzOwner.TIME_DEFINITION,
        "timeslice_in_timebracket",
        "Conversionlh",
        (OSEMOSYS_TIMESLICE,),
        value_set=OSEMOSYS_DAILYTIMEBRACKET,
    ),
    TzField(
        TzOwner.TIME_DEFINITION,
        "timeslice_in_daytype",
        "Conversionld",
        (OSEMOSYS_TIMESLICE,),
        value_set=OSEMOSYS_DAYTYPE,
    ),
    TzField(
        TzOwner.TIME_DEFINITION,
        "timeslice_in_season",
        "Conversionls",
        (OSEMOSYS_TIMESLICE,),
        value_set=OSEMOSYS_SEASON,
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

TZ_FIELDS_BY_KEY: dict[tuple[TzOwner, str], TzField] = {
    (field.owner, field.field): field for field in TZ_FIELDS
}

OWNER_COLUMNS: dict[TzOwner, tuple[str, ...]] = {
    TzOwner.MODEL: (),
    TzOwner.TIME_DEFINITION: (),
    TzOwner.REGIONS: (OSEMOSYS_REGION,),
    TzOwner.REGION_GROUPS: (OSEMOSYS_REGIONGROUP,),
    TzOwner.COMMODITIES: (OSEMOSYS_FUEL,),
    TzOwner.IMPACTS: (OSEMOSYS_EMISSION,),
    TzOwner.TECHNOLOGIES: (OSEMOSYS_TECHNOLOGY,),
    TzOwner.OPERATING_MODES: (OSEMOSYS_TECHNOLOGY, OSEMOSYS_MODE_OF_OPERATION),
    TzOwner.STORAGE: (OSEMOSYS_STORAGE,),
    TzOwner.TRADE: (OSEMOSYS_FUEL,),
}

OBJECT_SETS: dict[TzOwner, str] = {
    TzOwner.REGIONS: OSEMOSYS_REGION,
    TzOwner.REGION_GROUPS: OSEMOSYS_REGIONGROUP,
    TzOwner.COMMODITIES: OSEMOSYS_FUEL,
    TzOwner.IMPACTS: OSEMOSYS_EMISSION,
    TzOwner.TECHNOLOGIES: OSEMOSYS_TECHNOLOGY,
    TzOwner.STORAGE: OSEMOSYS_STORAGE,
    TzOwner.OPERATING_MODES: OSEMOSYS_MODE_OF_OPERATION,
}

TIME_SETS: dict[str, str] = {
    "years": OSEMOSYS_YEAR,
    "timeslices": OSEMOSYS_TIMESLICE,
    "seasons": OSEMOSYS_SEASON,
    "day_types": OSEMOSYS_DAYTYPE,
    "daily_time_brackets": OSEMOSYS_DAILYTIMEBRACKET,
}

# The trade fields that `construct_region_pairs` copies to the opposite direction of each pair.
REGION_PAIR_FIELDS = frozenset(
    {
        "trade_routes",
        "trade_loss",
        "residual_capacity",
        "capex",
        "capacity_additional_max",
        "operating_life",
        "cost_of_capital",
        "capacity_activity_unit_ratio",
    }
)

# A composed value is a wrapper object that holds these two keys.
COMPOSED_FLAG = "is_composed"
COMPOSED_DATA = "data"

# The key of a nested level that stands for every member of its set.
WILDCARD = "*"

# The words that a TZ-format value can state, and the number that the OSeMOSYS model file uses
# for each in DepreciationMethod.
VALUE_WORDS: dict[str, float] = {"sinking-fund": 1.0, "straight-line": 2.0}


class DemandSplit(NamedTuple):
    profile_table: str
    specified_table: str
    accumulated_table: str


ANNUAL_DEMAND_SPLIT = DemandSplit(
    profile_table="SpecifiedDemandProfile",
    specified_table="SpecifiedAnnualDemand",
    accumulated_table="AccumulatedAnnualDemand",
)
