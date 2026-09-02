"""Reshaping helpers every PLEXOS component mapping starts from.

``stage_plexos_xml`` hands over two long tables — one row per property value and one
row per relationship — rather than a frame per component. These turn that shape into
the per-object lookups a mapping reads while it walks its class.
"""

from __future__ import annotations

from collections.abc import Iterator
from enum import Enum, auto
from typing import Any

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.plexos_constants import (
    PlexosClass,
    PlexosCollection,
    PlexosMembershipCol,
    PlexosProperty,
    PlexosPropertyCol,
)
from interop.plugins.shared.plexos_pypsa_translations.constants import FULL_AVAILABILITY
from interop.plugins.shared.pypsa_constants import (
    PyPSABusCol,
    PyPSADestinationTable,
)
from interop.plugins.shared.pypsa_time_series import (
    metadata_row,
    series_components,
    series_timing,
)

# One object's property values, keyed by property name. A file-backed property carries
# no scalar value, so it is absent here and ``read_file_backed_properties`` finds it.
ObjectProperties = dict[str, dict[str, float]]

# The unit each of an object's properties is stated in, keyed the same way.
ObjectUnits = dict[str, dict[str, str | None]]


class MultiValueRule(Enum):
    """How to collapse a property that exports several values (bands) into one scalar.

    A banded property stages as several ``properties`` rows for the same object and
    property; which value applies depends on the property (doc: Special business rules).
    """

    FIRST = auto()
    LOWEST = auto()
    HIGHEST = auto()


def _has_property_columns(properties: pl.LazyFrame) -> bool:
    """A model with no property values at all stages a column-less properties frame."""
    return PlexosPropertyCol.CHILD_CLASS in properties.collect_schema().names()


def _has_membership_columns(memberships: pl.LazyFrame) -> bool:
    """A model with no relationships at all stages a column-less memberships frame."""
    return PlexosMembershipCol.PARENT_CLASS in memberships.collect_schema().names()


def collapse_properties_by_object(
    properties: pl.LazyFrame,
    plexos_class: PlexosClass,
    rules: dict[str, MultiValueRule] | None = None,
    *,
    default: MultiValueRule = MultiValueRule.FIRST,
) -> ObjectProperties:
    """Per-object property values for one class, each banded property collapsed per its rule.

    A line's ``Max Flow`` takes the lowest band, ``Min Flow`` the highest, impedance the
    first. A property absent from ``rules`` uses ``default`` (first in band order). Null
    (file-backed) values are dropped, so a purely file-backed property is absent from the
    result and ``read_file_backed_properties`` is what finds it.
    """
    rules = rules or {}
    banded: dict[str, dict[str, list[float]]] = {}
    for row in read_property_rows(properties, plexos_class).iter_rows(named=True):
        value = row[PlexosPropertyCol.VALUE]
        if value is not None:
            values = banded.setdefault(row[PlexosPropertyCol.CHILD_OBJECT], {})
            values.setdefault(row[PlexosPropertyCol.PROPERTY], []).append(value)
    return {
        name: {
            property_name: _reduce(values, rules.get(property_name, default))
            for property_name, values in by_property.items()
        }
        for name, by_property in banded.items()
    }


def _reduce(values: list[float], rule: MultiValueRule) -> float:
    match rule:
        case MultiValueRule.FIRST:
            return values[0]
        case MultiValueRule.LOWEST:
            return min(values)
        case MultiValueRule.HIGHEST:
            return max(values)


def collapse_membership_properties_by_parent(
    properties: pl.LazyFrame,
    parent_class: PlexosClass,
    collection: PlexosCollection,
    rule: MultiValueRule = MultiValueRule.FIRST,
) -> ObjectProperties:
    """Per-parent property values for one membership collection, collapsed per ``rule``.

    ``collapse_properties_by_object`` keys a value by the child object, which is what a
    property describing the child wants. A property whose subject is the parent — the fuel
    a generator burns to start, stated on the Generator to Fuel membership — belongs to
    that parent, so its values collapse across every child the parent relates to as well as
    across the bands of each. Null (file-backed) values are dropped, as they are there.
    """
    banded: dict[str, dict[str, list[float]]] = {}
    for row in _read_membership_property_rows(properties, parent_class, collection):
        name, property_name, value = row
        banded.setdefault(name, {}).setdefault(property_name, []).append(value)
    return {
        name: {
            property_name: _reduce(values, rule) for property_name, values in by_property.items()
        }
        for name, by_property in banded.items()
    }


def _read_membership_property_rows(
    properties: pl.LazyFrame, parent_class: PlexosClass, collection: PlexosCollection
) -> Iterator[tuple[str, str, float]]:
    """(parent, property, value) for one collection's properties, in band order."""
    if not _has_property_columns(properties):
        return iter(())
    frame = (
        properties.filter(
            (pl.col(PlexosPropertyCol.PARENT_CLASS) == parent_class)
            & (pl.col(PlexosPropertyCol.COLLECTION) == collection)
            & pl.col(PlexosPropertyCol.VALUE).is_not_null()
        )
        .sort(
            PlexosPropertyCol.PARENT_OBJECT,
            PlexosPropertyCol.PROPERTY,
            # Bands are staged as text, so a lexicographic sort would put band 10 first.
            pl.col(PlexosPropertyCol.BAND).cast(pl.Int64, strict=False),
        )
        .select(
            PlexosPropertyCol.PARENT_OBJECT,
            PlexosPropertyCol.PROPERTY,
            PlexosPropertyCol.VALUE,
        )
        .collect()
    )
    return frame.iter_rows()


def collapse_units_by_object(properties: pl.LazyFrame, plexos_class: PlexosClass) -> ObjectUnits:
    """The unit each object states each of its properties in, first band winning.

    A value converts to the unit interop reads it in as it stages, so a mapping asks this
    only where the stated unit decides what the value means at all.
    """
    units: ObjectUnits = {}
    for row in read_property_rows(properties, plexos_class).iter_rows(named=True):
        by_property = units.setdefault(row[PlexosPropertyCol.CHILD_OBJECT], {})
        by_property.setdefault(row[PlexosPropertyCol.PROPERTY], row[PlexosPropertyCol.UNIT])
    return units


def read_property_rows(properties: pl.LazyFrame, plexos_class: PlexosClass) -> pl.DataFrame:
    """One class's resolved properties, one row per object per property per band.

    Keeps every band, the stated unit, and the ``data_file`` path that
    ``collapse_properties_by_object`` drops, for a mapping that must carry a property as
    PLEXOS states it rather than as one value.
    """
    if not _has_property_columns(properties):
        return pl.DataFrame()
    return (
        properties.filter(pl.col(PlexosPropertyCol.CHILD_CLASS) == plexos_class)
        .select(
            PlexosPropertyCol.CHILD_OBJECT,
            PlexosPropertyCol.PROPERTY,
            PlexosPropertyCol.BAND,
            PlexosPropertyCol.VALUE,
            PlexosPropertyCol.UNIT,
            PlexosPropertyCol.DATA_FILE,
        )
        .sort(
            PlexosPropertyCol.CHILD_OBJECT,
            PlexosPropertyCol.PROPERTY,
            # Bands are staged as text, so a lexicographic sort would put band 10 first.
            pl.col(PlexosPropertyCol.BAND).cast(pl.Int64, strict=False),
        )
        .collect()
    )


def read_file_backed_properties(
    properties: pl.LazyFrame, plexos_class: PlexosClass
) -> dict[str, list[str]]:
    """Which properties of each object of a class are file-backed.

    A file-backed property has no scalar value; its values live in
    ``State.source_time_series`` under ``(class, property)``.
    """
    if not _has_property_columns(properties):
        return {}
    frame = (
        properties.filter(
            (pl.col(PlexosPropertyCol.CHILD_CLASS) == plexos_class)
            & pl.col(PlexosPropertyCol.DATA_FILE).is_not_null()
        )
        .select(PlexosPropertyCol.CHILD_OBJECT, PlexosPropertyCol.PROPERTY)
        .unique()
        .collect()
    )
    result: dict[str, list[str]] = {}
    for name, property_name in frame.iter_rows():
        result.setdefault(name, []).append(property_name)
    return result


def relate_children(
    memberships: pl.LazyFrame,
    parent_class: PlexosClass,
    collection: PlexosCollection,
) -> dict[str, list[str]]:
    """Every child each object of ``parent_class`` relates to under ``collection``.

    The collection is part of the key because one pair of classes can be related more
    than once: a pumped-storage generator reaches one Storage as its ``Head Storage``
    and another as its ``Tail Storage``.
    """
    result: dict[str, list[str]] = {}
    for parent, child in _membership_pairs(memberships, parent_class, collection):
        children = result.setdefault(parent, [])
        if child not in children:
            children.append(child)
    return result


def relate_child(
    memberships: pl.LazyFrame,
    parent_class: PlexosClass,
    collection: PlexosCollection,
) -> dict[str, str]:
    """The one child each object of ``parent_class`` relates to under ``collection``."""
    related = relate_children(memberships, parent_class, collection)
    return {parent: children[0] for parent, children in related.items()}


def relate_parent(
    memberships: pl.LazyFrame,
    parent_class: PlexosClass,
    collection: PlexosCollection,
) -> dict[str, str]:
    """The ``parent_class`` object each child belongs to under ``collection``."""
    return dict(
        (child, parent)
        for parent, child in _membership_pairs(memberships, parent_class, collection)
    )


def _membership_pairs(
    memberships: pl.LazyFrame,
    parent_class: PlexosClass,
    collection: PlexosCollection,
) -> Iterator[tuple[str, str]]:
    if not _has_membership_columns(memberships):
        return iter(())
    frame = (
        memberships.filter(
            (pl.col(PlexosMembershipCol.PARENT_CLASS) == parent_class)
            & (pl.col(PlexosMembershipCol.COLLECTION) == collection)
        )
        .select(PlexosMembershipCol.PARENT_OBJECT, PlexosMembershipCol.CHILD_OBJECT)
        .collect()
    )
    return frame.iter_rows()


def built_bus_names(state: State) -> set[str]:
    """Names of the buses the bus mapping actually wrote.

    Every later mapping resolves its bus references against this set rather than
    re-deriving which PLEXOS Nodes are buses.
    """
    buses = state.destination_tables.get(PyPSADestinationTable.BUSES)
    if buses is None:
        return set()
    return set(buses[PyPSABusCol.NAME].to_list())


def outage_time_series(
    state: State,
    owner_class: PlexosClass,
    destination_table: str,
    attribute: str,
    units_by_object: dict[str, float],
) -> list[dict[str, Any]]:
    """The trace counts units unavailable, so the fraction still available is one less the
    count over the object's unit count. It compounds with any rating profile already emitted
    for the same attribute rather than replacing it.
    """
    frame = state.source_time_series.get((owner_class, PlexosProperty.UNITS_OUT))
    if frame is None:
        return []
    timing = series_timing(frame)
    present = set(series_components(frame))
    return [
        metadata_row(
            component_table=destination_table,
            component_name=name,
            attribute=attribute,
            source_owner_type=owner_class,
            source_series_name=PlexosProperty.UNITS_OUT,
            scaling_factor=-1.0 / units,
            offset=FULL_AVAILABILITY,
            timing=timing,
        )
        for name, units in sorted(units_by_object.items())
        if name in present and units
    ]
