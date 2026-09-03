"""Translation objects and helpers for Sienna Area derivation.

Areas are derived from the already-translated buses destination table, not from
the PyPSA source topology. ``build_areas_source`` aggregates the buses table to
one row per distinct area name, keeping a representative bus name as enrichment
context for the area_creation event. ``finalise`` drops the enrichment column.
"""

from __future__ import annotations

import polars as pl

from interop.plugins.shared.constants import Framework
from interop.plugins.shared.sienna_constants import (
    SIENNA_TYPE_ATTRIBUTE,
    SiennaACBusCol,
    SiennaAreaCol,
    SiennaComponent,
)
from interop.plugins.shared.translation_runner import Translation
from interop.ports.outbound.reporting import (
    DestinationField,
    EventKind,
    SourceField,
    TranslationEvent,
)

# Enrichment column: representative bus name for the area_creation event.
_REP_BUS_NAME = "rep_bus_name"


def build_areas_source_table(sienna_buses: pl.DataFrame) -> pl.DataFrame:
    """Aggregate the mapped Sienna buses into one row per distinct non-null area.

    Returns a DataFrame with columns ``name`` (area name) and ``rep_bus_name``
    (name of an arbitrary bus in that area, used for translation event attribution).
    Empty if no buses have a location.
    """
    return (
        sienna_buses.filter(pl.col(SiennaACBusCol.AREA).is_not_null())
        .group_by(SiennaACBusCol.AREA)
        .agg(pl.col(SiennaACBusCol.NAME).first().alias(_REP_BUS_NAME))
        .sort(SiennaACBusCol.AREA)
        .rename({SiennaACBusCol.AREA: SiennaAreaCol.NAME})
    )


AREA_ID = Translation(
    exprs=[pl.int_range(1, pl.len() + 1, dtype=pl.Int64).alias(SiennaAreaCol.ID)],
    make_events=lambda old, new: [
        TranslationEvent(
            kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
            destinations=[
                DestinationField(
                    framework=Framework.SIENNA,
                    component=SiennaComponent.AREA,
                    name=new[SiennaAreaCol.NAME],
                    attribute=SiennaAreaCol.ID,
                    value=new[SiennaAreaCol.ID],
                )
            ],
            note="assigned by 1-based row position in areas DataFrame",
        )
    ],
)

AREA_NAME = Translation(
    exprs=[pl.col(SiennaAreaCol.NAME)],  # identity — column already named correctly
    make_events=lambda old, new: [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                SourceField(
                    framework=Framework.SIENNA,
                    component=SiennaComponent.AC_BUS,
                    name=old[_REP_BUS_NAME],
                    attribute=SiennaACBusCol.AREA,
                    value=old[SiennaAreaCol.NAME],
                )
            ],
            destinations=[
                DestinationField(
                    framework=Framework.SIENNA,
                    component=SiennaComponent.AREA,
                    name=new[SiennaAreaCol.NAME],
                )
            ],
            derivation="one Area per distinct location",
        )
    ],
)

AREA_SIENNA_TYPE = Translation(
    exprs=[],
    make_events=lambda old, _: [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                SourceField(
                    framework=Framework.SIENNA,
                    component=SiennaComponent.AREA,
                    name=old[SiennaAreaCol.NAME],
                )
            ],
            destinations=[
                DestinationField(
                    framework=Framework.SIENNA,
                    component=SiennaComponent.AREA,
                    name=old[SiennaAreaCol.NAME],
                    attribute=SIENNA_TYPE_ATTRIBUTE,
                    value=SiennaComponent.AREA,
                )
            ],
            derivation="Area",
        )
    ],
)

AREA_TRANSLATIONS: list[Translation] = [AREA_ID, AREA_NAME, AREA_SIENNA_TYPE]
