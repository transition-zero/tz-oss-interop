"""OSeMOSYS AggregateTransportTechnology -> Sienna TwoTerminalGenericHVDCLine.

At the operations mode, a transport technology takes in electricity at one location and puts
it out at another. The line runs from the bus of the first to the bus of the second, in that
direction. It sends at most its residual capacity in MW × its availability factor × its
electricity input ratio, and it loses the share `1 - output ratio / input ratio` of what it
sends. When another mode takes electricity in at the second location and puts it out at the
first, the line also flows back, within the limits of that mode. A mode that puts out
electricity at one end and takes in none is an import, which becomes a generator. The values of
every other mode, and each value that a Sienna line has no field for, go to the line record of
extensions.json.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, NamedTuple

import polars as pl

from interop.core.extensions import (
    CompanionSeriesCol,
    ControllableLineCompanionCol,
    ControllableLineExtension,
    ExtensionKind,
    companion_filename,
)
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
    TECHNOLOGIES_LABEL,
    WHOLE_CAPACITY,
    SupplyParameter,
)
from interop.plugins.shared.osemosys_sienna_translations._activity_limits import (
    LOWER_BOUND,
    UPPER_BOUND,
    build_yearly_limits,
    enrich_activity_limits,
    set_bounds_persisted,
)
from interop.plugins.shared.osemosys_sienna_translations._buses import read_electricity_fuels
from interop.plugins.shared.osemosys_sienna_translations._canonical import (
    read_annotations,
    read_parameter,
)
from interop.plugins.shared.osemosys_sienna_translations._capacity_factors import (
    HAS_CAPACITY_FACTORS,
    build_capacity_factor_series,
    express_has_capacity_factors,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_columns import (
    RESIDUAL_CAPACITY,
    SIENNA_TYPE,
    TECHNOLOGY_NAME,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_costs import (
    OTHER_MODE_VALUES,
    PARAMETER,
    enrich_other_mode_values,
)
from interop.plugins.shared.osemosys_sienna_translations._names import (
    express_component_name,
    express_report_name,
)
from interop.plugins.shared.osemosys_sienna_translations._operating_modes import (
    LINK_RUN_PARAMETERS,
    build_operating_mode_field,
    build_operating_modes,
    set_mode_bounds_persisted,
)
from interop.plugins.shared.osemosys_sienna_translations._operations import OperationsYear
from interop.plugins.shared.osemosys_sienna_translations._technologies import (
    AVAILABILITY_FACTOR,
    VARIABLE_COST,
    enrich_residual_capacity,
    read_availability_factors,
    read_variable_costs,
)
from interop.plugins.shared.osemosys_sienna_translations._technology_values import (
    LINK_VALUES,
    RATED_PARAMETERS,
    RATING_RATIO,
    ValueOwners,
    build_value_fields,
    enrich_technology_values,
    set_applied_rows,
    set_values_persisted,
)
from interop.plugins.shared.osemosys_sienna_translations._transport_columns import (
    AVAILABILITY,
    CAPACITY_MW,
    COST,
    COST_MWH,
    FROM_FUEL,
    FROM_LOCATION,
    FROM_LOCATIONS,
    INPUT_RATIO,
    LINE_NAME,
    LOSS,
    OUTPUT_RATIO,
    RECEIVED_MW,
    REVERSE_INPUT_RATIO,
    REVERSE_MODE,
    REVERSE_OUTPUT_RATIO,
    REVERSE_RECEIVED_MW,
    REVERSE_SENT_MW,
    SENT_MW,
    TO_FUEL,
    TO_LOCATION,
    TO_LOCATIONS,
)
from interop.plugins.shared.osemosys_sienna_translations._transport_imports import (
    build_imports_source,
    enrich_import_flows,
    is_held_by_import_mode,
    read_import_modes,
)
from interop.plugins.shared.osemosys_sienna_translations._units import express_converted
from interop.plugins.shared.sienna_constants import SiennaComponent
from interop.plugins.shared.translation_runner import (
    SkippedNames,
    SkipReport,
    SkipRule,
    filter_component,
)
from interop.plugins.shared.warning_text import name_a_few

log = logging.getLogger(__name__)

_KEYS = [REGION, TECHNOLOGY]
_MODE_KEYS = [REGION, TECHNOLOGY, OPERATING_MODE]
_FLOWS = (FlowParameter.INPUT_ACTIVITY_RATIO, FlowParameter.OUTPUT_ACTIVITY_RATIO)
_COUNTED_NOUN = "transport technology(ies)"
_LISTED = SkippedNames(column=TECHNOLOGY_NAME, label=TECHNOLOGIES_LABEL)
_ONE_LOCATION = 1
_NO_COST = 0.0
_NO_FLOW = 0.0
_SERIES_FILE = companion_filename(ExtensionKind.CONTROLLABLE_LINE)

# The records of the lines, and the columns that name each line and its technology.
LINE_OWNERS = ValueOwners(ExtensionKind.CONTROLLABLE_LINE, LINE_NAME, TECHNOLOGY_NAME, SIENNA_TYPE)
# The rows of a line technology that the line applies, beside those its record keeps.
_APPLIED_PARAMETERS = (*RATED_PARAMETERS, SupplyParameter.CAPACITY_FACTOR)


@dataclass(frozen=True)
class TransportSources:
    """One row for each line, the capacity factor of each hour of each line that has one, and
    one row for each import mode.
    """

    table: pl.DataFrame
    series: pl.DataFrame
    imports: pl.DataFrame


class _EndColumns(NamedTuple):
    """The columns that one end of a transport technology fills."""

    location: str
    locations: str
    fuel: str
    ratio: str


_FROM = _EndColumns(FROM_LOCATION, FROM_LOCATIONS, FROM_FUEL, INPUT_RATIO)
_TO = _EndColumns(TO_LOCATION, TO_LOCATIONS, TO_FUEL, OUTPUT_RATIO)


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


def read_transport_ends(state: State, year: int, mode: str) -> pl.DataFrame:
    """Where each technology takes in and puts out electricity at the mode, with the ratios.

    `from_locations` and `to_locations` count the locations of each end; a line needs one each.
    """
    ends = _read_mode_ends(state, year)
    return ends.filter(pl.col(OPERATING_MODE) == mode).drop(OPERATING_MODE)


def build_transport_source(
    state: State, operations: OperationsYear, recorder: ScopedRecorder
) -> TransportSources:
    """One row for each transport technology that the operations system holds as a line.

    Each end of a line is the location of an electricity fuel, which always has a bus.
    """
    lines = _read_lines(state, operations)
    for rule in _SKIP_RULES:
        lines, _ = filter_component(lines, rule.keep, rule.report, recorder)
    if lines.height == 0:
        return TransportSources(lines, pl.DataFrame(), pl.DataFrame())
    imports = read_import_modes(state, operations, lines)
    lines = enrich_import_flows(lines, imports)
    lines = _enrich_reverse_modes(state, operations, lines)
    lines = _enrich_ratings(state, operations, lines)
    lines = _enrich_costs(state, operations, lines)
    lines = enrich_other_mode_values(state, operations, lines)
    lines = _enrich_extension_values(state, operations, lines)
    series = build_capacity_factor_series(
        state,
        operations,
        lines.select(REGION, TECHNOLOGY, pl.col(LINE_NAME).alias(CompanionSeriesCol.NAME)),
        ControllableLineCompanionCol.P_MAX_PU,
    )
    lines = lines.with_columns(
        express_has_capacity_factors(series, LINE_NAME).alias(HAS_CAPACITY_FACTORS)
    )
    imports = build_imports_source(state, operations, imports, lines)
    return TransportSources(lines.sort(LINE_NAME), series, imports)


def build_line_extensions(lines: pl.DataFrame) -> list[ControllableLineExtension]:
    """What each line states that a Sienna line has no field for, for each line with any."""
    records = [_build_extension(row) for row in lines.iter_rows(named=True)]
    return [record for record in records if record.has_any_value()]


def has_series(line: dict[str, Any]) -> bool:
    """Whether the companion parquet holds the capacity factor of each hour of the line."""
    return bool(line[HAS_CAPACITY_FACTORS])


def set_line_values_persisted(state: State, lines: pl.DataFrame) -> None:
    """Note the rows of each line technology that the lines apply or keep."""
    set_values_persisted(state, LINE_OWNERS, lines, LINK_VALUES)
    set_mode_bounds_persisted(state, LINE_OWNERS, lines)
    set_bounds_persisted(state, LINE_OWNERS, lines)
    set_applied_rows(state, LINE_OWNERS, lines, _APPLIED_PARAMETERS)


def _build_extension(row: dict[str, Any]) -> ControllableLineExtension:
    return ControllableLineExtension(
        name=row[LINE_NAME],
        marginal_cost=row[COST_MWH] if row[COST_MWH] != _NO_COST else None,
        p_max_pu=row[AVAILABILITY] if row[AVAILABILITY] != WHOLE_CAPACITY else None,
        p_max_pu_series=_SERIES_FILE if has_series(row) else None,
        operating_modes=build_operating_mode_field(row),
        e_sum_min=build_yearly_limits(row[LOWER_BOUND.column]),
        e_sum_max=build_yearly_limits(row[UPPER_BOUND.column]),
        **build_value_fields(row, LINK_VALUES),
    )


def _enrich_extension_values(
    state: State, operations: OperationsYear, lines: pl.DataFrame
) -> pl.DataFrame:
    """The values that a line rates on the electricity that it sends, and its other modes."""
    rated = lines.with_columns(
        pl.col(INPUT_RATIO).alias(RATING_RATIO),
        pl.lit(SiennaComponent.TWO_TERMINAL_GENERIC_HVDC_LINE.value).alias(SIENNA_TYPE),
    )
    table = enrich_technology_values(state, operations, rated, LINK_VALUES)
    held = lines.select(REGION, TECHNOLOGY, pl.lit(operations.mode).alias(OPERATING_MODE))
    bounds = enrich_activity_limits(state, operations, held, FlowParameter.INPUT_ACTIVITY_RATIO)
    table = table.join(bounds.drop(OPERATING_MODE), on=_KEYS, how="left")
    modes = build_operating_modes(state, operations, held, LINK_RUN_PARAMETERS)
    return modes.enrich(table)


def warn_one_way_lines(lines: pl.DataFrame) -> None:
    """Name the lines whose technology states values at a mode that is neither the flow back
    nor an import.
    """
    named = [
        line[TECHNOLOGY_NAME] for line in lines.iter_rows(named=True) if _list_lost_values(line)
    ]
    if named:
        log.warning(
            "%s: %d transport technology(ies) state values at an operating mode that is neither "
            "the flow back nor an import, and the line does not run them; extensions.json holds "
            "them. Technologies: %s",
            OSEMOSYS_TO_SIENNA_PIPELINE,
            len(named),
            name_a_few(named),
        )


def _list_lost_values(line: dict[str, Any]) -> list[dict[str, Any]]:
    """The values of the other modes that neither the line nor an import generator runs.

    The flows of the reverse mode are the flow back, and a cost of the reverse mode that is
    the cost of the operations mode is the one cost of the line.
    """
    return [
        value
        for value in line[OTHER_MODE_VALUES] or []
        if not _is_held_by_reverse_mode(line, value) and not is_held_by_import_mode(line, value)
    ]


def _is_held_by_reverse_mode(line: dict[str, Any], value: dict[str, Any]) -> bool:
    if value[OPERATING_MODE] != line[REVERSE_MODE]:
        return False
    if value[PARAMETER] in _FLOWS:
        return True
    return value[PARAMETER] == SupplyParameter.VARIABLE_OPERATION_COST and math.isclose(
        value[VALUE_COL], line[COST]
    )


def _read_mode_ends(state: State, year: int) -> pl.DataFrame:
    """The ends of each technology at each operating mode."""
    fuels = read_electricity_fuels(state).select(REGION, FUEL, AnnotationColumn.LOCATION)
    ends = [
        _read_end(state, year, parameter, fuels, columns)
        for parameter, columns in ((_FLOWS[0], _FROM), (_FLOWS[1], _TO))
    ]
    return ends[0].join(ends[1], on=_MODE_KEYS, how="full", coalesce=True)


def _read_end(
    state: State, year: int, parameter: str, fuels: pl.DataFrame, columns: _EndColumns
) -> pl.DataFrame:
    location = pl.col(AnnotationColumn.LOCATION)
    return (
        read_parameter(state, parameter, year)
        .filter(pl.col(VALUE_COL) > 0)
        .join(fuels.filter(location.is_not_null()), on=[REGION, FUEL])
        .group_by(_MODE_KEYS)
        .agg(
            location.min().alias(columns.location),
            location.n_unique().alias(columns.locations),
            pl.col(FUEL).min().alias(columns.fuel),
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


def _express_has_ends() -> pl.Expr:
    return (
        (pl.col(FROM_LOCATIONS) == _ONE_LOCATION)
        & (pl.col(TO_LOCATIONS) == _ONE_LOCATION)
        & (pl.col(FROM_LOCATION) != pl.col(TO_LOCATION))
    )


_SKIP_RULES = (
    SkipRule(pl.col(RESIDUAL_CAPACITY) > 0, NO_CAPACITY_SKIP),
    SkipRule(_express_has_ends(), NO_ENDS_SKIP),
)


def _enrich_reverse_modes(
    state: State, operations: OperationsYear, lines: pl.DataFrame
) -> pl.DataFrame:
    """The flow back: the first other mode that takes electricity in at the to end, and puts it
    out at the from end.
    """
    reverse = (
        _read_mode_ends(state, operations.year)
        .filter((pl.col(OPERATING_MODE) != operations.mode) & _express_has_ends())
        .join(
            lines.select(*_KEYS, FROM_LOCATION, TO_LOCATION),
            left_on=[*_KEYS, FROM_LOCATION, TO_LOCATION],
            right_on=[*_KEYS, TO_LOCATION, FROM_LOCATION],
        )
        .sort(pl.col(OPERATING_MODE).cast(pl.Int64, strict=False), OPERATING_MODE)
        .group_by(_KEYS)
        .agg(
            pl.col(OPERATING_MODE).first().alias(REVERSE_MODE),
            pl.col(INPUT_RATIO).first().alias(REVERSE_INPUT_RATIO),
            pl.col(OUTPUT_RATIO).first().alias(REVERSE_OUTPUT_RATIO),
        )
    )
    return lines.join(reverse, on=_KEYS, how="left")


def _enrich_ratings(state: State, operations: OperationsYear, lines: pl.DataFrame) -> pl.DataFrame:
    stated = read_availability_factors(state, operations.year, lines.select(_KEYS)).rename(
        {AVAILABILITY_FACTOR: AVAILABILITY}
    )
    rated = lines.join(stated, on=_KEYS).with_columns(
        (
            operations.units.convert_capacity_to_mw(pl.col(RESIDUAL_CAPACITY))
            * pl.col(AVAILABILITY)
        ).alias(CAPACITY_MW)
    )
    capacity = pl.col(CAPACITY_MW)
    return rated.with_columns(
        (capacity * pl.col(INPUT_RATIO)).alias(SENT_MW),
        (capacity * pl.col(OUTPUT_RATIO)).alias(RECEIVED_MW),
        (1.0 - pl.col(OUTPUT_RATIO) / pl.col(INPUT_RATIO)).alias(LOSS),
        (capacity * pl.col(REVERSE_INPUT_RATIO)).fill_null(_NO_FLOW).alias(REVERSE_SENT_MW),
        (capacity * pl.col(REVERSE_OUTPUT_RATIO)).fill_null(_NO_FLOW).alias(REVERSE_RECEIVED_MW),
    )


def _enrich_costs(state: State, operations: OperationsYear, lines: pl.DataFrame) -> pl.DataFrame:
    """The cost of each MWh that the line sends, from the cost of each unit of activity."""
    keys = lines.select(*_KEYS, pl.lit(operations.mode).alias(OPERATING_MODE))
    stated = read_variable_costs(state, operations.year, keys).select(
        *_KEYS, pl.col(VARIABLE_COST).alias(COST)
    )
    table = lines.join(stated, on=_KEYS)
    convert = operations.units.convert_cost_per_energy_to_dollars_per_mwh
    per_sent = express_converted(table, COST, convert) / pl.col(INPUT_RATIO)
    return table.with_columns(per_sent.alias(COST_MWH))
