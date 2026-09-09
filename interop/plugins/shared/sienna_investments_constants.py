"""Sienna investments vocabulary: the types a portfolio document is made of.

Every name and every required/optional status here comes from the ``Investments/`` namespace
of SiennaSchemas. A portfolio is a separate document from a system: it holds the candidate
technologies, the policy requirements and the regional aggregations of an expansion problem,
and it names the base power system it expands rather than embedding it.
"""

from __future__ import annotations

from enum import StrEnum

import polars as pl

from interop.plugins.shared.sienna_constants import (
    COST_CURVE_DTYPE,
    COST_TYPE_DTYPE,
    IO_CURVE_DTYPE,
    MIN_MAX_DTYPE,
    PRIME_MOVERS_DTYPE,
    SiennaStructField,
)


class SiennaInvestmentsComponent(StrEnum):
    """The investments types this translation writes into ``PortfolioDocument.components``."""

    SUPPLY_TECHNOLOGY = "SupplyTechnology"
    STORAGE_TECHNOLOGY = "StorageTechnology"
    DEMAND_REQUIREMENT = "DemandRequirement"
    CARBON_CAPS = "CarbonCaps"


class SiennaSupplementalAttribute(StrEnum):
    """The supplemental attribute types a portfolio carries in its flat array.

    Each one holds names of things in the base system, so it describes a component rather
    than standing beside it: the association table says which component each describes.
    """

    EXISTING_DEVICES = "ExistingDevices"
    RETIREMENT_POTENTIAL = "RetirementPotential"
    TOPOLOGY_MAPPING = "TopologyMapping"


class PortfolioDocument:
    """Top-level keys of a SiennaSchemas ``PortfolioDocument``."""

    NAME = "name"
    DESCRIPTION = "description"
    DATA_SOURCE = "data_source"
    AGGREGATION = "aggregation"
    FINANCIAL_DATA = "financial_data"
    COMPONENTS = "components"
    SUPPLEMENTAL_ATTRIBUTES = "supplemental_attributes"
    SUPPLEMENTAL_ATTRIBUTE_ASSOCIATIONS = "supplemental_attribute_associations"
    INVESTMENT_SCHEDULE = "investment_schedule"
    TIME_SERIES_ASSOCIATIONS = "time_series_associations"
    EXT = "ext"
    BASE_SYSTEM_FILE = "base_system_file"
    TIME_SERIES_STORAGE_FILE = "time_series_storage_file"


PORTFOLIO_JSON_FILENAME = "portfolio.json"
"""Default basename of the portfolio document written beside the base system."""

PORTFOLIO_AGGREGATION = "Area"
"""The base system type a portfolio's regions are grouped by.

``PortfolioDocument.aggregation`` names a type the consumer resolves rather than a component
of the document, and the regions a PyPSA network states are the areas of the base system.
"""


class SiennaSupplyTechnologyCol:
    """SiennaSchemas ``SupplyTechnology`` field names.

    ``region_name`` is not a schema field: it holds the area name until the sink resolves it
    to the ``region`` list of integer ids, the way a load carries ``bus_name``.
    """

    ID = "id"
    NAME = "name"
    AVAILABLE = "available"
    POWER_SYSTEMS_TYPE = "power_systems_type"
    REGION = "region"
    REGION_NAME = "region_name"
    PRIME_MOVER_TYPE = "prime_mover_type"
    FUEL = "fuel"
    COFIRE_START_LIMITS = "cofire_start_limits"
    COFIRE_LEVEL_LIMITS = "cofire_level_limits"
    CAPITAL_COSTS = "capital_costs"
    OPERATION_COSTS = "operation_costs"
    UNIT_SIZE = "unit_size"
    CAPACITY_LIMITS = "capacity_limits"
    OUTAGE_FACTOR = "outage_factor"
    MIN_GENERATION_FRACTION = "min_generation_fraction"
    RAMP_LIMITS = "ramp_limits"
    TIME_LIMITS = "time_limits"
    START_FUEL_MMBTU_PER_MW = "start_fuel_mmbtu_per_mw"
    LIFETIME = "lifetime"
    REQUIREMENTS = "requirements"
    FINANCIAL_DATA = "financial_data"


class SiennaStorageTechnologyCol:
    """SiennaSchemas ``StorageTechnology`` field names.

    Charge, discharge and energy capacity are added independently, so each has its own
    capital cost, unit size and capacity limits.
    """

    ID = "id"
    NAME = "name"
    AVAILABLE = "available"
    REGION = "region"
    REGION_NAME = "region_name"
    POWER_SYSTEMS_TYPE = "power_systems_type"
    MIN_DISCHARGE_FRACTION = "min_discharge_fraction"
    PRIME_MOVER_TYPE = "prime_mover_type"
    STORAGE_TECH = "storage_tech"
    CAPITAL_COSTS = "capital_costs"
    OPERATION_COSTS = "operation_costs"
    UNIT_SIZE_DISCHARGE = "unit_size_discharge"
    UNIT_SIZE_CHARGE = "unit_size_charge"
    UNIT_SIZE_ENERGY = "unit_size_energy"
    CAPACITY_LIMITS_CHARGE = "capacity_limits_charge"
    CAPACITY_LIMITS_DISCHARGE = "capacity_limits_discharge"
    CAPACITY_LIMITS_ENERGY = "capacity_limits_energy"
    DURATION_LIMITS = "duration_limits"
    EFFICIENCY = "efficiency"
    LOSSES = "losses"
    LIFETIME = "lifetime"
    REQUIREMENTS = "requirements"
    FINANCIAL_DATA = "financial_data"


class SiennaDemandRequirementCol:
    """SiennaSchemas ``DemandRequirement`` field names."""

    ID = "id"
    NAME = "name"
    AVAILABLE = "available"
    POWER_SYSTEMS_TYPE = "power_systems_type"
    CONFORMITY = "conformity"
    GROWTH_RATE = "growth_rate"
    NEW_DEMAND_MW = "new_demand_mw"
    NEW_CONSTRUCTION_YEAR = "new_construction_year"
    REGION = "region"
    REGION_NAME = "region_name"
    VALUE_OF_LOST_LOAD = "value_of_lost_load"
    UNSERVED_DEMAND_CURVE = "unserved_demand_curve"
    REQUIREMENTS = "requirements"


class SiennaCarbonCapsCol:
    """SiennaSchemas ``CarbonCaps`` field names.

    The type names no members and no region: a cap holds the whole portfolio.
    """

    ID = "id"
    NAME = "name"
    AVAILABLE = "available"
    TARGET_YEAR = "target_year"
    MAX_TONS_MWH = "max_tons_mwh"
    MAX_MTONS = "max_mtons"


class SiennaExistingDevicesCol:
    """SiennaSchemas ``ExistingDevices`` field names."""

    ID = "id"
    EXISTING_DEVICES = "existing_devices"


class SiennaRetirementPotentialCol:
    """SiennaSchemas ``RetirementPotential`` field names.

    ``build_year`` and ``planned_retirement_year`` are objects keyed by device name. A
    Polars struct has fixed field names, so both travel as a list of name/year pairs and the
    sink writes each list out as the object the schema states.
    """

    ID = "id"
    ELIGIBLE_GENERATORS = "eligible_generators"
    PLANNED_RETIREMENT_YEAR = "planned_retirement_year"
    BUILD_YEAR = "build_year"
    RETIREMENT_COST = "retirement_cost"


class NamedYearField:
    """Field names of one entry in a name-keyed year object."""

    NAME = "name"
    YEAR = "year"


class SiennaTopologyMappingCol:
    """SiennaSchemas ``TopologyMapping`` field names."""

    ID = "id"
    BUSES = "buses"


class SiennaPortfolioFinancialDataCol:
    """SiennaSchemas ``PortfolioFinancialData`` field names."""

    ID = "id"
    DISCOUNT_RATE = "discount_rate"
    INFLATION_RATE = "inflation_rate"
    INTEREST_RATE = "interest_rate"
    BASE_YEAR = "base_year"


class SiennaTechnologyFinancialDataField:
    """SiennaSchemas ``TechnologyFinancialData`` field names. All six are required."""

    CAPITAL_RECOVERY_PERIOD = "capital_recovery_period"
    TECHNOLOGY_BASE_YEAR = "technology_base_year"
    DEBT_FRACTION = "debt_fraction"
    DEBT_RATE = "debt_rate"
    RETURN_ON_EQUITY = "return_on_equity"
    TAX_RATE = "tax_rate"


class SiennaCapitalCostField:
    """Field names of the Sienna ``CapitalCost`` struct."""

    CAPITAL_COST = "capital_cost"
    INTERCONNECTION_COST = "interconnection_cost"


class SiennaStorageCapitalCostField:
    """Field names of the Sienna ``StorageCapitalCost`` struct."""

    CHARGE_CAPITAL_COST = "charge_capital_cost"
    DISCHARGE_CAPITAL_COST = "discharge_capital_cost"
    ENERGY_CAPITAL_COST = "energy_capital_cost"
    INTERCONNECTION_COST = "interconnection_cost"


class SiennaOutageFactorsField:
    """Field names of the Sienna ``OutageFactors`` struct.

    ``min`` is the forced outage factor and ``max`` the planned one, which is why the pair
    is its own type rather than a ``MinMax``.
    """

    FORCED = "min"
    PLANNED = "max"


class SiennaOperationCostField:
    """Field names of the Sienna ``GenericOperationCost`` variants this translation writes."""

    COST_TYPE = "cost_type"
    FIXED = "fixed"
    START_UP = "start_up"
    SHUT_DOWN = "shut_down"
    VARIABLE_OPERATION_COST = "variable_operation_cost"


class SiennaSupplementalAttributeAssociationCol:
    """SiennaSchemas ``SupplementalAttributeAssociation`` field names.

    ``component_name`` is not a schema field: it holds the described component's name until
    the sink resolves it to ``component_id``.
    """

    COMPONENT_ID = "component_id"
    COMPONENT_NAME = "component_name"
    COMPONENT_TYPE = "component_type"
    ATTRIBUTE_ID = "attribute_id"
    ATTRIBUTE_TYPE = "attribute_type"


# --- Nested struct dtypes ---

IN_OUT_DTYPE: pl.DataType = pl.Struct(
    {SiennaStructField.IN: pl.Float64, SiennaStructField.OUT: pl.Float64}
)

OUTAGE_FACTORS_DTYPE: pl.DataType = pl.Struct(
    {SiennaOutageFactorsField.FORCED: pl.Float64, SiennaOutageFactorsField.PLANNED: pl.Float64}
)

CAPITAL_COST_DTYPE: pl.DataType = pl.Struct(
    {
        SiennaCapitalCostField.CAPITAL_COST: IO_CURVE_DTYPE,
        SiennaCapitalCostField.INTERCONNECTION_COST: pl.Float64,
    }
)

STORAGE_CAPITAL_COST_DTYPE: pl.DataType = pl.Struct(
    {
        SiennaStorageCapitalCostField.CHARGE_CAPITAL_COST: IO_CURVE_DTYPE,
        SiennaStorageCapitalCostField.DISCHARGE_CAPITAL_COST: IO_CURVE_DTYPE,
        SiennaStorageCapitalCostField.ENERGY_CAPITAL_COST: IO_CURVE_DTYPE,
        SiennaStorageCapitalCostField.INTERCONNECTION_COST: pl.Float64,
    }
)

GENERIC_OPERATION_COST_DTYPE: pl.DataType = pl.Struct(
    {
        SiennaOperationCostField.COST_TYPE: COST_TYPE_DTYPE,
        SiennaOperationCostField.FIXED: pl.Float64,
        SiennaOperationCostField.START_UP: pl.Float64,
        SiennaOperationCostField.SHUT_DOWN: pl.Float64,
        SiennaOperationCostField.VARIABLE_OPERATION_COST: COST_CURVE_DTYPE,
    }
)

STORAGE_OPERATION_COST_DTYPE: pl.DataType = pl.Struct(
    {
        SiennaOperationCostField.COST_TYPE: COST_TYPE_DTYPE,
        SiennaOperationCostField.FIXED: pl.Float64,
        SiennaOperationCostField.START_UP: pl.Float64,
        SiennaOperationCostField.SHUT_DOWN: pl.Float64,
    }
)

TECHNOLOGY_FINANCIAL_DATA_DTYPE: pl.DataType = pl.Struct(
    {
        SiennaTechnologyFinancialDataField.CAPITAL_RECOVERY_PERIOD: pl.Int64,
        SiennaTechnologyFinancialDataField.TECHNOLOGY_BASE_YEAR: pl.Int64,
        SiennaTechnologyFinancialDataField.DEBT_FRACTION: pl.Float64,
        SiennaTechnologyFinancialDataField.DEBT_RATE: pl.Float64,
        SiennaTechnologyFinancialDataField.RETURN_ON_EQUITY: pl.Float64,
        SiennaTechnologyFinancialDataField.TAX_RATE: pl.Float64,
    }
)

NAMED_YEAR_DTYPE: pl.DataType = pl.List(
    pl.Struct({NamedYearField.NAME: pl.Utf8, NamedYearField.YEAR: pl.Int64})
)

CAPACITY_LIMITS_DTYPE: pl.DataType = MIN_MAX_DTYPE


# --- Destination table schemas ---

SUPPLY_TECHNOLOGY_DESTINATION_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    SiennaSupplyTechnologyCol.ID: pl.Int64,
    SiennaSupplyTechnologyCol.NAME: pl.Utf8,
    SiennaSupplyTechnologyCol.AVAILABLE: pl.Boolean,
    SiennaSupplyTechnologyCol.POWER_SYSTEMS_TYPE: pl.Utf8,
    SiennaSupplyTechnologyCol.REGION_NAME: pl.Utf8,
    SiennaSupplyTechnologyCol.PRIME_MOVER_TYPE: PRIME_MOVERS_DTYPE,
    SiennaSupplyTechnologyCol.FUEL: pl.List(pl.Utf8),
    SiennaSupplyTechnologyCol.COFIRE_START_LIMITS: pl.Utf8,
    SiennaSupplyTechnologyCol.COFIRE_LEVEL_LIMITS: pl.Utf8,
    SiennaSupplyTechnologyCol.CAPITAL_COSTS: CAPITAL_COST_DTYPE,
    SiennaSupplyTechnologyCol.OPERATION_COSTS: GENERIC_OPERATION_COST_DTYPE,
    SiennaSupplyTechnologyCol.UNIT_SIZE: pl.Float64,
    SiennaSupplyTechnologyCol.CAPACITY_LIMITS: CAPACITY_LIMITS_DTYPE,
    SiennaSupplyTechnologyCol.OUTAGE_FACTOR: OUTAGE_FACTORS_DTYPE,
    SiennaSupplyTechnologyCol.MIN_GENERATION_FRACTION: pl.Float64,
    SiennaSupplyTechnologyCol.RAMP_LIMITS: pl.Utf8,
    SiennaSupplyTechnologyCol.TIME_LIMITS: pl.Utf8,
    SiennaSupplyTechnologyCol.START_FUEL_MMBTU_PER_MW: pl.Float64,
    SiennaSupplyTechnologyCol.LIFETIME: pl.Int64,
    SiennaSupplyTechnologyCol.REQUIREMENTS: pl.List(pl.Int64),
    SiennaSupplyTechnologyCol.FINANCIAL_DATA: TECHNOLOGY_FINANCIAL_DATA_DTYPE,
}

STORAGE_TECHNOLOGY_DESTINATION_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    SiennaStorageTechnologyCol.ID: pl.Int64,
    SiennaStorageTechnologyCol.NAME: pl.Utf8,
    SiennaStorageTechnologyCol.AVAILABLE: pl.Boolean,
    SiennaStorageTechnologyCol.REGION_NAME: pl.Utf8,
    SiennaStorageTechnologyCol.POWER_SYSTEMS_TYPE: pl.Utf8,
    SiennaStorageTechnologyCol.MIN_DISCHARGE_FRACTION: pl.Float64,
    SiennaStorageTechnologyCol.PRIME_MOVER_TYPE: PRIME_MOVERS_DTYPE,
    SiennaStorageTechnologyCol.STORAGE_TECH: pl.Utf8,
    SiennaStorageTechnologyCol.CAPITAL_COSTS: STORAGE_CAPITAL_COST_DTYPE,
    SiennaStorageTechnologyCol.OPERATION_COSTS: STORAGE_OPERATION_COST_DTYPE,
    SiennaStorageTechnologyCol.UNIT_SIZE_DISCHARGE: pl.Float64,
    SiennaStorageTechnologyCol.UNIT_SIZE_CHARGE: pl.Float64,
    SiennaStorageTechnologyCol.UNIT_SIZE_ENERGY: pl.Float64,
    SiennaStorageTechnologyCol.CAPACITY_LIMITS_CHARGE: CAPACITY_LIMITS_DTYPE,
    SiennaStorageTechnologyCol.CAPACITY_LIMITS_DISCHARGE: CAPACITY_LIMITS_DTYPE,
    SiennaStorageTechnologyCol.CAPACITY_LIMITS_ENERGY: CAPACITY_LIMITS_DTYPE,
    SiennaStorageTechnologyCol.DURATION_LIMITS: CAPACITY_LIMITS_DTYPE,
    SiennaStorageTechnologyCol.EFFICIENCY: IN_OUT_DTYPE,
    SiennaStorageTechnologyCol.LOSSES: pl.Float64,
    SiennaStorageTechnologyCol.LIFETIME: pl.Int64,
    SiennaStorageTechnologyCol.REQUIREMENTS: pl.List(pl.Int64),
    SiennaStorageTechnologyCol.FINANCIAL_DATA: TECHNOLOGY_FINANCIAL_DATA_DTYPE,
}

DEMAND_REQUIREMENT_DESTINATION_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    SiennaDemandRequirementCol.ID: pl.Int64,
    SiennaDemandRequirementCol.NAME: pl.Utf8,
    SiennaDemandRequirementCol.AVAILABLE: pl.Boolean,
    SiennaDemandRequirementCol.POWER_SYSTEMS_TYPE: pl.Utf8,
    SiennaDemandRequirementCol.REGION_NAME: pl.Utf8,
    SiennaDemandRequirementCol.CONFORMITY: pl.Utf8,
    SiennaDemandRequirementCol.GROWTH_RATE: pl.Float64,
    SiennaDemandRequirementCol.NEW_DEMAND_MW: pl.Float64,
    SiennaDemandRequirementCol.NEW_CONSTRUCTION_YEAR: pl.Int64,
    SiennaDemandRequirementCol.VALUE_OF_LOST_LOAD: pl.Float64,
    SiennaDemandRequirementCol.UNSERVED_DEMAND_CURVE: IO_CURVE_DTYPE,
    SiennaDemandRequirementCol.REQUIREMENTS: pl.List(pl.Int64),
}

CARBON_CAPS_DESTINATION_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    SiennaCarbonCapsCol.ID: pl.Int64,
    SiennaCarbonCapsCol.NAME: pl.Utf8,
    SiennaCarbonCapsCol.AVAILABLE: pl.Boolean,
    SiennaCarbonCapsCol.TARGET_YEAR: pl.Int64,
    SiennaCarbonCapsCol.MAX_TONS_MWH: pl.Float64,
    SiennaCarbonCapsCol.MAX_MTONS: pl.Float64,
}

EXISTING_DEVICES_DESTINATION_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    SiennaExistingDevicesCol.ID: pl.Int64,
    SiennaExistingDevicesCol.EXISTING_DEVICES: pl.List(pl.Utf8),
}

RETIREMENT_POTENTIAL_DESTINATION_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    SiennaRetirementPotentialCol.ID: pl.Int64,
    SiennaRetirementPotentialCol.ELIGIBLE_GENERATORS: pl.List(pl.Utf8),
    SiennaRetirementPotentialCol.PLANNED_RETIREMENT_YEAR: NAMED_YEAR_DTYPE,
    SiennaRetirementPotentialCol.BUILD_YEAR: NAMED_YEAR_DTYPE,
    SiennaRetirementPotentialCol.RETIREMENT_COST: IO_CURVE_DTYPE,
}

TOPOLOGY_MAPPING_DESTINATION_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    SiennaTopologyMappingCol.ID: pl.Int64,
    SiennaTopologyMappingCol.BUSES: pl.List(pl.Utf8),
}

PORTFOLIO_FINANCIAL_DATA_DESTINATION_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    SiennaPortfolioFinancialDataCol.ID: pl.Int64,
    SiennaPortfolioFinancialDataCol.DISCOUNT_RATE: pl.Float64,
    SiennaPortfolioFinancialDataCol.INFLATION_RATE: pl.Float64,
    SiennaPortfolioFinancialDataCol.INTEREST_RATE: pl.Float64,
    SiennaPortfolioFinancialDataCol.BASE_YEAR: pl.Int64,
}

SUPPLEMENTAL_ATTRIBUTE_ASSOCIATION_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    SiennaSupplementalAttributeAssociationCol.COMPONENT_NAME: pl.Utf8,
    SiennaSupplementalAttributeAssociationCol.COMPONENT_TYPE: pl.Utf8,
    SiennaSupplementalAttributeAssociationCol.ATTRIBUTE_ID: pl.Int64,
    SiennaSupplementalAttributeAssociationCol.ATTRIBUTE_TYPE: pl.Utf8,
}

# The order the flat supplemental attribute array lists its types in. One id counter runs
# across all three, because an id identifies an attribute within that array rather than
# within its own type, so the step numbering them and the sink writing them share this.
SUPPLEMENTAL_ATTRIBUTE_ORDER: tuple[SiennaSupplementalAttribute, ...] = (
    SiennaSupplementalAttribute.EXISTING_DEVICES,
    SiennaSupplementalAttribute.RETIREMENT_POTENTIAL,
    SiennaSupplementalAttribute.TOPOLOGY_MAPPING,
)

# Keys for the destination tables that are not components of the document: the association
# rows and the portfolio-wide financial data.
SUPPLEMENTAL_ATTRIBUTE_ASSOCIATIONS_TABLE = "supplemental_attribute_associations"
PORTFOLIO_FINANCIAL_DATA_TABLE = "PortfolioFinancialData"

# A cost of capital PyPSA states as one discount rate, written as all-equity financing.
# TechnologyFinancialData requires all six of its fields and has none for a weighted average
# cost of capital; with no debt that average equals the return on equity, so the rate the
# source states is the rate the solver uses.
ALL_EQUITY_DEBT_FRACTION: float = 0.0
ALL_EQUITY_DEBT_RATE: float = 0.0
ALL_EQUITY_TAX_RATE: float = 0.0

# The base economic year every cost is discounted to, where no source states one. It matches
# the year SiennaSchemas itself defaults a construction year to.
DEFAULT_BASE_YEAR: int = 2020

# A portfolio this translation writes carries no rate of its own beside the per-technology
# return on equity, so the document-level rates take the schema's own defaults.
DEFAULT_PORTFOLIO_RATE: float = 0.0
