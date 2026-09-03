"""The comma-separated spec a fixture writes one PLEXOS Generator with.

``node=Bus1, fuel=Gas, Max Capacity=100`` names the memberships, the category and every
property in one string, so a scenario states a generator on one line and no step has to
know which properties that kind of generator carries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import NamedTuple

# Keys in a generator spec that name something other than a property value. Everything
# else in a spec is a PLEXOS property name, written verbatim.
_NODE_KEY = "node"
_CATEGORY_KEY = "category"
_FUEL_KEY = "fuel"
_MEMBERSHIP_KEYS = (_NODE_KEY, _CATEGORY_KEY, _FUEL_KEY)


# Marks a property whose values live in a Data File rather than in the XML.
_FILE_BACKED_PREFIX = "file:"

# Marks a property whose value scales a Variable's own profile: ``variable:<name>:<value>``,
# where an omitted value is zero (a Units Out trace states the shape, not a share of it).
_VARIABLE_BACKED_PREFIX = "variable:"
_VARIABLE_FIELD_SEPARATOR = ":"
_NO_VARIABLE_SHARE = 0.0

# A spec's entries are separated by commas, so no value may hold one.
_SPEC_SEPARATOR = ","


class VariableShare(NamedTuple):
    """A property whose value is a share of the named Variable's profile."""

    variable: str
    value: float


@dataclass(frozen=True)
class GeneratorSpec:
    """One PLEXOS Generator: what it connects to, what category it is in, what it carries."""

    node: str | None = None
    fuels: tuple[str, ...] = ()
    category: str | None = None
    properties: dict[str, float] = field(default_factory=dict)
    file_backed: dict[str, str] = field(default_factory=dict)
    variable_backed: dict[str, VariableShare] = field(default_factory=dict)


def parse_generator_spec(spec: str) -> GeneratorSpec:
    """Read a comma-separated generator spec, e.g. ``node=Bus1, Max Capacity=100``.

    ``node``, ``category`` and ``fuel`` (repeatable, in priority order) name memberships
    and the object's category. Every other key is a PLEXOS property name and takes a
    number, ``file:<data file>`` where the property's values are file-backed, or
    ``variable:<variable>:<value>`` where the value scales that Variable's own profile.
    """
    entries = _spec_entries(spec)
    return GeneratorSpec(
        node=_first_value(entries, _NODE_KEY),
        fuels=tuple(value for key, value in entries if key == _FUEL_KEY),
        category=_first_value(entries, _CATEGORY_KEY),
        properties=_property_values(entries),
        file_backed=_prefixed_values(entries, _FILE_BACKED_PREFIX),
        variable_backed=_variable_backed_properties(entries),
    )


def build_generator_spec(fields: dict[str, str]) -> GeneratorSpec:
    """Read a generator spec given field by field, as a Gherkin table row gives it.

    Rejects a value holding a comma rather than letting the spec split on it, since a
    table cell reads as one value even where the comma-separated form could not hold it.
    """
    for key, value in fields.items():
        if _SPEC_SEPARATOR in value:
            raise ValueError(f"generator field {key!r} may not hold a comma: {value!r}")
    return parse_generator_spec(
        f"{_SPEC_SEPARATOR} ".join(f"{key}={value}" for key, value in fields.items())
    )


_SpecEntries = list[tuple[str, str]]


def _spec_entries(spec: str) -> _SpecEntries:
    entries = []
    for entry in spec.split(_SPEC_SEPARATOR):
        key, _, value = entry.partition("=")
        entries.append((key.strip(), value.strip()))
    return entries


def _first_value(entries: _SpecEntries, wanted: str) -> str | None:
    return next((value for key, value in entries if key == wanted), None)


def _property_values(entries: _SpecEntries) -> dict[str, float]:
    return {
        key: float(value)
        for key, value in _property_entries(entries)
        if not value.startswith((_FILE_BACKED_PREFIX, _VARIABLE_BACKED_PREFIX))
    }


def _prefixed_values(entries: _SpecEntries, prefix: str) -> dict[str, str]:
    return {
        key: value.removeprefix(prefix)
        for key, value in _property_entries(entries)
        if value.startswith(prefix)
    }


def _variable_backed_properties(entries: _SpecEntries) -> dict[str, VariableShare]:
    return {
        key: _read_variable_share(value)
        for key, value in _prefixed_values(entries, _VARIABLE_BACKED_PREFIX).items()
    }


def _read_variable_share(stated: str) -> VariableShare:
    variable, _, share = stated.partition(_VARIABLE_FIELD_SEPARATOR)
    return VariableShare(variable, float(share) if share else _NO_VARIABLE_SHARE)


def _property_entries(entries: _SpecEntries) -> _SpecEntries:
    return [(key, value) for key, value in entries if key not in _MEMBERSHIP_KEYS]
