"""The structure of a TZ-format model.json: its objects, the key members they add, and its sets.

The structure is the file format, so a document that does not have it is not a TZ-format model.
Every other field holds model data, which the field table reads.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Annotated, NamedTuple

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator

from interop.core.reporting import EventRecorder
from interop.plugins.shared.osemosys_canonical.constants import TableKind
from interop.plugins.shared.osemosys_canonical.events import record_not_mapped
from interop.plugins.shared.tz_osemosys_fields import OBJECT_SETS, TIME_SETS, TZ_FIELDS, TzOwner
from interop.plugins.shared.warning_text import name_a_few

log = logging.getLogger(__name__)

_FIELD_NAME = "{owner}.{field}"
_UNKNOWN_FIELD_NOTE = "the TZ-format field has no raw table, so the raw stage leaves it out"
_KNOWN_FIELDS = frozenset((field.owner, field.field) for field in TZ_FIELDS)


def _normalise_member(value: object) -> object:
    """A member that the document states as a number keeps the digits it has."""
    return str(value) if isinstance(value, int) and not isinstance(value, bool) else value


def _normalise_set_members(value: object) -> object:
    """A count n stands for the members 1 to n."""
    if value is None:
        return []
    if isinstance(value, int) and not isinstance(value, bool):
        return list(range(1, value + 1))
    return value


Member = Annotated[str, BeforeValidator(_normalise_member)]
SetMembers = Annotated[list[Member], BeforeValidator(_normalise_set_members)]


class TzPart(BaseModel):
    """One object of the document; each field that it does not declare holds model data."""

    model_config = ConfigDict(extra="allow")

    long_name: object = None
    description: object = None
    otoole_cfg: object = None
    defaults_otoole: object = None

    @property
    def field_values(self) -> dict[str, object]:
        return dict(self.model_extra or {})


class TzNamedPart(TzPart):
    id: Member


class TzTechnologyPart(TzNamedPart):
    operating_modes: list[TzNamedPart] = Field(default_factory=list)

    @field_validator("operating_modes", mode="before")
    @classmethod
    def _validate_null_list(cls, value: object) -> object:
        return [] if value is None else value


class TzTradePart(TzPart):
    """A trade adds its commodity to its rows; its `id` names the trade and no set."""

    id: object = None
    commodity: Member
    construct_region_pairs: object = None


class TzTimeDefinitionPart(TzPart):
    id: object = None
    years: SetMembers = Field(default_factory=list)
    timeslices: SetMembers = Field(default_factory=list)
    seasons: SetMembers = Field(default_factory=list)
    day_types: SetMembers = Field(default_factory=list)
    daily_time_brackets: SetMembers = Field(default_factory=list)
    adj: object = None
    adj_inv: object = None

    def list_set_members(self) -> dict[str, list[str]]:
        return {set_name: getattr(self, field) for field, set_name in TIME_SETS.items()}


class TzModelDocument(TzPart):
    id: object = None
    time_definition: TzTimeDefinitionPart
    regions: list[TzNamedPart] = Field(default_factory=list)
    regionsgroup: list[TzNamedPart] = Field(default_factory=list)
    commodities: list[TzNamedPart] = Field(default_factory=list)
    impacts: list[TzNamedPart] = Field(default_factory=list)
    technologies: list[TzTechnologyPart] = Field(default_factory=list)
    storage: list[TzNamedPart] = Field(default_factory=list)
    trade: list[TzTradePart] = Field(default_factory=list)

    @field_validator(
        "regions",
        "regionsgroup",
        "commodities",
        "impacts",
        "technologies",
        "storage",
        "trade",
        mode="before",
    )
    @classmethod
    def _validate_null_list(cls, value: object) -> object:
        return [] if value is None else value

    def list_named_parts(self) -> dict[TzOwner, Sequence[TzNamedPart]]:
        return {
            TzOwner.REGIONS: self.regions,
            TzOwner.REGION_GROUPS: self.regionsgroup,
            TzOwner.COMMODITIES: self.commodities,
            TzOwner.IMPACTS: self.impacts,
            TzOwner.TECHNOLOGIES: self.technologies,
            TzOwner.STORAGE: self.storage,
        }


class TzObject(NamedTuple):
    """One object, the member of each owner column that it adds to its rows, and its fields."""

    owner: TzOwner
    keys: tuple[str, ...]
    field_values: Mapping[str, object]


def list_tz_objects(document: TzModelDocument) -> list[TzObject]:
    return [
        TzObject(TzOwner.MODEL, (), document.field_values),
        TzObject(TzOwner.TIME_DEFINITION, (), document.time_definition.field_values),
        *_list_named_objects(document),
        *[TzObject(TzOwner.TRADE, (part.commodity,), part.field_values) for part in document.trade],
        *_list_operating_modes(document),
    ]


def _list_named_objects(document: TzModelDocument) -> list[TzObject]:
    return [
        TzObject(owner, (part.id,), part.field_values)
        for owner, parts in document.list_named_parts().items()
        for part in parts
    ]


def _list_operating_modes(document: TzModelDocument) -> list[TzObject]:
    return [
        TzObject(TzOwner.OPERATING_MODES, (technology.id, mode.id), mode.field_values)
        for technology in document.technologies
        for mode in technology.operating_modes
    ]


def list_tz_sets(document: TzModelDocument, objects: list[TzObject]) -> dict[str, list[str]]:
    """The members of each set, once each, in the order that the document states them."""
    object_sets = {
        set_name: [tz_object.keys[-1] for tz_object in objects if tz_object.owner is owner]
        for owner, set_name in OBJECT_SETS.items()
    }
    sets = {**document.time_definition.list_set_members(), **object_sets}
    return {name: list(dict.fromkeys(members)) for name, members in sets.items()}


def report_unknown_fields(objects: list[TzObject], recorder: EventRecorder) -> None:
    unknown = _list_unknown_fields(objects)
    for name in unknown:
        record_not_mapped(recorder, TableKind.PARAMETER, name, _UNKNOWN_FIELD_NOTE)
    if unknown:
        log.warning(
            "%d TZ-format field(s) have no raw table, so the raw stage leaves each out: %s",
            len(unknown),
            name_a_few(unknown),
        )


def _list_unknown_fields(objects: list[TzObject]) -> list[str]:
    """A field that states null holds no model data, so it is not unknown."""
    names = [
        _FIELD_NAME.format(owner=tz_object.owner, field=name)
        for tz_object in objects
        for name, value in tz_object.field_values.items()
        if value is not None and (tz_object.owner, name) not in _KNOWN_FIELDS
    ]
    return list(dict.fromkeys(names))
