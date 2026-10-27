"""Leaves out the part of a canonical stage that lies outside a scope of locations and years."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import NamedTuple

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.osemosys_canonical.canonical_stage import (
    CanonicalTable,
    build_table_key,
    list_canonical_tables,
    set_canonical_table,
)
from interop.plugins.shared.osemosys_canonical.constants import (
    END_REGION,
    REGION,
    START_REGION,
    VALUE_COL,
    YEAR,
    TableKind,
)
from interop.plugins.shared.osemosys_canonical.scope_locations import (
    KeptMember,
    build_located_drop,
    list_model_locations,
)
from interop.ports.errors import UserInputError

_LOCATIONS_PARAMETER = "locations"
_YEARS_PARAMETER = "years"
# The columns that hold a member of a set, where a table can name that set in more than one.
_SET_COLUMNS: dict[str, tuple[str, ...]] = {REGION: (REGION, START_REGION, END_REGION)}


class Scope(NamedTuple):
    """An empty `locations` or `years` keeps everything."""

    locations: tuple[str, ...]
    years: tuple[int, ...]

    @property
    def has_years(self) -> bool:
        return bool(self.years)


class ScopeDrop(NamedTuple):
    """`members` hold what leaves every region, by set, and a year is a member of `year`.
    `pairs` hold each (region, member) row outside the scope. `kept` hold the members that stay
    although their location is outside it, and `region_groups` the regions that each group
    loses."""

    members: dict[str, list[str]]
    pairs: dict[str, pl.DataFrame]
    kept: list[KeptMember]
    region_groups: dict[str, list[str]]


def reject_scope_outside_model(state: State, scope: Scope) -> None:
    """Raise when the scope names a location or a year that the model does not hold."""
    _reject_unknown(_LOCATIONS_PARAMETER, scope.locations, list_model_locations(state))
    _reject_unknown(_YEARS_PARAMETER, _list_year_names(scope), _list_model_years(state))


def _reject_unknown(parameter: str, requested: Sequence[str], known: list[str]) -> None:
    unknown = [one for one in requested if one not in known]
    if unknown:
        raise UserInputError(
            f"The parameter `{parameter}` names {', '.join(unknown)}, which the model does not "
            f"hold. The model {parameter} are: {', '.join(known) or 'none'}."
        )


def _list_model_years(state: State) -> list[str]:
    years = state.source_topology.get(build_table_key(TableKind.SET, YEAR))
    if years is None:
        return []
    return years.select(pl.col(VALUE_COL).cast(pl.String)).collect().to_series().to_list()


def _list_year_names(scope: Scope) -> list[str]:
    return [str(year) for year in scope.years]


def build_scope_drop(state: State, scope: Scope) -> ScopeDrop:
    located = build_located_drop(state, scope.locations)
    years = _list_years_outside_scope(state, scope)
    members = {**located.members, YEAR: years} if years else located.members
    return ScopeDrop(members, located.pairs, located.kept, located.region_groups)


def _list_years_outside_scope(state: State, scope: Scope) -> list[str]:
    if not scope.has_years:
        return []
    kept = _list_year_names(scope)
    return [member for member in _list_model_years(state) if member not in kept]


def set_scoped_tables(state: State, drop: ScopeDrop) -> None:
    """Replace each canonical table with the table that holds no row that `drop` names."""
    for canonical in list_canonical_tables(state):
        set_canonical_table(state, canonical._replace(table=_build_scoped_table(canonical, drop)))


def _build_scoped_table(canonical: CanonicalTable, drop: ScopeDrop) -> pl.LazyFrame:
    return _drop_pairs(_drop_members(canonical, drop.members), drop.pairs)


def _drop_members(canonical: CanonicalTable, members: Mapping[str, list[str]]) -> pl.LazyFrame:
    columns = canonical.table.collect_schema().names()
    table = canonical.table
    for set_name, dropped in members.items():
        for column in _list_set_columns(canonical, set_name, columns):
            table = table.filter(~pl.col(column).cast(pl.String).is_in(dropped).fill_null(False))
    return table


def _list_set_columns(canonical: CanonicalTable, set_name: str, columns: list[str]) -> list[str]:
    """The columns that hold the members of `set_name`; none where the table has none."""
    if canonical.kind == TableKind.SET and canonical.name == set_name:
        return [VALUE_COL]
    return [column for column in _SET_COLUMNS.get(set_name, (set_name,)) if column in columns]


def _drop_pairs(table: pl.LazyFrame, pairs: Mapping[str, pl.DataFrame]) -> pl.LazyFrame:
    schema = table.collect_schema()
    for set_name, outside in pairs.items():
        if REGION in schema and set_name in schema:
            keys = {REGION: schema[REGION], set_name: schema[set_name]}
            table = table.join(outside.lazy().cast(pl.Schema(keys)), on=list(keys), how="anti")
    return table
