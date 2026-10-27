"""The emission limits of each pollutant of each region, over a set of years.

OSeMOSYS adds `annual_exogenous_emission` to the emissions that an annual limit holds, so the
net limit of a year is the limit less that emission, in t. The limit over the whole model
period nets its own exogenous emission the same way. A pollutant covers the whole model when
each technology that emits any pollutant emits it.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import NamedTuple

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.osemosys_canonical.constants import (
    POLLUTANT,
    REGION,
    TECHNOLOGY,
    VALUE_COL,
    YEAR,
)
from interop.plugins.shared.osemosys_sienna_constants import (
    NO_LIMIT,
    EmissionParameter,
    SupplyParameter,
)
from interop.plugins.shared.osemosys_sienna_translations._canonical import (
    list_set_members,
    read_parameter_for_years,
    read_parameter_with_defaults,
    read_yearly_values,
)
from interop.plugins.shared.osemosys_sienna_translations._names import (
    express_component_name,
    express_report_name,
)
from interop.plugins.shared.osemosys_sienna_translations._units import (
    ModelUnits,
    express_converted,
)

# The columns of the pollutant table, in OSeMOSYS words.
POLLUTANT_NAME = "pollutant_name"
POLLUTANT_REPORT_NAME = "pollutant_report_name"
EMITTERS = "emitters"
COVERS_MODEL = "covers_model"
ANNUAL_LIMIT = EmissionParameter.ANNUAL_EMISSION_LIMIT.value
EXOGENOUS = EmissionParameter.ANNUAL_EXOGENOUS_EMISSION.value
PERIOD_LIMIT = EmissionParameter.MODEL_PERIOD_EMISSION_LIMIT.value
PERIOD_EXOGENOUS = EmissionParameter.MODEL_PERIOD_EXOGENOUS_EMISSION.value
NET_LIMIT_T = "net_limit_t"
PERIOD_NET_LIMIT_T = "period_net_limit_t"

POLLUTANT_KEYS = [REGION, POLLUTANT]
_HAS_LIMIT = "has_limit"
_NO_EMISSION = 0.0


class NetLimit(NamedTuple):
    """The columns of a stated limit, of its exogenous emission and of the net limit in t."""

    limit: str
    exogenous: str
    net: str


class LimitScope(NamedTuple):
    """The years in scope, in order, and the units that the model states its values in."""

    years: Sequence[int]
    units: ModelUnits


ANNUAL_NET_LIMIT = NetLimit(ANNUAL_LIMIT, EXOGENOUS, NET_LIMIT_T)
PERIOD_NET_LIMIT = NetLimit(PERIOD_LIMIT, PERIOD_EXOGENOUS, PERIOD_NET_LIMIT_T)


def read_pollutants(state: State, years: Sequence[int]) -> pl.DataFrame:
    """Each pollutant of each region, with the technologies that emit it in some year."""
    regions = pl.DataFrame({REGION: list_set_members(state, REGION)}, schema={REGION: pl.Utf8})
    members = pl.DataFrame(
        {POLLUTANT: list_set_members(state, POLLUTANT)}, schema={POLLUTANT: pl.Utf8}
    )
    rates = (
        read_parameter_for_years(state, SupplyParameter.EMISSION_RATE, years)
        .lazy()
        .filter(pl.col(VALUE_COL) != 0)
        .select(*POLLUTANT_KEYS, TECHNOLOGY)
        .unique()
        .collect()
    )
    emitters = rates.group_by(POLLUTANT_KEYS).agg(
        pl.col(TECHNOLOGY).unique().sort().alias(EMITTERS)
    )
    all_emitters = rates.select(REGION, TECHNOLOGY).unique().height
    covers = (pl.col(EMITTERS).list.len() == all_emitters) & (all_emitters > 0)
    return (
        regions.join(members, how="cross")
        .join(emitters, on=POLLUTANT_KEYS, how="left")
        .with_columns(
            covers.fill_null(False).alias(COVERS_MODEL),  # noqa: FBT003
            express_component_name(POLLUTANT).alias(POLLUTANT_NAME),
            express_report_name(POLLUTANT).alias(POLLUTANT_REPORT_NAME),
        )
    )


def read_annual_limits(
    state: State, years: Sequence[int], units: ModelUnits, pollutants: pl.DataFrame
) -> pl.DataFrame:
    """Each year in which a pollutant has a limit, with the net limit in t."""
    scope = LimitScope(years, units)
    return read_net_limits(state, pollutants.select(POLLUTANT_KEYS), ANNUAL_NET_LIMIT, scope)


def enrich_period_limits(
    state: State, year: int, units: ModelUnits, pollutants: pl.DataFrame
) -> pl.DataFrame:
    """Add the limit over the whole model period, net of its exogenous emission, in t."""
    scope = LimitScope([year], units)
    limits = read_horizon_limits(state, pollutants.select(POLLUTANT_KEYS), PERIOD_NET_LIMIT, scope)
    return pollutants.join(limits, on=POLLUTANT_KEYS)


def read_net_limits(
    state: State, keys: pl.DataFrame, columns: NetLimit, scope: LimitScope
) -> pl.DataFrame:
    """Each year in which a key has a limit, with the net limit in t.

    `keys` holds the key columns of the two parameters other than `year`.
    """
    on = [*keys.columns, YEAR]
    limits = read_yearly_values(state, columns.limit, keys, scope.years).join(
        read_yearly_values(state, columns.exogenous, keys, scope.years), on=on
    )
    net = enrich_net_limit(limits, columns, scope.units)
    return net.filter(pl.col(columns.net).is_not_null()).sort(*on)


def read_horizon_limits(
    state: State, keys: pl.DataFrame, columns: NetLimit, scope: LimitScope
) -> pl.DataFrame:
    """The limit over the whole model period of each key, net of its exogenous emission, in t."""
    table = keys
    for name in (columns.limit, columns.exogenous):
        stated = read_parameter_with_defaults(state, name, scope.years[0], keys)
        table = table.join(
            stated.select(*keys.columns, pl.col(VALUE_COL).cast(pl.Float64).alias(name)),
            on=keys.columns,
        )
    return enrich_net_limit(table, columns, scope.units)


def enrich_net_limit(table: pl.DataFrame, columns: NetLimit, units: ModelUnits) -> pl.DataFrame:
    """Add the limit less its exogenous emission, in t. A limit of -1 or none gives no net limit."""
    limit = pl.col(columns.limit)
    net = limit - pl.col(columns.exogenous).fill_null(_NO_EMISSION)
    table = table.with_columns(pl.when(limit != NO_LIMIT).then(net).alias(columns.net))
    converted = express_converted(table, columns.net, units.convert_emissions_to_tonnes)
    return table.with_columns(converted.alias(columns.net))


def drop_unlimited(pollutants: pl.DataFrame, yearly: pl.DataFrame) -> pl.DataFrame:
    """The pollutants with a limit in some year, or over the whole model period."""
    annual = (
        yearly.select(POLLUTANT_KEYS).unique().with_columns(pl.lit(value=True).alias(_HAS_LIMIT))
    )
    table = pollutants.join(annual, on=POLLUTANT_KEYS, how="left")
    has_limit = pl.col(_HAS_LIMIT).fill_null(False) | pl.col(PERIOD_NET_LIMIT_T).is_not_null()  # noqa: FBT003
    return table.filter(has_limit).drop(_HAS_LIMIT)
