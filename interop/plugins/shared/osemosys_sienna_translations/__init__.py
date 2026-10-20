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
from interop.plugins.shared.osemosys_sienna_translations._conversions import (
    build_conversion_records,
    build_conversions_source,
    build_routes_source,
    set_conversion_values_persisted,
)
from interop.plugins.shared.osemosys_sienna_translations._defaults import (
    report_unread_defaults,
)
from interop.plugins.shared.osemosys_sienna_translations._fuel_loads import (
    FuelLoads,
    build_fuel_loads,
)
from interop.plugins.shared.osemosys_sienna_translations._fuel_modes import (
    build_fuel_modes_source,
)
from interop.plugins.shared.osemosys_sienna_translations._fuel_records import (
    FuelRecords,
    build_fuel_records,
    set_fuel_values_persisted,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_columns import (
    GENERATOR_NAME,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_events import (
    warn_lost_costs,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_translations import (
    GENERATOR_TYPE_MAPPINGS,
)
from interop.plugins.shared.osemosys_sienna_translations._generators import (
    GeneratorSources,
    build_generator_extensions,
    build_generators_source,
    set_generator_values_persisted,
)
from interop.plugins.shared.osemosys_sienna_translations._import_translations import (
    build_import_mapping,
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
from interop.plugins.shared.osemosys_sienna_translations._policies import (
    build_policies,
    report_policy_changes,
    set_policies_persisted,
)
from interop.plugins.shared.osemosys_sienna_translations._series import (
    StagedSeries,
    add_per_unit_series,
    add_series,
    add_to_per_unit_series,
)
from interop.plugins.shared.osemosys_sienna_translations._storage import (
    build_storage_extensions,
    build_storages_source,
    set_storage_values_persisted,
)
from interop.plugins.shared.osemosys_sienna_translations._storage_translations import (
    STORAGE_MAPPING,
)
from interop.plugins.shared.osemosys_sienna_translations._technology_columns import (
    SIENNA_TYPE,
)
from interop.plugins.shared.osemosys_sienna_translations._technology_values import (
    CANDIDATE_VALUES,
    enrich_technology_values,
)
from interop.plugins.shared.osemosys_sienna_translations._transport import (
    build_line_extensions,
    build_transport_source,
    read_transport_ends,
    set_line_values_persisted,
)
from interop.plugins.shared.osemosys_sienna_translations._transport_imports import (
    build_import_extensions,
    set_import_values_persisted,
)
from interop.plugins.shared.osemosys_sienna_translations._transport_translations import (
    TRANSPORT_MAPPING,
)
from interop.plugins.shared.osemosys_sienna_translations._unapplied_parameters import (
    INVESTMENTS_PARAMETERS,
    OPERATIONS_PARAMETERS,
    report_unapplied_parameters,
)
from interop.plugins.shared.osemosys_sienna_translations._units import ModelUnits, parse_units

__all__ = [
    "BUS_MAPPING",
    "CANDIDATE_VALUES",
    "GENERATOR_NAME",
    "GENERATOR_TYPE_MAPPINGS",
    "INVESTMENTS_PARAMETERS",
    "LOAD_MAPPING",
    "OPERATIONS_PARAMETERS",
    "SIENNA_TYPE",
    "STORAGE_MAPPING",
    "TRANSPORT_MAPPING",
    "BuiltRecords",
    "Calendar",
    "ComponentMapping",
    "FuelLoads",
    "FuelRecords",
    "GeneratorSources",
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
    "build_conversion_records",
    "build_conversions_source",
    "build_fuel_loads",
    "build_fuel_loads_source",
    "build_fuel_modes_source",
    "build_fuel_records",
    "build_generator_extensions",
    "build_generators_source",
    "build_import_extensions",
    "build_import_mapping",
    "build_line_extensions",
    "build_load_series",
    "build_loads_source",
    "build_period_records",
    "build_policies",
    "build_routes_source",
    "build_storage_extensions",
    "build_storages_source",
    "build_transport_source",
    "enrich_technology_values",
    "list_model_years",
    "map_component_table",
    "read_operations_mode",
    "parse_units",
    "read_electricity_fuels",
    "read_transport_ends",
    "report_calendar",
    "report_left_out_technologies",
    "report_policy_changes",
    "report_unapplied_parameters",
    "report_unread_defaults",
    "require_model_year",
    "set_conversion_values_persisted",
    "set_days_persisted",
    "set_fuel_values_persisted",
    "set_generator_values_persisted",
    "set_import_values_persisted",
    "set_line_values_persisted",
    "set_operations_year",
    "set_policies_persisted",
    "set_storage_values_persisted",
    "warn_lost_costs",
]
