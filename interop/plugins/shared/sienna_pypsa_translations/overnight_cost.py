"""An overnight cost reaches a PyPSA component only beside the discount rate that annualises it.

PyPSA refuses a network in which a component states `overnight_cost` and no `discount_rate`.
So a record that states a cost and no rate keeps the cost in the PyPSA sidecar, and the
network leaves it out.
"""

from __future__ import annotations

import logging
from typing import NamedTuple, TypeVar

from interop.core.extensions import ExpansionExtension, ExtensionLookup
from interop.plugins.shared.sienna_pypsa_translations.mapped_fields import build_field_names
from interop.plugins.shared.sienna_pypsa_translations.reporters import (
    GeneratorReporter,
    StorageUnitReporter,
)
from interop.plugins.shared.warning_text import name_a_few

log = logging.getLogger(__name__)

RecordT = TypeVar("RecordT", bound=ExpansionExtension)

OVERNIGHT_COST_FIELDS = build_field_names(ExpansionExtension, "overnight_cost_per_mw")

_UNPRICED_WARNING = (
    "%d %s(s) state an overnight cost and no discount rate, and PyPSA cannot annualise the "
    "cost without one, so the network leaves the cost out and extensions.json keeps it: %s"
)


class UnpricedCost(NamedTuple):
    """An overnight cost that a record states with no discount rate."""

    sienna_type: str
    name: str
    overnight_cost: float


def find_overnight_cost(lookup: ExtensionLookup[RecordT], record: RecordT) -> float | None:
    """The overnight cost of a record that also states a discount rate, read as mapped."""
    if record.overnight_cost_per_mw is None or record.discount_rate is None:
        return None
    return lookup.get_fields(record.name, OVERNIGHT_COST_FIELDS).overnight_cost_per_mw


def find_unpriced_cost(sienna_type: str, record: ExpansionExtension) -> UnpricedCost | None:
    """The overnight cost of a record that states no discount rate, which the network leaves out."""
    if record.overnight_cost_per_mw is None or record.discount_rate is not None:
        return None
    return UnpricedCost(sienna_type, record.name, record.overnight_cost_per_mw)


def report_unpriced_costs(
    reporter: GeneratorReporter | StorageUnitReporter, unpriced: list[UnpricedCost]
) -> None:
    """Record each cost that the network leaves out, and warn once for all of them."""
    for cost in unpriced:
        reporter.record_overnight_cost_unpriced(cost.sienna_type, cost.name, cost.overnight_cost)
    if unpriced:
        names = [cost.name for cost in unpriced]
        log.warning(
            _UNPRICED_WARNING, len(names), reporter.destination_component, name_a_few(names)
        )
