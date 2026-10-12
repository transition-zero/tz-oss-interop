"""How one nested TZ-format value becomes one entry for each combination of set members."""

from __future__ import annotations

import itertools
from collections.abc import Mapping
from typing import NamedTuple

from interop.plugins.shared.osemosys_canonical.constants import (
    OSEMOSYS_REGION,
    OSEMOSYS_SECOND_REGION,
)
from interop.plugins.shared.tz_osemosys_fields import (
    COMPOSED_DATA,
    COMPOSED_FLAG,
    VALUE_WORDS,
    WILDCARD,
)


class TzEntry(NamedTuple):
    """The member of each nested level, outermost first, and the value that they lead to."""

    members: tuple[str, ...]
    value: object


def list_tz_entries(
    value: object, levels: tuple[str, ...], sets: Mapping[str, list[str]]
) -> list[TzEntry]:
    """A value that stops above the last level stands for each member of every level below."""
    if not levels:
        return [TzEntry((), value)]
    if not isinstance(value, dict):
        return _list_repeated_entries(value, levels, sets)
    return [
        TzEntry((member, *entry.members), entry.value)
        for member, child in _list_level_members(value, _get_set_members(levels[0], sets))
        for entry in list_tz_entries(child, levels[1:], sets)
    ]


def build_bare_value(value: object) -> object:
    """A composed value holds its nested value under a data key, beside a flag."""
    if isinstance(value, dict) and COMPOSED_FLAG in value and COMPOSED_DATA in value:
        return value[COMPOSED_DATA]
    return value


def build_float_value(value: object) -> float | None:
    """A boolean is 1 or 0, and a value that is not a number or a known word is `None`."""
    if isinstance(value, bool | int | float):
        return float(value)
    if not isinstance(value, str):
        return None
    if value in VALUE_WORDS:
        return VALUE_WORDS[value]
    try:
        return float(value)
    except ValueError:
        return None


def has_empty_expansion(
    value: object, levels: tuple[str, ...], sets: Mapping[str, list[str]]
) -> bool:
    """A wildcard, or a value that stops above the last level, that stands for an empty set."""
    if not levels:
        return False
    if not isinstance(value, dict):
        return any(not _get_set_members(level, sets) for level in levels)
    if WILDCARD in value and not _get_set_members(levels[0], sets):
        return True
    return any(has_empty_expansion(child, levels[1:], sets) for child in value.values())


def build_region_pairs(value: object) -> object:
    """Each pair of regions that the value states in one direction gets the same value in the
    other direction, unless the value states that direction too."""
    pairs = build_bare_value(value)
    if not isinstance(pairs, dict):
        return pairs
    mirrored = _build_pair_copy(pairs)
    for region, other, rest in _list_region_pairs(pairs):
        reverse = mirrored.setdefault(other, {})
        if isinstance(reverse, dict):
            reverse.setdefault(region, rest)
    return mirrored


def _build_pair_copy(pairs: dict[object, object]) -> dict[object, object]:
    return {
        region: dict(others) if isinstance(others, dict) else others
        for region, others in pairs.items()
    }


def _list_region_pairs(pairs: dict[object, object]) -> list[tuple[object, object, object]]:
    return [
        (region, other, rest)
        for region, others in pairs.items()
        if isinstance(others, dict)
        for other, rest in others.items()
    ]


def _list_repeated_entries(
    value: object, levels: tuple[str, ...], sets: Mapping[str, list[str]]
) -> list[TzEntry]:
    member_lists = [_get_set_members(level, sets) for level in levels]
    return [TzEntry(members, value) for members in itertools.product(*member_lists)]


def _list_level_members(
    level: dict[object, object], members: list[str]
) -> list[tuple[str, object]]:
    """A wildcard stands for each member of the set that the level does not name itself."""
    named = [(str(key), child) for key, child in level.items() if key != WILDCARD]
    if WILDCARD not in level:
        return named
    named_members = {member for member, _ in named}
    wildcard = level[WILDCARD]
    return [*named, *((member, wildcard) for member in members if member not in named_members)]


def _get_set_members(level: str, sets: Mapping[str, list[str]]) -> list[str]:
    """The second region of a key takes its members from the region set."""
    return sets[OSEMOSYS_REGION if level == OSEMOSYS_SECOND_REGION else level]
