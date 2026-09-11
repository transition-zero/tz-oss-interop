"""The buses each region holds: the Sienna TopologyMapping supplemental attribute.

A portfolio groups its technologies by region and the base system holds the buses, so the
mapping between the two travels as an attribute of the region rather than as a component.
"""

from __future__ import annotations

from functools import partial

import polars as pl

from interop.plugins.shared.constants import Framework
from interop.plugins.shared.pypsa_sienna_translations._shared import sienna_dest_field
from interop.plugins.shared.sienna_constants import SiennaACBusCol, SiennaComponent
from interop.plugins.shared.sienna_investments_constants import (
    SiennaSupplementalAttribute,
    SiennaTopologyMappingCol,
)
from interop.plugins.shared.translation_runner import Translation, row_position_id_translation
from interop.ports.outbound.reporting import EventKind, SourceField, TranslationEvent

# Source-table column holding the region a mapping describes; not a schema field.
AREA_NAME = "area_name"

T = SiennaTopologyMappingCol

_dest = partial(sienna_dest_field, SiennaSupplementalAttribute.TOPOLOGY_MAPPING)


def build_topology_source_table(buses: pl.DataFrame) -> pl.DataFrame:
    """One row per area of the base system, holding the names of the buses in it."""
    return (
        buses.filter(pl.col(SiennaACBusCol.AREA).is_not_null())
        .group_by(SiennaACBusCol.AREA)
        .agg(pl.col(SiennaACBusCol.NAME).alias(T.BUSES))
        .sort(SiennaACBusCol.AREA)
        .rename({SiennaACBusCol.AREA: AREA_NAME})
    )


TOPOLOGY_BUSES = Translation(
    exprs=[pl.col(T.BUSES)],  # identity: the aggregation already named the column
    make_events=lambda old, new: [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                SourceField(
                    framework=Framework.SIENNA,
                    component=SiennaComponent.AC_BUS,
                    name=bus,
                    attribute=SiennaACBusCol.AREA,
                    value=old[AREA_NAME],
                )
                for bus in old[T.BUSES]
            ],
            destinations=[_dest(old[AREA_NAME], T.BUSES, new[T.BUSES])],
            derivation="the buses of the base system that sit in this area",
        )
    ],
)


def build_topology_mapping_translations(start: int) -> list[Translation]:
    """The TopologyMapping attributes, taking ids from the counter the flat array shares."""
    return [
        row_position_id_translation(
            _dest,
            dest_name_col=AREA_NAME,
            id_col=T.ID,
            note="assigned by position in the portfolio's flat supplemental attribute array",
            start=start,
        ),
        TOPOLOGY_BUSES,
    ]
