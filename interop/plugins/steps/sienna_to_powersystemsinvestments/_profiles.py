"""Which supply technologies the model reads a profile for, and the record of those it does not."""

from __future__ import annotations

import logging

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.power_systems_investments_schema import (
    InvestmentsSeriesName,
    PortfolioColumn,
)
from interop.plugins.shared.sienna_constants import SiennaComponent, SiennaSeriesName
from interop.plugins.shared.sienna_investments_constants import SiennaInvestmentsComponent
from interop.plugins.shared.warning_text import name_a_few
from interop.plugins.steps.sienna_to_powersystemsinvestments._events import record_not_mapped

log = logging.getLogger(__name__)

PROFILED_SUPPLY_TYPES = frozenset(
    {SiennaComponent.RENEWABLE_DISPATCH.value, SiennaComponent.HYDRO_DISPATCH.value}
)
"""The supply types whose ``ops_variable_cap_factor`` the model reads, and stops without."""

_UNPROFILED_NOTE = (
    "the model reads ops_variable_cap_factor for a RenewableDispatch and a HydroDispatch only, "
    "so a technology of this type runs up to its capacity in every hour"
)
_UNPROFILED_WARNING = (
    "sienna-to-power-systems-investments: %d supply technology(ies) state a profile that "
    "PowerSystemsInvestments does not read for their type, so each runs up to its capacity in "
    "every hour: %s"
)


def build_supply_types(state: State) -> dict[str, str]:
    """The PowerSystems type of each supply technology of the plan, by its name."""
    table = state.destination_tables.get(SiennaInvestmentsComponent.SUPPLY_TECHNOLOGY.value)
    if table is None:
        return {}
    return dict(table.select(PortfolioColumn.NAME, PortfolioColumn.POWER_SYSTEMS_TYPE).iter_rows())


def report_unprofiled(names: list[str], recorder: ScopedRecorder) -> None:
    """Record and warn each supply technology whose stated profile the model does not read."""
    for name in names:
        record_not_mapped(
            recorder,
            component=SiennaInvestmentsComponent.SUPPLY_TECHNOLOGY.value,
            name=name,
            field=SiennaSeriesName.MAX_ACTIVE_POWER,
            value=str(InvestmentsSeriesName.VARIABLE_CAPACITY_FACTOR),
            derivation=_UNPROFILED_NOTE,
        )
    if names:
        log.warning(_UNPROFILED_WARNING, len(names), name_a_few(names))
