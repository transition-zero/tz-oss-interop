from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Annotated, Generic, NamedTuple, TypeVar

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError

from interop.core.reporting import EventRecorder
from interop.plugins.shared.osemosys_canonical.events import (
    SourceName,
    SourceReport,
    report_source_events,
)
from interop.plugins.shared.osemosys_canonical.tz_fields import (
    OBJECT_SETS,
    REGION_PAIR_FIELDS,
    TIME_SETS,
    TZ_FIELDS_BY_KEY,
    TzField,
    TzOwner,
    build_tz_name,
)
from interop.plugins.shared.osemosys_canonical.tz_values import (
    build_region_pairs,
    normalise_member,
)
from interop.ports.outbound.reporting import EventKind

_UNKNOWN_FIELD_NOTE = "the TZ-format field has no raw table, so the raw stage leaves it out"
_SKIPPED_OBJECT_NOTE = "the object cannot be used ({reason}), so the raw stage leaves it out"
_SKIPPED_MEMBER_NOTE = (
    "the member {value!r} is not a string or a number, so the raw stage leaves it out"
)
_ITEM_NAME = "item {position}"
_REGION_PAIRS_FIELD = "construct_region_pairs"
_UNREAD_REGION_PAIRS_NOTE = (
    "the field states {value!r}, not true or false, so the source copies no region pair"
)
_TZ_WARNING = "%d TZ-format {reason}, so the raw stage leaves each out: %s"


def _build_tz_report(kind: EventKind, reason: str) -> SourceReport:
    return SourceReport(kind, _TZ_WARNING.format(reason=reason), is_labelled_by_path=True)


_UNREAD_FIELDS = _build_tz_report(
    EventKind.NOT_MAPPED, "field(s) state a value that cannot be read"
)
_UNKNOWN_FIELDS = _build_tz_report(EventKind.NOT_MAPPED, "field(s) have no raw table")
_SKIPPED_OBJECTS = _build_tz_report(EventKind.COMPONENT_SKIPPED, "object(s) cannot be used")
_SKIPPED_MEMBERS = _build_tz_report(
    EventKind.COMPONENT_SKIPPED, "set member(s) are not a string or a number"
)
_NAMED_OWNERS = (
    TzOwner.REGIONS,
    TzOwner.REGION_GROUPS,
    TzOwner.COMMODITIES,
    TzOwner.IMPACTS,
    TzOwner.STORAGE,
)


def _normalise_set_members(value: object) -> object:
    """The TZ format can state a set as a count n, which stands for the members 1 to n."""
    if value is None:
        return []
    if isinstance(value, int) and not isinstance(value, bool):
        return list(range(1, value + 1))
    return value


def _normalise_items(value: object) -> object:
    return [] if value is None else value


Member = Annotated[str, BeforeValidator(normalise_member)]
# Check each member and each object later and alone, so that one bad one does not fail the
# whole document.
SetMembers = Annotated[list[object], BeforeValidator(_normalise_set_members)]
Items = Annotated[list[object], BeforeValidator(_normalise_items)]


class TzPart(BaseModel):
    """The fields that an object does not declare are its model data, so do not forbid extra
    fields."""

    model_config = ConfigDict(extra="allow")

    long_name: object = None
    description: object = None
    otoole_cfg: object = None
    defaults_otoole: object = None

    @property
    def field_values(self) -> dict[str, object]:
        return dict(self.model_extra or {})


class TzKeyedPart(TzPart):
    @property
    def key_member(self) -> str:
        raise NotImplementedError

    @property
    def label(self) -> str:
        return self.key_member

    @property
    def unread_fields(self) -> dict[str, str]:
        return {}


class TzNamedPart(TzKeyedPart):
    id: Member

    @property
    def key_member(self) -> str:
        return self.id


class TzTechnologyPart(TzNamedPart):
    operating_modes: Items = Field(default_factory=list)


class TzTradePart(TzKeyedPart):
    """The `id` of a trade names no set member, so the commodity is the key member of its rows."""

    id: Member | None = None
    commodity: Member
    construct_region_pairs: object = None

    @property
    def key_member(self) -> str:
        return self.commodity

    @property
    def label(self) -> str:
        return self.id or self.commodity

    @property
    def field_values(self) -> dict[str, object]:
        values = super().field_values
        if self.construct_region_pairs is not True:
            return values
        return {
            name: build_region_pairs(value) if name in REGION_PAIR_FIELDS else value
            for name, value in values.items()
        }

    @property
    def unread_fields(self) -> dict[str, str]:
        flag = self.construct_region_pairs
        if flag is None or isinstance(flag, bool):
            return {}
        return {_REGION_PAIRS_FIELD: _UNREAD_REGION_PAIRS_NOTE.format(value=flag)}


class TimeSets(NamedTuple):
    sets: dict[str, list[str]]
    skipped: dict[SourceName, str]


class TzTimeDefinitionPart(TzPart):
    id: object = None
    years: SetMembers = Field(default_factory=list)
    timeslices: SetMembers = Field(default_factory=list)
    seasons: SetMembers = Field(default_factory=list)
    day_types: SetMembers = Field(default_factory=list)
    daily_time_brackets: SetMembers = Field(default_factory=list)

    def build_time_sets(self) -> TimeSets:
        members = {field: list(map(normalise_member, getattr(self, field))) for field in TIME_SETS}
        return TimeSets(
            sets={
                TIME_SETS[field]: [member for member in found if isinstance(member, str)]
                for field, found in members.items()
            },
            skipped=_build_skipped_members(members),
        )


def _build_skipped_members(members: dict[str, list[object]]) -> dict[SourceName, str]:
    return {
        SourceName(
            TzOwner.TIME_DEFINITION, build_tz_name(field, _ITEM_NAME.format(position=position))
        ): _SKIPPED_MEMBER_NOTE.format(value=member)
        for field, found in members.items()
        for position, member in enumerate(found, 1)
        if not isinstance(member, str)
    }


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
    owner: TzOwner
    name: str
    keys: tuple[str, ...]
    field_values: Mapping[str, object]


class SkippedObject(NamedTuple):
    path: SourceName
    note: str


class ItemPlace(NamedTuple):
    owner: TzOwner
    keys: tuple[str, ...]


Part = TypeVar("Part", bound=TzKeyedPart, covariant=True)


@dataclass(frozen=True)
class PartList(Generic[Part]):
    place: ItemPlace
    parts: Sequence[Part]
    skipped: Sequence[SkippedObject]

    @property
    def objects(self) -> list[TzObject]:
        return [
            TzObject(
                self.place.owner, self._build_name(part), self._build_keys(part), part.field_values
            )
            for part in self.parts
        ]

    @property
    def unread_fields(self) -> dict[SourceName, str]:
        return {
            SourceName(self.place.owner, build_tz_name(self._build_name(part), field)): note
            for part in self.parts
            for field, note in part.unread_fields.items()
        }

    def _build_name(self, part: TzKeyedPart) -> str:
        return build_tz_name(*self.place.keys, part.label)

    def _build_keys(self, part: TzKeyedPart) -> tuple[str, ...]:
        return (*self.place.keys, part.key_member)


@dataclass(frozen=True)
class TzObjects:
    objects: list[TzObject]
    skipped: list[SkippedObject]
    unread_fields: dict[SourceName, str]


class StatedField(NamedTuple):
    tz_object: TzObject
    field: TzField
    value: object

    @property
    def path(self) -> SourceName:
        return SourceName(
            self.tz_object.owner, build_tz_name(self.tz_object.name, self.field.field)
        )


class StatedFields(NamedTuple):
    """`unknown` names each field that states a value but that the field table does not hold."""

    known: list[StatedField]
    unknown: list[SourceName]


def build_tz_objects(document: TzModelDocument) -> TzObjects:
    technologies = _build_owner_parts(TzOwner.TECHNOLOGIES, document, TzTechnologyPart)
    part_lists: list[PartList[TzKeyedPart]] = [
        technologies,
        _build_owner_parts(TzOwner.TRADE, document, TzTradePart),
        *[_build_owner_parts(owner, document, TzNamedPart) for owner in _NAMED_OWNERS],
        *[_build_operating_modes(technology) for technology in technologies.parts],
    ]
    return _build_object_summary(document, part_lists)


def _build_object_summary(
    document: TzModelDocument, part_lists: list[PartList[TzKeyedPart]]
) -> TzObjects:
    listed = [tz_object for part_list in part_lists for tz_object in part_list.objects]
    return TzObjects(
        objects=[*_build_single_objects(document), *listed],
        skipped=[skipped for part_list in part_lists for skipped in part_list.skipped],
        unread_fields={
            path: note for part_list in part_lists for path, note in part_list.unread_fields.items()
        },
    )


def _build_single_objects(document: TzModelDocument) -> list[TzObject]:
    return [
        TzObject(TzOwner.MODEL, "", (), document.field_values),
        TzObject(TzOwner.TIME_DEFINITION, "", (), document.time_definition.field_values),
    ]


def _build_operating_modes(technology: TzTechnologyPart) -> PartList[TzNamedPart]:
    place = ItemPlace(TzOwner.OPERATING_MODES, (technology.id,))
    return _build_part_list(place, technology.operating_modes, TzNamedPart)


def _build_owner_parts(
    owner: TzOwner, document: TzModelDocument, part_type: type[Part]
) -> PartList[Part]:
    return _build_part_list(ItemPlace(owner, ()), document.list_items(owner), part_type)


def _build_part_list(
    place: ItemPlace, items: list[object], part_type: type[Part]
) -> PartList[Part]:
    parts: list[Part] = []
    skipped: list[SkippedObject] = []
    for position, item in enumerate(items, 1):
        try:
            parts.append(part_type.model_validate(item))
        except ValidationError as exc:
            label = _build_item_label(position, item)
            skipped.append(_build_skipped_object(place, label, _build_error_reason(exc)))
    return PartList(place, parts, skipped)


def _build_error_reason(error: ValidationError) -> str:
    first = error.errors()[0]
    return f"{build_tz_name(*map(str, first['loc']))}: {first['msg']}"


def _build_item_label(position: int, item: object) -> str:
    item_id = normalise_member(item.get("id")) if isinstance(item, dict) else None
    return item_id if isinstance(item_id, str) else _ITEM_NAME.format(position=position)


def _build_skipped_object(place: ItemPlace, label: str, reason: str) -> SkippedObject:
    path = SourceName(place.owner, build_tz_name(*place.keys, label))
    return SkippedObject(path, _SKIPPED_OBJECT_NOTE.format(reason=reason))


def build_stated_fields(objects: list[TzObject]) -> StatedFields:
    known: list[StatedField] = []
    unknown: list[SourceName] = []
    for tz_object, name, value in _list_field_values(objects):
        field = TZ_FIELDS_BY_KEY.get((tz_object.owner, name))
        if field is None:
            unknown.append(SourceName(tz_object.owner, build_tz_name(tz_object.name, name)))
        else:
            known.append(StatedField(tz_object, field, value))
    return StatedFields(known, unknown)


def _list_field_values(objects: list[TzObject]) -> list[tuple[TzObject, str, object]]:
    return [
        (tz_object, name, value)
        for tz_object in objects
        for name, value in tz_object.field_values.items()
        if value is not None
    ]


def build_tz_sets(time_sets: dict[str, list[str]], objects: list[TzObject]) -> dict[str, list[str]]:
    """A member repeated in the model is one member, so a wildcard expands over it once."""
    object_sets = {
        set_name: [tz_object.keys[-1] for tz_object in objects if tz_object.owner is owner]
        for owner, set_name in OBJECT_SETS.items()
    }
    sets = {**time_sets, **object_sets}
    return {name: list(dict.fromkeys(members)) for name, members in sets.items()}


def report_skipped_objects(skipped: list[SkippedObject], recorder: EventRecorder) -> None:
    notes = {skipped_object.path: skipped_object.note for skipped_object in skipped}
    report_source_events(_SKIPPED_OBJECTS, notes, recorder)


def report_skipped_members(skipped: dict[SourceName, str], recorder: EventRecorder) -> None:
    report_source_events(_SKIPPED_MEMBERS, skipped, recorder)


def report_unread_fields(unread_fields: dict[SourceName, str], recorder: EventRecorder) -> None:
    report_source_events(_UNREAD_FIELDS, unread_fields, recorder)


def report_unknown_fields(unknown: list[SourceName], recorder: EventRecorder) -> None:
    report_source_events(_UNKNOWN_FIELDS, dict.fromkeys(unknown, _UNKNOWN_FIELD_NOTE), recorder)
