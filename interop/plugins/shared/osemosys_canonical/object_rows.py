from __future__ import annotations

from typing import NamedTuple

from interop.plugins.shared.osemosys_canonical.constants import (
    OBJECT_PART_LABEL,
    REGION,
    AnnotationColumn,
    ObjectPart,
)
from interop.plugins.shared.osemosys_canonical.mappings import ObjectRow, list_template_fields

_UNFILLED_LOCATION_NOTE = (
    "row {index} of {part} gives the location {template}, but its match captures no {groups} "
    "for {member}, so location stays empty"
)


class MemberKey(NamedTuple):
    """The key of a region's own annotation row repeats the region name as `member`."""

    region: str
    member: str


class RowAnnotations(NamedTuple):
    """`unfilled_note` says why the row gives a location that it cannot fill for this member."""

    part: ObjectPart
    row_index: int
    annotations: dict[AnnotationColumn, str]
    unfilled_note: str | None = None

    @property
    def stated_columns(self) -> set[AnnotationColumn]:
        """A location that the row cannot fill still stops an inference of the location."""
        unfilled = {AnnotationColumn.LOCATION} if self.unfilled_note is not None else set()
        return {*self.annotations, *unfilled}


class RowMember(NamedTuple):
    part: ObjectPart
    row_index: int
    row: ObjectRow
    groups: dict[str, str | None]


class LocationTemplate(NamedTuple):
    matched: RowMember
    template: str
    key: MemberKey


def find_row_annotations(
    rows: list[ObjectRow], part: ObjectPart, key: MemberKey
) -> RowAnnotations | None:
    for index, row in enumerate(rows):
        groups = row.find_groups(key.member)
        if groups is not None:
            return _build_row_annotations(RowMember(part, index, row, groups), key)
    return None


def _build_row_annotations(matched: RowMember, key: MemberKey) -> RowAnnotations:
    annotations = matched.row.annotations
    template = annotations.pop(AnnotationColumn.LOCATION, None)
    found = RowAnnotations(matched.part, matched.row_index, annotations)
    if template is None:
        return found
    return _build_located_annotations(found, LocationTemplate(matched, template, key))


def _build_located_annotations(found: RowAnnotations, location: LocationTemplate) -> RowAnnotations:
    values = {**location.matched.groups, REGION: location.key.region}
    fields = list_template_fields(location.template)
    uncaptured = [name for name in fields if values.get(name) is None]
    if uncaptured:
        return found._replace(unfilled_note=_build_unfilled_note(location, uncaptured))
    filled = {**found.annotations, AnnotationColumn.LOCATION: location.template.format(**values)}
    return found._replace(annotations=filled)


def _build_unfilled_note(location: LocationTemplate, uncaptured: list[str]) -> str:
    return _UNFILLED_LOCATION_NOTE.format(
        index=location.matched.row_index,
        part=OBJECT_PART_LABEL.format(part=location.matched.part),
        template=location.template,
        groups=", ".join(uncaptured),
        member=location.key.member,
    )


def build_row_note(row: RowAnnotations) -> str:
    columns = ", ".join(row.annotations)
    return f"row {row.row_index} of {OBJECT_PART_LABEL.format(part=row.part)} gives {columns}"
