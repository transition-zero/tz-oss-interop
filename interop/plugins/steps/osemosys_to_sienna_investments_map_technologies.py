"""Turn the canonical stage of an OSeMOSYS model into a Sienna investments portfolio.

The operations step runs first and writes the base system: the fleet of the earliest year in
scope. This step reads the canonical stage again over every year in scope, and writes what a
plan may build, the demand that it must meet, the caps that it runs under, and the attributes
that tie each technology to the fleet of the base system.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from functools import partial
from typing import ClassVar

from pydantic import BaseModel

from interop.core.extensions import ExtensionKind, append_extensions
from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.osemosys_sienna_investments_translations import (
    FLEET_SOURCE,
    LOADS_SOURCE,
    Candidates,
    InvestmentPlan,
    build_availability_series,
    build_carbon_cap_translations,
    build_carbon_caps,
    build_demand_series,
    build_fleet_table,
    build_osemosys_financial_data,
    build_osemosys_financial_events,
    build_plan_year,
    build_portfolio_technologies,
    build_storage_candidates,
    build_supply_candidates,
    build_technology_extensions,
    build_transport_candidates,
    drop_capped_limits,
    find_investment_plan,
    find_region_discount_rate,
    read_region_discount_rates,
    report_other_region_rates,
    set_portfolio_series,
    set_producers_persisted,
    set_technology_extensions_persisted,
)
from interop.plugins.shared.osemosys_sienna_translations import (
    CANDIDATE_VALUES,
    OperationsYear,
    enrich_technology_values,
)
from interop.plugins.shared.osemosys_sienna_user_mappings import OsemosysSiennaCarrierMappings
from interop.plugins.shared.pypsa_sienna_investments_translations import (
    OSEMOSYS_TO_SIENNA_INVESTMENTS,
    PortfolioMapper,
    PortfolioTable,
    build_demand_translations,
)
from interop.plugins.shared.sienna_constants import (
    SIENNA_ID_COLUMN,
    SIENNA_NAME_COLUMN,
    SiennaComponent,
)
from interop.plugins.shared.sienna_investments_constants import (
    CARBON_CAPS_DESTINATION_SCHEMA,
    DEMAND_REQUIREMENT_DESTINATION_SCHEMA,
    PORTFOLIO_FINANCIAL_DATA_TABLE,
    SiennaInvestmentsComponent,
)
from interop.plugins.shared.sienna_investments_sources import (
    build_demand_table,
    read_area_by_bus,
)


@dataclass(frozen=True)
class _Candidates:
    supply: Candidates
    storage: Candidates
    transport: Candidates

    @property
    def families(self) -> tuple[Candidates, ...]:
        """The candidates of each kind, in the order in which they take their ids."""
        return (self.supply, self.storage, self.transport)


_DEMAND_TABLE = PortfolioTable(
    SiennaInvestmentsComponent.DEMAND_REQUIREMENT,
    DEMAND_REQUIREMENT_DESTINATION_SCHEMA,
    partial(build_demand_translations, LOADS_SOURCE),
)
_CARBON_CAPS_TABLE = PortfolioTable(
    SiennaInvestmentsComponent.CARBON_CAPS,
    CARBON_CAPS_DESTINATION_SCHEMA,
    build_carbon_cap_translations,
)

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
        mapper = PortfolioMapper(self._recorder, FLEET_SOURCE)
        candidates = self._map_candidates(state, plan, plan_years, mapper)
        self._map_demand(state, mapper)
        self._map_carbon_caps(state, plan, mapper, candidates)
        self._map_series(state, plan_years, candidates)
        fleet = build_fleet_table(state, plan, candidates.families)
        mapper.map_supplemental_attributes(state, fleet, buses)
        self._map_extensions(state, plan_years[plan.base_year], candidates)
        self._map_financial_data(state, plan)
        return state

    # --- the components ----------------------------------------------------------------------

    def _map_candidates(
        self,
        state: State,
        plan: InvestmentPlan,
        plan_years: Mapping[int, OperationsYear],
        mapper: PortfolioMapper,
    ) -> _Candidates:
        candidates = _Candidates(
            supply=build_supply_candidates(state, plan_years, plan, self._mappings, self._recorder),
            storage=build_storage_candidates(
                state, plan_years, plan, self._mappings, self._recorder
            ),
            transport=build_transport_candidates(state, plan, self._recorder),
        )
        for family in candidates.families:
            mapper.map_table(state, family.table, family.kind.build_table(plan.cost_year))
        return candidates

    def _map_demand(self, state: State, mapper: PortfolioMapper) -> None:
        """One requirement for each load that the base system holds."""
        table = build_demand_table(state, read_area_by_bus(state))
        mapper.map_table(state, table, _DEMAND_TABLE)

    def _map_carbon_caps(
        self, state: State, plan: InvestmentPlan, mapper: PortfolioMapper, candidates: _Candidates
    ) -> None:
        """The caps, and the constraint records that the operations step wrote without them."""
        portfolio = build_portfolio_technologies(state, candidates.families)
        caps = build_carbon_caps(state, plan, portfolio, self._recorder)
        constraints = state.destination_extensions.get(ExtensionKind.CONSTRAINT, [])
        capped = drop_capped_limits(constraints, caps.pollutants)
        state.destination_extensions[ExtensionKind.CONSTRAINT] = capped.records
        for event in capped.events:
            self._recorder.append(event)
        mapper.map_table(state, caps.table, _CARBON_CAPS_TABLE)

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

    # --- the records of extensions.json and the portfolio financial data ----------------------

    def _map_extensions(self, state: State, base: OperationsYear, candidates: _Candidates) -> None:
        for family in candidates.families:
            valued = enrich_technology_values(state, base, family.table, CANDIDATE_VALUES)
            records = build_technology_extensions(family, valued, self._recorder)
            append_extensions(state.destination_extensions, ExtensionKind.TECHNOLOGY, records)
        set_producers_persisted(state, candidates.supply.yearly)
        set_technology_extensions_persisted(state, candidates.families)

    def _map_financial_data(self, state: State, plan: InvestmentPlan) -> None:
        rates = read_region_discount_rates(state, plan)
        rate = find_region_discount_rate(rates)
        state.destination_tables[PORTFOLIO_FINANCIAL_DATA_TABLE] = build_osemosys_financial_data(
            plan, rate
        )
        for event in build_osemosys_financial_events(plan, rate):
            self._recorder.append(event)
        report_other_region_rates(rates, rate, self._recorder)


def _read_ids(state: State, component: str) -> dict[str, int]:
    """The id of each component of a type that the step wrote, by name."""
    table = state.destination_tables.get(component)
    if table is None:
        return {}
    return dict(table.select(SIENNA_NAME_COLUMN, SIENNA_ID_COLUMN).iter_rows())
