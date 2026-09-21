"""The PowerSystemsInvestmentsPortfolios.jl portfolio envelope, and the series beside it.

The package does not read the SiennaSchemas portfolio document. It reads its own envelope:
one flat component list under ``data``, and a ``__metadata__`` block on every component
naming the Julia module and the type to build. A technology is parametric on a PowerSystems
type, so its block also names that type.

A portfolio written here carries no time series. The package reads a component through a
generated struct with no field for a UUID, so a component gets a fresh UUID on the way in
while the association rows still name the old one, and every series is lost. The series
travel in a companion document instead, and the adapter attaches them after the read.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from interop.plugins.shared.sienna_constants import SiennaComponent

PSIP_MODULE = "PowerSystemsInvestmentsPortfolios"
"""The Julia module every portfolio component names in its ``__metadata__`` block."""

PORTFOLIO_DATA_FORMAT_VERSION = "0.1.0"
"""The only version ``Portfolio(path)`` accepts."""

PORTFOLIO_JSON_FILENAME = "portfolio.json"
BASE_SYSTEM_SUFFIX = "_base_system.json"
"""The reader derives the base system's name from the document's own, and never reads a field.

For ``portfolio.json`` it opens ``portfolio_base_system.json`` in the same directory.
"""

SERIES_JSON_SUFFIX = "_series.json"
"""The companion holding the series the envelope cannot carry."""


class PortfolioEnvelope:
    """Keys of the document ``Portfolio(path)`` reads."""

    AGGREGATION = "aggregation"
    DATA = "data"
    DATA_FORMAT_VERSION = "data_format_version"
    FINANCIAL_DATA = "financial_data"
    INTERNAL = "internal"
    INVESTMENT_SCHEDULE = "investment_schedule"
    METADATA = "metadata"

    COMPONENTS = "components"
    MASKED_COMPONENTS = "masked_components"
    SUBSYSTEMS = "subsystems"
    SUPPLEMENTAL_ATTRIBUTE_MANAGER = "supplemental_attribute_manager"
    TIME_SERIES_STORAGE_TYPE = "time_series_storage_type"
    VERSION_INFO = "version_info"

    METADATA_KEY = "__metadata__"
    MODULE = "module"
    TYPE = "type"
    PARAMETERS = "parameters"
    CONSTRUCT_WITH_PARAMETERS = "construct_with_parameters"


class PortfolioComponent(StrEnum):
    """The types the envelope's flat component list holds."""

    ZONE = "Zone"
    SUPPLY_TECHNOLOGY = "SupplyTechnology"
    STORAGE_TECHNOLOGY = "StorageTechnology"
    DEMAND_REQUIREMENT = "DemandRequirement"
    CARBON_CAPS = "CarbonCaps"


PARAMETRIC_COMPONENTS: frozenset[PortfolioComponent] = frozenset(
    {
        PortfolioComponent.SUPPLY_TECHNOLOGY,
        PortfolioComponent.STORAGE_TECHNOLOGY,
        PortfolioComponent.DEMAND_REQUIREMENT,
    }
)
"""The types the package builds as ``Type{Parameter}``, naming a PowerSystems type."""

# The order the flat list states its types in. A technology names its region by id, and the
# package resolves that id against the regions it has already built, so the zones come first.
COMPONENT_ORDER: tuple[PortfolioComponent, ...] = (
    PortfolioComponent.ZONE,
    PortfolioComponent.SUPPLY_TECHNOLOGY,
    PortfolioComponent.STORAGE_TECHNOLOGY,
    PortfolioComponent.DEMAND_REQUIREMENT,
    PortfolioComponent.CARBON_CAPS,
)

PORTFOLIO_FINANCIAL_DATA_TYPE = "PortfolioFinancialData"
PORTFOLIO_METADATA_TYPE = "PortfolioMetadata"
TECHNOLOGY_FINANCIAL_DATA_TYPE = "TechnologyFinancialData"

PORTFOLIO_AGGREGATION = SiennaComponent.AREA
"""The base system type the portfolio's regions stand for."""

TIME_SERIES_STORAGE_TYPE = "InfrastructureSystems.Hdf5TimeSeriesStorage"
"""What the document states it would store series in, even where it stores none."""


class PortfolioColumn:
    """Columns of the destination tables the sink formats, beyond the SiennaSchemas fields."""

    REGION = "region"
    POWER_SYSTEMS_TYPE = "power_systems_type"
    NAME = "name"
    ID = "id"


PORTFOLIO_SERIES_TABLE = "PortfolioSeries"
PORTFOLIO_PERIODS_TABLE = "PortfolioPeriods"
"""Destination tables holding the series the envelope drops, and the periods they fall in."""


class InvestmentsSeriesName(StrEnum):
    """The series names PowerSystemsInvestments looks a technology's profile up by.

    The package hard-codes one name per technology type, so a document that states any other
    name reaches a model that finds nothing.
    """

    VARIABLE_CAPACITY_FACTOR = "ops_variable_cap_factor"
    DEMAND = "ops_demand"


class SeriesDocument:
    """Keys of the companion document holding the series the envelope drops."""

    PERIODS = "periods"
    RECORDS = "records"

    START = "start"
    END = "end"

    COMPONENT_TYPE = "component_type"
    COMPONENT_NAME = "component_name"
    SERIES_NAME = "series_name"
    YEAR = "year"
    REPRESENTATIVE_DAY = "rep_day"
    WEIGHT = "weight"
    INITIAL_TIMESTAMP = "initial_timestamp"
    RESOLUTION_SECONDS = "resolution_seconds"
    VALUES = "values"


def build_component_metadata(
    component: PortfolioComponent, power_systems_type: str | None
) -> dict[str, Any]:
    """The ``__metadata__`` block one component carries, naming the type to build."""
    metadata: dict[str, Any] = {
        PortfolioEnvelope.MODULE: PSIP_MODULE,
        PortfolioEnvelope.TYPE: str(component),
    }
    if component in PARAMETRIC_COMPONENTS and power_systems_type is not None:
        metadata[PortfolioEnvelope.PARAMETERS] = [power_systems_type]
        metadata[PortfolioEnvelope.CONSTRUCT_WITH_PARAMETERS] = True
    return metadata
