"""Tells which technologies, fuels, storages and regions of a canonical stage lie outside a list
of locations."""

from __future__ import annotations

from typing import NamedTuple

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.osemosys_canonical.canonical_stage import build_table_key
from interop.plugins.shared.osemosys_canonical.constants import (
    ANNOTATION_NAME_SEPARATOR,
    FUEL,
    LOCATION_SEPARATOR,
    REGION,
    REGION_GROUP,
    STORAGE,
    TECHNOLOGY,
    VALUE_COL,
    AnnotationColumn,
    FlowParameter,
    TableKind,
)

# The sets whose members the annotations place at a location.
LOCATED_SETS = (TECHNOLOGY, FUEL, STORAGE)
# The sets whose annotations state a location.
_ANNOTATED_SETS = (*LOCATED_SETS, REGION)
# The sets whose members a technology uses through a flow or a storage link.
_LINKED_SETS = (FUEL, STORAGE)
_KEPT_ORDER = (*_LINKED_SETS, TECHNOLOGY)
_LINK_PARAMETERS: dict[str, str] = {
    FlowParameter.INPUT_ACTIVITY_RATIO: FUEL,
    FlowParameter.OUTPUT_ACTIVITY_RATIO: FUEL,
    FlowParameter.TECHNOLOGY_TO_STORAGE: STORAGE,
    FlowParameter.TECHNOLOGY_FROM_STORAGE: STORAGE,
}
_REGION_GROUP_TAG_REGION = "region_group_tag_region"
# The leading underscores keep these temporary columns from clashing with a column of the model.
_IS_IN_SCOPE_COL = "__is_in_scope"
_IS_KEPT_COL = "__is_kept"
_IS_MARKED_COL = "__is_marked"
_LINKED_SET_COL = "__linked_set"
_LINKED_MEMBER_COL = "__linked_member"
_LINK_SCHEMA = dict.fromkeys([REGION, TECHNOLOGY, _LINKED_SET_COL, _LINKED_MEMBER_COL], pl.String)


class KeptMember(NamedTuple):
    """A member that stays in one region although its location is outside the scope."""

    set_name: str
    region: str
    member: str
    location: str

    @property
    def name(self) -> str:
        return ANNOTATION_NAME_SEPARATOR.join((self.region, self.member))


class LocatedDrop(NamedTuple):
    """`pairs` hold the (region, member) rows outside the locations, by set. `members` hold the
    members with no row inside them, and the regions that leave the stage."""

    members: dict[str, list[str]]
    pairs: dict[str, pl.DataFrame]
    kept: list[KeptMember]
    region_groups: dict[str, list[str]]


def express_is_in_scope(locations: tuple[str, ...]) -> pl.Expr:
    """A member with no location is in scope, and so is one whose every location part is."""
    location = pl.col(AnnotationColumn.LOCATION)
    parts_in_scope = (
        location.str.split(LOCATION_SEPARATOR)
        .list.eval(pl.element().is_in(list(locations)))
        .list.all()
    )
    return location.is_null() | parts_in_scope


def list_model_locations(state: State) -> list[str]:
    """Each location part that an annotation states, in order."""
    annotations = [_find_annotation(state, set_name) for set_name in _ANNOTATED_SETS]
    location = pl.col(AnnotationColumn.LOCATION)
    parts = [
        annotation.select(location.str.split(LOCATION_SEPARATOR).explode())
        for annotation in annotations
        if annotation is not None
    ]
    if not parts:
        return []
    return pl.concat(parts).drop_nulls().unique().sort(location).collect().to_series().to_list()


def find_parameter(state: State, name: str) -> pl.LazyFrame | None:
    return state.source_time_series.get((TableKind.PARAMETER, name))


def build_located_drop(state: State, locations: tuple[str, ...]) -> LocatedDrop:
    links = _build_links(state) if locations else pl.DataFrame(schema=_LINK_SCHEMA)
    located = _build_located_rows(state, locations, links)
    regions = _list_regions_outside(state, locations, located, links)
    located = _enrich_with_dropped_regions(located, regions)
    members = {
        set_name: _list_members_outside(rows, set_name) for set_name, rows in located.items()
    }
    return LocatedDrop(
        members={name: found for name, found in {**members, REGION: regions}.items() if found},
        pairs=_build_pairs(located),
        kept=_list_kept_members(located),
        region_groups=_build_region_groups_losing(state, regions),
    )


def _find_annotation(state: State, set_name: str) -> pl.LazyFrame | None:
    return state.source_topology.get(build_table_key(TableKind.ANNOTATION, set_name))


def _build_links(state: State) -> pl.DataFrame:
    """Each (region, technology) and the fuel or the storage that it uses, once."""
    links = [
        _build_parameter_links(table, set_name)
        for parameter, set_name in _LINK_PARAMETERS.items()
        if (table := find_parameter(state, parameter)) is not None
    ]
    return pl.concat(links).unique() if links else pl.DataFrame(schema=_LINK_SCHEMA)


def _build_parameter_links(table: pl.LazyFrame, set_name: str) -> pl.DataFrame:
    """A parameter table can hold billions of rows, so collect only the distinct key columns."""
    return (
        table.filter(pl.col(VALUE_COL) > 0)
        .select(
            pl.col(REGION).cast(pl.String),
            pl.col(TECHNOLOGY).cast(pl.String),
            pl.lit(set_name).alias(_LINKED_SET_COL),
            pl.col(set_name).cast(pl.String).alias(_LINKED_MEMBER_COL),
        )
        .unique()
        .collect()
    )


def _build_located_rows(
    state: State, locations: tuple[str, ...], links: pl.DataFrame
) -> dict[str, pl.DataFrame]:
    """Each annotation row, with the column that tells if it stays."""
    if not locations:
        return {}
    located = {
        set_name: _enrich_with_scope(annotation, locations)
        for set_name in LOCATED_SETS
        if (annotation := _find_annotation(state, set_name)) is not None
    }
    return _build_with_users_of_kept_members(_build_with_named_members(located, links), links)


def _enrich_with_scope(annotation: pl.LazyFrame, locations: tuple[str, ...]) -> pl.DataFrame:
    return annotation.with_columns(
        express_is_in_scope(locations).alias(_IS_IN_SCOPE_COL), pl.lit(False).alias(_IS_KEPT_COL)
    ).collect()


def _build_with_named_members(
    located: dict[str, pl.DataFrame], links: pl.DataFrame
) -> dict[str, pl.DataFrame]:
    """Keep each fuel and storage that a technology in scope uses, in the region of that use."""
    named = links.join(
        _build_in_scope_keys(located, TECHNOLOGY), on=[REGION, TECHNOLOGY], how="semi"
    )
    return {
        set_name: _enrich_with_kept(rows, _build_linked_keys(named, set_name), set_name)
        if set_name in _LINKED_SETS
        else rows
        for set_name, rows in located.items()
    }


def _build_with_users_of_kept_members(
    located: dict[str, pl.DataFrame], links: pl.DataFrame
) -> dict[str, pl.DataFrame]:
    """Keep a technology at the location of its region that uses only fuels and storages that
    stay, such as the supply of a kept fuel."""
    technologies = located.get(TECHNOLOGY)
    if technologies is None:
        return located
    at_region = technologies.filter(pl.col(AnnotationColumn.LOCATION) == pl.col(REGION))
    users = _build_users_of_kept_members(located, links)
    keys = users.join(at_region, on=[REGION, TECHNOLOGY], how="semi")
    return {**located, TECHNOLOGY: _enrich_with_kept(technologies, keys, TECHNOLOGY)}


def _build_users_of_kept_members(
    located: dict[str, pl.DataFrame], links: pl.DataFrame
) -> pl.DataFrame:
    """Each (region, technology) whose every link names a fuel or a storage that stays."""
    kept = pl.concat([_build_kept_links(located, set_name) for set_name in _LINKED_SETS])
    marked = links.join(
        _enrich_with_mark(kept), on=[REGION, _LINKED_SET_COL, _LINKED_MEMBER_COL], how="left"
    )
    has_only_kept = pl.col(_IS_MARKED_COL).fill_null(False).all()
    users = marked.group_by(REGION, TECHNOLOGY).agg(has_only_kept)
    return users.filter(pl.col(_IS_MARKED_COL)).select(REGION, TECHNOLOGY)


def _build_kept_links(located: dict[str, pl.DataFrame], set_name: str) -> pl.DataFrame:
    linked_set = pl.lit(set_name).alias(_LINKED_SET_COL)
    linked_member = pl.col(set_name).alias(_LINKED_MEMBER_COL)
    return _build_in_scope_keys(located, set_name).select(REGION, linked_set, linked_member)


def _build_in_scope_keys(located: dict[str, pl.DataFrame], set_name: str) -> pl.DataFrame:
    rows = located.get(set_name)
    if rows is None:
        return pl.DataFrame(schema=dict.fromkeys([REGION, set_name], pl.String))
    return rows.filter(pl.col(_IS_IN_SCOPE_COL)).select(REGION, set_name)


def _build_linked_keys(links: pl.DataFrame, set_name: str) -> pl.DataFrame:
    linked = links.filter(pl.col(_LINKED_SET_COL) == set_name)
    return linked.select(REGION, pl.col(_LINKED_MEMBER_COL).alias(set_name)).unique()


def _enrich_with_kept(rows: pl.DataFrame, keys: pl.DataFrame, set_name: str) -> pl.DataFrame:
    """Put each row that `keys` names in the scope, and mark the ones outside it as kept."""
    marked = rows.join(_enrich_with_mark(keys), on=[REGION, set_name], how="left")
    is_kept = ~pl.col(_IS_IN_SCOPE_COL) & pl.col(_IS_MARKED_COL).fill_null(False)
    with_kept = marked.with_columns(is_kept.alias(_IS_KEPT_COL)).drop(_IS_MARKED_COL)
    return with_kept.with_columns(pl.col(_IS_IN_SCOPE_COL) | pl.col(_IS_KEPT_COL))


def _enrich_with_mark(keys: pl.DataFrame) -> pl.DataFrame:
    return keys.with_columns(pl.lit(True).alias(_IS_MARKED_COL))


def _list_regions_outside(
    state: State,
    locations: tuple[str, ...],
    located: dict[str, pl.DataFrame],
    links: pl.DataFrame,
) -> list[str]:
    """A region leaves when its own location is outside the scope and no technology in the
    scope has a flow in it, so a model with one region keeps that region."""
    annotation = _find_annotation(state, REGION)
    if annotation is None or TECHNOLOGY not in located:
        return []
    in_scope = _build_in_scope_keys(located, TECHNOLOGY)
    holding = links.join(in_scope, on=[REGION, TECHNOLOGY], how="semi").select(REGION)
    outside = annotation.filter(~express_is_in_scope(locations)).collect()
    regions = outside.join(holding, on=REGION, how="anti").get_column(REGION)
    return regions.unique().sort().to_list()


def _enrich_with_dropped_regions(
    located: dict[str, pl.DataFrame], regions: list[str]
) -> dict[str, pl.DataFrame]:
    is_in_scope = pl.col(_IS_IN_SCOPE_COL) & ~pl.col(REGION).is_in(regions)
    return {set_name: rows.with_columns(is_in_scope) for set_name, rows in located.items()}


def _list_members_outside(rows: pl.DataFrame, set_name: str) -> list[str]:
    has_row_in_scope = pl.col(_IS_IN_SCOPE_COL).any()
    outside = rows.group_by(set_name).agg(has_row_in_scope).filter(~pl.col(_IS_IN_SCOPE_COL))
    return outside.get_column(set_name).sort().to_list()


def _build_pairs(located: dict[str, pl.DataFrame]) -> dict[str, pl.DataFrame]:
    return {
        set_name: rows.filter(~pl.col(_IS_IN_SCOPE_COL)).select(REGION, set_name)
        for set_name, rows in located.items()
    }


def _list_kept_members(located: dict[str, pl.DataFrame]) -> list[KeptMember]:
    return [
        KeptMember(set_name, *row)
        for set_name in _KEPT_ORDER
        if (rows := located.get(set_name)) is not None
        for row in _build_kept_keys(rows, set_name).rows()
    ]


def _build_kept_keys(rows: pl.DataFrame, set_name: str) -> pl.DataFrame:
    kept = rows.filter(pl.col(_IS_KEPT_COL))
    return kept.select(REGION, set_name, AnnotationColumn.LOCATION).sort(REGION, set_name)


def _build_region_groups_losing(state: State, regions: list[str]) -> dict[str, list[str]]:
    """The regions outside the scope that each region group holds."""
    table = find_parameter(state, _REGION_GROUP_TAG_REGION)
    if table is None or not regions:
        return {}
    tags = table.filter((pl.col(VALUE_COL) > 0) & pl.col(REGION).cast(pl.String).is_in(regions))
    pairs = tags.select(pl.col(REGION_GROUP).cast(pl.String), pl.col(REGION).cast(pl.String))
    groups: dict[str, list[str]] = {}
    for group, region in pairs.unique().sort(REGION_GROUP, REGION).collect().rows():
        groups.setdefault(group, []).append(region)
    return groups
