"""The columns of the generators table, which both routes to a technology fill.

A Sienna generator fills one row, and a `generator` record of a fuel that is not electricity
fills another, because Sienna holds electricity only. Every step after the two routes reads
these columns alone, so it needs to know neither route.
"""

from __future__ import annotations

import polars as pl

from interop.plugins.shared.constants import EXTENSIONS_PREFIX
from interop.plugins.shared.osemosys_canonical.constants import FUEL, REGION, TECHNOLOGY
from interop.plugins.shared.sienna_constants import (
    SiennaComponent,
    SiennaGeneratorCol,
    SiennaSeriesName,
    SiennaStructField,
)

# The mode that the component or the record runs, which the sidecar states by leaving it out.
HELD_MODE = "held_mode"
# MW. The capacity that already runs, which OSeMOSYS states as ResidualCapacity.
BASE_POWER_MW = "base_power_mw"
# The field that BASE_POWER_MW comes from, which differs by route.
BASE_POWER_ATTRIBUTE = "base_power_attribute"
# MW. What one value of the staged series of the generator stands for.
CAPACITY_MW = "capacity_mw"
# The field that CAPACITY_MW comes from, which differs by Sienna type.
CAPACITY_ATTRIBUTE = "capacity_attribute"
# The region and the fuel of the bus of the generator, under names that no Sienna field has.
BUS_REGION = "bus_region"
BUS_FUEL = "bus_fuel"
# The Sienna type, or the record kind, that an event names as the source of the technology.
SOURCE_COMPONENT = "source_component"
# $/MWh. What one MWh of the technology costs, where the source states a cost.
VARIABLE_COST_MWH = "variable_cost_mwh"
# The field that VARIABLE_COST_MWH comes from, which an event names.
COST_ATTRIBUTE = "cost_attribute"
# Per unit of a whole year. Only a technology that no Sienna component holds states one.
AVAILABILITY = "availability"

# The field of a Sienna generator that states what one MWh of its electricity costs.
CURVE_COST_ATTRIBUTE = (
    f"{SiennaGeneratorCol.OPERATION_COST}.{SiennaStructField.VARIABLE_OPERATION_COST}"
)
# The field of a Sienna generator that states the megawatts it can put out.
OUTPUT_LIMIT_ATTRIBUTE = f"{SiennaGeneratorCol.ACTIVE_POWER_LIMITS}.{SiennaStructField.MAX}"
# The record fields that a technology which no Sienna component holds comes from.
RECORD_BUS_ATTRIBUTE = f"{EXTENSIONS_PREFIX}bus"
RECORD_CAPACITY_ATTRIBUTE = f"{EXTENSIONS_PREFIX}p_nom"
RECORD_COST_ATTRIBUTE = f"{EXTENSIONS_PREFIX}marginal_cost"
RECORD_AVAILABILITY_ATTRIBUTE = f"{EXTENSIONS_PREFIX}p_max_pu"

# The staged series that holds the hourly shape of a generator, by the type that owns each.
GENERATOR_SERIES_KEYS = (
    (SiennaComponent.THERMAL_STANDARD, SiennaSeriesName.MAX_ACTIVE_POWER),
    (SiennaComponent.RENEWABLE_DISPATCH, SiennaSeriesName.MAX_ACTIVE_POWER),
    (SiennaComponent.RENEWABLE_NON_DISPATCH, SiennaSeriesName.MAX_ACTIVE_POWER),
    (SiennaComponent.HYDRO_DISPATCH, SiennaSeriesName.MAX_ACTIVE_POWER),
    (SiennaComponent.HYDRO_TURBINE, SiennaSeriesName.MAX_ACTIVE_POWER),
)
# The Sienna types whose series is a share of their rating rather than of another capacity.
RATED_BY_RATING = (SiennaComponent.RENEWABLE_DISPATCH, SiennaComponent.RENEWABLE_NON_DISPATCH)
# The Sienna types whose series is a share of their base power.
RATED_BY_BASE_POWER = (SiennaComponent.HYDRO_DISPATCH, SiennaComponent.HYDRO_TURBINE)

GENERATORS_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    TECHNOLOGY: pl.Utf8,
    REGION: pl.Utf8,
    FUEL: pl.Utf8,
    HELD_MODE: pl.Utf8,
    BASE_POWER_MW: pl.Float64,
    BASE_POWER_ATTRIBUTE: pl.Utf8,
    CAPACITY_MW: pl.Float64,
    CAPACITY_ATTRIBUTE: pl.Utf8,
    VARIABLE_COST_MWH: pl.Float64,
    COST_ATTRIBUTE: pl.Utf8,
    AVAILABILITY: pl.Float64,
    SOURCE_COMPONENT: pl.Utf8,
}

NO_BASE_POWER_NOTE = (
    "OSeMOSYS states the share of a fleet that a technology can use, so a generator of no "
    "base power has no fleet to take a share of and is left out"
)
NO_CAPACITY_NOTE = (
    "OSeMOSYS states the share of a fleet that a technology can use, so a generator record of "
    "no p_nom has no fleet to take a share of and is left out"
)
# What a warning counts, and what it says a generator with no capacity did.
GENERATOR_COUNTED_NOUN = "generator(s)"
NO_BASE_POWER_REASON = "state no base power"
NO_CAPACITY_REASON = "state no capacity"
