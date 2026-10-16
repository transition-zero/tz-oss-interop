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

HOURS_PER_YEAR = 8760.0
UNIT_DAYS = "d"
HOURS_PER_DAY = 24
# A daily time bracket this close to a whole number of hours takes that number of hours.
WHOLE_HOUR_TOLERANCE = 0.05
# Two day weights this close, as a share of the larger, are the same weight.
WEIGHT_RELATIVE_TOLERANCE = 1e-6
# The value that marks a timeslice as a member of a season, a day type or a daily time bracket.
MEMBERSHIP_FLAG = 1.0

# The parameter that the operations step takes when it is to use the earliest model year.
EARLIEST_YEAR = "earliest"

# The name of the one period of a calendar with one hour per timeslice.
TIMESLICE_PERIOD_NAME = "timeslices"
# The character between the season and the day type in the name of a representative day.
PERIOD_NAME_SEPARATOR = "/"

# A load of accumulated annual demand takes the name of its fuel, this separator and suffix.
LOAD_NAME_SEPARATOR = "/"
ACCUMULATED_LOAD_SUFFIX = "accumulated"

# The fallback that the base power of a load takes when its peak is lower, in MVA.
MIN_LOAD_BASE_POWER_MVA = 0.1

# OSeMOSYS states no voltage, so a bus takes the per-unit values that a Sienna consumer assumes.
DEFAULT_BASE_VOLTAGE = 1.0
DEFAULT_MAGNITUDE = 1.0
DEFAULT_ANGLE = 0.0
VOLTAGE_LIMIT_MIN = 0.9
VOLTAGE_LIMIT_MAX = 1.1


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
    DAY = "day"
    WEIGHT_HOURS = "weight_hours"


class CalendarDayCol(StrEnum):
    """A column of the days table of a calendar."""

    DAY = "day"
    NAME = "name"
    SEASON = "season"
    DAY_TYPE = "day_type"
    WEIGHT_DAYS = "weight_days"
    FIRST_TIMESTAMP = "first_timestamp"
    HOURS = "hours"
