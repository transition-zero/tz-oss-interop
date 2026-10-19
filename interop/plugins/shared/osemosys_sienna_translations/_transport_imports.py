"""An import mode of an OSeMOSYS AggregateTransportTechnology -> a Sienna ThermalStandard.

An import mode puts out electricity at one end of a line and takes in no electricity. So it
brings electricity from outside the model. The system holds it as a generator on the bus of
that end. The generator rates at the residual capacity of the line in MW × the electricity
output ratio of the mode. Its availability in each hour is that of the line: the capacity
factor of the hour × the availability factor. For each MWh of output, it pays the variable cost
of the mode and the penalty of each pollutant that the mode emits.
"""

from __future__ import annotations

import logging
from typing import Any

import polars as pl

from interop.core.extensions import GeneratorExtension
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import StagedTimeSeriesCol
from interop.plugins.shared.osemosys_canonical.constants import (
    FUEL,
    OPERATING_MODE,
    POLLUTANT,
    REGION,
    TECHNOLOGY,
    VALUE_COL,
    AnnotationColumn,
    FlowParameter,
)
from interop.plugins.shared.osemosys_sienna_constants import (
    IMPORT_CARRIER,
    IMPORT_NAME_PART,
    IMPORT_NAME_SEPARATOR,
    OSEMOSYS_TO_SIENNA_PIPELINE,
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
from interop.plugins.shared.osemosys_sienna_translations._buses import read_electricity_fuels
from interop.plugins.shared.osemosys_sienna_translations._canonical import read_parameter
from interop.plugins.shared.osemosys_sienna_translations._events import build_osemosys_field
from interop.plugins.shared.osemosys_sienna_translations._generator_columns import (
    CAPACITY_MW,
    CAPACITY_UNIT,
    GENERATOR_NAME,
    HAS_SERIES,
    OUTPUT_CAPACITY_MW,
    RESIDUAL_CAPACITY,
    SIENNA_TYPE,
    TECHNOLOGY_NAME,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_costs import (
    DETAIL,
    OWN_COST,
    OWN_COST_MWH,
    PARAMETER,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_emissions import (
    EMISSION_TERMS,
    OWN_RATE,
    RATE_T_PER_MWH,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_penalties import (
    EMISSION_COST_MWH,
    OPERATION_COST_MWH,
    PENALTY,
    PENALTY_COST_MWH,
    PENALTY_PER_TONNE,
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
from interop.plugins.shared.osemosys_sienna_translations._transport_columns import (
    FROM_LOCATION,
    IMPORT_FLOWS,
    LINE_NAME,
    TO_LOCATION,
)
from interop.plugins.shared.osemosys_sienna_translations._units import express_converted
from interop.plugins.shared.sienna_constants import SiennaComponent
from interop.plugins.shared.warning_text import name_a_few
from interop.ports.outbound.reporting import EventKind, TranslationEvent

log = logging.getLogger(__name__)

# The electricity fuels that an import mode puts out, in name order.
IMPORT_FUELS = "import_fuels"

_KEYS = [REGION, TECHNOLOGY]
_MODE_KEYS = [REGION, TECHNOLOGY, OPERATING_MODE]
_LOCATIONS = "locations"
_ONE_LOCATION = 1
_NO_COST = 0.0
_NAME_INFIX = f"{IMPORT_NAME_SEPARATOR}{IMPORT_NAME_PART}{IMPORT_NAME_SEPARATOR}"
# The values of an import mode, other than its flows, that its generator holds.
_HELD_PARAMETERS = frozenset(
    {SupplyParameter.VARIABLE_OPERATION_COST, SupplyParameter.EMISSION_RATE}
)


def read_import_modes(
    state: State, operations: OperationsYear, lines: pl.DataFrame, recorder: ScopedRecorder
) -> pl.DataFrame:
    """Each mode of a line that puts out electricity at one end of it, and takes in none.

    `lines` holds the name and the ends of each line. Each row holds the location of the end,
    the electricity fuels that the mode puts out there, and the sum of their output ratios. An
    output to an electricity fuel with no location is reported, because no bus can hold it.
    """
    ends = lines.select(*_KEYS, TECHNOLOGY_NAME, FROM_LOCATION, TO_LOCATION)
    outputs = _read_unfed_outputs(state, operations).join(ends, on=_KEYS)
    has_location = pl.col(AnnotationColumn.LOCATION).is_not_null()
    _report_unplaced_outputs(outputs.filter(~has_location), recorder)
    return _build_import_modes(outputs.filter(has_location))


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

    `lines` holds the name and the residual capacity of each line.
    """
    if imports.height == 0:
        return GeneratorSources(imports, pl.DataFrame())
    held = lines.select(*_KEYS, LINE_NAME, TECHNOLOGY_NAME, RESIDUAL_CAPACITY)
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
    electricity, with the location of its fuel.
    """
    fuels = read_electricity_fuels(state).select(REGION, FUEL, AnnotationColumn.LOCATION)
    outputs = _read_flows(state, operations.year, FlowParameter.OUTPUT_ACTIVITY_RATIO, fuels)
    inputs = _read_flows(state, operations.year, FlowParameter.INPUT_ACTIVITY_RATIO, fuels)
    return outputs.filter(pl.col(OPERATING_MODE) != operations.mode).join(
        inputs.select(_MODE_KEYS).unique(), on=_MODE_KEYS, how="anti"
    )


def _build_import_modes(outputs: pl.DataFrame) -> pl.DataFrame:
    """The modes whose electricity outputs are at one location, which is one end of the line."""
    location = pl.col(AnnotationColumn.LOCATION)
    at_an_end = (location == pl.col(FROM_LOCATION)) | (location == pl.col(TO_LOCATION))
    return (
        outputs.group_by(_MODE_KEYS)
        .agg(
            location.min(),
            location.n_unique().alias(_LOCATIONS),
            pl.col(FROM_LOCATION).first(),
            pl.col(TO_LOCATION).first(),
            pl.col(FUEL).sort().alias(IMPORT_FUELS),
            pl.col(VALUE_COL).cast(pl.Float64).sum().alias(ELECTRICITY_OUTPUT_RATIO),
        )
        .filter((pl.col(_LOCATIONS) == _ONE_LOCATION) & at_an_end)
        .drop(_LOCATIONS, FROM_LOCATION, TO_LOCATION)
        .sort(_MODE_KEYS)
    )


def _report_unplaced_outputs(outputs: pl.DataFrame, recorder: ScopedRecorder) -> None:
    """Record each import of an electricity fuel with no location, and name a few lines."""
    if outputs.height == 0:
        return
    for row in outputs.iter_rows(named=True):
        recorder.append(_build_unplaced_event(row))
    names = outputs[TECHNOLOGY_NAME].unique().sort().to_list()
    log.warning(
        "%s: %d transport technology(ies) have a mode that imports an electricity fuel with no "
        "location, so no generator holds that import. Technologies: %s",
        OSEMOSYS_TO_SIENNA_PIPELINE,
        len(names),
        name_a_few(names),
    )


def _build_unplaced_event(row: dict[str, Any]) -> TranslationEvent:
    detail = f"{OPERATING_MODE} {row[OPERATING_MODE]}, {row[FUEL]}"
    return TranslationEvent(
        kind=EventKind.NOT_MAPPED,
        sources=[
            build_osemosys_field(
                FlowParameter.OUTPUT_ACTIVITY_RATIO, row[TECHNOLOGY_NAME], detail, row[VALUE_COL]
            )
        ],
        note=(
            f"the electricity fuel {row[FUEL]} has no location, so no bus can hold what the "
            "mode imports"
        ),
    )


def _read_flows(
    state: State, year: int, parameter: FlowParameter, fuels: pl.DataFrame
) -> pl.DataFrame:
    return (
        read_parameter(state, parameter, year)
        .filter(pl.col(VALUE_COL) > 0)
        .join(fuels, on=[REGION, FUEL])
    )


def _enrich_capacity(operations: OperationsYear, imports: pl.DataFrame) -> pl.DataFrame:
    name = pl.concat_str(LINE_NAME, pl.lit(_NAME_INFIX), OPERATING_MODE)
    capacity = operations.units.convert_capacity_to_mw(pl.col(RESIDUAL_CAPACITY))
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
        .with_columns(pl.col(EMISSION_COST_MWH).fill_null(_NO_COST))
    )
    total = pl.col(OWN_COST_MWH) + pl.col(EMISSION_COST_MWH)
    return table.with_columns(total.alias(OPERATION_COST_MWH))


def _read_emission_rates(
    state: State, operations: OperationsYear, imports: pl.DataFrame
) -> pl.DataFrame:
    """The `emission_rate` of each import mode, in t for each MWh of its output."""
    rates = (
        read_parameter(state, SupplyParameter.EMISSION_RATE, operations.year)
        .filter(pl.col(VALUE_COL) != 0)
        .join(imports.select(*_MODE_KEYS, ELECTRICITY_OUTPUT_RATIO), on=_MODE_KEYS)
        .select(
            *_MODE_KEYS,
            POLLUTANT,
            pl.col(VALUE_COL).cast(pl.Float64).alias(OWN_RATE),
            ELECTRICITY_OUTPUT_RATIO,
        )
    )
    convert = operations.units.convert_emissions_per_energy_to_tonnes_per_mwh
    rate = express_per_output(express_converted(rates, OWN_RATE, convert))
    return rates.with_columns(rate.alias(RATE_T_PER_MWH))


def _build_extension(row: dict[str, Any]) -> GeneratorExtension:
    return GeneratorExtension(
        name=row[GENERATOR_NAME],
        carrier=IMPORT_CARRIER,
        category=IMPORT_CARRIER,
        emission_rates_t_per_mwh=build_emission_rates(row[EMISSION_TERMS]),
        source_technology=row[TECHNOLOGY_NAME],
        source_mode=row[OPERATING_MODE],
    )
