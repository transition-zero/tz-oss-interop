"""The members of the model that an OSeMOSYS results CSV names, read from the canonical stage.

The name of each technology and storage is built once from the whole set, so that one member
has one name in every variable, as in the Sienna translation of the same model.
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
    STORAGE,
    TECHNOLOGY,
    VALUE_COL,
    YEAR,
    AnnotationColumn,
    FlowParameter,
    TableKind,
)
from interop.plugins.shared.osemosys_sienna_translations._canonical import list_set_members
from interop.plugins.shared.osemosys_sienna_translations._names import express_component_name

# The column that holds the results component name of a member.
COMPONENT = "component"
# The column that holds the stated output ratio of a technology onto all its electricity fuels.
RATIO = "ratio"
# The column that holds the Sienna name of the storage that a technology discharges.
STORAGE_COMPONENT = "storage_component"

_NO_RATIO = 0.0


class ResultsModel(NamedTuple):
    """`technologies` holds region, technology, component, category and kind; `pollutants`
    holds region, pollutant and component. `ratios` holds, for each technology, mode and year
    that the model states, the sum of the stated output ratios onto electricity fuels.
    `storages` holds, for each technology that discharges a storage, the region, the
    technology, the storage and its Sienna name.

    Like the Sienna translation, the results read only the ratios that the model states, so
    the default of the parameter gives no technology an electricity output.
    """

    technologies: pl.DataFrame
    pollutants: pl.DataFrame
    ratios: pl.DataFrame
    storages: pl.DataFrame


def read_results_model(state: State) -> ResultsModel:
    return ResultsModel(
        technologies=_read_technologies(state),
        pollutants=_build_pollutants(state),
        ratios=_read_stated_ratios(state, _read_electricity_fuels(state)),
        storages=_read_storage_links(state),
    )


def build_electricity_ratios(keys: pl.DataFrame, ratios: pl.DataFrame) -> pl.DataFrame:
    """`keys` holds region, technology, operating_mode and year; the result adds `ratio`.

    A key that the model states no electricity ratio for takes no output.
    """
    return keys.join(
        ratios, on=[REGION, TECHNOLOGY, OPERATING_MODE, YEAR], how="left"
    ).with_columns(pl.col(RATIO).fill_null(_NO_RATIO))


def build_electricity_producers(model: ResultsModel) -> pl.DataFrame:
    """The region and technology of each technology that states an electricity output."""
    stated = model.ratios.filter(pl.col(RATIO) > _NO_RATIO)
    return stated.select(REGION, TECHNOLOGY).unique()


def _read_technologies(state: State) -> pl.DataFrame:
    columns = [REGION, TECHNOLOGY, AnnotationColumn.CATEGORY, AnnotationColumn.KIND]
    annotations = state.source_topology.get(build_table_key(TableKind.ANNOTATION, TECHNOLOGY))
    if annotations is None:
        technologies = pl.DataFrame(schema=dict.fromkeys(columns, pl.Utf8))
    else:
        technologies = annotations.select(columns).collect()
    return technologies.with_columns(express_component_name(TECHNOLOGY).alias(COMPONENT))


def _read_storage_links(state: State) -> pl.DataFrame:
    """The storage that each technology discharges, the first by name when it discharges two.

    The Sienna storage takes its rating from the technology that discharges it, so a technology
    that only charges a storage keeps its own name. The Sienna name of a storage is built from
    every storage of the model, as the Sienna translation does.
    """
    links = state.source_time_series.get(
        (TableKind.PARAMETER, FlowParameter.TECHNOLOGY_FROM_STORAGE)
    )
    if links is None:
        return _build_empty_storage_links()
    chosen = (
        links.filter(pl.col(VALUE_COL) > 0)
        .select(REGION, TECHNOLOGY, STORAGE)
        .collect()
        .sort(STORAGE)
        .group_by(REGION, TECHNOLOGY, maintain_order=True)
        .agg(pl.col(STORAGE).first())
    )
    return chosen.join(_read_storage_names(state), on=[REGION, STORAGE])


def _read_storage_names(state: State) -> pl.DataFrame:
    annotations = state.source_topology.get(build_table_key(TableKind.ANNOTATION, STORAGE))
    if annotations is None:
        return pl.DataFrame(schema=dict.fromkeys([REGION, STORAGE, STORAGE_COMPONENT], pl.Utf8))
    return (
        annotations.select(REGION, STORAGE)
        .collect()
        .with_columns(express_component_name(STORAGE).alias(STORAGE_COMPONENT))
    )


def _build_empty_storage_links() -> pl.DataFrame:
    columns = [REGION, TECHNOLOGY, STORAGE, STORAGE_COMPONENT]
    return pl.DataFrame(schema=dict.fromkeys(columns, pl.Utf8))


def _build_pollutants(state: State) -> pl.DataFrame:
    """OSeMOSYS sets hold no region, so each region holds every pollutant.

    A pollutant takes its plain name in every region, because the Sienna system keys an
    emission rate by the pollutant alone.
    """
    regions = pl.DataFrame({REGION: list_set_members(state, REGION)}, schema={REGION: pl.Utf8})
    pollutants = pl.DataFrame(
        {POLLUTANT: list_set_members(state, POLLUTANT)}, schema={POLLUTANT: pl.Utf8}
    )
    return regions.join(pollutants, how="cross").with_columns(pl.col(POLLUTANT).alias(COMPONENT))


def _read_electricity_fuels(state: State) -> pl.DataFrame:
    fuels = state.source_topology.get(build_table_key(TableKind.ANNOTATION, FUEL))
    if fuels is None:
        return pl.DataFrame(schema=dict.fromkeys([REGION, FUEL], pl.Utf8))
    is_electricity = pl.col(AnnotationColumn.CARRIER) == ELECTRICITY_CARRIER
    return fuels.filter(is_electricity).select(REGION, FUEL).collect()


def _read_stated_ratios(state: State, electricity: pl.DataFrame) -> pl.DataFrame:
    """The sum of the stated output ratios onto the electricity fuels, by technology, mode and
    year."""
    ratios = state.source_time_series.get(
        (TableKind.PARAMETER, FlowParameter.OUTPUT_ACTIVITY_RATIO)
    )
    if ratios is None:
        return _build_empty_stated_ratios()
    return (
        ratios.join(electricity.lazy(), on=[REGION, FUEL], how="semi")
        .group_by(REGION, TECHNOLOGY, OPERATING_MODE, pl.col(YEAR).cast(pl.Int64))
        .agg(pl.col(VALUE_COL).sum().alias(RATIO))
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
        }
    )
