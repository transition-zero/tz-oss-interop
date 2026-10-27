"""The output of a PowerSystemsInvestments.jl solve, and the staging keys that read it.

The expansion adapter writes one long CSV for each variable and each stored expression, under
``results_wide/variables`` and ``results_wide/expressions``. A file is named
``<result>__<technology>__<parameter>__<formulation>.csv``. An investment result has one row for
each investment period, keyed by ``time_index``; an operations result has one row for each hour
of a representative day, keyed by ``DateTime``.
"""

from __future__ import annotations

from enum import StrEnum
from typing import NamedTuple

from interop.plugins.shared.power_systems_investments_schema import (
    MODELLED_TECHNOLOGIES,
    PortfolioComponent,
)
from interop.ports.outbound.expansion import (
    INVESTMENT_FORMULATIONS as INVESTMENT_FORMULATION_NAMES,
)
from interop.ports.outbound.expansion import ExpansionResultsLayout


class InvestmentsResult(StrEnum):
    """The results that the results step reads, by their PowerSystemsInvestments names."""

    BUILD_CAPACITY = "BuildCapacity"
    BUILD_POWER_CAPACITY = "BuildPowerCapacity"
    CUMULATIVE_CAPACITY = "CumulativeCapacity"
    CUMULATIVE_POWER_CAPACITY = "CumulativePowerCapacity"
    ACTIVE_POWER = "ActivePowerVariable"
    ACTIVE_OUT_POWER = "ActiveOutPowerVariable"
    FLOW_ACTIVE_POWER = "FlowActivePowerVariable"


class ResultsCsvCol:
    """The columns of a result CSV."""

    TIME_INDEX = "time_index"
    DATE_TIME = "DateTime"
    NAME = "name"
    VALUE = "value"


class StagedResultCol:
    """The columns of a staged result table."""

    RESULT = "result"
    TECHNOLOGY = "technology"
    FORMULATION = "formulation"
    COMPONENT = "component"
    PERIOD = "period"
    SNAPSHOT = "snapshot"
    VALUE = "value"
    YEAR = "year"
    REPRESENTATIVE_DAY = "rep_day"
    WEIGHT = "weight"
    HOURS = "hours"
    UNIT_SIZE = "unit_size"


_LAYOUT = ExpansionResultsLayout
VARIABLES_FOLDER = f"{_LAYOUT.WIDE_DIR}/{_LAYOUT.VARIABLES_DIR}"
EXPRESSIONS_FOLDER = f"{_LAYOUT.WIDE_DIR}/{_LAYOUT.EXPRESSIONS_DIR}"
OPTIMIZER_STATS_CSV = f"{_LAYOUT.STATISTICS_DIR}/{_LAYOUT.OPTIMIZER_STATS_FILE}"
OBJECTIVE_VALUE_COLUMN = "objective_value"

# The character between the parts of a file name.
_FILE_NAME_SEPARATOR = "__"


def _list_file_technologies(component: PortfolioComponent) -> tuple[str, ...]:
    """The technology part of a file name: the technology type and its PowerSystems parameter."""
    return tuple(
        f"{modelled.component}{_FILE_NAME_SEPARATOR}{modelled.parameter}"
        for modelled in MODELLED_TECHNOLOGIES
        if modelled.component is component
    )


SUPPLY_TECHNOLOGIES = _list_file_technologies(PortfolioComponent.SUPPLY_TECHNOLOGY)
STORAGE_TECHNOLOGIES = _list_file_technologies(PortfolioComponent.STORAGE_TECHNOLOGY)
TRANSPORT_TECHNOLOGIES = _list_file_technologies(PortfolioComponent.AGGREGATE_TRANSPORT_TECHNOLOGY)

INVESTMENT_FORMULATIONS = tuple(INVESTMENT_FORMULATION_NAMES.values())
OPERATIONS_FORMULATIONS = tuple(
    dict.fromkeys(modelled.operations for modelled in MODELLED_TECHNOLOGIES)
)


class ResultCsvs(NamedTuple):
    """One result, the folder that holds it, and the technologies and formulations it has."""

    result: InvestmentsResult
    folder: str
    technologies: tuple[str, ...]
    formulations: tuple[str, ...]

    def list_paths(self) -> list[tuple[str, str]]:
        """Each technology, and the path of each file that may hold its rows."""
        return [
            (
                technology,
                f"{self.folder}/{self.result}{_FILE_NAME_SEPARATOR}{technology}"
                f"{_FILE_NAME_SEPARATOR}{formulation}{_LAYOUT.CSV_SUFFIX}",
            )
            for technology in self.technologies
            for formulation in self.formulations
        ]


INVESTMENT_RESULT_CSVS: tuple[ResultCsvs, ...] = (
    ResultCsvs(
        InvestmentsResult.BUILD_CAPACITY,
        VARIABLES_FOLDER,
        SUPPLY_TECHNOLOGIES + TRANSPORT_TECHNOLOGIES,
        INVESTMENT_FORMULATIONS,
    ),
    ResultCsvs(
        InvestmentsResult.BUILD_POWER_CAPACITY,
        VARIABLES_FOLDER,
        STORAGE_TECHNOLOGIES,
        INVESTMENT_FORMULATIONS,
    ),
    ResultCsvs(
        InvestmentsResult.CUMULATIVE_CAPACITY,
        EXPRESSIONS_FOLDER,
        SUPPLY_TECHNOLOGIES + TRANSPORT_TECHNOLOGIES,
        INVESTMENT_FORMULATIONS,
    ),
    ResultCsvs(
        InvestmentsResult.CUMULATIVE_POWER_CAPACITY,
        EXPRESSIONS_FOLDER,
        STORAGE_TECHNOLOGIES,
        INVESTMENT_FORMULATIONS,
    ),
)

OPERATIONS_RESULT_CSVS: tuple[ResultCsvs, ...] = (
    ResultCsvs(
        InvestmentsResult.ACTIVE_POWER,
        VARIABLES_FOLDER,
        SUPPLY_TECHNOLOGIES,
        OPERATIONS_FORMULATIONS,
    ),
    ResultCsvs(
        InvestmentsResult.ACTIVE_OUT_POWER,
        VARIABLES_FOLDER,
        STORAGE_TECHNOLOGIES,
        OPERATIONS_FORMULATIONS,
    ),
    ResultCsvs(
        InvestmentsResult.FLOW_ACTIVE_POWER,
        VARIABLES_FOLDER,
        TRANSPORT_TECHNOLOGIES,
        OPERATIONS_FORMULATIONS,
    ),
)

INVESTMENT_RESULTS_KEY = "investment_results"
"""``State.source_topology`` key of the results with one row for each investment period."""

OPERATIONS_RESULTS_KEY = ("power-systems-investments", "operations")
"""``State.source_time_series`` key of the results with one row for each hour."""

PERIOD_YEARS_KEY = "period_years"
"""``State.source_topology`` key of the year of each investment period."""

HOUR_WEIGHTS_KEY = "hour_weights"
"""``State.source_topology`` key of each hour of each slice, its year, its weight and its length."""

UNIT_SIZES_KEY = "unit_sizes"
"""``State.source_topology`` key of the MW of one unit of each technology of an integer solve."""

OBJECTIVE_KEY = "objective"
"""``State.source_topology`` key of the one-row objective table."""
