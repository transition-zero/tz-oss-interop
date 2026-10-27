"""The columns that name a generator, its capacity and its record, in the generator source table."""

from __future__ import annotations

from interop.core.extensions import ExtensionKind
from interop.plugins.shared.osemosys_sienna_translations._technology_columns import (
    SIENNA_TYPE,
    TECHNOLOGY_NAME,
)
from interop.plugins.shared.osemosys_sienna_translations._technology_values import ValueOwners

GENERATOR_NAME = "generator_name"
CAPACITY_UNIT = "capacity_unit"
CAPACITY_MW = "capacity_mw"
HAS_SERIES = "has_series"
OUTPUT_CAPACITY_MW = "output_capacity_mw"

# The records of the generators, and the columns that name each generator and its technology.
GENERATOR_OWNERS = ValueOwners(
    ExtensionKind.GENERATOR, GENERATOR_NAME, TECHNOLOGY_NAME, SIENNA_TYPE
)
