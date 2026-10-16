"""The price and the emission rates of a fuel, from the technology that produces it.

A technology pays for each fuel that it takes in at the price of the producer of that fuel. The
producer is the cheapest `fuel_supply` technology that puts the fuel out in the region of the
technology, at the operations mode. A fuel balances in one region and has one location, so
that producer makes the fuel at the place where the technology takes it in. A technology of any
other kind, for example a pipeline, is not a producer. A producer whose activity upper limit in
the year is zero makes nothing, so it is not a producer either.

Each value stays in the units of the model: currency and emissions per energy unit of the fuel.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import NamedTuple

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
from interop.plugins.shared.osemosys_sienna_constants import SupplyParameter
from interop.plugins.shared.osemosys_sienna_translations._canonical import (
    read_annotations,
    read_mode_parameter,
    read_parameter_with_defaults,
)

INPUT_RATIO = "input_ratio"
PRODUCER = "producer"
PRODUCER_COUNT = "producer_count"
PRODUCER_COST = "producer_cost"
OUTPUT_RATIO = "output_ratio"
COST_PER_OUTPUT = "cost_per_output"
PRODUCER_EMISSION_RATE = "producer_emission_rate"
EMISSION_RATE_PER_OUTPUT = "emission_rate_per_output"

# The activity upper limit that OSeMOSYS reads as no limit.
_NO_LIMIT = -1.0

_PRICES_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    REGION: pl.Utf8,
    FUEL: pl.Utf8,
    PRODUCER: pl.Utf8,
    PRODUCER_COUNT: pl.Int64,
    PRODUCER_COST: pl.Float64,
    OUTPUT_RATIO: pl.Float64,
    COST_PER_OUTPUT: pl.Float64,
}


class FuelProducer(NamedTuple):
    """One `fuel_supply` technology that puts out a fuel, and its variable cost at the mode."""

    technology: str
    variable_cost: float
    output_ratio: float

    @property
    def cost_per_output(self) -> float:
        return self.variable_cost / self.output_ratio


@dataclass(frozen=True)
class FuelSupply:
    """The producer of each fuel that has one, and the emission rates of those producers.

    `prices` holds one row for each region and fuel, with the chosen producer, the number of
    producers it was chosen from and its cost per unit of the fuel. `emission_rates` holds one
    row for each region, fuel and pollutant of a producer that emits.
    """

    prices: pl.DataFrame
    emission_rates: pl.DataFrame


def choose_fuel_producer(producers: Sequence[FuelProducer]) -> FuelProducer | None:
    """The producer with the lowest variable cost for each unit of the fuel, or None.

    Two producers at one cost go to the first name, so the choice does not depend on row order.
    """
    return min(producers, key=lambda one: (one.cost_per_output, one.technology), default=None)


def build_fuel_supply(state: State, year: int, mode: str) -> FuelSupply:
    candidates = _read_candidates(state, year, mode)
    prices = _build_prices(candidates)
    return FuelSupply(prices, _read_emission_rates(state, year, mode, prices))


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
    """Each fuel that a `fuel_supply` technology puts out, with the cost of that technology."""
    suppliers = _read_suppliers(state, year)
    outputs = (
        read_mode_parameter(state, FlowParameter.OUTPUT_ACTIVITY_RATIO, year, mode)
        .filter(pl.col(VALUE_COL) > 0)
        .join(suppliers.select(REGION, TECHNOLOGY), on=[REGION, TECHNOLOGY], how="semi")
        .select(REGION, TECHNOLOGY, FUEL, pl.col(VALUE_COL).alias(OUTPUT_RATIO))
    )
    keys = outputs.select(REGION, TECHNOLOGY, pl.lit(mode).alias(OPERATING_MODE)).unique()
    costs = read_parameter_with_defaults(
        state, SupplyParameter.VARIABLE_OPERATION_COST, year, keys
    ).select(REGION, TECHNOLOGY, pl.col(VALUE_COL).fill_null(0.0).alias(PRODUCER_COST))
    return outputs.join(costs, on=[REGION, TECHNOLOGY])


def _read_suppliers(state: State, year: int) -> pl.DataFrame:
    """Each `fuel_supply` technology, except one whose activity limit of the year is zero."""
    suppliers = read_annotations(state, TECHNOLOGY).filter(
        pl.col(AnnotationColumn.KIND) == TechnologyKind.FUEL_SUPPLY
    )
    limits = read_parameter_with_defaults(
        state, SupplyParameter.ACTIVITY_UPPER_LIMIT, year, suppliers.select(REGION, TECHNOLOGY)
    )
    return limits.filter(pl.col(VALUE_COL).fill_null(_NO_LIMIT) != 0).select(REGION, TECHNOLOGY)


def _build_prices(candidates: pl.DataFrame) -> pl.DataFrame:
    rows = []
    for (region, fuel), group in candidates.sort(REGION, FUEL).group_by(
        [REGION, FUEL], maintain_order=True
    ):
        producers = [
            FuelProducer(*row)
            for row in group.select(TECHNOLOGY, PRODUCER_COST, OUTPUT_RATIO).iter_rows()
        ]
        chosen = choose_fuel_producer(producers)
        if chosen is not None:
            rows.append(_build_price_row(str(region), str(fuel), chosen, len(producers)))
    return pl.DataFrame(rows, schema=_PRICES_SCHEMA)


def _build_price_row(
    region: str, fuel: str, chosen: FuelProducer, count: int
) -> dict[str, str | int | float]:
    return {
        REGION: region,
        FUEL: fuel,
        PRODUCER: chosen.technology,
        PRODUCER_COUNT: count,
        PRODUCER_COST: chosen.variable_cost,
        OUTPUT_RATIO: chosen.output_ratio,
        COST_PER_OUTPUT: chosen.cost_per_output,
    }


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
        .select(REGION, FUEL, PRODUCER, POLLUTANT, PRODUCER_EMISSION_RATE, EMISSION_RATE_PER_OUTPUT)
    )
