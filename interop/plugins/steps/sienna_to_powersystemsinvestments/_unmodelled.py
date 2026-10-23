"""The technologies of a type that the adapter sets no model for, which the plan leaves out."""

from __future__ import annotations

import logging
from typing import Any

from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.power_systems_investments_schema import (
    AGGREGATE_TRANSPORT_PARAMETER,
    MODELLED_TECHNOLOGIES,
    PortfolioColumn,
)
from interop.plugins.shared.sienna_investments_constants import SiennaInvestmentsComponent
from interop.plugins.shared.warning_text import name_a_few
from interop.plugins.steps.sienna_to_powersystemsinvestments._events import record_not_mapped

log = logging.getLogger(__name__)

_MODELLED = frozenset((str(model.component), model.parameter) for model in MODELLED_TECHNOLOGIES)
# The components whose type the adapter looks a model up for; a requirement is not one of them.
_TECHNOLOGY_COMPONENTS = frozenset(
    {
        SiennaInvestmentsComponent.SUPPLY_TECHNOLOGY.value,
        SiennaInvestmentsComponent.STORAGE_TECHNOLOGY.value,
        SiennaInvestmentsComponent.AGGREGATE_TRANSPORT_TECHNOLOGY.value,
        SiennaInvestmentsComponent.DEMAND_REQUIREMENT.value,
    }
)

_UNMODELLED_NOTE = (
    "the adapter sets a PowerSystemsInvestments model for {types} only, so a technology of "
    "this type is left out of the plan"
)
_UNMODELLED_WARNING = (
    "sienna-to-power-systems-investments: %d technology(ies) are of a type that no "
    "PowerSystemsInvestments model covers, so the plan leaves each out: %s"
)


def report_unmodelled(
    rows_by_type: dict[str, list[dict[str, Any]]], recorder: ScopedRecorder
) -> None:
    """Record and warn each technology of a type that no model covers."""
    left_out: list[str] = []
    for component, rows in rows_by_type.items():
        if component not in _TECHNOLOGY_COMPONENTS:
            continue
        for row in rows:
            if (component, _get_parameter(component, row)) not in _MODELLED:
                left_out.append(row[PortfolioColumn.NAME])
                _record(component, row, recorder)
    if left_out:
        log.warning(_UNMODELLED_WARNING, len(left_out), name_a_few(left_out))


def _get_parameter(component: str, row: dict[str, Any]) -> str | None:
    if component == SiennaInvestmentsComponent.AGGREGATE_TRANSPORT_TECHNOLOGY:
        return AGGREGATE_TRANSPORT_PARAMETER
    parameter: str | None = row.get(PortfolioColumn.POWER_SYSTEMS_TYPE)
    return parameter


def _record(component: str, row: dict[str, Any], recorder: ScopedRecorder) -> None:
    types = ", ".join(f"{model.component}{{{model.parameter}}}" for model in MODELLED_TECHNOLOGIES)
    record_not_mapped(
        recorder,
        component=component,
        name=row[PortfolioColumn.NAME],
        field=PortfolioColumn.POWER_SYSTEMS_TYPE,
        value=row.get(PortfolioColumn.POWER_SYSTEMS_TYPE),
        derivation=_UNMODELLED_NOTE.format(types=types),
    )
