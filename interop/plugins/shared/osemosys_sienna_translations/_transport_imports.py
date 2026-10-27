"""An import mode of an OSeMOSYS AggregateTransportTechnology -> a Sienna ThermalStandard.

An import mode puts out electricity at one end of a line and takes in no electricity. So it
brings electricity from outside the model. The system holds it as a generator on the bus of
that end. The generator rates at the residual capacity of the line in MW × the electricity
output ratio of the mode. Its availability in each hour is that of the line: the capacity
factor of the hour × the availability factor. For each MWh of output, it pays the variable cost
of the mode and the penalty of each pollutant that the mode emits.
"""

from __future__ import annotations

from typing import Any

import polars as pl

from interop.core.extensions import GeneratorExtension
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import StagedTimeSeriesCol
from interop.plugins.shared.osemosys_canonical.constants import (
    FUEL,
    OPERATING_MODE,
    OSEMOSYS_FRAMEWORK,
    POLLUTANT,
    REGION,
    TECHNOLOGY,
    VALUE_COL,
    FlowParameter,
)
from interop.plugins.shared.osemosys_sienna_constants import (
    IMPORT_CARRIER,
    IMPORT_NAME_PART,
    IMPORT_NAME_SEPARATOR,
    NO_COST,
    OSEMOSYS_TO_SIENNA_PIPELINE,
    TECHNOLOGIES_LABEL,
    SupplyParameter,
)
from interop.plugins.shared.osemosys_sienna_translations._activity import (
    ELECTRICITY_OUTPUT_RATIO,
    express_output_capacity,
    express_per_output,
)
from interop.plugins.shared.osemosys_sienna_translations._availability import (
    IS_VARYING,
    build_availability,
)
from interop.plugins.shared.osemosys_sienna_translations._buses import (
    ELECTRICITY_BUS,
    read_electricity_fuels,
)
from interop.plugins.shared.osemosys_sienna_translations._canonical import read_parameter
from interop.plugins.shared.osemosys_sienna_translations._generator_columns import (
    CAPACITY_MW,
    CAPACITY_UNIT,
    GENERATOR_NAME,
    HAS_SERIES,
    OUTPUT_CAPACITY_MW,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_costs import (
    DETAIL,
    OWN_COST,
    OWN_COST_MWH,
    PARAMETER,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_emissions import (
    ACTIVITY_RATE_T_PER_MWH,
    EMISSION_TERMS,
    OWN_RATE,
    PENALTY,
    PENALTY_PER_TONNE,
    RATE_T_PER_MWH,
    STATED_RATE,
    read_emission_rates,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_penalties import (
    EMISSION_COST_MWH,
    OPERATION_COST_MWH,
    PENALTY_COST_MWH,
    PENALTY_TERMS,
    build_penalty_terms,
)
from interop.plugins.shared.osemosys_sienna_translations._generators import (
    GeneratorSources,
    build_emission_rates,
)
from interop.plugins.shared.osemosys_sienna_translations._operations import OperationsYear
from interop.plugins.shared.osemosys_sienna_translations._technologies import (
    VARIABLE_COST,
    read_variable_costs,
)
from interop.plugins.shared.osemosys_sienna_translations._technology_columns import (
    SIENNA_TYPE,
    TECHNOLOGY_NAME,
)
from interop.plugins.shared.osemosys_sienna_translations._transport_columns import (
    CAPACITY_PARAMETER,
    FROM_BUS,
    IMPORT_FLOWS,
    IS_UNLIMITED,
    LINE_CAPACITY,
    LINE_NAME,
    TO_BUS,
)
from interop.plugins.shared.osemosys_sienna_translations._units import express_converted
from interop.plugins.shared.sienna_constants import SiennaComponent
from interop.plugins.shared.translation_runner import (
    SkippedNames,
    SkipReport,
    filter_component,
    report_not_mapped,
)

# The electricity fuels that an import mode puts out, in name order.
IMPORT_FUELS = "import_fuels"

_KEYS = [REGION, TECHNOLOGY]
_MODE_KEYS = [REGION, TECHNOLOGY, OPERATING_MODE]
_BUSES = "buses"
_ONE_BUS = 1
_NAME_INFIX = f"{IMPORT_NAME_SEPARATOR}{IMPORT_NAME_PART}{IMPORT_NAME_SEPARATOR}"
# The values of an import mode, other than its flows, that its generator holds.
_HELD_PARAMETERS = frozenset(
    {SupplyParameter.VARIABLE_OPERATION_COST, SupplyParameter.EMISSION_RATE}
)
_MODE_NAME = "mode_name"
_IMPORT_MODES = "import_modes"
_IMPORT_MODE_COUNT = "import_mode_count"
_ONE_IMPORT = 1
_LISTED = SkippedNames(column=TECHNOLOGY_NAME, label=TECHNOLOGIES_LABEL)
_MODE_SEPARATOR = ", "
_MODE_INFIX = f"{IMPORT_NAME_SEPARATOR}mode"

_IMPORT_MODES_ATTRIBUTE = "import modes"
_UNPLACED_REPORT = SkipReport(
    pipeline=OSEMOSYS_TO_SIENNA_PIPELINE,
    framework=OSEMOSYS_FRAMEWORK,
    component=FlowParameter.OUTPUT_ACTIVITY_RATIO,
    name_col=TECHNOLOGY_NAME,
    reason="put out an electricity fuel with no location, which no bus can hold",
    counted_noun="import(s) of a line technology",
    note=lambda row: (
        f"at the {OPERATING_MODE} {row[OPERATING_MODE]}, the electricity fuel {row[FUEL]} has "
        "no location, so no bus can hold what the mode imports"
    ),
    listed=_LISTED,
    attribute_col=VALUE_COL,
    attribute_name="electricity with no location",
)
_SHARED_CAPACITY_REPORT = SkipReport(
    pipeline=OSEMOSYS_TO_SIENNA_PIPELINE,
    framework=OSEMOSYS_FRAMEWORK,
    component=TECHNOLOGY,
    name_col=TECHNOLOGY_NAME,
    reason=(
        "bind the sum of two or more import modes, and each import generator takes the whole "
        "capacity of the line"
    ),
    counted_noun="shared capacity limit(s) of a line",
    note=lambda row: (
        f"the import modes {row[_IMPORT_MODES]} each become a ThermalStandard at the whole "
        f"capacity of the line, {row[CAPACITY_PARAMETER]} = {row[LINE_CAPACITY]}, and the system "
        "holds no limit on their sum, so together they can import more than the line can carry"
    ),
    listed=_LISTED,
    attribute_col=_IMPORT_MODES,
    attribute_name=_IMPORT_MODES_ATTRIBUTE,
)

UNLIMITED_IMPORT_SKIP = SkipReport(
    pipeline=OSEMOSYS_TO_SIENNA_PIPELINE,
    framework=OSEMOSYS_FRAMEWORK,
    component=TECHNOLOGY,
    name_col=_MODE_NAME,
    reason="import on a line that the model builds at no cost with no limit",
    counted_noun="import mode(s)",
    note=(
        "the line has no capacity that limits it, so the import has no rating; the line record "
        "keeps the values of the mode"
    ),
)


def read_import_modes(
    state: State, operations: OperationsYear, lines: pl.DataFrame, recorder: ScopedRecorder
) -> pl.DataFrame:
    """Each mode of a line that puts out electricity at one end of it, and takes in none.

    `lines` holds the name, the ends and the capacity of each line. Each row holds the bus of
    the end, the electricity fuels that the mode puts out there, and the sum of their output
    ratios. An output to an electricity fuel with no location is reported, because no bus can
    hold it, and so is an import of a line that no limit binds, as it has no rating.
    """
    ends = lines.select(*_KEYS, TECHNOLOGY_NAME, FROM_BUS, TO_BUS, IS_UNLIMITED)
    outputs = _read_unfed_outputs(state, operations).join(ends, on=_KEYS)
    placed, _ = report_not_mapped(
        outputs, pl.col(ELECTRICITY_BUS).is_not_null(), _UNPLACED_REPORT, recorder
    )
    modes = _build_import_modes(placed).with_columns(
        pl.concat_str(TECHNOLOGY_NAME, pl.lit(_MODE_INFIX), OPERATING_MODE).alias(_MODE_NAME)
    )
    modes, _ = filter_component(modes, ~pl.col(IS_UNLIMITED), UNLIMITED_IMPORT_SKIP, recorder)
    report_not_mapped(
        _count_import_modes(modes, lines),
        pl.col(_IMPORT_MODE_COUNT) == _ONE_IMPORT,
        _SHARED_CAPACITY_REPORT,
        recorder,
    )
    return modes.drop(IS_UNLIMITED, TECHNOLOGY_NAME, _MODE_NAME)


def enrich_import_flows(lines: pl.DataFrame, imports: pl.DataFrame) -> pl.DataFrame:
    """The mode and the fuel of each electricity output of the import modes of each line."""
    flows = (
        imports.select(*_MODE_KEYS, pl.col(IMPORT_FUELS).alias(FUEL))
        .explode(FUEL, empty_as_null=True)
        .group_by(_KEYS)
        .agg(pl.struct(OPERATING_MODE, FUEL).alias(IMPORT_FLOWS))
    )
    return lines.join(flows, on=_KEYS, how="left")


def is_held_by_import_mode(line: dict[str, Any], value: dict[str, Any]) -> bool:
    """Whether the generator of an import mode of the line holds a value of another mode."""
    flows = line[IMPORT_FLOWS] or []
    if value[OPERATING_MODE] not in {flow[OPERATING_MODE] for flow in flows}:
        return False
    if value[PARAMETER] == FlowParameter.OUTPUT_ACTIVITY_RATIO:
        return {OPERATING_MODE: value[OPERATING_MODE], FUEL: value[DETAIL]} in flows
    return value[PARAMETER] in _HELD_PARAMETERS


def build_imports_source(
    state: State, operations: OperationsYear, imports: pl.DataFrame, lines: pl.DataFrame
) -> GeneratorSources:
    """One row for each import mode, with what its ThermalStandard and its record read, and the
    availability of each hour of each import whose hours differ.

    `lines` holds the name and the capacity of each line.
    """
    if imports.height == 0:
        return GeneratorSources(imports, pl.DataFrame())
    held = lines.select(*_KEYS, LINE_NAME, TECHNOLOGY_NAME, LINE_CAPACITY, CAPACITY_PARAMETER)
    table = _enrich_capacity(operations, imports.join(held, on=_KEYS))
    availability = build_availability(state, operations, table, GENERATOR_NAME)
    table = _enrich_own_costs(state, operations, availability.table)
    table = _enrich_emissions(state, operations, table)
    table = table.with_columns(pl.col(IS_VARYING).alias(HAS_SERIES))
    with_series = table.filter(pl.col(HAS_SERIES))[GENERATOR_NAME].implode()
    series = availability.series.filter(pl.col(StagedTimeSeriesCol.COMPONENT).is_in(with_series))
    return GeneratorSources(table.sort(GENERATOR_NAME), series)


def build_import_extensions(imports: pl.DataFrame) -> list[GeneratorExtension]:
    """The generator record of each import mode."""
    return [_build_extension(row) for row in imports.iter_rows(named=True)]


def _read_unfed_outputs(state: State, operations: OperationsYear) -> pl.DataFrame:
    """Each electricity output of a mode, other than the operations mode, that takes in no
    electricity, with the bus of its fuel.
    """
    fuels = read_electricity_fuels(state).select(REGION, FUEL, ELECTRICITY_BUS)
    outputs = _read_flows(state, operations.year, FlowParameter.OUTPUT_ACTIVITY_RATIO, fuels)
    inputs = _read_flows(state, operations.year, FlowParameter.INPUT_ACTIVITY_RATIO, fuels)
    return outputs.filter(pl.col(OPERATING_MODE) != operations.mode).join(
        inputs.select(_MODE_KEYS).unique(), on=_MODE_KEYS, how="anti"
    )


def _build_import_modes(outputs: pl.DataFrame) -> pl.DataFrame:
    """The modes whose electricity outputs are at one bus, which is one end of the line."""
    bus = pl.col(ELECTRICITY_BUS)
    at_an_end = (bus == pl.col(FROM_BUS)) | (bus == pl.col(TO_BUS))
    return (
        outputs.group_by(_MODE_KEYS)
        .agg(
            bus.min(),
            bus.n_unique().alias(_BUSES),
            pl.col(FROM_BUS).first(),
            pl.col(TO_BUS).first(),
            pl.col(IS_UNLIMITED).first(),
            pl.col(TECHNOLOGY_NAME).first(),
            pl.col(FUEL).sort().alias(IMPORT_FUELS),
            pl.col(VALUE_COL).cast(pl.Float64).sum().alias(ELECTRICITY_OUTPUT_RATIO),
        )
        .filter((pl.col(_BUSES) == _ONE_BUS) & at_an_end)
        .drop(_BUSES, FROM_BUS, TO_BUS)
        .sort(_MODE_KEYS)
    )


def _count_import_modes(modes: pl.DataFrame, lines: pl.DataFrame) -> pl.DataFrame:
    """Each line with an import mode, with its capacity, its import modes and their count."""
    capacities = lines.select(*_KEYS, CAPACITY_PARAMETER, LINE_CAPACITY)
    mode = pl.col(OPERATING_MODE).sort()
    return (
        modes.group_by(*_KEYS, TECHNOLOGY_NAME)
        .agg(
            mode.str.join(_MODE_SEPARATOR).alias(_IMPORT_MODES),
            mode.len().alias(_IMPORT_MODE_COUNT),
        )
        .join(capacities, on=_KEYS)
        .sort(TECHNOLOGY_NAME)
    )


def _read_flows(
    state: State, year: int, parameter: FlowParameter, fuels: pl.DataFrame
) -> pl.DataFrame:
    return (
        read_parameter(state, parameter, year)
        .filter(pl.col(VALUE_COL) > 0)
        .join(fuels.lazy(), on=[REGION, FUEL])
        .select(*_MODE_KEYS, FUEL, VALUE_COL, ELECTRICITY_BUS)
        .collect()
    )


def _enrich_capacity(operations: OperationsYear, imports: pl.DataFrame) -> pl.DataFrame:
    name = pl.concat_str(LINE_NAME, pl.lit(_NAME_INFIX), OPERATING_MODE)
    capacity = express_converted(imports, LINE_CAPACITY, operations.units.convert_capacity_to_mw)
    return imports.with_columns(
        name.alias(GENERATOR_NAME),
        pl.lit(SiennaComponent.THERMAL_STANDARD.value).alias(SIENNA_TYPE),
        capacity.alias(CAPACITY_MW),
        pl.lit(operations.units.capacity_unit, dtype=pl.Utf8).alias(CAPACITY_UNIT),
    ).with_columns(express_output_capacity(pl.col(CAPACITY_MW)).alias(OUTPUT_CAPACITY_MW))


def _enrich_own_costs(
    state: State, operations: OperationsYear, imports: pl.DataFrame
) -> pl.DataFrame:
    """The variable cost of the mode, for each MWh of the electricity that it puts out."""
    stated = read_variable_costs(state, operations.year, imports.select(_MODE_KEYS))
    table = imports.join(stated.rename({VARIABLE_COST: OWN_COST}), on=_MODE_KEYS)
    convert = operations.units.convert_cost_per_energy_to_dollars_per_mwh
    own = express_per_output(express_converted(table, OWN_COST, convert))
    return table.with_columns(own.alias(OWN_COST_MWH))


def _enrich_emissions(
    state: State, operations: OperationsYear, imports: pl.DataFrame
) -> pl.DataFrame:
    """The rate of each pollutant that the mode emits, its penalty, and the operation cost."""
    rates = _read_emission_rates(state, operations, imports)
    priced = build_penalty_terms(state, operations, rates)
    emissions = (
        rates.sort(POLLUTANT)
        .group_by(_MODE_KEYS)
        .agg(pl.struct(POLLUTANT, OWN_RATE, RATE_T_PER_MWH).alias(EMISSION_TERMS))
    )
    penalties = (
        priced.sort(POLLUTANT)
        .group_by(_MODE_KEYS)
        .agg(
            pl.struct(
                POLLUTANT, RATE_T_PER_MWH, PENALTY, PENALTY_PER_TONNE, PENALTY_COST_MWH
            ).alias(PENALTY_TERMS),
            pl.col(PENALTY_COST_MWH).sum().alias(EMISSION_COST_MWH),
        )
    )
    table = (
        imports.join(emissions, on=_MODE_KEYS, how="left")
        .join(penalties, on=_MODE_KEYS, how="left")
        .with_columns(pl.col(EMISSION_COST_MWH).fill_null(NO_COST))
    )
    total = pl.col(OWN_COST_MWH) + pl.col(EMISSION_COST_MWH)
    return table.with_columns(total.alias(OPERATION_COST_MWH))


def _read_emission_rates(
    state: State, operations: OperationsYear, imports: pl.DataFrame
) -> pl.DataFrame:
    """The `emission_rate` of each import mode, in t for each MWh of its output."""
    modes = imports.select(*_MODE_KEYS, ELECTRICITY_OUTPUT_RATIO)
    rates = read_emission_rates(state, operations, modes).join(modes, on=_MODE_KEYS)
    return rates.select(
        *_MODE_KEYS,
        POLLUTANT,
        pl.col(STATED_RATE).alias(OWN_RATE),
        express_per_output(pl.col(ACTIVITY_RATE_T_PER_MWH)).alias(RATE_T_PER_MWH),
    )


def _build_extension(row: dict[str, Any]) -> GeneratorExtension:
    return GeneratorExtension(
        name=row[GENERATOR_NAME],
        carrier=IMPORT_CARRIER,
        category=IMPORT_CARRIER,
        emission_rates_t_per_mwh=build_emission_rates(row[EMISSION_TERMS]),
        source_technology=row[TECHNOLOGY_NAME],
        source_mode=row[OPERATING_MODE],
    )
