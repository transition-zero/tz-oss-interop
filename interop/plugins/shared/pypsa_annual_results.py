"""The annual rows of a PyPSA solve whose snapshots stand for more hours than they last.

A network over representative periods weights each snapshot by how many hours of the year it
stands for. This writes production, installed capacity and emissions at 1 January of each year
of the solve, with the definitions of `sienna-to-results`, so the two solves compare row by
row. A network whose every snapshot counts once, with no representative periods in its
sidecar, covers the hours it states and nothing more, so it gets no annual row.
"""

from __future__ import annotations

import logging
from typing import NamedTuple

import polars as pl

from interop.core.extensions import ExtensionKind, record_for
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.annual_results import (
    PRODUCTION_SCHEMA,
    build_annual_rows,
    build_emission_rates,
    build_emissions,
)
from interop.plugins.shared.constants import ALL_COMPONENTS, Framework
from interop.plugins.shared.pypsa_constants import (
    PYPSA_NAME_COLUMN,
    PyPSAComponent,
    PyPSAGeneratorCol,
    PyPSASolvedAttr,
    PyPSATable,
    PyPSATimeSeriesCol,
)
from interop.plugins.shared.results_constants import (
    RESULTS_TABLE_KEY,
    VARIABLE_UNIT,
    ResultsCol,
    ResultsVariable,
)
from interop.plugins.shared.sienna_results_constants import AnnualCol
from interop.plugins.shared.warning_text import name_a_few
from interop.ports.outbound.reporting import (
    DestinationField,
    EventKind,
    SourceField,
    TranslationEvent,
)

log = logging.getLogger(__name__)

_UNWEIGHTED = 1.0
_P_MAX_PU = "p_max_pu"
_P_NOM = "p_nom"
# PyPSA writes a static attribute only where a component differs from its default, so an
# absent column holds the default.
_DEFAULTS: dict[str, float | str] = {_P_NOM: 0.0, _P_MAX_PU: 1.0, PyPSAGeneratorCol.CARRIER: ""}
_EMISSION_RATES_FIELD = "emission_rates_t_per_mwh"
_DELIVERED = "delivered"

_PRODUCTION_DERIVATION = (
    "Σ over the snapshots of max(p, 0) for a generator or a storage unit, or of the power that "
    "a link delivers at the end that receives it, max(-p0, 0) + max(-p1, 0), × the generators "
    "snapshot weighting → production at 1 January of the year"
)
_INSTALLED_CAPACITY_DERIVATION = (
    "p_nom × p_max_pu for a generator, a storage unit or a link → installed_capacity at "
    "1 January of the year"
)
_EMISSIONS_DERIVATION = (
    "Σ over generators of production × emission_rates_t_per_mwh of the pollutant → emissions "
    "at 1 January of the year"
)
_UNPRODUCED_NOTE = (
    "the solve states no output for the component, so it has installed_capacity and no production"
)
_UNPRODUCED_WARNING = (
    "%d component(s) have a rating, but the solve states no output for them, so they have no "
    "production: %s"
)


class _Rated(NamedTuple):
    """A component table that states rated power, and how the results name its components."""

    table: str
    component: PyPSAComponent
    has_category: bool


_RATED = (
    _Rated(PyPSATable.GENERATORS, PyPSAComponent.GENERATOR, has_category=True),
    _Rated(PyPSATable.STORAGE_UNITS, PyPSAComponent.STORAGE_UNIT, has_category=True),
    _Rated(PyPSATable.LINKS, PyPSAComponent.LINK, has_category=False),
)


class Production(NamedTuple):
    """MWh in each year, by component, for each kind of component that produces."""

    generators: pl.DataFrame
    storage: pl.DataFrame
    links: pl.DataFrame

    def build_table(self) -> pl.DataFrame:
        return pl.concat([self.generators, self.storage, self.links])


class PypsaAnnualResultsMapper:
    """Writes `production`, `installed_capacity` and `emissions` for a weighted solve."""

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def map_annual(self, state: State) -> list[pl.LazyFrame]:
        weights = _find_weights(state)
        if weights is None or not _is_annual(state, weights):
            return []
        production = _build_all_production(state, weights)
        produced = production.build_table()
        capacity = _build_capacity(state, _build_years(weights))
        return [
            *self._map_production(produced),
            *self._map_installed_capacity(capacity, produced),
            *self._map_emissions(state, production.generators),
        ]

    def _map_production(self, production: pl.DataFrame) -> list[pl.LazyFrame]:
        if production.is_empty():
            return []
        sources = [
            _build_source(PyPSAComponent.GENERATOR, PyPSASolvedAttr.DISPATCH),
            _build_source(PyPSAComponent.STORAGE_UNIT, PyPSASolvedAttr.DISPATCH),
            _build_source(PyPSAComponent.LINK, PyPSASolvedAttr.FLOW),
            _build_source(PyPSAComponent.LINK, PyPSASolvedAttr.FAR_END_FLOW),
            _build_source(PyPSATable.SNAPSHOTS, PyPSASolvedAttr.GENERATOR_WEIGHTING),
        ]
        self._record(ResultsVariable.PRODUCTION, sources, _PRODUCTION_DERIVATION)
        return [build_annual_rows(production, ResultsVariable.PRODUCTION)]

    def _map_installed_capacity(
        self, capacity: pl.DataFrame, production: pl.DataFrame
    ) -> list[pl.LazyFrame]:
        if capacity.is_empty():
            return []
        sources = [_build_source(rated.component, _P_NOM) for rated in _RATED]
        self._record(ResultsVariable.INSTALLED_CAPACITY, sources, _INSTALLED_CAPACITY_DERIVATION)
        self._report_unproduced(capacity.join(production, on=ResultsCol.COMPONENT, how="anti"))
        return [build_annual_rows(capacity, ResultsVariable.INSTALLED_CAPACITY)]

    def _map_emissions(self, state: State, production: pl.DataFrame) -> list[pl.LazyFrame]:
        rates = build_emission_rates(production, lambda name: _find_rates(state, name))
        if rates.is_empty():
            return []
        source = SourceField(
            framework=Framework.PYPSA,
            component=ExtensionKind.GENERATOR,
            name=ALL_COMPONENTS,
            attribute=_EMISSION_RATES_FIELD,
        )
        self._record(ResultsVariable.EMISSIONS, [source], _EMISSIONS_DERIVATION)
        return [build_annual_rows(build_emissions(production, rates), ResultsVariable.EMISSIONS)]

    def _record(
        self, variable: ResultsVariable, sources: list[SourceField], derivation: str
    ) -> None:
        self._recorder.append(
            TranslationEvent(
                kind=EventKind.VALUE_DERIVED,
                sources=sources,
                destinations=[_build_results_destination(variable)],
                derivation=derivation,
            )
        )

    def _report_unproduced(self, capacity: pl.DataFrame) -> None:
        """Report each component that has a rating and no output in the solve."""
        rows = capacity.unique(ResultsCol.COMPONENT, maintain_order=True).iter_rows(named=True)
        names = []
        for row in rows:
            names.append(row[ResultsCol.COMPONENT])
            self._recorder.append(
                TranslationEvent(
                    kind=EventKind.NOT_MAPPED,
                    sources=[
                        SourceField(
                            framework=Framework.PYPSA,
                            component=row[AnnualCol.SIENNA_TYPE],
                            name=row[ResultsCol.COMPONENT],
                        )
                    ],
                    destinations=[_build_results_destination(ResultsVariable.PRODUCTION)],
                    note=_UNPRODUCED_NOTE,
                )
            )
        if names:
            log.warning(_UNPRODUCED_WARNING, len(names), name_a_few(names))


def _find_weights(state: State) -> pl.DataFrame | None:
    """The hours each snapshot counts for in a generator's energy, by snapshot."""
    for attribute in (PyPSASolvedAttr.GENERATOR_WEIGHTING, PyPSASolvedAttr.SNAPSHOT_WEIGHTING):
        frame = state.source_time_series.get((PyPSATable.SNAPSHOTS, attribute))
        if frame is not None:
            return frame.select(
                PyPSATimeSeriesCol.SNAPSHOT,
                pl.col(PyPSATimeSeriesCol.VALUE).alias(AnnualCol.WEIGHT),
            ).collect()
    return None


def _is_annual(state: State, weights: pl.DataFrame) -> bool:
    """Whether a snapshot counts for other than one hour, or the sidecar states periods."""
    is_weighted = bool((weights[AnnualCol.WEIGHT] != _UNWEIGHTED).any())
    return is_weighted or bool(state.source_extensions.get(ExtensionKind.REPRESENTATIVE_PERIOD))


def _build_years(weights: pl.DataFrame) -> pl.DataFrame:
    year = pl.col(PyPSATimeSeriesCol.SNAPSHOT).dt.year().cast(pl.Int32).alias(AnnualCol.YEAR)
    return weights.select(year).unique().sort(AnnualCol.YEAR)


def _build_all_production(state: State, weights: pl.DataFrame) -> Production:
    positive_part = pl.col(PyPSATimeSeriesCol.VALUE).clip(lower_bound=0.0)
    return Production(
        generators=_build_production(
            state,
            PyPSATable.GENERATORS,
            _find_series(state, PyPSATable.GENERATORS),
            weights,
            positive_part,
        ),
        storage=_build_production(
            state,
            PyPSATable.STORAGE_UNITS,
            _find_series(state, PyPSATable.STORAGE_UNITS),
            weights,
            positive_part,
        ),
        links=_build_production(
            state, PyPSATable.LINKS, _build_link_delivery(state), weights, pl.col(_DELIVERED)
        ),
    )


def _find_series(state: State, table: str) -> pl.LazyFrame | None:
    return state.source_time_series.get((table, PyPSASolvedAttr.DISPATCH))


def _build_link_delivery(state: State) -> pl.LazyFrame | None:
    """The power each link delivers at the end that receives it, at each snapshot.

    PyPSA states p0 and p1 as the power the link withdraws at each end, so the end that
    receives power states a negative value.
    """
    sent = state.source_time_series.get((PyPSATable.LINKS, PyPSASolvedAttr.FLOW))
    received = state.source_time_series.get((PyPSATable.LINKS, PyPSASolvedAttr.FAR_END_FLOW))
    if sent is None or received is None:
        return None
    keys = [PyPSATimeSeriesCol.SNAPSHOT, PyPSATimeSeriesCol.COMPONENT]
    far_end = received.select(*keys, pl.col(PyPSATimeSeriesCol.VALUE).alias(_DELIVERED))
    delivered = (-pl.col(PyPSATimeSeriesCol.VALUE)).clip(lower_bound=0.0) + (
        -pl.col(_DELIVERED)
    ).clip(lower_bound=0.0)
    return sent.join(far_end, on=keys, how="inner").select(*keys, delivered.alias(_DELIVERED))


def _build_production(
    state: State,
    table: str,
    series: pl.LazyFrame | None,
    weights: pl.DataFrame,
    power: pl.Expr,
) -> pl.DataFrame:
    """MWh in each year, by component: power × the hours of the snapshot, summed."""
    if series is None:
        return pl.DataFrame(schema=PRODUCTION_SCHEMA)
    energy = (power * pl.col(AnnualCol.WEIGHT)).sum().alias(ResultsCol.VALUE)
    year = pl.col(PyPSATimeSeriesCol.SNAPSHOT).dt.year().cast(pl.Int32).alias(AnnualCol.YEAR)
    produced = (
        series.join(weights.lazy(), on=PyPSATimeSeriesCol.SNAPSHOT, how="inner")
        .with_columns(year)
        .group_by(PyPSATimeSeriesCol.COMPONENT, AnnualCol.YEAR, maintain_order=True)
        .agg(energy)
        .rename({PyPSATimeSeriesCol.COMPONENT: ResultsCol.COMPONENT})
    )
    return (
        produced.join(_build_categories(state, table), on=ResultsCol.COMPONENT, how="left")
        .select(list(PRODUCTION_SCHEMA))
        .collect()
        .cast(pl.Schema(PRODUCTION_SCHEMA))
    )


def _build_categories(state: State, table: str) -> pl.LazyFrame:
    """The category of each component: its carrier, and none for a link, as Sienna has none."""
    topology = state.source_topology.get(table)
    if topology is None:
        return pl.LazyFrame(schema={ResultsCol.COMPONENT: pl.Utf8, ResultsCol.CATEGORY: pl.Utf8})
    rated = next(one for one in _RATED if one.table == table)
    category = (
        _express_attribute(topology, PyPSAGeneratorCol.CARRIER)
        if rated.has_category
        else pl.lit(None, dtype=pl.Utf8)
    )
    return topology.select(
        pl.col(PYPSA_NAME_COLUMN).alias(ResultsCol.COMPONENT),
        category.cast(pl.Utf8).alias(ResultsCol.CATEGORY),
    )


def _build_capacity(state: State, years: pl.DataFrame) -> pl.DataFrame:
    """The MW rating of each generator, storage unit and link, for each year of the solve."""
    ratings = [
        _build_rating(state, rated)
        for rated in _RATED
        if state.source_topology.get(rated.table) is not None
    ]
    if not ratings:
        return pl.DataFrame()
    return pl.concat(ratings).collect().join(years, how="cross")


def _build_rating(state: State, rated: _Rated) -> pl.LazyFrame:
    topology = state.source_topology[rated.table]
    rating = _express_attribute(topology, _P_NOM) * _express_attribute(topology, _P_MAX_PU)
    return topology.select(
        pl.col(PYPSA_NAME_COLUMN).alias(ResultsCol.COMPONENT),
        pl.lit(str(rated.component)).alias(AnnualCol.SIENNA_TYPE),
        rating.cast(pl.Float64).alias(ResultsCol.VALUE),
    ).join(_build_categories(state, rated.table), on=ResultsCol.COMPONENT, how="left")


def _express_attribute(topology: pl.LazyFrame, attribute: str) -> pl.Expr:
    """A static attribute of the components, or PyPSA's default where the file omits it."""
    if attribute in topology.collect_schema().names():
        return pl.col(attribute)
    return pl.lit(_DEFAULTS[attribute])


def _find_rates(state: State, name: str) -> dict[str, float] | None:
    record = record_for(state.source_extensions, ExtensionKind.GENERATOR, name)
    return None if record is None else record.emission_rates_t_per_mwh


def _build_source(component: str, attribute: str) -> SourceField:
    return SourceField(
        framework=Framework.PYPSA, component=component, name=ALL_COMPONENTS, attribute=attribute
    )


def _build_results_destination(variable: ResultsVariable) -> DestinationField:
    return DestinationField(
        framework=Framework.RESULTS,
        component=RESULTS_TABLE_KEY,
        name=str(variable),
        attribute=ResultsCol.VARIABLE,
        unit=VARIABLE_UNIT[variable],
    )
