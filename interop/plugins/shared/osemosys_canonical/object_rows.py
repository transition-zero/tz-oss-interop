from __future__ import annotations

from typing import NamedTuple

from interop.plugins.shared.osemosys_canonical.constants import (
    OBJECT_PART_LABEL,
    REGION,
    AnnotationColumn,
    ObjectPart,
)
from interop.plugins.shared.osemosys_canonical.mappings import ObjectRow, list_template_fields
from interop.ports.errors import UserInputError


class MemberKey(NamedTuple):
    """The key of a region's own annotation row repeats the region name as `member`."""

    region: str
    member: str


class RowAnnotations(NamedTuple):
    part: ObjectPart
    row_index: int
    annotations: dict[AnnotationColumn, str]


class RowMember(NamedTuple):
    part: ObjectPart
    row_index: int
    row: ObjectRow
    groups: dict[str, str | None]


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
    template = annotations.get(AnnotationColumn.LOCATION)
    if template is not None:
        annotations[AnnotationColumn.LOCATION] = _build_location(matched, template, key)
    return RowAnnotations(matched.part, matched.row_index, annotations)


def _build_location(matched: RowMember, template: str, key: MemberKey) -> str:
    values = {**matched.groups, REGION: key.region}
    uncaptured = [name for name in list_template_fields(template) if values.get(name) is None]
    if uncaptured:
        raise UserInputError(
            f"row {matched.row_index} of {OBJECT_PART_LABEL.format(part=matched.part)} gives the "
            f"location {template}, but its match captures no {', '.join(uncaptured)} "
            f"for {key.member}"
        )
    return template.format(**values)


def build_row_note(row: RowAnnotations) -> str:
    columns = ", ".join(row.annotations)
    return f"row {row.row_index} of {OBJECT_PART_LABEL.format(part=row.part)} gives {columns}"
