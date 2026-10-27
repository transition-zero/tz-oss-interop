"""OSeMOSYS to Sienna investments portfolio translations, one module per part of the portfolio.

Each module reads the canonical OSeMOSYS stage over every year in scope, and the base system
that the operations step wrote for the earliest of them.
"""

from __future__ import annotations

from interop.plugins.shared.osemosys_sienna_investments_translations._availability import (
    build_availability_series,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._carbon_caps import (
    build_carbon_cap_translations,
    build_carbon_caps,
    drop_capped_limits,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._columns import (
    CANDIDATE_NAME,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._demand import (
    LOADS_SOURCE,
    build_demand_series,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._extensions import (
    STORAGE_FIELDS,
    SUPPLY_APPLIED,
    SUPPLY_FIELDS,
    TRANSPORT_FIELDS,
    CandidateFamily,
    YearlyField,
    build_technology_extensions,
    set_producers_persisted,
    set_technology_extensions_persisted,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._financials import (
    build_osemosys_financial_data,
    build_osemosys_financial_events,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._fleet import (
    FLEET_SOURCE,
    FleetFamily,
    build_fleet_table,
    build_portfolio_technologies,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._plan import (
    InvestmentPlan,
    build_plan_year,
    find_investment_plan,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._series import (
    PortfolioSeries,
    set_portfolio_series,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._storage import (
    STORAGE_SCHEMA,
    StorageCandidates,
    build_storage_candidates,
    build_storage_technology_keys,
    build_storage_translations,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._supply import (
    SUPPLY_SCHEMA,
    SupplyCandidates,
    build_supply_candidates,
    build_supply_translations,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._technologies import (
    find_region_discount_rate,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._transport import (
    TRANSPORT_SCHEMA,
    TransportCandidates,
    build_transport_candidates,
    build_transport_translations,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._yearly import (
    TECHNOLOGY_KEYS,
)

__all__ = [
    "CANDIDATE_NAME",
    "FLEET_SOURCE",
    "LOADS_SOURCE",
    "STORAGE_FIELDS",
    "STORAGE_SCHEMA",
    "SUPPLY_APPLIED",
    "SUPPLY_FIELDS",
    "SUPPLY_SCHEMA",
    "TECHNOLOGY_KEYS",
    "TRANSPORT_FIELDS",
    "TRANSPORT_SCHEMA",
    "CandidateFamily",
    "FleetFamily",
    "InvestmentPlan",
    "PortfolioSeries",
    "StorageCandidates",
    "SupplyCandidates",
    "TransportCandidates",
    "YearlyField",
    "set_portfolio_series",
    "set_producers_persisted",
    "set_technology_extensions_persisted",
    "build_availability_series",
    "build_carbon_cap_translations",
    "build_carbon_caps",
    "drop_capped_limits",
    "build_demand_series",
    "build_fleet_table",
    "build_portfolio_technologies",
    "build_storage_technology_keys",
    "build_osemosys_financial_data",
    "build_osemosys_financial_events",
    "build_plan_year",
    "build_storage_candidates",
    "build_storage_translations",
    "build_supply_candidates",
    "build_supply_translations",
    "build_technology_extensions",
    "build_transport_candidates",
    "build_transport_translations",
    "find_investment_plan",
    "find_region_discount_rate",
]
