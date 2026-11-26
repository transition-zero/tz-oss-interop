"""The set tables that only a parameter key names.

A set whose members a Sienna component states directly is written by the step that reads that
component: `region` and `fuel` come from the buses. Every other set exists only as the key of a
parameter, so this builds it from the parameter tables that the component steps wrote, and it
writes no member that no parameter table names.
"""

from __future__ import annotations

import polars as pl

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import ALL_COMPONENTS
from interop.plugins.shared.osemosys_canonical.canonical_stage import (
    list_destination_canonical_tables,
)
from interop.plugins.shared.osemosys_canonical.constants import TableKind
from interop.plugins.shared.osemosys_canonical.schema import load_canonical_schema
from interop.plugins.shared.sienna_osemosys_translations.destination import (
    list_destination_parameter_tables,
    set_set_table,
)
from interop.plugins.shared.sienna_osemosys_translations.events import (
    build_derived,
    build_osemosys_member,
)

_MEMBER_COL = "member"
_DERIVATION = "the {count} member(s) that a parameter table of the written model names"


def set_derived_set_tables(state: State, recorder: ScopedRecorder) -> None:
    """One set table for each set that a parameter table names and no component step wrote."""
    held = _list_held_set_names(state)
    members = _build_members_by_set(state)
    for set_name, found in sorted(members.items()):
        if set_name not in held:
            set_set_table(state, set_name, found)
            _record_set(set_name, found, recorder)


def _list_held_set_names(state: State) -> set[str]:
    return {
        canonical.name
        for canonical in list_destination_canonical_tables(state)
        if canonical.kind is TableKind.SET
    }


def _build_members_by_set(state: State) -> dict[str, list[str]]:
    """The members that each parameter table names, by the set that holds the column."""
    schema = load_canonical_schema()
    members: dict[str, set[str]] = {}
    for name, table in list_destination_parameter_tables(state).items():
        entry = schema.parameters[name]
        for column in entry.column_names:
            found = members.setdefault(entry.get_column_set(column), set())
            found.update(_list_column_members(table, column))
    return {set_name: sorted(found) for set_name, found in members.items() if found}


def _list_column_members(table: pl.LazyFrame, column: str) -> list[str]:
    distinct = table.select(pl.col(column).cast(pl.Utf8).alias(_MEMBER_COL)).unique().collect()
    return [member for member in distinct[_MEMBER_COL].to_list() if member is not None]


def _record_set(set_name: str, members: list[str], recorder: ScopedRecorder) -> None:
    """One event for the whole set, because a model of 8760 hours holds 8760 timeslices."""
    destination = build_osemosys_member(set_name, ALL_COMPONENTS)
    derivation = _DERIVATION.format(count=len(members))
    recorder.append(build_derived([], [destination], derivation))
