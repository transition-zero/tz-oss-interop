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
    find_parameter,
    list_model_locations,
)
from interop.ports.errors import UserInputError

_LOCATIONS_PARAMETER = "locations"
_YEARS_PARAMETER = "years"
# The columns that hold a member of a set, where a table can name that set in more than one.
_SET_COLUMNS: dict[str, tuple[str, ...]] = {REGION: (REGION, START_REGION, END_REGION)}
# Each of these states one value for the whole model period.
_MODEL_PERIOD_PARAMETERS = (
    "total_technology_model_period_activity_upper_limit",
    "total_technology_model_period_activity_lower_limit",
    "model_period_emission_limit",
    "model_period_exogenous_emission",
)
# This states the level of each storage at the start of the first model year.
_STORAGE_LEVEL_START = "storage_level_start"
_MODEL_PERIOD_NOTE = (
    "it states one value for the whole model period, and the scope leaves out {count} year(s), "
    "so no value of it is kept"
)
_STORAGE_LEVEL_START_NOTE = (
    "it states the level at the start of the first model year {year}, which the scope leaves "
    "out, so no value of it is kept"
)


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
    although their location is outside it. `region_groups` hold the regions that each group
    loses, and `tables` the note of each parameter table that loses all of its rows."""

    members: dict[str, list[str]]
    pairs: dict[str, pl.DataFrame]
    kept: list[KeptMember]
    region_groups: dict[str, list[str]]
    tables: dict[str, str]


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
    tables = _build_period_table_notes(state, years)
    return ScopeDrop(members, located.pairs, located.kept, located.region_groups, tables)


def _list_years_outside_scope(state: State, scope: Scope) -> list[str]:
    if not scope.has_years:
        return []
    kept = _list_year_names(scope)
    return [member for member in _list_model_years(state) if member not in kept]


def _build_period_table_notes(state: State, years: list[str]) -> dict[str, str]:
    """A value for the whole model period, or for its start, does not fit a subset of the years."""
    if not years:
        return {}
    notes = dict.fromkeys(_MODEL_PERIOD_PARAMETERS, _MODEL_PERIOD_NOTE.format(count=len(years)))
    first = _find_first_model_year(state)
    if first in years:
        notes[_STORAGE_LEVEL_START] = _STORAGE_LEVEL_START_NOTE.format(year=first)
    return {name: note for name, note in notes.items() if _has_rows(state, name)}


def _find_first_model_year(state: State) -> str | None:
    """Sort by the length first, so that a year of four digits comes after one of three."""
    return min(_list_model_years(state), key=lambda year: (len(year), year), default=None)


def _has_rows(state: State, name: str) -> bool:
    table = find_parameter(state, name)
    return table is not None and table.select(pl.len()).collect().item() > 0


def set_scoped_tables(state: State, drop: ScopeDrop) -> None:
    """Replace each canonical table with the table that holds no row that `drop` names."""
    for canonical in list_canonical_tables(state):
        set_canonical_table(state, canonical._replace(table=_build_scoped_table(canonical, drop)))


def _build_scoped_table(canonical: CanonicalTable, drop: ScopeDrop) -> pl.LazyFrame:
    if canonical.kind == TableKind.PARAMETER and canonical.name in drop.tables:
        return canonical.table.clear()
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
