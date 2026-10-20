"""The columns of the generator source table, in OSeMOSYS words, before any Sienna column."""

from __future__ import annotations

from interop.core.extensions import ExtensionKind
from interop.plugins.shared.osemosys_sienna_translations._technology_values import ValueOwners

GENERATOR_NAME = "generator_name"
TECHNOLOGY_NAME = "technology_name"
SIENNA_TYPE = "sienna_type"
PRIME_MOVER = "prime_mover"
FUEL_TYPE = "fuel_type"
RESIDUAL_CAPACITY = "residual_capacity"
CAPACITY_UNIT = "capacity_unit"
CAPACITY_MW = "capacity_mw"
HAS_SERIES = "has_series"
OUTPUT_CAPACITY_MW = "output_capacity_mw"

# The records of the generators, and the columns that name each generator and its technology.
GENERATOR_OWNERS = ValueOwners(
    ExtensionKind.GENERATOR, GENERATOR_NAME, TECHNOLOGY_NAME, SIENNA_TYPE
)
