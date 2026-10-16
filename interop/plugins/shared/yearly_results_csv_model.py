"""The members of the model that an OSeMOSYS results CSV names, read from the canonical stage.

The name of each member is built once from the whole set, so that one member has one name in
every variable, as in the Sienna translation of the same model.
"""

from __future__ import annotations

from typing import NamedTuple

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.osemosys_canonical.canonical_stage import build_table_key
from interop.plugins.shared.osemosys_canonical.constants import (
    ELECTRICITY_CARRIER,
    FUEL,
    OPERATING_MODE,
    POLLUTANT,
    REGION,
    TECHNOLOGY,
    VALUE_COL,
    YEAR,
    AnnotationColumn,
    FlowParameter,
    TableKind,
)
from interop.plugins.shared.osemosys_sienna_translations._canonical import (
    find_parameter_default,
    list_set_members,
)
from interop.plugins.shared.osemosys_sienna_translations._names import express_component_name

# The column that holds the results component name of a member.
COMPONENT = "component"
# The column that holds the output ratio of a technology onto all its electricity fuels.
RATIO = "ratio"

_STATED_COUNT = "stated_count"
_FUEL_COUNT = "fuel_count"
_NO_DEFAULT = 0.0


class ElectricityRatios(NamedTuple):
    """`stated` holds, for each technology, mode and year that the model states, the sum of the
    stated output ratios onto electricity fuels and how many electricity fuels it covers. Each
    other electricity fuel of the region takes `default`."""

    stated: pl.DataFrame
    fuel_counts: pl.DataFrame
    default: float


class ResultsModel(NamedTuple):
    """`technologies` holds region, technology, component, category and kind; `pollutants`
    holds region, pollutant and component."""

    technologies: pl.DataFrame
    pollutants: pl.DataFrame
    ratios: ElectricityRatios


def read_results_model(state: State) -> ResultsModel:
    return ResultsModel(
        technologies=_read_technologies(state),
        pollutants=_build_pollutants(state),
        ratios=_read_electricity_ratios(state),
    )


def build_electricity_ratios(keys: pl.DataFrame, ratios: ElectricityRatios) -> pl.DataFrame:
    """`keys` holds region, technology, operating_mode and year; the result adds `ratio`."""
    unstated = pl.col(_FUEL_COUNT).fill_null(0) - pl.col(_STATED_COUNT).fill_null(0)
    ratio = pl.col(RATIO).fill_null(0.0) + ratios.default * unstated
    return (
        keys.join(ratios.stated, on=[REGION, TECHNOLOGY, OPERATING_MODE, YEAR], how="left")
        .join(ratios.fuel_counts, on=REGION, how="left")
        .with_columns(ratio.alias(RATIO))
        .drop(_STATED_COUNT, _FUEL_COUNT)
    )


def build_electricity_producers(model: ResultsModel) -> pl.DataFrame:
    """The region and technology of each technology that can put out electricity.

    With a positive default ratio, every technology of a region with an electricity fuel can.
    """
    ratios = model.ratios
    if ratios.default > 0:
        regions = ratios.fuel_counts.filter(pl.col(_FUEL_COUNT) > 0).select(REGION)
        return model.technologies.join(regions, on=REGION, how="semi").select(REGION, TECHNOLOGY)
    return ratios.stated.filter(pl.col(RATIO) > 0).select(REGION, TECHNOLOGY).unique()


def _read_technologies(state: State) -> pl.DataFrame:
    columns = [REGION, TECHNOLOGY, AnnotationColumn.CATEGORY, AnnotationColumn.KIND]
    annotations = state.source_topology.get(build_table_key(TableKind.ANNOTATION, TECHNOLOGY))
    if annotations is None:
        technologies = pl.DataFrame(schema=dict.fromkeys(columns, pl.Utf8))
    else:
        technologies = annotations.select(columns).collect()
    return technologies.with_columns(express_component_name(TECHNOLOGY).alias(COMPONENT))


def _build_pollutants(state: State) -> pl.DataFrame:
    """OSeMOSYS sets hold no region, so each region holds every pollutant."""
    regions = pl.DataFrame({REGION: list_set_members(state, REGION)}, schema={REGION: pl.Utf8})
    pollutants = pl.DataFrame(
        {POLLUTANT: list_set_members(state, POLLUTANT)}, schema={POLLUTANT: pl.Utf8}
    )
    return regions.join(pollutants, how="cross").with_columns(
        express_component_name(POLLUTANT).alias(COMPONENT)
    )


def _read_electricity_ratios(state: State) -> ElectricityRatios:
    default = find_parameter_default(state, FlowParameter.OUTPUT_ACTIVITY_RATIO)
    electricity = _read_electricity_fuels(state)
    return ElectricityRatios(
        stated=_sum_stated_ratios(state, electricity),
        fuel_counts=electricity.group_by(REGION).agg(pl.len().cast(pl.Int64).alias(_FUEL_COUNT)),
        default=_NO_DEFAULT if default is None else float(default),
    )


def _read_electricity_fuels(state: State) -> pl.DataFrame:
    fuels = state.source_topology.get(build_table_key(TableKind.ANNOTATION, FUEL))
    if fuels is None:
        return pl.DataFrame(schema=dict.fromkeys([REGION, FUEL], pl.Utf8))
    is_electricity = pl.col(AnnotationColumn.CARRIER) == ELECTRICITY_CARRIER
    return fuels.filter(is_electricity).select(REGION, FUEL).collect()


def _sum_stated_ratios(state: State, electricity: pl.DataFrame) -> pl.DataFrame:
    ratios = state.source_time_series.get(
        (TableKind.PARAMETER, FlowParameter.OUTPUT_ACTIVITY_RATIO)
    )
    if ratios is None:
        return _build_empty_stated_ratios()
    return (
        ratios.join(electricity.lazy(), on=[REGION, FUEL], how="semi")
        .group_by(REGION, TECHNOLOGY, OPERATING_MODE, pl.col(YEAR).cast(pl.Int64))
        .agg(
            pl.col(VALUE_COL).sum().alias(RATIO),
            pl.len().cast(pl.Int64).alias(_STATED_COUNT),
        )
        .collect()
    )


def _build_empty_stated_ratios() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            REGION: pl.Utf8,
            TECHNOLOGY: pl.Utf8,
            OPERATING_MODE: pl.Utf8,
            YEAR: pl.Int64,
            RATIO: pl.Float64,
            _STATED_COUNT: pl.Int64,
        }
    )
