"""The annual rows of a solve over representative periods.

A solve over representative periods states each hour of a period once, and the period occurs
`weight` times in the year. The `representative_period` records of the extensions sidecar give
each period's hours and weight, so the hourly rows of the solve sum to the energy of the year.
With no such records, the solve covers the hours it states and nothing more, so no annual row
is written.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import NamedTuple

import polars as pl

from interop.core.extensions import (
    ExtensionKind,
    ExtensionLookup,
    GeneratorExtension,
    RepresentativePeriodExtension,
)
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import Framework, StagedTimeSeriesCol
from interop.plugins.shared.results_constants import (
    RESULTS_SCHEMA,
    RESULTS_TABLE_KEY,
    VARIABLE_UNIT,
    ResultsCol,
    ResultsVariable,
)
from interop.plugins.shared.sienna_constants import (
    MinMaxField,
    SiennaGeneratorCol,
    SiennaLinkCol,
    SiennaTable,
)
from interop.plugins.shared.sienna_results_constants import SNAPSHOT_HOURS, SiennaResultSeries
from interop.plugins.shared.warning_text import name_a_few
from interop.ports.outbound.reporting import (
    DestinationField,
    EventKind,
    SourceField,
    TranslationEvent,
)

log = logging.getLogger(__name__)

_WEIGHT = "weight"
_YEAR = "year"
_POLLUTANT = "pollutant"
_RATE = "rate"
_FIRST_MONTH = 1
_FIRST_DAY = 1
_SNAPSHOT_COMPONENT = "snapshot"
_EMISSION_RATES_FIELD = "emission_rates_t_per_mwh"

_Schema = dict[str, pl.DataType | type[pl.DataType]]
_HOURS_SCHEMA: _Schema = {ResultsCol.TIMESTAMP: RESULTS_SCHEMA[ResultsCol.TIMESTAMP]}
_CALENDAR_SCHEMA: _Schema = {**_HOURS_SCHEMA, _WEIGHT: pl.Float64}
_PRODUCTION_SCHEMA: _Schema = {
    ResultsCol.COMPONENT: pl.Utf8,
    ResultsCol.CATEGORY: pl.Utf8,
    _YEAR: pl.Int32,
    ResultsCol.VALUE: pl.Float64,
}
_RATES_SCHEMA: _Schema = {ResultsCol.COMPONENT: pl.Utf8, _POLLUTANT: pl.Utf8, _RATE: pl.Float64}

_PRODUCTION_DERIVATION = (
    "Σ over the hours of the solve of max(dispatch, 0) for a generator or a storage, or "
    "|flow| for a TwoTerminalGenericHVDCLine, × 1 h × the weight of the representative "
    "period that holds the hour → production at 1 January of the year. The solve models the "
    "HVDC line as lossless, so the energy that it delivers equals the energy that it sends."
)
_INSTALLED_CAPACITY_DERIVATION = (
    "base_power × rating for a generator or a storage, active_power_limits_from.max for a "
    "TwoTerminalGenericHVDCLine → installed_capacity at 1 January of the year"
)
_EMISSIONS_DERIVATION = (
    "Σ over generators of production × emission_rates_t_per_mwh of the pollutant → emissions "
    "at 1 January of the year"
)

_OUTSIDE_PERIODS_NOTE = (
    "the hour falls in no representative period, so it has no weight, and production and "
    "emissions leave it out"
)
_OUTSIDE_PERIODS_WARNING = (
    "%d hour(s) of the solve fall in no representative period, so production and emissions "
    "leave them out: %s"
)
_INCOMPLETE_PERIOD_NOTE = (
    "the representative period states no usable first_timestamp, hours or weight, so its "
    "hours have no weight and production and emissions leave them out"
)
_INCOMPLETE_PERIOD_WARNING = (
    "%d representative period(s) state no usable first_timestamp, hours or weight, so "
    "production and emissions leave their hours out: %s"
)

_PRODUCTION_SOURCES = [
    SourceField(
        framework=Framework.SIENNA,
        component=SiennaResultSeries.ACTIVE_POWER,
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
        name=_WEIGHT,
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
        name=SiennaGeneratorCol.RATING,
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


class Period(NamedTuple):
    first_hour: datetime
    hours: int
    weight: float


class AnnualResultsMapper:
    """Writes `production`, `installed_capacity` and `emissions` for a solve over
    representative periods."""

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def map_annual(
        self, state: State, hourly: HourlyResults, carrier_lookup: pl.LazyFrame | None
    ) -> list[pl.LazyFrame]:
        reader = state.extension_reader(self._recorder)
        records = reader.read(ExtensionKind.REPRESENTATIVE_PERIOD).read_all()
        if not records:
            return []
        weights = self._build_hour_weights(records, hourly.list_production_frames())
        if weights.is_empty():
            return []
        generator_production = _derive_production(
            hourly.generator_dispatch, weights, _express_positive_part()
        )
        production = pl.concat(
            [
                generator_production,
                _derive_production(hourly.storage_dispatch, weights, _express_positive_part()),
                _derive_production(hourly.link_flow, weights, pl.col(ResultsCol.VALUE).abs()),
            ]
        )
        generators = reader.read(ExtensionKind.GENERATOR)
        return [
            *self._map_production(production),
            *self._map_installed_capacity(state, carrier_lookup, _build_years(weights)),
            *self._map_emissions(generator_production, generators),
        ]

    def _build_hour_weights(
        self, records: list[RepresentativePeriodExtension], frames: list[pl.LazyFrame]
    ) -> pl.DataFrame:
        """The weight of each hour of the solve that a representative period holds."""
        calendar = _build_calendar(self._list_periods(records))
        hours = _build_solve_hours(frames)
        self._report_hours_outside(hours.join(calendar, on=ResultsCol.TIMESTAMP, how="anti"))
        return hours.join(calendar, on=ResultsCol.TIMESTAMP, how="inner")

    def _list_periods(self, records: list[RepresentativePeriodExtension]) -> list[Period]:
        periods = {record.name: _find_period(record) for record in records}
        self._report_incomplete_periods(
            [name for name, period in periods.items() if period is None]
        )
        return [period for period in periods.values() if period is not None]

    def _map_production(self, production: pl.DataFrame) -> list[pl.LazyFrame]:
        if production.is_empty():
            return []
        self._record_derivation(
            ResultsVariable.PRODUCTION, _PRODUCTION_SOURCES, _PRODUCTION_DERIVATION
        )
        return [_build_annual_rows(production, ResultsVariable.PRODUCTION)]

    def _map_installed_capacity(
        self, state: State, carrier_lookup: pl.LazyFrame | None, years: pl.DataFrame
    ) -> list[pl.LazyFrame]:
        ratings = _list_ratings(state, carrier_lookup)
        if not ratings:
            return []
        self._record_derivation(
            ResultsVariable.INSTALLED_CAPACITY,
            _INSTALLED_CAPACITY_SOURCES,
            _INSTALLED_CAPACITY_DERIVATION,
        )
        capacity = pl.concat(ratings).collect().join(years, how="cross")
        return [_build_annual_rows(capacity, ResultsVariable.INSTALLED_CAPACITY)]

    def _map_emissions(
        self, production: pl.DataFrame, generators: ExtensionLookup[GeneratorExtension]
    ) -> list[pl.LazyFrame]:
        rates = _build_emission_rates(production, generators)
        if rates.is_empty():
            return []
        self._record_derivation(
            ResultsVariable.EMISSIONS, _EMISSIONS_SOURCES, _EMISSIONS_DERIVATION
        )
        emissions = (
            production.join(rates, on=ResultsCol.COMPONENT, how="inner")
            .group_by(_POLLUTANT, _YEAR, maintain_order=True)
            .agg((pl.col(ResultsCol.VALUE) * pl.col(_RATE)).sum().alias(ResultsCol.VALUE))
            .select(
                pl.col(_POLLUTANT).alias(ResultsCol.COMPONENT),
                pl.lit(None, dtype=pl.Utf8).alias(ResultsCol.CATEGORY),
                _YEAR,
                ResultsCol.VALUE,
            )
        )
        return [_build_annual_rows(emissions, ResultsVariable.EMISSIONS)]

    def _record_derivation(
        self, variable: ResultsVariable, sources: list[SourceField], derivation: str
    ) -> None:
        self._recorder.append(
            TranslationEvent(
                kind=EventKind.VALUE_DERIVED,
                sources=list(sources),
                destinations=[
                    DestinationField(
                        framework=Framework.RESULTS,
                        component=RESULTS_TABLE_KEY,
                        name=str(variable),
                        attribute=ResultsCol.VARIABLE,
                        unit=VARIABLE_UNIT[variable],
                    )
                ],
                derivation=derivation,
            )
        )

    def _report_hours_outside(self, hours: pl.DataFrame) -> None:
        names = [hour.isoformat() for hour in hours[ResultsCol.TIMESTAMP].sort().to_list()]
        for name in names:
            self._recorder.append(
                TranslationEvent(
                    kind=EventKind.NOT_MAPPED,
                    sources=[
                        SourceField(
                            framework=Framework.SIENNA, component=_SNAPSHOT_COMPONENT, name=name
                        )
                    ],
                    note=_OUTSIDE_PERIODS_NOTE,
                )
            )
        if names:
            log.warning(_OUTSIDE_PERIODS_WARNING, len(names), name_a_few(names))

    def _report_incomplete_periods(self, names: list[str]) -> None:
        for name in names:
            self._recorder.append(
                TranslationEvent(
                    kind=EventKind.COMPONENT_SKIPPED,
                    sources=[
                        SourceField(
                            framework=Framework.SIENNA,
                            component=ExtensionKind.REPRESENTATIVE_PERIOD,
                            name=name,
                        )
                    ],
                    note=_INCOMPLETE_PERIOD_NOTE,
                )
            )
        if names:
            log.warning(_INCOMPLETE_PERIOD_WARNING, len(names), name_a_few(names))


def _find_period(record: RepresentativePeriodExtension) -> Period | None:
    """The period that a record states, or `None` when a field it needs is absent or wrong."""
    if record.first_timestamp is None or record.hours is None or record.weight is None:
        return None
    if record.hours <= 0 or record.weight < 0:
        return None
    try:
        first_hour = datetime.fromisoformat(record.first_timestamp)
    except ValueError:
        return None
    return Period(first_hour, record.hours, record.weight)


def _build_calendar(periods: list[Period]) -> pl.DataFrame:
    """One row for each hour that a period holds, with the weight of the period.

    Where two periods hold one hour, the first period gives its weight.
    """
    rows = [
        (period.first_hour + timedelta(hours=offset), period.weight)
        for period in periods
        for offset in range(period.hours)
    ]
    calendar = pl.DataFrame(rows, schema=_CALENDAR_SCHEMA, orient="row")
    return calendar.unique(subset=ResultsCol.TIMESTAMP, keep="first", maintain_order=True)


def _build_solve_hours(frames: list[pl.LazyFrame]) -> pl.DataFrame:
    if not frames:
        return pl.DataFrame(schema=_HOURS_SCHEMA)
    hours = pl.concat([frame.select(ResultsCol.TIMESTAMP) for frame in frames])
    return hours.unique().collect().cast(pl.Schema(_HOURS_SCHEMA))


def _build_years(weights: pl.DataFrame) -> pl.DataFrame:
    return weights.select(pl.col(ResultsCol.TIMESTAMP).dt.year().alias(_YEAR)).unique().sort(_YEAR)


def _express_positive_part() -> pl.Expr:
    return pl.col(ResultsCol.VALUE).clip(lower_bound=0.0)


def _derive_production(
    frames: list[pl.LazyFrame], weights: pl.DataFrame, power: pl.Expr
) -> pl.DataFrame:
    """MWh in each year, by component: power × 1 h × the weight of the hour, summed."""
    if not frames:
        return pl.DataFrame(schema=_PRODUCTION_SCHEMA)
    energy = (power * SNAPSHOT_HOURS * pl.col(_WEIGHT)).sum().alias(ResultsCol.VALUE)
    return (
        pl.concat(frames)
        .join(weights.lazy(), on=ResultsCol.TIMESTAMP, how="inner")
        .with_columns(pl.col(ResultsCol.TIMESTAMP).dt.year().alias(_YEAR))
        .group_by(ResultsCol.COMPONENT, ResultsCol.CATEGORY, _YEAR, maintain_order=True)
        .agg(energy)
        .collect()
        .cast(pl.Schema(_PRODUCTION_SCHEMA))
    )


def _list_ratings(state: State, carrier_lookup: pl.LazyFrame | None) -> list[pl.LazyFrame]:
    """The MW rating of each generator, storage and HVDC line that the system states."""
    rated = pl.col(SiennaGeneratorCol.BASE_POWER) * pl.col(SiennaGeneratorCol.RATING)
    ratings = [
        _build_rating(state.source_topology.get(SiennaTable.GENERATORS), rated, carrier_lookup),
        _build_rating(state.source_topology.get(SiennaTable.STORAGE), rated, carrier_lookup),
        _build_rating(
            state.source_topology.get(SiennaTable.LINKS),
            pl.col(SiennaLinkCol.ACTIVE_POWER_LIMITS_FROM).struct.field(MinMaxField.MAX),
            None,
        ),
    ]
    return [rating for rating in ratings if rating is not None]


def _build_rating(
    table: pl.LazyFrame | None, rating: pl.Expr, carrier_lookup: pl.LazyFrame | None
) -> pl.LazyFrame | None:
    if table is None:
        return None
    rows = table.select(
        pl.col(SiennaGeneratorCol.NAME).alias(ResultsCol.COMPONENT),
        rating.cast(pl.Float64).alias(ResultsCol.VALUE),
    )
    if carrier_lookup is None:
        return rows.with_columns(pl.lit(None, dtype=pl.Utf8).alias(ResultsCol.CATEGORY))
    categories = carrier_lookup.rename({StagedTimeSeriesCol.COMPONENT: ResultsCol.COMPONENT})
    return rows.join(categories, on=ResultsCol.COMPONENT, how="left").unique(
        subset=ResultsCol.COMPONENT, keep="first", maintain_order=True
    )


def _build_emission_rates(
    production: pl.DataFrame, generators: ExtensionLookup[GeneratorExtension]
) -> pl.DataFrame:
    """The t/MWh of each pollutant, for each generator of the solve that states a rate."""
    rows = [
        (name, pollutant, rate)
        for name in production[ResultsCol.COMPONENT].unique().sort().to_list()
        for pollutant, rate in (generators.get(name).emission_rates_t_per_mwh or {}).items()
    ]
    return pl.DataFrame(rows, schema=_RATES_SCHEMA, orient="row")


def _build_annual_rows(rows: pl.DataFrame, variable: ResultsVariable) -> pl.LazyFrame:
    january_first = pl.datetime(pl.col(_YEAR), _FIRST_MONTH, _FIRST_DAY)
    return rows.lazy().select(
        pl.lit(variable.value).alias(ResultsCol.VARIABLE),
        pl.col(ResultsCol.COMPONENT),
        pl.col(ResultsCol.CATEGORY),
        january_first.cast(RESULTS_SCHEMA[ResultsCol.TIMESTAMP]).alias(ResultsCol.TIMESTAMP),
        pl.col(ResultsCol.VALUE).cast(pl.Float64),
    )
