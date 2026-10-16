"""Leaves out the part of a canonical stage that lies outside a scope of locations and years."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import NamedTuple

import polars as pl

from interop.core.pipeline import State
from interop.core.reporting import EventRecorder
from interop.plugins.shared.osemosys_canonical.canonical_stage import (
    CanonicalTable,
    build_table_key,
    list_canonical_tables,
    set_canonical_table,
)
from interop.plugins.shared.osemosys_canonical.constants import (
    FUEL,
    LOCATION_SEPARATOR,
    STORAGE,
    TECHNOLOGY,
    VALUE_COL,
    YEAR,
    AnnotationColumn,
    TableKind,
)
from interop.plugins.shared.osemosys_canonical.events import SourceName, record_source_event
from interop.plugins.shared.warning_text import name_a_few
from interop.ports.outbound.reporting import EventKind

log = logging.getLogger(__name__)

# The sets whose members the annotations place at a location.
LOCATED_SETS = (TECHNOLOGY, FUEL, STORAGE)
# The temporary column of the group that tells if a member has a row in scope.
_IS_IN_SCOPE_COL = "__is_in_scope"


class Scope(NamedTuple):
    """An empty `locations` or `years` keeps everything."""

    locations: tuple[str, ...]
    years: tuple[int, ...]

    @property
    def has_locations(self) -> bool:
        return bool(self.locations)

    @property
    def has_years(self) -> bool:
        return bool(self.years)


def set_scoped_tables(state: State, dropped: Mapping[str, list[str]]) -> None:
    """Replace each canonical table with the table that holds no dropped member."""
    for canonical in list_canonical_tables(state):
        set_canonical_table(state, canonical._replace(table=_drop_from_table(canonical, dropped)))


def build_dropped_members(state: State, scope: Scope) -> dict[str, list[str]]:
    """The members to leave out, by the set that holds them. A year is a member of `year`."""
    dropped = {
        set_name: _list_members_outside_locations(state, set_name, scope)
        for set_name in LOCATED_SETS
    }
    dropped[YEAR] = _list_years_outside_scope(state, scope)
    return {set_name: members for set_name, members in dropped.items() if members}


def _list_members_outside_locations(state: State, set_name: str, scope: Scope) -> list[str]:
    annotation = state.source_topology.get(build_table_key(TableKind.ANNOTATION, set_name))
    if annotation is None or not scope.has_locations:
        return []
    has_row_in_scope = _express_is_in_scope(scope).any().alias(_IS_IN_SCOPE_COL)
    outside = annotation.group_by(set_name).agg(has_row_in_scope).filter(~pl.col(_IS_IN_SCOPE_COL))
    return outside.select(set_name).sort(set_name).collect().to_series().to_list()


def _express_is_in_scope(scope: Scope) -> pl.Expr:
    """A member with no location is in scope, and so is one whose every location part is."""
    location = pl.col(AnnotationColumn.LOCATION)
    parts_in_scope = (
        location.str.split(LOCATION_SEPARATOR)
        .list.eval(pl.element().is_in(list(scope.locations)))
        .list.all()
    )
    return location.is_null() | parts_in_scope


def _list_years_outside_scope(state: State, scope: Scope) -> list[str]:
    years = state.source_topology.get(build_table_key(TableKind.SET, YEAR))
    if years is None or not scope.has_years:
        return []
    members = years.select(pl.col(VALUE_COL).cast(pl.String)).collect().to_series().to_list()
    kept = _list_year_names(scope)
    return [member for member in members if member not in kept]


def _list_year_names(scope: Scope) -> list[str]:
    return [str(year) for year in scope.years]


def _drop_from_table(canonical: CanonicalTable, dropped: Mapping[str, list[str]]) -> pl.LazyFrame:
    columns = canonical.table.collect_schema().names()
    table = canonical.table
    for set_name, members in dropped.items():
        column = _find_set_column(canonical, set_name, columns)
        if column is not None:
            table = table.filter(~pl.col(column).cast(pl.String).is_in(members).fill_null(False))
    return table


def _find_set_column(canonical: CanonicalTable, set_name: str, columns: list[str]) -> str | None:
    """The column that holds the members of `set_name`, or `None` where the table has none."""
    if canonical.kind == TableKind.SET and canonical.name == set_name:
        return VALUE_COL
    return set_name if set_name in columns else None


def report_dropped(dropped: Mapping[str, list[str]], recorder: EventRecorder) -> None:
    for set_name, members in dropped.items():
        note = f"{len(members)} {set_name} member(s) outside the scope, so each is left out"
        record_source_event(
            recorder, EventKind.COMPONENT_SKIPPED, SourceName(set_name, name_a_few(members)), note
        )
    if dropped:
        counted = ", ".join(f"{len(members)} {set_name}" for set_name, members in dropped.items())
        names = name_a_few(member for members in dropped.values() for member in members)
        log.warning("Left out %s member(s) that are outside the scope: %s", counted, names)
