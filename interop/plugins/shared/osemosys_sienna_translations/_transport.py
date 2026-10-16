"""OSeMOSYS AggregateTransportTechnology -> Sienna TwoTerminalGenericHVDCLine.

At the operations mode, a transport technology takes in electricity at one location and puts
it out at another. The line runs from the bus of the first to the bus of the second, in that
direction only. It sends at most its residual capacity in MW × its availability factor × its
electricity input ratio, and it loses the share `1 - output ratio / input ratio` of what it
sends. The values of the other modes, for example the flow back, are reported and left out.
"""

from __future__ import annotations

import logging
from typing import NamedTuple

import polars as pl

from interop.core.extensions import ControllableLineExtension
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.osemosys_canonical.constants import (
    FUEL,
    OPERATING_MODE,
    OSEMOSYS_FRAMEWORK,
    REGION,
    TECHNOLOGY,
    VALUE_COL,
    AnnotationColumn,
    FlowParameter,
    TechnologyKind,
)
from interop.plugins.shared.osemosys_sienna_constants import (
    OSEMOSYS_TO_SIENNA_PIPELINE,
    SupplyParameter,
)
from interop.plugins.shared.osemosys_sienna_translations._buses import read_electricity_fuels
from interop.plugins.shared.osemosys_sienna_translations._canonical import (
    read_annotations,
    read_mode_parameter,
    read_parameter_with_defaults,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_columns import (
    RESIDUAL_CAPACITY,
    TECHNOLOGY_NAME,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_costs import (
    OTHER_MODE_VALUES,
    enrich_other_modes,
)
from interop.plugins.shared.osemosys_sienna_translations._names import (
    express_component_name,
    express_report_name,
)
from interop.plugins.shared.osemosys_sienna_translations._operations import OperationsYear
from interop.plugins.shared.osemosys_sienna_translations._technologies import (
    enrich_residual_capacity,
    list_bus_names,
)
from interop.plugins.shared.osemosys_sienna_translations._transport_columns import (
    AVAILABILITY,
    CAPACITY_MW,
    COST,
    COST_MWH,
    FROM_LOCATION,
    FROM_LOCATIONS,
    INPUT_RATIO,
    LINE_NAME,
    LOSS,
    OUTPUT_RATIO,
    RECEIVED_MW,
    SENT_MW,
    TO_LOCATION,
    TO_LOCATIONS,
)
from interop.plugins.shared.osemosys_sienna_translations._units import express_converted
from interop.plugins.shared.translation_runner import (
    SkippedNames,
    SkipReport,
    SkipRule,
    filter_component,
)
from interop.plugins.shared.warning_text import name_a_few

log = logging.getLogger(__name__)

_KEYS = [REGION, TECHNOLOGY]
_COUNTED_NOUN = "transport technology(ies)"
_LISTED = SkippedNames(column=TECHNOLOGY_NAME, label="Technologies")
_ONE_LOCATION = 1
_WHOLE_CAPACITY = 1.0
_NO_COST = 0.0


class _EndColumns(NamedTuple):
    """The columns that one end of a transport technology fills."""

    location: str
    locations: str
    ratio: str


_FROM = _EndColumns(FROM_LOCATION, FROM_LOCATIONS, INPUT_RATIO)
_TO = _EndColumns(TO_LOCATION, TO_LOCATIONS, OUTPUT_RATIO)


def _build_skip(
    reason: str, note: str, attribute_col: str | None = None, attribute_name: str | None = None
) -> SkipReport:
    return SkipReport(
        pipeline=OSEMOSYS_TO_SIENNA_PIPELINE,
        framework=OSEMOSYS_FRAMEWORK,
        component=TECHNOLOGY,
        name_col=TECHNOLOGY_NAME,
        reason=reason,
        counted_noun=_COUNTED_NOUN,
        note=note,
        listed=_LISTED,
        attribute_col=attribute_col,
        attribute_name=attribute_name,
    )


NO_CAPACITY_SKIP = _build_skip(
    "have no residual capacity in the operations year",
    "the fleet of the operations year is its residual capacity, which holds none of it",
    RESIDUAL_CAPACITY,
)
NO_ENDS_SKIP = _build_skip(
    "do not take in electricity at one location and put it out at another at the operations mode",
    "a line needs one location where the technology takes in electricity and another where it "
    "puts electricity out, at the operations mode",
    AnnotationColumn.LOCATION,
)
NO_BUS_SKIP = _build_skip(
    "have an end that holds no bus",
    "no bus is at one end of the technology, so no line can join the two",
    AnnotationColumn.LOCATION,
)


def read_transport_ends(state: State, year: int, mode: str) -> pl.DataFrame:
    """Where each technology takes in and puts out electricity at the mode, with the ratios.

    `from_locations` and `to_locations` count the locations of each end; a line needs one each.
    """
    fuels = read_electricity_fuels(state).select(REGION, FUEL, AnnotationColumn.LOCATION)
    ends = [
        _read_end(state, year, mode, parameter, fuels, columns)
        for parameter, columns in (
            (FlowParameter.INPUT_ACTIVITY_RATIO, _FROM),
            (FlowParameter.OUTPUT_ACTIVITY_RATIO, _TO),
        )
    ]
    return ends[0].join(ends[1], on=_KEYS, how="full", coalesce=True)


def build_transport_source(
    state: State, operations: OperationsYear, recorder: ScopedRecorder
) -> pl.DataFrame:
    """One row for each transport technology that the operations system holds as a line."""
    lines = _read_lines(state, operations)
    for rule in _build_skip_rules(list_bus_names(state)):
        lines, _ = filter_component(lines, rule.keep, rule.report, recorder)
    if lines.height == 0:
        return lines
    lines = _enrich_ratings(state, operations, lines)
    lines = _enrich_costs(state, operations, lines)
    return enrich_other_modes(state, operations, lines).sort(LINE_NAME)


def build_line_extensions(lines: pl.DataFrame) -> list[ControllableLineExtension]:
    """The cost of each MWh that a line sends, which a Sienna line prices nowhere."""
    return [
        ControllableLineExtension(name=row[LINE_NAME], marginal_cost=row[COST_MWH])
        for row in lines.filter(pl.col(COST_MWH) != _NO_COST).iter_rows(named=True)
    ]


def warn_one_way_lines(lines: pl.DataFrame) -> None:
    """Name the lines whose technology states flows at another mode, which the line drops."""
    named = lines.filter(pl.col(OTHER_MODE_VALUES).list.len() > 0)[TECHNOLOGY_NAME].to_list()
    if named:
        log.warning(
            "%s: %d transport technology(ies) state values at another operating mode, for "
            "example a flow back, and each line runs at the operations mode only. "
            "Technologies: %s",
            OSEMOSYS_TO_SIENNA_PIPELINE,
            len(named),
            name_a_few(named),
        )


def _read_end(
    state: State,
    year: int,
    mode: str,
    parameter: str,
    fuels: pl.DataFrame,
    columns: _EndColumns,
) -> pl.DataFrame:
    location = pl.col(AnnotationColumn.LOCATION)
    return (
        read_mode_parameter(state, parameter, year, mode)
        .filter(pl.col(VALUE_COL) > 0)
        .join(fuels.filter(location.is_not_null()), on=[REGION, FUEL])
        .group_by(_KEYS)
        .agg(
            location.min().alias(columns.location),
            location.n_unique().alias(columns.locations),
            pl.col(VALUE_COL).cast(pl.Float64).sum().alias(columns.ratio),
        )
    )


def _read_lines(state: State, operations: OperationsYear) -> pl.DataFrame:
    """Every transport technology, so that each Sienna name knows of a clash in another region."""
    lines = (
        read_annotations(state, TECHNOLOGY)
        .filter(pl.col(AnnotationColumn.KIND) == TechnologyKind.AGGREGATE_TRANSPORT_TECHNOLOGY)
        .with_columns(
            express_component_name(TECHNOLOGY).alias(LINE_NAME),
            express_report_name(TECHNOLOGY).alias(TECHNOLOGY_NAME),
        )
    )
    lines = enrich_residual_capacity(state, operations.year, lines)
    ends = read_transport_ends(state, operations.year, operations.mode)
    return lines.join(ends, on=_KEYS, how="left")


def _build_skip_rules(bus_names: list[str]) -> list[SkipRule]:
    has_ends = (
        (pl.col(FROM_LOCATIONS) == _ONE_LOCATION)
        & (pl.col(TO_LOCATIONS) == _ONE_LOCATION)
        & (pl.col(FROM_LOCATION) != pl.col(TO_LOCATION))
    )
    has_buses = pl.col(FROM_LOCATION).is_in(bus_names) & pl.col(TO_LOCATION).is_in(bus_names)
    return [
        SkipRule(pl.col(RESIDUAL_CAPACITY) > 0, NO_CAPACITY_SKIP),
        SkipRule(has_ends, NO_ENDS_SKIP),
        SkipRule(has_buses, NO_BUS_SKIP),
    ]


def _enrich_ratings(state: State, operations: OperationsYear, lines: pl.DataFrame) -> pl.DataFrame:
    stated = read_parameter_with_defaults(
        state, SupplyParameter.AVAILABILITY_FACTOR, operations.year, lines.select(_KEYS)
    ).select(*_KEYS, pl.col(VALUE_COL).fill_null(_WHOLE_CAPACITY).alias(AVAILABILITY))
    rated = lines.join(stated, on=_KEYS).with_columns(
        (
            operations.units.convert_capacity_to_mw(pl.col(RESIDUAL_CAPACITY))
            * pl.col(AVAILABILITY)
        ).alias(CAPACITY_MW)
    )
    return rated.with_columns(
        (pl.col(CAPACITY_MW) * pl.col(INPUT_RATIO)).alias(SENT_MW),
        (pl.col(CAPACITY_MW) * pl.col(OUTPUT_RATIO)).alias(RECEIVED_MW),
        (1.0 - pl.col(OUTPUT_RATIO) / pl.col(INPUT_RATIO)).alias(LOSS),
    )


def _enrich_costs(state: State, operations: OperationsYear, lines: pl.DataFrame) -> pl.DataFrame:
    """The cost of each MWh that the line sends, from the cost of each unit of activity."""
    keys = lines.select(*_KEYS, pl.lit(operations.mode).alias(OPERATING_MODE))
    stated = read_parameter_with_defaults(
        state, SupplyParameter.VARIABLE_OPERATION_COST, operations.year, keys
    ).select(*_KEYS, pl.col(VALUE_COL).cast(pl.Float64).fill_null(_NO_COST).alias(COST))
    table = lines.join(stated, on=_KEYS)
    convert = operations.units.convert_cost_per_energy_to_dollars_per_mwh
    per_sent = express_converted(table, COST, convert) / pl.col(INPUT_RATIO)
    return table.with_columns(per_sent.alias(COST_MWH))
