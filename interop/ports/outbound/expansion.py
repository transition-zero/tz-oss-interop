"""What the core needs to run a capacity expansion, and the two answers a user gives it.

Separate from ``SolverPort``, which dispatches a fixed fleet over a system. An expansion
decides what to build as well as how to run it, so it reads a portfolio rather than a system
and takes a different pair of answers.

The portfolio carries no time series, so a series document travels beside it. This module
states that document, which the sink writes and the adapter reads, and the files the adapter
writes its decisions to.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import ClassVar, NamedTuple, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from interop.ports.outbound.solver import HiGHSOptions


class BalanceModel(StrEnum):
    """How much of the network the expansion respects.

    The expansion path's answer to the dispatch path's network model question.
    """

    SINGLE_REGION = "single-region"
    MULTI_REGION = "multi-region"
    NODAL = "nodal"


class InvestmentTreatment(StrEnum):
    """Whether a plan may build any amount of capacity, or only whole units."""

    CONTINUOUS = "continuous"
    INTEGER = "integer"


INVESTMENT_FORMULATIONS: dict[InvestmentTreatment, str] = {
    InvestmentTreatment.CONTINUOUS: "ContinuousInvestment",
    InvestmentTreatment.INTEGER: "IntegerInvestment",
}
"""The PowerSystemsInvestments formulation that builds each investment treatment."""


SERIES_JSON_SUFFIX = "_series.json"
"""The companion holding the series the portfolio cannot carry, named after the portfolio."""


class SeriesDocument:
    """Keys of the companion document holding the series the portfolio drops."""

    PERIODS = "periods"
    RECORDS = "records"
    EXISTING_DEVICES = "existing_devices"
    DEVICES = "devices"

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


class InvestmentPeriod(BaseModel):
    """One period that a plan builds in, from its first day to its last."""

    start: date
    end: date


class OperationalSlice(NamedTuple):
    """One representative day that every technology states a profile over."""

    year: str
    rep_day: int
    weight: float
    timestamps: tuple[datetime, ...]


class SeriesRecord(BaseModel):
    """One profile of one technology over one representative day of one year."""

    component_type: str
    component_name: str
    series_name: str
    year: str
    rep_day: int
    weight: float
    initial_timestamp: datetime
    resolution_seconds: float
    values: list[float]

    def list_timestamps(self) -> list[datetime]:
        """The instant of every value, which the model indexes its variables by."""
        step = timedelta(seconds=self.resolution_seconds)
        return [self.initial_timestamp + step * index for index in range(len(self.values))]

    def build_slice(self) -> OperationalSlice:
        return OperationalSlice(self.year, self.rep_day, self.weight, tuple(self.list_timestamps()))


class ExistingDevicesRecord(BaseModel):
    """The base system components that one technology already holds."""

    component_type: str
    component_name: str
    devices: list[str]


class PortfolioSeries(BaseModel):
    """The series document: the periods, the profiles and the existing devices of a plan."""

    periods: list[InvestmentPeriod]
    records: list[SeriesRecord]
    existing_devices: list[ExistingDevicesRecord] = Field(default_factory=list)

    def list_slices(self) -> list[OperationalSlice]:
        """One slice for each year and representative day of the records, in the model's order."""
        by_day: dict[tuple[str, int], OperationalSlice] = {}
        for record in self.records:
            by_day.setdefault((record.year, record.rep_day), record.build_slice())
        return [by_day[day] for day in sorted(by_day)]


class ExpansionResultsLayout:
    """Where an expansion writes its decisions, under its output directory."""

    WIDE_DIR = "results_wide"
    VARIABLES_DIR = "variables"
    EXPRESSIONS_DIR = "expressions"
    STATISTICS_DIR = "results"
    OPTIMIZER_STATS_FILE = "optimizer_stats.csv"
    CSV_SUFFIX = ".csv"


class ExpansionOutcome(NamedTuple):
    """What one expansion solve reports."""

    status: str
    objective: float


@runtime_checkable
class ExpansionPort(Protocol):
    name: ClassVar[str]

    def is_provisioned(self) -> bool:
        """Report whether the expansion runtime is already installed.

        Must be side-effect free: no downloads, no installs. Inbound surfaces call this to
        warn the user, and get consent, before a first run triggers a long download.
        """

    def solve_expansion(
        self,
        portfolio_json_path: Path,
        balance_model: BalanceModel,
        output_dir: Path | None = None,
        *,
        highs: HiGHSOptions,
        investment_treatment: InvestmentTreatment = InvestmentTreatment.CONTINUOUS,
        discount_rate: float | None = None,
    ) -> ExpansionOutcome:
        """Build and solve the expansion stated by the portfolio at ``portfolio_json_path``.

        ``discount_rate`` outranks the rate the portfolio states, for a portfolio that states
        none. The caller reads a status containing "SUCCESSFULLY" as success.
        """
