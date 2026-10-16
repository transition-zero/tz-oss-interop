"""The vocabulary of the OSeMOSYS to Sienna translation, which both of its steps share."""

from __future__ import annotations

from enum import StrEnum

# The pipeline name that each warning of the translation starts with.
OSEMOSYS_TO_SIENNA_PIPELINE = "osemosys-to-sienna"

# The first part of the `State.source_time_series` key of each series that the translation
# stages for the HDF5 sink. It is not a canonical table kind, so no canonical reader takes it.
OSEMOSYS_SIENNA_SERIES = "osemosys_sienna_series"
# The character between the owner type and the attribute in the second part of that key.
SERIES_KEY_SEPARATOR = "."
# The `State.source_time_series` key of the one-row table that holds the operations year, which
# the operations step writes for a later step of the pipeline. It is not a canonical table kind.
OPERATIONS_YEAR_KEY = ("osemosys_sienna_operations", "year")

HOURS_PER_YEAR = 8760.0
HOURS_PER_DAY = 24
# A daily time bracket this close to a whole number of hours takes that number of hours.
WHOLE_HOUR_TOLERANCE = 0.05
# Two day weights this close, as a share of the larger, are the same weight.
WEIGHT_RELATIVE_TOLERANCE = 1e-6
# The value that marks a timeslice as a member of a season, a day type or a daily time bracket.
MEMBERSHIP_FLAG = 1.0

# The parameter that the operations step takes when it is to use the earliest model year.
EARLIEST_YEAR = "earliest"

# The character between the season and the day type in the name of a representative day.
PERIOD_NAME_SEPARATOR = "/"

# The character between a region and a member, in a name that needs both.
REGION_NAME_SEPARATOR = "/"
# A load of accumulated annual demand takes the name of its fuel, this separator and suffix.
LOAD_NAME_SEPARATOR = "/"
ACCUMULATED_LOAD_SUFFIX = "accumulated"

# The fallback that the base power of a load takes when its peak is lower, in MVA.
MIN_LOAD_BASE_POWER_MVA = 0.1


class UnitQuantity(StrEnum):
    """A field of the `units:` part of the user mappings file."""

    CAPACITY = "capacity"
    ENERGY = "energy"
    CURRENCY = "currency"
    CURRENCY_YEAR = "currency_year"
    EMISSIONS = "emissions"


class DemandParameter(StrEnum):
    """A canonical parameter that states the demand for a fuel."""

    SPECIFIED_ANNUAL_DEMAND = "specified_annual_demand"
    SPECIFIED_DEMAND_PROFILE = "specified_demand_profile"
    ACCUMULATED_ANNUAL_DEMAND = "accumulated_annual_demand"


class CalendarParameter(StrEnum):
    """A canonical parameter that states the time structure of a model year."""

    YEAR_SPLIT = "year_split"
    DAY_SPLIT = "day_split"
    TIMESLICE_IN_SEASON = "timeslice_in_season"
    TIMESLICE_IN_DAY_TYPE = "timeslice_in_day_type"
    TIMESLICE_IN_DAILY_TIME_BRACKET = "timeslice_in_daily_time_bracket"


class CalendarHourCol(StrEnum):
    """A column of the hours table of a calendar."""

    TIMESTAMP = "timestamp"
    TIMESLICE = "timeslice"
    PERIOD = "period"
    WEIGHT_HOURS = "weight_hours"


class CalendarPeriodCol(StrEnum):
    """A column of the periods table of a calendar."""

    PERIOD = "period"
    NAME = "name"
    SEASON = "season"
    DAY_TYPE = "day_type"
    WEIGHT = "weight"
    FIRST_TIMESTAMP = "first_timestamp"
    HOURS = "hours"


# The operating mode whose values the operations system runs, when the model holds it.
OPERATIONS_MODE = "1"


class SupplyParameter(StrEnum):
    """A canonical parameter that states what a technology can make, and what it costs or emits."""

    RESIDUAL_CAPACITY = "residual_capacity"
    CAPACITY_FACTOR = "capacity_factor"
    AVAILABILITY_FACTOR = "availability_factor"
    VARIABLE_OPERATION_COST = "variable_operation_cost"
    FIXED_COST = "fixed_cost"
    EMISSION_RATE = "emission_rate"
    EMISSION_PENALTY = "emission_penalty"
    ACTIVITY_UPPER_LIMIT = "total_technology_annual_activity_upper_limit"
    ACTIVITY_LOWER_LIMIT = "total_technology_annual_activity_lower_limit"


class StorageParameter(StrEnum):
    """A canonical parameter that states the energy of a storage."""

    RESIDUAL_STORAGE_CAPACITY = "residual_storage_capacity"
    STORAGE_LEVEL_START = "storage_level_start"
    MIN_STORAGE_CHARGE = "min_storage_charge"
    MAX_CHARGE_RATE = "storage_max_charge_rate"
    MAX_DISCHARGE_RATE = "storage_max_discharge_rate"


# The word that counts technologies in a warning, and the label of the names that it lists.
TECHNOLOGY_COUNTED_NOUN = "technology(ies)"
TECHNOLOGIES_LABEL = "Technologies"


# --- The investments portfolio ---------------------------------------------------------

# The value of a limit parameter that states no limit.
NO_LIMIT = -1.0
# The key of the feature that names the year of a series of the portfolio.
YEAR_FEATURE = "year"
# The first part of the `State.source_time_series` key of each series of the portfolio.
OSEMOSYS_PORTFOLIO_SERIES = "osemosys_sienna_portfolio_series"
# The character between the attribute and the year in the second part of that key.
SERIES_YEAR_SEPARATOR = "/"
MINUTES_PER_HOUR = 60.0
TONNES_PER_MEGATONNE = 1e6


class InvestmentParameter(StrEnum):
    """A canonical parameter that states what new capacity costs and how much a plan may build."""

    CAPITAL_COST = "capital_cost"
    CAPACITY_LIMITS_MIN = "capacity_limits_min"
    CAPACITY_LIMITS_MAX = "capacity_limits_max"
    MAX_CAPACITY_INVESTMENT = "total_annual_max_capacity_investment"
    LIFETIME = "lifetime"
    UNIT_SIZE = "unit_size"
    DISCOUNT_RATE = "discount_rate"
    TECHNOLOGY_DISCOUNT_RATE = "technology_discount_rate"
    ENERGY_CAPITAL_COST = "energy_capital_cost"
    DURATION_LIMITS_MAX = "duration_limits_max"
    STORAGE_LIFETIME = "storage_lifetime"
    STORAGE_DISCOUNT_RATE = "storage_discount_rate"


class EmissionParameter(StrEnum):
    """A canonical parameter that states a limit on a pollutant."""

    ANNUAL_EMISSION_LIMIT = "annual_emission_limit"
    ANNUAL_EXOGENOUS_EMISSION = "annual_exogenous_emission"
    MODEL_PERIOD_EMISSION_LIMIT = "model_period_emission_limit"
    MODEL_PERIOD_EXOGENOUS_EMISSION = "model_period_exogenous_emission"
