"""The price and the emission rates of a fuel, from the technology that produces it.

A technology pays for each fuel that it takes in at the price of the producer of that fuel. The
producer is the cheapest `fuel_supply` technology that puts the fuel out in the region of the
technology, at the operations mode. A fuel balances in one region and has one location, so
that producer makes the fuel at the place where the technology takes it in. A technology of any
other kind, for example a pipeline, is not a producer. A producer whose activity upper limit in
the year is zero makes nothing, and neither does a producer with no capacity that can run in the
year, so neither is a producer. A fuel whose producers all make nothing is stranded.

Each value stays in the units of the model: currency and emissions per energy unit of the fuel.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.osemosys_canonical.constants import (
    FUEL,
    OPERATING_MODE,
    POLLUTANT,
    REGION,
    TECHNOLOGY,
    VALUE_COL,
    AnnotationColumn,
    FlowParameter,
    TechnologyKind,
)
from interop.plugins.shared.osemosys_sienna_constants import NO_LIMIT, SupplyParameter
from interop.plugins.shared.osemosys_sienna_translations._canonical import (
    read_annotations,
    read_mode_parameter,
    read_parameter_with_defaults,
)
from interop.plugins.shared.osemosys_sienna_translations._free_build import (
    enrich_free_build,
    express_has_capacity,
)
from interop.plugins.shared.osemosys_sienna_translations._technologies import (
    VARIABLE_COST,
    read_variable_costs,
)

INPUT_RATIO = "input_ratio"
PRODUCER = "producer"
PRODUCER_COUNT = "producer_count"
PRODUCER_COST = "producer_cost"
OUTPUT_RATIO = "output_ratio"
COST_PER_OUTPUT = "cost_per_output"
PRODUCER_EMISSION_RATE = "producer_emission_rate"
EMISSION_RATE_PER_OUTPUT = "emission_rate_per_output"
# Whether a fuel_supply technology makes anything in the year.
IS_RUNNABLE = "is_runnable"

_KEYS = [REGION, TECHNOLOGY]
_FUEL_KEYS = [REGION, FUEL]


@dataclass(frozen=True)
class FuelSupply:
    """The producer of each fuel that has one, and the emission rates of those producers.

    `prices` holds one row for each region and fuel, with the chosen producer, the number of
    producers it was chosen from and its cost per unit of the fuel. `emission_rates` holds one
    row for each region, fuel and pollutant of a producer that emits. `stranded` holds one row
    for each region and fuel whose producers all make nothing in the year.
    """

    prices: pl.DataFrame
    emission_rates: pl.DataFrame
    stranded: pl.DataFrame


def build_fuel_supply(state: State, year: int, mode: str) -> FuelSupply:
    candidates = _read_candidates(state, year, mode)
    prices = _build_prices(candidates.filter(pl.col(IS_RUNNABLE)))
    emission_rates = _read_emission_rates(state, year, mode, prices)
    return FuelSupply(prices, emission_rates, _list_stranded_fuels(candidates))


def read_input_ratios(
    state: State, year: int, mode: str, technologies: pl.DataFrame
) -> pl.DataFrame:
    """Each fuel that a technology of `technologies` takes in at the mode, with its ratio."""
    return (
        read_mode_parameter(state, FlowParameter.INPUT_ACTIVITY_RATIO, year, mode)
        .filter(pl.col(VALUE_COL) > 0)
        .join(technologies.select(REGION, TECHNOLOGY), on=[REGION, TECHNOLOGY], how="semi")
        .select(REGION, TECHNOLOGY, FUEL, pl.col(VALUE_COL).alias(INPUT_RATIO))
    )


def _read_candidates(state: State, year: int, mode: str) -> pl.DataFrame:
    """Each fuel that a `fuel_supply` technology puts out, with its cost and whether it runs."""
    suppliers = _read_suppliers(state, year)
    outputs = (
        read_mode_parameter(state, FlowParameter.OUTPUT_ACTIVITY_RATIO, year, mode)
        .filter(pl.col(VALUE_COL) > 0)
        .join(suppliers, on=_KEYS)
        .select(*_KEYS, FUEL, pl.col(VALUE_COL).alias(OUTPUT_RATIO), IS_RUNNABLE)
    )
    keys = outputs.select(*_KEYS, pl.lit(mode).alias(OPERATING_MODE)).unique()
    costs = read_variable_costs(state, year, keys).select(
        *_KEYS, pl.col(VARIABLE_COST).alias(PRODUCER_COST)
    )
    return outputs.join(costs, on=_KEYS)


def _read_suppliers(state: State, year: int) -> pl.DataFrame:
    """Each `fuel_supply` technology, and whether it has capacity that can run in the year and
    an activity limit of the year above zero."""
    suppliers = (
        read_annotations(state, TECHNOLOGY)
        .filter(pl.col(AnnotationColumn.KIND) == TechnologyKind.FUEL_SUPPLY)
        .select(_KEYS)
    )
    limits = read_parameter_with_defaults(
        state, SupplyParameter.ACTIVITY_UPPER_LIMIT, year, suppliers
    )
    is_open = pl.col(VALUE_COL).fill_null(NO_LIMIT) != 0
    built = enrich_free_build(state, year, suppliers).join(limits, on=_KEYS, how="left")
    return built.select(*_KEYS, (express_has_capacity() & is_open).alias(IS_RUNNABLE))


def _list_stranded_fuels(candidates: pl.DataFrame) -> pl.DataFrame:
    return (
        candidates.group_by(_FUEL_KEYS)
        .agg(pl.col(IS_RUNNABLE).any(), pl.len().alias(PRODUCER_COUNT))
        .filter(~pl.col(IS_RUNNABLE))
        .select(*_FUEL_KEYS, PRODUCER_COUNT)
    )


def _build_prices(candidates: pl.DataFrame) -> pl.DataFrame:
    """The producer with the lowest variable cost for each unit of each fuel.

    Two producers at one cost go to the first name, so the choice does not depend on row order.
    """
    cost = (pl.col(PRODUCER_COST) / pl.col(OUTPUT_RATIO)).alias(COST_PER_OUTPUT)
    return (
        candidates.with_columns(cost)
        .sort(REGION, FUEL, COST_PER_OUTPUT, TECHNOLOGY)
        .group_by(REGION, FUEL, maintain_order=True)
        .agg(
            pl.col(TECHNOLOGY).first().alias(PRODUCER),
            pl.len().alias(PRODUCER_COUNT),
            pl.col(PRODUCER_COST, OUTPUT_RATIO, COST_PER_OUTPUT).first(),
        )
    )


def _read_emission_rates(state: State, year: int, mode: str, prices: pl.DataFrame) -> pl.DataFrame:
    """What each chosen producer emits for each unit of the fuel that it puts out."""
    rates = (
        read_mode_parameter(state, SupplyParameter.EMISSION_RATE, year, mode)
        .filter(pl.col(VALUE_COL) != 0)
        .select(
            REGION,
            pl.col(TECHNOLOGY).alias(PRODUCER),
            POLLUTANT,
            pl.col(VALUE_COL).alias(PRODUCER_EMISSION_RATE),
        )
    )
    return (
        prices.select(REGION, FUEL, PRODUCER, OUTPUT_RATIO)
        .join(rates, on=[REGION, PRODUCER])
        .with_columns(
            (pl.col(PRODUCER_EMISSION_RATE) / pl.col(OUTPUT_RATIO)).alias(EMISSION_RATE_PER_OUTPUT)
        )
        .select(
            REGION,
            FUEL,
            PRODUCER,
            POLLUTANT,
            OUTPUT_RATIO,
            PRODUCER_EMISSION_RATE,
            EMISSION_RATE_PER_OUTPUT,
        )
    )
