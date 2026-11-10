"""Translation objects for the Sienna Area table, derived from the mapped buses.

``build_bus_group_source_table`` gives one row per distinct area that a bus names.
"""

from __future__ import annotations

from functools import partial

from interop.plugins.shared.constants import Framework
from interop.plugins.shared.pypsa_sienna_translations._bus_groups import (
    build_bus_group_name_translation,
)
from interop.plugins.shared.pypsa_sienna_translations._units import AREA_UNIT_TRANSLATIONS
from interop.plugins.shared.sienna_constants import (
    SIENNA_TYPE_ATTRIBUTE,
    SiennaACBusCol,
    SiennaAreaCol,
    SiennaComponent,
)
from interop.plugins.shared.sienna_events import build_sienna_field
from interop.plugins.shared.translation_runner import (
    Translation,
    build_document_id_translation,
)
from interop.ports.outbound.reporting import (
    DestinationField,
    EventKind,
    SourceField,
    TranslationEvent,
)

AREA_ID = build_document_id_translation(
    partial(build_sienna_field, SiennaComponent.AREA),
    dest_name_col=SiennaAreaCol.NAME,
    id_col=SiennaAreaCol.ID,
    note="assigned by row position in the Area table, after the ids of earlier components",
)

AREA_NAME = build_bus_group_name_translation(
    SiennaComponent.AREA, SiennaACBusCol.AREA, "one Area per distinct location"
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

AREA_TRANSLATIONS: list[Translation] = [
    *AREA_UNIT_TRANSLATIONS,
    AREA_ID,
    AREA_NAME,
    AREA_SIENNA_TYPE,
]
