"""Turn the canonical stage of an OSeMOSYS model into a Sienna investments portfolio.

The operations step runs first and writes the base system: the fleet of the earliest year in
scope. This step reads the canonical stage again over every year in scope, and writes what a
plan may build, the demand that it must meet, the caps that it runs under, and the attributes
that tie each technology to the fleet of the base system.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from typing import ClassVar, NamedTuple

import polars as pl
from pydantic import BaseModel

from interop.core.extensions import ExtensionKind, append_extensions
from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.osemosys_canonical.constants import (
    REGION,
    STORAGE,
    TECHNOLOGY,
)
from interop.plugins.shared.osemosys_sienna_investments_translations import (
    FLEET_SOURCE,
    LOADS_SOURCE,
    STORAGE_FIELDS,
    STORAGE_SCHEMA,
    SUPPLY_FIELDS,
    SUPPLY_SCHEMA,
    TECHNOLOGY_KEYS,
    TRANSPORT_FIELDS,
    TRANSPORT_SCHEMA,
    FleetFamily,
    InvestmentPlan,
    StorageCandidates,
    SupplyCandidates,
    TransportCandidates,
    build_availability_series,
    build_carbon_cap_translations,
    build_demand_series,
    build_fleet_table,
    build_osemosys_financial_data,
    build_osemosys_financial_events,
    build_plan_year,
    build_pollutant_limits,
    build_storage_candidates,
    build_storage_translations,
    build_supply_candidates,
    build_supply_translations,
    build_technology_extensions,
    build_transport_candidates,
    build_transport_translations,
    find_investment_plan,
    find_region_discount_rate,
    set_portfolio_series,
)
from interop.plugins.shared.osemosys_sienna_translations import OperationsYear
from interop.plugins.shared.osemosys_sienna_user_mappings import OsemosysSiennaCarrierMappings
from interop.plugins.shared.pypsa_sienna_investments_translations import (
    AREA_NAME,
    OSEMOSYS_TO_SIENNA_INVESTMENTS,
    TECHNOLOGY_NAME,
    TECHNOLOGY_TYPE,
    build_association_rows,
    build_demand_translations,
    build_existing_devices_translations,
    build_retirement_potential_translations,
    build_topology_mapping_translations,
    build_topology_source_table,
)
from interop.plugins.shared.sienna_constants import (
    SIENNA_ID_COLUMN,
    SIENNA_NAME_COLUMN,
    SiennaComponent,
)
from interop.plugins.shared.sienna_investments_constants import (
    CARBON_CAPS_DESTINATION_SCHEMA,
    DEMAND_REQUIREMENT_DESTINATION_SCHEMA,
    EXISTING_DEVICES_DESTINATION_SCHEMA,
    PORTFOLIO_FINANCIAL_DATA_TABLE,
    RETIREMENT_POTENTIAL_DESTINATION_SCHEMA,
    SUPPLEMENTAL_ATTRIBUTE_ASSOCIATION_SCHEMA,
    SUPPLEMENTAL_ATTRIBUTE_ASSOCIATIONS_TABLE,
    SUPPLEMENTAL_ATTRIBUTE_ORDER,
    TOPOLOGY_MAPPING_DESTINATION_SCHEMA,
    SiennaInvestmentsComponent,
    SiennaSupplementalAttribute,
)
from interop.plugins.shared.sienna_investments_sources import (
    GENERATOR_TYPES,
    build_demand_table,
    read_area_by_bus,
)
from interop.plugins.shared.translation_runner import Translation, apply_translations, finalise

_Schema = dict[str, pl.DataType | type[pl.DataType]]
_BuildTranslations = Callable[[int], list[Translation]]

_STORAGE_KEYS = [REGION, STORAGE]


class _Numbering:
    """One id counter, which each table written under it takes its share of in turn.

    An association names a component or an attribute by id alone, so ids are unique across the
    components of a portfolio, and across its flat attribute array.
    """

    def __init__(self) -> None:
        self.next_id = 1


@dataclass(frozen=True)
class _Candidates:
    supply: SupplyCandidates
    storage: StorageCandidates
    transport: TransportCandidates


class _Attribute(NamedTuple):
    schema: _Schema
    build: _BuildTranslations
    name_col: str
    describes: Callable[[pl.DataFrame], list[str]]


_ATTRIBUTES: dict[SiennaSupplementalAttribute, _Attribute] = {
    SiennaSupplementalAttribute.EXISTING_DEVICES: _Attribute(
        schema=EXISTING_DEVICES_DESTINATION_SCHEMA,
        build=partial(build_existing_devices_translations, FLEET_SOURCE),
        name_col=TECHNOLOGY_NAME,
        describes=lambda source: source[TECHNOLOGY_TYPE].to_list(),
    ),
    SiennaSupplementalAttribute.RETIREMENT_POTENTIAL: _Attribute(
        schema=RETIREMENT_POTENTIAL_DESTINATION_SCHEMA,
        build=partial(build_retirement_potential_translations, FLEET_SOURCE),
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


log = logging.getLogger(__name__)

_NO_YEAR_WARNING = "%s: the model states no year in scope, so the portfolio holds no technology"


class OsemosysToSiennaInvestmentsMapTechnologies(TranslationStep):
    """Writes the portfolio of every year in scope beside the base system of the earliest.

    Declaring the carrier mappings on ``__init__`` makes ``UserMappingsLoader`` ask for the file.
    """

    name: ClassVar[str] = "osemosys_to_sienna_investments_map_technologies"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(
        self,
        recorder: ScopedRecorder,
        osemosys_sienna_mappings: OsemosysSiennaCarrierMappings,
    ) -> None:
        self._recorder = recorder
        self._mappings = osemosys_sienna_mappings

    def run(self, state: State, params: BaseModel | None) -> State:
        buses = state.destination_tables.get(SiennaComponent.AC_BUS)
        plan = find_investment_plan(state)
        if plan is None:
            log.warning(_NO_YEAR_WARNING, OSEMOSYS_TO_SIENNA_INVESTMENTS)
            return state
        if buses is None:
            return state
        plan_years = {year: build_plan_year(state, plan, year) for year in plan.years}
        numbering = _Numbering()
        candidates = self._map_candidates(state, plan, plan_years, numbering)
        self._map_demand(state, numbering)
        self._map_carbon_caps(state, plan, numbering)
        self._map_series(state, plan_years, candidates)
        self._map_supplemental_attributes(state, plan, buses, candidates)
        self._map_extensions(state, candidates)
        self._map_financial_data(state, plan)
        return state

    # --- the components ----------------------------------------------------------------------

    def _map_candidates(
        self,
        state: State,
        plan: InvestmentPlan,
        plan_years: Mapping[int, OperationsYear],
        numbering: _Numbering,
    ) -> _Candidates:
        base = plan_years[plan.base_year]
        candidates = _Candidates(
            supply=build_supply_candidates(state, plan_years, plan, self._mappings, self._recorder),
            storage=build_storage_candidates(state, base, plan, self._mappings, self._recorder),
            transport=build_transport_candidates(state, plan, self._recorder),
        )
        tables: Sequence[tuple[pl.DataFrame, _BuildTranslations, _Schema, str]] = (
            (
                candidates.supply.table,
                partial(build_supply_translations, plan.cost_year),
                SUPPLY_SCHEMA,
                SiennaInvestmentsComponent.SUPPLY_TECHNOLOGY,
            ),
            (
                candidates.storage.table,
                partial(build_storage_translations, plan.cost_year),
                STORAGE_SCHEMA,
                SiennaInvestmentsComponent.STORAGE_TECHNOLOGY,
            ),
            (
                candidates.transport.table,
                partial(build_transport_translations, plan.cost_year),
                TRANSPORT_SCHEMA,
                SiennaInvestmentsComponent.AGGREGATE_TRANSPORT_TECHNOLOGY,
            ),
        )
        for table, build, schema, component in tables:
            self._map_table(state, table, build, schema, component, numbering)
        return candidates

    def _map_demand(self, state: State, numbering: _Numbering) -> None:
        """One requirement for each load that the base system holds."""
        table = build_demand_table(state, read_area_by_bus(state))
        self._map_table(
            state,
            table,
            partial(build_demand_translations, LOADS_SOURCE),
            DEMAND_REQUIREMENT_DESTINATION_SCHEMA,
            SiennaInvestmentsComponent.DEMAND_REQUIREMENT,
            numbering,
        )

    def _map_carbon_caps(self, state: State, plan: InvestmentPlan, numbering: _Numbering) -> None:
        limits = build_pollutant_limits(state, plan, self._recorder)
        append_extensions(state.destination_extensions, ExtensionKind.CONSTRAINT, limits.records)
        self._map_table(
            state,
            limits.caps,
            build_carbon_cap_translations,
            CARBON_CAPS_DESTINATION_SCHEMA,
            SiennaInvestmentsComponent.CARBON_CAPS,
            numbering,
        )

    def _map_table(
        self,
        state: State,
        table: pl.DataFrame,
        build: _BuildTranslations,
        schema: _Schema,
        component: str,
        numbering: _Numbering,
    ) -> pl.DataFrame | None:
        """Translate one source table, and take its share of the ids. An empty table maps none."""
        if table.is_empty():
            return None
        out = finalise(
            apply_translations(table, build(numbering.next_id), self._recorder),
            schema,
            self._recorder,
            component,
        )
        state.destination_tables[component] = out
        numbering.next_id += out.height
        return out

    # --- the series ----------------------------------------------------------------------------

    def _map_series(
        self, state: State, plan_years: Mapping[int, OperationsYear], candidates: _Candidates
    ) -> None:
        demand = _read_ids(state, SiennaInvestmentsComponent.DEMAND_REQUIREMENT)
        supply = _read_ids(state, SiennaInvestmentsComponent.SUPPLY_TECHNOLOGY)
        if demand:
            series = build_demand_series(state, plan_years, sorted(demand), self._recorder)
            set_portfolio_series(state, series, demand)
        if supply:
            series = build_availability_series(
                state, plan_years, candidates.supply.table, self._recorder
            )
            set_portfolio_series(state, series, supply)

    # --- the supplemental attributes -----------------------------------------------------------

    def _map_supplemental_attributes(
        self,
        state: State,
        plan: InvestmentPlan,
        buses: pl.DataFrame,
        candidates: _Candidates,
    ) -> None:
        """The three attributes, numbered from the one counter that the flat array shares."""
        fleet = build_fleet_table(state, plan, _list_fleet_families(candidates))
        sources = {
            SiennaSupplementalAttribute.EXISTING_DEVICES: fleet,
            SiennaSupplementalAttribute.RETIREMENT_POTENTIAL: fleet,
            SiennaSupplementalAttribute.TOPOLOGY_MAPPING: build_topology_source_table(buses),
        }
        associations: list[pl.DataFrame] = []
        numbering = _Numbering()
        for kind in SUPPLEMENTAL_ATTRIBUTE_ORDER:
            attribute = _ATTRIBUTES[kind]
            source = sources[kind]
            out = self._map_table(state, source, attribute.build, attribute.schema, kind, numbering)
            if out is not None:
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

    # --- the records of extensions.json and the portfolio financial data ----------------------

    def _map_extensions(self, state: State, candidates: _Candidates) -> None:
        families = (
            (
                SiennaInvestmentsComponent.SUPPLY_TECHNOLOGY,
                candidates.supply.table,
                candidates.supply.yearly,
                SUPPLY_FIELDS,
                TECHNOLOGY_KEYS,
            ),
            (
                SiennaInvestmentsComponent.STORAGE_TECHNOLOGY,
                candidates.storage.table,
                candidates.storage.yearly,
                STORAGE_FIELDS,
                _STORAGE_KEYS,
            ),
            (
                SiennaInvestmentsComponent.AGGREGATE_TRANSPORT_TECHNOLOGY,
                candidates.transport.table,
                candidates.transport.yearly,
                TRANSPORT_FIELDS,
                TECHNOLOGY_KEYS,
            ),
        )
        for component, table, yearly, fields, keys in families:
            records = build_technology_extensions(
                component, table, yearly, fields, keys, self._recorder
            )
            append_extensions(state.destination_extensions, ExtensionKind.TECHNOLOGY, records)

    def _map_financial_data(self, state: State, plan: InvestmentPlan) -> None:
        rate = find_region_discount_rate(state, plan)
        state.destination_tables[PORTFOLIO_FINANCIAL_DATA_TABLE] = build_osemosys_financial_data(
            plan, rate
        )
        for event in build_osemosys_financial_events(plan, rate):
            self._recorder.append(event)


def _list_fleet_families(candidates: _Candidates) -> list[FleetFamily]:
    return [
        FleetFamily(
            component_type=SiennaInvestmentsComponent.SUPPLY_TECHNOLOGY,
            device_class=TECHNOLOGY,
            candidates=candidates.supply.table,
            base_types=GENERATOR_TYPES,
        ),
        FleetFamily(
            component_type=SiennaInvestmentsComponent.STORAGE_TECHNOLOGY,
            device_class=STORAGE,
            candidates=candidates.storage.table,
            base_types=(SiennaComponent.ENERGY_RESERVOIR_STORAGE,),
        ),
        FleetFamily(
            component_type=SiennaInvestmentsComponent.AGGREGATE_TRANSPORT_TECHNOLOGY,
            device_class=TECHNOLOGY,
            candidates=candidates.transport.table,
            base_types=(SiennaComponent.TWO_TERMINAL_GENERIC_HVDC_LINE,),
        ),
    ]


def _read_ids(state: State, component: str) -> dict[str, int]:
    """The id of each component of a type that the step wrote, by name."""
    table = state.destination_tables.get(component)
    if table is None:
        return {}
    return dict(table.select(SIENNA_NAME_COLUMN, SIENNA_ID_COLUMN).iter_rows())
