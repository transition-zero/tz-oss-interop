"""The ratings, the levels and the costs of each storage, in Sienna units.

The base power is the residual capacity of the discharging technology in MW × its electricity
output ratio at the discharge mode. Each side of the storage, its charge and its discharge, gives
one power limit: its derated capacity, capped by the grid side of its rate. Each cost is the
variable cost of the technology at the mode of its side, plus the emission penalty of each
pollutant that it emits there, for each MWh of electricity.
"""

from __future__ import annotations

from collections.abc import Callable

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.constants import HOURS_PER_YEAR
from interop.plugins.shared.osemosys_canonical.constants import (
    OPERATING_MODE,
    POLLUTANT,
    REGION,
    STORAGE,
    TECHNOLOGY,
    VALUE_COL,
)
from interop.plugins.shared.osemosys_sienna_constants import (
    NO_COST,
    WHOLE_CAPACITY,
    StorageParameter,
    SupplyParameter,
)
from interop.plugins.shared.osemosys_sienna_translations._activity import (
    ELECTRICITY_OUTPUT_RATIO,
)
from interop.plugins.shared.osemosys_sienna_translations._canonical import (
    read_parameter,
    read_parameter_with_defaults,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_emissions import (
    PENALTY,
    RATE_T_PER_MWH,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_penalties import (
    PENALTY_COST_MWH,
    build_penalty_terms,
)
from interop.plugins.shared.osemosys_sienna_translations._operations import OperationsYear
from interop.plugins.shared.osemosys_sienna_translations._storage_columns import (
    CHARGE_SIDE,
    DISCHARGE_SIDE,
    EFFICIENCY_IN,
    EFFICIENCY_OUT,
    ENERGY,
    ENERGY_MWH,
    INITIAL_LEVEL,
    LEVEL_MWH,
    LEVEL_START,
    MIN_LEVEL,
    POWER_MW,
    STATED_RATE,
    STORAGE_HOURS,
    STORAGE_SIDES,
    StorageSide,
)
from interop.plugins.shared.osemosys_sienna_translations._technologies import (
    VARIABLE_COST,
    read_variable_costs,
)
from interop.plugins.shared.osemosys_sienna_translations._technology_costs import (
    FIXED_COST,
    FIXED_COST_MW_YEAR,
    enrich_fixed_costs,
)
from interop.plugins.shared.osemosys_sienna_translations._units import (
    ModelUnits,
    express_converted,
)

_STORAGE_KEYS = [REGION, STORAGE]
_MODE_KEYS = [REGION, TECHNOLOGY, OPERATING_MODE]
_EMPTY = 0.0


def enrich_ratings(
    state: State, operations: OperationsYear, storages: pl.DataFrame
) -> pl.DataFrame:
    """Power in MW of electricity, energy in MWh, and each limit in terms of the base power.

    The availability factor of a technology derates its power, and a stated rate of charge or
    discharge caps it.
    """
    units = operations.units
    table = _enrich_rates(state, operations, storages)
    table = table.with_columns(
        _express_activity_mw(table, units, side).alias(side.activity_mw) for side in STORAGE_SIDES
    ).with_columns(
        (pl.col(DISCHARGE_SIDE.activity_mw) * pl.col(DISCHARGE_SIDE.ratio)).alias(POWER_MW),
        units.convert_energy_to_mwh(pl.col(ENERGY)).alias(ENERGY_MWH),
    )
    return table.with_columns(
        *(_express_limit(side).alias(side.limit) for side in STORAGE_SIDES),
        (pl.col(ENERGY_MWH) / pl.col(POWER_MW)).alias(STORAGE_HOURS),
        (pl.col(CHARGE_SIDE.link_value) / pl.col(CHARGE_SIDE.ratio)).alias(EFFICIENCY_IN),
        (pl.col(DISCHARGE_SIDE.ratio) / pl.col(DISCHARGE_SIDE.link_value)).alias(EFFICIENCY_OUT),
    )


def enrich_levels(state: State, operations: OperationsYear, storages: pl.DataFrame) -> pl.DataFrame:
    """The level at the start and the lowest level, each as a share of the energy."""
    start = _read_storage_values(state, operations, storages, StorageParameter.STORAGE_LEVEL_START)
    minimum = _read_storage_values(state, operations, storages, StorageParameter.MIN_STORAGE_CHARGE)
    table = storages.join(start.rename({VALUE_COL: LEVEL_START}), on=_STORAGE_KEYS).join(
        minimum.rename({VALUE_COL: MIN_LEVEL}), on=_STORAGE_KEYS
    )
    level = express_converted(table, LEVEL_START, operations.units.convert_energy_to_mwh)
    return table.with_columns(level.alias(LEVEL_MWH)).with_columns(
        (pl.col(LEVEL_MWH) / pl.col(ENERGY_MWH)).clip(_EMPTY, WHOLE_CAPACITY).alias(INITIAL_LEVEL),
        pl.col(MIN_LEVEL).clip(_EMPTY, WHOLE_CAPACITY),
    )


def enrich_costs(state: State, operations: OperationsYear, storages: pl.DataFrame) -> pl.DataFrame:
    """The cost of each MWh drawn at the charge mode, and of each MWh put out at the other: the
    variable cost of the mode, and the emission penalty of each pollutant that it emits."""
    table = storages
    for side in STORAGE_SIDES:
        table = table.join(_read_mode_costs(state, operations, storages, side), on=side.mode_keys)
        table = _enrich_penalties(state, operations, table, side)
    convert = operations.units.convert_cost_per_energy_to_dollars_per_mwh
    return table.with_columns(
        (
            express_converted(table, side.cost, convert) / pl.col(side.ratio)
            + pl.col(side.penalty_mwh)
        ).alias(side.cost_mwh)
        for side in STORAGE_SIDES
    )


def enrich_storage_fixed_costs(
    state: State, operations: OperationsYear, storages: pl.DataFrame
) -> pl.DataFrame:
    """The fixed cost of the discharging technology, in $ for each MW of output and year."""
    technologies = storages.select(
        *_STORAGE_KEYS,
        pl.col(DISCHARGE_SIDE.technology).alias(TECHNOLOGY),
        pl.col(DISCHARGE_SIDE.ratio).alias(ELECTRICITY_OUTPUT_RATIO),
    )
    costs = enrich_fixed_costs(state, operations, technologies)
    return storages.join(
        costs.select(*_STORAGE_KEYS, FIXED_COST, FIXED_COST_MW_YEAR), on=_STORAGE_KEYS
    )


def _express_activity_mw(table: pl.DataFrame, units: ModelUnits, side: StorageSide) -> pl.Expr:
    """MW of activity: the capacity × its yearly activity over 8760 h, or the capacity in the
    capacity unit where the model states no capacity_to_activity_unit."""
    capacity = pl.col(side.capacity)
    is_stated = pl.col(side.capacity_to_activity).is_not_null()
    yearly = capacity * pl.col(side.capacity_to_activity)
    stated = _convert_where(table, is_stated, yearly, units.convert_energy_to_mwh)
    unstated = _convert_where(table, ~is_stated, capacity, units.convert_capacity_to_mw)
    return pl.when(is_stated).then(stated / HOURS_PER_YEAR).otherwise(unstated)


def _convert_where(
    table: pl.DataFrame, rows: pl.Expr, value: pl.Expr, convert: Callable[[pl.Expr], pl.Expr]
) -> pl.Expr:
    """The value in Sienna units; a unit that no row of `rows` needs is not asked for."""
    is_needed = table.select(rows.any()).item()
    return convert(value) if is_needed else value


def _express_limit(side: StorageSide) -> pl.Expr:
    """The most power of one side, per unit of the base power.

    A rate caps the storage side, so the cap takes the grid side of that rate.
    """
    ratio = pl.col(side.ratio)
    derated = pl.col(side.activity_mw) * ratio * pl.col(side.availability)
    capped = pl.col(side.rate_mw) * ratio / pl.col(side.link_value)
    return pl.min_horizontal(derated, capped) / pl.col(POWER_MW)


def _enrich_rates(state: State, operations: OperationsYear, storages: pl.DataFrame) -> pl.DataFrame:
    """Each rate in MW, from energy in a year; a rate of zero states no limit, so it is null."""
    table = storages
    for side in STORAGE_SIDES:
        values = _read_storage_values(state, operations, storages, side.rate_parameter)
        table = table.join(values.rename({VALUE_COL: side.rate}), on=_STORAGE_KEYS)
    convert = operations.units.convert_energy_to_mwh
    return table.with_columns(
        _express_rate_mw(table, side.rate, convert).alias(side.rate_mw) for side in STORAGE_SIDES
    )


def _express_rate_mw(
    table: pl.DataFrame, column: str, convert: Callable[[pl.Expr], pl.Expr]
) -> pl.Expr:
    rate = express_converted(table, column, convert) / HOURS_PER_YEAR
    return pl.when(pl.col(column) > 0).then(rate)


def _read_storage_values(
    state: State, operations: OperationsYear, storages: pl.DataFrame, parameter: str
) -> pl.DataFrame:
    keys = storages.select(_STORAGE_KEYS)
    stated = read_parameter_with_defaults(state, parameter, operations.year, keys)
    return stated.select(*_STORAGE_KEYS, pl.col(VALUE_COL).cast(pl.Float64).fill_null(_EMPTY))


def _read_mode_costs(
    state: State, operations: OperationsYear, storages: pl.DataFrame, side: StorageSide
) -> pl.DataFrame:
    keys = storages.select(
        REGION,
        pl.col(side.technology).alias(TECHNOLOGY),
        pl.col(side.mode).alias(OPERATING_MODE),
    ).unique()
    return read_variable_costs(state, operations.year, keys).select(
        REGION,
        pl.col(TECHNOLOGY).alias(side.technology),
        pl.col(OPERATING_MODE).alias(side.mode),
        pl.col(VARIABLE_COST).alias(side.cost),
    )


def _enrich_penalties(
    state: State, operations: OperationsYear, storages: pl.DataFrame, side: StorageSide
) -> pl.DataFrame:
    """The emission penalty of each pollutant at the mode of one side, in $/MWh of electricity."""
    priced = build_penalty_terms(
        state, operations, _read_mode_rates(state, operations, storages, side)
    )
    term = pl.struct(POLLUTANT, STATED_RATE, RATE_T_PER_MWH, PENALTY, PENALTY_COST_MWH)
    listed = (
        priced.sort(POLLUTANT)
        .group_by(side.mode_keys)
        .agg(term.alias(side.penalty_terms), pl.col(PENALTY_COST_MWH).sum().alias(side.penalty_mwh))
    )
    return storages.join(listed, on=side.mode_keys, how="left").with_columns(
        pl.col(side.penalty_mwh).fill_null(NO_COST)
    )


def _read_mode_rates(
    state: State, operations: OperationsYear, storages: pl.DataFrame, side: StorageSide
) -> pl.DataFrame:
    """The emission rate of each pollutant at the mode of one side, in t/MWh of electricity."""
    modes = storages.select(
        REGION,
        pl.col(side.technology).alias(TECHNOLOGY),
        pl.col(side.mode).alias(OPERATING_MODE),
        side.ratio,
    ).unique()
    rates = (
        read_parameter(state, SupplyParameter.EMISSION_RATE, operations.year)
        .filter(pl.col(VALUE_COL) != 0)
        .join(modes.lazy(), on=_MODE_KEYS)
        .select(
            REGION,
            pl.col(TECHNOLOGY).alias(side.technology),
            pl.col(OPERATING_MODE).alias(side.mode),
            POLLUTANT,
            side.ratio,
            pl.col(VALUE_COL).cast(pl.Float64).alias(STATED_RATE),
        )
        .collect()
    )
    convert = operations.units.convert_emissions_per_energy_to_tonnes_per_mwh
    rate = express_converted(rates, STATED_RATE, convert) / pl.col(side.ratio)
    return rates.with_columns(rate.alias(RATE_T_PER_MWH))
