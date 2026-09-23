"""PLEXOS to Sienna translations, one module per component group.

Each module states what one PLEXOS class becomes in Sienna words. Nothing here reads or
writes a PyPSA table: the step that uses these translations is one hop, so PyPSA takes no
part in it.
"""

from __future__ import annotations

from interop.plugins.shared.plexos_sienna_translations._buses import (
    BUS_TRANSLATIONS,
    build_bus_extensions,
    build_buses_source_table,
)
from interop.plugins.shared.plexos_sienna_translations._carriers import (
    CarrierTarget,
    CarrierTargets,
)
from interop.plugins.shared.plexos_sienna_translations._generators import (
    generator_schema,
    generator_types,
    map_generators,
)
from interop.plugins.shared.plexos_sienna_translations._loads import (
    LOAD_BASE_POWER_TRANSLATIONS,
    LOAD_TRANSLATIONS,
    NODE_LOAD_SERIES_KEY,
    REGION_LOAD_SERIES_KEY,
    build_load_extensions,
    build_load_ts_associations,
    build_loads_source_table,
)
from interop.plugins.shared.plexos_sienna_translations._transmission import (
    map_transmission,
)

__all__ = [
    "BUS_TRANSLATIONS",
    "CarrierTarget",
    "CarrierTargets",
    "generator_schema",
    "generator_types",
    "map_generators",
    "map_transmission",
    "LOAD_BASE_POWER_TRANSLATIONS",
    "LOAD_TRANSLATIONS",
    "NODE_LOAD_SERIES_KEY",
    "REGION_LOAD_SERIES_KEY",
    "build_bus_extensions",
    "build_buses_source_table",
    "build_load_extensions",
    "build_load_ts_associations",
    "build_loads_source_table",
]
