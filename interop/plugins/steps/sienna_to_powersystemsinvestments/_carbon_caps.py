"""A carbon cap reaches the portfolio, and the model builds no constraint from it."""

from __future__ import annotations

import logging

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.sienna_constants import SIENNA_NAME_COLUMN
from interop.plugins.shared.sienna_investments_constants import (
    SiennaCarbonCapsCol,
    SiennaInvestmentsComponent,
)
from interop.plugins.shared.warning_text import name_a_few
from interop.plugins.steps.sienna_to_powersystemsinvestments._events import record_not_mapped

log = logging.getLogger(__name__)

_NO_CONSTRAINT_NOTE = (
    "PowerSystemsInvestments builds a constraint from an EnergyShareRequirements only, so the "
    "CarbonCaps reaches the portfolio with its target_year and does not limit the plan"
)
_NO_CONSTRAINT_WARNING = (
    "sienna-to-power-systems-investments: %d carbon cap(s) reach the portfolio, and "
    "PowerSystemsInvestments builds no constraint from a CarbonCaps, so none limits the plan: %s"
)


def report_carbon_caps(state: State, recorder: ScopedRecorder) -> None:
    """Record and warn that each carbon cap leaves the plan unlimited."""
    table = state.destination_tables.get(SiennaInvestmentsComponent.CARBON_CAPS.value)
    if table is None or table.is_empty():
        return
    names: list[str] = []
    for row in table.iter_rows(named=True):
        names.append(row[SIENNA_NAME_COLUMN])
        record_not_mapped(
            recorder,
            component=SiennaInvestmentsComponent.CARBON_CAPS.value,
            name=row[SIENNA_NAME_COLUMN],
            field=SiennaCarbonCapsCol.MAX_MTONS,
            value=row.get(SiennaCarbonCapsCol.MAX_MTONS),
            derivation=_NO_CONSTRAINT_NOTE,
        )
    log.warning(_NO_CONSTRAINT_WARNING, len(names), name_a_few(names))
