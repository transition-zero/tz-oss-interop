"""Turn what a PyPSA network says about its own expansion into a Sienna portfolio.

The operations steps run first and write the base system, leaving out every component whose
capacity a build has yet to decide. This step reads the same network again and writes what
those steps had no home for: the candidates as technologies, the demand they have to meet,
the caps they run under, and the attributes tying each technology to the fleet the base
system already holds.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import ClassVar, Literal, NamedTuple

import polars as pl
from pydantic import BaseModel, Field

from interop.core.extensions import (
    ExtensionKind,
    ExtensionReader,
)
from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
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
    AREA_NAME,
    CARBON_CAP_SKIPS,
    FUEL_COL,
    LOAD_TYPE_COL,
    POWER_SYSTEMS_TYPE_COL,
    PRIME_MOVER_COL,
    REGION_COL,
    STORAGE_SKIPS,
    SUPPLY_SKIPS,
    TECHNICAL_LIFE_COL,
    TECHNOLOGY_NAME,
    TECHNOLOGY_TYPE,
    UNIT_SIZE_COL,
    CandidateTechnology,
    build_association_rows,
    build_carbon_cap_translations,
    build_carbon_caps_source_table,
    build_demand_translations,
    build_existing_devices_translations,
    build_existing_fleet_source_table,
    build_financial_data_events,
    build_portfolio_financial_data,
    build_retirement_potential_translations,
    build_scope_skips,
    build_storage_technology_translations,
    build_supply_translations,
    build_topology_mapping_translations,
    build_topology_source_table,
    enrich_from_names,
    fill_storage_technology_defaults,
    fill_supply_defaults,
)
from interop.plugins.shared.pypsa_sienna_user_mappings import CarrierMappings
from interop.plugins.shared.sienna_constants import (
    SIENNA_ID_COLUMN,
    SIENNA_NAME_COLUMN,
    SiennaACBusCol,
    SiennaComponent,
)
from interop.plugins.shared.sienna_investments_constants import (
    CARBON_CAPS_DESTINATION_SCHEMA,
    DEFAULT_BASE_YEAR,
    DEMAND_REQUIREMENT_DESTINATION_SCHEMA,
    EXISTING_DEVICES_DESTINATION_SCHEMA,
    PORTFOLIO_FINANCIAL_DATA_TABLE,
    RETIREMENT_POTENTIAL_DESTINATION_SCHEMA,
    STORAGE_TECHNOLOGY_DESTINATION_SCHEMA,
    SUPPLEMENTAL_ATTRIBUTE_ASSOCIATION_SCHEMA,
    SUPPLEMENTAL_ATTRIBUTE_ASSOCIATIONS_TABLE,
    SUPPLY_TECHNOLOGY_DESTINATION_SCHEMA,
    TOPOLOGY_MAPPING_DESTINATION_SCHEMA,
    SiennaInvestmentsComponent,
    SiennaSupplementalAttribute,
)
from interop.plugins.shared.translation_runner import (
    SkipRule,
    Translation,
    apply_translations,
    filter_component,
    finalise,
)

_BASE_GENERATOR_TYPES: tuple[SiennaComponent, ...] = (
    SiennaComponent.THERMAL_STANDARD,
    SiennaComponent.RENEWABLE_DISPATCH,
    SiennaComponent.RENEWABLE_NON_DISPATCH,
    SiennaComponent.HYDRO_DISPATCH,
)
_BASE_STORAGE_TYPES: tuple[SiennaComponent, ...] = (SiennaComponent.ENERGY_RESERVOIR_STORAGE,)

# The base system types a PyPSA StorageUnit becomes, which is the storage type plus the hydro
# type the operations steps write a storage unit with an inflow as.
_STORAGE_BASE_TYPES: tuple[SiennaComponent, ...] = (
    *_BASE_STORAGE_TYPES,
    SiennaComponent.HYDRO_DISPATCH,
)

_BASE_LOAD_TYPES: tuple[SiennaComponent, ...] = (
    SiennaComponent.POWER_LOAD,
    SiennaComponent.INTERRUPTIBLE_POWER_LOAD,
)

# A PyPSA build year of zero is what the network writes when it states none.
_UNSTATED_BUILD_YEAR = 0

_Schema = dict[str, pl.DataType | type[pl.DataType]]
_FillDefaults = Callable[[pl.DataFrame], pl.DataFrame]
_BuildTranslations = Callable[[int], list[Translation]]
_CandidateTranslations = Callable[[int, int], list[Translation]]


class _CandidateKind(NamedTuple):
    """Everything one candidate table does differently from the other."""

    source_table: str
    extendable_col: str
    fill: _FillDefaults
    skips: tuple[SkipRule, ...]
    extension: Literal[ExtensionKind.GENERATOR, ExtensionKind.STORAGE]
    with_fuel: bool
    build: _CandidateTranslations
    schema: _Schema
    component: SiennaInvestmentsComponent
    base_types: tuple[SiennaComponent, ...]


_SUPPLY = _CandidateKind(
    source_table=PyPSATable.GENERATORS,
    extendable_col=PyPSAGeneratorCol.P_NOM_EXTENDABLE,
    fill=fill_supply_defaults,
    skips=SUPPLY_SKIPS,
    extension=ExtensionKind.GENERATOR,
    with_fuel=True,
    build=build_supply_translations,
    schema=SUPPLY_TECHNOLOGY_DESTINATION_SCHEMA,
    component=SiennaInvestmentsComponent.SUPPLY_TECHNOLOGY,
    base_types=_BASE_GENERATOR_TYPES,
)

_STORAGE = _CandidateKind(
    source_table=PyPSATable.STORAGE_UNITS,
    extendable_col=PyPSAStorageUnitCol.P_NOM_EXTENDABLE,
    fill=fill_storage_technology_defaults,
    skips=STORAGE_SKIPS,
    extension=ExtensionKind.STORAGE,
    with_fuel=False,
    build=build_storage_technology_translations,
    schema=STORAGE_TECHNOLOGY_DESTINATION_SCHEMA,
    component=SiennaInvestmentsComponent.STORAGE_TECHNOLOGY,
    base_types=_STORAGE_BASE_TYPES,
)


class _Attribute(NamedTuple):
    """Everything one supplemental attribute is: its schema, its translations and its subject."""

    kind: SiennaSupplementalAttribute
    schema: _Schema
    build: _BuildTranslations
    name_col: str
    describes: Callable[[pl.DataFrame], list[str]]


# In the order the flat array lists them, which is the order their ids run in.
_ATTRIBUTES: tuple[_Attribute, ...] = (
    _Attribute(
        kind=SiennaSupplementalAttribute.EXISTING_DEVICES,
        schema=EXISTING_DEVICES_DESTINATION_SCHEMA,
        build=build_existing_devices_translations,
        name_col=TECHNOLOGY_NAME,
        describes=lambda source: source[TECHNOLOGY_TYPE].to_list(),
    ),
    _Attribute(
        kind=SiennaSupplementalAttribute.RETIREMENT_POTENTIAL,
        schema=RETIREMENT_POTENTIAL_DESTINATION_SCHEMA,
        build=build_retirement_potential_translations,
        name_col=TECHNOLOGY_NAME,
        describes=lambda source: source[TECHNOLOGY_TYPE].to_list(),
    ),
    _Attribute(
        kind=SiennaSupplementalAttribute.TOPOLOGY_MAPPING,
        schema=TOPOLOGY_MAPPING_DESTINATION_SCHEMA,
        build=build_topology_mapping_translations,
        name_col=AREA_NAME,
        describes=lambda source: [str(SiennaComponent.AREA)] * source.height,
    ),
)


class PypsaToSiennaInvestmentsMapTechnologiesParams(BaseModel):
    base_year: int = Field(
        default=DEFAULT_BASE_YEAR,
        description=(
            "the economic year every cost in the portfolio is quoted in; no PyPSA field states one"
        ),
    )


class _Candidates(NamedTuple):
    """One candidate table as translated, beside the rows it was translated from."""

    source: pl.DataFrame
    destination: pl.DataFrame


class _CandidateScope(NamedTuple):
    """What every candidate table reads off the base system, and the year its costs are in."""

    area_by_bus: Mapping[str, str | None]
    bus_names: Sequence[str]
    base_year: int


class _Years(NamedTuple):
    """The two ends of a base-system component's life, for the devices that state them."""

    built: dict[str, int]
    retired: dict[str, int]


class _Numbering:
    """One id counter, handed to each table written under it in turn.

    An association names a component by id alone, and an attribute by id alone, so ids are
    unique across a portfolio's components and across its flat attribute array rather than
    within either's own type.
    """

    def __init__(self) -> None:
        self.next_id = 1

    def take(self, rows: int) -> None:
        self.next_id += rows


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
        reader = state.extension_reader()
        bus_names = buses[SiennaACBusCol.NAME].to_list()
        area_by_bus = dict(zip(bus_names, buses[SiennaACBusCol.AREA].to_list(), strict=True))
        numbering = _Numbering()
        scope = _CandidateScope(area_by_bus=area_by_bus, bus_names=bus_names, base_year=base_year)
        supply = self._map_candidates(state, reader, scope, _SUPPLY, numbering)
        storage = self._map_candidates(state, reader, scope, _STORAGE, numbering)
        self._map_demand(state, area_by_bus, numbering)
        self._map_carbon_caps(state, reader, numbering)
        self._map_supplemental_attributes(state, buses, reader, supply, storage)
        state.destination_tables[PORTFOLIO_FINANCIAL_DATA_TABLE] = build_portfolio_financial_data(
            base_year
        )
        for event in build_financial_data_events(base_year):
            self._recorder.append(event)
        return state

    # --- candidates ---

    def _map_candidates(
        self,
        state: State,
        reader: ExtensionReader,
        scope: _CandidateScope,
        kind: _CandidateKind,
        numbering: _Numbering,
    ) -> _Candidates:
        table = self._candidate_rows(state, kind, scope.bus_names)
        if table.is_empty():
            return _Candidates(table, table)
        lookup = reader.read(kind.extension)
        names = table[PyPSAComponentCol.NAME].to_list()
        table = self._enrich_candidate(
            table,
            scope.area_by_bus,
            with_fuel=kind.with_fuel,
            unit_sizes=[lookup.get(name).unit_size_mw for name in names],
            technical_lives=[lookup.get(name).technical_life_years for name in names],
        )
        destination = self._write_table(
            state,
            table,
            kind.build(scope.base_year, numbering.next_id),
            kind.schema,
            kind.component,
            numbering,
        )
        return _Candidates(table, destination)

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
                PYPSA_COMPONENT_NAMING[kind.source_table],
                name_col=PyPSAComponentCol.NAME,
                carrier_col=PyPSAComponentCol.CARRIER,
                bus_col=PyPSAComponentCol.BUS,
                carriers=sorted(self._carrier_mappings.get_carriers()),
                translated_carriers=sorted(self._translated_carriers(kind)),
                bus_names=bus_names,
            ),
            *kind.skips,
        ]
        for rule in rules:
            table, _ = filter_component(table, rule.keep, rule.report, self._recorder)
        return table

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
        with_fuel: bool,
        unit_sizes: Sequence[float | None],
        technical_lives: Sequence[float | None],
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
        table = enrich_from_names(
            table, carrier_col, POWER_SYSTEMS_TYPE_COL, component_types, pl.Utf8
        )
        table = enrich_from_names(table, carrier_col, PRIME_MOVER_COL, prime_movers, pl.Utf8)
        table = enrich_from_names(table, carrier_col, FUEL_COL, fuels if with_fuel else {}, pl.Utf8)
        table = enrich_from_names(
            table, PyPSAComponentCol.BUS, REGION_COL, dict(area_by_bus), pl.Utf8
        )
        return table.with_columns(
            pl.Series(UNIT_SIZE_COL, list(unit_sizes), dtype=pl.Float64),
            pl.Series(TECHNICAL_LIFE_COL, list(technical_lives), dtype=pl.Float64),
        )

    def _write_table(
        self,
        state: State,
        table: pl.DataFrame,
        translations: list[Translation],
        schema: _Schema,
        component: str,
        numbering: _Numbering,
    ) -> pl.DataFrame:
        """Translate one source table into a destination table, and take its share of the ids."""
        out = finalise(
            apply_translations(table, translations, self._recorder),
            schema,
            self._recorder,
            component,
        )
        state.destination_tables[component] = out
        numbering.take(out.height)
        return out

    # --- demand ---

    def _map_demand(
        self, state: State, area_by_bus: Mapping[str, str | None], numbering: _Numbering
    ) -> None:
        """One requirement per load the base system holds, named as the type it holds it as."""
        src = state.source_topology.get(PyPSATable.LOADS)
        if src is None:
            return
        load_types = _base_load_types(state)
        table = src.collect().filter(pl.col(PyPSALoadCol.NAME).is_in(list(load_types)))
        if table.is_empty():
            return
        table = enrich_from_names(table, PyPSALoadCol.BUS, REGION_COL, dict(area_by_bus), pl.Utf8)
        table = enrich_from_names(table, PyPSALoadCol.NAME, LOAD_TYPE_COL, load_types, pl.Utf8)
        self._write_table(
            state,
            table,
            build_demand_translations(numbering.next_id),
            DEMAND_REQUIREMENT_DESTINATION_SCHEMA,
            SiennaInvestmentsComponent.DEMAND_REQUIREMENT,
            numbering,
        )

    # --- policy ---

    def _map_carbon_caps(
        self, state: State, reader: ExtensionReader, numbering: _Numbering
    ) -> None:
        records = reader.read(ExtensionKind.CONSTRAINT).read_all()
        if not records:
            return
        table = build_carbon_caps_source_table(records, self._model_components(state))
        for rule in CARBON_CAP_SKIPS:
            table, _ = filter_component(table, rule.keep, rule.report, self._recorder)
        if table.is_empty():
            return
        self._write_table(
            state,
            table,
            build_carbon_cap_translations(numbering.next_id),
            CARBON_CAPS_DESTINATION_SCHEMA,
            SiennaInvestmentsComponent.CARBON_CAPS,
            numbering,
        )

    @staticmethod
    def _model_components(state: State) -> set[str]:
        """Every component of the network a constraint could weight."""
        names: set[str] = set()
        for key in (PyPSATable.GENERATORS, PyPSATable.STORAGE_UNITS):
            src = state.source_topology.get(key)
            if src is not None:
                column = src.select(PYPSA_NAME_COLUMN).collect()[PYPSA_NAME_COLUMN]
                names |= set(column.to_list())
        return names

    # --- supplemental attributes ---

    def _map_supplemental_attributes(
        self,
        state: State,
        buses: pl.DataFrame,
        reader: ExtensionReader,
        supply: _Candidates,
        storage: _Candidates,
    ) -> None:
        """The three attributes, numbered from the one counter the flat array shares."""
        fleet = self._build_fleet(state, reader, supply, storage)
        sources: dict[SiennaSupplementalAttribute, pl.DataFrame] = {
            SiennaSupplementalAttribute.EXISTING_DEVICES: fleet,
            SiennaSupplementalAttribute.RETIREMENT_POTENTIAL: fleet,
            SiennaSupplementalAttribute.TOPOLOGY_MAPPING: build_topology_source_table(buses),
        }
        associations: list[pl.DataFrame] = []
        numbering = _Numbering()
        for attribute in _ATTRIBUTES:
            source = sources[attribute.kind]
            if source.is_empty():
                continue
            out = self._write_table(
                state,
                source,
                attribute.build(numbering.next_id),
                attribute.schema,
                attribute.kind,
                numbering,
            )
            associations.append(
                build_association_rows(
                    attribute.kind,
                    out[SIENNA_ID_COLUMN].to_list(),
                    source[attribute.name_col].to_list(),
                    attribute.describes(source),
                )
            )
        state.destination_tables[SUPPLEMENTAL_ATTRIBUTE_ASSOCIATIONS_TABLE] = (
            pl.concat(associations)
            if associations
            else pl.DataFrame(schema=SUPPLEMENTAL_ATTRIBUTE_ASSOCIATION_SCHEMA)
        )

    def _build_fleet(
        self,
        state: State,
        reader: ExtensionReader,
        supply: _Candidates,
        storage: _Candidates,
    ) -> pl.DataFrame:
        """The base-system devices each technology stands for, and the years they state."""
        years = self._read_years(state, reader)
        generators = _carrier_groups(
            state, PyPSATable.GENERATORS, _base_names(state, _BASE_GENERATOR_TYPES)
        )
        storages = _carrier_groups(
            state, PyPSATable.STORAGE_UNITS, _base_names(state, _BASE_STORAGE_TYPES)
        )
        generator_years = years[PyPSATable.GENERATORS]
        storage_years = years[PyPSATable.STORAGE_UNITS]
        return pl.concat(
            [
                build_existing_fleet_source_table(
                    _technologies(
                        supply,
                        SiennaInvestmentsComponent.SUPPLY_TECHNOLOGY,
                        PyPSAComponent.GENERATOR,
                    ),
                    generators,
                    generator_years.built,
                    generator_years.retired,
                ),
                build_existing_fleet_source_table(
                    _technologies(
                        storage,
                        SiennaInvestmentsComponent.STORAGE_TECHNOLOGY,
                        PyPSAComponent.STORAGE_UNIT,
                    ),
                    storages,
                    storage_years.built,
                    storage_years.retired,
                ),
            ]
        )

    @staticmethod
    def _read_years(state: State, reader: ExtensionReader) -> dict[str, _Years]:
        """Each device's build year, from the network, and its retirement year, from the sidecar.

        PyPSA carries a build year on the component and nothing for the other end of a life,
        which is why one of the pair comes off the sidecar. A generator and a storage unit may
        share a name, so each source table keeps its own pair of maps.
        """
        years: dict[str, _Years] = {}
        generators = reader.read(ExtensionKind.GENERATOR)
        storages = reader.read(ExtensionKind.STORAGE)
        for key, lookup in (
            (PyPSATable.GENERATORS, generators),
            (PyPSATable.STORAGE_UNITS, storages),
        ):
            built: dict[str, int] = {}
            retired: dict[str, int] = {}
            years[key] = _Years(built=built, retired=retired)
            src = state.source_topology.get(key)
            if src is None:
                continue
            table = src.collect()
            has_build_year = PyPSAGeneratorCol.BUILD_YEAR in table.columns
            for row in table.iter_rows(named=True):
                name = row[PYPSA_NAME_COLUMN]
                year = row[PyPSAGeneratorCol.BUILD_YEAR] if has_build_year else None
                if year is not None and int(year) != _UNSTATED_BUILD_YEAR:
                    built[name] = int(year)
                retirement_year = lookup.get(name).retirement_year
                if retirement_year is not None:
                    retired[name] = retirement_year
        return years


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


def _carrier_groups(
    state: State, source_table: str, in_base_system: set[str]
) -> dict[str, list[str]]:
    """The base-system components of each carrier, in the order the network states them."""
    src = state.source_topology.get(source_table)
    if src is None:
        return {}
    table = src.collect()
    groups: dict[str, list[str]] = {}
    for name, carrier in zip(
        table[PYPSA_NAME_COLUMN].to_list(),
        table[PyPSAComponentCol.CARRIER].to_list(),
        strict=True,
    ):
        if name in in_base_system:
            groups.setdefault(carrier, []).append(name)
    return groups


def _technologies(
    candidates: _Candidates, component: SiennaInvestmentsComponent, device_class: str
) -> list[CandidateTechnology]:
    """Each translated technology, beside the fleet its base-system devices make up."""
    if candidates.destination.is_empty():
        return []
    return [
        CandidateTechnology(
            name=name,
            component_type=str(component),
            device_class=device_class,
            carrier=carrier,
        )
        for name, carrier in zip(
            candidates.destination[SIENNA_NAME_COLUMN].to_list(),
            candidates.source[PyPSAComponentCol.CARRIER].to_list(),
            strict=True,
        )
    ]
