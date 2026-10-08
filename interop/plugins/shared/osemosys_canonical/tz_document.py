"""The structure of a TZ-format model.json: its objects, the key members they add, and its sets.

The document must be a JSON object with a time definition. Each object of a list is checked
alone, so an object that the source cannot use is left out and the rest of the model stays.
Every field that an object does not declare holds model data, which the field table reads.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Annotated, Generic, NamedTuple, TypeVar

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError

from interop.core.reporting import EventRecorder
from interop.plugins.shared.osemosys_canonical.events import record_not_mapped, record_skipped
from interop.plugins.shared.osemosys_canonical.tz_reports import (
    TzPath,
    TzPathReport,
    join_tz_names,
    report_tz_paths,
)
from interop.plugins.shared.osemosys_canonical.tz_values import build_region_pairs
from interop.plugins.shared.tz_osemosys_fields import (
    OBJECT_SETS,
    REGION_PAIR_FIELDS,
    TIME_SETS,
    TZ_FIELDS,
    TzOwner,
)

_UNKNOWN_FIELD_NOTE = "the TZ-format field has no raw table, so the raw stage leaves it out"
_SKIPPED_OBJECT_NOTE = "the object cannot be used ({reason}), so the raw stage leaves it out"
_ITEM_NAME = "item {position}"
_UNKNOWN_FIELDS = TzPathReport(record_not_mapped, "field(s) have no raw table")
_SKIPPED_OBJECTS = TzPathReport(record_skipped, "object(s) cannot be used")
_KNOWN_FIELDS = frozenset((field.owner, field.field) for field in TZ_FIELDS)
# The lists of objects that state an `id` and nothing else that the structure declares.
_NAMED_OWNERS = (
    TzOwner.REGIONS,
    TzOwner.REGION_GROUPS,
    TzOwner.COMMODITIES,
    TzOwner.IMPACTS,
    TzOwner.STORAGE,
)


def _normalise_member(value: object) -> object:
    """A member that the document states as a number keeps its digits, and 2030.0 is 2030."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, int | float) and not isinstance(value, bool):
        return str(value)
    return value


def _normalise_set_members(value: object) -> object:
    """A count n stands for the members 1 to n."""
    if value is None:
        return []
    if isinstance(value, int) and not isinstance(value, bool):
        return list(range(1, value + 1))
    return value


def _normalise_items(value: object) -> object:
    return [] if value is None else value


Member = Annotated[str, BeforeValidator(_normalise_member)]
SetMembers = Annotated[list[Member], BeforeValidator(_normalise_set_members)]
# The objects of a list, each unchecked, so that one object the source cannot use stays alone.
Items = Annotated[list[object], BeforeValidator(_normalise_items)]


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


class TzKeyedPart(TzPart):
    """An object of a list, which adds one member to the key of its rows."""

    @property
    def key_member(self) -> str:
        raise NotImplementedError

    @property
    def label(self) -> str:
        return self.key_member


class TzNamedPart(TzKeyedPart):
    id: Member

    @property
    def key_member(self) -> str:
        return self.id


class TzTechnologyPart(TzNamedPart):
    operating_modes: Items = Field(default_factory=list)


class TzTradePart(TzKeyedPart):
    """A trade adds its commodity to its rows; its `id` names the trade and no set."""

    id: Member | None = None
    commodity: Member
    construct_region_pairs: bool | None = None

    @property
    def key_member(self) -> str:
        return self.commodity

    @property
    def label(self) -> str:
        return self.id or self.commodity

    @property
    def field_values(self) -> dict[str, object]:
        """With `construct_region_pairs`, a pair stated in one direction holds in both."""
        values = super().field_values
        if not self.construct_region_pairs:
            return values
        return {
            name: build_region_pairs(value) if name in REGION_PAIR_FIELDS else value
            for name, value in values.items()
        }


class TzTimeDefinitionPart(TzPart):
    id: object = None
    years: SetMembers = Field(default_factory=list)
    timeslices: SetMembers = Field(default_factory=list)
    seasons: SetMembers = Field(default_factory=list)
    day_types: SetMembers = Field(default_factory=list)
    daily_time_brackets: SetMembers = Field(default_factory=list)

    def build_time_sets(self) -> dict[str, list[str]]:
        return {set_name: getattr(self, field) for field, set_name in TIME_SETS.items()}


class TzModelDocument(TzPart):
    id: object = None
    time_definition: TzTimeDefinitionPart
    regions: Items = Field(default_factory=list)
    regionsgroup: Items = Field(default_factory=list)
    commodities: Items = Field(default_factory=list)
    impacts: Items = Field(default_factory=list)
    technologies: Items = Field(default_factory=list)
    storage: Items = Field(default_factory=list)
    trade: Items = Field(default_factory=list)

    def list_items(self, owner: TzOwner) -> list[object]:
        items: list[object] = getattr(self, owner)
        return items


class TzObject(NamedTuple):
    """One object, its name in messages, the member of each owner column that it adds to its
    rows, and its fields."""

    owner: TzOwner
    name: str
    keys: tuple[str, ...]
    field_values: Mapping[str, object]


class SkippedObject(NamedTuple):
    path: TzPath
    note: str


class ItemPlace(NamedTuple):
    """The owner of a list, and the key members that the object holding the list adds."""

    owner: TzOwner
    keys: tuple[str, ...]


Part = TypeVar("Part", bound=TzKeyedPart, covariant=True)


@dataclass(frozen=True)
class CheckedItems(Generic[Part]):
    """The objects of one list that the source can use, and a note for each that it cannot."""

    place: ItemPlace
    parts: Sequence[Part]
    skipped: Sequence[SkippedObject]

    @property
    def objects(self) -> list[TzObject]:
        return [
            TzObject(
                self.place.owner,
                join_tz_names(*self.place.keys, part.label),
                (*self.place.keys, part.key_member),
                part.field_values,
            )
            for part in self.parts
        ]


@dataclass(frozen=True)
class TzObjects:
    objects: list[TzObject]
    skipped: list[SkippedObject]


def build_tz_objects(document: TzModelDocument) -> TzObjects:
    technologies = _check_items(_build_list_place(TzOwner.TECHNOLOGIES), document, TzTechnologyPart)
    groups: list[CheckedItems[TzKeyedPart]] = [
        technologies,
        _check_items(_build_list_place(TzOwner.TRADE), document, TzTradePart),
        *[_check_items(_build_list_place(owner), document, TzNamedPart) for owner in _NAMED_OWNERS],
        *[_check_operating_modes(technology) for technology in technologies.parts],
    ]
    return TzObjects(
        objects=[
            *_build_single_objects(document),
            *[tz_object for group in groups for tz_object in group.objects],
        ],
        skipped=[skipped for group in groups for skipped in group.skipped],
    )


def _build_list_place(owner: TzOwner) -> ItemPlace:
    return ItemPlace(owner, ())


def _build_single_objects(document: TzModelDocument) -> list[TzObject]:
    return [
        TzObject(TzOwner.MODEL, "", (), document.field_values),
        TzObject(TzOwner.TIME_DEFINITION, "", (), document.time_definition.field_values),
    ]


def _check_operating_modes(technology: TzTechnologyPart) -> CheckedItems[TzNamedPart]:
    place = ItemPlace(TzOwner.OPERATING_MODES, (technology.id,))
    return _check_list(place, technology.operating_modes, TzNamedPart)


def _check_items(
    place: ItemPlace, document: TzModelDocument, part_type: type[Part]
) -> CheckedItems[Part]:
    return _check_list(place, document.list_items(place.owner), part_type)


def _check_list(place: ItemPlace, items: list[object], part_type: type[Part]) -> CheckedItems[Part]:
    results = [
        (position, item, _check_item(item, part_type)) for position, item in enumerate(items, 1)
    ]
    return CheckedItems(
        place=place,
        parts=[result for _, _, result in results if not isinstance(result, str)],
        skipped=[
            _build_skipped_object(place, _build_item_label(position, item), result)
            for position, item, result in results
            if isinstance(result, str)
        ],
    )


def _check_item(item: object, part_type: type[Part]) -> Part | str:
    """The checked object, or the first reason that the source cannot use it."""
    try:
        return part_type.model_validate(item)
    except ValidationError as exc:
        error = exc.errors()[0]
        return f"{join_tz_names(*map(str, error['loc']))}: {error['msg']}"


def _build_item_label(position: int, item: object) -> str:
    """An object that states a usable `id` takes it as its name, else its place in the list."""
    item_id = _normalise_member(item.get("id")) if isinstance(item, dict) else None
    return item_id if isinstance(item_id, str) else _ITEM_NAME.format(position=position)


def _build_skipped_object(place: ItemPlace, label: str, reason: str) -> SkippedObject:
    path = TzPath(place.owner, join_tz_names(*place.keys, label))
    return SkippedObject(path, _SKIPPED_OBJECT_NOTE.format(reason=reason))


def build_tz_sets(document: TzModelDocument, objects: list[TzObject]) -> dict[str, list[str]]:
    """The members of each set, once each, in the order that the document states them."""
    object_sets = {
        set_name: [tz_object.keys[-1] for tz_object in objects if tz_object.owner is owner]
        for owner, set_name in OBJECT_SETS.items()
    }
    sets = {**document.time_definition.build_time_sets(), **object_sets}
    return {name: list(dict.fromkeys(members)) for name, members in sets.items()}


def report_skipped_objects(skipped: list[SkippedObject], recorder: EventRecorder) -> None:
    notes = {skipped_object.path: skipped_object.note for skipped_object in skipped}
    report_tz_paths(_SKIPPED_OBJECTS, notes, recorder)


def report_unknown_fields(objects: list[TzObject], recorder: EventRecorder) -> None:
    notes = dict.fromkeys(_list_unknown_fields(objects), _UNKNOWN_FIELD_NOTE)
    report_tz_paths(_UNKNOWN_FIELDS, notes, recorder)


def _list_unknown_fields(objects: list[TzObject]) -> list[TzPath]:
    """A field that states null holds no model data, so it is not unknown."""
    return [
        TzPath(tz_object.owner, join_tz_names(tz_object.name, name))
        for tz_object in objects
        for name, value in tz_object.field_values.items()
        if value is not None and (tz_object.owner, name) not in _KNOWN_FIELDS
    ]
