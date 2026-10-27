"""The flow a Sienna HVDC line may carry, read from its ratings and its operational flow limit.

``rating`` is the transfer rating of the DC line, and ``rating_from`` and ``rating_to`` are the
converter ratings at its two ends. A converter rating that a line leaves out adds no limit. The
optional ``operational_flow_limit`` bounds the flow in each direction, in addition to the
ratings. A line that states no operational flow limit can move power both ways.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from interop.plugins.shared.sienna_constants import OperationalFlowLimitField, SiennaLinkCol

FROM_TO_MAX = f"{SiennaLinkCol.OPERATIONAL_FLOW_LIMIT}.{OperationalFlowLimitField.FROM_TO_MAX}"
TO_FROM_MAX = f"{SiennaLinkCol.OPERATIONAL_FLOW_LIMIT}.{OperationalFlowLimitField.TO_FROM_MAX}"
FLOW_BOUNDS_DERIVATION = (
    "the smallest of rating, rating_from and rating_to bounds the flow each way; "
    "operational_flow_limit.from_to_max and .to_from_max lower it, when stated"
)
_RATING_COLUMNS = (SiennaLinkCol.RATING, SiennaLinkCol.RATING_FROM, SiennaLinkCol.RATING_TO)


@dataclass(frozen=True)
class HvdcFlowBounds:
    """The flow bounds of one line, in MW. A positive flow runs from the from bus to the to bus."""

    minimum: float
    maximum: float


def build_hvdc_flow_bounds(component: Mapping[str, Any]) -> HvdcFlowBounds:
    """The bounds that the ratings and the operational flow limit of a line allow together."""
    ceiling = _choose_ceiling(component)
    limit = component.get(SiennaLinkCol.OPERATIONAL_FLOW_LIMIT)
    if limit is None:
        return HvdcFlowBounds(minimum=-ceiling, maximum=ceiling)
    reverse = min(float(limit[OperationalFlowLimitField.TO_FROM_MAX]), ceiling)
    return HvdcFlowBounds(
        minimum=-reverse if reverse > 0.0 else 0.0,
        maximum=min(float(limit[OperationalFlowLimitField.FROM_TO_MAX]), ceiling),
    )


def _choose_ceiling(component: Mapping[str, Any]) -> float:
    """The smallest of the transfer rating and each converter rating that the line states."""
    stated = (component.get(column) for column in _RATING_COLUMNS)
    return min(float(rating) for rating in stated if rating is not None)
