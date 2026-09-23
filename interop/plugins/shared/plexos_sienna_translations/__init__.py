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

__all__ = [
    "BUS_TRANSLATIONS",
    "build_bus_extensions",
    "build_buses_source_table",
]
