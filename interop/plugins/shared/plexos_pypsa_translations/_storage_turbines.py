"""Which PLEXOS Generators belong to the storage-unit mapping rather than the generator one.

PLEXOS has no hydro or pumped-storage class: both are ordinary ``Generator`` objects, told
apart by the reservoirs they are linked to. Both mappings walk the Generator class, so this
is the single home for that split — without it a turbine is translated twice, once as a
``Generator`` and once as a ``StorageUnit``, and its capacity is counted twice.
"""

from __future__ import annotations

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.plexos_constants import (
    PlexosClass,
    PlexosCollection,
    PlexosProperty,
    PlexosResolvedTable,
)
from interop.plugins.shared.plexos_pypsa_translations._shared import (
    collapse_properties_by_object,
    relate_children,
)


def can_pump(properties: dict[str, float]) -> bool:
    """Whether a Generator states a Pump Load above zero, which is the most MW it draws to pump."""
    return properties.get(PlexosProperty.PUMP_LOAD, 0.0) > 0.0


def storage_turbine_names(state: State) -> frozenset[str]:
    """Generators the storage-unit mapping claims: linked to a reservoir, or able to pump.

    A tail-only turbine is claimed too. The storage mapping skips it with an event naming
    the missing head, so leaving it to the generator mapping would translate a broken
    pumped-storage plant as a thermal unit.
    """
    memberships = state.source_topology[PlexosResolvedTable.MEMBERSHIPS]
    properties = state.source_topology[PlexosResolvedTable.PROPERTIES]
    return frozenset(
        _linked_to(memberships, PlexosCollection.HEAD_STORAGE)
        | _linked_to(memberships, PlexosCollection.TAIL_STORAGE)
        | _list_pumps(properties)
    )


def _linked_to(memberships: pl.LazyFrame, collection: PlexosCollection) -> set[str]:
    return set(relate_children(memberships, PlexosClass.GENERATOR, collection))


def _list_pumps(properties: pl.LazyFrame) -> set[str]:
    generators = collapse_properties_by_object(properties, PlexosClass.GENERATOR)
    return {name for name, stated in generators.items() if can_pump(stated)}
