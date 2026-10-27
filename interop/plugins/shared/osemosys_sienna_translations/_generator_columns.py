"""The columns that name a generator and its capacity, and the values that its record holds."""

from __future__ import annotations

from interop.core.extensions import ExtensionKind
from interop.plugins.shared.osemosys_canonical.constants import FlowParameter
from interop.plugins.shared.osemosys_sienna_translations._operating_modes import (
    GENERATOR_RUN_PARAMETERS,
)
from interop.plugins.shared.osemosys_sienna_translations._technology_columns import (
    SIENNA_TYPE,
    TECHNOLOGY_NAME,
)
from interop.plugins.shared.osemosys_sienna_translations._technology_extras import (
    TechnologyExtras,
)
from interop.plugins.shared.osemosys_sienna_translations._technology_values import (
    COMPONENT_VALUES,
    ValueOwners,
)

GENERATOR_NAME = "generator_name"
CAPACITY_UNIT = "capacity_unit"
CAPACITY_MW = "capacity_mw"
HAS_SERIES = "has_series"
OUTPUT_CAPACITY_MW = "output_capacity_mw"

# The records of the generators, and the columns that name each generator and its technology.
GENERATOR_OWNERS = ValueOwners(
    ExtensionKind.GENERATOR, GENERATOR_NAME, TECHNOLOGY_NAME, SIENNA_TYPE
)
# A generator rates on its electricity output, and runs the operations mode.
GENERATOR_EXTRAS = TechnologyExtras(
    GENERATOR_OWNERS,
    COMPONENT_VALUES,
    GENERATOR_RUN_PARAMETERS,
    FlowParameter.OUTPUT_ACTIVITY_RATIO,
)
