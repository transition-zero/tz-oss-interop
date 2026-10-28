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
    build_technology_extensions,
    set_producers_persisted,
    set_technology_extensions_persisted,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._financials import (
    build_osemosys_financial_data,
    build_osemosys_financial_events,
    report_other_region_rates,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._fleet import (
    FLEET_SOURCE,
    build_fleet_table,
    build_portfolio_technologies,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._kinds import (
    CandidateKind,
    Candidates,
    YearlyField,
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
    STORAGE_KIND,
    build_storage_candidates,
    build_storage_translations,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._supply import (
    SUPPLY_KIND,
    build_supply_candidates,
    build_supply_translations,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._technologies import (
    find_region_discount_rate,
    read_region_discount_rates,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._transport import (
    TRANSPORT_KIND,
    build_transport_candidates,
    build_transport_translations,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._yearly import (
    TECHNOLOGY_KEYS,
)

__all__ = [
    "build_availability_series",
    "build_carbon_cap_translations",
    "build_carbon_caps",
    "drop_capped_limits",
    "CANDIDATE_NAME",
    "LOADS_SOURCE",
    "build_demand_series",
    "build_technology_extensions",
    "set_producers_persisted",
    "set_technology_extensions_persisted",
    "build_osemosys_financial_data",
    "build_osemosys_financial_events",
    "report_other_region_rates",
    "FLEET_SOURCE",
    "build_fleet_table",
    "build_portfolio_technologies",
    "CandidateKind",
    "Candidates",
    "YearlyField",
    "InvestmentPlan",
    "build_plan_year",
    "find_investment_plan",
    "PortfolioSeries",
    "set_portfolio_series",
    "STORAGE_KIND",
    "build_storage_candidates",
    "build_storage_translations",
    "SUPPLY_KIND",
    "build_supply_candidates",
    "build_supply_translations",
    "find_region_discount_rate",
    "read_region_discount_rates",
    "TRANSPORT_KIND",
    "build_transport_candidates",
    "build_transport_translations",
    "TECHNOLOGY_KEYS",
]
