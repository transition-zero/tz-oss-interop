"""The columns of the transport source table, in OSeMOSYS words, before any Sienna column."""

from __future__ import annotations

from enum import StrEnum

LINE_NAME = "line_name"
FROM_LOCATION = "from_location"
FROM_LOCATIONS = "from_locations"
FROM_FUEL = "from_fuel"
TO_LOCATION = "to_location"
TO_LOCATIONS = "to_locations"
TO_FUEL = "to_fuel"
FROM_BUS = "from_bus"
FROM_BUSES = "from_buses"
TO_BUS = "to_bus"
TO_BUSES = "to_buses"
# The capacity that the year can use, in the capacity unit, whether it is capacity that the model
# builds at no cost, and whether no limit binds it.
LINE_CAPACITY = "line_capacity"
CAPACITY_PARAMETER = "capacity_parameter"
IS_BUILT_FREE = "is_built_free"
IS_UNLIMITED = "is_unlimited"
# Whether a line with no limit leaves out an availability or a capacity factor that it states.
HAS_DROPPED_DERATE = "has_dropped_derate"
# Whether the model states a capacity factor for the line.
HAS_STATED_FACTORS = "has_stated_factors"
# Whether the line is a conversion between two electricity fuels, which its record marks.
IS_CONVERSION = "is_conversion"
INPUT_RATIO = "electricity_input_ratio"
OUTPUT_RATIO = "electricity_output_ratio"
AVAILABILITY = "availability"
# The availability factor that the rating applies, where it is less than the whole capacity.
DERATE = "derate"
CAPACITY_MW = "capacity_mw"
SENT_MW = "sent_mw"
RECEIVED_MW = "received_mw"
LOSS = "loss"
COST = "cost"
COST_MWH = "cost_mwh"
REVERSE_MODE = "reverse_mode"
REVERSE_INPUT_RATIO = "reverse_input_ratio"
REVERSE_OUTPUT_RATIO = "reverse_output_ratio"
REVERSE_SENT_MW = "reverse_sent_mw"
REVERSE_RECEIVED_MW = "reverse_received_mw"
IMPORT_FLOWS = "import_flows"
# The capacity that each line rates at, and the source value that gives it.
RATING = "rating"


class RatingField(StrEnum):
    """The fields of a rating.

    `parameter`, `name`, `attribute`, `value` and `unit` state the source value of the capacity.
    `is_stand_in` marks a capacity that no limit of the model gives, which never binds. `term`
    names the capacity in the derivation of the limits.
    """

    PARAMETER = "parameter"
    NAME = "name"
    ATTRIBUTE = "attribute"
    VALUE = "value"
    UNIT = "unit"
    IS_STAND_IN = "is_stand_in"
    TERM = "term"
