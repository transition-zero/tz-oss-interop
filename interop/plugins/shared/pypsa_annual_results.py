"""The annual rows of a PyPSA solve whose snapshots stand for more hours than they last.

A network over representative periods weights each snapshot by the hours of the year that it
stands for. This writes production, installed capacity and emissions at 1 January of each year
of the solve, with the definitions of `sienna-to-results`, so the two solves compare row by
row. A network whose every snapshot counts once, with no representative periods in its
sidecar, covers the hours it states and nothing more, so it gets no annual row.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import NamedTuple

import polars as pl

from interop.core.extensions import NETWORK_RECORD_NAME, ExtensionKind, record_for
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.annual_results import (
    PRODUCTION_SCHEMA,
    AnnualReporter,
    Production,
    build_annual_rows,
    build_emission_rates,
    build_emissions,
)
from interop.plugins.shared.constants import ALL_COMPONENTS, Framework
from interop.plugins.shared.pypsa_constants import (
    PYPSA_NAME_COLUMN,
    REVERSE_LINK_SUFFIX,
    PyPSAComponent,
    PyPSAGeneratorCol,
    PyPSASolvedAttr,
    PyPSATable,
    PyPSATimeSeriesCol,
)
from interop.plugins.shared.pypsa_fuel_components import FuelComponents, build_fuel_components
from interop.plugins.shared.results_constants import ResultsCol, ResultsVariable
from interop.plugins.shared.sienna_results_constants import AnnualCol
from interop.ports.outbound.reporting import SourceField

_UNWEIGHTED = 1.0
_NO_PRODUCTION = 0.0
_P_MAX_PU = "p_max_pu"
_P_NOM = "p_nom"
_EFFICIENCY = "efficiency"
# PyPSA writes a static attribute only where a component differs from its default, so an
# absent column holds the default.
_DEFAULTS: dict[str, float | str] = {
    _P_NOM: 0.0,
    _P_MAX_PU: 1.0,
    _EFFICIENCY: 1.0,
    PyPSAGeneratorCol.CARRIER: "",
}
_EMISSION_RATES_FIELD = "emission_rates_t_per_mwh"
_OWN_EMISSION_RATES_FIELD = "own_emission_rates_t_per_mwh"
_DELIVERED = "delivered"
_KEYS = [PyPSATimeSeriesCol.SNAPSHOT, PyPSATimeSeriesCol.COMPONENT]

_FUEL_EMISSIONS_DERIVATION = (
    "Σ over the snapshots of the energy of a component × its rate of the pollutant × the "
    "generators snapshot weighting → emissions at 1 January of the year: the output of a "
    "generator, including a generator of a fuel, × emission_rates_t_per_mwh; the electricity of "
    "a plant link × own_emission_rates_t_per_mwh of its generator record; max(p0, 0) of a link "
    "of a fuel × emission_rates_t_per_mwh of its conversion record"
)
_PRODUCTION_DERIVATION = (
    "Σ over the snapshots of max(p, 0) for a generator or a storage unit, or of the power that "
    "a link delivers at the end that receives it, max(-p0, 0) + max(-p1, 0), × the generators "
    "snapshot weighting → production at 1 January of the year; the reverse link of a two-way "
    "link adds to the production of the two-way link; a solved network gives 0 to a rated "
    "component with no p, as PyPSA's netCDF export leaves out a series that is 0 in each "
    "snapshot; a generator and a link on the bus of a fuel make no electricity, so they have no "
    "row, and a plant link makes the electricity that it delivers at bus1"
)
_INSTALLED_CAPACITY_DERIVATION = (
    "p_nom, the nameplate, for a generator; p_nom × p_max_pu for a storage unit or a link, and "
    "once for a two-way link and its reverse link; p_nom × efficiency for a plant link → "
    "installed_capacity at 1 January of the year"
)


class _Rated(NamedTuple):
    """A component table that states rated power, and how the results name its components."""

    table: str
    component: PyPSAComponent
    has_category: bool
    # A generator's p_max_pu is what it may make, so its nameplate is p_nom alone.
    is_rated_by_p_max_pu: bool


_RATED = (
    _Rated(
        PyPSATable.GENERATORS,
        PyPSAComponent.GENERATOR,
        has_category=True,
        is_rated_by_p_max_pu=False,
    ),
    _Rated(
        PyPSATable.STORAGE_UNITS,
        PyPSAComponent.STORAGE_UNIT,
        has_category=True,
        is_rated_by_p_max_pu=True,
    ),
    _Rated(PyPSATable.LINKS, PyPSAComponent.LINK, has_category=False, is_rated_by_p_max_pu=True),
)
# Finds the power of the components of one table, by snapshot, or None where it states none.
_PowerFinder = Callable[[State, str], pl.LazyFrame | None]


class PypsaAnnualResultsMapper:
    """Writes `production`, `installed_capacity` and `emissions` for a weighted solve."""

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._reporter = AnnualReporter(recorder, Framework.PYPSA)

    def map_annual(self, state: State) -> list[pl.LazyFrame]:
        weights = _find_weights(state)
        if weights is None or not _is_annual(state, weights):
            return []
        fuels = build_fuel_components(state)
        activity = _build_all_production(state, weights, fuels)
        production = activity.drop_fuels(fuels)
        capacity = _build_capacity(state, _build_years(weights), fuels)
        produced = production.build_table()
        if is_solved(state):
            produced = _fill_unproduced(produced, capacity)
        emitting = pl.concat([activity.generators, activity.storage, activity.links])
        return [
            *self._map_production(produced),
            *self._map_installed_capacity(capacity, produced),
            *self._map_emissions(state, emitting, fuels),
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
        self._reporter.record_derivation(
            ResultsVariable.PRODUCTION, sources, _PRODUCTION_DERIVATION
        )
        return [build_annual_rows(production, ResultsVariable.PRODUCTION)]

    def _map_installed_capacity(
        self, capacity: pl.DataFrame, production: pl.DataFrame
    ) -> list[pl.LazyFrame]:
        if capacity.is_empty():
            return []
        sources = [_build_source(rated.component, _P_NOM) for rated in _RATED]
        self._reporter.record_derivation(
            ResultsVariable.INSTALLED_CAPACITY, sources, _INSTALLED_CAPACITY_DERIVATION
        )
        unproduced = capacity.join(production, on=ResultsCol.COMPONENT, how="anti")
        self._reporter.report_unproduced(unproduced)
        return [build_annual_rows(capacity, ResultsVariable.INSTALLED_CAPACITY)]

    def _map_emissions(
        self, state: State, activity: pl.DataFrame, fuels: FuelComponents
    ) -> list[pl.LazyFrame]:
        """Emissions of each component with a rate: a generator, a storage unit such as a hydro
        plant, a plant link and a link of a fuel."""
        rates = build_emission_rates(activity, lambda name: _find_rates(state, name, fuels))
        if rates.is_empty():
            return []
        sources = [
            _build_source(ExtensionKind.GENERATOR, _EMISSION_RATES_FIELD),
            _build_source(ExtensionKind.GENERATOR, _OWN_EMISSION_RATES_FIELD),
            _build_source(ExtensionKind.CONVERSION, _EMISSION_RATES_FIELD),
        ]
        self._reporter.record_derivation(
            ResultsVariable.EMISSIONS, sources, _FUEL_EMISSIONS_DERIVATION
        )
        return [build_annual_rows(build_emissions(activity, rates), ResultsVariable.EMISSIONS)]


def is_solved(state: State) -> bool:
    """Whether the network states an objective, which only a solve writes."""
    record = record_for(state.source_extensions, ExtensionKind.NETWORK, NETWORK_RECORD_NAME)
    return record is not None and record.objective is not None


def _fill_unproduced(production: pl.DataFrame, capacity: pl.DataFrame) -> pl.DataFrame:
    """A production of 0 for each rated component with no output; PyPSA's netCDF export
    leaves out a series that is 0 in every snapshot."""
    if capacity.is_empty():
        return production
    keys = [ResultsCol.COMPONENT, AnnualCol.YEAR]
    unproduced = capacity.join(production, on=keys, how="anti").select(
        ResultsCol.COMPONENT,
        ResultsCol.CATEGORY,
        AnnualCol.YEAR,
        pl.lit(_NO_PRODUCTION).alias(ResultsCol.VALUE),
    )
    return pl.concat([production, unproduced.cast(pl.Schema(PRODUCTION_SCHEMA))])


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
    return weights.select(_express_year()).unique().sort(AnnualCol.YEAR)


def _express_year() -> pl.Expr:
    return pl.col(PyPSATimeSeriesCol.SNAPSHOT).dt.year().cast(pl.Int32).alias(AnnualCol.YEAR)


def _build_all_production(state: State, weights: pl.DataFrame, fuels: FuelComponents) -> Production:
    """The energy of each component: what a link of a fuel takes in at bus0, and what every
    other component puts out."""
    links = _build_production(state, PyPSATable.LINKS, _build_link_delivery, weights, fuels)
    inputs = _build_production(state, PyPSATable.LINKS, _find_link_input, weights, fuels)
    is_fuel_link = pl.col(ResultsCol.COMPONENT).is_in(list(fuels.fuel_links))
    return Production(
        generators=_build_production(state, PyPSATable.GENERATORS, _find_dispatch, weights, fuels),
        storage=_build_production(state, PyPSATable.STORAGE_UNITS, _find_dispatch, weights, fuels),
        links=pl.concat([links.filter(~is_fuel_link), inputs.filter(is_fuel_link)]),
    )


def _find_dispatch(state: State, table: str) -> pl.LazyFrame | None:
    """The positive part of the dispatch of each component, in the `delivered` column."""
    return _find_positive(state, table, PyPSASolvedAttr.DISPATCH)


def _find_positive(state: State, table: str, attribute: str) -> pl.LazyFrame | None:
    series = state.source_time_series.get((table, attribute))
    if series is None:
        return None
    positive = pl.col(PyPSATimeSeriesCol.VALUE).clip(lower_bound=0.0).alias(_DELIVERED)
    return series.select(*_KEYS, positive)


def _find_link_input(state: State, table: str) -> pl.LazyFrame | None:
    """The power that each link takes in at bus0, in the `delivered` column."""
    return _find_positive(state, table, PyPSASolvedAttr.FLOW)


def _build_link_delivery(state: State, table: str) -> pl.LazyFrame | None:
    """The power each link delivers at the end that receives it; PyPSA states p0 and p1 as
    the power that the link withdraws, so the receiving end states a negative value."""
    sent = state.source_time_series.get((table, PyPSASolvedAttr.FLOW))
    received = state.source_time_series.get((table, PyPSASolvedAttr.FAR_END_FLOW))
    if sent is None or received is None:
        return None
    far_end = received.select(*_KEYS, pl.col(PyPSATimeSeriesCol.VALUE).alias(_DELIVERED))
    delivered = (-pl.col(PyPSATimeSeriesCol.VALUE)).clip(lower_bound=0.0) + (
        -pl.col(_DELIVERED)
    ).clip(lower_bound=0.0)
    joined = sent.join(far_end, on=_KEYS, how="inner")
    return joined.select(*_KEYS, delivered.alias(_DELIVERED))


def _build_production(
    state: State,
    table: str,
    find_power: _PowerFinder,
    weights: pl.DataFrame,
    fuels: FuelComponents,
) -> pl.DataFrame:
    """MWh in each year, by component: the power × the hours of the snapshot, summed."""
    power = find_power(state, table)
    if power is None:
        return pl.DataFrame(schema=PRODUCTION_SCHEMA)
    named = power.with_columns(_express_owner(state, table).alias(PyPSATimeSeriesCol.COMPONENT))
    produced = _sum_energy(named, weights)
    return (
        produced.join(_build_categories(state, table, fuels), on=ResultsCol.COMPONENT, how="left")
        .select(list(PRODUCTION_SCHEMA))
        .collect()
        .cast(pl.Schema(PRODUCTION_SCHEMA))
    )


def _sum_energy(power: pl.LazyFrame, weights: pl.DataFrame) -> pl.LazyFrame:
    energy = (pl.col(_DELIVERED) * pl.col(AnnualCol.WEIGHT)).sum().alias(ResultsCol.VALUE)
    return (
        power.join(weights.lazy(), on=PyPSATimeSeriesCol.SNAPSHOT, how="inner")
        .with_columns(_express_year())
        .group_by(PyPSATimeSeriesCol.COMPONENT, AnnualCol.YEAR, maintain_order=True)
        .agg(energy)
        .rename({PyPSATimeSeriesCol.COMPONENT: ResultsCol.COMPONENT})
    )


def _express_owner(state: State, table: str) -> pl.Expr:
    """The component that owns each row: the two-way link of a reverse link, else itself."""
    component = pl.col(PyPSATimeSeriesCol.COMPONENT)
    reverses = build_reverse_links(state) if table == PyPSATable.LINKS else {}
    if not reverses:
        return component
    return component.replace(reverses)


def build_reverse_links(state: State) -> dict[str, str]:
    """Each reverse link of the network, mapped to the two-way link it carries the flow back of."""
    topology = state.source_topology.get(PyPSATable.LINKS)
    if topology is None:
        return {}
    names = set(topology.select(PYPSA_NAME_COLUMN).collect().to_series().to_list())
    return {
        name: name.removesuffix(REVERSE_LINK_SUFFIX)
        for name in names
        if name.endswith(REVERSE_LINK_SUFFIX) and name.removesuffix(REVERSE_LINK_SUFFIX) in names
    }


def _build_categories(state: State, table: str, fuels: FuelComponents) -> pl.LazyFrame:
    """The category of each component: its carrier; a link has none, as Sienna has none, except
    a plant link, whose carrier names the plant."""
    topology = state.source_topology.get(table)
    if topology is None:
        return pl.LazyFrame(schema={ResultsCol.COMPONENT: pl.Utf8, ResultsCol.CATEGORY: pl.Utf8})
    rated = next(one for one in _RATED if one.table == table)
    carrier = _express_attribute(topology, PyPSAGeneratorCol.CARRIER)
    if rated.has_category:
        category = carrier
    else:
        is_plant = pl.col(PYPSA_NAME_COLUMN).is_in(list(fuels.plant_links))
        category = pl.when(is_plant).then(carrier).otherwise(pl.lit(None, dtype=pl.Utf8))
    return topology.select(
        pl.col(PYPSA_NAME_COLUMN).alias(ResultsCol.COMPONENT),
        category.cast(pl.Utf8).alias(ResultsCol.CATEGORY),
    )


def _build_capacity(state: State, years: pl.DataFrame, fuels: FuelComponents) -> pl.DataFrame:
    """The MW rating of each component that puts out electricity, for each year of the solve."""
    ratings = [
        _build_rating(state, rated, fuels)
        for rated in _RATED
        if state.source_topology.get(rated.table) is not None
    ]
    if not ratings:
        return pl.DataFrame()
    excluded = [*build_reverse_links(state), *fuels.generators, *fuels.fuel_links]
    rated = pl.concat(ratings).filter(~pl.col(ResultsCol.COMPONENT).is_in(excluded))
    return rated.collect().join(years, how="cross")


def _build_rating(state: State, rated: _Rated, fuels: FuelComponents) -> pl.LazyFrame:
    """A plant link rates the electricity that it can put out, p_nom × efficiency."""
    topology = state.source_topology[rated.table]
    rating = _express_attribute(topology, _P_NOM)
    if rated.is_rated_by_p_max_pu:
        is_plant = pl.col(PYPSA_NAME_COLUMN).is_in(list(fuels.plant_links))
        output = rating * _express_attribute(topology, _EFFICIENCY)
        rating = (
            pl.when(is_plant)
            .then(output)
            .otherwise(rating * _express_attribute(topology, _P_MAX_PU))
        )
    return topology.select(
        pl.col(PYPSA_NAME_COLUMN).alias(ResultsCol.COMPONENT),
        pl.lit(str(rated.component)).alias(AnnualCol.COMPONENT_TYPE),
        rating.cast(pl.Float64).alias(ResultsCol.VALUE),
    ).join(_build_categories(state, rated.table, fuels), on=ResultsCol.COMPONENT, how="left")


def _express_attribute(topology: pl.LazyFrame, attribute: str) -> pl.Expr:
    """A static attribute of the components, or PyPSA's default where the file omits it."""
    if attribute in topology.collect_schema().names():
        return pl.col(attribute)
    return pl.lit(_DEFAULTS[attribute])


def _find_rates(state: State, name: str, fuels: FuelComponents) -> dict[str, float] | None:
    """A link of a fuel emits for each MWh in; a plant link emits its own rate for each MWh of
    electricity, as the generator of its fuel emits for the fuel."""
    if name in fuels.fuel_links:
        conversion = record_for(state.source_extensions, ExtensionKind.CONVERSION, name)
        return None if conversion is None else conversion.emission_rates_t_per_mwh
    record = record_for(state.source_extensions, ExtensionKind.GENERATOR, name)
    if record is None:
        return None
    if name in fuels.plant_links:
        return record.own_emission_rates_t_per_mwh
    return record.emission_rates_t_per_mwh


def _build_source(component: str, attribute: str) -> SourceField:
    return SourceField(
        framework=Framework.PYPSA, component=component, name=ALL_COMPONENTS, attribute=attribute
    )
