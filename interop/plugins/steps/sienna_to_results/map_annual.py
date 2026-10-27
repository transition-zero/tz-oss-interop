"""The annual rows of a solve over representative periods.

A solve over representative periods states each hour of a period once, and the period occurs
`weight` times in the year. The `representative_period` records of the extensions sidecar give
each period's hours and weight, so the hourly rows of the solve sum to the energy of the year.
With no such records, the solve covers the hours it states and nothing more, so no annual row
is written.

A line between two buses of one area whose record states no mark counts as production and
trade; the report names it, as it can be a conversion that an older sidecar does not mark.

A TwoTerminalGenericHVDCLine whose `controllable_line` record marks it as a conversion between
two electricity fuels of one location is neither production nor trade, so it has no production
and no installed capacity row.
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
    CAPACITY_SCHEMA,
    PRODUCTION_SCHEMA,
    AnnualDerivation,
    AnnualRowsMapper,
    LineEnds,
    Production,
    ResultsLeg,
    build_one_place_lines,
    build_results_source,
    drop_components,
)
from interop.plugins.shared.constants import (
    ALL_COMPONENTS,
    Framework,
    StagedTimeSeriesCol,
    require_extension_attribute,
)
from interop.plugins.shared.conversion_lines import build_conversion_lines
from interop.plugins.shared.results_constants import SIENNA_TO_RESULTS, ResultsCol, ResultsVariable
from interop.plugins.shared.sienna_constants import (
    MinMaxField,
    SiennaACBusCol,
    SiennaComponent,
    SiennaGeneratorCol,
    SiennaLinkCol,
    SiennaStorageCol,
    SiennaTable,
)
from interop.plugins.shared.sienna_results_constants import (
    SNAPSHOT_HOURS,
    AnnualCol,
)
from interop.plugins.steps.sienna_to_results.hour_weights import HourWeighter
from interop.ports.outbound.reporting import (
    SourceField,
)

_EMISSION_RATES_ATTRIBUTE = require_extension_attribute(
    GeneratorExtension, "emission_rates_t_per_mwh"
)
_LINE_TYPE = SiennaComponent.TWO_TERMINAL_GENERIC_HVDC_LINE
_LINE_ENDS = LineEnds(
    name=SiennaLinkCol.NAME,
    end0=SiennaLinkCol.BUS0,
    end1=SiennaLinkCol.BUS1,
    place_key=SiennaACBusCol.ID,
    place=SiennaACBusCol.AREA,
)

_EMISSIONS_DERIVATION = (
    "Σ over generators of production × emission_rates_t_per_mwh of the pollutant → emissions "
    "at 1 January of the year"
)

_PRODUCTION_DERIVATION = (
    "Σ over the hours of the solve of max(dispatch, 0) for a generator or a storage, or "
    "|flow| for a TwoTerminalGenericHVDCLine, × 1 h × the weight of the representative "
    "period that holds the hour → production at 1 January of the year. The dispatch rows hold "
    "ActivePowerVariable, ActivePowerTimeSeriesParameter for a RenewableNonDispatch, and "
    "ActivePowerOutVariable - ActivePowerInVariable for a storage. The solve models the HVDC "
    "line as lossless, so the energy that it delivers equals the energy that it sends. A line "
    "that its extensions record marks as a conversion has no row."
)
_INSTALLED_CAPACITY_DERIVATION = (
    "base_power × rating for a generator, base_power × output_active_power_limits.max for a "
    "storage, active_power_limits_from.max for a TwoTerminalGenericHVDCLine that is not a "
    "conversion → installed_capacity at 1 January of the year"
)
_PRODUCTION_SOURCES = [
    build_results_source(ResultsVariable.DISPATCH),
    build_results_source(ResultsVariable.FLOW),
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
    build_results_source(ResultsVariable.PRODUCTION),
    SourceField(
        framework=Framework.SIENNA,
        component=SiennaTable.GENERATORS,
        name=ALL_COMPONENTS,
        attribute=_EMISSION_RATES_ATTRIBUTE,
    ),
]
_PRODUCTION = AnnualDerivation(_PRODUCTION_SOURCES, _PRODUCTION_DERIVATION)
_INSTALLED_CAPACITY = AnnualDerivation(_INSTALLED_CAPACITY_SOURCES, _INSTALLED_CAPACITY_DERIVATION)
_EMISSIONS = AnnualDerivation(_EMISSIONS_SOURCES, _EMISSIONS_DERIVATION)


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
        self._mapper = AnnualRowsMapper(recorder, ResultsLeg(Framework.SIENNA, SIENNA_TO_RESULTS))

    def map_annual(
        self, state: State, hourly: HourlyResults, carrier_lookup: pl.LazyFrame | None
    ) -> list[pl.LazyFrame]:
        reader = state.extension_reader(self._recorder)
        weights = self._build_weights(reader, hourly)
        if weights.is_empty():
            return []
        conversions = build_conversion_lines(state.source_extensions)
        self._report_lines(state, conversions)
        production = _build_all_production(hourly, weights).drop_links(conversions)
        capacity = _build_capacity(state, carrier_lookup, _build_years(weights))
        return self._map_rows(reader, production, drop_components(capacity, conversions))

    def _report_lines(self, state: State, conversions: frozenset[str]) -> None:
        """Report each conversion line, and each line inside one area that states no mark."""
        self._mapper.report_conversions(_LINE_TYPE, conversions)
        self._mapper.report_unmarked(_LINE_TYPE, _build_one_area_lines(state) - conversions)

    def _map_rows(
        self, reader: ExtensionReader, production: Production, capacity: pl.DataFrame
    ) -> list[pl.LazyFrame]:
        produced = production.build_table()
        generators = reader.read(ExtensionKind.GENERATOR)
        return [
            *self._mapper.map_production(produced, _PRODUCTION),
            *self._mapper.map_installed_capacity(capacity, produced, _INSTALLED_CAPACITY),
            *self._mapper.map_emissions(
                production.generators, lambda name: _find_rates(generators, name), _EMISSIONS
            ),
        ]

    def _build_weights(self, reader: ExtensionReader, hourly: HourlyResults) -> pl.DataFrame:
        records = reader.read(ExtensionKind.REPRESENTATIVE_PERIOD).read_all()
        if not records:
            return pl.DataFrame()
        weighter = HourWeighter(self._recorder)
        return weighter.build_hour_weights(records, hourly.list_production_frames())


def _find_rates(
    generators: ExtensionLookup[GeneratorExtension], name: str
) -> dict[str, float] | None:
    return generators.get(name).emission_rates_t_per_mwh


def _build_one_area_lines(state: State) -> frozenset[str]:
    """Each HVDC line whose two buses have one area."""
    links = state.source_topology.get(SiennaTable.LINKS)
    buses = state.source_topology.get(SiennaTable.BUSES)
    if links is None or buses is None:
        return frozenset()
    areas = buses.select(SiennaACBusCol.ID, SiennaACBusCol.AREA)
    ends = links.select(SiennaLinkCol.NAME, SiennaLinkCol.BUS0, SiennaLinkCol.BUS1)
    return build_one_place_lines(ends, areas, _LINE_ENDS)


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
        return pl.DataFrame(schema=CAPACITY_SCHEMA)
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
