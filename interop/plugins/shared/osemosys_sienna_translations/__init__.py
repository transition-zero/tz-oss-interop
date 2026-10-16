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
    add_series,
)
from interop.plugins.shared.osemosys_sienna_translations._units import ModelUnits, parse_units

__all__ = [
    "BUS_TRANSLATIONS",
    "LOAD_BASE_POWER_TRANSLATIONS",
    "LOAD_TRANSLATIONS",
    "Calendar",
    "LoadSources",
    "ModelUnits",
    "OperationsMapping",
    "OperationsYear",
    "StagedSeries",
    "add_series",
    "build_bus_extensions",
    "build_buses_source_table",
    "build_calendar",
    "build_loads_source",
    "build_representative_periods",
    "parse_units",
    "read_electricity_fuels",
    "report_calendar",
    "require_model_year",
]
