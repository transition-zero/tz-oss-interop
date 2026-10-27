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

from interop.core.extensions import (
    ConversionExtension,
    ExtensionKind,
    GeneratorExtension,
    record_for,
)
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.annual_results import (
    CAPACITY_SCHEMA,
    PRODUCTION_SCHEMA,
    AnnualDerivation,
    AnnualRowsMapper,
    Production,
    ResultsLeg,
    drop_components,
)
from interop.plugins.shared.constants import (
    ALL_COMPONENTS,
    Framework,
    require_extension_attribute,
)
from interop.plugins.shared.pypsa_constants import (
    PYPSA_GENERATOR_DEFAULTS,
    PYPSA_LINK_DEFAULTS,
    PYPSA_NAME_COLUMN,
    PYPSA_STORAGE_UNIT_DEFAULTS,
    PyPSAComponent,
    PyPSAComponentCol,
    PyPSADefault,
    PyPSAGeneratorCol,
    PyPSALinkCol,
    PyPSASolvedAttr,
    PyPSATable,
    PyPSATimeSeriesCol,
)
from interop.plugins.shared.pypsa_fuel_components import FuelComponents
from interop.plugins.shared.pypsa_link_places import build_one_location_links
from interop.plugins.shared.pypsa_network_view import PypsaNetworkView
from interop.plugins.shared.results_constants import PYPSA_TO_RESULTS, ResultsCol
from interop.plugins.shared.sienna_results_constants import AnnualCol
from interop.ports.outbound.reporting import SourceField

_UNWEIGHTED = 1.0
_NO_PRODUCTION = 0.0
_EMISSION_RATES_FIELD = "emission_rates_t_per_mwh"
_GENERATOR_RATES = require_extension_attribute(GeneratorExtension, _EMISSION_RATES_FIELD)
_OWN_RATES = require_extension_attribute(GeneratorExtension, "own_emission_rates_t_per_mwh")
_CONVERSION_RATES = require_extension_attribute(ConversionExtension, _EMISSION_RATES_FIELD)
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
    "row, and a plant link makes the electricity that it delivers at bus1; a link that its "
    "extensions record marks as a conversion has no row"
)
_INSTALLED_CAPACITY_DERIVATION = (
    "p_nom, the nameplate, for a generator; p_nom × p_max_pu for a storage unit or a link, and "
    "once for a two-way link and its reverse link; p_nom × efficiency for a plant link; no row "
    "for a link that its extensions record marks as a conversion → installed_capacity at 1 "
    "January of the year"
)


class _Rated(NamedTuple):
    """A component table that states rated power, and how the results name its components."""

    table: str
    component: PyPSAComponent
    defaults: dict[str, PyPSADefault]
    has_category: bool
    # A generator's p_max_pu is what it may make, so its nameplate is p_nom alone.
    is_rated_by_p_max_pu: bool


# PyPSA names p_nom, p_max_pu, efficiency and carrier the same on all three tables.
_RATED = (
    _Rated(
        PyPSATable.GENERATORS,
        PyPSAComponent.GENERATOR,
        PYPSA_GENERATOR_DEFAULTS,
        has_category=True,
        is_rated_by_p_max_pu=False,
    ),
    _Rated(
        PyPSATable.STORAGE_UNITS,
        PyPSAComponent.STORAGE_UNIT,
        PYPSA_STORAGE_UNIT_DEFAULTS,
        has_category=True,
        is_rated_by_p_max_pu=True,
    ),
    _Rated(
        PyPSATable.LINKS,
        PyPSAComponent.LINK,
        PYPSA_LINK_DEFAULTS,
        has_category=False,
        is_rated_by_p_max_pu=True,
    ),
)
_RATED_BY_TABLE = {rated.table: rated for rated in _RATED}
# Finds the power of the components of one table, by snapshot, or None where it states none.
_PowerFinder = Callable[[State, str], pl.LazyFrame | None]


def _build_source(component: str, attribute: str) -> SourceField:
    return SourceField(
        framework=Framework.PYPSA, component=component, name=ALL_COMPONENTS, attribute=attribute
    )


_ENERGY_SOURCES = [
    _build_source(PyPSAComponent.GENERATOR, PyPSASolvedAttr.DISPATCH),
    _build_source(PyPSAComponent.STORAGE_UNIT, PyPSASolvedAttr.DISPATCH),
    _build_source(PyPSAComponent.LINK, PyPSASolvedAttr.FLOW),
    _build_source(PyPSAComponent.LINK, PyPSASolvedAttr.FAR_END_FLOW),
    _build_source(PyPSATable.SNAPSHOTS, PyPSASolvedAttr.GENERATOR_WEIGHTING),
]
_PRODUCTION = AnnualDerivation(_ENERGY_SOURCES, _PRODUCTION_DERIVATION)
_INSTALLED_CAPACITY = AnnualDerivation(
    [_build_source(rated.component, PyPSAGeneratorCol.P_NOM) for rated in _RATED],
    _INSTALLED_CAPACITY_DERIVATION,
)
_EMISSIONS = AnnualDerivation(
    [
        *_ENERGY_SOURCES,
        _build_source(PyPSAComponent.GENERATOR, _GENERATOR_RATES),
        _build_source(PyPSAComponent.LINK, _OWN_RATES),
        _build_source(PyPSAComponent.LINK, _CONVERSION_RATES),
    ],
    _FUEL_EMISSIONS_DERIVATION,
)


class PypsaAnnualResultsMapper:
    """Writes `production`, `installed_capacity` and `emissions` for a weighted solve."""

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._mapper = AnnualRowsMapper(recorder, ResultsLeg(Framework.PYPSA, PYPSA_TO_RESULTS))

    def map_annual(self, state: State, view: PypsaNetworkView) -> list[pl.LazyFrame]:
        weights = _find_weights(state)
        if weights is None or not _is_annual(state, weights):
            return []
        self._report_lines(state, view)
        activity = _build_all_production(state, weights, view)
        production = _drop_fuels(activity, view.fuels).drop_links(view.conversion_lines)
        capacity = _build_capacity(state, _build_years(weights), view)
        produced = production.build_table()
        if view.is_solved:
            produced = _fill_unproduced(produced, capacity)
        return [
            *self._mapper.map_production(produced, _PRODUCTION),
            *self._mapper.map_installed_capacity(capacity, produced, _INSTALLED_CAPACITY),
            *self._map_emissions(state, activity, view.fuels),
        ]

    def _report_lines(self, state: State, view: PypsaNetworkView) -> None:
        """Report each conversion link, and each link at one location that states no mark."""
        conversions = view.conversion_lines
        self._mapper.report_conversions(PyPSAComponent.LINK, conversions)
        unmarked = build_one_location_links(state, view.fuels) - conversions
        self._mapper.report_unmarked(PyPSAComponent.LINK, unmarked - set(view.reverse_links))

    def _map_emissions(
        self, state: State, activity: Production, fuels: FuelComponents
    ) -> list[pl.LazyFrame]:
        """Emissions of each component with a rate: a generator, a storage unit such as a hydro
        plant, a plant link and a link of a fuel."""
        fuel_links = activity.links.filter(pl.col(ResultsCol.COMPONENT).is_in(list(fuels.links)))
        energy = pl.concat([activity.generators, activity.storage, fuel_links])
        return self._mapper.map_emissions(
            energy, lambda name: _find_rates(state, name, fuels), _EMISSIONS
        )


def _drop_fuels(production: Production, fuels: FuelComponents) -> Production:
    """The production of electricity: no generator and no link of a fuel."""
    return Production(
        generators=drop_components(production.generators, fuels.generators),
        storage=production.storage,
        links=drop_components(production.links, fuels.fuel_links),
    )


def _fill_unproduced(production: pl.DataFrame, capacity: pl.DataFrame) -> pl.DataFrame:
    """A production of 0 for each rated component with no output; PyPSA's netCDF export
    leaves out a series that is 0 in every snapshot."""
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


def _build_all_production(
    state: State, weights: pl.DataFrame, view: PypsaNetworkView
) -> Production:
    """The energy of each component: what a link of a fuel takes in at bus0, and what every
    other component puts out."""
    energy = _EnergyBuilder(state, weights, view)
    is_fuel_link = pl.col(ResultsCol.COMPONENT).is_in(list(view.fuels.fuel_links))
    links = energy.build_production(PyPSATable.LINKS, _build_link_delivery)
    inputs = energy.build_production(PyPSATable.LINKS, _find_link_input)
    return Production(
        generators=energy.build_production(PyPSATable.GENERATORS, _find_dispatch),
        storage=energy.build_production(PyPSATable.STORAGE_UNITS, _find_dispatch),
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


class _EnergyBuilder:
    """Builds the MWh of the components of one table, in each year of the solve."""

    def __init__(self, state: State, weights: pl.DataFrame, view: PypsaNetworkView) -> None:
        self._state = state
        self._weights = weights
        self._view = view

    def build_production(self, table: str, find_power: _PowerFinder) -> pl.DataFrame:
        """MWh in each year, by component: the power × the hours of the snapshot, summed."""
        power = find_power(self._state, table)
        if power is None:
            return pl.DataFrame(schema=PRODUCTION_SCHEMA)
        owner = _express_owner(table, self._view.reverse_links)
        named = power.with_columns(owner.alias(PyPSATimeSeriesCol.COMPONENT))
        categories = _build_categories(self._state, table, self._view.fuels)
        return (
            _build_yearly_energy(named, self._weights)
            .join(categories, on=ResultsCol.COMPONENT, how="left")
            .select(list(PRODUCTION_SCHEMA))
            .collect()
            .cast(pl.Schema(PRODUCTION_SCHEMA))
        )


def _build_yearly_energy(power: pl.LazyFrame, weights: pl.DataFrame) -> pl.LazyFrame:
    energy = (pl.col(_DELIVERED) * pl.col(AnnualCol.WEIGHT)).sum().alias(ResultsCol.VALUE)
    return (
        power.join(weights.lazy(), on=PyPSATimeSeriesCol.SNAPSHOT, how="inner")
        .with_columns(_express_year())
        .group_by(PyPSATimeSeriesCol.COMPONENT, AnnualCol.YEAR, maintain_order=True)
        .agg(energy)
        .rename({PyPSATimeSeriesCol.COMPONENT: ResultsCol.COMPONENT})
    )


def _express_owner(table: str, reverse_links: dict[str, str]) -> pl.Expr:
    """The component that owns each row: the two-way link of a reverse link, else itself."""
    component = pl.col(PyPSATimeSeriesCol.COMPONENT)
    if table != PyPSATable.LINKS or not reverse_links:
        return component
    return component.replace(reverse_links)


def _build_categories(state: State, table: str, fuels: FuelComponents) -> pl.LazyFrame:
    """The category of each component: its carrier; a link has none, as Sienna has none, except
    a plant link, whose carrier names the plant."""
    topology = state.source_topology.get(table)
    if topology is None:
        return pl.LazyFrame(schema={ResultsCol.COMPONENT: pl.Utf8, ResultsCol.CATEGORY: pl.Utf8})
    rated = _RATED_BY_TABLE[table]
    carrier = _express_attribute(topology, rated, PyPSAComponentCol.CARRIER)
    if rated.has_category:
        category = carrier
    else:
        is_plant = pl.col(PYPSA_NAME_COLUMN).is_in(list(fuels.plant_links))
        category = pl.when(is_plant).then(carrier).otherwise(pl.lit(None, dtype=pl.Utf8))
    return topology.select(
        pl.col(PYPSA_NAME_COLUMN).alias(ResultsCol.COMPONENT),
        category.cast(pl.Utf8).alias(ResultsCol.CATEGORY),
    )


def _build_capacity(state: State, years: pl.DataFrame, view: PypsaNetworkView) -> pl.DataFrame:
    """The MW rating of each component that puts out electricity, for each year of the solve."""
    ratings = [
        _build_rating(state, rated, view.fuels)
        for rated in _RATED
        if state.source_topology.get(rated.table) is not None
    ]
    if not ratings:
        return pl.DataFrame(schema=CAPACITY_SCHEMA)
    fuels = view.fuels
    excluded = [*view.reverse_links, *fuels.generators, *fuels.fuel_links, *view.conversion_lines]
    rated = pl.concat(ratings).filter(~pl.col(ResultsCol.COMPONENT).is_in(excluded))
    return rated.collect().join(years, how="cross")


def _build_rating(state: State, rated: _Rated, fuels: FuelComponents) -> pl.LazyFrame:
    topology = state.source_topology[rated.table]
    return topology.select(
        pl.col(PYPSA_NAME_COLUMN).alias(ResultsCol.COMPONENT),
        pl.lit(str(rated.component)).alias(AnnualCol.COMPONENT_TYPE),
        _express_rating(topology, rated, fuels).cast(pl.Float64).alias(ResultsCol.VALUE),
    ).join(_build_categories(state, rated.table, fuels), on=ResultsCol.COMPONENT, how="left")


def _express_rating(topology: pl.LazyFrame, rated: _Rated, fuels: FuelComponents) -> pl.Expr:
    """A plant link rates the electricity that it can put out, p_nom × efficiency."""
    rating = _express_attribute(topology, rated, PyPSAGeneratorCol.P_NOM)
    if not rated.is_rated_by_p_max_pu:
        return rating
    available = rating * _express_attribute(topology, rated, PyPSALinkCol.P_MAX_PU)
    if rated.table != PyPSATable.LINKS:
        return available
    is_plant = pl.col(PYPSA_NAME_COLUMN).is_in(list(fuels.plant_links))
    output = rating * _express_attribute(topology, rated, PyPSALinkCol.EFFICIENCY)
    return pl.when(is_plant).then(output).otherwise(available)


def _express_attribute(topology: pl.LazyFrame, rated: _Rated, attribute: str) -> pl.Expr:
    """A static attribute of the components, or PyPSA's default where the file omits it."""
    if attribute in topology.collect_schema().names():
        return pl.col(attribute)
    return pl.lit(rated.defaults[attribute])


def _find_rates(state: State, name: str, fuels: FuelComponents) -> dict[str, float] | None:
    """A link of a fuel emits for each MWh in; a plant link emits its own rate for each MWh of
    electricity, as the generator of its fuel emits for the fuel. Every other link emits
    nothing, so the caller gives no other link."""
    if name in fuels.fuel_links:
        conversion = record_for(state.source_extensions, ExtensionKind.CONVERSION, name)
        return None if conversion is None else conversion.emission_rates_t_per_mwh
    record = record_for(state.source_extensions, ExtensionKind.GENERATOR, name)
    if record is None:
        return None
    if name in fuels.plant_links:
        return record.own_emission_rates_t_per_mwh
    return record.emission_rates_t_per_mwh
