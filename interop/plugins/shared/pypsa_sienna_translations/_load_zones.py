"""Translation objects for the Sienna LoadZone table, derived from the mapped buses.

``build_bus_group_source_table`` gives one row per distinct load zone that a bus names.
"""

from __future__ import annotations

from functools import partial

import polars as pl

from interop.plugins.shared.constants import UNIT_MVA, UNIT_MVAR, UNIT_MW
from interop.plugins.shared.pypsa_sienna_translations._bus_groups import (
    build_bus_group_name_translation,
)
from interop.plugins.shared.pypsa_sienna_translations._units import (
    build_power_units_translation,
)
from interop.plugins.shared.sienna_constants import (
    SYSTEM_BASE_MVA,
    SiennaACBusCol,
    SiennaComponent,
    SiennaLoadZoneCol,
    SiennaUnitSystem,
)
from interop.plugins.shared.sienna_events import build_sienna_field
from interop.plugins.shared.translation_runner import (
    Translation,
    build_document_id_translation,
    default_translation,
)

# A load zone states no peak of its own in any source the translator reads.
_NO_PEAK = 0.0

_ID_NOTE = "assigned by row position in the LoadZone table, after the ids of earlier components"
_UNITS_NOTE = "LoadZone power values are in MW, so the units are NATURAL_UNITS"
_BASE_POWER_NOTE = "the source states no power base for a load zone; the system base applies"
_PEAK_NOTE = "the source states no peak for a load zone; the peak is 0"

_load_zone_field = partial(build_sienna_field, SiennaComponent.LOAD_ZONE)

LOAD_ZONE_ID = build_document_id_translation(
    _load_zone_field,
    dest_name_col=SiennaLoadZoneCol.NAME,
    id_col=SiennaLoadZoneCol.ID,
    note=_ID_NOTE,
)

LOAD_ZONE_NAME = build_bus_group_name_translation(
    SiennaComponent.LOAD_ZONE,
    SiennaACBusCol.LOAD_ZONE,
    "one LoadZone per distinct load zone a bus names",
)


def _peak_translation(dest_col: str, unit: str) -> Translation:
    return default_translation(
        _load_zone_field,
        name_col=SiennaLoadZoneCol.NAME,
        dest_col=dest_col,
        value=_NO_PEAK,
        note=_PEAK_NOTE,
        dtype=pl.Float64,
        unit=unit,
    )


LOAD_ZONE_TRANSLATIONS: list[Translation] = [
    LOAD_ZONE_ID,
    LOAD_ZONE_NAME,
    _peak_translation(SiennaLoadZoneCol.PEAK_ACTIVE_POWER, UNIT_MW),
    _peak_translation(SiennaLoadZoneCol.PEAK_REACTIVE_POWER, UNIT_MVAR),
    default_translation(
        _load_zone_field,
        name_col=SiennaLoadZoneCol.NAME,
        dest_col=SiennaLoadZoneCol.BASE_POWER,
        value=SYSTEM_BASE_MVA,
        note=_BASE_POWER_NOTE,
        dtype=pl.Float64,
        unit=UNIT_MVA,
    ),
    build_power_units_translation(
        _load_zone_field,
        name_col=SiennaLoadZoneCol.NAME,
        dest_col=SiennaLoadZoneCol.POWER_UNITS,
        units=SiennaUnitSystem.NATURAL_UNITS,
        note=_UNITS_NOTE,
    ),
]
