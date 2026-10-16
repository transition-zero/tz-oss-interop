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
from interop.plugins.shared.osemosys_sienna_translations._left_out import (
    report_left_out_technologies,
)
from interop.plugins.shared.osemosys_sienna_translations._loads import (
    LOAD_BASE_POWER_TRANSLATIONS,
    LOAD_TRANSLATIONS,
    LoadSources,
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
)
from interop.plugins.shared.osemosys_sienna_translations._storage import (
    build_storage_extensions,
    build_storage_technologies,
    build_storages_source,
    read_storage_links,
)
from interop.plugins.shared.osemosys_sienna_translations._storage_translations import (
    STORAGE_TRANSLATIONS,
)
from interop.plugins.shared.osemosys_sienna_translations._technologies import (
    report_unread_capacity_factors,
)
from interop.plugins.shared.osemosys_sienna_translations._transport import (
    build_line_extensions,
    build_transport_source,
    read_transport_ends,
    warn_one_way_lines,
)
from interop.plugins.shared.osemosys_sienna_translations._transport_translations import (
    TRANSPORT_TRANSLATIONS,
)
from interop.plugins.shared.osemosys_sienna_translations._unapplied_parameters import (
    INVESTMENTS_PARAMETERS,
    OPERATIONS_PARAMETERS,
    report_unapplied_parameters,
)
from interop.plugins.shared.osemosys_sienna_translations._units import ModelUnits, parse_units

__all__ = [
    "BUS_TRANSLATIONS",
    "GENERATOR_NAME",
    "GENERATOR_TYPE_MAPPINGS",
    "INVESTMENTS_PARAMETERS",
    "LOAD_BASE_POWER_TRANSLATIONS",
    "LOAD_TRANSLATIONS",
    "OPERATIONS_PARAMETERS",
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
    "build_bus_extensions",
    "build_buses_source_table",
    "build_calendar",
    "build_generator_extensions",
    "build_generators_source",
    "build_line_extensions",
    "build_load_series",
    "build_loads_source",
    "build_representative_periods",
    "build_storage_extensions",
    "build_storage_technologies",
    "build_storages_source",
    "build_transport_source",
    "read_operations_mode",
    "parse_units",
    "read_electricity_fuels",
    "read_storage_links",
    "read_transport_ends",
    "report_calendar",
    "report_left_out_technologies",
    "report_unapplied_parameters",
    "report_unread_capacity_factors",
    "require_model_year",
    "set_operations_year",
    "warn_one_way_lines",
]
