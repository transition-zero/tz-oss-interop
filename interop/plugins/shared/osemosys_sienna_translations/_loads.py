"""OSeMOSYS demand for an electricity fuel -> Sienna PowerLoad with an hourly series.

The specified annual demand of a fuel becomes a load named for the fuel. In each hour of the
calendar, the load is `specified_annual_demand (MWh) × specified_demand_profile /
(year_split × 8760 h)` of the timeslice of that hour. The accumulated annual demand of a fuel
becomes a second load, `<fuel>/accumulated`, flat at `accumulated_annual_demand (MWh) / 8760 h`.

A load states its peak as `max_active_power`. Its series is in MW, and the sink divides it by
that peak.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import Any

import polars as pl

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import UNIT_MVA, UNIT_MW, StagedTimeSeriesCol
from interop.plugins.shared.osemosys_canonical.constants import (
    FUEL,
    OSEMOSYS_FRAMEWORK,
    REGION,
    TIMESLICE,
    VALUE_COL,
    AnnotationColumn,
)
from interop.plugins.shared.osemosys_sienna_constants import (
    ACCUMULATED_LOAD_SUFFIX,
    HOURS_PER_YEAR,
    LOAD_NAME_SEPARATOR,
    MIN_LOAD_BASE_POWER_MVA,
    OSEMOSYS_TO_SIENNA_PIPELINE,
    CalendarHourCol,
    DemandParameter,
)
from interop.plugins.shared.osemosys_sienna_translations._buses import (
    FUEL_NAME,
    read_electricity_fuels,
)
from interop.plugins.shared.osemosys_sienna_translations._canonical import (
    read_parameter,
    read_parameter_with_defaults,
)
from interop.plugins.shared.osemosys_sienna_translations._events import (
    build_derived,
    build_osemosys_field,
    build_sienna_field,
    build_sienna_source,
)
from interop.plugins.shared.osemosys_sienna_translations._names import (
    express_component_name,
    express_report_name,
)
from interop.plugins.shared.osemosys_sienna_translations._operations import OperationsYear
from interop.plugins.shared.osemosys_sienna_translations._series import (
    build_series_firsts,
    build_series_peaks,
)
from interop.plugins.shared.sienna_constants import (
    LOAD_CONFORMITY_DTYPE,
    LoadConformity,
    SiennaComponent,
    SiennaLoadCol,
)
from interop.plugins.shared.translation_runner import (
    SkippedNames,
    SkipReport,
    SkipRule,
    Translation,
    default_translation,
    filter_component,
    row_position_id_translation,
)
from interop.plugins.shared.warning_text import name_a_few
from interop.ports.outbound.reporting import EventKind, TranslationEvent

log = logging.getLogger(__name__)

# One row for each load, in OSeMOSYS words, before any Sienna column exists.
LOAD_NAME = "load_name"
DEMAND_PARAMETER = "demand_parameter"
ANNUAL_DEMAND = "annual_demand"
ANNUAL_DEMAND_MWH = "annual_demand_mwh"
ENERGY_UNIT = "energy_unit"
PEAK_MW = "peak_mw"
FIRST_MW = "first_mw"

_PROFILE = "profile"
_YEAR_SPLIT = "year_split"
_HOURLY_MW = "hourly_mw"
_NO_REACTIVE_POWER = 0.0

_ID_NOTE = "assigned by 1-based row position in the PowerLoad table"
_AVAILABLE_NOTE = "OSeMOSYS states no availability of a demand; every load is available"
_REACTIVE_POWER_NOTE = "OSeMOSYS states no reactive demand; reactive_power defaults to 0.0"
_MAX_REACTIVE_POWER_NOTE = "OSeMOSYS states no reactive demand; max_reactive_power defaults to 0.0"
_CONFORMITY_NOTE = "OSeMOSYS has no load conformity concept"
_NAME_DERIVATION = (
    "the fuel, after its region when two regions state demand for one fuel, and then "
    f"'{LOAD_NAME_SEPARATOR}{ACCUMULATED_LOAD_SUFFIX}' for accumulated annual demand"
)
_BUS_DERIVATION = "the location of the fuel -> bus"
_SPECIFIED_DERIVATION = (
    "specified_annual_demand (MWh) × specified_demand_profile / (year_split × 8760 h) of the "
    "timeslice of each hour"
)
_ACCUMULATED_DERIVATION = "accumulated_annual_demand (MWh) / 8760 h in each hour"
_PEAK_DERIVATION = "the highest hour of the max_active_power series"
_FIRST_DERIVATION = "the first hour of the max_active_power series"
_BASE_POWER_DERIVATION = f"max(max_active_power, {MIN_LOAD_BASE_POWER_MVA}) MVA"
_SERIES_ATTRIBUTE = f"{SiennaLoadCol.MAX_ACTIVE_POWER} time series"
_LOST_DEMAND_NOTE = (
    "the timeslice has a year_split of zero, so it holds no hour of the calendar and this share "
    "of the demand is left out"
)

_SOURCE_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    REGION: pl.Utf8,
    FUEL: pl.Utf8,
    FUEL_NAME: pl.Utf8,
    AnnotationColumn.LOCATION: pl.Utf8,
    DEMAND_PARAMETER: pl.Utf8,
    ANNUAL_DEMAND: pl.Float64,
}
_SERIES_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    StagedTimeSeriesCol.SNAPSHOT: pl.Datetime("us"),
    StagedTimeSeriesCol.COMPONENT: pl.Utf8,
    StagedTimeSeriesCol.VALUE: pl.Float64,
}

NO_HOURLY_DEMAND_SKIP = SkipReport(
    pipeline=OSEMOSYS_TO_SIENNA_PIPELINE,
    framework=OSEMOSYS_FRAMEWORK,
    component=FUEL,
    name_col=FUEL_NAME,
    reason="have an annual demand but no demand in any hour of the calendar",
    counted_noun="load(s)",
    note=(
        "the demand profile or the timeslices of the year give the demand no hour, so the "
        "load is left out"
    ),
    listed=SkippedNames(column=LOAD_NAME, label="Loads"),
    attribute_col=ANNUAL_DEMAND,
)


# Takes out the rows that a rule does not keep, and reports them or not.
_DropRows = Callable[[pl.DataFrame, SkipRule], pl.DataFrame]


@dataclass(frozen=True)
class LoadSources:
    """One row for each load, and the hourly series in MW of each load."""

    table: pl.DataFrame
    series: pl.DataFrame


def build_loads_source(
    state: State, operations: OperationsYear, recorder: ScopedRecorder
) -> LoadSources:
    return _build_loads(state, operations, _build_reported_drop(recorder), recorder)


def build_load_series(
    state: State, operations: OperationsYear, recorder: ScopedRecorder
) -> pl.DataFrame:
    """The hourly MW of each load of the year, for a caller that reports the loads it needs.

    A demand that is not a load leaves no report here, so a caller that reads many years does
    not repeat one report for each year.
    """
    return _build_loads(state, operations, _drop_silently, recorder).series


def _build_loads(
    state: State, operations: OperationsYear, drop: _DropRows, recorder: ScopedRecorder
) -> LoadSources:
    demands = _enrich_load_names(_read_demands(state, operations.year, drop))
    if demands.height == 0:
        return LoadSources(demands, pl.DataFrame(schema=_SERIES_SCHEMA))
    demands = demands.with_columns(
        operations.units.convert_energy_to_mwh(pl.col(ANNUAL_DEMAND)).alias(ANNUAL_DEMAND_MWH),
        pl.lit(operations.units.energy_unit, dtype=pl.Utf8).alias(ENERGY_UNIT),
    )
    series = _build_series(state, operations, demands, recorder)
    table = _enrich_series_values(demands, series)
    table = drop(table, SkipRule(pl.col(PEAK_MW) > 0, NO_HOURLY_DEMAND_SKIP))
    kept = series.filter(pl.col(StagedTimeSeriesCol.COMPONENT).is_in(table[LOAD_NAME].implode()))
    return LoadSources(table.sort(LOAD_NAME), kept)


# --- the demands of the year ---------------------------------------------------


def _build_reported_drop(recorder: ScopedRecorder) -> _DropRows:
    def drop(table: pl.DataFrame, rule: SkipRule) -> pl.DataFrame:
        return filter_component(table, rule.keep, rule.report, recorder)[0]

    return drop


def _drop_silently(table: pl.DataFrame, rule: SkipRule) -> pl.DataFrame:
    return table.filter(rule.keep.fill_null(False))  # noqa: FBT003


def _read_demands(state: State, year: int, drop: _DropRows) -> pl.DataFrame:
    fuels = read_electricity_fuels(state).filter(pl.col(AnnotationColumn.LOCATION).is_not_null())
    tables = [
        _read_demand(state, year, parameter, fuels, drop)
        for parameter in (
            DemandParameter.SPECIFIED_ANNUAL_DEMAND,
            DemandParameter.ACCUMULATED_ANNUAL_DEMAND,
        )
    ]
    return pl.concat(tables).select(list(_SOURCE_SCHEMA))


def _read_demand(
    state: State,
    year: int,
    parameter: DemandParameter,
    fuels: pl.DataFrame,
    drop: _DropRows,
) -> pl.DataFrame:
    stated = read_parameter(state, parameter, year).filter(pl.col(VALUE_COL) != 0)
    rows = stated.select(
        REGION,
        FUEL,
        express_report_name(FUEL).alias(FUEL_NAME),
        pl.lit(parameter.value).alias(DEMAND_PARAMETER),
        pl.col(VALUE_COL).cast(pl.Float64).alias(ANNUAL_DEMAND),
    ).join(fuels.select(REGION, FUEL, AnnotationColumn.LOCATION), on=[REGION, FUEL], how="left")
    positive = drop(
        rows, SkipRule(pl.col(ANNUAL_DEMAND) > 0, _build_negative_demand_skip(parameter))
    )
    electricity = drop(
        positive,
        SkipRule(
            pl.col(AnnotationColumn.LOCATION).is_not_null(),
            _build_not_electricity_skip(parameter),
        ),
    )
    return electricity.cast(pl.Schema(_SOURCE_SCHEMA))


def _build_negative_demand_skip(parameter: DemandParameter) -> SkipReport:
    return SkipReport(
        pipeline=OSEMOSYS_TO_SIENNA_PIPELINE,
        framework=OSEMOSYS_FRAMEWORK,
        component=FUEL,
        name_col=FUEL_NAME,
        reason=f"state a negative {parameter}",
        counted_noun="fuel(s)",
        note="a demand below zero is not a load, so the demand is left out",
        attribute_col=ANNUAL_DEMAND,
        attribute_name=parameter,
    )


def _build_not_electricity_skip(parameter: DemandParameter) -> SkipReport:
    return SkipReport(
        pipeline=OSEMOSYS_TO_SIENNA_PIPELINE,
        framework=OSEMOSYS_FRAMEWORK,
        component=FUEL,
        name_col=FUEL_NAME,
        reason=f"state {parameter} but are not electricity fuels with a location",
        counted_noun="fuel(s)",
        note=(
            "the operations system holds electricity only, and a demand needs a bus at the "
            "location of its fuel, so the demand is left out"
        ),
        attribute_col=ANNUAL_DEMAND,
        attribute_name=parameter,
    )


def _enrich_load_names(demands: pl.DataFrame) -> pl.DataFrame:
    """A load takes the Sienna name of its fuel, and a suffix for accumulated demand."""
    accumulated = pl.col(DEMAND_PARAMETER) == DemandParameter.ACCUMULATED_ANNUAL_DEMAND
    suffix = f"{LOAD_NAME_SEPARATOR}{ACCUMULATED_LOAD_SUFFIX}"
    base = express_component_name(FUEL)
    return demands.with_columns(
        pl.when(accumulated)
        .then(pl.concat_str(base, pl.lit(suffix)))
        .otherwise(base)
        .alias(LOAD_NAME)
    )


# --- the hourly series ----------------------------------------------------------------


def _build_series(
    state: State, operations: OperationsYear, demands: pl.DataFrame, recorder: ScopedRecorder
) -> pl.DataFrame:
    specified = _build_specified_demand(state, operations, demands)
    _report_demand_without_hours(specified, recorder)
    hourly = specified.select(LOAD_NAME, TIMESLICE, _HOURLY_MW)
    return pl.concat(
        [_reshape_to_series(operations, hourly), _build_accumulated_series(operations, demands)]
    )


def _build_specified_demand(
    state: State, operations: OperationsYear, demands: pl.DataFrame
) -> pl.DataFrame:
    """One row for each load of specified demand and each timeslice, with its MW."""
    specified = demands.filter(
        pl.col(DEMAND_PARAMETER) == DemandParameter.SPECIFIED_ANNUAL_DEMAND
    ).select(LOAD_NAME, REGION, FUEL, FUEL_NAME, ANNUAL_DEMAND_MWH)
    timeslices = _build_year_split_table(operations)
    keys = specified.select(REGION, FUEL).join(timeslices.select(TIMESLICE), how="cross")
    profile = read_parameter_with_defaults(
        state, DemandParameter.SPECIFIED_DEMAND_PROFILE, operations.year, keys
    ).rename({VALUE_COL: _PROFILE})
    return (
        specified.join(profile, on=[REGION, FUEL])
        .join(timeslices, on=TIMESLICE)
        .with_columns(_express_specified_mw().alias(_HOURLY_MW))
    )


def _report_demand_without_hours(specified: pl.DataFrame, recorder: ScopedRecorder) -> None:
    """A profile above zero in a timeslice with no share of the year reaches no hour."""
    lost = specified.filter((pl.col(_YEAR_SPLIT) <= 0) & (pl.col(_PROFILE) > 0))
    for row in lost.iter_rows(named=True):
        recorder.append(_build_lost_demand_event(row))
    _warn_lost_demand(lost)


def _warn_lost_demand(lost: pl.DataFrame) -> None:
    if lost.is_empty():
        return
    names = sorted(
        f"{load}{LOAD_NAME_SEPARATOR}{timeslice}"
        for load, timeslice in lost.select(LOAD_NAME, TIMESLICE).iter_rows()
    )
    log.warning(
        "%s: %d demand profile value(s) above zero fall in a timeslice whose year_split is "
        "zero, so that demand reaches no hour and is left out. Each one: %s",
        OSEMOSYS_TO_SIENNA_PIPELINE,
        lost.height,
        name_a_few(names),
    )


def _build_lost_demand_event(row: dict[str, Any]) -> TranslationEvent:
    return TranslationEvent(
        kind=EventKind.NOT_MAPPED,
        sources=[
            build_osemosys_field(
                DemandParameter.SPECIFIED_DEMAND_PROFILE,
                row[FUEL_NAME],
                row[TIMESLICE],
                row[_PROFILE],
            )
        ],
        note=_LOST_DEMAND_NOTE,
    )


def _build_year_split_table(operations: OperationsYear) -> pl.DataFrame:
    year_split = operations.calendar.year_split
    return pl.DataFrame(
        {TIMESLICE: list(year_split), _YEAR_SPLIT: list(year_split.values())},
        schema={TIMESLICE: pl.Utf8, _YEAR_SPLIT: pl.Float64},
    )


def _express_specified_mw() -> pl.Expr:
    """A timeslice with no share of the year holds no hour, so its demand is zero."""
    hours = pl.col(_YEAR_SPLIT) * HOURS_PER_YEAR
    energy = pl.col(ANNUAL_DEMAND_MWH) * pl.col(_PROFILE).fill_null(0.0)
    return pl.when(hours > 0).then(energy / hours).otherwise(0.0)


def _build_accumulated_series(operations: OperationsYear, demands: pl.DataFrame) -> pl.DataFrame:
    accumulated = demands.filter(
        pl.col(DEMAND_PARAMETER) == DemandParameter.ACCUMULATED_ANNUAL_DEMAND
    )
    flat = accumulated.select(
        LOAD_NAME, (pl.col(ANNUAL_DEMAND_MWH) / HOURS_PER_YEAR).alias(_HOURLY_MW)
    )
    hours = operations.calendar.hours.select(CalendarHourCol.TIMESTAMP)
    return hours.join(flat, how="cross").select(
        pl.col(CalendarHourCol.TIMESTAMP).alias(StagedTimeSeriesCol.SNAPSHOT),
        pl.col(LOAD_NAME).alias(StagedTimeSeriesCol.COMPONENT),
        pl.col(_HOURLY_MW).alias(StagedTimeSeriesCol.VALUE),
    )


def _reshape_to_series(operations: OperationsYear, hourly: pl.DataFrame) -> pl.DataFrame:
    """One row for each hour of the calendar and each load, from one row for each timeslice."""
    hours = operations.calendar.hours.select(CalendarHourCol.TIMESTAMP, CalendarHourCol.TIMESLICE)
    return (
        hours.join(hourly, on=CalendarHourCol.TIMESLICE)
        .select(
            pl.col(CalendarHourCol.TIMESTAMP).alias(StagedTimeSeriesCol.SNAPSHOT),
            pl.col(LOAD_NAME).alias(StagedTimeSeriesCol.COMPONENT),
            pl.col(_HOURLY_MW).alias(StagedTimeSeriesCol.VALUE),
        )
        .cast(pl.Schema(_SERIES_SCHEMA))
    )


def _enrich_series_values(demands: pl.DataFrame, series: pl.DataFrame) -> pl.DataFrame:
    peaks = build_series_peaks(series)
    firsts = build_series_firsts(series)
    return demands.with_columns(
        pl.col(LOAD_NAME)
        .replace_strict(peaks, default=None, return_dtype=pl.Float64)
        .alias(PEAK_MW),
        pl.col(LOAD_NAME)
        .replace_strict(firsts, default=None, return_dtype=pl.Float64)
        .alias(FIRST_MW),
    )


# --- Translation constants ----------------------------------------------------------------


_load_field = partial(build_sienna_field, SiennaComponent.POWER_LOAD)
_load_source = partial(build_sienna_source, SiennaComponent.POWER_LOAD)


def _build_demand_source(old: dict[str, Any]) -> Any:
    return build_osemosys_field(
        old[DEMAND_PARAMETER], old[FUEL_NAME], None, old[ANNUAL_DEMAND], old[ENERGY_UNIT]
    )


def _choose_series_derivation(old: dict[str, Any]) -> str:
    if old[DEMAND_PARAMETER] == DemandParameter.ACCUMULATED_ANNUAL_DEMAND:
        return _ACCUMULATED_DERIVATION
    return _SPECIFIED_DERIVATION


LOAD_NAME_TRANSLATION = Translation(
    exprs=[pl.col(LOAD_NAME).alias(SiennaLoadCol.NAME)],
    make_events=lambda old, new: build_derived(
        [build_osemosys_field(FUEL, old[FUEL_NAME], FUEL, old[FUEL])],
        [_load_field(new[SiennaLoadCol.NAME], SiennaLoadCol.NAME, new[SiennaLoadCol.NAME])],
        _NAME_DERIVATION,
    ),
)

LOAD_BUS_NAME = Translation(
    exprs=[pl.col(AnnotationColumn.LOCATION).alias(SiennaLoadCol.BUS_NAME)],
    make_events=lambda old, new: build_derived(
        [
            build_osemosys_field(
                FUEL,
                old[FUEL_NAME],
                AnnotationColumn.LOCATION,
                old[AnnotationColumn.LOCATION],
            )
        ],
        [_load_field(old[LOAD_NAME], SiennaLoadCol.BUS_NAME, new[SiennaLoadCol.BUS_NAME])],
        _BUS_DERIVATION,
    ),
)

LOAD_SERIES = Translation(
    exprs=[],
    make_events=lambda old, new: build_derived(
        [_build_demand_source(old)],
        [_load_field(old[LOAD_NAME], _SERIES_ATTRIBUTE, None, UNIT_MW)],
        _choose_series_derivation(old),
    ),
)

LOAD_MAX_ACTIVE_POWER = Translation(
    exprs=[pl.col(PEAK_MW).alias(SiennaLoadCol.MAX_ACTIVE_POWER)],
    make_events=lambda old, new: build_derived(
        [_load_source(old[LOAD_NAME], _SERIES_ATTRIBUTE, None, UNIT_MW)],
        [
            _load_field(
                old[LOAD_NAME],
                SiennaLoadCol.MAX_ACTIVE_POWER,
                new[SiennaLoadCol.MAX_ACTIVE_POWER],
                UNIT_MW,
            )
        ],
        _PEAK_DERIVATION,
    ),
)

LOAD_ACTIVE_POWER = Translation(
    exprs=[pl.col(FIRST_MW).alias(SiennaLoadCol.ACTIVE_POWER)],
    make_events=lambda old, new: build_derived(
        [_load_source(old[LOAD_NAME], _SERIES_ATTRIBUTE, None, UNIT_MW)],
        [
            _load_field(
                old[LOAD_NAME],
                SiennaLoadCol.ACTIVE_POWER,
                new[SiennaLoadCol.ACTIVE_POWER],
                UNIT_MW,
            )
        ],
        _FIRST_DERIVATION,
    ),
)

LOAD_TRANSLATIONS: list[Translation] = [
    LOAD_NAME_TRANSLATION,
    row_position_id_translation(
        _load_field, dest_name_col=SiennaLoadCol.NAME, id_col=SiennaLoadCol.ID, note=_ID_NOTE
    ),
    default_translation(
        _load_field,
        name_col=LOAD_NAME,
        dest_col=SiennaLoadCol.AVAILABLE,
        value=True,
        note=_AVAILABLE_NOTE,
    ),
    LOAD_BUS_NAME,
    LOAD_SERIES,
    LOAD_MAX_ACTIVE_POWER,
    LOAD_ACTIVE_POWER,
    default_translation(
        _load_field,
        name_col=LOAD_NAME,
        dest_col=SiennaLoadCol.REACTIVE_POWER,
        value=_NO_REACTIVE_POWER,
        note=_REACTIVE_POWER_NOTE,
        unit=UNIT_MW,
    ),
    default_translation(
        _load_field,
        name_col=LOAD_NAME,
        dest_col=SiennaLoadCol.MAX_REACTIVE_POWER,
        value=_NO_REACTIVE_POWER,
        note=_MAX_REACTIVE_POWER_NOTE,
        unit=UNIT_MW,
    ),
    default_translation(
        _load_field,
        name_col=LOAD_NAME,
        dest_col=SiennaLoadCol.CONFORMITY,
        value=LoadConformity.UNDEFINED.value,
        note=_CONFORMITY_NOTE,
        dtype=LOAD_CONFORMITY_DTYPE,
    ),
]

# The base power reads the max_active_power of the batch before it, so it runs in a batch of
# its own.
LOAD_BASE_POWER_TRANSLATIONS: list[Translation] = [
    Translation(
        exprs=[
            pl.max_horizontal(
                pl.col(SiennaLoadCol.MAX_ACTIVE_POWER), pl.lit(MIN_LOAD_BASE_POWER_MVA)
            ).alias(SiennaLoadCol.BASE_POWER)
        ],
        make_events=lambda old, new: build_derived(
            [
                build_sienna_source(
                    SiennaComponent.POWER_LOAD,
                    old[LOAD_NAME],
                    SiennaLoadCol.MAX_ACTIVE_POWER,
                    old[SiennaLoadCol.MAX_ACTIVE_POWER],
                    UNIT_MW,
                )
            ],
            [
                _load_field(
                    old[LOAD_NAME],
                    SiennaLoadCol.BASE_POWER,
                    new[SiennaLoadCol.BASE_POWER],
                    UNIT_MVA,
                )
            ],
            _BASE_POWER_DERIVATION,
        ),
    )
]
