"""The bounds that OSeMOSYS puts on the activity of a technology in a year, in MWh of electricity.

An operations system has no field for an annual energy bound, so the extension record of the
component holds the bound of each year. A bound on activity is a bound on electricity × the
electricity ratio of that year at the mode that rates the component: the output of a generator
and of a storage, and the input of a line and of a conversion.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, NamedTuple

import polars as pl

from interop.core.extensions import ByYear
from interop.core.pipeline import State
from interop.plugins.shared.constants import EXTENSIONS_PREFIX, UNIT_MWH
from interop.plugins.shared.osemosys_canonical.constants import (
    FUEL,
    OPERATING_MODE,
    REGION,
    TECHNOLOGY,
    VALUE_COL,
    YEAR,
    FlowParameter,
)
from interop.plugins.shared.osemosys_sienna_constants import SupplyParameter
from interop.plugins.shared.osemosys_sienna_translations._buses import read_electricity_fuels
from interop.plugins.shared.osemosys_sienna_translations._canonical import (
    read_parameter_all_years,
    read_parameter_for_years,
)
from interop.plugins.shared.osemosys_sienna_translations._events import (
    build_osemosys_field,
    build_sienna_field,
)
from interop.plugins.shared.osemosys_sienna_translations._operations import OperationsYear
from interop.plugins.shared.osemosys_sienna_translations._persisted import set_persisted_rows
from interop.plugins.shared.osemosys_sienna_translations._technology_values import (
    ValueOwners,
)
from interop.plugins.shared.osemosys_sienna_translations._units import express_converted
from interop.ports.outbound.reporting import EventKind, TranslationEvent

LIMIT = "limit"
YEAR_RATIO = "year_ratio"
LIMIT_MWH = "limit_mwh"

_KEYS = [REGION, TECHNOLOGY]


class ActivityBound(NamedTuple):
    """One annual activity parameter, the column that lists its bounds, what binds, and the
    field of the extension record that holds it."""

    parameter: SupplyParameter
    column: str
    binds: pl.Expr
    extension_field: str


# A lower limit of 0 and a negative upper limit bind nothing, as OSeMOSYS states them.
LOWER_BOUND = ActivityBound(
    SupplyParameter.ACTIVITY_LOWER_LIMIT,
    "activity_lower_limits",
    pl.col(LIMIT) > 0,
    "e_sum_min",
)
UPPER_BOUND = ActivityBound(
    SupplyParameter.ACTIVITY_UPPER_LIMIT,
    "activity_upper_limits",
    pl.col(LIMIT) >= 0,
    "e_sum_max",
)
ACTIVITY_BOUNDS = (LOWER_BOUND, UPPER_BOUND)


def enrich_activity_limits(
    state: State, operations: OperationsYear, rated: pl.DataFrame, flow: FlowParameter
) -> pl.DataFrame:
    """One list of yearly bounds for each annual activity parameter, null when none binds.

    `rated` holds `region`, `technology` and the `operating_mode` whose electricity `flow`
    rates the technology.
    """
    for bound in ACTIVITY_BOUNDS:
        listed = _list_bounds(state, rated, flow, bound, operations)
        rated = rated.join(listed, on=_KEYS, how="left")
    return rated


def build_yearly_limits(bounds: list[dict[str, Any]] | None) -> ByYear | None:
    """The bound of each year in MWh, keyed by the year, or None when no year binds."""
    if not bounds:
        return None
    return {int(bound[YEAR]): bound[LIMIT_MWH] for bound in bounds}


def build_bound_events(
    row: dict[str, Any], owners: ValueOwners, flow: FlowParameter
) -> list[TranslationEvent]:
    """One event for each bound that the record of one row holds."""
    return [
        _build_bound_event(row, owners, flow, bound)
        for bound in ACTIVITY_BOUNDS
        if row[bound.column]
    ]


def set_bounds_persisted(state: State, owners: ValueOwners, rated: pl.DataFrame) -> None:
    """Note that the records of `owners.kind` hold the annual activity bounds of `rated`."""
    for bound in ACTIVITY_BOUNDS:
        set_persisted_rows(
            state, owners.kind, bound.parameter, [rated.select(_KEYS)], bound.extension_field
        )


def _list_bounds(
    state: State,
    rated: pl.DataFrame,
    flow: FlowParameter,
    bound: ActivityBound,
    operations: OperationsYear,
) -> pl.DataFrame:
    stated = _read_stated_bounds(state, rated, bound)
    ratios = _read_year_ratios(state, rated, flow, stated[YEAR].unique().to_list())
    joined = stated.join(ratios, on=[*_KEYS, YEAR], how="left").with_columns(
        pl.col(YEAR_RATIO).fill_null(0.0)
    )
    energy = express_converted(joined, LIMIT, operations.units.convert_energy_to_mwh)
    return (
        joined.with_columns((energy * pl.col(YEAR_RATIO)).alias(LIMIT_MWH))
        .sort(YEAR)
        .group_by(_KEYS)
        .agg(pl.struct(YEAR, LIMIT, YEAR_RATIO, LIMIT_MWH).alias(bound.column))
    )


def _read_stated_bounds(state: State, rated: pl.DataFrame, bound: ActivityBound) -> pl.DataFrame:
    """The rows of the technologies in every year, which a parameter table holds a few of."""
    return (
        read_parameter_all_years(state, bound.parameter, rated.select(_KEYS).unique())
        .select(*_KEYS, YEAR, pl.col(VALUE_COL).cast(pl.Float64).alias(LIMIT))
        .filter(bound.binds)
    )


def _read_year_ratios(
    state: State, rated: pl.DataFrame, flow: FlowParameter, years: Sequence[str]
) -> pl.DataFrame:
    """The electricity of the flow at the rated mode of each technology, in each year."""
    electricity = read_electricity_fuels(state).select(REGION, FUEL)
    return (
        read_parameter_for_years(state, flow, [int(year) for year in years])
        .join(rated.select(*_KEYS, OPERATING_MODE), on=[*_KEYS, OPERATING_MODE], how="semi")
        .join(electricity, on=[REGION, FUEL], how="semi")
        .group_by(*_KEYS, YEAR)
        .agg(pl.col(VALUE_COL).cast(pl.Float64).sum().alias(YEAR_RATIO))
    )


def _build_bound_event(
    row: dict[str, Any], owners: ValueOwners, flow: FlowParameter, bound: ActivityBound
) -> TranslationEvent:
    """One event for each component and bound, which reads the bound and ratio of each year."""
    member = row[owners.report_col]
    sources = [
        source
        for year in row[bound.column]
        for source in (
            build_osemosys_field(bound.parameter, member, f"{YEAR} {year[YEAR]}", year[LIMIT]),
            build_osemosys_field(
                flow, member, f"{_RATED_ATTRIBUTE}, {YEAR} {year[YEAR]}", year[YEAR_RATIO]
            ),
        )
    ]
    destination = build_sienna_field(
        row[owners.component_col],
        row[owners.name_col],
        f"{EXTENSIONS_PREFIX}{bound.extension_field}",
        build_yearly_limits(row[bound.column]),
        UNIT_MWH,
    )
    return TranslationEvent(
        kind=EventKind.VALUE_DERIVED,
        sources=sources,
        destinations=[destination],
        derivation=_BOUND_DERIVATION.format(parameter=bound.parameter, flow=flow),
    )


_RATED_ATTRIBUTE = "electricity at the rated mode"
_BOUND_DERIVATION = (
    "the {parameter} of each year, in MWh, × the electricity {flow} of that year at the mode "
    "that rates the component; a Sienna operations system has no field for an annual energy "
    "bound"
)
