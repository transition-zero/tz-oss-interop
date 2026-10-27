"""Turn what a PyPSA network says about its own expansion into a Sienna portfolio.

The operations steps run first and write the base system, leaving out every component whose
capacity a build has yet to decide. This step reads the same network again and writes what
those steps had no home for: the candidates as technologies, the demand they have to meet,
the caps they run under, and the attributes tying each technology to the fleet the base
system already holds.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from functools import partial
from typing import ClassVar, Literal, NamedTuple

import polars as pl
from pydantic import BaseModel, Field

from interop.core.extensions import (
    ExtensionKind,
    ExtensionReader,
)
from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import Framework
from interop.plugins.shared.pypsa_constants import (
    PYPSA_COMPONENT_NAMING,
    PYPSA_NAME_COLUMN,
    PyPSAComponent,
    PyPSAComponentCol,
    PyPSAGeneratorCol,
    PyPSALoadCol,
    PyPSAStorageUnitCol,
    PyPSATable,
)
from interop.plugins.shared.pypsa_sienna_investments_translations import (
    FOM_CHARGE_COL,
    FUEL_COL,
    GENERATOR_SOURCE,
    LOAD_TYPE_COL,
    NO_RETIREMENT_COST_NOTE,
    NO_RETIREMENT_DERIVATION,
    POWER_SYSTEMS_TYPE_COL,
    PRIME_MOVER_COL,
    PYPSA_TO_SIENNA_INVESTMENTS,
    REGION_COL,
    STORAGE_UNIT_SOURCE,
    TECHNICAL_LIFE_COL,
    UNIT_SIZE_COL,
    CandidateTechnology,
    InvestmentsSource,
    PortfolioMapper,
    PortfolioTable,
    Schema,
    build_carbon_cap_skips,
    build_carbon_cap_translations,
    build_carbon_caps_source_table,
    build_demand_translations,
    build_existing_fleet_source_table,
    build_financial_data_events,
    build_portfolio_financial_data,
    build_scope_skips,
    build_storage_skips,
    build_storage_technology_translations,
    build_supply_skips,
    build_supply_translations,
    constraint_source,
    fill_storage_technology_defaults,
    fill_supply_defaults,
)
from interop.plugins.shared.pypsa_sienna_user_mappings import CarrierMappings
from interop.plugins.shared.sienna_constants import (
    SIENNA_NAME_COLUMN,
    SiennaACBusCol,
    SiennaComponent,
)
from interop.plugins.shared.sienna_investments_constants import (
    CARBON_CAPS_DESTINATION_SCHEMA,
    DEFAULT_BASE_YEAR,
    DEMAND_REQUIREMENT_DESTINATION_SCHEMA,
    PORTFOLIO_FINANCIAL_DATA_TABLE,
    STORAGE_TECHNOLOGY_DESTINATION_SCHEMA,
    SUPPLY_TECHNOLOGY_DESTINATION_SCHEMA,
    SiennaInvestmentsComponent,
)
from interop.plugins.shared.translation_runner import (
    SkipRule,
    Translation,
    drop_skipped,
)

_GENERATOR_BASE_TYPES: tuple[SiennaComponent, ...] = (
    SiennaComponent.THERMAL_STANDARD,
    SiennaComponent.RENEWABLE_DISPATCH,
    SiennaComponent.RENEWABLE_NON_DISPATCH,
    SiennaComponent.HYDRO_DISPATCH,
)

# The base system types a PyPSA StorageUnit becomes, which is the storage type plus the hydro
# type the operations steps write a storage unit with an inflow as.
_STORAGE_BASE_TYPES: tuple[SiennaComponent, ...] = (
    SiennaComponent.ENERGY_RESERVOIR_STORAGE,
    SiennaComponent.HYDRO_DISPATCH,
)

# The base system types each PyPSA class alone writes, which a fleet is matched against. Only
# a StorageUnit becomes HydroDispatch, and a Generator may carry the name of a StorageUnit.
_GENERATOR_FLEET_TYPES: tuple[SiennaComponent, ...] = (
    SiennaComponent.THERMAL_STANDARD,
    SiennaComponent.RENEWABLE_DISPATCH,
    SiennaComponent.RENEWABLE_NON_DISPATCH,
)

# The loads a portfolio's demand is read from, as the report names them.
_LOADS = InvestmentsSource(
    framework=Framework.PYPSA,
    pipeline=PYPSA_TO_SIENNA_INVESTMENTS,
    component=PyPSAComponent.LOAD,
    display=PYPSA_COMPONENT_NAMING[PyPSATable.LOADS].display,
    plural=PYPSA_COMPONENT_NAMING[PyPSATable.LOADS].plural,
    retirement_derivation=NO_RETIREMENT_DERIVATION,
    retirement_cost_note=NO_RETIREMENT_COST_NOTE,
)

_BASE_LOAD_TYPES: tuple[SiennaComponent, ...] = (
    SiennaComponent.POWER_LOAD,
    SiennaComponent.INTERRUPTIBLE_POWER_LOAD,
)

_DEMAND_TABLE = PortfolioTable(
    SiennaInvestmentsComponent.DEMAND_REQUIREMENT,
    DEMAND_REQUIREMENT_DESTINATION_SCHEMA,
    partial(build_demand_translations, _LOADS),
)

# A PyPSA build year of zero is what the network writes when it states none.
_UNSTATED_BUILD_YEAR = 0

_FillDefaults = Callable[[pl.DataFrame], pl.DataFrame]
_CandidateTranslations = Callable[[InvestmentsSource, int, int], list[Translation]]


class _CandidateKind(NamedTuple):
    """Everything one candidate table does differently from the other."""

    source_table: str
    extendable_col: str
    fill: _FillDefaults
    skips: Callable[[InvestmentsSource], tuple[SkipRule, ...]]
    extension: Literal[ExtensionKind.GENERATOR, ExtensionKind.STORAGE]
    build: _CandidateTranslations
    schema: Schema
    component: SiennaInvestmentsComponent
    base_types: tuple[SiennaComponent, ...]
    fleet_types: tuple[SiennaComponent, ...]
    device_class: str
    build_year_col: str
    source: InvestmentsSource


_SUPPLY = _CandidateKind(
    source_table=PyPSATable.GENERATORS,
    extendable_col=PyPSAGeneratorCol.P_NOM_EXTENDABLE,
    fill=fill_supply_defaults,
    skips=build_supply_skips,
    extension=ExtensionKind.GENERATOR,
    build=build_supply_translations,
    schema=SUPPLY_TECHNOLOGY_DESTINATION_SCHEMA,
    component=SiennaInvestmentsComponent.SUPPLY_TECHNOLOGY,
    base_types=_GENERATOR_BASE_TYPES,
    fleet_types=_GENERATOR_FLEET_TYPES,
    device_class=PyPSAComponent.GENERATOR,
    build_year_col=PyPSAGeneratorCol.BUILD_YEAR,
    source=GENERATOR_SOURCE,
)

_STORAGE = _CandidateKind(
    source_table=PyPSATable.STORAGE_UNITS,
    extendable_col=PyPSAStorageUnitCol.P_NOM_EXTENDABLE,
    fill=fill_storage_technology_defaults,
    skips=build_storage_skips,
    extension=ExtensionKind.STORAGE,
    build=build_storage_technology_translations,
    schema=STORAGE_TECHNOLOGY_DESTINATION_SCHEMA,
    component=SiennaInvestmentsComponent.STORAGE_TECHNOLOGY,
    base_types=_STORAGE_BASE_TYPES,
    fleet_types=_STORAGE_BASE_TYPES,
    device_class=PyPSAComponent.STORAGE_UNIT,
    build_year_col=PyPSAStorageUnitCol.BUILD_YEAR,
    source=STORAGE_UNIT_SOURCE,
)

# In the order they take their ids, which one counter hands out in turn.
_CANDIDATE_KINDS: tuple[_CandidateKind, ...] = (_SUPPLY, _STORAGE)


class PypsaToSiennaInvestmentsMapTechnologiesParams(BaseModel):
    base_year: int = Field(
        default=DEFAULT_BASE_YEAR,
        description=(
            "the economic year every cost in the portfolio is quoted in; no PyPSA field states one"
        ),
    )


class _CandidateScope(NamedTuple):
    """What every candidate table reads off the base system, and the year its costs are in."""

    area_by_bus: Mapping[str, str | None]
    bus_names: Sequence[str]
    base_year: int


class _Years(NamedTuple):
    """The two ends of a base-system component's life, for the devices that state them."""

    built: dict[str, int]
    retired: dict[str, int]


class PypsaToSiennaInvestmentsMapTechnologies(TranslationStep):
    name: ClassVar[str] = "pypsa_to_sienna_investments_map_technologies"
    params_schema: ClassVar[type[BaseModel] | None] = PypsaToSiennaInvestmentsMapTechnologiesParams

    def __init__(self, recorder: ScopedRecorder, carrier_mappings: CarrierMappings) -> None:
        self._recorder = recorder
        self._carrier_mappings = carrier_mappings

    def run(self, state: State, params: BaseModel | None) -> State:
        base_year = (
            params.base_year
            if isinstance(params, PypsaToSiennaInvestmentsMapTechnologiesParams)
            else DEFAULT_BASE_YEAR
        )
        buses = state.destination_tables.get(SiennaComponent.AC_BUS)
        if buses is None:
            return state
        reader = state.extension_reader(self._recorder)
        bus_names = buses[SiennaACBusCol.NAME].to_list()
        area_by_bus = dict(zip(bus_names, buses[SiennaACBusCol.AREA].to_list(), strict=True))
        mapper = PortfolioMapper(self._recorder, GENERATOR_SOURCE)
        scope = _CandidateScope(area_by_bus=area_by_bus, bus_names=bus_names, base_year=base_year)
        candidates = [
            (kind, self._map_candidates(state, reader, scope, kind, mapper))
            for kind in _CANDIDATE_KINDS
        ]
        self._map_demand(state, area_by_bus, mapper)
        self._map_carbon_caps(state, reader, mapper, candidates)
        fleet = self._build_fleet(state, reader, scope, candidates)
        mapper.map_supplemental_attributes(state, fleet, buses)
        state.destination_tables[PORTFOLIO_FINANCIAL_DATA_TABLE] = build_portfolio_financial_data(
            base_year
        )
        for event in build_financial_data_events(base_year):
            self._recorder.append(event)
        return state

    def _map_candidates(
        self,
        state: State,
        reader: ExtensionReader,
        scope: _CandidateScope,
        kind: _CandidateKind,
        mapper: PortfolioMapper,
    ) -> pl.DataFrame:
        """The rows one candidate table was translated from, once the table is written."""
        table = self._candidate_rows(state, kind, scope.bus_names)
        if table.is_empty():
            return table
        lookup = reader.read(kind.extension)
        names = table[PyPSAComponentCol.NAME].to_list()
        table = self._enrich_candidate(
            table,
            scope.area_by_bus,
            unit_sizes=[lookup.get(name).unit_size_mw for name in names],
            technical_lives=[lookup.get(name).technical_life_years for name in names],
            fom_charges=[lookup.get(name).fom_charge_per_mw_year for name in names],
        )
        build = partial(kind.build, kind.source, scope.base_year)
        mapper.map_table(state, table, PortfolioTable(kind.component, kind.schema, build))
        return table

    def _candidate_rows(
        self, state: State, kind: _CandidateKind, bus_names: Sequence[str]
    ) -> pl.DataFrame:
        """The rows of one source table that state a build, less what cannot be translated.

        A component whose capacity the network fixes is not a candidate and belongs to the
        base system alone, so it is filtered out silently rather than reported as dropped.
        """
        src = state.source_topology.get(kind.source_table)
        if src is None:
            return pl.DataFrame()
        table = kind.fill(src.collect()).filter(pl.col(kind.extendable_col))
        rules = [
            *build_scope_skips(
                kind.source,
                name_col=PyPSAComponentCol.NAME,
                carrier_col=PyPSAComponentCol.CARRIER,
                bus_col=PyPSAComponentCol.BUS,
                carriers=sorted(self._carrier_mappings.get_carriers()),
                translated_carriers=sorted(self._translated_carriers(kind)),
                bus_names=bus_names,
            ),
            *kind.skips(kind.source),
        ]
        return drop_skipped(table, rules, self._recorder)

    def _translated_carriers(self, kind: _CandidateKind) -> set[str]:
        """The carriers the mappings file sends to a type this kind of candidate becomes."""
        carriers: set[str] = set()
        for component in kind.base_types:
            carriers |= self._carrier_mappings.get_carriers(component)
        return carriers

    def _enrich_candidate(
        self,
        table: pl.DataFrame,
        area_by_bus: Mapping[str, str | None],
        *,
        unit_sizes: Sequence[float | None],
        technical_lives: Sequence[float | None],
        fom_charges: Sequence[float | None],
    ) -> pl.DataFrame:
        """Add what the carrier, the bus and the sidecar say about a candidate."""
        component_types = {
            mapping.pypsa_carrier: str(mapping.sienna_component_type)
            for mapping in self._carrier_mappings.carriers
        }
        prime_movers = {
            carrier: str(mover)
            for carrier, mover in self._carrier_mappings.get_prime_mover_map().items()
        }
        fuels = {
            carrier: str(target[0])
            for carrier, target in self._carrier_mappings.get_thermal_carrier_map().items()
        }
        carrier_col = PyPSAComponentCol.CARRIER
        return table.with_columns(
            _looked_up(carrier_col, component_types, POWER_SYSTEMS_TYPE_COL),
            _looked_up(carrier_col, prime_movers, PRIME_MOVER_COL),
            _looked_up(carrier_col, fuels, FUEL_COL),
            _looked_up(PyPSAComponentCol.BUS, dict(area_by_bus), REGION_COL),
            pl.Series(UNIT_SIZE_COL, list(unit_sizes), dtype=pl.Float64),
            pl.Series(TECHNICAL_LIFE_COL, list(technical_lives), dtype=pl.Float64),
            pl.Series(FOM_CHARGE_COL, list(fom_charges), dtype=pl.Float64),
        )

    def _map_demand(
        self, state: State, area_by_bus: Mapping[str, str | None], mapper: PortfolioMapper
    ) -> None:
        """One requirement per load the base system holds, named as the type it holds it as."""
        src = state.source_topology.get(PyPSATable.LOADS)
        if src is None:
            return
        load_types = _base_load_types(state)
        table = src.collect().filter(pl.col(PyPSALoadCol.NAME).is_in(list(load_types)))
        if table.is_empty():
            return
        table = table.with_columns(
            _looked_up(PyPSALoadCol.BUS, dict(area_by_bus), REGION_COL),
            _looked_up(PyPSALoadCol.NAME, load_types, LOAD_TYPE_COL),
        )
        mapper.map_table(state, table, _DEMAND_TABLE)

    def _map_carbon_caps(
        self,
        state: State,
        reader: ExtensionReader,
        mapper: PortfolioMapper,
        candidates: Sequence[tuple[_CandidateKind, pl.DataFrame]],
    ) -> None:
        records = reader.read(ExtensionKind.CONSTRAINT).read_all()
        if not records:
            return
        table = build_carbon_caps_source_table(records, _model_components(state, candidates))
        source = constraint_source(Framework.PYPSA, PYPSA_TO_SIENNA_INVESTMENTS)
        table = drop_skipped(table, build_carbon_cap_skips(source), self._recorder)
        if table.is_empty():
            return
        mapper.map_table(
            state,
            table,
            PortfolioTable(
                SiennaInvestmentsComponent.CARBON_CAPS,
                CARBON_CAPS_DESTINATION_SCHEMA,
                partial(build_carbon_cap_translations, source),
            ),
        )

    def _build_fleet(
        self,
        state: State,
        reader: ExtensionReader,
        scope: _CandidateScope,
        candidates: Sequence[tuple[_CandidateKind, pl.DataFrame]],
    ) -> pl.DataFrame:
        """The base-system devices each technology stands for, and the years they state."""
        fleets: list[pl.DataFrame] = []
        for kind, found in candidates:
            source = state.source_topology.get(kind.source_table)
            devices = pl.DataFrame() if source is None else source.collect()
            years = self._years(devices, reader, kind)
            fleets.append(
                build_existing_fleet_source_table(
                    _technologies(found, kind.component, kind.device_class),
                    _fleet_groups(devices, _base_names(state, kind.fleet_types), scope.area_by_bus),
                    years.built,
                    years.retired,
                )
            )
        return pl.concat(fleets)

    @staticmethod
    def _years(devices: pl.DataFrame, reader: ExtensionReader, kind: _CandidateKind) -> _Years:
        """Each device's build year, from the network, and its retirement year, from the sidecar.

        PyPSA carries a build year on the component and nothing for the other end of a life,
        which is why one of the pair comes off the sidecar. A generator and a storage unit may
        share a name, so each source table is read on its own.
        """
        built: dict[str, int] = {}
        retired: dict[str, int] = {}
        if devices.is_empty():
            return _Years(built=built, retired=retired)
        lookup = reader.read(kind.extension)
        has_build_year = kind.build_year_col in devices.columns
        for row in devices.iter_rows(named=True):
            name = row[PYPSA_NAME_COLUMN]
            year = row[kind.build_year_col] if has_build_year else None
            if year is not None and int(year) != _UNSTATED_BUILD_YEAR:
                built[name] = int(year)
            retirement_year = lookup.get(name).retirement_year
            if retirement_year is not None:
                retired[name] = retirement_year
        return _Years(built=built, retired=retired)


def _looked_up(name_col: str, values: Mapping[str, str | None], dest_col: str) -> pl.Expr:
    """What a mapping says about each row, null where the mapping names no such row."""
    return (
        pl.col(name_col)
        .replace_strict(dict(values), default=None, return_dtype=pl.Utf8)
        .alias(dest_col)
    )


def _model_components(
    state: State, candidates: Sequence[tuple[_CandidateKind, pl.DataFrame]]
) -> set[tuple[str, str]]:
    """Every component of the network a constraint could weight, with the class that wrote it.

    The devices the base system holds, and the candidates the portfolio holds. A generator
    neither document carries emits nothing a cap could bound, so a constraint reaches the
    whole model without naming it. Each name travels with its PyPSA class, because a
    constraint can weight an object of another class that carries the same name.
    """
    components: set[tuple[str, str]] = set()
    for kind, found in candidates:
        names = set(_base_names(state, kind.fleet_types))
        if not found.is_empty():
            names |= set(found[PyPSAComponentCol.NAME].to_list())
        components |= {(name, kind.device_class) for name in names}
    return components


def _base_load_types(state: State) -> dict[str, str]:
    """The Sienna type the base system wrote each load as, by load name."""
    types: dict[str, str] = {}
    for component in _BASE_LOAD_TYPES:
        table = state.destination_tables.get(component)
        if table is not None:
            types |= {name: str(component) for name in table[SIENNA_NAME_COLUMN].to_list()}
    return types


def _base_names(state: State, types: tuple[SiennaComponent, ...]) -> set[str]:
    """Every component of the given types the base system holds."""
    names: set[str] = set()
    for key in types:
        table = state.destination_tables.get(key)
        if table is not None:
            names |= set(table[SIENNA_NAME_COLUMN].to_list())
    return names


def _fleet_groups(
    devices: pl.DataFrame,
    in_base_system: set[str],
    area_by_bus: Mapping[str, str | None],
) -> dict[tuple[str, str | None], list[str]]:
    """The base-system components of each carrier and area, in the order the network states them.

    A technology sits in one region, so a device of its carrier in another region is not a
    plant it adds to and not a plant a build of it may retire.
    """
    groups: dict[tuple[str, str | None], list[str]] = {}
    if devices.is_empty():
        return groups
    for name, carrier, bus in zip(
        devices[PYPSA_NAME_COLUMN].to_list(),
        devices[PyPSAComponentCol.CARRIER].to_list(),
        devices[PyPSAComponentCol.BUS].to_list(),
        strict=True,
    ):
        if name in in_base_system:
            groups.setdefault((carrier, area_by_bus.get(bus)), []).append(name)
    return groups


def _technologies(
    candidates: pl.DataFrame, component: SiennaInvestmentsComponent, device_class: str
) -> list[CandidateTechnology]:
    """Each translated technology, beside the fleet its base-system devices make up."""
    if candidates.is_empty():
        return []
    return [
        CandidateTechnology(
            name=name,
            component_type=str(component),
            device_class=device_class,
            carrier=carrier,
            region=region,
        )
        for name, carrier, region in zip(
            candidates[PyPSAComponentCol.NAME].to_list(),
            candidates[PyPSAComponentCol.CARRIER].to_list(),
            candidates[REGION_COL].to_list(),
            strict=True,
        )
    ]
