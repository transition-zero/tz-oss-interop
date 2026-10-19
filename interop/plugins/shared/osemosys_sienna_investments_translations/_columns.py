"""The columns of the candidate source tables, in OSeMOSYS words, before any Sienna column."""

from __future__ import annotations

CANDIDATE_NAME = "candidate_name"
REPORT_NAME = "report_name"
AREA = "area"
RATING_RATIO = "rating_ratio"

# The values of the year of the base system, in the unit of the model.
CAPITAL_COST = "capital_cost"
FIXED_COST = "fixed_cost"
UNIT_SIZE = "unit_size"
LIFETIME = "lifetime"
DISCOUNT_RATE = "discount_rate"
# The parameter that gave the life and the rate, and the member that states it.
LIFETIME_PARAMETER = "lifetime_parameter"
LIFETIME_MEMBER = "lifetime_member"
RATE_PARAMETER = "rate_parameter"
RATE_MEMBER = "rate_member"

# The same values, in Sienna units.
CAPITAL_COST_MW = "capital_cost_mw"
FIXED_COST_MW_YEAR = "fixed_cost_mw_year"
UNIT_SIZE_MW = "unit_size_mw"
VARIABLE_COST_MWH = "variable_cost_mwh"
EMISSION_COST_MWH = "emission_cost_mwh"
# The variable cost without the emission penalty: the own cost and the fuel cost.
OWN_AND_FUEL_COST_MWH = "own_and_fuel_cost_mwh"
ENERGY_CAPITAL_COST_MWH = "energy_capital_cost_mwh"

# Whether a plan can add capacity to the technology in the year of the row.
IS_BUILDABLE = "is_buildable"
# The year whose capital cost a candidate states, and the same for the energy of a storage.
CAPITAL_COST_YEAR = "capital_cost_year"
ENERGY_COST_YEAR = "energy_cost_year"

# The total capacity bounds of each year, as `MinMaxByKey` entries.
CAPACITY_LIMITS_BY_YEAR = "capacity_limits_by_year"

# The columns of the yearly table, one row for each technology and year, in Sienna units.
RESIDUAL_CAPACITY_MW = "residual_capacity_mw"
CAPACITY_LIMITS_MIN_MW = "capacity_limits_min_mw"
CAPACITY_LIMITS_MAX_MW = "capacity_limits_max_mw"
MAX_CAPACITY_INVESTMENT_MW = "max_capacity_investment_mw"
MIN_GROWTH_MW = "min_growth_mw"
MAX_GROWTH_RATE = "max_growth_rate"
MIN_GROWTH_RATE = "min_growth_rate"
MAX_GROWTH_FLOOR_MW = "max_growth_floor_mw"
E_SUM_MIN_MWH = "e_sum_min_mwh"
E_SUM_MAX_MWH = "e_sum_max_mwh"
