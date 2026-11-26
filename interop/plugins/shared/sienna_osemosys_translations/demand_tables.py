"""The canonical parameter tables of the demands.

A timeslice covers one hour, so the energy that a load asks for in one timeslice is the
megawatts of its hour times the hours of the year that the timeslice covers. The annual demand
is the sum over the timeslices, and the share that OSeMOSYS spreads over the timeslices is the
energy of one timeslice divided by that sum. So the shares of one fuel sum to 1.

An accumulated annual demand states the energy of the year alone, because OSeMOSYS lets the
model meet it in any timeslice.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import polars as pl

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import (
    UNIT_MW,
    UNIT_MWH,
    Framework,
    StagedTimeSeriesCol,
)
from interop.plugins.shared.osemosys_canonical.constants import (
    FUEL,
    REGION,
    TIMESLICE,
    VALUE_COL,
    YEAR,
)
from interop.plugins.shared.osemosys_sienna_constants import DemandParameter
from interop.plugins.shared.sienna_osemosys_translations.constants import (
    NAME_SEPARATOR,
    SIENNA_TO_OSEMOSYS_PIPELINE,
)
from interop.plugins.shared.sienna_osemosys_translations.demands import (
    FLAT_MW,
    LOAD_NAME,
    LOAD_PARAMETER,
    SERIES_SCALE,
    SOURCE_ATTRIBUTE,
    SOURCE_COMPONENT,
    DemandSources,
)
from interop.plugins.shared.sienna_osemosys_translations.destination import (
    ParameterRows,
    set_parameter_table,
)
from interop.plugins.shared.sienna_osemosys_translations.events import (
    build_derived,
    build_osemosys_parameter,
    build_sienna_source,
)
from interop.plugins.shared.sienna_osemosys_translations.hours import TIMESLICE_HOURS
from interop.plugins.shared.translation_runner import SkipReport, SkipRule, drop_skipped
from interop.ports.outbound.reporting import SourceField

SPECIFIED_DEMAND_PROFILE = DemandParameter.SPECIFIED_DEMAND_PROFILE.value

# The megawatts of one load in one timeslice, and the energy that they state over the year.
_LOAD_MW = "load_mw"
_LOAD_ENERGY = "load_energy"
# The energy of the whole year that one demand asks for, in MWh.
_ANNUAL_ENERGY = "annual_energy"
# The share of that energy that falls in one timeslice.
_SHARE = "share"

# The columns that one OSeMOSYS demand is keyed by.
_KEYS = (REGION, FUEL, LOAD_PARAMETER)
# One demand, as the loads behind it are looked up: its region, its fuel and its parameter.
DemandKey = tuple[str, str, str]

_ANNUAL_DERIVATION = (
    "the sum over the timeslices of the megawatts of the hour of each timeslice x the hours "
    "of the year that the timeslice covers"
)
_PROFILE_DERIVATION = "the energy of one timeslice / the energy of the whole year"
_NO_ENERGY_NOTE = (
    "the load asks for no energy over the timeslices of the year, so it spreads over no "
    "demand profile and is left out"
)
_ANNUAL_PARAMETERS = (
    DemandParameter.SPECIFIED_ANNUAL_DEMAND,
    DemandParameter.ACCUMULATED_ANNUAL_DEMAND,
)


def set_demand_tables(
    state: State,
    sources: DemandSources,
    hours: pl.DataFrame,
    years: Sequence[int],
    recorder: ScopedRecorder,
) -> None:
    """Write the demand of each fuel, over the years of the model."""
    if sources.table.height == 0 or hours.height == 0:
        return
    energy = _build_timeslice_energy(sources, hours)
    kept = _drop_quiet_loads(sources.table, energy, recorder)
    demands = _build_demands(energy, kept)
    annual = demands.group_by(*_KEYS).agg(pl.col(_LOAD_ENERGY).sum().alias(_ANNUAL_ENERGY))
    behind = _build_loads_behind(kept)
    _set_annual_tables(state, annual, years, recorder, behind)
    _set_profile_table(state, demands, annual, years, recorder, behind)


# --- the energy of each load in each timeslice ----------------------------------


def _build_timeslice_energy(sources: DemandSources, hours: pl.DataFrame) -> pl.LazyFrame:
    """One row for each load and each timeslice, with the energy that the load asks for."""
    shaped = pl.concat([_build_shaped(sources, hours), _build_flat(sources, hours)])
    return shaped.with_columns((pl.col(_LOAD_MW) * pl.col(TIMESLICE_HOURS)).alias(_LOAD_ENERGY))


def _build_shaped(sources: DemandSources, hours: pl.DataFrame) -> pl.LazyFrame:
    """The megawatts of each hour of a load that states a series, by the timeslice of that
    hour."""
    scales = sources.table.lazy().select(LOAD_NAME, SERIES_SCALE)
    return (
        sources.series.join(hours.lazy(), on=StagedTimeSeriesCol.SNAPSHOT, how="inner")
        .join(scales, left_on=StagedTimeSeriesCol.COMPONENT, right_on=LOAD_NAME, how="inner")
        .select(
            pl.col(StagedTimeSeriesCol.COMPONENT).alias(LOAD_NAME),
            pl.col(TIMESLICE),
            pl.col(TIMESLICE_HOURS),
            (pl.col(StagedTimeSeriesCol.VALUE) * pl.col(SERIES_SCALE)).alias(_LOAD_MW),
        )
    )


def _build_flat(sources: DemandSources, hours: pl.DataFrame) -> pl.LazyFrame:
    """The one value that a load with no series asks for, in every timeslice of the year."""
    shaped = _list_shaped_loads(sources.series)
    flat = sources.table.lazy().filter(~pl.col(LOAD_NAME).is_in(shaped))
    return flat.join(hours.lazy(), how="cross").select(
        pl.col(LOAD_NAME),
        pl.col(TIMESLICE),
        pl.col(TIMESLICE_HOURS),
        pl.col(FLAT_MW).alias(_LOAD_MW),
    )


def _list_shaped_loads(series: pl.LazyFrame) -> list[str]:
    """Each load that states a series, read as an aggregate of the series column."""
    named = series.select(pl.col(StagedTimeSeriesCol.COMPONENT).unique()).collect()
    return named[StagedTimeSeriesCol.COMPONENT].to_list()


# --- the loads that reach no demand ---------------------------------------------


def _drop_quiet_loads(
    loads: pl.DataFrame, energy: pl.LazyFrame, recorder: ScopedRecorder
) -> pl.DataFrame:
    """A load of no energy spreads over no profile, so the leg reports it and leaves it out."""
    by_load = (
        energy.group_by(LOAD_NAME).agg(pl.col(_LOAD_ENERGY).sum().alias(_ANNUAL_ENERGY)).collect()
    )
    named = loads.join(by_load, on=LOAD_NAME, how="left")
    kept = [
        _drop_quiet_part(part, str(component), recorder)
        for (component,), part in named.group_by(SOURCE_COMPONENT, maintain_order=True)
    ]
    return pl.concat(kept) if kept else named


def _drop_quiet_part(part: pl.DataFrame, component: str, recorder: ScopedRecorder) -> pl.DataFrame:
    """One Sienna component type at a time, so the report names the type of each load."""
    rule = SkipRule(pl.col(_ANNUAL_ENERGY) > 0, _build_quiet_report(component))
    return drop_skipped(part, [rule], recorder)


def _build_quiet_report(component: str) -> SkipReport:
    return SkipReport(
        pipeline=SIENNA_TO_OSEMOSYS_PIPELINE,
        framework=Framework.SIENNA,
        component=component,
        name_col=LOAD_NAME,
        reason="ask for no energy in any hour of the calendar",
        counted_noun="load(s)",
        note=_NO_ENERGY_NOTE,
    )


# --- the demand of each fuel ----------------------------------------------------


def _build_demands(energy: pl.LazyFrame, kept: pl.DataFrame) -> pl.DataFrame:
    """One row for each demand and each timeslice, with the energy of every load behind it."""
    keyed = kept.select(LOAD_NAME, *_KEYS)
    return (
        energy.join(keyed.lazy(), on=LOAD_NAME, how="inner")
        .group_by(*_KEYS, TIMESLICE)
        .agg(pl.col(_LOAD_ENERGY).sum().alias(_LOAD_ENERGY))
        .collect()
    )


def _build_loads_behind(kept: pl.DataFrame) -> dict[DemandKey, list[SourceField]]:
    """The Sienna value that each demand reads, for each load that states part of it."""
    behind: dict[DemandKey, list[SourceField]] = {}
    for row in kept.sort(LOAD_NAME).iter_rows(named=True):
        key = (row[REGION], row[FUEL], row[LOAD_PARAMETER])
        behind.setdefault(key, []).append(_build_load_source(row))
    return behind


def _build_load_source(row: dict[str, Any]) -> SourceField:
    return build_sienna_source(
        row[SOURCE_COMPONENT], row[LOAD_NAME], row[SOURCE_ATTRIBUTE], unit=UNIT_MW
    )


# --- the tables and their events ------------------------------------------------


def _set_annual_tables(
    state: State,
    annual: pl.DataFrame,
    years: Sequence[int],
    recorder: ScopedRecorder,
    behind: dict[DemandKey, list[SourceField]],
) -> None:
    for parameter in _ANNUAL_PARAMETERS:
        stated = annual.filter(pl.col(LOAD_PARAMETER) == parameter.value)
        _set_table_with_rows(state, parameter.value, _list_annual_rows(stated, years))
        _record_demands(stated, parameter.value, _ANNUAL_DERIVATION, recorder, behind)


def _list_annual_rows(stated: pl.DataFrame, years: Sequence[int]) -> ParameterRows:
    return [
        {REGION: row[REGION], FUEL: row[FUEL], YEAR: year, VALUE_COL: row[_ANNUAL_ENERGY]}
        for row in stated.iter_rows(named=True)
        for year in years
    ]


def _set_profile_table(
    state: State,
    demands: pl.DataFrame,
    annual: pl.DataFrame,
    years: Sequence[int],
    recorder: ScopedRecorder,
    behind: dict[DemandKey, list[SourceField]],
) -> None:
    """The share of the annual demand that each timeslice of a specified demand holds."""
    specified = pl.col(LOAD_PARAMETER) == DemandParameter.SPECIFIED_ANNUAL_DEMAND.value
    shares = _build_shares(demands.filter(specified), annual.filter(specified))
    _set_table_with_rows(state, SPECIFIED_DEMAND_PROFILE, _list_profile_rows(shares, years))
    _record_demands(
        annual.filter(specified),
        SPECIFIED_DEMAND_PROFILE,
        _PROFILE_DERIVATION,
        recorder,
        behind,
    )


def _build_shares(demands: pl.DataFrame, annual: pl.DataFrame) -> pl.DataFrame:
    totals = annual.select(*_KEYS, _ANNUAL_ENERGY)
    return demands.join(totals, on=list(_KEYS), how="inner").with_columns(
        (pl.col(_LOAD_ENERGY) / pl.col(_ANNUAL_ENERGY)).alias(_SHARE)
    )


def _list_profile_rows(shares: pl.DataFrame, years: Sequence[int]) -> ParameterRows:
    return [
        {
            REGION: row[REGION],
            FUEL: row[FUEL],
            TIMESLICE: row[TIMESLICE],
            YEAR: year,
            VALUE_COL: row[_SHARE],
        }
        for row in shares.iter_rows(named=True)
        for year in years
    ]


def _set_table_with_rows(state: State, parameter: str, rows: ParameterRows) -> None:
    if rows:
        set_parameter_table(state, parameter, rows)


def _record_demands(
    stated: pl.DataFrame,
    parameter: str,
    derivation: str,
    recorder: ScopedRecorder,
    behind: dict[DemandKey, list[SourceField]],
) -> None:
    """One event for each demand, because a model of 8760 hours holds 8760 shares of one."""
    unit = None if parameter == SPECIFIED_DEMAND_PROFILE else UNIT_MWH
    for row in stated.iter_rows(named=True):
        key = (row[REGION], row[FUEL], row[LOAD_PARAMETER])
        value = None if parameter == SPECIFIED_DEMAND_PROFILE else row[_ANNUAL_ENERGY]
        destination = build_osemosys_parameter(parameter, _build_demand_name(row), value, unit)
        recorder.append(build_derived(behind.get(key, []), [destination], derivation))


def _build_demand_name(row: dict[str, Any]) -> str:
    """A demand is keyed by its region and its fuel, so an event names it `<region>/<fuel>`."""
    return f"{row[REGION]}{NAME_SEPARATOR}{row[FUEL]}"
