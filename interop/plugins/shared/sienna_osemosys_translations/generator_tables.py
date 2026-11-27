"""The canonical parameter tables of the generators: the fleet, its flows and its hours.

`ResidualCapacity` is the base power of the generator, in megawatts, because the units of the
written model make one megawatt of capacity run the 8760 megawatt hours of a whole year.

`CapacityFactor` is the share of that fleet that the generator can use in one timeslice. The
share of 1 is the default of the parameter, so a generator that can use its whole fleet in
every hour gets no row.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

import polars as pl

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import (
    UNIT_MW,
    UNIT_PER_UNIT,
    StagedTimeSeriesCol,
)
from interop.plugins.shared.osemosys_canonical.constants import (
    FUEL,
    OPERATING_MODE,
    REGION,
    TECHNOLOGY,
    TIMESLICE,
    VALUE_COL,
    YEAR,
    FlowParameter,
)
from interop.plugins.shared.osemosys_sienna_constants import SupplyParameter
from interop.plugins.shared.sienna_osemosys_translations.constants import (
    NAME_SEPARATOR,
    SIENNA_TO_OSEMOSYS_PIPELINE,
)
from interop.plugins.shared.sienna_osemosys_translations.destination import (
    ParameterRows,
    set_parameter_table,
)
from interop.plugins.shared.sienna_osemosys_translations.events import (
    build_defaulted,
    build_derived,
    build_not_mapped,
    build_osemosys_parameter,
    build_sienna_source,
)
from interop.plugins.shared.sienna_osemosys_translations.generator_columns import (
    BASE_POWER_ATTRIBUTE,
    BASE_POWER_MW,
    CAPACITY_ATTRIBUTE,
    CAPACITY_MW,
    SOURCE_COMPONENT,
)
from interop.plugins.shared.sienna_osemosys_translations.generator_flows import (
    PARAMETER,
    SOURCE_ATTRIBUTE,
    build_generator_flows,
)
from interop.plugins.shared.sienna_osemosys_translations.generators import GeneratorSources
from interop.plugins.shared.warning_text import name_a_few

log = logging.getLogger(__name__)

# The share of its fleet that a generator can use in one timeslice.
SHARE = "share"
# The share that is the default of CapacityFactor, which needs no row of its own.
WHOLE_SHARE = 1.0

_FLOW_PARAMETERS = (
    FlowParameter.INPUT_ACTIVITY_RATIO,
    FlowParameter.OUTPUT_ACTIVITY_RATIO,
)
_CAPACITY_DERIVATION = (
    "the base power of the generator, because one MW of capacity runs the 8760 MWh of a whole "
    "year in the units of the written model"
)
_WHOLE_RATIO_NOTE = (
    "the forward leg divided every value of the technology by its electricity output ratio, "
    "and no Sienna field states that ratio, so the leg writes the ratio as 1"
)
_FLOW_DERIVATION = "the ratio of the record, which already divides by the electricity ratio"
_SHARE_DERIVATION = (
    "the megawatts that the generator can put out in the hour of the timeslice / its base power"
)
_UNRECOVERED_RATIO_NOTE = (
    "the forward leg rated this technology on the output_activity_ratio of the fuel that it "
    "puts out, which no Sienna field states, so the leg writes that ratio as 1 and this value "
    "as the forward leg left it"
)
_UNRECOVERED_RATIO_WARNING = (
    "%s: no Sienna field states the output ratio that the forward leg rated each technology "
    "on, so the leg writes it as 1 for %d technology(ies): %s"
)


def set_generator_tables(
    state: State,
    sources: GeneratorSources,
    hours: pl.DataFrame,
    years: Sequence[int],
    recorder: ScopedRecorder,
) -> None:
    """Write the fleet, the flows and the hourly share of each technology, over every year."""
    if sources.table.height == 0:
        return
    _set_residual_capacity(state, sources.table, years, recorder)
    _set_activity_ratios(state, sources, years, recorder)
    _set_capacity_factor(state, sources, hours, years, recorder)
    _report_unrecovered_ratio(sources.table, recorder)


# --- the fleet ------------------------------------------------------------------


def _set_residual_capacity(
    state: State, generators: pl.DataFrame, years: Sequence[int], recorder: ScopedRecorder
) -> None:
    rows = _list_capacity_rows(generators, years)
    _set_table_with_rows(state, SupplyParameter.RESIDUAL_CAPACITY, rows)
    _record_capacities(generators, recorder)


def _list_capacity_rows(generators: pl.DataFrame, years: Sequence[int]) -> ParameterRows:
    return [
        {
            REGION: row[REGION],
            TECHNOLOGY: row[TECHNOLOGY],
            YEAR: year,
            VALUE_COL: row[BASE_POWER_MW],
        }
        for row in generators.iter_rows(named=True)
        for year in years
    ]


def _record_capacities(generators: pl.DataFrame, recorder: ScopedRecorder) -> None:
    for row in generators.iter_rows(named=True):
        source = _build_source(row, row[BASE_POWER_ATTRIBUTE], row[BASE_POWER_MW], UNIT_MW)
        destination = build_osemosys_parameter(
            SupplyParameter.RESIDUAL_CAPACITY, _build_name(row), row[BASE_POWER_MW], UNIT_MW
        )
        recorder.append(build_derived([source], [destination], _CAPACITY_DERIVATION))


# --- the flows ------------------------------------------------------------------


def _set_activity_ratios(
    state: State, sources: GeneratorSources, years: Sequence[int], recorder: ScopedRecorder
) -> None:
    flows = build_generator_flows(sources)
    for parameter in _FLOW_PARAMETERS:
        stated = flows.filter(pl.col(PARAMETER) == parameter)
        _set_table_with_rows(state, parameter, _list_flow_rows(stated, years))
        _record_flows(stated, parameter, recorder)


def _list_flow_rows(stated: pl.DataFrame, years: Sequence[int]) -> ParameterRows:
    return [
        {
            REGION: row[REGION],
            TECHNOLOGY: row[TECHNOLOGY],
            FUEL: row[FUEL],
            OPERATING_MODE: row[OPERATING_MODE],
            YEAR: year,
            VALUE_COL: row[VALUE_COL],
        }
        for row in stated.iter_rows(named=True)
        for year in years
    ]


def _record_flows(stated: pl.DataFrame, parameter: str, recorder: ScopedRecorder) -> None:
    """One event for each flow, which a record states or which the electricity ratio fixes."""
    for row in stated.iter_rows(named=True):
        destination = build_osemosys_parameter(
            parameter, _build_flow_name(row), row[VALUE_COL], UNIT_PER_UNIT
        )
        if row[SOURCE_ATTRIBUTE] is None:
            recorder.append(build_defaulted([destination], _WHOLE_RATIO_NOTE))
            continue
        source = _build_source(row, row[SOURCE_ATTRIBUTE], row[VALUE_COL], UNIT_PER_UNIT)
        recorder.append(build_derived([source], [destination], _FLOW_DERIVATION))


# --- the hours ------------------------------------------------------------------


def _set_capacity_factor(
    state: State,
    sources: GeneratorSources,
    hours: pl.DataFrame,
    years: Sequence[int],
    recorder: ScopedRecorder,
) -> None:
    if hours.height == 0:
        return
    shares = _build_shares(sources, hours).filter(pl.col(SHARE) != WHOLE_SHARE)
    _set_table_with_rows(state, SupplyParameter.CAPACITY_FACTOR, _list_share_rows(shares, years))
    _record_shares(shares, sources.table, recorder)


def _build_shares(sources: GeneratorSources, hours: pl.DataFrame) -> pl.DataFrame:
    """One row for each technology and each timeslice, with the share of the fleet it can use."""
    shaped = pl.concat([_build_shaped(sources, hours), _build_flat(sources, hours)])
    return shaped.select(REGION, TECHNOLOGY, TIMESLICE, SHARE).collect()


def _build_shaped(sources: GeneratorSources, hours: pl.DataFrame) -> pl.LazyFrame:
    """The share of each hour of a generator that states a series, by the timeslice of that
    hour."""
    scales = sources.table.lazy().select(TECHNOLOGY, REGION, CAPACITY_MW, BASE_POWER_MW)
    share = pl.col(StagedTimeSeriesCol.VALUE) * pl.col(CAPACITY_MW) / pl.col(BASE_POWER_MW)
    return (
        sources.series.join(hours.lazy(), on=StagedTimeSeriesCol.SNAPSHOT, how="inner")
        .join(scales, left_on=StagedTimeSeriesCol.COMPONENT, right_on=TECHNOLOGY, how="inner")
        .select(
            pl.col(REGION),
            pl.col(StagedTimeSeriesCol.COMPONENT).alias(TECHNOLOGY),
            pl.col(TIMESLICE),
            share.alias(SHARE),
        )
    )


def _build_flat(sources: GeneratorSources, hours: pl.DataFrame) -> pl.LazyFrame:
    """The one share that a generator with no series can use in every timeslice of the year."""
    shaped = _list_shaped_generators(sources.series)
    flat = sources.table.lazy().filter(~pl.col(TECHNOLOGY).is_in(shaped))
    share = pl.col(CAPACITY_MW) / pl.col(BASE_POWER_MW)
    return flat.join(hours.lazy().select(TIMESLICE), how="cross").select(
        pl.col(REGION), pl.col(TECHNOLOGY), pl.col(TIMESLICE), share.alias(SHARE)
    )


def _list_shaped_generators(series: pl.LazyFrame) -> list[str]:
    """Each generator that states a series, read as an aggregate of the series column."""
    named = series.select(pl.col(StagedTimeSeriesCol.COMPONENT).unique()).collect()
    return named[StagedTimeSeriesCol.COMPONENT].to_list()


def _list_share_rows(shares: pl.DataFrame, years: Sequence[int]) -> ParameterRows:
    return [
        {
            REGION: row[REGION],
            TECHNOLOGY: row[TECHNOLOGY],
            TIMESLICE: row[TIMESLICE],
            YEAR: year,
            VALUE_COL: row[SHARE],
        }
        for row in shares.iter_rows(named=True)
        for year in years
    ]


def _record_shares(
    shares: pl.DataFrame, generators: pl.DataFrame, recorder: ScopedRecorder
) -> None:
    """One event for each technology, because a model of 8760 hours holds 8760 of its shares."""
    written = shares.select(REGION, TECHNOLOGY).unique()
    for row in generators.join(written, on=[REGION, TECHNOLOGY], how="semi").iter_rows(named=True):
        source = _build_source(row, row[CAPACITY_ATTRIBUTE], row[CAPACITY_MW], UNIT_MW)
        destination = build_osemosys_parameter(
            SupplyParameter.CAPACITY_FACTOR, _build_name(row), None, UNIT_PER_UNIT
        )
        recorder.append(build_derived([source], [destination], _SHARE_DERIVATION))


# --- what the electricity output ratio took with it -----------------------------


def _report_unrecovered_ratio(generators: pl.DataFrame, recorder: ScopedRecorder) -> None:
    """One event for each value that the ratio scaled, because the leg cannot undo it."""
    for row in generators.iter_rows(named=True):
        source = _build_source(row, row[BASE_POWER_ATTRIBUTE], row[BASE_POWER_MW], UNIT_MW)
        recorder.append(build_not_mapped([source], _UNRECOVERED_RATIO_NOTE))
    names = generators[TECHNOLOGY].to_list()
    log.warning(
        _UNRECOVERED_RATIO_WARNING, SIENNA_TO_OSEMOSYS_PIPELINE, len(names), name_a_few(names)
    )


# --- the tables and the names they take -----------------------------------------


def _set_table_with_rows(state: State, parameter: str, rows: ParameterRows) -> None:
    if rows:
        set_parameter_table(state, parameter, rows)


def _build_source(row: dict[str, Any], attribute: str, value: Any, unit: str) -> Any:
    return build_sienna_source(
        row[SOURCE_COMPONENT], row[TECHNOLOGY], attribute, value=value, unit=unit
    )


def _build_name(row: dict[str, Any]) -> str:
    """A technology is keyed by its region, so an event names it `<region>/<technology>`."""
    return f"{row[REGION]}{NAME_SEPARATOR}{row[TECHNOLOGY]}"


def _build_flow_name(row: dict[str, Any]) -> str:
    """A flow is keyed by its fuel and its mode too, so an event names all four."""
    parts = (row[REGION], row[TECHNOLOGY], row[FUEL], row[OPERATING_MODE])
    return NAME_SEPARATOR.join(parts)
