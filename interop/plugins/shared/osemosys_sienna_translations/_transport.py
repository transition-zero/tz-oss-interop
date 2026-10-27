"""OSeMOSYS AggregateTransportTechnology and conversion of electricity -> Sienna
TwoTerminalGenericHVDCLine.

At the operations mode, a transport technology takes in electricity at the bus of one fuel and
puts it out at the bus of another, in another location. A conversion technology does the same
between two electricity fuels of one location. Each becomes a line from the first bus to the
second, in that direction. It sends at most its capacity in MW × its availability factor × its
electricity input ratio, and it loses the share `1 - output ratio / input ratio` of what it
sends. `_line_capacity` gives the capacity. When another mode takes electricity in at the second
bus and puts it out at the first, the line also flows back, within the limits of that mode. A
mode that puts out electricity at one end and takes in none is an import, which becomes a
generator. The values of every other mode, and each value that a Sienna line has no field for,
go to the line record of extensions.json.
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
from interop.plugins.shared.constants import UNIT_MW
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
from interop.plugins.shared.osemosys_sienna_translations._buses import (
    ELECTRICITY_BUS,
    read_electricity_fuels,
)
from interop.plugins.shared.osemosys_sienna_translations._canonical import (
    read_annotations,
    read_parameter,
)
from interop.plugins.shared.osemosys_sienna_translations._capacity_factors import (
    HAS_CAPACITY_FACTORS,
    build_capacity_factor_series,
    express_has_capacity_factors,
)
from interop.plugins.shared.osemosys_sienna_translations._free_build import (
    FREE_BUILD_PARAMETERS,
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
from interop.plugins.shared.osemosys_sienna_translations._generators import GeneratorSources
from interop.plugins.shared.osemosys_sienna_translations._left_out import (
    IS_ALL_ELECTRICITY,
    read_left_out_technologies,
)
from interop.plugins.shared.osemosys_sienna_translations._line_capacity import (
    enrich_line_capacity,
    read_fleet_output_mw,
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
from interop.plugins.shared.osemosys_sienna_translations._persisted import set_persisted_rows
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
    CAPACITY_PARAMETER,
    COST,
    COST_MWH,
    DERATE,
    FROM_BUS,
    FROM_BUSES,
    FROM_FUEL,
    FROM_LOCATION,
    FROM_LOCATIONS,
    HAS_DROPPED_DERATE,
    HAS_STATED_FACTORS,
    INPUT_RATIO,
    IS_BUILT_FREE,
    IS_CONVERSION,
    IS_UNLIMITED,
    LINE_CAPACITY,
    LINE_NAME,
    LOSS,
    OUTPUT_RATIO,
    RATING,
    RECEIVED_MW,
    REVERSE_INPUT_RATIO,
    REVERSE_MODE,
    REVERSE_OUTPUT_RATIO,
    REVERSE_RECEIVED_MW,
    REVERSE_SENT_MW,
    SENT_MW,
    TO_BUS,
    TO_BUSES,
    TO_FUEL,
    TO_LOCATION,
    TO_LOCATIONS,
    RatingField,
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
_COUNTED_NOUN = "line technology(ies)"
_LISTED = SkippedNames(column=TECHNOLOGY_NAME, label=TECHNOLOGIES_LABEL)
_ONE_BUS = 1
_NO_COST = 0.0
_NO_FLOW = 0.0
_SERIES_FILE = companion_filename(ExtensionKind.CONTROLLABLE_LINE)
_NO_IMPORTS = GeneratorSources(pl.DataFrame(), pl.DataFrame())

# The records of the lines, and the columns that name each line and its technology.
LINE_OWNERS = ValueOwners(ExtensionKind.CONTROLLABLE_LINE, LINE_NAME, TECHNOLOGY_NAME, SIENNA_TYPE)
_FREE_BUILD_SCOPE = "free-build"
_FLEET_MW = "fleet_mw"
# The source value of the rating of a line with no limit: the output of the whole fleet.
_FLEET = "the whole fleet"
_FLEET_ATTRIBUTE = "Σ in MW × the largest electricity output_activity_ratio of each technology"
_STATED_TERM = "the capacity is "
_STATED_TERM_END = " in MW × availability_factor"
_BUILD_LIMIT_TERM = ", the most that the model builds at no cost in the year,"
_FLEET_TERM = (
    "the model builds the technology at no cost and no limit binds it, so the capacity is the "
    "electricity that the whole fleet of the year can put out / the smallest ratio of the line, "
    "which no flow of the operations system can exceed"
)
# The rows of a line technology that the line applies, beside those its record keeps.
_APPLIED_PARAMETERS = (*RATED_PARAMETERS, SupplyParameter.CAPACITY_FACTOR)


@dataclass(frozen=True)
class TransportSources:
    """One row for each line, the capacity factor of each hour of each line that has one, and
    one row for each import mode.
    """

    table: pl.DataFrame
    series: pl.DataFrame
    imports: GeneratorSources


class _EndColumns(NamedTuple):
    """The columns that one end of a transport technology fills."""

    location: str
    locations: str
    bus: str
    buses: str
    fuel: str
    ratio: str


_FROM = _EndColumns(FROM_LOCATION, FROM_LOCATIONS, FROM_BUS, FROM_BUSES, FROM_FUEL, INPUT_RATIO)
_TO = _EndColumns(TO_LOCATION, TO_LOCATIONS, TO_BUS, TO_BUSES, TO_FUEL, OUTPUT_RATIO)


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
    "have no residual capacity in the operations year, and the model builds none at no cost",
    "the fleet of the operations year is its residual capacity, which holds none of it",
    RESIDUAL_CAPACITY,
)
NO_ENDS_SKIP = _build_skip(
    "do not take in electricity at one bus and put it out at another at the operations mode",
    "a line needs one bus where the technology takes in electricity and another where it puts "
    "electricity out, at the operations mode",
)


def read_transport_ends(state: State, year: int, mode: str) -> pl.DataFrame:
    """Where each technology takes in and puts out electricity at the mode, with the ratios.

    `from_buses` and `to_buses` count the buses of each end; a line needs one each.
    `from_locations` and `to_locations` count the locations of each end.
    """
    return _drop_other_modes(_read_mode_ends(state, year), mode)


def build_transport_source(
    state: State, operations: OperationsYear, recorder: ScopedRecorder
) -> TransportSources:
    """One row for each technology that the operations system holds as a line.

    Each end of a line is the bus of an electricity fuel.
    """
    mode_ends = _read_mode_ends(state, operations.year)
    lines = _read_lines(state, operations, _drop_other_modes(mode_ends, operations.mode))
    for rule in _SKIP_RULES:
        lines, _ = filter_component(lines, rule.keep, rule.report, recorder)
    if lines.height == 0:
        return TransportSources(lines, pl.DataFrame(), _NO_IMPORTS)
    imports = read_import_modes(state, operations, lines, recorder)
    lines = enrich_import_flows(lines, imports)
    lines = _enrich_reverse_modes(lines, mode_ends, operations.mode)
    lines = _enrich_ratings(state, operations, _enrich_fleet_output(state, operations, lines))
    lines = _enrich_costs(state, operations, lines)
    lines = enrich_other_mode_values(state, operations, lines)
    lines = _enrich_extension_values(state, operations, lines)
    lines, series = _enrich_capacity_factors(state, operations, lines)
    import_sources = build_imports_source(state, operations, imports, lines)
    return TransportSources(lines.sort(LINE_NAME), series, import_sources)


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
    free = lines.filter(pl.col(IS_BUILT_FREE)).select(_KEYS)
    if free.height > 0:
        for parameter in FREE_BUILD_PARAMETERS:
            set_persisted_rows(
                state, ExtensionKind.CONTROLLABLE_LINE, parameter, [free], _FREE_BUILD_SCOPE
            )


def _build_extension(row: dict[str, Any]) -> ControllableLineExtension:
    return ControllableLineExtension(
        name=row[LINE_NAME],
        marginal_cost=row[COST_MWH] if row[COST_MWH] != _NO_COST else None,
        p_max_pu=row[DERATE],
        p_max_pu_series=_SERIES_FILE if has_series(row) else None,
        is_conversion=True if row[IS_CONVERSION] else None,
        operating_modes=build_operating_mode_field(row),
        e_sum_min=build_yearly_limits(row[LOWER_BOUND.column]),
        e_sum_max=build_yearly_limits(row[UPPER_BOUND.column]),
        **build_value_fields(row, LINK_VALUES),
    )


def _enrich_capacity_factors(
    state: State, operations: OperationsYear, lines: pl.DataFrame
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """The capacity factor of each hour of each line that has a limit, and whether a line with
    no limit leaves out a derate that the model states."""
    limited = lines.filter(~pl.col(IS_UNLIMITED))
    series = build_capacity_factor_series(
        state,
        operations,
        limited.select(REGION, TECHNOLOGY, pl.col(LINE_NAME).alias(CompanionSeriesCol.NAME)),
        ControllableLineCompanionCol.P_MAX_PU,
    )
    stated = read_parameter(state, SupplyParameter.CAPACITY_FACTOR, operations.year)
    has_factors = pl.struct(_KEYS).is_in(stated.select(_KEYS).unique().to_struct().implode())
    is_derated = has_factors | (pl.col(AVAILABILITY) != WHOLE_CAPACITY)
    return lines.with_columns(
        express_has_capacity_factors(series, LINE_NAME).alias(HAS_CAPACITY_FACTORS),
        has_factors.alias(HAS_STATED_FACTORS),
        (pl.col(IS_UNLIMITED) & is_derated).alias(HAS_DROPPED_DERATE),
    ), series


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
            "%s: %d line technology(ies) state values at an operating mode that is neither the "
            "flow back nor an import, and the line does not run them; extensions.json holds "
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
    fuels = read_electricity_fuels(state).select(
        REGION, FUEL, AnnotationColumn.LOCATION, ELECTRICITY_BUS
    )
    ends = [
        _read_end(state, year, parameter, fuels, columns)
        for parameter, columns in ((_FLOWS[0], _FROM), (_FLOWS[1], _TO))
    ]
    return ends[0].join(ends[1], on=_MODE_KEYS, how="full", coalesce=True)


def _drop_other_modes(mode_ends: pl.DataFrame, mode: str) -> pl.DataFrame:
    """The ends of each technology at the one mode."""
    return mode_ends.filter(pl.col(OPERATING_MODE) == mode).drop(OPERATING_MODE)


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
            pl.col(ELECTRICITY_BUS).min().alias(columns.bus),
            pl.col(ELECTRICITY_BUS).n_unique().alias(columns.buses),
            pl.col(FUEL).min().alias(columns.fuel),
            pl.col(VALUE_COL).cast(pl.Float64).sum().alias(columns.ratio),
        )
    )


def _read_lines(state: State, operations: OperationsYear, ends: pl.DataFrame) -> pl.DataFrame:
    """Every transport technology and every conversion of electricity alone, so that each
    Sienna name knows of a clash in another region, with its ends at the operations mode."""
    lines = _read_line_technologies(state, operations).with_columns(
        express_component_name(TECHNOLOGY).alias(LINE_NAME),
        express_report_name(TECHNOLOGY).alias(TECHNOLOGY_NAME),
    )
    lines = enrich_residual_capacity(state, operations.year, lines)
    lines = enrich_line_capacity(state, operations, lines)
    return lines.join(ends, on=_KEYS, how="left")


def _read_line_technologies(state: State, operations: OperationsYear) -> pl.DataFrame:
    kind = pl.col(AnnotationColumn.KIND)
    conversions = (
        read_left_out_technologies(state, operations)
        .filter(kind.eq_missing(TechnologyKind.CONVERSION) & pl.col(IS_ALL_ELECTRICITY))
        .select(_KEYS)
    )
    technologies = read_annotations(state, TECHNOLOGY)
    transport = technologies.filter(kind == TechnologyKind.AGGREGATE_TRANSPORT_TECHNOLOGY)
    lines = pl.concat([transport, technologies.join(conversions, on=_KEYS, how="semi")])
    return lines.with_columns(kind.eq_missing(TechnologyKind.CONVERSION).alias(IS_CONVERSION))


def _express_has_ends() -> pl.Expr:
    return (
        (pl.col(FROM_BUSES) == _ONE_BUS)
        & (pl.col(TO_BUSES) == _ONE_BUS)
        & (pl.col(FROM_BUS) != pl.col(TO_BUS))
    )


_SKIP_RULES = (
    SkipRule((pl.col(RESIDUAL_CAPACITY) > 0) | pl.col(IS_BUILT_FREE), NO_CAPACITY_SKIP),
    SkipRule(_express_has_ends(), NO_ENDS_SKIP),
)


def _enrich_reverse_modes(
    lines: pl.DataFrame, mode_ends: pl.DataFrame, operations_mode: str
) -> pl.DataFrame:
    """The flow back: the first other mode that takes electricity in at the to end, and puts it
    out at the from end.
    """
    reverse = (
        mode_ends.filter((pl.col(OPERATING_MODE) != operations_mode) & _express_has_ends())
        .join(
            lines.select(*_KEYS, FROM_BUS, TO_BUS),
            left_on=[*_KEYS, FROM_BUS, TO_BUS],
            right_on=[*_KEYS, TO_BUS, FROM_BUS],
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
    """The capacity in MW of activity × the availability factor; a line with no limit gets
    what the whole fleet can put out / its smallest ratio, so that no limit of the line binds.

    The rating states the source value of each capacity once, for each event that reads it.
    """
    stated = read_availability_factors(state, operations.year, lines.select(_KEYS))
    rated = lines.join(stated.rename({AVAILABILITY_FACTOR: AVAILABILITY}), on=_KEYS)
    limited = express_converted(rated, LINE_CAPACITY, operations.units.convert_capacity_to_mw)
    is_stand_in = pl.col(IS_UNLIMITED)
    is_derated = ~is_stand_in & (pl.col(AVAILABILITY) != WHOLE_CAPACITY)
    rated = rated.with_columns(
        pl.when(is_stand_in)
        .then(pl.col(_FLEET_MW) / _express_smallest_ratio())
        .otherwise(limited * pl.col(AVAILABILITY))
        .alias(CAPACITY_MW),
        pl.when(is_stand_in)
        .then(_express_fleet_rating())
        .otherwise(_express_stated_rating())
        .alias(RATING),
        pl.when(is_derated).then(pl.col(AVAILABILITY).cast(pl.Float64)).alias(DERATE),
    )
    capacity = pl.col(CAPACITY_MW)
    return rated.with_columns(
        (capacity * pl.col(INPUT_RATIO)).alias(SENT_MW),
        (capacity * pl.col(OUTPUT_RATIO)).alias(RECEIVED_MW),
        (1.0 - pl.col(OUTPUT_RATIO) / pl.col(INPUT_RATIO)).alias(LOSS),
        (capacity * pl.col(REVERSE_INPUT_RATIO)).fill_null(_NO_FLOW).alias(REVERSE_SENT_MW),
        (capacity * pl.col(REVERSE_OUTPUT_RATIO)).fill_null(_NO_FLOW).alias(REVERSE_RECEIVED_MW),
    )


def _express_stated_rating() -> pl.Expr:
    """The capacity that the model states, or the most that it builds at no cost."""
    is_residual = pl.col(CAPACITY_PARAMETER) == SupplyParameter.RESIDUAL_CAPACITY
    build_limit = pl.when(is_residual).then(pl.lit("")).otherwise(pl.lit(_BUILD_LIMIT_TERM))
    term = [pl.lit(_STATED_TERM), pl.col(CAPACITY_PARAMETER), build_limit, pl.lit(_STATED_TERM_END)]
    return _express_rating(
        parameter=pl.col(CAPACITY_PARAMETER),
        name=pl.col(TECHNOLOGY_NAME),
        attribute=pl.lit(None, dtype=pl.Utf8),
        value=pl.col(LINE_CAPACITY).cast(pl.Float64),
        unit=pl.lit(None, dtype=pl.Utf8),
        is_stand_in=pl.lit(False),  # noqa: FBT003
        term=pl.concat_str(term),
    )


def _express_fleet_rating() -> pl.Expr:
    """What the whole fleet of the year can put out, for a line that no limit binds."""
    return _express_rating(
        parameter=pl.lit(SupplyParameter.RESIDUAL_CAPACITY.value),
        name=pl.lit(_FLEET),
        attribute=pl.lit(_FLEET_ATTRIBUTE),
        value=pl.col(_FLEET_MW),
        unit=pl.lit(UNIT_MW),
        is_stand_in=pl.lit(True),  # noqa: FBT003
        term=pl.lit(_FLEET_TERM),
    )


def _express_rating(**fields: pl.Expr) -> pl.Expr:
    """The rating struct, with its fields in the order of `RatingField`."""
    return pl.struct([fields[field].alias(field) for field in RatingField])


def _enrich_fleet_output(
    state: State, operations: OperationsYear, lines: pl.DataFrame
) -> pl.DataFrame:
    """What the whole fleet can put out, where a line has no limit, and a warning where that
    is nothing."""
    unlimited = lines.filter(pl.col(IS_UNLIMITED))
    fleet_mw = read_fleet_output_mw(state, operations) if unlimited.height > 0 else None
    if fleet_mw is not None and fleet_mw <= 0:
        _warn_empty_fleet(unlimited[TECHNOLOGY_NAME].sort().to_list())
    return lines.with_columns(pl.lit(fleet_mw, dtype=pl.Float64).alias(_FLEET_MW))


def _warn_empty_fleet(names: list[str]) -> None:
    log.warning(
        "%s: the fleet of the operations year puts out no electricity, so %d line "
        "technology(ies) that the model builds at no cost with no limit rate at 0 MW. "
        "Technologies: %s",
        OSEMOSYS_TO_SIENNA_PIPELINE,
        len(names),
        name_a_few(names),
    )


def _express_smallest_ratio() -> pl.Expr:
    ratios = (INPUT_RATIO, OUTPUT_RATIO, REVERSE_INPUT_RATIO, REVERSE_OUTPUT_RATIO)
    return pl.concat_list(*ratios).list.drop_nulls().list.min()


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
