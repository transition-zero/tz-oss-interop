"""PLEXOS Reserve -> extensions sidecar.

PyPSA has no reserve component, so a reserve has nowhere to go in the translated network.
Rather than drop it, each one is carried into the extensions sidecar as a ``reserve`` record
in framework-neutral terms (see ``interop/core/extensions.py``), so a later hop into a
framework that does have reserves can restore it. Its absence from the network itself is
recorded as NOT_MAPPED so the gap is visible, not silent.

The requirement normalises to megawatts, which is what PLEXOS states ``Min Provision`` in.
What its ``t_data`` row is tagged with decides whether the number is the whole requirement
or a share of a profile, and the staged ``data_file`` column is what says which.

- Tagged to nothing, it stands on its own and is the megawatts of reserve wanted.
- Tagged to a PLEXOS "Variable" whose own Profile points at a load file the network's
  Load components are built from, it is that reserve's share of that profile. The staging
  layer already multiplies the profile by the share, so the staged series is the megawatts
  wanted at each snapshot and the record points at the companion parquet holding it.
- Tagged to a profile that is not one the Loads read, what the share is of has no megawatt
  meaning here, so no requirement is stated.
- Tagged straight to a Data File carrying its own MW columns, the property stages with no
  scalar of its own and the staged series is the requirement outright.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import polars as pl

from interop.core.extensions import (
    CompanionSeriesCol,
    ExtensionKind,
    ReserveDirection,
    ReserveExtension,
    ReserveKind,
    append_extensions,
    companion_filename,
)
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import UNIT_MW, StagedTimeSeriesCol
from interop.plugins.shared.plexos_constants import (
    PlexosClass,
    PlexosCollection,
    PlexosObjectCol,
    PlexosProperty,
    PlexosPropertyCol,
    PlexosResolvedTable,
    is_plexos_true,
)
from interop.plugins.shared.plexos_pypsa_translations._shared import (
    collapse_properties_by_object,
    read_property_rows,
    relate_children,
)
from interop.plugins.shared.plexos_pypsa_translations.decisions import (
    SourceReporter,
    SourceValue,
)

# The requirement column of the reserves companion parquet, named for the record field it
# stands in for so it carries that field's unit.
RESERVE_REQUIREMENT_COLUMN = "requirement_mw"

# PLEXOS packs direction and product into one Type code. The decode table is the model
# file's own input_mask on that property: 1 Raise, 2 Lower, 3 Regulation Raise, 4 Regulation
# Lower, 5 Replacement, 6 Operational, 7 Regulation, 8 Inertia. Raise and Lower name a
# direction only, so their product stays unknown.
_RESERVE_TYPES: dict[int, tuple[ReserveDirection, ReserveKind]] = {
    1: (ReserveDirection.UP, ReserveKind.UNKNOWN),
    2: (ReserveDirection.DOWN, ReserveKind.UNKNOWN),
    3: (ReserveDirection.UP, ReserveKind.REGULATING),
    4: (ReserveDirection.DOWN, ReserveKind.REGULATING),
    5: (ReserveDirection.UNKNOWN, ReserveKind.REPLACEMENT),
    6: (ReserveDirection.UNKNOWN, ReserveKind.OPERATING),
    7: (ReserveDirection.SYMMETRIC, ReserveKind.REGULATING),
    8: (ReserveDirection.UNKNOWN, ReserveKind.INERTIA),
}

# PLEXOS's Mutually Exclusive decode table, again from the model file's own input_mask.
# Auto leaves the choice to PLEXOS, so the sidecar states nothing rather than guessing.
_MUTUALLY_EXCLUSIVE_AUTO = 0.0
_MUTUALLY_EXCLUSIVE_YES = 1.0

_CARRIED_NOTE = (
    "reserve carried to the extensions sidecar; the network file itself has no reserve component"
)
_MEGAWATTS_NOTE = (
    "Min Provision is tagged to no profile, so it stands on its own and the sidecar "
    "states the requirement as megawatts"
)
_SERIES_NOTE = (
    "Min Provision varies over the horizon, so the sidecar states the requirement as "
    "megawatts at each snapshot in the companion parquet"
)


class _Form(StrEnum):
    """How PLEXOS states one reserve's Min Provision, and what the sidecar can do with it."""

    MEGAWATTS = "megawatts"
    SERIES = "series"
    # The three ways a reserve ends up travelling without a requirement.
    NONE = "none"
    UNNAMEABLE = "unnameable"
    UNSTAGED = "unstaged"


# Why a carried reserve travels without a requirement, one note per form.
_MISSING_NOTES: dict[_Form, str] = {
    _Form.NONE: (
        "Min Provision states neither a positive scalar nor a data file, so the reserve "
        "travels without a requirement"
    ),
    _Form.UNSTAGED: (
        "the profile behind Min Provision did not stage, so there is no series to state the "
        "requirement from and the reserve travels without one"
    ),
}


@dataclass(frozen=True)
class _Provision:
    """What Min Provision states, and the number the report shows for it."""

    form: _Form
    value: float | None = None


@dataclass(frozen=True)
class _Reserve:
    """One PLEXOS Reserve, as everything the sidecar record needs it.

    ``scalars`` is this reserve's properties collapsed to one value each, which every field
    but the requirement is read from. ``provision_profile`` is the CSV the ``Min Provision``
    value is a share of, null where the value stands on its own.
    """

    name: str
    scalars: dict[str, Any]
    contributing_generators: list[str]
    provision_profile: str | None
    stated_provision: float | None


def map_reserves(state: State, recorder: ScopedRecorder) -> None:
    """Carry every PLEXOS reserve into the extensions sidecar."""
    reserves = _read_reserves(state)
    if not reserves:
        return
    load_profiles = _load_profiles(state)
    stated = {reserve.name: _read_provision(reserve, load_profiles) for reserve in reserves}
    staged = _stage_requirement_series(state, [name for name, p in stated.items() if _varies(p)])
    provisions = {name: _settle(provision, name in staged) for name, provision in stated.items()}
    _record_decisions(reserves, provisions, recorder)
    records = [_extension_record(reserve, provisions[reserve.name]) for reserve in reserves]
    append_extensions(state.destination_extensions, ExtensionKind.RESERVE, records)


def _varies(provision: _Provision) -> bool:
    return provision.form is _Form.SERIES


def _settle(provision: _Provision, is_staged: bool) -> _Provision:
    """Downgrade a varying requirement whose series did not stage, so no record points at a
    companion the sink will not write."""
    if not _varies(provision) or is_staged:
        return provision
    return _Provision(_Form.UNSTAGED, provision.value)


# --- Reading the source ---


def _read_reserves(state: State) -> list[_Reserve]:
    properties = _properties_by_reserve(state)
    scalars = collapse_properties_by_object(
        state.source_topology[PlexosResolvedTable.PROPERTIES], PlexosClass.RESERVE
    )
    contributors = relate_children(
        state.source_topology[PlexosResolvedTable.MEMBERSHIPS],
        PlexosClass.RESERVE,
        PlexosCollection.GENERATORS,
    )
    return [
        _Reserve(
            name=name,
            scalars=scalars.get(name, {}),
            contributing_generators=contributors.get(name, []),
            provision_profile=_provision_row(properties.get(name, []), PlexosPropertyCol.DATA_FILE),
            stated_provision=_provision_row(properties.get(name, []), PlexosPropertyCol.VALUE),
        )
        for name in _reserve_names(state)
    ]


def _reserve_names(state: State) -> list[str]:
    reserves = state.source_topology.get(PlexosClass.RESERVE)
    if reserves is None:
        return []
    frame = reserves.select(PlexosObjectCol.NAME).collect()
    names: list[str] = frame[PlexosObjectCol.NAME].to_list()
    return names


def _properties_by_reserve(state: State) -> dict[str, list[dict[str, Any]]]:
    """Each reserve's property rows, kept long so a file-backed one keeps its ``data_file``."""
    properties = read_property_rows(
        state.source_topology[PlexosResolvedTable.PROPERTIES], PlexosClass.RESERVE
    )
    if properties.is_empty():
        return {}
    return {
        reserve: frame.drop(PlexosPropertyCol.CHILD_OBJECT).to_dicts()
        for (reserve,), frame in properties.partition_by(
            PlexosPropertyCol.CHILD_OBJECT, as_dict=True
        ).items()
    }


def _provision_row(properties: list[dict[str, Any]], column: str) -> Any:
    """One column of this reserve's Min Provision row, or None where it states none."""
    for row in properties:
        if row[PlexosPropertyCol.PROPERTY] == PlexosProperty.MIN_PROVISION:
            return row[column]
    return None


def _load_profiles(state: State) -> set[str]:
    """The CSVs the network's demand is read from, whether stated on a Region or a Node."""
    properties = state.source_topology[PlexosResolvedTable.PROPERTIES]
    if PlexosPropertyCol.CHILD_CLASS not in properties.collect_schema().names():
        return set()
    demand_classes = (PlexosClass.REGION, PlexosClass.NODE)
    paths = (
        properties.filter(
            pl.col(PlexosPropertyCol.CHILD_CLASS).is_in(demand_classes)
            & (pl.col(PlexosPropertyCol.PROPERTY) == PlexosProperty.LOAD)
            & pl.col(PlexosPropertyCol.DATA_FILE).is_not_null()
        )
        .select(PlexosPropertyCol.DATA_FILE)
        .unique()
        .collect()
    )
    return set(paths[PlexosPropertyCol.DATA_FILE].to_list())


def _read_provision(reserve: _Reserve, load_profiles: set[str]) -> _Provision:
    """How this reserve states its requirement, in the sidecar's own terms.

    ``collapse_properties_by_object`` drops file-backed values, so a Min Provision held
    wholly in a data file is absent from ``scalars`` and only the long row states it.
    """
    scalar = reserve.scalars.get(PlexosProperty.MIN_PROVISION)
    if reserve.provision_profile is None:
        if scalar is None or scalar <= 0:
            return _Provision(_Form.NONE)
        return _Provision(_Form.MEGAWATTS, scalar)
    # A profile with no scalar of its own, or with the 0 PLEXOS writes in place of one,
    # supplies the requirement outright. A positive scalar makes it a share of that profile,
    # which is megawatts only where the profile is one the network's Loads are built from.
    if scalar is None or scalar <= 0 or reserve.provision_profile in load_profiles:
        return _Provision(_Form.SERIES, reserve.stated_provision)
    return _Provision(_Form.UNNAMEABLE, reserve.stated_provision)


# --- Building the record ---


def _extension_record(reserve: _Reserve, provision: _Provision) -> ReserveExtension:
    direction, kind = _reserve_type(reserve)
    return ReserveExtension(
        name=reserve.name,
        requirement_mw=provision.value if provision.form is _Form.MEGAWATTS else None,
        requirement_series=_companion(provision),
        contributing_generators=reserve.contributing_generators,
        direction=direction,
        kind=kind,
        sustained_time_seconds=reserve.scalars.get(PlexosProperty.DURATION),
        is_available=_is_available(reserve),
        shortage_price=reserve.scalars.get(PlexosProperty.VALUE_OF_RESERVE_SHORTAGE),
        is_mutually_exclusive=_is_mutually_exclusive(reserve),
    )


def _companion(provision: _Provision) -> str | None:
    """The parquet a varying requirement is held in, or None where it states a scalar."""
    return companion_filename(ExtensionKind.RESERVE) if _varies(provision) else None


def _reserve_type(reserve: _Reserve) -> tuple[ReserveDirection, ReserveKind]:
    code = reserve.scalars.get(PlexosProperty.RESERVE_TYPE)
    if code is None:
        return ReserveDirection.UNKNOWN, ReserveKind.UNKNOWN
    return _RESERVE_TYPES.get(int(code), (ReserveDirection.UNKNOWN, ReserveKind.UNKNOWN))


def _is_available(reserve: _Reserve) -> bool | None:
    flag = reserve.scalars.get(PlexosProperty.IS_ENABLED)
    return None if flag is None else is_plexos_true(flag)


def _is_mutually_exclusive(reserve: _Reserve) -> bool | None:
    """PLEXOS states Yes, No or Auto; Auto leaves the choice to PLEXOS, so we state nothing."""
    flag = reserve.scalars.get(PlexosProperty.MUTUALLY_EXCLUSIVE)
    if flag is None or flag == _MUTUALLY_EXCLUSIVE_AUTO:
        return None
    return bool(flag == _MUTUALLY_EXCLUSIVE_YES)


# --- The companion series ---


def _stage_requirement_series(state: State, names: list[str]) -> set[str]:
    """Put every varying requirement into the companion frame, and name the ones that landed.

    The staging layer already multiplies a shared profile by each owner's share, so a
    reserve's staged Min Provision is the megawatts it wants at each snapshot. A reserve
    whose profile the source could not read has no rows, so it is not among the names.
    """
    source = state.source_time_series.get((PlexosClass.RESERVE, PlexosProperty.MIN_PROVISION))
    if not names or source is None:
        return set()
    wanted = source.filter(pl.col(StagedTimeSeriesCol.COMPONENT).is_in(names))
    staged = _staged_names(wanted)
    if staged:
        state.destination_extension_series[ExtensionKind.RESERVE] = _companion_frame(wanted)
    return staged


def _staged_names(wanted: pl.LazyFrame) -> set[str]:
    """The reserves the source staged rows for. A column subset, so safe to collect."""
    names = wanted.select(StagedTimeSeriesCol.COMPONENT).unique().collect()
    return set(names[StagedTimeSeriesCol.COMPONENT].to_list())


def _companion_frame(wanted: pl.LazyFrame) -> pl.LazyFrame:
    """The staged series restated in the terms of the field that references the file."""
    return wanted.select(
        pl.col(StagedTimeSeriesCol.SNAPSHOT).alias(CompanionSeriesCol.SNAPSHOT),
        pl.col(StagedTimeSeriesCol.COMPONENT).alias(CompanionSeriesCol.NAME),
        pl.col(StagedTimeSeriesCol.VALUE).alias(RESERVE_REQUIREMENT_COLUMN),
    ).sort(CompanionSeriesCol.NAME, CompanionSeriesCol.SNAPSHOT)


# --- Reporting ---


def _record_decisions(
    reserves: list[_Reserve],
    provisions: dict[str, _Provision],
    recorder: ScopedRecorder,
) -> None:
    reporter = SourceReporter(recorder)
    for reserve in reserves:
        reporter.record_dropped(_provision_source(reserve.name, None), _CARRIED_NOTE)
        _record_provision(reporter, reserve, provisions[reserve.name])


def _provision_source(name: str, value: Any, unit: str | None = None) -> SourceValue:
    return SourceValue(PlexosClass.RESERVE, name, PlexosProperty.MIN_PROVISION, value, unit)


def _record_provision(reporter: SourceReporter, reserve: _Reserve, provision: _Provision) -> None:
    note, unit = _provision_note(reserve, provision)
    reporter.record_dropped(_provision_source(reserve.name, provision.value, unit), note)


def _provision_note(reserve: _Reserve, provision: _Provision) -> tuple[str, str | None]:
    """What the report says about this requirement, and the unit its value is in."""
    match provision.form:
        case _Form.MEGAWATTS:
            return _MEGAWATTS_NOTE, UNIT_MW
        case _Form.SERIES:
            return _SERIES_NOTE, UNIT_MW
        case _Form.UNNAMEABLE:
            return _unnameable_note(reserve.provision_profile), None
        case _:
            return _MISSING_NOTES[provision.form], None


def _unnameable_note(profile: str | None) -> str:
    return (
        f"Min Provision is a share of {profile!r}, which is not a profile the network's "
        "Loads are built from, so what it is a share of cannot be stated in megawatts and "
        "the reserve travels without a requirement"
    )
