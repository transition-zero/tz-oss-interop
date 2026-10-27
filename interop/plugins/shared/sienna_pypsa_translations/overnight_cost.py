"""An overnight cost reaches a PyPSA component only beside the rate and the life that annualise it.

PyPSA refuses a network in which a component states `overnight_cost` and no `discount_rate`,
and it annualises a cost with no `lifetime` as a cost that never ends. So a record that states
a cost and no rate, or no life, keeps the cost in the PyPSA sidecar, and the network leaves it
out.
"""

from __future__ import annotations

import logging
from typing import NamedTuple, TypeVar

from interop.core.extensions import ExpansionExtension, ExtensionLookup
from interop.plugins.shared.constants import UNIT_DOLLARS_PER_MW
from interop.plugins.shared.pypsa_constants import PyPSAGeneratorCol, PyPSAStorageUnitCol
from interop.plugins.shared.sienna_pypsa_translations.mapped_fields import (
    MappedField,
    build_field_names,
)
from interop.plugins.shared.sienna_pypsa_translations.reporters import (
    GeneratorReporter,
    StorageUnitReporter,
)
from interop.plugins.shared.warning_text import name_a_few

log = logging.getLogger(__name__)

RecordT = TypeVar("RecordT", bound=ExpansionExtension)

GENERATOR_OVERNIGHT_COST = MappedField(
    "overnight_cost_per_mw", PyPSAGeneratorCol.OVERNIGHT_COST, UNIT_DOLLARS_PER_MW
)
STORAGE_OVERNIGHT_COST = MappedField(
    "overnight_cost_per_mw", PyPSAStorageUnitCol.OVERNIGHT_COST, UNIT_DOLLARS_PER_MW
)
OVERNIGHT_COST_FIELDS = build_field_names(ExpansionExtension, GENERATOR_OVERNIGHT_COST)
_DISCOUNT_RATE_FIELD = "discount_rate"
_LIFETIME_FIELD = "lifetime_years"

_UNPRICED_WARNING = (
    "%d %s(s) state an overnight cost with no discount rate or no lifetime, which PyPSA needs "
    "to annualise the cost, so the network leaves the cost out and extensions.json keeps it: %s"
)


class UnpricedCost(NamedTuple):
    """An overnight cost that a record states with no discount rate or no lifetime."""

    sienna_type: str
    name: str
    overnight_cost: float
    # The field that the record does not state, which annualising the cost needs.
    missing_field: str


def find_overnight_cost(lookup: ExtensionLookup[RecordT], record: RecordT) -> float | None:
    """The overnight cost of a record that also states a discount rate and a lifetime."""
    if record.overnight_cost_per_mw is None or _find_missing_field(record) is not None:
        return None
    return lookup.get_fields(record.name, OVERNIGHT_COST_FIELDS).overnight_cost_per_mw


def find_unpriced_cost(sienna_type: str, record: ExpansionExtension) -> UnpricedCost | None:
    """The overnight cost of a record that cannot annualise it, which the network leaves out."""
    missing_field = _find_missing_field(record)
    if record.overnight_cost_per_mw is None or missing_field is None:
        return None
    return UnpricedCost(sienna_type, record.name, record.overnight_cost_per_mw, missing_field)


def _find_missing_field(record: ExpansionExtension) -> str | None:
    """The first of the discount rate and the lifetime that the record does not state."""
    if record.discount_rate is None:
        return _DISCOUNT_RATE_FIELD
    if record.lifetime_years is None:
        return _LIFETIME_FIELD
    return None


def report_unpriced_costs(
    reporter: GeneratorReporter | StorageUnitReporter, unpriced: list[UnpricedCost]
) -> None:
    """Record each cost that the network leaves out, and warn once for all of them."""
    for cost in unpriced:
        reporter.record_overnight_cost_unpriced(
            cost.sienna_type, cost.name, cost.overnight_cost, cost.missing_field
        )
    if unpriced:
        names = [cost.name for cost in unpriced]
        log.warning(
            _UNPRICED_WARNING, len(names), reporter.destination_component, name_a_few(names)
        )
