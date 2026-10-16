"""The loss of a transport technology, which the model applies in one direction only.

PowerSystemsInvestments lets an ``AggregateTransportTechnology`` flow both ways, and takes the
loss from the energy that reaches the end region. A flow from the end to the start therefore
delivers more energy than it takes, so a stated loss lets a plan make energy. The step writes no
loss, and the transport is lossless in both directions.
"""

from __future__ import annotations

import logging
from typing import Any

from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.sienna_investments_constants import (
    SiennaAggregateTransportTechnologyCol,
    SiennaInvestmentsComponent,
)
from interop.plugins.shared.warning_text import name_a_few
from interop.plugins.steps.sienna_to_powersystemsinvestments._events import record_not_mapped

log = logging.getLogger(__name__)

_NO_LOSS = 0.0

_LOSS_NOTE = (
    "the model takes the loss from the energy that reaches the end region and lets the flow "
    "run both ways, so a flow from the end to the start would make energy; the transport is "
    "lossless instead"
)
_LOSS_WARNING = (
    "sienna-to-power-systems-investments: %d transport technology(ies) state a loss, which "
    "PowerSystemsInvestments would turn into energy on a reverse flow, so each is lossless: %s"
)


class TransportLosses:
    """Writes each transport technology lossless, and names those that state a loss."""

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder
        self._lossy: list[str] = []

    def set_lossless(self, row: dict[str, Any]) -> None:
        loss = row.get(SiennaAggregateTransportTechnologyCol.LINE_LOSS)
        row[SiennaAggregateTransportTechnologyCol.LINE_LOSS] = _NO_LOSS
        if not loss:
            return
        name = row[SiennaAggregateTransportTechnologyCol.NAME]
        self._lossy.append(name)
        record_not_mapped(
            self._recorder,
            component=SiennaInvestmentsComponent.AGGREGATE_TRANSPORT_TECHNOLOGY.value,
            name=name,
            field=SiennaAggregateTransportTechnologyCol.LINE_LOSS,
            value=loss,
            derivation=_LOSS_NOTE,
        )

    def warn_lost(self) -> None:
        if self._lossy:
            log.warning(_LOSS_WARNING, len(self._lossy), name_a_few(self._lossy))
