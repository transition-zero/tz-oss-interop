"""The annual rows of a solve over representative periods.

A solve over representative periods states each hour of a period once, and the period occurs
`weight` times in the year. The `representative_period` records of the extensions sidecar give
each period's hours and weight, so the hourly rows of the solve sum to the energy of the year.
With no such records, the solve covers the hours it states and nothing more, so no annual row
is written.
"""

from __future__ import annotations

from typing import NamedTuple

import polars as pl

from interop.core.extensions import (
    ExtensionKind,
    ExtensionLookup,
    ExtensionReader,
    GeneratorExtension,
)
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.annual_results import (
    EMISSIONS_DERIVATION,
    PRODUCTION_SCHEMA,
    AnnualReporter,
    Production,
    build_annual_rows,
    build_emission_rates,
    build_emissions,
)
from interop.plugins.shared.constants import Framework, StagedTimeSeriesCol
from interop.plugins.shared.results_constants import ResultsCol, ResultsVariable
from interop.plugins.shared.sienna_constants import (
    MinMaxField,
    SiennaGeneratorCol,
    SiennaLinkCol,
    SiennaStorageCol,
    SiennaTable,
)
from interop.plugins.shared.sienna_results_constants import (
    SNAPSHOT_HOURS,
    AnnualCol,
    SiennaResultSeries,
)
from interop.plugins.steps.sienna_to_results.hour_weights import HourWeighter
from interop.ports.outbound.reporting import (
    SourceField,
)

_EMISSION_RATES_FIELD = "emission_rates_t_per_mwh"

_PRODUCTION_DERIVATION = (
    "Σ over the hours of the solve of max(dispatch, 0) for a generator or a storage, or "
    "|flow| for a TwoTerminalGenericHVDCLine, × 1 h × the weight of the representative "
    "period that holds the hour → production at 1 January of the year. The dispatch of a "
    "RenewableNonDispatch is its ActivePowerTimeSeriesParameter. The solve models the HVDC "
    "line as lossless, so the energy that it delivers equals the energy that it sends."
)
_INSTALLED_CAPACITY_DERIVATION = (
    "base_power × rating for a generator, base_power × output_active_power_limits.max for a "
    "storage, active_power_limits_from.max for a TwoTerminalGenericHVDCLine → "
    "installed_capacity at 1 January of the year"
)
_PRODUCTION_SOURCES = [
    SourceField(
        framework=Framework.SIENNA,
        component=SiennaResultSeries.ACTIVE_POWER,
        name=ResultsVariable.DISPATCH,
    ),
    SourceField(
        framework=Framework.SIENNA,
        component=SiennaResultSeries.ACTIVE_POWER_PARAMETER,
        name=ResultsVariable.DISPATCH,
    ),
    SourceField(
        framework=Framework.SIENNA,
        component=SiennaResultSeries.FLOW_ACTIVE_POWER,
        name=ResultsVariable.FLOW,
    ),
    SourceField(
        framework=Framework.SIENNA,
        component=ExtensionKind.REPRESENTATIVE_PERIOD,
        name=AnnualCol.WEIGHT,
    ),
]
_INSTALLED_CAPACITY_SOURCES = [
    SourceField(
        framework=Framework.SIENNA,
        component=SiennaTable.GENERATORS,
        name=SiennaGeneratorCol.RATING,
    ),
    SourceField(
        framework=Framework.SIENNA,
        component=SiennaTable.STORAGE,
        name=SiennaStorageCol.OUTPUT_ACTIVE_POWER_LIMITS,
    ),
    SourceField(
        framework=Framework.SIENNA,
        component=SiennaTable.LINKS,
        name=SiennaLinkCol.ACTIVE_POWER_LIMITS_FROM,
    ),
]
_EMISSIONS_SOURCES = [
    SourceField(
        framework=Framework.SIENNA,
        component=ExtensionKind.GENERATOR,
        name=_EMISSION_RATES_FIELD,
    ),
]


class HourlyResults(NamedTuple):
    """The hourly rows of the solve, in the results format, by the kind of component."""

    generator_dispatch: list[pl.LazyFrame]
    storage_dispatch: list[pl.LazyFrame]
    line_flow: list[pl.LazyFrame]
    link_flow: list[pl.LazyFrame]
    load: list[pl.LazyFrame]

    def list_frames(self) -> list[pl.LazyFrame]:
        return [
            *self.generator_dispatch,
            *self.storage_dispatch,
            *self.line_flow,
            *self.link_flow,
            *self.load,
        ]

    def list_production_frames(self) -> list[pl.LazyFrame]:
        return [*self.generator_dispatch, *self.storage_dispatch, *self.link_flow]


class AnnualResultsMapper:
    """Writes `production`, `installed_capacity` and `emissions` for a solve over
    representative periods."""

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder
        self._reporter = AnnualReporter(recorder, Framework.SIENNA)

    def map_annual(
        self, state: State, hourly: HourlyResults, carrier_lookup: pl.LazyFrame | None
    ) -> list[pl.LazyFrame]:
        reader = state.extension_reader(self._recorder)
        weights = self._build_weights(reader, hourly)
        if weights.is_empty():
            return []
        production = _build_all_production(hourly, weights)
        produced = production.build_table()
        capacity = _build_capacity(state, carrier_lookup, _build_years(weights))
        return [
            *self._map_production(produced),
            *self._map_installed_capacity(capacity, produced),
            *self._map_emissions(production.generators, reader.read(ExtensionKind.GENERATOR)),
        ]

    def _build_weights(self, reader: ExtensionReader, hourly: HourlyResults) -> pl.DataFrame:
        records = reader.read(ExtensionKind.REPRESENTATIVE_PERIOD).read_all()
        if not records:
            return pl.DataFrame()
        weighter = HourWeighter(self._recorder)
        return weighter.build_hour_weights(records, hourly.list_production_frames())

    def _map_production(self, production: pl.DataFrame) -> list[pl.LazyFrame]:
        if production.is_empty():
            return []
        self._reporter.record_derivation(
            ResultsVariable.PRODUCTION, _PRODUCTION_SOURCES, _PRODUCTION_DERIVATION
        )
        return [build_annual_rows(production, ResultsVariable.PRODUCTION)]

    def _map_installed_capacity(
        self, capacity: pl.DataFrame, production: pl.DataFrame
    ) -> list[pl.LazyFrame]:
        if capacity.is_empty():
            return []
        self._reporter.record_derivation(
            ResultsVariable.INSTALLED_CAPACITY,
            _INSTALLED_CAPACITY_SOURCES,
            _INSTALLED_CAPACITY_DERIVATION,
        )
        self._reporter.report_unproduced(
            capacity.join(production, on=ResultsCol.COMPONENT, how="anti")
        )
        return [build_annual_rows(capacity, ResultsVariable.INSTALLED_CAPACITY)]

    def _map_emissions(
        self, production: pl.DataFrame, generators: ExtensionLookup[GeneratorExtension]
    ) -> list[pl.LazyFrame]:
        rates = build_emission_rates(
            production, lambda name: generators.get(name).emission_rates_t_per_mwh
        )
        if rates.is_empty():
            return []
        self._reporter.record_derivation(
            ResultsVariable.EMISSIONS, _EMISSIONS_SOURCES, EMISSIONS_DERIVATION
        )
        return [build_annual_rows(build_emissions(production, rates), ResultsVariable.EMISSIONS)]


def _build_all_production(hourly: HourlyResults, weights: pl.DataFrame) -> Production:
    positive_part = pl.col(ResultsCol.VALUE).clip(lower_bound=0.0)
    return Production(
        generators=_build_production(hourly.generator_dispatch, weights, positive_part),
        storage=_build_production(hourly.storage_dispatch, weights, positive_part),
        links=_build_production(hourly.link_flow, weights, pl.col(ResultsCol.VALUE).abs()),
    )


def _build_years(weights: pl.DataFrame) -> pl.DataFrame:
    year = pl.col(ResultsCol.TIMESTAMP).dt.year().alias(AnnualCol.YEAR)
    return weights.select(year).unique().sort(AnnualCol.YEAR)


def _build_production(
    frames: list[pl.LazyFrame], weights: pl.DataFrame, power: pl.Expr
) -> pl.DataFrame:
    """MWh in each year, by component: power × 1 h × the weight of the hour, summed."""
    if not frames:
        return pl.DataFrame(schema=PRODUCTION_SCHEMA)
    energy = (power * SNAPSHOT_HOURS * pl.col(AnnualCol.WEIGHT)).sum().alias(ResultsCol.VALUE)
    year = pl.col(ResultsCol.TIMESTAMP).dt.year().alias(AnnualCol.YEAR)
    return (
        pl.concat(frames)
        .join(weights.lazy(), on=ResultsCol.TIMESTAMP, how="inner")
        .with_columns(year)
        .group_by(ResultsCol.COMPONENT, ResultsCol.CATEGORY, AnnualCol.YEAR, maintain_order=True)
        .agg(energy)
        .collect()
        .cast(pl.Schema(PRODUCTION_SCHEMA))
    )


def _build_capacity(
    state: State, carrier_lookup: pl.LazyFrame | None, years: pl.DataFrame
) -> pl.DataFrame:
    """The MW rating of each generator, storage and HVDC line, for each year of the solve."""
    base_power = pl.col(SiennaGeneratorCol.BASE_POWER)
    rated = base_power * pl.col(SiennaGeneratorCol.RATING)
    output = pl.col(SiennaStorageCol.OUTPUT_ACTIVE_POWER_LIMITS).struct.field(MinMaxField.MAX)
    limit = pl.col(SiennaLinkCol.ACTIVE_POWER_LIMITS_FROM).struct.field(MinMaxField.MAX)
    ratings = [
        _build_rating(state.source_topology.get(SiennaTable.GENERATORS), rated, carrier_lookup),
        _build_rating(
            state.source_topology.get(SiennaTable.STORAGE), base_power * output, carrier_lookup
        ),
        _build_rating(state.source_topology.get(SiennaTable.LINKS), limit, None),
    ]
    stated = [rating for rating in ratings if rating is not None]
    if not stated:
        return pl.DataFrame()
    return pl.concat(stated).collect().join(years, how="cross")


def _build_rating(
    table: pl.LazyFrame | None, rating: pl.Expr, carrier_lookup: pl.LazyFrame | None
) -> pl.LazyFrame | None:
    if table is None:
        return None
    rows = table.select(
        pl.col(SiennaGeneratorCol.NAME).alias(ResultsCol.COMPONENT),
        pl.col(SiennaGeneratorCol.SIENNA_TYPE).alias(AnnualCol.COMPONENT_TYPE),
        rating.cast(pl.Float64).alias(ResultsCol.VALUE),
    )
    if carrier_lookup is None:
        return rows.with_columns(pl.lit(None, dtype=pl.Utf8).alias(ResultsCol.CATEGORY))
    categories = carrier_lookup.rename({StagedTimeSeriesCol.COMPONENT: ResultsCol.COMPONENT})
    return rows.join(categories, on=ResultsCol.COMPONENT, how="left").unique(
        subset=ResultsCol.COMPONENT, keep="first", maintain_order=True
    )
