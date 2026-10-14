from __future__ import annotations

from typing import NamedTuple

import polars as pl

from interop.core.reporting import EventRecorder
from interop.plugins.shared.osemosys_canonical.constants import RAW_VALUE_COL
from interop.plugins.shared.osemosys_canonical.raw_stage import RawTables
from interop.plugins.shared.osemosys_canonical.tz_document import (
    StatedFields,
    TimeSets,
    TzModelDocument,
    TzObjects,
    build_stated_fields,
    build_tz_objects,
    build_tz_sets,
    report_skipped_members,
    report_skipped_objects,
    report_unknown_fields,
    report_unread_fields,
)
from interop.plugins.shared.osemosys_canonical.tz_tables import (
    build_tz_declarations,
    build_tz_parameter_tables,
)


class TzParts(NamedTuple):
    objects: TzObjects
    fields: StatedFields
    time_sets: TimeSets


def build_tz_raw_tables(document: TzModelDocument, recorder: EventRecorder) -> RawTables:
    parts = _build_tz_parts(document)
    _report_unusable_parts(parts, recorder)
    sets = build_tz_sets(parts.time_sets.sets, parts.objects.objects)
    return RawTables(
        sets={name: _build_set_table(members) for name, members in sets.items()},
        parameters=build_tz_parameter_tables(parts.fields.known, sets, recorder),
        declarations=build_tz_declarations(),
    )


def _build_tz_parts(document: TzModelDocument) -> TzParts:
    tz_objects = build_tz_objects(document)
    return TzParts(
        objects=tz_objects,
        fields=build_stated_fields(tz_objects.objects),
        time_sets=document.time_definition.build_time_sets(),
    )


def _report_unusable_parts(parts: TzParts, recorder: EventRecorder) -> None:
    report_skipped_objects(parts.objects.skipped, recorder)
    report_skipped_members(parts.time_sets.skipped, recorder)
    report_unknown_fields(parts.fields.unknown, recorder)
    report_unread_fields(parts.objects.unread_fields, recorder)


def _build_set_table(members: list[str]) -> pl.DataFrame:
    return pl.DataFrame({RAW_VALUE_COL: members}, schema={RAW_VALUE_COL: pl.Utf8})
