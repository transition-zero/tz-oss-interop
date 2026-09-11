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
    FOM_CHARGE_COL,
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
    SUPPLEMENTAL_ATTRIBUTE_ORDER,
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
    build: _CandidateTranslations
    schema: _Schema
    component: SiennaInvestmentsComponent
    base_types: tuple[SiennaComponent, ...]
    fleet_types: tuple[SiennaComponent, ...]
    device_class: str
    build_year_col: str


_SUPPLY = _CandidateKind(
    source_table=PyPSATable.GENERATORS,
    extendable_col=PyPSAGeneratorCol.P_NOM_EXTENDABLE,
    fill=fill_supply_defaults,
    skips=SUPPLY_SKIPS,
    extension=ExtensionKind.GENERATOR,
    build=build_supply_translations,
    schema=SUPPLY_TECHNOLOGY_DESTINATION_SCHEMA,
    component=SiennaInvestmentsComponent.SUPPLY_TECHNOLOGY,
    base_types=_GENERATOR_BASE_TYPES,
    fleet_types=_GENERATOR_FLEET_TYPES,
    device_class=PyPSAComponent.GENERATOR,
    build_year_col=PyPSAGeneratorCol.BUILD_YEAR,
)

_STORAGE = _CandidateKind(
    source_table=PyPSATable.STORAGE_UNITS,
    extendable_col=PyPSAStorageUnitCol.P_NOM_EXTENDABLE,
    fill=fill_storage_technology_defaults,
    skips=STORAGE_SKIPS,
    extension=ExtensionKind.STORAGE,
    build=build_storage_technology_translations,
    schema=STORAGE_TECHNOLOGY_DESTINATION_SCHEMA,
    component=SiennaInvestmentsComponent.STORAGE_TECHNOLOGY,
    base_types=_STORAGE_BASE_TYPES,
    fleet_types=_STORAGE_BASE_TYPES,
    device_class=PyPSAComponent.STORAGE_UNIT,
    build_year_col=PyPSAStorageUnitCol.BUILD_YEAR,
)

# In the order they take their ids, which one counter hands out in turn.
_CANDIDATE_KINDS: tuple[_CandidateKind, ...] = (_SUPPLY, _STORAGE)


class _Attribute(NamedTuple):
    schema: _Schema
    build: _BuildTranslations
    name_col: str
    describes: Callable[[pl.DataFrame], list[str]]


# An attribute takes its id from its place in the flat array, so the step numbers the types in
# the order the sink writes them, SUPPLEMENTAL_ATTRIBUTE_ORDER.
_ATTRIBUTES: dict[SiennaSupplementalAttribute, _Attribute] = {
    SiennaSupplementalAttribute.EXISTING_DEVICES: _Attribute(
        schema=EXISTING_DEVICES_DESTINATION_SCHEMA,
        build=build_existing_devices_translations,
        name_col=TECHNOLOGY_NAME,
        describes=lambda source: source[TECHNOLOGY_TYPE].to_list(),
    ),
    SiennaSupplementalAttribute.RETIREMENT_POTENTIAL: _Attribute(
        schema=RETIREMENT_POTENTIAL_DESTINATION_SCHEMA,
        build=build_retirement_potential_translations,
        name_col=TECHNOLOGY_NAME,
        describes=lambda source: source[TECHNOLOGY_TYPE].to_list(),
    ),
    SiennaSupplementalAttribute.TOPOLOGY_MAPPING: _Attribute(
        schema=TOPOLOGY_MAPPING_DESTINATION_SCHEMA,
        build=build_topology_mapping_translations,
        name_col=AREA_NAME,
        describes=lambda source: [str(SiennaComponent.AREA)] * source.height,
    ),
}


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


class _Numbering:
    """One id counter, handed to each table written under it in turn.

    An association names a component by id alone, and an attribute by id alone, so ids are
    unique across a portfolio's components and across its flat attribute array rather than
    within either's own type.
    """

    def __init__(self) -> None:
        self.next_id = 1


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
        candidates = [
            (kind, self._map_candidates(state, reader, scope, kind, numbering))
            for kind in _CANDIDATE_KINDS
        ]
        self._map_demand(state, area_by_bus, numbering)
        self._map_carbon_caps(state, reader, numbering, candidates)
        self._map_supplemental_attributes(state, buses, reader, scope, candidates)
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
        numbering: _Numbering,
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
        self._write_table(
            state,
            table,
            partial(kind.build, scope.base_year),
            kind.schema,
            kind.component,
            numbering,
        )
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

    def _write_table(
        self,
        state: State,
        table: pl.DataFrame,
        build: _BuildTranslations,
        schema: _Schema,
        component: str,
        numbering: _Numbering,
    ) -> pl.DataFrame:
        """Translate one source table into a destination table, and take its share of the ids."""
        out = finalise(
            apply_translations(table, build(numbering.next_id), self._recorder),
            schema,
            self._recorder,
            component,
        )
        state.destination_tables[component] = out
        numbering.next_id += out.height
        return out

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
        table = table.with_columns(
            _looked_up(PyPSALoadCol.BUS, dict(area_by_bus), REGION_COL),
            _looked_up(PyPSALoadCol.NAME, load_types, LOAD_TYPE_COL),
        )
        self._write_table(
            state,
            table,
            build_demand_translations,
            DEMAND_REQUIREMENT_DESTINATION_SCHEMA,
            SiennaInvestmentsComponent.DEMAND_REQUIREMENT,
            numbering,
        )

    def _map_carbon_caps(
        self,
        state: State,
        reader: ExtensionReader,
        numbering: _Numbering,
        candidates: Sequence[tuple[_CandidateKind, pl.DataFrame]],
    ) -> None:
        records = reader.read(ExtensionKind.CONSTRAINT).read_all()
        if not records:
            return
        table = build_carbon_caps_source_table(records, _model_components(state, candidates))
        for rule in CARBON_CAP_SKIPS:
            table, _ = filter_component(table, rule.keep, rule.report, self._recorder)
        if table.is_empty():
            return
        self._write_table(
            state,
            table,
            build_carbon_cap_translations,
            CARBON_CAPS_DESTINATION_SCHEMA,
            SiennaInvestmentsComponent.CARBON_CAPS,
            numbering,
        )

    def _map_supplemental_attributes(
        self,
        state: State,
        buses: pl.DataFrame,
        reader: ExtensionReader,
        scope: _CandidateScope,
        candidates: Sequence[tuple[_CandidateKind, pl.DataFrame]],
    ) -> None:
        """The three attributes, numbered from the one counter the flat array shares."""
        fleet = self._build_fleet(state, reader, scope, candidates)
        sources: dict[SiennaSupplementalAttribute, pl.DataFrame] = {
            SiennaSupplementalAttribute.EXISTING_DEVICES: fleet,
            SiennaSupplementalAttribute.RETIREMENT_POTENTIAL: fleet,
            SiennaSupplementalAttribute.TOPOLOGY_MAPPING: build_topology_source_table(buses),
        }
        associations: list[pl.DataFrame] = []
        numbering = _Numbering()
        for kind in SUPPLEMENTAL_ATTRIBUTE_ORDER:
            attribute = _ATTRIBUTES[kind]
            source = sources[kind]
            if source.is_empty():
                continue
            out = self._write_table(
                state, source, attribute.build, attribute.schema, kind, numbering
            )
            associations.append(
                build_association_rows(
                    kind,
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
