"""A transport technology, which the model flows both ways.

PowerSystemsInvestments lets an ``AggregateTransportTechnology`` flow both ways, and takes the
loss from the energy that reaches the end region. A flow from the end to the start therefore
delivers more energy than it takes, so a stated loss lets a plan make energy. The step writes no
loss, and the transport is lossless in both directions. A source that states one direction for
a link, such as one technology for each direction, gets a link in the plan that flows both ways.
The model builds a transport technology from a lower bound of 0 and never reads the minimum of
its capacity limit, so the step writes a minimum of 0.
"""

from __future__ import annotations

from typing import Any

from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.sienna_constants import MinMaxField
from interop.plugins.shared.sienna_investments_constants import (
    SiennaAggregateTransportTechnologyCol,
    SiennaInvestmentsComponent,
)
from interop.plugins.shared.warning_text import name_a_few
from interop.plugins.steps.sienna_to_powersystemsinvestments._events import (
    record_not_mapped,
    warn_step,
)

_NO_LOSS = 0.0
_NO_MINIMUM = 0.0
_COMPONENT = SiennaInvestmentsComponent.AGGREGATE_TRANSPORT_TECHNOLOGY.value
_DIRECTION_FIELD = "direction"

_LOSS_NOTE = (
    "the model takes the loss from the energy that reaches the end region and lets the flow "
    "run both ways, so a flow from the end to the start would make energy; the transport is "
    "lossless instead"
)
_LOSS_WARNING = (
    "%d transport technology(ies) state a loss, which "
    "PowerSystemsInvestments would turn into energy on a reverse flow, so each is lossless: %s"
)
_MINIMUM_NOTE = (
    "the model builds a transport technology from a lower bound of 0 and never reads the "
    "minimum of its capacity limit, so the minimum is 0"
)
_MINIMUM_WARNING = (
    "%d transport technology(ies) state a minimum capacity, which "
    "PowerSystemsInvestments never reads, so each builds from 0: %s"
)
_DIRECTION_NOTE = (
    "the model lets every transport technology flow from the end region to the start region "
    "too, so the direction that the source states does not bound the flow"
)
_DIRECTION_WARNING = (
    "PowerSystemsInvestments flows %d transport "
    "technology(ies) both ways, whatever direction the source states: %s"
)


class TransportLinks:
    """Writes each transport technology lossless and with no minimum, and names what it loses."""

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder
        self._lossy: list[str] = []
        self._with_minimum: list[str] = []
        self._links: list[str] = []

    def set_links(self, row: dict[str, Any]) -> None:
        name = row[SiennaAggregateTransportTechnologyCol.NAME]
        self._links.append(name)
        self._set_lossless(row, name)
        self._set_no_minimum(row, name)
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
            warn_step(_LOSS_WARNING, len(self._lossy), name_a_few(self._lossy))
        if self._with_minimum:
            warn_step(_MINIMUM_WARNING, len(self._with_minimum), name_a_few(self._with_minimum))
        if self._links:
            warn_step(_DIRECTION_WARNING, len(self._links), name_a_few(self._links))

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

    def _set_no_minimum(self, row: dict[str, Any], name: str) -> None:
        limits = row.get(SiennaAggregateTransportTechnologyCol.CAPACITY_LIMITS)
        if limits is None or (limits.get(MinMaxField.MIN) or _NO_MINIMUM) <= _NO_MINIMUM:
            return
        row[SiennaAggregateTransportTechnologyCol.CAPACITY_LIMITS] = {
            **limits,
            MinMaxField.MIN: _NO_MINIMUM,
        }
        self._with_minimum.append(name)
        record_not_mapped(
            self._recorder,
            component=_COMPONENT,
            name=name,
            field=f"{SiennaAggregateTransportTechnologyCol.CAPACITY_LIMITS}.{MinMaxField.MIN}",
            value=limits[MinMaxField.MIN],
            derivation=_MINIMUM_NOTE,
        )
