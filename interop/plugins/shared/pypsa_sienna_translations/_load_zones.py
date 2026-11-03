"""Translation objects for the Sienna LoadZone table, derived from the mapped buses.

A bus names the load zone it sits in by name. ``build_load_zones_source_table`` gives one
row per distinct name, with a representative bus for the event that creates the zone.
``finalise`` drops that column.
"""

from __future__ import annotations

from functools import partial

import polars as pl

from interop.plugins.shared.constants import UNIT_MVA, UNIT_MVAR, UNIT_MW, Framework
from interop.plugins.shared.pypsa_sienna_translations._shared import sienna_dest_field
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
from interop.plugins.shared.translation_runner import (
    Translation,
    default_translation,
    express_document_id,
)
from interop.ports.outbound.reporting import (
    DestinationField,
    EventKind,
    SourceField,
    TranslationEvent,
)

_REP_BUS_NAME = "rep_bus_name"
# A load zone states no peak of its own in any source the translator reads.
_NO_PEAK = 0.0

_ID_NOTE = "assigned by row position in the LoadZone table, after the ids of earlier components"
_UNITS_NOTE = "LoadZone power values are in MW, so the units are NATURAL_UNITS"
_BASE_POWER_NOTE = "the source states no power base for a load zone; the system base applies"
_PEAK_NOTE = "the source states no peak for a load zone; the peak is 0"

_load_zone_field = partial(sienna_dest_field, SiennaComponent.LOAD_ZONE)


def build_load_zones_source_table(sienna_buses: pl.DataFrame) -> pl.DataFrame:
    """One row per distinct load zone the buses name, with one bus that names it."""
    return (
        sienna_buses.filter(pl.col(SiennaACBusCol.LOAD_ZONE).is_not_null())
        .group_by(SiennaACBusCol.LOAD_ZONE)
        .agg(pl.col(SiennaACBusCol.NAME).first().alias(_REP_BUS_NAME))
        .sort(SiennaACBusCol.LOAD_ZONE)
        .rename({SiennaACBusCol.LOAD_ZONE: SiennaLoadZoneCol.NAME})
    )


LOAD_ZONE_ID = Translation(
    exprs=[express_document_id().alias(SiennaLoadZoneCol.ID)],
    make_events=lambda old, new: [
        TranslationEvent(
            kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
            destinations=[
                _load_zone_field(
                    new[SiennaLoadZoneCol.NAME], SiennaLoadZoneCol.ID, new[SiennaLoadZoneCol.ID]
                )
            ],
            note=_ID_NOTE,
        )
    ],
)

LOAD_ZONE_NAME = Translation(
    exprs=[pl.col(SiennaLoadZoneCol.NAME)],
    make_events=lambda old, new: [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                SourceField(
                    framework=Framework.SIENNA,
                    component=SiennaComponent.AC_BUS,
                    name=old[_REP_BUS_NAME],
                    attribute=SiennaACBusCol.LOAD_ZONE,
                    value=old[SiennaLoadZoneCol.NAME],
                )
            ],
            destinations=[
                DestinationField(
                    framework=Framework.SIENNA,
                    component=SiennaComponent.LOAD_ZONE,
                    name=new[SiennaLoadZoneCol.NAME],
                )
            ],
            derivation="one LoadZone per distinct load zone a bus names",
        )
    ],
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
