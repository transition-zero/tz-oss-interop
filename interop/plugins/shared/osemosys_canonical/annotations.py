from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import NamedTuple

import polars as pl

from interop.core.reporting import EventRecorder
from interop.plugins.shared.osemosys_canonical.absent_members import build_set_members
from interop.plugins.shared.osemosys_canonical.constants import (
    ANNOTATION_NAME_SEPARATOR,
    ELECTRICITY_CARRIER,
    OBJECT_PART_COLUMNS,
    OBJECT_PART_SETS,
    REGION,
    AnnotationColumn,
    FlowParameter,
    ObjectPart,
)
from interop.plugins.shared.osemosys_canonical.events import AnnotatedMember, record_annotation
from interop.plugins.shared.osemosys_canonical.mappings import ObjectRows
from interop.plugins.shared.osemosys_canonical.object_rows import (
    MemberKey,
    RowAnnotations,
    build_row_note,
    find_row_annotations,
)
from interop.plugins.shared.osemosys_canonical.technology_kinds import (
    FuelAnnotation,
    FuelFlow,
    Inference,
    LocatedFlow,
    TechnologyStructure,
    build_storage_technologies,
    build_technology_flows,
    build_technology_location,
    choose_kind,
)
from interop.plugins.shared.warning_text import name_a_few
from interop.ports.outbound.reporting import EventKind

log = logging.getLogger(__name__)

_REGION_LOCATION_RULES: dict[ObjectPart, str] = {
    ObjectPart.REGIONS: "a region is its own location",
    ObjectPart.FUELS: "a fuel takes the location of its region",
    ObjectPart.STORAGES: "a storage takes the location of its region",
}
_NO_KIND_NOTE = (
    f"no kind fits its rows in {FlowParameter.INPUT_ACTIVITY_RATIO}, "
    f"{FlowParameter.OUTPUT_ACTIVITY_RATIO}, {FlowParameter.TECHNOLOGY_TO_STORAGE} and "
    f"{FlowParameter.TECHNOLOGY_FROM_STORAGE}, so kind stays empty"
)


class MemberAnnotation(NamedTuple):
    part: ObjectPart
    key: MemberKey
    row: RowAnnotations | None
    inferred: dict[AnnotationColumn, Inference]

    @property
    def given(self) -> dict[AnnotationColumn, str]:
        return {} if self.row is None else self.row.annotations

    @property
    def unfilled_note(self) -> str | None:
        return None if self.row is None else self.row.unfilled_note

    @property
    def values(self) -> dict[AnnotationColumn, str]:
        """Merge `given` last, so that a value a row gives overrides an inferred value."""
        return {**{column: found.value for column, found in self.inferred.items()}, **self.given}


def map_annotations(
    canonical: dict[str, pl.LazyFrame], rows: ObjectRows, recorder: EventRecorder
) -> dict[str, pl.DataFrame]:
    keys = _list_member_keys(canonical)
    annotated = {
        part: [_build_region_annotation(part, key, rows) for key in keys[part]]
        for part in _REGION_LOCATION_RULES
    }
    fuels = _build_fuel_annotations(annotated[ObjectPart.FUELS])
    annotated[ObjectPart.TECHNOLOGIES] = _build_technology_annotations(canonical, keys, rows, fuels)
    _report_annotations(annotated, recorder)
    return {OBJECT_PART_SETS[part]: _build_table(part, found) for part, found in annotated.items()}


def _list_member_keys(canonical: dict[str, pl.LazyFrame]) -> dict[ObjectPart, list[MemberKey]]:
    sets = {name: canonical[name] for name in OBJECT_PART_SETS.values() if name in canonical}
    members = {name: series.to_list() for name, series in build_set_members(sets).items()}
    regions = members.get(REGION, [])
    return {
        part: _build_member_keys(part, regions, members.get(set_name, []))
        for part, set_name in OBJECT_PART_SETS.items()
    }


def _build_member_keys(part: ObjectPart, regions: list[str], members: list[str]) -> list[MemberKey]:
    if part == ObjectPart.REGIONS:
        return [MemberKey(region, region) for region in regions]
    return [MemberKey(region, member) for region in regions for member in members]


def _build_region_annotation(
    part: ObjectPart, key: MemberKey, rows: ObjectRows
) -> MemberAnnotation:
    inference = Inference(key.region, _REGION_LOCATION_RULES[part])
    return _build_member_annotation(part, key, rows, {AnnotationColumn.LOCATION: inference})


def _build_member_annotation(
    part: ObjectPart,
    key: MemberKey,
    rows: ObjectRows,
    inferences: dict[AnnotationColumn, Inference],
) -> MemberAnnotation:
    row = find_row_annotations(rows.list_rows(part), part, key)
    stated = set() if row is None else row.stated_columns
    inferred = {column: found for column, found in inferences.items() if column not in stated}
    return MemberAnnotation(part, key, row, inferred)


def _build_fuel_annotations(fuels: list[MemberAnnotation]) -> dict[MemberKey, FuelAnnotation]:
    return {
        fuel.key: FuelAnnotation(
            row_location=fuel.given.get(AnnotationColumn.LOCATION),
            is_electricity=fuel.values.get(AnnotationColumn.CARRIER) == ELECTRICITY_CARRIER,
        )
        for fuel in fuels
    }


def _build_technology_annotations(
    canonical: dict[str, pl.LazyFrame],
    keys: dict[ObjectPart, list[MemberKey]],
    rows: ObjectRows,
    fuels: dict[MemberKey, FuelAnnotation],
) -> list[MemberAnnotation]:
    flows = build_technology_flows(canonical)
    storages = build_storage_technologies(canonical)
    structures = {
        key: TechnologyStructure(
            _build_located_flows(key, flows.get(key, []), fuels), key in storages
        )
        for key in keys[ObjectPart.TECHNOLOGIES]
    }
    return [
        _build_member_annotation(
            ObjectPart.TECHNOLOGIES, key, rows, _build_technology_inferences(key, structure)
        )
        for key, structure in structures.items()
    ]


def _build_located_flows(
    key: MemberKey, flows: list[FuelFlow], fuels: dict[MemberKey, FuelAnnotation]
) -> list[LocatedFlow]:
    """The absent-member rule already left out each flow whose fuel is not in the fuel set, so
    the lookup cannot fail."""
    return [LocatedFlow(flow, fuels[MemberKey(key.region, flow.fuel)]) for flow in flows]


def _build_technology_inferences(
    key: MemberKey, structure: TechnologyStructure
) -> dict[AnnotationColumn, Inference]:
    inferences = {AnnotationColumn.LOCATION: build_technology_location(structure, key.region)}
    kind = choose_kind(structure)
    if kind is not None:
        inferences[AnnotationColumn.KIND] = kind
    return inferences


def _report_annotations(
    annotated: dict[ObjectPart, list[MemberAnnotation]], recorder: EventRecorder
) -> None:
    for found in annotated.values():
        for annotation in found:
            _record_member_events(annotation, recorder)
    _report_missing_kinds(annotated[ObjectPart.TECHNOLOGIES], recorder)
    _report_unfilled_locations([found for part in annotated.values() for found in part], recorder)


def _record_member_events(annotation: MemberAnnotation, recorder: EventRecorder) -> None:
    if annotation.row is not None and annotation.given:
        member = _build_annotated_member(annotation, annotation.given)
        record_annotation(
            recorder, EventKind.USER_CONFIG_DEFAULT_APPLIED, member, build_row_note(annotation.row)
        )
    if annotation.inferred:
        values = {column: found.value for column, found in annotation.inferred.items()}
        member = _build_annotated_member(annotation, values)
        record_annotation(
            recorder, EventKind.VALUE_DERIVED, member, _build_inference_note(annotation.inferred)
        )


def _build_inference_note(inferred: dict[AnnotationColumn, Inference]) -> str:
    return "; ".join(f"{column} {found.value}: {found.rule}" for column, found in inferred.items())


def _build_annotated_member(
    annotation: MemberAnnotation, values: Mapping[AnnotationColumn, str | None]
) -> AnnotatedMember:
    name = _build_member_name(annotation)
    return AnnotatedMember(OBJECT_PART_SETS[annotation.part], name, values)


def _build_member_name(annotation: MemberAnnotation) -> str:
    return ANNOTATION_NAME_SEPARATOR.join(_list_key_values(annotation.part, annotation.key))


def _report_missing_kinds(technologies: list[MemberAnnotation], recorder: EventRecorder) -> None:
    missing = [found for found in technologies if AnnotationColumn.KIND not in found.values]
    for annotation in missing:
        member = _build_annotated_member(annotation, {AnnotationColumn.KIND: None})
        record_annotation(recorder, EventKind.NOT_MAPPED, member, _NO_KIND_NOTE)
    if missing:
        log.warning(
            "no kind fits %d technology(ies) in their region, so each keeps an empty kind: %s",
            len(missing),
            name_a_few(_build_member_name(found) for found in missing),
        )


def _report_unfilled_locations(
    annotations: list[MemberAnnotation], recorder: EventRecorder
) -> None:
    unfilled = [found for found in annotations if found.unfilled_note is not None]
    for annotation in unfilled:
        member = _build_annotated_member(annotation, {AnnotationColumn.LOCATION: None})
        record_annotation(recorder, EventKind.NOT_MAPPED, member, annotation.unfilled_note or "")
    _warn_unfilled_locations(unfilled)


def _warn_unfilled_locations(unfilled: list[MemberAnnotation]) -> None:
    if unfilled:
        log.warning(
            "%d member(s) match an `objects:` row whose location captures nothing for them, so "
            "each keeps an empty location: %s",
            len(unfilled),
            name_a_few(_build_member_name(found) for found in unfilled),
        )


def _build_table(part: ObjectPart, annotations: list[MemberAnnotation]) -> pl.DataFrame:
    keys = [REGION] if part == ObjectPart.REGIONS else [REGION, OBJECT_PART_SETS[part]]
    columns = OBJECT_PART_COLUMNS[part]
    rows = [_build_table_row(found, columns) for found in annotations]
    return pl.DataFrame(rows, schema=dict.fromkeys([*keys, *columns], pl.Utf8), orient="row")


def _build_table_row(
    found: MemberAnnotation, columns: tuple[AnnotationColumn, ...]
) -> list[str | None]:
    values = found.values
    return [*_list_key_values(found.part, found.key), *(values.get(column) for column in columns)]


def _list_key_values(part: ObjectPart, key: MemberKey) -> list[str]:
    return [key.region] if part == ObjectPart.REGIONS else [key.region, key.member]
