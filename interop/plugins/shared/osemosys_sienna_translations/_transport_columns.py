"""The columns of the transport source table, in OSeMOSYS words, before any Sienna column."""

from __future__ import annotations

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
IS_BUILT_FREE = "is_built_free"
IS_UNLIMITED = "is_unlimited"
# Whether a line with no limit leaves out an availability or a capacity factor that it states.
HAS_DROPPED_DERATE = "has_dropped_derate"
# Whether the line is a conversion between two electricity fuels, which its record marks.
IS_CONVERSION = "is_conversion"
INPUT_RATIO = "electricity_input_ratio"
OUTPUT_RATIO = "electricity_output_ratio"
AVAILABILITY = "availability"
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
