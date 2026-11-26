"""The set tables that a parameter key names.

A set whose members a Sienna component states directly is written by the step that reads that
component: `region` and `fuel` come from the buses. Every other set exists only as the key of
a parameter, so this builds it from the parameter tables that the component steps wrote, and
it writes no member that no parameter table names.

A parameter can also name a member of a set that a component step wrote: a fuel that a plant
burns and no bus balances is a member of `fuel` that no bus states. So a set that a component
step wrote keeps its own members and gains each member that a parameter table names.
"""

from __future__ import annotations

import polars as pl

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import ALL_COMPONENTS
from interop.plugins.shared.osemosys_canonical.canonical_stage import (
    list_destination_canonical_tables,
)
from interop.plugins.shared.osemosys_canonical.constants import VALUE_COL, TableKind
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
_ADDED_DERIVATION = (
    "the {count} member(s) that a parameter table of the written model names and that no "
    "Sienna component states"
)


def set_derived_set_tables(state: State, recorder: ScopedRecorder) -> None:
    """Each set that a parameter table names, over the members that a component step wrote."""
    written = _build_written_members(state)
    for set_name, named in sorted(_build_members_by_set(state).items()):
        _set_one_table(state, set_name, written.get(set_name), named, recorder)


def _set_one_table(
    state: State,
    set_name: str,
    written: list[str] | None,
    named: list[str],
    recorder: ScopedRecorder,
) -> None:
    """A set that no component step wrote is the members a parameter names; any other grows."""
    if written is None:
        set_set_table(state, set_name, named)
        _record_set(set_name, len(named), _DERIVATION, recorder)
        return
    added = [member for member in named if member not in set(written)]
    if not added:
        return
    set_set_table(state, set_name, [*written, *added])
    _record_set(set_name, len(added), _ADDED_DERIVATION, recorder)


def _build_written_members(state: State) -> dict[str, list[str]]:
    """The members of each set table that a component step of this hop already wrote."""
    return {
        canonical.name: _list_table_members(canonical.table)
        for canonical in list_destination_canonical_tables(state)
        if canonical.kind is TableKind.SET
    }


def _list_table_members(table: pl.LazyFrame) -> list[str]:
    members = table.select(pl.col(VALUE_COL).cast(pl.Utf8)).collect()
    return [member for member in members[VALUE_COL].to_list() if member is not None]


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


def _record_set(set_name: str, count: int, derivation: str, recorder: ScopedRecorder) -> None:
    """One event for the whole set, because a model of 8760 hours holds 8760 timeslices."""
    destination = build_osemosys_member(set_name, ALL_COMPONENTS)
    recorder.append(build_derived([], [destination], derivation.format(count=count)))
