"""PLEXOS Forced Outage Rate and Mean Time to Repair -> a Sienna GeometricDistributionForcedOutage.

PLEXOS states the share of the time a unit is out, as a percentage, and the hours one repair
takes. Sienna states the minutes one recovery takes, and the chance in each minute that a
unit in service fails. In a two-state model the share of the time out is
``p / (p + 1 / T)`` for a chance ``p`` and a recovery time ``T``, so
``p = r / (1 - r) / T`` for a share ``r``.

The attribute describes a component that an earlier sub-step wrote, so this sub-step runs
after every unit has its Sienna id. A unit the translation left out takes no attribute. Each
attribute joins its unit through one row of the document's
``supplemental_attribute_associations`` list.
"""

from __future__ import annotations

from typing import Any, NamedTuple

import polars as pl

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import (
    MINUTES_PER_HOUR,
    UNIT_HOURS,
    UNIT_MINUTES,
    UNIT_PERCENT,
    Framework,
)
from interop.plugins.shared.plexos_constants import (
    PlexosClass,
    PlexosObjectCol,
    PlexosProperty,
    PlexosResolvedTable,
)
from interop.plugins.shared.plexos_pypsa_translations._shared import (
    collapse_properties_by_object,
    read_file_backed_properties,
)
from interop.plugins.shared.plexos_sienna_translations._shared import (
    ID_NOTE,
    UNIT_TYPES,
    TranslatedUnit,
    build_translated_units,
    plexos_field,
)
from interop.plugins.shared.sienna_constants import (
    ATTRIBUTE_ASSOCIATION_SCHEMA,
    FORCED_OUTAGES_DESTINATION_SCHEMA,
    SiennaAttributeAssociationCol,
    SiennaComponent,
    SiennaForcedOutageCol,
    SiennaSupplementalAttribute,
)
from interop.plugins.shared.sienna_events import (
    build_defaulted,
    build_derived,
    build_sienna_field,
    build_sienna_source,
)
from interop.plugins.shared.translation_runner import (
    SkipReport,
    SkipRule,
    Translation,
    apply_translations,
    build_document_id_translation,
    enrich_first_id,
    finalise,
    report_not_mapped,
)
from interop.ports.outbound.reporting import DestinationField, SourceField

_PERCENT = 100.0
_OUTAGE = SiennaSupplementalAttribute.GEOMETRIC_DISTRIBUTION_FORCED_OUTAGE

# One row per translated unit, in PLEXOS words, before any Sienna column exists.
_UNIT_NAME = "unit_name"
_UNIT_CLASS = "unit_class"
_UNIT_TYPE = "unit_type"
_UNIT_ID = "unit_id"
_UNIT_RATE = "unit_rate"
_UNIT_REPAIR_HOURS = "unit_repair_hours"
_IS_RATE_FILE_BACKED = "is_rate_file_backed"
_IS_REPAIR_FILE_BACKED = "is_repair_file_backed"

_UNITS_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    _UNIT_NAME: pl.Utf8,
    _UNIT_CLASS: pl.Utf8,
    _UNIT_TYPE: pl.Utf8,
    _UNIT_ID: pl.Int64,
    _UNIT_RATE: pl.Float64,
    _UNIT_REPAIR_HOURS: pl.Float64,
    _IS_RATE_FILE_BACKED: pl.Boolean,
    _IS_REPAIR_FILE_BACKED: pl.Boolean,
}

# The Sienna types each PLEXOS class that states a forced outage can become.
_SIENNA_TYPES: dict[PlexosClass, tuple[SiennaComponent, ...]] = {
    PlexosClass.GENERATOR: UNIT_TYPES,
    PlexosClass.BATTERY: (SiennaComponent.ENERGY_RESERVOIR_STORAGE,),
}

_RECOVERY_DERIVATION = "Mean Time to Repair in hours x 60"
_PROBABILITY_DERIVATION = (
    "Forced Outage Rate / 100 / (1 - Forced Outage Rate / 100) / mean_time_to_recovery"
)
_MONITORED_NOTE = "PLEXOS names no component whose state an outage watches; the list is empty"
_IDENTIFIER_DERIVATION = "the PLEXOS name of the unit the outage describes"
_FULL_OUTAGE_NOTE = (
    "a Forced Outage Rate of 100 % or more leaves the unit no time in service to fail from, "
    "so no forced outage states it"
)
_NO_REPAIR_NOTE = (
    "the unit states no Mean Time to Repair above 0, so neither the recovery time nor the "
    "chance of failure can be stated, and no forced outage is written"
)
_FILE_BACKED_NOTE = (
    "Forced Outage Rate comes from a data file, and a forced outage states one rate, so no "
    "forced outage is written"
)
_REPAIR_FILE_BACKED_NOTE = (
    "Mean Time to Repair comes from a data file, and a forced outage states one recovery time, "
    "so no forced outage is written"
)
_UNUSED_REPAIR_NOTE = (
    "the unit states no Forced Outage Rate above 0, so it never fails and its Mean Time to "
    "Repair has no forced outage to belong to"
)


class ForcedOutages(NamedTuple):
    """The forced outage attributes, and the rows that join each one to its unit."""

    attributes: pl.DataFrame
    associations: pl.DataFrame


def map_forced_outages(state: State, recorder: ScopedRecorder) -> ForcedOutages:
    """One forced outage for each translated unit that states a usable one."""
    units = build_translated_units(state)
    usable = pl.concat(
        [
            _report_unusable(_build_units_table(state, plexos_class, units), plexos_class, recorder)
            for plexos_class in _SIENNA_TYPES
        ]
    )
    outages = _translate(enrich_first_id(usable, state), recorder)
    return ForcedOutages(
        attributes=finalise(outages, FORCED_OUTAGES_DESTINATION_SCHEMA, recorder, _OUTAGE),
        associations=_build_associations(outages),
    )


# --- reading the staged PLEXOS tables ---------------------------------------


class _ClassValues(NamedTuple):
    """The scalar values and the file-backed properties of each object of one class."""

    scalars: dict[str, dict[str, float]]
    file_backed: dict[str, list[str]]


def _build_units_table(
    state: State, plexos_class: PlexosClass, units: dict[str, list[TranslatedUnit]]
) -> pl.DataFrame:
    """The objects of one PLEXOS class that a Sienna table holds, with their outage values."""
    values = _build_class_values(state, plexos_class)
    rows = [
        _build_unit_row(plexos_class, name, unit, values)
        for name in _list_object_names(state, plexos_class)
        if (unit := _find_unit(units.get(name, []), plexos_class)) is not None
    ]
    return pl.DataFrame(rows, schema=_UNITS_SCHEMA)


def _build_class_values(state: State, plexos_class: PlexosClass) -> _ClassValues:
    properties = state.source_topology.get(PlexosResolvedTable.PROPERTIES)
    if properties is None:
        return _ClassValues({}, {})
    return _ClassValues(
        collapse_properties_by_object(properties, plexos_class),
        read_file_backed_properties(properties, plexos_class),
    )


def _find_unit(
    candidates: list[TranslatedUnit], plexos_class: PlexosClass
) -> TranslatedUnit | None:
    """The first Sienna component of the name that this class can become."""
    return next((one for one in candidates if one.sienna_type in _SIENNA_TYPES[plexos_class]), None)


def _build_unit_row(
    plexos_class: PlexosClass, name: str, unit: TranslatedUnit, values: _ClassValues
) -> dict[str, Any]:
    stated = values.scalars.get(name, {})
    file_backed = values.file_backed.get(name, [])
    return {
        _UNIT_NAME: name,
        _UNIT_CLASS: plexos_class,
        _UNIT_TYPE: unit.sienna_type,
        _UNIT_ID: unit.sienna_id,
        _UNIT_RATE: stated.get(PlexosProperty.FORCED_OUTAGE_RATE),
        _UNIT_REPAIR_HOURS: stated.get(PlexosProperty.MEAN_TIME_TO_REPAIR),
        _IS_RATE_FILE_BACKED: PlexosProperty.FORCED_OUTAGE_RATE in file_backed,
        _IS_REPAIR_FILE_BACKED: PlexosProperty.MEAN_TIME_TO_REPAIR in file_backed,
    }


def _list_object_names(state: State, plexos_class: PlexosClass) -> list[str]:
    objects = state.source_topology.get(plexos_class)
    if objects is None:
        return []
    names: list[str] = (
        objects.select(PlexosObjectCol.NAME).collect()[PlexosObjectCol.NAME].to_list()
    )
    return sorted(names)


# --- leaving out each unit that states no usable outage ---------------------


class _OutageValue(NamedTuple):
    """One PLEXOS value an outage reads: its column, its property and its unit."""

    column: str
    plexos_property: str
    unit: str


_RATE = _OutageValue(_UNIT_RATE, PlexosProperty.FORCED_OUTAGE_RATE, UNIT_PERCENT)
_REPAIR = _OutageValue(_UNIT_REPAIR_HOURS, PlexosProperty.MEAN_TIME_TO_REPAIR, UNIT_HOURS)


class _Reason(NamedTuple):
    """One reason a unit takes no forced outage, and the units it keeps."""

    keep: pl.Expr
    reason: str
    note: str
    value: _OutageValue


# Each reason in the order it is tried, so a unit is reported for the first that holds.
_REASONS: tuple[_Reason, ...] = (
    _Reason(
        ~pl.col(_IS_RATE_FILE_BACKED),
        "read Forced Outage Rate from a data file, and a forced outage states one rate, "
        "so none is written",
        _FILE_BACKED_NOTE,
        _RATE,
    ),
    _Reason(
        pl.col(_UNIT_RATE) > 0,
        "state a Mean Time to Repair but no Forced Outage Rate above 0, so the repair time "
        "has no forced outage to belong to",
        _UNUSED_REPAIR_NOTE,
        _REPAIR,
    ),
    _Reason(
        pl.col(_UNIT_RATE) < _PERCENT,
        "state a Forced Outage Rate of 100 % or more, so no forced outage is written",
        _FULL_OUTAGE_NOTE,
        _RATE,
    ),
    _Reason(
        ~pl.col(_IS_REPAIR_FILE_BACKED),
        "read Mean Time to Repair from a data file, and a forced outage states one recovery "
        "time, so none is written",
        _REPAIR_FILE_BACKED_NOTE,
        _REPAIR,
    ),
    _Reason(
        pl.col(_UNIT_REPAIR_HOURS) > 0,
        "state a Forced Outage Rate but no Mean Time to Repair above 0, so no forced outage "
        "is written",
        _NO_REPAIR_NOTE,
        _RATE,
    ),
)

# A unit that states no rate and no repair time states no outage, so there is nothing to report.
_STATES_AN_OUTAGE = (
    pl.col(_IS_RATE_FILE_BACKED)
    | (pl.col(_UNIT_RATE) > 0)
    | pl.col(_UNIT_REPAIR_HOURS).is_not_null()
)


def _report_unusable(
    units: pl.DataFrame, plexos_class: PlexosClass, recorder: ScopedRecorder
) -> pl.DataFrame:
    """The units with a usable outage. Each reason records every unit it holds for, and warns."""
    usable = units.filter(_STATES_AN_OUTAGE)
    for rule in _build_rules(plexos_class):
        usable, _ = report_not_mapped(usable, rule.keep, rule.report, recorder)
    return usable


def _build_rules(plexos_class: PlexosClass) -> list[SkipRule]:
    return [SkipRule(one.keep, _build_report(plexos_class, one)) for one in _REASONS]


def _build_report(plexos_class: PlexosClass, reason: _Reason) -> SkipReport:
    return SkipReport(
        pipeline=Framework.PLEXOS,
        framework=Framework.PLEXOS,
        component=plexos_class,
        name_col=_UNIT_NAME,
        reason=reason.reason,
        counted_noun=f"{plexos_class}(s)",
        note=reason.note,
        attribute_col=reason.value.column,
        attribute_name=reason.value.plexos_property,
        attribute_unit=reason.value.unit,
    )


# --- the outage each usable unit becomes ------------------------------------


def _translate(units: pl.DataFrame, recorder: ScopedRecorder) -> pl.DataFrame:
    """The recovery time first, since the chance of failure reads it."""
    outages = apply_translations(units, OUTAGE_TRANSLATIONS, recorder)
    return apply_translations(outages, OUTAGE_PROBABILITY_TRANSLATIONS, recorder)


def _build_associations(outages: pl.DataFrame) -> pl.DataFrame:
    """One row for each outage, which names the unit the outage describes."""
    col = SiennaAttributeAssociationCol
    return outages.select(
        pl.col(_UNIT_ID).alias(col.COMPONENT_ID),
        pl.col(_UNIT_TYPE).alias(col.COMPONENT_TYPE),
        pl.col(SiennaForcedOutageCol.ID).alias(col.ATTRIBUTE_ID),
        pl.lit(_OUTAGE.value).alias(col.ATTRIBUTE_TYPE),
    ).cast(pl.Schema(ATTRIBUTE_ASSOCIATION_SCHEMA))


def _build_rate_source(row: dict[str, Any]) -> SourceField:
    return plexos_field(
        row[_UNIT_CLASS],
        row[_UNIT_NAME],
        PlexosProperty.FORCED_OUTAGE_RATE,
        row[_UNIT_RATE],
        UNIT_PERCENT,
    )


def _build_repair_source(row: dict[str, Any]) -> SourceField:
    return plexos_field(
        row[_UNIT_CLASS],
        row[_UNIT_NAME],
        PlexosProperty.MEAN_TIME_TO_REPAIR,
        row[_UNIT_REPAIR_HOURS],
        UNIT_HOURS,
    )


def _build_outage_field(
    name: str, attribute: str, value: Any = None, unit: str | None = None
) -> DestinationField:
    return build_sienna_field(_OUTAGE, name, attribute, value, unit)


def _build_outage_value(
    row: dict[str, Any], column: str, unit: str | None = None
) -> DestinationField:
    return _build_outage_field(row[_UNIT_NAME], column, row[column], unit)


# --- Translation constants ---

OUTAGE_ID = build_document_id_translation(
    _build_outage_field, dest_name_col=_UNIT_NAME, id_col=SiennaForcedOutageCol.ID, note=ID_NOTE
)

OUTAGE_RECOVERY = Translation(
    exprs=[
        (pl.col(_UNIT_REPAIR_HOURS) * MINUTES_PER_HOUR).alias(
            SiennaForcedOutageCol.MEAN_TIME_TO_RECOVERY
        )
    ],
    make_events=lambda old, new: build_derived(
        [_build_repair_source(old)],
        [_build_outage_value(new, SiennaForcedOutageCol.MEAN_TIME_TO_RECOVERY, UNIT_MINUTES)],
        _RECOVERY_DERIVATION,
    ),
)

OUTAGE_MONITORED = Translation(
    exprs=[
        pl.lit(
            [], dtype=FORCED_OUTAGES_DESTINATION_SCHEMA[SiennaForcedOutageCol.MONITORED_COMPONENTS]
        ).alias(SiennaForcedOutageCol.MONITORED_COMPONENTS)
    ],
    make_events=lambda old, new: build_defaulted(
        [_build_outage_value(new, SiennaForcedOutageCol.MONITORED_COMPONENTS)], _MONITORED_NOTE
    ),
)

OUTAGE_IDENTIFIER = Translation(
    exprs=[pl.col(_UNIT_NAME).alias(SiennaForcedOutageCol.IDENTIFIER)],
    make_events=lambda old, new: build_derived(
        [plexos_field(old[_UNIT_CLASS], old[_UNIT_NAME], PlexosObjectCol.NAME, old[_UNIT_NAME])],
        [_build_outage_value(new, SiennaForcedOutageCol.IDENTIFIER)],
        _IDENTIFIER_DERIVATION,
    ),
)

# The chance of failure reads the recovery time an earlier translation wrote, so it runs in a
# batch of its own after them.
OUTAGE_PROBABILITY = Translation(
    exprs=[
        (
            pl.col(_UNIT_RATE)
            / _PERCENT
            / (1 - pl.col(_UNIT_RATE) / _PERCENT)
            / pl.col(SiennaForcedOutageCol.MEAN_TIME_TO_RECOVERY)
        ).alias(SiennaForcedOutageCol.OUTAGE_TRANSITION_PROBABILITY)
    ],
    make_events=lambda old, new: build_derived(
        [
            _build_rate_source(old),
            build_sienna_source(
                _OUTAGE,
                old[_UNIT_NAME],
                SiennaForcedOutageCol.MEAN_TIME_TO_RECOVERY,
                old[SiennaForcedOutageCol.MEAN_TIME_TO_RECOVERY],
                UNIT_MINUTES,
            ),
        ],
        [_build_outage_value(new, SiennaForcedOutageCol.OUTAGE_TRANSITION_PROBABILITY)],
        _PROBABILITY_DERIVATION,
    ),
)

OUTAGE_TRANSLATIONS: list[Translation] = [
    OUTAGE_ID,
    OUTAGE_RECOVERY,
    OUTAGE_MONITORED,
    OUTAGE_IDENTIFIER,
]

OUTAGE_PROBABILITY_TRANSLATIONS: list[Translation] = [OUTAGE_PROBABILITY]
