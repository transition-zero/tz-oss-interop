"""Stage a PLEXOS input XML into the resolved dataset for the selected Model.

Parses the ``<MasterDataSet>`` XML into its ``t_*`` tables, then stages:

- one ``topology/<class>.parquet`` per PLEXOS class (verbatim class names, e.g.
  ``Node``, ``Region``, ``Generator``), one row per object of that class;
- ``topology/memberships.parquet``, the ``t_membership`` relationships with
  their class, object, and collection ids resolved back to names;
- ``topology/properties.parquet``, each property resolved to its winning
  ``t_data`` value under the selected Model's Scenario overlays (highest Read
  Order wins, base value otherwise), with a ``data_file`` path where the value
  is file-backed;
- one ``source_time_series`` frame per (owner class, property) whose value comes
  from an external CSV, streamed in as ``(snapshot, component, sample, value)`` rows.
  ``sample`` is null except where the CSV carries one column per Monte Carlo
  replication.

A row pointing at an id no other table defines is dropped and recorded as a
validation error, so a partial export stages the records it can resolve.

Each staging concern with a life of its own sits in a sibling module: the chronology in
``plexos_horizon``, the dated-property windowing in ``plexos_dated_properties``, the CSV
layouts in ``plexos_csv_layouts``, and the units a property is stated in with the rest of
the unit vocabulary in ``plexos_units``.
"""

from __future__ import annotations

import logging
import shutil
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar, NamedTuple

import polars as pl
from pydantic import BaseModel, Field

from interop.core.pipeline import StagedSource, State
from interop.plugins.shared.plexos_constants import (
    PlexosClass,
    PlexosMembershipCol,
    PlexosObjectCol,
    PlexosPropertyCol,
    PlexosResolvedTable,
)
from interop.plugins.shared.plexos_units import (
    StatedValue,
    UnitConversions,
    is_percent,
    stated_units,
)
from interop.plugins.shared.warning_text import name_a_few
from interop.plugins.sources.plexos_csv_layouts import (
    SampleScope,
    is_supported_layout,
    reshape_for_file,
    strip_bom,
    warn_no_series,
    warn_unstageable_layout,
)
from interop.plugins.sources.plexos_dated_properties import (
    UNDATED,
    DateBand,
    DatedRow,
    apply_window,
    date_bands,
    stepped_series_parts,
)
from interop.plugins.sources.plexos_horizon import Chronology, Window, reindex_onto
from interop.plugins.sources.plexos_tables import class_id_of, objects_of_class
from interop.ports.outbound.filesystem import FilesystemPort, Location
from interop.ports.outbound.validation import EnergyModelValidationError, ValidationSeverity

log = logging.getLogger(__name__)

_TOPOLOGY_SUBDIR = "topology"
_OBJECT_TABLE = "t_object"
_CLASS_TABLE = "t_class"
_CATEGORY_TABLE = "t_category"
_MEMBERSHIP_TABLE = "t_membership"
_COLLECTION_TABLE = "t_collection"
_CLASS_ID = "class_id"
_OBJECT_ID = "object_id"
_CATEGORY_ID = "category_id"
_COLLECTION_ID = "collection_id"
_NAME = "name"

_MEMBERSHIP_NAME_COLUMNS = (
    PlexosMembershipCol.PARENT_CLASS,
    PlexosMembershipCol.PARENT_OBJECT,
    PlexosMembershipCol.COLLECTION,
    PlexosMembershipCol.CHILD_CLASS,
    PlexosMembershipCol.CHILD_OBJECT,
)
# t_membership's own id, and its foreign-key columns.
_MEMBERSHIP_ID = "membership_id"
_PARENT_CLASS_ID = "parent_class_id"
_PARENT_OBJECT_ID = "parent_object_id"
_CHILD_CLASS_ID = "child_class_id"
_CHILD_OBJECT_ID = "child_object_id"

_DATA_TABLE = "t_data"
_PROPERTY_TABLE = "t_property"
_PROPERTY_ID = "property_id"
# The raw payload column t_data, t_text and t_attribute_data each carry.
_VALUE = "value"

# Scenario overlay resolution. A t_data row tagged (t_tag) to a Scenario is an
# override; its priority is the Scenario's "Read Order" attribute. Untagged
# rows are the base value, and lose to any active override.
_TAG_TABLE = "t_tag"
_BAND_TABLE = "t_band"
_ATTRIBUTE_TABLE = "t_attribute"
_ATTRIBUTE_DATA_TABLE = "t_attribute_data"
_DATA_ID = "data_id"
_BAND_ID = "band_id"
_ATTRIBUTE_ID = "attribute_id"
_READ_ORDER_ATTRIBUTE = "Read Order"

# A candidate's priority ranks the override above the base value first, and only
# then by Read Order, so an active Scenario carrying no Read Order still wins.
_BASE_RANK = 0
_OVERRIDE_RANK = 1
_UNRANKED_READ_ORDER = 0.0
_Priority = tuple[int, float]
_BASE_PRIORITY: _Priority = (_BASE_RANK, _UNRANKED_READ_ORDER)

# Data File references: a property value tagged to a Data File object reads from
# an external CSV, whose path is that object's Filename (a t_text value).
_TEXT_TABLE = "t_text"
_FILENAME_PROPERTY = "Filename"
# A property value can read a CSV indirectly: tagged to a Variable whose Profile names it,
# either as its own text or through a Data File object the Profile is tagged to. Such a value
# is the object's share of that shared profile, so the staged series is scaled by it.
_VARIABLE_CLASS = "Variable"
_PROFILE_PROPERTY = "Profile"
_NO_SCALING = 1.0
_PERCENT = 100.0
_TIME_SERIES_SUBDIR = "time_series"
_CSV_SUBDIR = "csv"


_Rows = list[dict[str, Any]]
_RowsByTable = dict[str, _Rows]
_RowsByClass = dict[str, _Rows]


class _WinnerKey(NamedTuple):
    """What a t_data row competes for: one value per property per band of a membership.

    Dated rows do not compete with each other, so the date they apply from is part of the
    key; a Scenario override still displaces the base value it shares a date with.
    """

    membership_id: Any
    property_id: Any
    band: Any
    date_from: datetime | None


class _Candidate(NamedTuple):
    """One t_data row in the running, with what it competes for and how strongly."""

    key: _WinnerKey
    priority: _Priority
    data: dict[str, Any]


class _WinningRow(NamedTuple):
    """The t_data row that won a band, carried with the band and dates so the row can name them."""

    band: Any
    dates: DateBand
    data: dict[str, Any]


class StagePlexosXmlParams(BaseModel):
    path: Location = Field(description="the PLEXOS <MasterDataSet> input XML")
    model: str | None = Field(
        default=None,
        description="which PLEXOS Model to translate; its Horizon sets the snapshots and its "
        "Scenario overlays are applied. Blank applies no overlays",
    )
    horizon_year: int | None = Field(
        default=None,
        description="a four-digit year such as 2026: the calendar year to translate. Its "
        "snapshots are the model's Horizon narrowed to that year, every dated value is the "
        "one in force during it, and profile rows carrying only Month/Day/Period are dated "
        "into it. Blank keeps the whole Horizon and takes each dated value as it stood when "
        "the Horizon opened",
    )


class StagePlexosXml(StagedSource):
    name: ClassVar[str] = "stage_plexos_xml"
    params_schema: ClassVar[type[BaseModel] | None] = StagePlexosXmlParams
    prefix: ClassVar[str] = "plexos"
    sample_scope: ClassVar[SampleScope] = SampleScope.FIRST

    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def load_into_state(self, params: BaseModel | None, staging_dir: Path) -> State:
        plexos_params = self._require_params(params)
        dropped = _DroppedRecords()
        tables = self._parse_tables(plexos_params.path)
        chronology = Chronology.of(tables, plexos_params.model, plexos_params.horizon_year)
        resolved = _resolve_dataset(tables, plexos_params.model, chronology.window, dropped)
        return State(
            staging_dir=staging_dir,
            source_topology=self._stage_topology(resolved, staging_dir),
            source_time_series=self._stage_all_series(
                resolved, plexos_params.path, staging_dir, chronology
            ),
            validation_errors=dropped.errors,
        )

    def _stage_all_series(
        self,
        resolved: _ResolvedDataset,
        xml_path: Location,
        staging_dir: Path,
        chronology: Chronology,
    ) -> dict[tuple[str, str], pl.LazyFrame]:
        """Both kinds of series a model states: read from a Data File, and dated in the XML."""
        series = self._stage_time_series(
            resolved.properties, xml_path, staging_dir, chronology.profile_year, chronology.index
        )
        for key, frames in stepped_series_parts(resolved.stepped_properties, series).items():
            series[key] = self._sink_series(key, frames, staging_dir, chronology.index)
        return series

    def _require_params(self, params: BaseModel | None) -> StagePlexosXmlParams:
        if not isinstance(params, StagePlexosXmlParams):
            raise TypeError(
                f"{type(self).__name__} requires {StagePlexosXmlParams.__name__}, "
                f"got {type(params).__name__}"
            )
        return params

    def _parse_tables(self, path: Location) -> _RowsByTable:
        with self._fs.open_read(path) as xml_file:
            root = ET.parse(xml_file).getroot()
        tables: _RowsByTable = {}
        for element in root:
            tables.setdefault(_local_name(element.tag), []).append(_element_record(element))
        return tables

    def _stage_topology(
        self, resolved: _ResolvedDataset, staging_dir: Path
    ) -> dict[str, pl.LazyFrame]:
        topology = self._stage(resolved.objects_by_class, staging_dir)
        memberships = PlexosResolvedTable.MEMBERSHIPS
        properties = PlexosResolvedTable.PROPERTIES
        topology[memberships] = self._stage_table(memberships, resolved.memberships, staging_dir)
        topology[properties] = self._stage_table(properties, resolved.properties, staging_dir)
        return topology

    def _stage(self, objects_by_class: _RowsByClass, staging_dir: Path) -> dict[str, pl.LazyFrame]:
        return {
            class_name: self._stage_table(class_name, rows, staging_dir)
            for class_name, rows in objects_by_class.items()
        }

    def _stage_table(self, name: str, rows: _Rows, staging_dir: Path) -> pl.LazyFrame:
        out = staging_dir / _TOPOLOGY_SUBDIR / f"{name}.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        # PLEXOS exports omit optional elements; without scanning every row, a
        # key first appearing after the inference window is silently dropped.
        pl.DataFrame(rows, infer_schema_length=None).write_parquet(out)
        return pl.scan_parquet(out)

    def _stage_time_series(
        self,
        properties: _Rows,
        xml_path: Location,
        staging_dir: Path,
        horizon_year: int | None,
        index: pl.DataFrame | None,
    ) -> dict[tuple[str, str], pl.LazyFrame]:
        """Read the CSV behind each file-backed property once, reshaping it for every object.

        Property rows are grouped by the Data File they read, so each CSV is spooled,
        layout-checked, and reshaped exactly once no matter how many objects read it: a
        layout that names its own objects (a Name column, or one column per object)
        reshapes straight into every object's rows; a layout with one shared value column,
        or one column per replication, carries no object identity, so its rows are joined
        against the objects that reference it and each gets its own share. A layout the
        reshaper does not handle (a timeslice Pattern or a scalar by-name file) is deferred
        once with a warning. Each series is reconciled onto the Horizon ``index`` when one
        is known, so mixed-resolution files share one snapshot window. One frame per
        (owner class, property); each row is (snapshot, component, sample, value).
        """
        rows_by_file: dict[str, _Rows] = {}
        for row in properties:
            relative = row[PlexosPropertyCol.DATA_FILE]
            if relative is not None:
                rows_by_file.setdefault(relative, []).append(row)

        parts: dict[tuple[str, str], list[pl.LazyFrame]] = {}
        missing: list[str] = []
        for file_index, (relative, rows) in enumerate(rows_by_file.items()):
            spooled = self._spool_csv_if_present(xml_path, relative, file_index, staging_dir)
            if spooled is None:
                missing.append(relative)
                continue
            scan = strip_bom(spooled)
            if not is_supported_layout(scan, horizon_year):
                warn_unstageable_layout(scan, relative, horizon_year)
                continue
            for key, owners in _group_by_series_key(rows).items():
                frame = reshape_for_file(scan, owners, horizon_year, self.sample_scope)
                if frame is None:
                    warn_no_series(relative, owners)
                    continue
                parts.setdefault(key, []).append(frame)
        _warn_missing_data_files(missing)
        return {
            key: self._sink_series(key, frames, staging_dir, index) for key, frames in parts.items()
        }

    def _spool_csv_if_present(
        self, xml_path: Location, relative: str, index: int, staging_dir: Path
    ) -> pl.LazyFrame | None:
        """Copy the CSV to local scratch in blocks and scan it, or None if it is not there.

        A published model routinely ships its traces as separate downloads, so a Data
        File the export names but the package omits leaves out that one profile rather
        than stopping the translation.
        """
        temp = staging_dir / _CSV_SUBDIR / f"{index}.csv"
        temp.parent.mkdir(parents=True, exist_ok=True)
        try:
            with (
                self._fs.open_read(self._fs.resolve(xml_path, relative)) as source,
                open(temp, "wb") as scratch,
            ):
                shutil.copyfileobj(source, scratch)
        except OSError:
            return None
        # Infer from the whole file: a profile column often looks integer for its first
        # rows and turns fractional later, which a bounded inference window mistypes.
        return pl.scan_csv(temp, infer_schema_length=None)

    def _sink_series(
        self,
        key: tuple[str, str],
        frames: list[pl.LazyFrame],
        staging_dir: Path,
        index: pl.DataFrame | None,
    ) -> pl.LazyFrame:
        out = staging_dir / _TIME_SERIES_SUBDIR / key[0]
        out.mkdir(parents=True, exist_ok=True)
        combined = pl.concat(frames)
        if index is None:
            path = out / f"{key[1]}.parquet"
            combined.sink_parquet(path)
            return pl.scan_parquet(path)
        return reindex_onto(combined, out, key[1], index)


class StagePlexosXmlEnsemble(StagePlexosXml):
    """Stages every replication of a sampled profile, for the ensemble pipeline.

    Identical to ``StagePlexosXml`` in every other respect; only ``sample_scope`` differs,
    so a later step or sink can fan out one network per replication.
    """

    name: ClassVar[str] = "stage_plexos_xml_ensemble"
    prefix: ClassVar[str] = "plexos-ensemble"
    sample_scope: ClassVar[SampleScope] = SampleScope.ALL


@dataclass(frozen=True)
class _ResolvedDataset:
    """The three staged topology tables, resolved from the raw ``t_*`` tables.

    ``properties`` holds one row per property, the value in force when the window opens.
    ``stepped_properties`` holds every value a property takes within the window, and only
    for the properties that take more than one, so a consumer can read the shape.
    """

    objects_by_class: _RowsByClass
    memberships: _Rows
    properties: _Rows
    stepped_properties: _Rows


def _resolve_dataset(
    tables: _RowsByTable, model: str | None, window: Window, dropped: _DroppedRecords
) -> _ResolvedDataset:
    memberships = _resolve_memberships(tables, dropped)
    resolved = _resolve_properties(tables, memberships, model, dropped)
    in_force, stepped = apply_window(resolved, window)
    return _ResolvedDataset(
        objects_by_class=_resolve_object_classes(tables, dropped),
        memberships=memberships,
        properties=in_force,
        stepped_properties=stepped,
    )


@dataclass(frozen=True)
class _Lookup:
    """One table's values by id, and the table's name for reporting."""

    table: str
    by_id: dict[Any, Any]


@dataclass(frozen=True)
class _Reference:
    """One row's pointer at another table: where it came from and the id it points at."""

    table: str
    row_id: Any
    column: str
    value: Any


class _DroppedRecords:
    """Records the rows dropped for pointing at an id nothing defines.

    A PLEXOS export can be filtered or hand-edited into referring to rows it no longer
    carries. Such a row cannot be resolved, so it is left out of the staged tables and
    recorded as a validation error rather than raised: the rest of the model still stages.
    """

    def __init__(self) -> None:
        self._errors: list[EnergyModelValidationError] = []

    @property
    def errors(self) -> list[EnergyModelValidationError]:
        return list(self._errors)

    def resolve(self, lookup: _Lookup, reference: _Reference) -> Any | None:
        """The value the reference points at, or None once the dangling id is recorded."""
        if reference.value in lookup.by_id:
            return lookup.by_id[reference.value]
        self._record(lookup, reference)
        return None

    def _record(self, lookup: _Lookup, reference: _Reference) -> None:
        self._errors.append(
            EnergyModelValidationError(
                validator=StagePlexosXml.name,
                severity=ValidationSeverity.WARNING,
                component=reference.table,
                name=str(reference.row_id),
                message=(
                    f"{reference.column} {reference.value!r} is not defined "
                    f"in {lookup.table}; the row is dropped"
                ),
                attribute=reference.column,
                value=reference.value,
            )
        )


@dataclass(frozen=True)
class _ResolvedColumn:
    """An id column, the table its ids resolve in, and the column the name is written to."""

    id_column: str
    lookup: _Lookup
    name_column: str


def _resolve_memberships(tables: _RowsByTable, dropped: _DroppedRecords) -> _Rows:
    """Resolve each ``t_membership`` row's class, object, and collection ids to names."""
    columns = _membership_id_columns(tables)
    rows = (_membership_row(row, columns, dropped) for row in tables.get(_MEMBERSHIP_TABLE, []))
    return [row for row in rows if row is not None]


def _membership_id_columns(tables: _RowsByTable) -> tuple[_ResolvedColumn, ...]:
    classes = _name_lookup(tables, _CLASS_TABLE, _CLASS_ID)
    objects = _name_lookup(tables, _OBJECT_TABLE, _OBJECT_ID)
    collections = _name_lookup(tables, _COLLECTION_TABLE, _COLLECTION_ID)
    return (
        _ResolvedColumn(_PARENT_CLASS_ID, classes, PlexosMembershipCol.PARENT_CLASS),
        _ResolvedColumn(_PARENT_OBJECT_ID, objects, PlexosMembershipCol.PARENT_OBJECT),
        _ResolvedColumn(_COLLECTION_ID, collections, PlexosMembershipCol.COLLECTION),
        _ResolvedColumn(_CHILD_CLASS_ID, classes, PlexosMembershipCol.CHILD_CLASS),
        _ResolvedColumn(_CHILD_OBJECT_ID, objects, PlexosMembershipCol.CHILD_OBJECT),
    )


def _membership_row(
    row: dict[str, Any], columns: tuple[_ResolvedColumn, ...], dropped: _DroppedRecords
) -> dict[str, Any] | None:
    """One membership with its ids resolved, or None if any of them dangles."""
    membership_id = row[_MEMBERSHIP_ID]
    resolved: dict[str, Any] = {PlexosMembershipCol.MEMBERSHIP_ID: membership_id}
    for column in columns:
        reference = _Reference(
            _MEMBERSHIP_TABLE, membership_id, column.id_column, row[column.id_column]
        )
        name = dropped.resolve(column.lookup, reference)
        if name is None:
            return None
        resolved[column.name_column] = name
    return resolved


@dataclass(frozen=True)
class _PropertyLookups:
    """The three tables a ``t_data`` row is resolved against."""

    memberships: _Lookup
    property_names: _Lookup
    profiles: dict[str, _ProfileRef]


def _resolve_properties(
    tables: _RowsByTable, memberships: _Rows, model: str | None, dropped: _DroppedRecords
) -> list[DatedRow]:
    """Resolve each property to its winning ``t_data`` value under the model's Scenario overlays.

    Among the rows for one (membership, property, band, date) the winner is the highest
    Read Order override active for the selected model, or the base value if none. A dated
    property keeps one row per date here; narrowing those to a window is ``apply_window``.
    """
    overlay = _read_scenario_overlay(tables, model)
    property_names = _name_lookup(tables, _PROPERTY_TABLE, _PROPERTY_ID)
    lookups = _PropertyLookups(
        memberships=_Lookup(
            _MEMBERSHIP_TABLE,
            {row[PlexosMembershipCol.MEMBERSHIP_ID]: row for row in memberships},
        ),
        property_names=property_names,
        profiles=_profile_ref_by_data(tables, property_names, overlay, dropped),
    )
    units = UnitConversions(stated_units(tables))
    rows = (
        _property_row(winner, lookups, dropped, units)
        for winner in _winning_data_rows(tables, model)
    )
    resolved = [row for row in rows if row is not None]
    units.warn()
    return resolved


def _winning_data_rows(tables: _RowsByTable, model: str | None) -> list[_WinningRow]:
    """The ``t_data`` row that wins each (membership, property, band, date) for the model."""
    dates = date_bands(tables)
    winners: dict[_WinnerKey, tuple[_Priority, dict[str, Any]]] = {}
    for key, priority, data in _property_candidates(tables, model, dates):
        if key not in winners or priority >= winners[key][0]:
            winners[key] = (priority, data)
    return [
        _WinningRow(key.band, dates.get(data[_DATA_ID], UNDATED), data)
        for key, (_, data) in winners.items()
    ]


def _property_candidates(
    tables: _RowsByTable, model: str | None, dates: dict[str, DateBand]
) -> Iterator[_Candidate]:
    """Every ``t_data`` row the model reads, with its (membership, property, band, date) key."""
    overlay = _read_scenario_overlay(tables, model)
    band_by_data = {row[_DATA_ID]: row[_BAND_ID] for row in tables.get(_BAND_TABLE, [])}
    for data in tables.get(_DATA_TABLE, []):
        priority = overlay.priority_of(data[_DATA_ID])
        if priority is not None:
            key = _WinnerKey(
                data[_MEMBERSHIP_ID],
                data[_PROPERTY_ID],
                band_by_data.get(data[_DATA_ID]),
                dates.get(data[_DATA_ID], UNDATED).date_from,
            )
            yield _Candidate(key, priority, data)


def _property_row(
    winner: _WinningRow,
    lookups: _PropertyLookups,
    dropped: _DroppedRecords,
    units: UnitConversions,
) -> DatedRow | None:
    """One resolved property row, or None if the ``t_data`` row's references dangle."""
    data = winner.data
    membership = dropped.resolve(lookups.memberships, _data_reference(data, _MEMBERSHIP_ID))
    property_name = dropped.resolve(lookups.property_names, _data_reference(data, _PROPERTY_ID))
    if membership is None or property_name is None:
        return None
    stated = StatedValue(
        value=_to_float(data[_VALUE]),
        unit=units.unit_of(data[_PROPERTY_ID]),
        collection=membership[PlexosMembershipCol.COLLECTION],
        property_name=property_name,
    )
    return DatedRow(
        winner.dates,
        {
            **{column: membership[column] for column in _MEMBERSHIP_NAME_COLUMNS},
            **_value_columns(stated, lookups.profiles.get(data[_DATA_ID]), units),
            PlexosPropertyCol.PROPERTY: property_name,
            PlexosPropertyCol.BAND: winner.band,
        },
    )


def _value_columns(
    stated: StatedValue, profile: _ProfileRef | None, units: UnitConversions
) -> dict[str, Any]:
    """The value in the unit interop reads it in, the unit the model stated, and the CSV."""
    if profile is not None:
        units.note_profile(stated)
    value = units.convert(stated)
    return {
        PlexosPropertyCol.VALUE: value,
        PlexosPropertyCol.UNIT: stated.unit,
        PlexosPropertyCol.DATA_FILE: profile.path if profile is not None else None,
        PlexosPropertyCol.SCALING: _profile_scaling(profile, value, is_percent(stated.unit)),
    }


def _data_reference(data: dict[str, Any], column: str) -> _Reference:
    return _Reference(_DATA_TABLE, data[_DATA_ID], column, data[column])


class _CsvSource(NamedTuple):
    """The class whose objects name a CSV, and the text property holding that path."""

    class_name: str
    text_property: str


_DATA_FILE_SOURCE = _CsvSource(PlexosClass.DATA_FILE, _FILENAME_PROPERTY)
_VARIABLE_SOURCE = _CsvSource(_VARIABLE_CLASS, _PROFILE_PROPERTY)


class _ProfileRef(NamedTuple):
    """The CSV a value reads from, and whether the value is a share of it rather than all of it."""

    path: str
    is_share: bool


def _profile_scaling(
    profile: _ProfileRef | None, value: float | None, is_share_percent: bool
) -> float:
    """A share written as a percentage is a multiplier of 100, so it divides down to one. A
    zero share is PLEXOS's placeholder for a value the profile supplies outright, not a
    multiplier that would erase it.
    """
    if profile is None or not profile.is_share or not value:
        return _NO_SCALING
    return value / _PERCENT if is_share_percent else value


def _profile_ref_by_data(
    tables: _RowsByTable,
    property_names: _Lookup,
    overlay: _ScenarioOverlay,
    dropped: _DroppedRecords,
) -> dict[str, _ProfileRef]:
    """Map each t_data id to the CSV it reads from, whether tagged directly or via a Variable.

    A value tagged straight to a Data File reads that file's Filename; a value tagged to a
    Variable reads the CSV named by that Variable's Profile, with the value as a scaling
    factor the mapping applies. A direct Data File wins if a value carries both.
    """
    data_files = _object_csv_paths(tables, property_names, overlay, dropped, _DATA_FILE_SOURCE)
    variables = _variable_csv_paths(tables, property_names, overlay, data_files)
    return {
        **_refs_by_data(tables, _VARIABLE_CLASS, variables, is_share=True),
        **_refs_by_data(tables, PlexosClass.DATA_FILE, data_files, is_share=False),
    }


def _refs_by_data(
    tables: _RowsByTable, class_name: str, paths: dict[str, str], *, is_share: bool
) -> dict[str, _ProfileRef]:
    """Map each t_data id tagged to an object of a class to that object's CSV."""
    tags = _tag_by_data(tables, class_name)
    return {
        data_id: _ProfileRef(paths[obj], is_share) for data_id, obj in tags.items() if obj in paths
    }


def _variable_csv_paths(
    tables: _RowsByTable,
    property_names: _Lookup,
    overlay: _ScenarioOverlay,
    data_file_paths: dict[str, str],
) -> dict[str, str]:
    """Each Variable's profile CSV, named by its Profile's own text or by a Data File it tags.

    A Profile carrying a timeslice pattern or a plain number names no file, so that Variable
    contributes no path; it is a value, not a broken reference.
    """
    texts = _data_file_text_lookup(tables)
    tagged_files = _tag_by_data(tables, PlexosClass.DATA_FILE)
    paths: dict[str, str] = {}
    for owner, data in _object_csv_data(tables, property_names, overlay, _VARIABLE_SOURCE).items():
        data_id = data[_DATA_ID]
        path = texts.by_id.get(data_id) or data_file_paths.get(tagged_files.get(data_id, ""))
        if path is not None:
            paths[owner] = path
    return paths


def _object_csv_paths(
    tables: _RowsByTable,
    property_names: _Lookup,
    overlay: _ScenarioOverlay,
    dropped: _DroppedRecords,
    source: _CsvSource,
) -> dict[str, str]:
    """Map each object of a class to the CSV path in its text-valued property."""
    texts = _data_file_text_lookup(tables)
    paths: dict[str, str] = {}
    for owner, data in _object_csv_data(tables, property_names, overlay, source).items():
        path = dropped.resolve(texts, _data_reference(data, _DATA_ID))
        if path is not None:
            paths[owner] = path
    return paths


def _object_csv_data(
    tables: _RowsByTable, property_names: _Lookup, overlay: _ScenarioOverlay, source: _CsvSource
) -> dict[str, dict[str, Any]]:
    """Map each object of a class to the winning ``t_data`` row of its Filename/Profile property.

    A Data File that names one CSV per month carries a row per Scenario, so a row belonging
    to a scenario the selected Model does not activate is skipped rather than overwriting.
    """
    object_ids = objects_of_class(tables, source.class_name)
    children = _child_object_lookup(tables)
    found: dict[str, dict[str, Any]] = {}
    for data in _text_property_rows(tables, property_names, source.text_property):
        owner = children.by_id.get(data[_MEMBERSHIP_ID])
        if owner in object_ids and overlay.priority_of(data[_DATA_ID]) is not None:
            found[owner] = data
    return found


def _data_file_text_lookup(tables: _RowsByTable) -> _Lookup:
    """The t_text values that name a file.

    t_text holds every text value in the export and tells them apart only by class_id:
    a Data File name is a path, a Timeslice is a banding pattern that names no file.
    """
    data_file_class = class_id_of(tables, PlexosClass.DATA_FILE)
    if data_file_class is None:
        return _Lookup(_TEXT_TABLE, {})
    return _Lookup(
        _TEXT_TABLE,
        {
            row[_DATA_ID]: row[_VALUE]
            for row in tables.get(_TEXT_TABLE, [])
            if row.get(_CLASS_ID) == data_file_class
        },
    )


def _child_object_lookup(tables: _RowsByTable) -> _Lookup:
    return _Lookup(
        _MEMBERSHIP_TABLE,
        {row[_MEMBERSHIP_ID]: row[_CHILD_OBJECT_ID] for row in tables.get(_MEMBERSHIP_TABLE, [])},
    )


def _text_property_rows(
    tables: _RowsByTable, property_names: _Lookup, text_property: str
) -> Iterator[dict[str, Any]]:
    """The ``t_data`` rows holding an object's text-valued property (a Filename or Profile)."""
    for data in tables.get(_DATA_TABLE, []):
        if property_names.by_id.get(data[_PROPERTY_ID]) == text_property:
            yield data


def _tag_by_data(tables: _RowsByTable, class_name: str) -> dict[str, str]:
    """Map each tagged t_data id to the object of the given class it reads from."""
    object_ids = objects_of_class(tables, class_name)
    return {
        row[_DATA_ID]: row[_OBJECT_ID]
        for row in tables.get(_TAG_TABLE, [])
        if row[_OBJECT_ID] in object_ids
    }


def _group_by_series_key(rows: _Rows) -> dict[tuple[str, str], _Rows]:
    """Group one Data File's owning property rows by the (owner class, property) series they
    feed.
    """
    grouped: dict[tuple[str, str], _Rows] = {}
    for row in rows:
        key = (row[PlexosPropertyCol.CHILD_CLASS], row[PlexosPropertyCol.PROPERTY])
        grouped.setdefault(key, []).append(row)
    return grouped


def _warn_missing_data_files(missing: list[str]) -> None:
    if not missing:
        return
    log.warning(
        "plexos: %d Data File(s) named by the model are not in the package, "
        "so their profiles are left out: %s",
        len(missing),
        name_a_few(sorted(missing)),
    )


@dataclass(frozen=True)
class _ScenarioOverlay:
    """The Scenario overrides one Model reads, and how they rank against each other."""

    scenario_tags: dict[str, list[str]]
    active: set[str]
    read_orders: dict[str, float]

    def priority_of(self, data_id: str) -> _Priority | None:
        """A t_data row's priority: base if untagged, else its highest active Read Order.

        A row tagged only to Scenarios the model does not read is no candidate at all
        (None). A row carrying several tags counts as active when any one of them is.
        """
        tags = self.scenario_tags.get(data_id)
        if tags is None:
            return _BASE_PRIORITY
        active_tags = [tag for tag in tags if tag in self.active]
        if not active_tags:
            return None
        return (_OVERRIDE_RANK, max(self._read_order_of(tag) for tag in active_tags))

    def _read_order_of(self, scenario: str) -> float:
        return self.read_orders.get(scenario, _UNRANKED_READ_ORDER)


def _read_scenario_overlay(tables: _RowsByTable, model: str | None) -> _ScenarioOverlay:
    return _ScenarioOverlay(
        scenario_tags=_scenario_tags_by_data(tables),
        active=_active_scenarios(tables, model),
        read_orders=_read_orders(tables),
    )


def _active_scenarios(tables: _RowsByTable, model: str | None) -> set[str]:
    """Scenario object ids that the selected model reads, via its Model->Scenario memberships."""
    if model is None:
        return set()
    model_class = class_id_of(tables, PlexosClass.MODEL)
    scenario_class = class_id_of(tables, PlexosClass.SCENARIO)
    model_ids = {
        row[_OBJECT_ID]
        for row in tables.get(_OBJECT_TABLE, [])
        if row[_CLASS_ID] == model_class and row[_NAME] == model
    }
    return {
        row[_CHILD_OBJECT_ID]
        for row in tables.get(_MEMBERSHIP_TABLE, [])
        if row[_PARENT_OBJECT_ID] in model_ids and row[_CHILD_CLASS_ID] == scenario_class
    }


def _read_orders(tables: _RowsByTable) -> dict[str, float]:
    """Map each Scenario object id to its Read Order attribute value (higher reads later)."""
    attribute_ids = {
        row[_ATTRIBUTE_ID]
        for row in tables.get(_ATTRIBUTE_TABLE, [])
        if row[_NAME] == _READ_ORDER_ATTRIBUTE
    }
    return {
        row[_OBJECT_ID]: float(row[_VALUE])
        for row in tables.get(_ATTRIBUTE_DATA_TABLE, [])
        if row[_ATTRIBUTE_ID] in attribute_ids
    }


def _scenario_tags_by_data(tables: _RowsByTable) -> dict[str, list[str]]:
    """Map each tagged t_data id to the Scenarios it overrides, ignoring non-scenario tags."""
    scenario_ids = objects_of_class(tables, PlexosClass.SCENARIO)
    tags: dict[str, list[str]] = {}
    for row in tables.get(_TAG_TABLE, []):
        if row[_OBJECT_ID] in scenario_ids:
            tags.setdefault(row[_DATA_ID], []).append(row[_OBJECT_ID])
    return tags


def _to_float(value: str) -> float | None:
    """PLEXOS scalar values are numeric text; file-backed rows carry no scalar."""
    try:
        return float(value)
    except ValueError:
        return None


def _resolve_object_classes(tables: _RowsByTable, dropped: _DroppedRecords) -> _RowsByClass:
    """Group the object rows by their resolved PLEXOS class name.

    Each row gains a ``category`` column, its ``category_id`` resolved to the
    ``t_category`` name, so a mapping reads the free-text grouping (the carrier hint
    and, for demand response, the resource kind) without re-resolving the id itself.
    """
    classes = _name_lookup(tables, _CLASS_TABLE, _CLASS_ID)
    categories = _name_lookup(tables, _CATEGORY_TABLE, _CATEGORY_ID)
    objects_by_class: _RowsByClass = {}
    for row in tables.get(_OBJECT_TABLE, []):
        reference = _Reference(_OBJECT_TABLE, row[_OBJECT_ID], _CLASS_ID, row[_CLASS_ID])
        class_name = dropped.resolve(classes, reference)
        if class_name is not None:
            resolved = {
                **row,
                PlexosObjectCol.CATEGORY: categories.by_id.get(row.get(_CATEGORY_ID)),
            }
            objects_by_class.setdefault(class_name, []).append(resolved)
    return objects_by_class


def _name_lookup(tables: _RowsByTable, table: str, id_column: str) -> _Lookup:
    """One table's ``name`` column by id, for resolving references into it."""
    return _Lookup(table, {row[id_column]: row[_NAME] for row in tables.get(table, [])})


def _element_record(element: ET.Element) -> dict[str, Any]:
    return {_local_name(child.tag): (child.text or "") for child in element}


def _local_name(tag: str) -> str:
    """Strip the ``{namespace}`` prefix ElementTree prepends to namespaced tags."""
    return tag.rsplit("}", 1)[-1]
