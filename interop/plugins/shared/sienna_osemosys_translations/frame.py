"""The frame of the written model: its years, its units and the default of each parameter.

A Sienna system states no year, so the years come from the `ByYear` keys of the sidecar. Every
value of a Sienna system is in MW, MWh, dollars or tonnes, so the written model states those
units and one MW of capacity runs 8760 MWh in a whole year.

`DiscountRate` and `CapacityToActivityUnit` get a table with no rows, because no Sienna field
states either for one region or one technology. The configuration then states the number as
the default of the parameter, which every region and every technology takes.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import NamedTuple

import polars as pl

from interop.core.extensions import ExtensionReader, RepresentativePeriodExtension
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import ALL_COMPONENTS, HOURS_PER_YEAR
from interop.plugins.shared.osemosys_canonical.constants import (
    YEAR,
    MetadataColumn,
    MetadataTable,
    TableKind,
)
from interop.plugins.shared.osemosys_canonical.metadata import DEFAULTS_SCHEMA, UNITS_SCHEMA
from interop.plugins.shared.osemosys_canonical.schema import load_canonical_schema
from interop.plugins.shared.sienna_osemosys_translations.constants import (
    CAPACITY_UNIT,
    CURRENCY_UNIT,
    EMISSIONS_UNIT,
    ENERGY_UNIT,
    UNDATED_YEAR,
)
from interop.plugins.shared.sienna_osemosys_translations.destination import (
    set_metadata_table,
    set_parameter_table,
)
from interop.plugins.shared.sienna_osemosys_translations.events import (
    build_defaulted,
    build_derived,
    build_osemosys_member,
    build_osemosys_metadata,
    build_osemosys_parameter,
    build_sienna_source,
)
from interop.plugins.shared.sienna_osemosys_translations.series import SeriesWindow
from interop.plugins.shared.sienna_osemosys_translations.years import list_sidecar_years

DISCOUNT_RATE = "discount_rate"
CAPACITY_TO_ACTIVITY_UNIT = "capacity_to_activity_unit"

_RECORD_KIND = "representative_period"
_SERIES_KIND = "time_series"
_SNAPSHOT_FIELD = "snapshot"


class _YearSource(NamedTuple):
    """The Sienna field that one year comes from, and the rule that reads the year off it."""

    kind: str
    field: str
    derivation: str


_FROM_RECORD = _YearSource(
    _RECORD_KIND,
    "first_timestamp",
    "the year of the first timestamp of the earliest representative period",
)
_FROM_SERIES = _YearSource(
    _SERIES_KIND, _SNAPSHOT_FIELD, "the year of the first snapshot of the series"
)
_UNDATED_YEAR_NOTE = (
    "the sidecar names no year and the system states no snapshot, so the leg writes one year"
)
_UNITS_NOTE = (
    "every value of a Sienna system is in {capacity}, {energy}, {currency} or {emissions}, so "
    "the written model states those units"
)
_ACTIVITY_NOTE = (
    "the units of the written model are MW and MWh, so one MW of capacity runs the 8760 MWh of "
    "a whole year and no Sienna field states that number"
)
_SCHEMA_DEFAULT_NOTE = (
    "no Sienna field states this parameter, so the written model takes the default of the "
    "canonical schema"
)

_FIXED_UNITS = {
    "capacity": CAPACITY_UNIT,
    "energy": ENERGY_UNIT,
    "currency": CURRENCY_UNIT,
    "emissions": EMISSIONS_UNIT,
}


def build_model_years(
    reader: ExtensionReader,
    records: list[RepresentativePeriodExtension],
    window: SeriesWindow | None,
    recorder: ScopedRecorder,
) -> list[int]:
    """The years of the model: the sidecar's own, or the one year that the timestamps give."""
    named = list_sidecar_years(reader)
    return named if named else [_build_undated_year(records, window, recorder)]


def _build_undated_year(
    records: list[RepresentativePeriodExtension],
    window: SeriesWindow | None,
    recorder: ScopedRecorder,
) -> int:
    earliest = min((record.first_timestamp for record in records), default=None)
    if earliest is not None:
        return _record_year(earliest.year, _FROM_RECORD, recorder)
    if window is not None:
        first = window.first_timestamp
        return _record_year(first.year, _FROM_SERIES, recorder)
    return _record_undated_year(recorder)


def _record_year(year: int, found: _YearSource, recorder: ScopedRecorder) -> int:
    source = build_sienna_source(found.kind, ALL_COMPONENTS, found.field, year)
    destination = build_osemosys_member(YEAR, str(year))
    recorder.append(build_derived([source], [destination], found.derivation))
    return year


def _record_undated_year(recorder: ScopedRecorder) -> int:
    destination = build_osemosys_member(YEAR, str(UNDATED_YEAR))
    recorder.append(build_defaulted([destination], _UNDATED_YEAR_NOTE))
    return UNDATED_YEAR


def set_frame_parameters(state: State, recorder: ScopedRecorder) -> None:
    """The two parameters whose value the units of the model fix, each with no rows."""
    for parameter in (DISCOUNT_RATE, CAPACITY_TO_ACTIVITY_UNIT):
        set_parameter_table(state, parameter, [])
    destination = build_osemosys_parameter(
        CAPACITY_TO_ACTIVITY_UNIT, ALL_COMPONENTS, HOURS_PER_YEAR, ENERGY_UNIT
    )
    recorder.append(build_defaulted([destination], _ACTIVITY_NOTE))


def set_units_table(state: State, recorder: ScopedRecorder) -> None:
    rows = [
        {MetadataColumn.QUANTITY: quantity, MetadataColumn.UNIT: unit}
        for quantity, unit in _FIXED_UNITS.items()
    ]
    set_metadata_table(state, MetadataTable.UNITS, pl.DataFrame(rows, schema=UNITS_SCHEMA))
    destinations = [
        build_osemosys_metadata(MetadataTable.UNITS, quantity, unit)
        for quantity, unit in _FIXED_UNITS.items()
    ]
    recorder.append(build_defaulted(destinations, _UNITS_NOTE.format(**_FIXED_UNITS)))


def set_defaults_table(state: State, written: Sequence[str], recorder: ScopedRecorder) -> None:
    """The default of every canonical parameter, so a parameter the leg writes states one."""
    schema = load_canonical_schema()
    rows = [_build_default_row(name) for name in schema.parameters]
    set_metadata_table(state, MetadataTable.DEFAULTS, pl.DataFrame(rows, schema=DEFAULTS_SCHEMA))
    _record_schema_defaults(written, recorder)


def _build_default_row(parameter: str) -> dict[str, object]:
    entry = load_canonical_schema().parameters[parameter]
    default = _choose_default(parameter, entry.default)
    return {
        MetadataColumn.KIND: TableKind.PARAMETER,
        MetadataColumn.PARAMETER: parameter,
        MetadataColumn.DEFAULT: default,
        MetadataColumn.DEFAULT_FROM: None if default is not None else entry.default_from,
    }


def _choose_default(parameter: str, stated: float | None) -> float | None:
    """The units of the model fix the activity of one unit of capacity; the schema fixes the
    rest."""
    return HOURS_PER_YEAR if parameter == CAPACITY_TO_ACTIVITY_UNIT else stated


def _record_schema_defaults(written: Sequence[str], recorder: ScopedRecorder) -> None:
    """One event for each parameter the leg writes, because that default reaches the model."""
    for parameter in sorted(set(written) - {CAPACITY_TO_ACTIVITY_UNIT}):
        default = _build_default_row(parameter)[MetadataColumn.DEFAULT]
        destination = build_osemosys_parameter(parameter, ALL_COMPONENTS, default)
        recorder.append(build_defaulted([destination], _SCHEMA_DEFAULT_NOTE))
