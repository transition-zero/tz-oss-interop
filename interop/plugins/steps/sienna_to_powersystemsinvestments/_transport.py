"""A transport technology, which the model flows both ways and treats as one branch type.

PowerSystemsInvestments lets an ``AggregateTransportTechnology`` flow both ways, and takes the
loss from the energy that reaches the end region. A flow from the end to the start therefore
delivers more energy than it takes, so a stated loss lets a plan make energy. The step writes no
loss, and the transport is lossless in both directions. A source that states one direction for
a link, such as one technology for each direction, gets a link in the plan that flows both ways.
"""

from __future__ import annotations

import logging
from typing import Any

from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.power_systems_investments_schema import AGGREGATE_TRANSPORT_PARAMETER
from interop.plugins.shared.sienna_investments_constants import (
    SiennaAggregateTransportTechnologyCol,
    SiennaInvestmentsComponent,
)
from interop.plugins.shared.warning_text import name_a_few
from interop.plugins.steps.sienna_to_powersystemsinvestments._events import (
    record_not_mapped,
    record_translation,
)

log = logging.getLogger(__name__)

_NO_LOSS = 0.0
_COMPONENT = SiennaInvestmentsComponent.AGGREGATE_TRANSPORT_TECHNOLOGY.value
_DIRECTION_FIELD = "direction"

_LOSS_NOTE = (
    "the model takes the loss from the energy that reaches the end region and lets the flow "
    "run both ways, so a flow from the end to the start would make energy; the transport is "
    "lossless instead"
)
_LOSS_WARNING = (
    "sienna-to-power-systems-investments: %d transport technology(ies) state a loss, which "
    "PowerSystemsInvestments would turn into energy on a reverse flow, so each is lossless: %s"
)
_DIRECTION_NOTE = (
    "the model lets every transport technology flow from the end region to the start region "
    "too, so the direction that the source states does not bound the flow"
)
_DIRECTION_WARNING = (
    "sienna-to-power-systems-investments: PowerSystemsInvestments flows %d transport "
    "technology(ies) both ways, whatever direction the source states: %s"
)
_TYPE_DERIVATION = (
    "the adapter sets a model for AggregateTransportTechnology{ACBranch} only, and the model "
    "treats every branch type alike, so the technology names ACBranch"
)


class TransportLinks:
    """Writes each transport technology lossless and as an ACBranch, and names what it loses."""

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder
        self._lossy: list[str] = []
        self._links: list[str] = []

    def set_links(self, row: dict[str, Any]) -> None:
        name = row[SiennaAggregateTransportTechnologyCol.NAME]
        self._links.append(name)
        self._set_branch_type(row, name)
        self._set_lossless(row, name)
        record_not_mapped(
            self._recorder,
            component=_COMPONENT,
            name=name,
            field=_DIRECTION_FIELD,
            value=(
                f"{row.get(SiennaAggregateTransportTechnologyCol.START_REGION)} -> "
                f"{row.get(SiennaAggregateTransportTechnologyCol.END_REGION)}"
            ),
            derivation=_DIRECTION_NOTE,
        )

    def warn_lost(self) -> None:
        if self._lossy:
            log.warning(_LOSS_WARNING, len(self._lossy), name_a_few(self._lossy))
        if self._links:
            log.warning(_DIRECTION_WARNING, len(self._links), name_a_few(self._links))

    def _set_branch_type(self, row: dict[str, Any], name: str) -> None:
        stated = row.get(SiennaAggregateTransportTechnologyCol.POWER_SYSTEMS_TYPE)
        row[SiennaAggregateTransportTechnologyCol.POWER_SYSTEMS_TYPE] = (
            AGGREGATE_TRANSPORT_PARAMETER
        )
        record_translation(
            self._recorder,
            component=_COMPONENT,
            name=name,
            source_field=SiennaAggregateTransportTechnologyCol.POWER_SYSTEMS_TYPE,
            source_value=stated,
            destination_field=SiennaAggregateTransportTechnologyCol.POWER_SYSTEMS_TYPE,
            destination_value=AGGREGATE_TRANSPORT_PARAMETER,
            derivation=_TYPE_DERIVATION,
        )

    def _set_lossless(self, row: dict[str, Any], name: str) -> None:
        loss = row.get(SiennaAggregateTransportTechnologyCol.LINE_LOSS)
        row[SiennaAggregateTransportTechnologyCol.LINE_LOSS] = _NO_LOSS
        if not loss:
            return
        self._lossy.append(name)
        record_not_mapped(
            self._recorder,
            component=_COMPONENT,
            name=name,
            field=SiennaAggregateTransportTechnologyCol.LINE_LOSS,
            value=loss,
            derivation=_LOSS_NOTE,
        )
