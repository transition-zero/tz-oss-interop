"""A group that buses name, such as an Area or a LoadZone, derived from the mapped buses.

A bus names each group it sits in by name. ``build_bus_group_source_table`` gives one row
per distinct name, with one bus that names it for the event that creates the group.
``finalise`` drops that column.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import polars as pl

from interop.plugins.shared.constants import Framework
from interop.plugins.shared.sienna_constants import (
    SIENNA_NAME_COLUMN,
    SiennaACBusCol,
    SiennaComponent,
)
from interop.plugins.shared.translation_runner import Translation
from interop.ports.outbound.reporting import (
    DestinationField,
    EventKind,
    SourceField,
    TranslationEvent,
)

# One bus that names the group, for the event that creates the group.
REPRESENTATIVE_BUS_NAME = "representative_bus_name"


def build_bus_group_source_table(buses: pl.DataFrame, bus_column: str) -> pl.DataFrame:
    """One row per distinct group that ``bus_column`` names, with one bus that names it."""
    return (
        buses.filter(pl.col(bus_column).is_not_null())
        .group_by(bus_column)
        .agg(pl.col(SiennaACBusCol.NAME).first().alias(REPRESENTATIVE_BUS_NAME))
        .sort(bus_column)
        .rename({bus_column: SIENNA_NAME_COLUMN})
    )


def build_bus_group_name_translation(
    component: SiennaComponent, bus_column: str, derivation: str
) -> Translation:
    """A VALUE_DERIVED translation from the group name a bus states to the group it creates."""

    def make_events(old: dict[str, Any], new: dict[str, Any]) -> Sequence[TranslationEvent]:
        return [
            TranslationEvent(
                kind=EventKind.VALUE_DERIVED,
                sources=[
                    SourceField(
                        framework=Framework.SIENNA,
                        component=SiennaComponent.AC_BUS,
                        name=old[REPRESENTATIVE_BUS_NAME],
                        attribute=bus_column,
                        value=old[SIENNA_NAME_COLUMN],
                    )
                ],
                destinations=[
                    DestinationField(
                        framework=Framework.SIENNA,
                        component=component,
                        name=new[SIENNA_NAME_COLUMN],
                    )
                ],
                derivation=derivation,
            )
        ]

    return Translation(exprs=[pl.col(SIENNA_NAME_COLUMN)], make_events=make_events)
