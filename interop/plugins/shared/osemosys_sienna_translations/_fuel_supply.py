"""The price and the emission rates of a fuel, from the technology that produces it.

A technology pays for each fuel that it takes in at the price of the producer of that fuel. The
producer is the `fuel_supply` technology with the lowest delivered cost that puts the fuel out
in the region of the technology, at the operations mode. The delivered cost of a unit of the
fuel is the variable cost of the producer and the penalty of its emissions, divided by its output
ratio, because OSeMOSYS minimises both terms. The price stays the variable cost alone, because
the technology pays the penalty of the producer emissions through its own emission rate.

A fuel balances in one region and has one location, so that producer makes the fuel at the place
where the technology takes it in. A technology of any other kind, for example a pipeline, is not
a producer. A producer whose activity upper limit in the year is zero makes nothing, and neither
does a producer with no capacity that can run in the year, so neither is a producer. A fuel whose
producers all make nothing is stranded.

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
from interop.plugins.shared.osemosys_sienna_constants import NO_COST, NO_LIMIT, SupplyParameter
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
# The variable cost and the emission penalty of a producer, for each unit of its activity.
PRODUCER_DELIVERED_COST = "producer_delivered_cost"
_DELIVERED_COST_PER_OUTPUT = "delivered_cost_per_output"
_PENALTY_COST = "penalty_cost"
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
    runnable = _enrich_delivered_costs(state, year, mode, candidates.filter(pl.col(IS_RUNNABLE)))
    prices = _build_prices(runnable)
    emission_rates = _read_emission_rates(state, year, mode, prices)
    return FuelSupply(prices, emission_rates, _list_stranded_fuels(candidates))


def read_input_ratios(
    state: State, year: int, mode: str, technologies: pl.DataFrame
) -> pl.DataFrame:
    """Each fuel that a technology of `technologies` takes in at the mode, with its ratio."""
    return (
        read_mode_parameter(state, FlowParameter.INPUT_ACTIVITY_RATIO, year, mode)
        .filter(pl.col(VALUE_COL) > 0)
        .join(technologies.select(REGION, TECHNOLOGY).lazy(), on=[REGION, TECHNOLOGY], how="semi")
        .select(REGION, TECHNOLOGY, FUEL, pl.col(VALUE_COL).alias(INPUT_RATIO))
        .collect()
    )


def _read_candidates(state: State, year: int, mode: str) -> pl.DataFrame:
    """Each fuel that a `fuel_supply` technology puts out, with its cost and whether it runs."""
    suppliers = _read_suppliers(state, year)
    outputs = (
        read_mode_parameter(state, FlowParameter.OUTPUT_ACTIVITY_RATIO, year, mode)
        .filter(pl.col(VALUE_COL) > 0)
        .join(suppliers.lazy(), on=_KEYS)
        .select(*_KEYS, FUEL, pl.col(VALUE_COL).alias(OUTPUT_RATIO), IS_RUNNABLE)
        .collect()
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


def _enrich_delivered_costs(
    state: State, year: int, mode: str, candidates: pl.DataFrame
) -> pl.DataFrame:
    """Each candidate with its variable cost and the penalty of its emissions, in model units."""
    penalties = _read_penalty_costs(state, year, mode, candidates.select(_KEYS).unique())
    return (
        candidates.join(penalties, on=_KEYS, how="left")
        .with_columns(pl.col(_PENALTY_COST).fill_null(NO_COST))
        .with_columns(
            (pl.col(PRODUCER_COST) + pl.col(_PENALTY_COST)).alias(PRODUCER_DELIVERED_COST)
        )
        .drop(_PENALTY_COST)
    )


def _read_penalty_costs(
    state: State, year: int, mode: str, producers: pl.DataFrame
) -> pl.DataFrame:
    """The sum of emission rate × emission penalty of each producer with a penalised pollutant."""
    rates = (
        read_mode_parameter(state, SupplyParameter.EMISSION_RATE, year, mode)
        .filter(pl.col(VALUE_COL) != 0)
        .join(producers.lazy(), on=_KEYS, how="semi")
        .select(*_KEYS, POLLUTANT, pl.col(VALUE_COL).alias(_PENALTY_COST))
        .collect()
    )
    keys = rates.select(REGION, POLLUTANT).unique()
    penalties = read_parameter_with_defaults(state, SupplyParameter.EMISSION_PENALTY, year, keys)
    return (
        rates.join(penalties.drop_nulls(VALUE_COL), on=[REGION, POLLUTANT])
        .group_by(_KEYS)
        .agg((pl.col(_PENALTY_COST) * pl.col(VALUE_COL).cast(pl.Float64)).sum())
    )


def _build_prices(candidates: pl.DataFrame) -> pl.DataFrame:
    """The producer with the lowest delivered cost for each unit of each fuel.

    Two producers at one cost go to the first name, so the choice does not depend on row order.
    """
    cost = (pl.col(PRODUCER_COST) / pl.col(OUTPUT_RATIO)).alias(COST_PER_OUTPUT)
    delivered = pl.col(PRODUCER_DELIVERED_COST) / pl.col(OUTPUT_RATIO)
    return (
        candidates.with_columns(cost, delivered.alias(_DELIVERED_COST_PER_OUTPUT))
        .sort(REGION, FUEL, _DELIVERED_COST_PER_OUTPUT, TECHNOLOGY)
        .group_by(REGION, FUEL, maintain_order=True)
        .agg(
            pl.col(TECHNOLOGY).first().alias(PRODUCER),
            pl.len().cast(pl.Int64).alias(PRODUCER_COUNT),
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
        .collect()
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
