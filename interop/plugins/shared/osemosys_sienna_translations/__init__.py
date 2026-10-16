"""OSeMOSYS to Sienna translations, one module per component group.

Each module reads the canonical OSeMOSYS stage for one operations year and states what a
part of it becomes in Sienna.
"""

from __future__ import annotations

from interop.plugins.shared.osemosys_sienna_translations._buses import (
    BUS_TRANSLATIONS,
    build_bus_extensions,
    build_buses_source_table,
    read_electricity_fuels,
)
from interop.plugins.shared.osemosys_sienna_translations._calendar import (
    Calendar,
    build_calendar,
    build_representative_periods,
    report_calendar,
)
from interop.plugins.shared.osemosys_sienna_translations._canonical import (
    read_operations_mode,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_columns import (
    GENERATOR_NAME,
    SIENNA_TYPE,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_translations import (
    GENERATOR_TYPE_MAPPINGS,
    GeneratorTypeMapping,
)
from interop.plugins.shared.osemosys_sienna_translations._generators import (
    GeneratorSources,
    build_generator_extensions,
    build_generators_source,
)
from interop.plugins.shared.osemosys_sienna_translations._loads import (
    LOAD_BASE_POWER_TRANSLATIONS,
    LOAD_TRANSLATIONS,
    LoadSources,
    build_loads_source,
)
from interop.plugins.shared.osemosys_sienna_translations._operations import (
    OperationsMapping,
    OperationsYear,
    require_model_year,
)
from interop.plugins.shared.osemosys_sienna_translations._series import (
    StagedSeries,
    add_per_unit_series,
    add_series,
)
from interop.plugins.shared.osemosys_sienna_translations._units import ModelUnits, parse_units

__all__ = [
    "BUS_TRANSLATIONS",
    "GENERATOR_NAME",
    "GENERATOR_TYPE_MAPPINGS",
    "LOAD_BASE_POWER_TRANSLATIONS",
    "LOAD_TRANSLATIONS",
    "SIENNA_TYPE",
    "Calendar",
    "GeneratorSources",
    "GeneratorTypeMapping",
    "LoadSources",
    "ModelUnits",
    "OperationsMapping",
    "OperationsYear",
    "StagedSeries",
    "add_per_unit_series",
    "add_series",
    "build_bus_extensions",
    "build_buses_source_table",
    "build_calendar",
    "build_generator_extensions",
    "build_generators_source",
    "build_loads_source",
    "build_representative_periods",
    "read_operations_mode",
    "parse_units",
    "read_electricity_fuels",
    "report_calendar",
    "require_model_year",
]
