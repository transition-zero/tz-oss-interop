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
    build_days_events,
    build_representative_periods,
    report_calendar,
    set_days_persisted,
)
from interop.plugins.shared.osemosys_sienna_translations._canonical import (
    list_model_years,
    read_operations_mode,
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
from interop.plugins.shared.osemosys_sienna_translations._fuel_modes import (
    build_fuel_modes_source,
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
    set_generator_values_persisted,
)
from interop.plugins.shared.osemosys_sienna_translations._import_translations import (
    build_import_translations,
)
from interop.plugins.shared.osemosys_sienna_translations._left_out import (
    report_left_out_technologies,
)
from interop.plugins.shared.osemosys_sienna_translations._loads import (
    LOAD_BASE_POWER_TRANSLATIONS,
    LOAD_TRANSLATIONS,
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
    append_per_unit_series,
)
from interop.plugins.shared.osemosys_sienna_translations._storage import (
    build_storage_extensions,
    build_storages_source,
    read_storage_links,
    set_storage_values_persisted,
)
from interop.plugins.shared.osemosys_sienna_translations._storage_translations import (
    STORAGE_TRANSLATIONS,
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
    warn_one_way_lines,
)
from interop.plugins.shared.osemosys_sienna_translations._transport_imports import (
    build_import_extensions,
)
from interop.plugins.shared.osemosys_sienna_translations._transport_translations import (
    TRANSPORT_TRANSLATIONS,
)
from interop.plugins.shared.osemosys_sienna_translations._units import ModelUnits, parse_units

__all__ = [
    "CANDIDATE_VALUES",
    "BUS_TRANSLATIONS",
    "GENERATOR_NAME",
    "GENERATOR_TYPE_MAPPINGS",
    "LOAD_BASE_POWER_TRANSLATIONS",
    "LOAD_TRANSLATIONS",
    "SIENNA_TYPE",
    "STORAGE_TRANSLATIONS",
    "TRANSPORT_TRANSLATIONS",
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
    "append_per_unit_series",
    "build_bus_extensions",
    "build_buses_source_table",
    "build_calendar",
    "build_conversion_records",
    "build_conversions_source",
    "build_days_events",
    "build_fuel_loads_source",
    "build_fuel_modes_source",
    "build_generator_extensions",
    "build_generators_source",
    "build_import_extensions",
    "build_import_translations",
    "build_line_extensions",
    "build_load_series",
    "build_loads_source",
    "build_representative_periods",
    "build_routes_source",
    "build_storage_extensions",
    "build_storages_source",
    "build_transport_source",
    "enrich_technology_values",
    "list_model_years",
    "read_operations_mode",
    "parse_units",
    "read_electricity_fuels",
    "read_storage_links",
    "read_transport_ends",
    "report_calendar",
    "report_left_out_technologies",
    "report_unread_defaults",
    "require_model_year",
    "set_conversion_values_persisted",
    "set_days_persisted",
    "set_generator_values_persisted",
    "set_line_values_persisted",
    "set_operations_year",
    "set_storage_values_persisted",
    "warn_one_way_lines",
]
