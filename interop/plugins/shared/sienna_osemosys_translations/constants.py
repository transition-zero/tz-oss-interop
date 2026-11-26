"""The names, the columns and the fixed values of the Sienna to OSeMOSYS leg."""

from __future__ import annotations

SIENNA_TO_OSEMOSYS_PIPELINE = "sienna-to-osemosys"

# The character between a region and a fuel in the name of a bus, and between a
# representative period and the hour of that period in the name of a timeslice.
NAME_SEPARATOR = "/"

# Every value of a Sienna system is in these units, so the written model states them.
CAPACITY_UNIT = "MW"
ENERGY_UNIT = "MWh"
CURRENCY_UNIT = "USD"
EMISSIONS_UNIT = "t"

# 1 puts a timeslice in a season, a day type or a daily time bracket.
MEMBERSHIP_FLAG = 1.0

# The one year of a model whose sidecar names no year and whose series states no timestamp.
UNDATED_YEAR = 1
