"""Turn what a PyPSA network says about its own expansion into a Sienna portfolio.

The operations steps run first and write the base system, leaving out every component whose
capacity a build has yet to decide. This step reads the same network again and writes what
those steps had no home for: the candidates as technologies, the demand they have to meet,
the caps they run under, and the attributes tying each technology to the fleet the base
system already holds.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import ClassVar, NamedTuple

import polars as pl
from pydantic import BaseModel, Field

from interop.core.extensions import (
    ConstraintExtension,
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
    AREA_NAME,
    CARBON_CAP_SKIPS,
    CARBON_CAP_TRANSLATIONS,
    DEMAND_TRANSLATIONS,
    FUEL_COL,
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
    build_carbon_caps_source_table,
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
    empty_association_rows,
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
    PORTFOLIO_FINANCIAL_DATA_TABLE,
    STORAGE_TECHNOLOGY_DESTINATION_SCHEMA,
    SUPPLEMENTAL_ATTRIBUTE_ASSOCIATIONS_TABLE,
    SUPPLEMENTAL_ATTRIBUTE_ORDER,
    SUPPLEMENTAL_ATTRIBUTE_SCHEMAS,
    SUPPLY_TECHNOLOGY_DESTINATION_SCHEMA,
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

# The base system types a candidate generator's fleet is drawn from, and the one a candidate
# storage unit's fleet is drawn from.
_BASE_GENERATOR_TYPES: tuple[SiennaComponent, ...] = (
    SiennaComponent.THERMAL_STANDARD,
    SiennaComponent.RENEWABLE_DISPATCH,
    SiennaComponent.RENEWABLE_NON_DISPATCH,
    SiennaComponent.HYDRO_DISPATCH,
)
_BASE_STORAGE_TYPES: tuple[SiennaComponent, ...] = (SiennaComponent.ENERGY_RESERVOIR_STORAGE,)

# A PyPSA build year of zero is what the network writes when it states none.
_UNSTATED_BUILD_YEAR = 0

_FillDefaults = Callable[[pl.DataFrame], pl.DataFrame]
_BuildTranslations = Callable[[int], list[Translation]]

# How each supplemental attribute is translated, once its source table is built.
_ATTRIBUTE_TRANSLATIONS: dict[SiennaSupplementalAttribute, _BuildTranslations] = {
    SiennaSupplementalAttribute.EXISTING_DEVICES: build_existing_devices_translations,
    SiennaSupplementalAttribute.RETIREMENT_POTENTIAL: build_retirement_potential_translations,
    SiennaSupplementalAttribute.TOPOLOGY_MAPPING: build_topology_mapping_translations,
}


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

    @property
    def is_empty(self) -> bool:
        return self.destination.is_empty()


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
        reader = ExtensionReader(state.source_extensions, Framework.PYPSA)
        area_by_bus = dict(
            zip(
                buses[SiennaACBusCol.NAME].to_list(),
                buses[SiennaACBusCol.AREA].to_list(),
                strict=True,
            )
        )
        supply = self._map_supply(state, reader, area_by_bus, base_year)
        storage = self._map_storage(state, reader, area_by_bus, base_year)
        self._map_demand(state, area_by_bus)
        self._map_carbon_caps(state)
        self._map_supplemental_attributes(state, buses, reader, supply, storage)
        state.destination_tables[PORTFOLIO_FINANCIAL_DATA_TABLE] = build_portfolio_financial_data(
            base_year
        )
        for event in build_financial_data_events(base_year):
            self._recorder.append(event)
        return state

    # --- candidates ---

    def _map_supply(
        self,
        state: State,
        reader: ExtensionReader,
        area_by_bus: Mapping[str, str | None],
        base_year: int,
    ) -> _Candidates:
        table = self._candidate_rows(
            state,
            PyPSATable.GENERATORS,
            PyPSAGeneratorCol.P_NOM_EXTENDABLE,
            fill_supply_defaults,
            SUPPLY_SKIPS,
        )
        if table.is_empty():
            return _Candidates(table, table)
        lookup = reader.read(ExtensionKind.GENERATOR)
        names = table[PyPSAComponentCol.NAME].to_list()
        table = self._enrich_candidate(
            table,
            area_by_bus,
            with_fuel=True,
            unit_sizes=[lookup.get(name).unit_size_mw for name in names],
            technical_lives=[lookup.get(name).technical_life_years for name in names],
        )
        return self._translate(
            state,
            table,
            build_supply_translations(base_year),
            SUPPLY_TECHNOLOGY_DESTINATION_SCHEMA,
            SiennaInvestmentsComponent.SUPPLY_TECHNOLOGY,
        )

    def _map_storage(
        self,
        state: State,
        reader: ExtensionReader,
        area_by_bus: Mapping[str, str | None],
        base_year: int,
    ) -> _Candidates:
        table = self._candidate_rows(
            state,
            PyPSATable.STORAGE_UNITS,
            PyPSAStorageUnitCol.P_NOM_EXTENDABLE,
            fill_storage_technology_defaults,
            STORAGE_SKIPS,
        )
        if table.is_empty():
            return _Candidates(table, table)
        lookup = reader.read(ExtensionKind.STORAGE)
        names = table[PyPSAComponentCol.NAME].to_list()
        table = self._enrich_candidate(
            table,
            area_by_bus,
            with_fuel=False,
            unit_sizes=[lookup.get(name).unit_size_mw for name in names],
            technical_lives=[lookup.get(name).technical_life_years for name in names],
        )
        return self._translate(
            state,
            table,
            build_storage_technology_translations(base_year),
            STORAGE_TECHNOLOGY_DESTINATION_SCHEMA,
            SiennaInvestmentsComponent.STORAGE_TECHNOLOGY,
        )

    def _candidate_rows(
        self,
        state: State,
        source_table: str,
        extendable_col: str,
        fill: _FillDefaults,
        skips: tuple[SkipRule, ...],
    ) -> pl.DataFrame:
        """The rows of one source table that state a build, less what cannot be translated.

        A component whose capacity the network fixes is not a candidate and belongs to the
        base system alone, so it is filtered out silently rather than reported as dropped.
        """
        src = state.source_topology.get(source_table)
        if src is None:
            return pl.DataFrame()
        table = fill(src.collect()).filter(pl.col(extendable_col))
        rules = [
            *build_scope_skips(
                PYPSA_COMPONENT_NAMING[source_table],
                name_col=PyPSAComponentCol.NAME,
                carrier_col=PyPSAComponentCol.CARRIER,
                bus_col=PyPSAComponentCol.BUS,
                carriers=sorted(self._carrier_mappings.get_carriers()),
                bus_names=self._ac_bus_names(state),
            ),
            *skips,
        ]
        for rule in rules:
            table, _ = filter_component(table, rule.keep, rule.report, self._recorder)
        return table

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
            carrier: str(component)
            for carrier, component in self._carrier_mappings.get_component_type_map().items()
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

    def _translate(
        self,
        state: State,
        table: pl.DataFrame,
        translations: list[Translation],
        schema: dict[str, pl.DataType | type[pl.DataType]],
        component: SiennaInvestmentsComponent,
    ) -> _Candidates:
        dst = apply_translations(table, translations, self._recorder)
        out = finalise(dst, schema, self._recorder, component)
        state.destination_tables[component] = out
        return _Candidates(table, out)

    # --- demand ---

    def _map_demand(self, state: State, area_by_bus: Mapping[str, str | None]) -> None:
        src = state.source_topology.get(PyPSATable.LOADS)
        if src is None:
            return
        table = src.collect().filter(pl.col(PyPSALoadCol.BUS).is_in(self._ac_bus_names(state)))
        if table.is_empty():
            return
        table = enrich_from_names(table, PyPSALoadCol.BUS, REGION_COL, dict(area_by_bus), pl.Utf8)
        dst = apply_translations(table, DEMAND_TRANSLATIONS, self._recorder)
        state.destination_tables[SiennaInvestmentsComponent.DEMAND_REQUIREMENT] = finalise(
            dst,
            DEMAND_REQUIREMENT_DESTINATION_SCHEMA,
            self._recorder,
            SiennaInvestmentsComponent.DEMAND_REQUIREMENT,
        )

    # --- policy ---

    def _map_carbon_caps(self, state: State) -> None:
        records = [
            record
            for record in state.source_extensions.get(ExtensionKind.CONSTRAINT, [])
            if isinstance(record, ConstraintExtension)
        ]
        if not records:
            return
        table = build_carbon_caps_source_table(records, self._model_components(state))
        for rule in CARBON_CAP_SKIPS:
            table, _ = filter_component(table, rule.keep, rule.report, self._recorder)
        if table.is_empty():
            return
        dst = apply_translations(table, CARBON_CAP_TRANSLATIONS, self._recorder)
        state.destination_tables[SiennaInvestmentsComponent.CARBON_CAPS] = finalise(
            dst,
            CARBON_CAPS_DESTINATION_SCHEMA,
            self._recorder,
            SiennaInvestmentsComponent.CARBON_CAPS,
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
        next_id = 1
        for attribute in SUPPLEMENTAL_ATTRIBUTE_ORDER:
            source = sources[attribute]
            if source.is_empty():
                continue
            translations = _ATTRIBUTE_TRANSLATIONS[attribute](next_id)
            dst = apply_translations(source, translations, self._recorder)
            out = finalise(
                dst, SUPPLEMENTAL_ATTRIBUTE_SCHEMAS[attribute], self._recorder, attribute
            )
            state.destination_tables[attribute] = out
            associations.append(_associate(attribute, source, out))
            next_id += out.height
        state.destination_tables[SUPPLEMENTAL_ATTRIBUTE_ASSOCIATIONS_TABLE] = (
            pl.concat(associations) if associations else empty_association_rows()
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
        return pl.concat(
            [
                build_existing_fleet_source_table(
                    _technologies(
                        supply,
                        SiennaInvestmentsComponent.SUPPLY_TECHNOLOGY,
                        PyPSAComponent.GENERATOR,
                    ),
                    generators,
                    years.built,
                    years.retired,
                ),
                build_existing_fleet_source_table(
                    _technologies(
                        storage,
                        SiennaInvestmentsComponent.STORAGE_TECHNOLOGY,
                        PyPSAComponent.STORAGE_UNIT,
                    ),
                    storages,
                    years.built,
                    years.retired,
                ),
            ]
        )

    @staticmethod
    def _read_years(state: State, reader: ExtensionReader) -> _Years:
        """Each device's build year, from the network, and its retirement year, from the sidecar.

        PyPSA carries a build year on the component and nothing for the other end of a life,
        which is why one of the pair comes off the sidecar.
        """
        built: dict[str, int] = {}
        retired: dict[str, int] = {}
        generators = reader.read(ExtensionKind.GENERATOR)
        storages = reader.read(ExtensionKind.STORAGE)
        for key, lookup in (
            (PyPSATable.GENERATORS, generators),
            (PyPSATable.STORAGE_UNITS, storages),
        ):
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
        return _Years(built=built, retired=retired)

    @staticmethod
    def _ac_bus_names(state: State) -> list[str]:
        buses = state.destination_tables.get(SiennaComponent.AC_BUS)
        return buses[SiennaACBusCol.NAME].to_list() if buses is not None else []


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
    if candidates.is_empty:
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


def _associate(
    attribute: SiennaSupplementalAttribute, source: pl.DataFrame, out: pl.DataFrame
) -> pl.DataFrame:
    """The association rows for one attribute table, naming what each row describes."""
    if attribute is SiennaSupplementalAttribute.TOPOLOGY_MAPPING:
        names = source[AREA_NAME].to_list()
        types = [str(SiennaComponent.AREA)] * len(names)
    else:
        names = source[TECHNOLOGY_NAME].to_list()
        types = source[TECHNOLOGY_TYPE].to_list()
    return build_association_rows(attribute, out[SIENNA_ID_COLUMN].to_list(), names, types)
