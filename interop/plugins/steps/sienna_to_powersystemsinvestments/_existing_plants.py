"""A technology of its own for each existing plant that no technology of the plan names.

The technology holds the plant's rating, its Zone and its operation cost, and the plan cannot
add to it. A plant of a type that no model covers stays out of the plan.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, NamedTuple

import polars as pl

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import StagedTimeSeriesCol
from interop.plugins.shared.power_systems_investments_schema import (
    MODELLED_TECHNOLOGIES,
    PortfolioColumn,
    PortfolioComponent,
)
from interop.plugins.shared.sienna_constants import (
    SIENNA_REGION_COLUMN,
    MinMaxField,
    SiennaComponent,
    SiennaGeneratorCol,
    SiennaSeriesName,
)
from interop.plugins.shared.sienna_investments_constants import (
    DEFAULT_BASE_YEAR,
    PORTFOLIO_FINANCIAL_DATA_TABLE,
    SiennaInvestmentsComponent,
    SiennaPortfolioFinancialDataCol,
    SiennaSupplyTechnologyCol,
    SiennaTechnologyFinancialDataField,
)
from interop.plugins.shared.warning_text import name_a_few
from interop.plugins.steps.sienna_to_powersystemsinvestments._base_devices import (
    BaseDevice,
    Technology,
)
from interop.plugins.steps.sienna_to_powersystemsinvestments._events import (
    PLAN,
    record_not_mapped,
    record_translation,
)

log = logging.getLogger(__name__)

# The existing plants that can stand as a technology of their own: the types a model covers.
_SUPPLY_TYPES = frozenset(
    model.parameter
    for model in MODELLED_TECHNOLOGIES
    if model.component is PortfolioComponent.SUPPLY_TECHNOLOGY
)
_SUPPLY = SiennaInvestmentsComponent.SUPPLY_TECHNOLOGY.value
_HYDRO_BUDGET_KEY = (SiennaComponent.HYDRO_DISPATCH.value, SiennaSeriesName.HYDRO_BUDGET.value)
_PS_FUEL = "fuel"
_PS_AVAILABLE = "available"
_EXISTING_SUFFIX = "/existing"
_LINK_KIND = "link"
_PLANT_KIND = "plant"
_NO_MINIMUM = 0.0
_ALL_EQUITY = 0.0
# A plant that the plan cannot add to costs nothing to build, so one year recovers its cost.
_EXISTING_RECOVERY_PERIOD = 1
# A rate above zero keeps the capital recovery factor defined when nothing states one.
FALLBACK_EXISTING_PLANT_RATE = 0.05

_NO_TECHNOLOGY_NOTE = (
    "no technology of the plan names this existing {kind} and the model has no technology type "
    "for it, so its capacity is left out of the plan"
)
_NAME_TAKEN_NOTE = (
    "a technology of the plan has the name of this existing plant, and so has the name with "
    "/existing, so the plant is left out of the plan"
)
_RENAME_DERIVATION = (
    "a technology of the plan has the name of this existing plant and does not name it as an "
    "existing device, so the plant's own technology takes the name with /existing"
)
_PLANT_DERIVATION = (
    "an existing plant that no technology names -> a technology of its own that holds its "
    "rating, with no capital cost and no room to build"
)
_OPERATION_COST_DERIVATION = (
    "the operation cost of the existing plant in the base system, unchanged"
)
_HYDRO_BUDGET_NOTE = (
    "the model reads no energy budget for a supply technology, so the hydro_budget of the "
    "existing plant does not limit its technology"
)
_RATE_DERIVATION = (
    "an existing plant is financed at the discount rate of the portfolio, or at the highest "
    "rate of a technology when the portfolio states none, because a rate of zero makes the "
    "capital recovery factor undefined"
)
_FALLBACK_RATE_DERIVATION = (
    "neither the portfolio nor a technology states a rate above zero, and a rate of zero makes "
    "the capital recovery factor undefined, so an existing plant is financed at the fallback "
    "rate; it builds nothing, so the rate prices nothing"
)

_LEFT_OUT_WARNING = (
    "sienna-to-power-systems-investments: %d existing component(s) have no technology in the "
    "plan, so their capacity is left out: %s"
)
_RENAMED_WARNING = (
    "sienna-to-power-systems-investments: %d existing plant(s) share a name with a technology "
    "that does not name them, so each plant's own technology takes the name with /existing: %s"
)
_HYDRO_BUDGET_WARNING = (
    "sienna-to-power-systems-investments: %d existing hydro plant(s) state a hydro_budget, which "
    "PowerSystemsInvestments does not read for a supply technology: %s"
)


class PlantRow(NamedTuple):
    """A technology row for one existing plant, the operation cost it runs at, and the plant."""

    row: dict[str, Any]
    operation_cost: dict[str, Any]
    technology: Technology
    device: BaseDevice


@dataclass
class _LeftOut:
    """The names each warning about the existing plants lists."""

    components: list[str] = field(default_factory=list)
    renamed: list[str] = field(default_factory=list)
    hydro_budgets: list[str] = field(default_factory=list)

    def list_warnings(self) -> list[tuple[str, list[str]]]:
        return [
            (_LEFT_OUT_WARNING, self.components),
            (_RENAMED_WARNING, self.renamed),
            (_HYDRO_BUDGET_WARNING, self.hydro_budgets),
        ]


class _PlantContext(NamedTuple):
    """What each technology made for an existing plant shares."""

    finance: dict[str, Any]
    first_id: int


class ExistingPlantBuilder:
    """Builds a technology for each existing plant that no technology names, and reports it."""

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder
        self._left_out = _LeftOut()

    def list_plants(
        self,
        unnamed: list[BaseDevice],
        rows_by_type: dict[str, list[dict[str, Any]]],
        state: State,
    ) -> list[PlantRow]:
        """A technology row and the operation cost of each existing plant that no one names."""
        rows = [row for type_rows in rows_by_type.values() for row in type_rows]
        taken = {row[PortfolioColumn.NAME] for row in rows}
        named = [(device, self._choose_plant_name(device, taken)) for device in unnamed]
        chosen = [(device, name) for device, name in named if name is not None]
        if not chosen:
            return []
        first_id = max((row[PortfolioColumn.ID] for row in rows), default=0) + 1
        context = _PlantContext(self._build_finance(state, rows), first_id)
        return [
            self._build_plant(device, name, context.first_id + index, context, state)
            for index, (device, name) in enumerate(chosen)
        ]

    def warn(self) -> None:
        """Warn each existing plant that the plan leaves out, renames or reads in part."""
        for warning, names in self._left_out.list_warnings():
            if names:
                log.warning(warning, len(names), name_a_few(names))

    def _choose_plant_name(self, device: BaseDevice, taken: set[str]) -> str | None:
        """The name of the plant's own technology, or None when the plan cannot hold it."""
        if device.sienna_type not in _SUPPLY_TYPES:
            self._record_component_left_out(device, _build_no_technology_note(device))
            return None
        if device.name not in taken:
            taken.add(device.name)
            return device.name
        renamed = f"{device.name}{_EXISTING_SUFFIX}"
        if renamed in taken:
            self._record_component_left_out(device, _NAME_TAKEN_NOTE)
            return None
        taken.add(renamed)
        self._left_out.renamed.append(device.name)
        self._record_renamed(device, renamed)
        return renamed

    def _build_plant(
        self,
        device: BaseDevice,
        name: str,
        component_id: int,
        context: _PlantContext,
        state: State,
    ) -> PlantRow:
        row = _build_plant_row(device, name, component_id, context.finance)
        self._record_plant(device, name)
        self._report_hydro_budget(device, state)
        operation_cost = device.row[SiennaGeneratorCol.OPERATION_COST]
        return PlantRow(row, operation_cost, Technology(_SUPPLY, name, device.sienna_type), device)

    def _build_finance(self, state: State, rows: list[dict[str, Any]]) -> dict[str, Any]:
        """All-equity financing at the portfolio's rate, else the highest rate of a technology."""
        stated = _find_portfolio_finance(state)
        rate = stated.get(SiennaPortfolioFinancialDataCol.DISCOUNT_RATE) or 0.0
        derivation = _RATE_DERIVATION
        if rate <= 0.0:
            rate = max((_find_return_on_equity(row) for row in rows), default=0.0)
        if rate <= 0.0:
            rate, derivation = FALLBACK_EXISTING_PLANT_RATE, _FALLBACK_RATE_DERIVATION
        self._record_rate(rate, derivation)
        base_year = stated.get(SiennaPortfolioFinancialDataCol.BASE_YEAR) or DEFAULT_BASE_YEAR
        return _build_finance_struct(rate, base_year)

    def _report_hydro_budget(self, device: BaseDevice, state: State) -> None:
        if not _has_hydro_budget(state, device):
            return
        self._left_out.hydro_budgets.append(device.name)
        record_not_mapped(
            self._recorder,
            component=device.sienna_type,
            name=device.name,
            field=SiennaSeriesName.HYDRO_BUDGET,
            value=SiennaSeriesName.HYDRO_BUDGET.value,
            derivation=_HYDRO_BUDGET_NOTE,
        )

    def _record_component_left_out(self, device: BaseDevice, note: str) -> None:
        self._left_out.components.append(device.name)
        record_not_mapped(
            self._recorder,
            component=device.sienna_type,
            name=device.name,
            field=SiennaGeneratorCol.RATING,
            value=device.rating_mw,
            derivation=note,
        )

    def _record_renamed(self, device: BaseDevice, renamed: str) -> None:
        record_translation(
            self._recorder,
            component=device.sienna_type,
            name=device.name,
            source_field=SiennaGeneratorCol.NAME,
            source_value=device.name,
            destination_field=PortfolioColumn.NAME,
            destination_value=renamed,
            derivation=_RENAME_DERIVATION,
        )

    def _record_plant(self, device: BaseDevice, name: str) -> None:
        self._record_plant_rating(device)
        self._record_plant_cost(device, name)

    def _record_plant_rating(self, device: BaseDevice) -> None:
        record_translation(
            self._recorder,
            component=device.sienna_type,
            name=device.name,
            source_field=SiennaGeneratorCol.RATING,
            source_value=device.rating_mw,
            destination_field=f"{SiennaSupplyTechnologyCol.CAPACITY_LIMITS}.{MinMaxField.MAX}",
            destination_value=device.rating_mw,
            derivation=_PLANT_DERIVATION,
        )

    def _record_plant_cost(self, device: BaseDevice, name: str) -> None:
        record_translation(
            self._recorder,
            component=_SUPPLY,
            name=name,
            source_field=SiennaGeneratorCol.OPERATION_COST,
            source_value=device.sienna_type,
            destination_field=SiennaSupplyTechnologyCol.OPERATION_COSTS,
            destination_value=device.sienna_type,
            derivation=_OPERATION_COST_DERIVATION,
        )

    def _record_rate(self, rate: float, derivation: str) -> None:
        record_translation(
            self._recorder,
            component=_SUPPLY,
            name=PLAN,
            source_field=SiennaPortfolioFinancialDataCol.DISCOUNT_RATE,
            source_value=rate,
            destination_field=(
                f"{SiennaSupplyTechnologyCol.FINANCIAL_DATA}."
                f"{SiennaTechnologyFinancialDataField.RETURN_ON_EQUITY}"
            ),
            destination_value=rate,
            derivation=derivation,
        )


def _build_no_technology_note(device: BaseDevice) -> str:
    is_link = device.sienna_type == SiennaComponent.TWO_TERMINAL_GENERIC_HVDC_LINE
    return _NO_TECHNOLOGY_NOTE.format(kind=_LINK_KIND if is_link else _PLANT_KIND)


def _find_portfolio_finance(state: State) -> dict[str, Any]:
    portfolio = state.source_topology.get(PORTFOLIO_FINANCIAL_DATA_TABLE)
    rows = [] if portfolio is None else portfolio.collect().to_dicts()
    return rows[0] if rows else {}


def _find_return_on_equity(row: dict[str, Any]) -> float:
    finance = row.get(SiennaSupplyTechnologyCol.FINANCIAL_DATA) or {}
    return float(finance.get(SiennaTechnologyFinancialDataField.RETURN_ON_EQUITY) or 0.0)


def _build_finance_struct(rate: float, base_year: int) -> dict[str, Any]:
    return {
        SiennaTechnologyFinancialDataField.CAPITAL_RECOVERY_PERIOD: _EXISTING_RECOVERY_PERIOD,
        SiennaTechnologyFinancialDataField.TECHNOLOGY_BASE_YEAR: base_year,
        SiennaTechnologyFinancialDataField.DEBT_FRACTION: _ALL_EQUITY,
        SiennaTechnologyFinancialDataField.DEBT_RATE: _ALL_EQUITY,
        SiennaTechnologyFinancialDataField.RETURN_ON_EQUITY: rate,
        SiennaTechnologyFinancialDataField.TAX_RATE: _ALL_EQUITY,
    }


def _build_plant_row(
    device: BaseDevice, name: str, component_id: int, finance: dict[str, Any]
) -> dict[str, Any]:
    """A supply technology that holds one existing plant and that the plan cannot add to."""
    fuel = device.row.get(_PS_FUEL)
    available = device.row.get(_PS_AVAILABLE)
    return {
        PortfolioColumn.ID: component_id,
        PortfolioColumn.NAME: name,
        SiennaSupplyTechnologyCol.AVAILABLE: True if available is None else bool(available),
        PortfolioColumn.POWER_SYSTEMS_TYPE: device.sienna_type,
        SiennaSupplyTechnologyCol.PRIME_MOVER_TYPE: device.row.get(
            SiennaGeneratorCol.PRIME_MOVER_TYPE
        ),
        SiennaSupplyTechnologyCol.FUEL: [fuel] if fuel else [],
        SIENNA_REGION_COLUMN: [] if device.zone is None else [device.zone],
        SiennaSupplyTechnologyCol.CAPITAL_COSTS: None,
        SiennaSupplyTechnologyCol.CAPACITY_LIMITS: {
            MinMaxField.MIN: _NO_MINIMUM,
            MinMaxField.MAX: device.rating_mw,
        },
        SiennaSupplyTechnologyCol.FINANCIAL_DATA: dict(finance),
    }


def _has_hydro_budget(state: State, device: BaseDevice) -> bool:
    frame = state.source_time_series.get(_HYDRO_BUDGET_KEY)
    if device.sienna_type != SiennaComponent.HYDRO_DISPATCH or frame is None:
        return False
    is_device = pl.col(StagedTimeSeriesCol.COMPONENT) == device.name
    return bool(frame.filter(is_device).select(pl.len()).collect().item())
