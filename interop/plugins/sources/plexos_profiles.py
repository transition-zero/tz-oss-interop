"""The data file that a PLEXOS property value reads, and the name its rows carry there.

A property value tagged to a Data File reads that object's ``Filename``. A value tagged to a
Variable reads the file that the Variable's ``Profile`` names, either as its own text or
through a Data File that the Profile is tagged to. Such a value is the object's share of
that shared profile, so the staged series is scaled by it. A value tagged to both reads the
Data File, and the Variable's profile escalates it.
"""

from __future__ import annotations

from typing import Any, NamedTuple

from interop.plugins.shared.plexos_constants import (
    PlexosClass,
    PlexosMembershipCol,
    PlexosProperty,
    PlexosPropertyCol,
)
from interop.plugins.sources.plexos_scenarios import ScenarioOverlay
from interop.plugins.sources.plexos_tables import (
    CLASS_ID,
    DATA_ID,
    DATA_TABLE,
    MEMBERSHIP_ID,
    MEMBERSHIP_TABLE,
    OBJECT_ID,
    OBJECT_TABLE,
    PROPERTY_ID,
    TAG_TABLE,
    TEXT_TABLE,
    VALUE,
    DroppedRecords,
    Lookup,
    RowsByTable,
    build_child_by_membership,
    build_data_reference,
    build_name_lookup,
    class_id_of,
    objects_of_class,
)

_NO_SCALING = 1.0
_PERCENT = 100.0


class _CsvSource(NamedTuple):
    """The class whose objects name a CSV, and the text property holding that path."""

    class_name: str
    text_property: str


_DATA_FILE_SOURCE = _CsvSource(PlexosClass.DATA_FILE, PlexosProperty.FILENAME)
_VARIABLE_SOURCE = _CsvSource(PlexosClass.VARIABLE, PlexosProperty.PROFILE)


class ProfileRef(NamedTuple):
    """The CSV a value reads from, whether the value is a share of it rather than all of it, and
    the Variable it reads through, whose name the file's rows carry.
    """

    path: str
    is_share: bool
    variable: str | None
    escalator: str | None = None


def build_scaling(profile: ProfileRef | None, value: float | None, is_share_percent: bool) -> float:
    """The multiplier that a value applies to the profile it reads.

    A share written as a percentage is a multiplier of 100, so it divides down to one. A zero
    share is PLEXOS's placeholder for a value the profile supplies outright, not a multiplier
    that would erase it.
    """
    if profile is None or not profile.is_share or not value:
        return _NO_SCALING
    return value / _PERCENT if is_share_percent else value


def build_row_name(profile: ProfileRef | None, membership: dict[str, Any]) -> str:
    """The name a data file gives this value's rows."""
    if profile is not None and profile.variable is not None:
        return profile.variable
    return str(membership[PlexosMembershipCol.CHILD_OBJECT])


def list_row_names(row: dict[str, Any]) -> list[str]:
    """The names a data file can give the row of this resolved property value.

    A property of a membership between two objects takes a row named after both of them, and
    a model can write them in either order.
    """
    row_name = str(row[PlexosPropertyCol.ROW_NAME])
    parent = str(row[PlexosMembershipCol.PARENT_OBJECT])
    if row[PlexosMembershipCol.PARENT_CLASS] == PlexosClass.SYSTEM:
        return [row_name]
    return [row_name, parent + row_name, row_name + parent]


def build_profile_refs(
    tables: RowsByTable,
    property_names: Lookup,
    overlay: ScenarioOverlay,
    dropped: DroppedRecords,
) -> dict[str, ProfileRef]:
    """Map each t_data id to the CSV it reads from, whether tagged directly or via a Variable.

    A value tagged straight to a Data File reads that file's Filename; a value tagged to a
    Variable reads the CSV named by that Variable's Profile, with the value as a scaling
    factor the mapping applies. A direct Data File wins if a value carries both, and the
    Variable then escalates it.
    """
    data_files = _build_object_csv_paths(
        tables, property_names, overlay, dropped, _DATA_FILE_SOURCE
    )
    variables = _build_variable_csv_paths(tables, property_names, overlay, data_files)
    by_variable = _build_variable_refs(tables, variables)
    by_data_file = _build_data_file_refs(tables, data_files)
    escalated = {
        data_id: ref._replace(escalator=by_variable[data_id].variable)
        for data_id, ref in by_data_file.items()
        if data_id in by_variable
    }
    return {**by_variable, **by_data_file, **escalated}


def _build_variable_refs(tables: RowsByTable, paths: dict[str, str]) -> dict[str, ProfileRef]:
    """Map each t_data id tagged to a Variable to that Variable's CSV, as a share of it."""
    names = build_name_lookup(tables, OBJECT_TABLE, OBJECT_ID).by_id
    tags = _build_tags_by_data(tables, PlexosClass.VARIABLE)
    return {
        data_id: ProfileRef(paths[obj], True, names.get(obj))
        for data_id, obj in tags.items()
        if obj in paths
    }


def _build_data_file_refs(tables: RowsByTable, paths: dict[str, str]) -> dict[str, ProfileRef]:
    """Map each t_data id tagged to a Data File to that file, as the whole of the value."""
    tags = _build_tags_by_data(tables, PlexosClass.DATA_FILE)
    return {
        data_id: ProfileRef(paths[obj], False, None)
        for data_id, obj in tags.items()
        if obj in paths
    }


def _build_variable_csv_paths(
    tables: RowsByTable,
    property_names: Lookup,
    overlay: ScenarioOverlay,
    data_file_paths: dict[str, str],
) -> dict[str, str]:
    """Each Variable's profile CSV, named by its Profile's own text or by a Data File it tags.

    A Profile carrying a timeslice pattern or a plain number names no file, so that Variable
    contributes no path; it is a value, not a broken reference.
    """
    texts = _build_file_text_lookup(tables)
    tagged_files = _build_tags_by_data(tables, PlexosClass.DATA_FILE)
    paths: dict[str, str] = {}
    for owner, data in _build_object_csv_data(
        tables, property_names, overlay, _VARIABLE_SOURCE
    ).items():
        data_id = data[DATA_ID]
        path = texts.by_id.get(data_id) or data_file_paths.get(tagged_files.get(data_id, ""))
        if path is not None:
            paths[owner] = path
    return paths


def _build_object_csv_paths(
    tables: RowsByTable,
    property_names: Lookup,
    overlay: ScenarioOverlay,
    dropped: DroppedRecords,
    source: _CsvSource,
) -> dict[str, str]:
    """Map each object of a class to the CSV path in its text-valued property."""
    texts = _build_file_text_lookup(tables)
    paths: dict[str, str] = {}
    for owner, data in _build_object_csv_data(tables, property_names, overlay, source).items():
        path = dropped.resolve(texts, build_data_reference(data, DATA_ID))
        if path is not None:
            paths[owner] = path
    return paths


def _build_object_csv_data(
    tables: RowsByTable, property_names: Lookup, overlay: ScenarioOverlay, source: _CsvSource
) -> dict[str, dict[str, Any]]:
    """Map each object of a class to the winning ``t_data`` row of its Filename/Profile property.

    A Data File that names one CSV per month carries a row per Scenario, so a row belonging
    to a scenario the selected Model does not activate is skipped rather than overwriting.
    """
    object_ids = objects_of_class(tables, source.class_name)
    children = Lookup(MEMBERSHIP_TABLE, build_child_by_membership(tables))
    found: dict[str, dict[str, Any]] = {}
    for data in _list_text_property_rows(tables, property_names, source.text_property):
        owner = children.by_id.get(data[MEMBERSHIP_ID])
        if owner in object_ids and overlay.find_priority(data[DATA_ID]) is not None:
            found[owner] = data
    return found


def _build_file_text_lookup(tables: RowsByTable) -> Lookup:
    """The t_text values that name a file.

    t_text holds every text value in the export and tells them apart only by class_id:
    a Data File name is a path, a Timeslice is a banding pattern that names no file.
    """
    data_file_class = class_id_of(tables, PlexosClass.DATA_FILE)
    if data_file_class is None:
        return Lookup(TEXT_TABLE, {})
    return Lookup(
        TEXT_TABLE,
        {
            row[DATA_ID]: row[VALUE]
            for row in tables.get(TEXT_TABLE, [])
            if row.get(CLASS_ID) == data_file_class
        },
    )


def _list_text_property_rows(
    tables: RowsByTable, property_names: Lookup, text_property: str
) -> list[dict[str, Any]]:
    """The ``t_data`` rows holding an object's text-valued property (a Filename or Profile)."""
    return [
        data
        for data in tables.get(DATA_TABLE, [])
        if property_names.by_id.get(data[PROPERTY_ID]) == text_property
    ]


def _build_tags_by_data(tables: RowsByTable, class_name: str) -> dict[str, str]:
    """Map each tagged t_data id to the object of the given class it reads from."""
    object_ids = objects_of_class(tables, class_name)
    return {
        row[DATA_ID]: row[OBJECT_ID]
        for row in tables.get(TAG_TABLE, [])
        if row[OBJECT_ID] in object_ids
    }
