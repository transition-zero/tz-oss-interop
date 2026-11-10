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
- ``topology/dated_properties.parquet``, every row of a property the model dates
  before it is narrowed to the window, each beside the dates it applies between;
- one ``source_time_series`` frame per (owner class, property) whose value comes
  from an external CSV, streamed in as ``(snapshot, component, sample, value)`` rows.
  ``sample`` is null except where the CSV carries one column per Monte Carlo
  replication.

A row pointing at an id no other table defines is dropped and recorded as a
validation error, so a partial export stages the records it can resolve.

Each staging concern with a life of its own sits in a sibling module: the chronology in
``plexos_horizon``, the Scenario overlay in ``plexos_scenarios``, the data file a value
reads in ``plexos_profiles``, the dated-property windowing in ``plexos_dated_properties``,
the files of dated values in ``plexos_dated_files``, the CSV layouts in
``plexos_csv_layouts``, and the units a property is stated in with the rest of the unit
vocabulary in ``plexos_units``.
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
    PlexosMembershipCol,
    PlexosObjectCol,
    PlexosPropertyCol,
    PlexosResolvedTable,
)
from interop.plugins.shared.plexos_dates import UNDATED, DateBand
from interop.plugins.shared.plexos_units import (
    StatedValue,
    UnitConversions,
    is_percent,
    stated_units,
)
from interop.plugins.shared.warning_text import name_a_few
from interop.plugins.sources.plexos_csv_layouts import (
    LayoutContext,
    SampleScope,
    drop_undated_rows,
    is_supported_layout,
    normalise_header,
    reshape_for_file,
    warn_no_series,
    warn_undated_rows,
    warn_unstageable_layout,
)
from interop.plugins.sources.plexos_dated_files import DatedFiles, build_rows_from_dated_files
from interop.plugins.sources.plexos_dated_properties import (
    DatedRow,
    apply_window,
    date_bands,
    read_dated_rows,
    stepped_series_parts,
)
from interop.plugins.sources.plexos_escalators import build_escalated_series
from interop.plugins.sources.plexos_horizon import Chronology, Window, reindex_onto
from interop.plugins.sources.plexos_patterns import PatternCalendar, build_calendar
from interop.plugins.sources.plexos_profiles import (
    ProfileRef,
    build_profile_refs,
    build_row_name,
    build_scaling,
)
from interop.plugins.sources.plexos_scenarios import (
    Priority,
    ScenarioOverlay,
    build_scenario_overlay,
)
from interop.plugins.sources.plexos_tables import (
    CLASS_ID,
    CLASS_TABLE,
    DATA_ID,
    DATA_TABLE,
    MEMBERSHIP_ID,
    MEMBERSHIP_TABLE,
    OBJECT_ID,
    OBJECT_TABLE,
    PROPERTY_ID,
    PROPERTY_TABLE,
    VALUE,
    DroppedRecords,
    Lookup,
    Reference,
    RowsByTable,
    build_data_reference,
    build_name_lookup,
)
from interop.plugins.sources.plexos_timeslices import TimesliceSource, is_timeslice_include
from interop.ports.outbound.filesystem import FilesystemPort, Location

log = logging.getLogger(__name__)

_TOPOLOGY_SUBDIR = "topology"
_CATEGORY_TABLE = "t_category"
_COLLECTION_TABLE = "t_collection"
_CATEGORY_ID = "category_id"
_COLLECTION_ID = "collection_id"

_MEMBERSHIP_NAME_COLUMNS = (
    PlexosMembershipCol.PARENT_CLASS,
    PlexosMembershipCol.PARENT_OBJECT,
    PlexosMembershipCol.COLLECTION,
    PlexosMembershipCol.CHILD_CLASS,
    PlexosMembershipCol.CHILD_OBJECT,
)
# The foreign-key columns of t_membership.
_PARENT_CLASS_ID = "parent_class_id"
_PARENT_OBJECT_ID = "parent_object_id"
_CHILD_CLASS_ID = "child_class_id"
_CHILD_OBJECT_ID = "child_object_id"

_BAND_TABLE = "t_band"
_BAND_ID = "band_id"

_TIME_SERIES_SUBDIR = "time_series"
_CSV_SUBDIR = "csv"
_ESCALATED_SUBDIR = "escalated"


_Rows = list[dict[str, Any]]
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
    priority: Priority
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
        dropped = DroppedRecords(StagePlexosXml.name)
        tables = self._parse_tables(plexos_params.path)
        chronology = Chronology.of(tables, plexos_params.model, plexos_params.horizon_year)
        overlay = build_scenario_overlay(tables, plexos_params.model)
        spool = _Spool(self._fs, plexos_params.path, staging_dir / _CSV_SUBDIR)
        selection = _Selection(overlay, chronology.window)
        resolved = _resolve_dataset(tables, selection, dropped, DatedFiles(spool.find_scan))
        package = _Package(tables, overlay, spool)
        return State(
            staging_dir=staging_dir,
            source_topology=self._stage_topology(resolved, staging_dir),
            source_time_series=self._stage_all_series(resolved, package, staging_dir, chronology),
            validation_errors=dropped.errors,
        )

    def _stage_all_series(
        self,
        resolved: _ResolvedDataset,
        package: _Package,
        staging_dir: Path,
        chronology: Chronology,
    ) -> dict[tuple[str, str], pl.LazyFrame]:
        """Both kinds of series a model states: read from a Data File, and dated in the XML."""
        context = LayoutContext(
            chronology.profile_year,
            self.sample_scope,
            _build_pattern_calendar(resolved.properties, package, chronology),
        )
        series = self._stage_time_series(resolved, package.spool, staging_dir, context, chronology)
        for key, frames in stepped_series_parts(resolved.stepped_properties, series).items():
            series[key] = self._sink_series(key, frames, staging_dir, chronology.index)
        return build_escalated_series(
            series, resolved.properties, staging_dir / _ESCALATED_SUBDIR, chronology.index
        )

    def _require_params(self, params: BaseModel | None) -> StagePlexosXmlParams:
        if not isinstance(params, StagePlexosXmlParams):
            raise TypeError(
                f"{type(self).__name__} requires {StagePlexosXmlParams.__name__}, "
                f"got {type(params).__name__}"
            )
        return params

    def _parse_tables(self, path: Location) -> RowsByTable:
        with self._fs.open_read(path) as xml_file:
            root = ET.parse(xml_file).getroot()
        tables: RowsByTable = {}
        for element in root:
            tables.setdefault(_local_name(element.tag), []).append(_element_record(element))
        return tables

    def _stage_topology(
        self, resolved: _ResolvedDataset, staging_dir: Path
    ) -> dict[str, pl.LazyFrame]:
        topology = self._stage(resolved.objects_by_class, staging_dir)
        memberships = PlexosResolvedTable.MEMBERSHIPS
        properties = PlexosResolvedTable.PROPERTIES
        dated = PlexosResolvedTable.DATED_PROPERTIES
        topology[memberships] = self._stage_table(memberships, resolved.memberships, staging_dir)
        topology[properties] = self._stage_table(properties, resolved.properties, staging_dir)
        topology[dated] = self._stage_table(dated, resolved.dated_properties, staging_dir)
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
        resolved: _ResolvedDataset,
        spool: _Spool,
        staging_dir: Path,
        context: LayoutContext,
        chronology: Chronology,
    ) -> dict[tuple[str, str], pl.LazyFrame]:
        """Read the CSV behind each file-backed property once, reshaping it for every object.

        Property rows are grouped by the Data File they read, so each CSV is spooled,
        layout-checked, and reshaped exactly once no matter how many objects read it: a
        layout that names its own objects (a Name column, or one column per object)
        reshapes straight into every object's rows; a layout with one shared value column,
        or one column per replication, carries no object identity, so its rows are joined
        against the objects that reference it and each gets its own share. A layout the
        reshaper does not handle (a timeslice Pattern or a scalar by-name file) is deferred
        once with a warning. A file the source read as dated values by object stages no
        series. Each series is reconciled onto the Horizon ``index`` when one is known, so
        mixed-resolution files share one snapshot window. One frame per (owner class,
        property); each row is (snapshot, component, sample, value).
        """
        rows_by_file = _group_by_data_file(resolved.properties)
        parts: dict[tuple[str, str], list[pl.LazyFrame]] = {}
        missing: list[str] = []
        for relative, rows in rows_by_file.items():
            if relative in resolved.dated_file_paths:
                _warn_objects_without_a_row(relative, rows)
                continue
            scan = spool.find_scan(relative)
            if scan is None:
                missing.append(relative)
                continue
            if not is_supported_layout(scan, context):
                warn_unstageable_layout(scan, relative, context)
                continue
            for key, owners in _group_by_series_key(rows).items():
                frame = reshape_for_file(scan, relative, owners, context)
                if frame is None:
                    warn_no_series(relative, owners)
                    continue
                warn_undated_rows(frame, relative)
                parts.setdefault(key, []).append(drop_undated_rows(frame))
        _warn_missing_data_files(missing)
        staged = {
            key: self._sink_series(key, frames, staging_dir, chronology.index)
            for key, frames in parts.items()
        }
        return _drop_empty_series(staged, rows_by_file)

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


class _Spool:
    """Each data file beside the XML, copied to local scratch once and scanned from there.

    A published model routinely ships its traces as separate downloads, so a Data File the
    export names but the package omits leaves out that one profile rather than stopping the
    translation.
    """

    def __init__(self, fs: FilesystemPort, xml_path: Location, scratch_dir: Path) -> None:
        self._fs = fs
        self._xml_path = xml_path
        self._scratch_dir = scratch_dir
        self._scans: dict[str, pl.LazyFrame | None] = {}

    def find_scan(self, relative: str) -> pl.LazyFrame | None:
        """The scanned data file, or None where the package omits it. The first call copies it."""
        if relative not in self._scans:
            target = self._scratch_dir / f"{len(self._scans)}.csv"
            try:
                self._copy_csv(relative, target)
            except OSError:
                self._scans[relative] = None
            else:
                self._scans[relative] = _scan_csv(target)
        return self._scans[relative]

    def _copy_csv(self, relative: str, target: Path) -> None:
        """Copy the data file to scratch in blocks. Raises ``OSError`` where it is absent."""
        target.parent.mkdir(parents=True, exist_ok=True)
        with (
            self._fs.open_read(self._fs.resolve(self._xml_path, relative)) as source,
            open(target, "wb") as scratch,
        ):
            shutil.copyfileobj(source, scratch)


def _scan_csv(path: Path) -> pl.LazyFrame:
    # Infer from the whole file: a profile column often looks integer for its first
    # rows and turns fractional later, which a bounded inference window mistypes.
    return normalise_header(pl.scan_csv(path, infer_schema_length=None))


def _build_pattern_calendar(
    properties: _Rows, package: _Package, chronology: Chronology
) -> PatternCalendar | None:
    """What a value by pattern expands onto, or None where the Horizon sets no snapshots."""
    if chronology.index is None:
        return None
    source = TimesliceSource(package.tables, package.overlay, properties)
    return build_calendar(chronology.index, source, package.spool.find_scan)


@dataclass(frozen=True)
class _ResolvedDataset:
    """The staged topology tables, resolved from the raw ``t_*`` tables.

    ``properties`` holds one row per property, the value in force when the window opens.
    ``stepped_properties`` holds every value a property takes within the window, and only
    for the properties that take more than one, so a consumer can read the shape.
    ``dated_properties`` holds every row of a property the model dates, with the dates it
    applies between, narrowed to no window at all. ``dated_file_paths`` names each data
    file that the source read as dated values by object, which stages no series.
    """

    objects_by_class: _RowsByClass
    memberships: _Rows
    properties: _Rows
    stepped_properties: _Rows
    dated_properties: _Rows
    dated_file_paths: set[str]


class _Package(NamedTuple):
    """The parsed tables of a model, the Scenario overlay it reads, and its data files."""

    tables: RowsByTable
    overlay: ScenarioOverlay
    spool: _Spool


class _Selection(NamedTuple):
    """What the user asked to translate: the overlay of one Model, over one window of time."""

    overlay: ScenarioOverlay
    window: Window


def _resolve_dataset(
    tables: RowsByTable, selection: _Selection, dropped: DroppedRecords, dated_files: DatedFiles
) -> _ResolvedDataset:
    memberships = _resolve_memberships(tables, dropped)
    units = UnitConversions(stated_units(tables))
    resolved = _resolve_properties(tables, memberships, selection.overlay, dropped, units)
    from_files = build_rows_from_dated_files(resolved, dated_files, units)
    units.warn()
    in_force, stepped = apply_window(from_files.rows, selection.window)
    return _ResolvedDataset(
        objects_by_class=_resolve_object_classes(tables, dropped),
        memberships=memberships,
        properties=in_force,
        stepped_properties=stepped,
        dated_properties=read_dated_rows(from_files.rows),
        dated_file_paths=from_files.dated_file_paths,
    )


@dataclass(frozen=True)
class _ResolvedColumn:
    """An id column, the table its ids resolve in, and the column the name is written to."""

    id_column: str
    lookup: Lookup
    name_column: str


def _resolve_memberships(tables: RowsByTable, dropped: DroppedRecords) -> _Rows:
    """Resolve each ``t_membership`` row's class, object, and collection ids to names."""
    columns = _membership_id_columns(tables)
    rows = (_membership_row(row, columns, dropped) for row in tables.get(MEMBERSHIP_TABLE, []))
    return [row for row in rows if row is not None]


def _membership_id_columns(tables: RowsByTable) -> tuple[_ResolvedColumn, ...]:
    classes = build_name_lookup(tables, CLASS_TABLE, CLASS_ID)
    objects = build_name_lookup(tables, OBJECT_TABLE, OBJECT_ID)
    collections = build_name_lookup(tables, _COLLECTION_TABLE, _COLLECTION_ID)
    return (
        _ResolvedColumn(_PARENT_CLASS_ID, classes, PlexosMembershipCol.PARENT_CLASS),
        _ResolvedColumn(_PARENT_OBJECT_ID, objects, PlexosMembershipCol.PARENT_OBJECT),
        _ResolvedColumn(_COLLECTION_ID, collections, PlexosMembershipCol.COLLECTION),
        _ResolvedColumn(_CHILD_CLASS_ID, classes, PlexosMembershipCol.CHILD_CLASS),
        _ResolvedColumn(_CHILD_OBJECT_ID, objects, PlexosMembershipCol.CHILD_OBJECT),
    )


def _membership_row(
    row: dict[str, Any], columns: tuple[_ResolvedColumn, ...], dropped: DroppedRecords
) -> dict[str, Any] | None:
    """One membership with its ids resolved, or None if any of them dangles."""
    membership_id = row[MEMBERSHIP_ID]
    resolved: dict[str, Any] = {PlexosMembershipCol.MEMBERSHIP_ID: membership_id}
    for column in columns:
        reference = Reference(
            MEMBERSHIP_TABLE, membership_id, column.id_column, row[column.id_column]
        )
        name = dropped.resolve(column.lookup, reference)
        if name is None:
            return None
        resolved[column.name_column] = name
    return resolved


@dataclass(frozen=True)
class _PropertyLookups:
    """The three tables a ``t_data`` row is resolved against."""

    memberships: Lookup
    property_names: Lookup
    profiles: dict[str, ProfileRef]


def _resolve_properties(
    tables: RowsByTable,
    memberships: _Rows,
    overlay: ScenarioOverlay,
    dropped: DroppedRecords,
    units: UnitConversions,
) -> list[DatedRow]:
    """Resolve each property to its winning ``t_data`` value under the model's Scenario overlays.

    Among the rows for one (membership, property, band, date) the winner is the highest
    Read Order override active for the selected model, or the base value if none. A dated
    property keeps one row per date here; narrowing those to a window is ``apply_window``.
    The function reads only the tables, and no data file.
    """
    property_names = build_name_lookup(tables, PROPERTY_TABLE, PROPERTY_ID)
    lookups = _PropertyLookups(
        memberships=Lookup(
            MEMBERSHIP_TABLE,
            {row[PlexosMembershipCol.MEMBERSHIP_ID]: row for row in memberships},
        ),
        property_names=property_names,
        profiles=build_profile_refs(tables, property_names, overlay, dropped),
    )
    return [
        row
        for winner in _winning_data_rows(tables, overlay)
        for row in _build_property_rows(winner, lookups, dropped, units)
    ]


def _winning_data_rows(tables: RowsByTable, overlay: ScenarioOverlay) -> list[_WinningRow]:
    """The ``t_data`` row that wins each (membership, property, band, date) for the model."""
    dates = date_bands(tables)
    winners: dict[_WinnerKey, tuple[Priority, dict[str, Any]]] = {}
    for key, priority, data in _property_candidates(tables, overlay, dates):
        if key not in winners or priority >= winners[key][0]:
            winners[key] = (priority, data)
    return [
        _WinningRow(key.band, dates.get(data[DATA_ID], UNDATED), data)
        for key, (_, data) in winners.items()
    ]


def _property_candidates(
    tables: RowsByTable, overlay: ScenarioOverlay, dates: dict[str, DateBand]
) -> Iterator[_Candidate]:
    """Every ``t_data`` row the model reads, with its (membership, property, band, date) key."""
    band_by_data = {row[DATA_ID]: row[_BAND_ID] for row in tables.get(_BAND_TABLE, [])}
    for data in tables.get(DATA_TABLE, []):
        priority = overlay.find_priority(data[DATA_ID])
        if priority is not None:
            key = _WinnerKey(
                data[MEMBERSHIP_ID],
                data[PROPERTY_ID],
                band_by_data.get(data[DATA_ID]),
                dates.get(data[DATA_ID], UNDATED).date_from,
            )
            yield _Candidate(key, priority, data)


def _build_property_rows(
    winner: _WinningRow,
    lookups: _PropertyLookups,
    dropped: DroppedRecords,
    units: UnitConversions,
) -> list[DatedRow]:
    """The resolved row of one ``t_data`` row, and none where its references dangle."""
    data = winner.data
    membership = dropped.resolve(lookups.memberships, build_data_reference(data, MEMBERSHIP_ID))
    property_name = dropped.resolve(lookups.property_names, build_data_reference(data, PROPERTY_ID))
    if membership is None or property_name is None:
        return []
    stated = StatedValue(
        value=_to_float(data[VALUE]),
        unit=units.unit_of(data[PROPERTY_ID]),
        collection=membership[PlexosMembershipCol.COLLECTION],
        property_name=property_name,
    )
    profile = lookups.profiles.get(data[DATA_ID])
    naming = {
        **{column: membership[column] for column in _MEMBERSHIP_NAME_COLUMNS},
        PlexosPropertyCol.PROPERTY: property_name,
        PlexosPropertyCol.BAND: winner.band,
        PlexosPropertyCol.ROW_NAME: build_row_name(profile, membership),
    }
    return [DatedRow(winner.dates, {**naming, **_build_value_columns(stated, profile, units)})]


def _build_value_columns(
    stated: StatedValue, profile: ProfileRef | None, units: UnitConversions
) -> dict[str, Any]:
    """The value in the unit interop reads it in, the unit the model stated, and the CSV."""
    value = units.convert(stated)
    return {
        PlexosPropertyCol.VALUE: value,
        PlexosPropertyCol.UNIT: stated.unit,
        PlexosPropertyCol.DATA_FILE: profile.path if profile is not None else None,
        PlexosPropertyCol.SCALING: build_scaling(profile, value, is_percent(stated.unit)),
        PlexosPropertyCol.ESCALATOR: profile.escalator if profile is not None else None,
    }


def _group_by_data_file(properties: _Rows) -> dict[str, _Rows]:
    """The property rows that read each data file, other than a Timeslice's Include."""
    rows_by_file: dict[str, _Rows] = {}
    for row in properties:
        relative = row[PlexosPropertyCol.DATA_FILE]
        if relative is not None and not is_timeslice_include(row):
            rows_by_file.setdefault(relative, []).append(row)
    return rows_by_file


def _group_by_series_key(rows: _Rows) -> dict[tuple[str, str], _Rows]:
    """Group one Data File's owning property rows by the (owner class, property) series they
    feed.
    """
    grouped: dict[tuple[str, str], _Rows] = {}
    for row in rows:
        grouped.setdefault(_build_group_key(row), []).append(row)
    return grouped


def _drop_empty_series(
    staged: dict[tuple[str, str], pl.LazyFrame], rows_by_file: dict[str, _Rows]
) -> dict[tuple[str, str], pl.LazyFrame]:
    """The staged series that hold a row. A series of no rows is no series, and is named.

    Reading one row is a column-scale check, so it is safe on a long series.
    """
    kept: dict[tuple[str, str], pl.LazyFrame] = {}
    for key, table in staged.items():
        if table.limit(1).collect().height:
            kept[key] = table
        else:
            _warn_empty_series(key, rows_by_file)
    return kept


def _warn_empty_series(key: tuple[str, str], rows_by_file: dict[str, _Rows]) -> None:
    for relative, rows in rows_by_file.items():
        owners = [row for row in rows if _build_group_key(row) == key]
        if owners:
            warn_no_series(relative, owners)


def _build_group_key(row: dict[str, Any]) -> tuple[str, str]:
    return (row[PlexosPropertyCol.CHILD_CLASS], row[PlexosPropertyCol.PROPERTY])


def _warn_objects_without_a_row(relative: str, rows: _Rows) -> None:
    """Name the objects that read a file of dated values which has no row for them."""
    names = sorted({row[PlexosPropertyCol.CHILD_OBJECT] for row in rows})
    log.warning(
        "plexos: %s has no row for %d object(s) that read it, so their values are left out: %s",
        relative,
        len(names),
        name_a_few(names),
    )


def _warn_missing_data_files(missing: list[str]) -> None:
    if not missing:
        return
    log.warning(
        "plexos: %d Data File(s) named by the model are not in the package, "
        "so their profiles are left out: %s",
        len(missing),
        name_a_few(sorted(missing)),
    )


def _to_float(value: str) -> float | None:
    """PLEXOS scalar values are numeric text; file-backed rows carry no scalar."""
    try:
        return float(value)
    except ValueError:
        return None


def _resolve_object_classes(tables: RowsByTable, dropped: DroppedRecords) -> _RowsByClass:
    """Group the object rows by their resolved PLEXOS class name.

    Each row gains a ``category`` column, its ``category_id`` resolved to the
    ``t_category`` name, so a mapping reads the free-text grouping (the carrier hint
    and, for demand response, the resource kind) without re-resolving the id itself.
    """
    classes = build_name_lookup(tables, CLASS_TABLE, CLASS_ID)
    categories = build_name_lookup(tables, _CATEGORY_TABLE, _CATEGORY_ID)
    objects_by_class: _RowsByClass = {}
    for row in tables.get(OBJECT_TABLE, []):
        reference = Reference(OBJECT_TABLE, row[OBJECT_ID], CLASS_ID, row[CLASS_ID])
        class_name = dropped.resolve(classes, reference)
        if class_name is not None:
            resolved = {
                **row,
                PlexosObjectCol.CATEGORY: categories.by_id.get(row.get(_CATEGORY_ID)),
            }
            objects_by_class.setdefault(class_name, []).append(resolved)
    return objects_by_class


def _element_record(element: ET.Element) -> dict[str, Any]:
    return {_local_name(child.tag): (child.text or "") for child in element}


def _local_name(tag: str) -> str:
    """Strip the ``{namespace}`` prefix ElementTree prepends to namespaced tags."""
    return tag.rsplit("}", 1)[-1]
