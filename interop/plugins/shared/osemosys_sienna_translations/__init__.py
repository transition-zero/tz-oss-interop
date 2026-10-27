"""OSeMOSYS to Sienna translations, one module per component group.

Each module reads the canonical OSeMOSYS stage for one operations year and states what a
part of it becomes in Sienna.
"""

from __future__ import annotations

from interop.plugins.shared.osemosys_sienna_translations._buses import (
    BUS_MAPPING,
    build_bus_extensions,
    build_buses_source_table,
    read_electricity_fuels,
)
from interop.plugins.shared.osemosys_sienna_translations._calendar import (
    Calendar,
    build_calendar,
    build_period_records,
    report_calendar,
    set_days_persisted,
)
from interop.plugins.shared.osemosys_sienna_translations._canonical import (
    list_model_years,
    read_operations_mode,
)
from interop.plugins.shared.osemosys_sienna_translations._component_mapping import (
    BuiltRecords,
    ComponentMapping,
    add_built_records,
    map_component_table,
)
from interop.plugins.shared.osemosys_sienna_translations._defaults import (
    report_unread_defaults,
)
from interop.plugins.shared.osemosys_sienna_translations._fuel_modes import (
    build_fuel_modes_source,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_columns import (
    GENERATOR_NAME,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_events import (
    warn_lost_costs,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_translations import (
    GENERATOR_TYPE_MAPPINGS,
    GeneratorTypeMapping,
)
from interop.plugins.shared.osemosys_sienna_translations._generators import (
    GeneratorSources,
    build_generator_extensions,
    build_generators_source,
    set_generator_values_persisted,
)
from interop.plugins.shared.osemosys_sienna_translations._left_out import (
    report_left_out_technologies,
)
from interop.plugins.shared.osemosys_sienna_translations._loads import (
    LOAD_MAPPING,
    LoadSources,
    build_fuel_loads_source,
    build_load_series,
    build_loads_source,
)
from interop.plugins.shared.osemosys_sienna_translations._operations import (
    OperationsMapping,
    OperationsYear,
    require_model_year,
    set_operations_year,
)
from interop.plugins.shared.osemosys_sienna_translations._series import (
    StagedSeries,
    add_per_unit_series,
    add_series,
    add_to_per_unit_series,
)
from interop.plugins.shared.osemosys_sienna_translations._technology_columns import (
    SIENNA_TYPE,
)
from interop.plugins.shared.osemosys_sienna_translations._technology_values import (
    CANDIDATE_VALUES,
    enrich_technology_values,
)
from interop.plugins.shared.osemosys_sienna_translations._units import ModelUnits, parse_units

__all__ = [
    "BUS_MAPPING",
    "CANDIDATE_VALUES",
    "GENERATOR_NAME",
    "GENERATOR_TYPE_MAPPINGS",
    "LOAD_MAPPING",
    "SIENNA_TYPE",
    "BuiltRecords",
    "Calendar",
    "ComponentMapping",
    "GeneratorSources",
    "GeneratorTypeMapping",
    "LoadSources",
    "ModelUnits",
    "OperationsMapping",
    "OperationsYear",
    "StagedSeries",
    "add_built_records",
    "add_per_unit_series",
    "add_series",
    "add_to_per_unit_series",
    "build_bus_extensions",
    "build_buses_source_table",
    "build_calendar",
    "build_fuel_loads_source",
    "build_fuel_modes_source",
    "build_generator_extensions",
    "build_generators_source",
    "build_load_series",
    "build_loads_source",
    "build_period_records",
    "enrich_technology_values",
    "list_model_years",
    "map_component_table",
    "read_operations_mode",
    "parse_units",
    "read_electricity_fuels",
    "report_calendar",
    "report_left_out_technologies",
    "report_unread_defaults",
    "require_model_year",
    "set_days_persisted",
    "set_generator_values_persisted",
    "warn_lost_costs",
    "set_operations_year",
]
