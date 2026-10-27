"""The base of every Sienna to PyPSA reporter, and the text that several of them share."""

from __future__ import annotations

from typing import ClassVar

from interop.plugins.shared.constants import (
    EXTENSIONS_PREFIX,
    UNIT_DOLLARS_PER_MW,
    UNIT_MW,
    Framework,
)
from interop.plugins.shared.framework_reporting import DestinationReporter
from interop.plugins.shared.pypsa_constants import PyPSAGeneratorCol
from interop.plugins.shared.sienna_constants import SiennaGeneratorCol, SiennaStructField

ACTIVE_POWER_LIMITS_MIN = f"{SiennaGeneratorCol.ACTIVE_POWER_LIMITS}.{SiennaStructField.MIN}"
CARRIER_FROM_PRIME_MOVER = "(sienna_type, prime_mover_type) -> carrier"
P_NOM_EXTENDABLE_DEFAULT = "no ext.p_nom_extendable; p_nom_extendable defaults to False"
# A Line states its capacity as s_nom, so each floor derivation names its own component's
# capacity field.
EXTENDABLE_FLOOR_TEMPLATE = (
    "PyPSA ignores the {capacity} of an extendable component, so the capacity an operations "
    "system already dispatches states itself as the floor a build cannot take away"
)
P_NOM_FLOOR_DERIVATION = EXTENDABLE_FLOOR_TEMPLATE.format(capacity=PyPSAGeneratorCol.P_NOM)
AVAILABLE_TO_ACTIVE = "available -> active"

_EXT_OVERNIGHT_COST_ATTR = f"{EXTENSIONS_PREFIX}overnight_cost_per_mw"
_UNPRICED_OVERNIGHT_COST_NOTE = (
    "the record states no {missing_field}, and PyPSA annualises an overnight_cost only over a "
    "discount_rate and a lifetime, so the network leaves the cost out; extensions.json keeps it"
)
_UNSTATED_DEFAULT_NOTE = "the {record} record states no {column}, so PyPSA's own default applies"
_EXT_P_NOM_ATTR = f"{EXTENSIONS_PREFIX}p_nom"


class SiennaToPypsaReporter(DestinationReporter):
    """Shared TranslationEvent plumbing for the Sienna -> PyPSA reporters."""

    source_framework = Framework.SIENNA
    destination_framework = Framework.PYPSA
    # The record that the note of a PyPSA default names.
    unstated_record: ClassVar[str] = "sidecar"

    def record_carried(
        self,
        sienna_type: str,
        name: str,
        field_name: str,
        column: str,
        value: object,
        unit: str | None = None,
    ) -> None:
        """A value Sienna states nowhere, read back from the sidecar into its PyPSA column."""
        attribute = f"{EXTENSIONS_PREFIX}{field_name}"
        self._derived(
            sources=[self._source_field(sienna_type, name, attribute, value, unit)],
            destinations=[self._destination(name, column, value, unit)],
            derivation=f"{attribute} (PyPSA round-trip)",
        )

    def record_unstated_default(self, name: str, column: str, value: object) -> None:
        """A PyPSA column that takes PyPSA's own value, as the sidecar record states none."""
        self._default_applied(
            destinations=[self._destination(name, column, value)],
            note=_UNSTATED_DEFAULT_NOTE.format(record=self.unstated_record, column=column),
        )

    def _record_stated_floor(self, sienna_type: str, name: str, p_nom: float) -> None:
        """The p_nom that a sidecar record states, as the floor of an extendable build."""
        self._derived(
            sources=[self._source_field(sienna_type, name, _EXT_P_NOM_ATTR, p_nom, UNIT_MW)],
            destinations=[self._destination(name, PyPSAGeneratorCol.P_NOM_MIN, p_nom, UNIT_MW)],
            derivation=P_NOM_FLOOR_DERIVATION,
        )

    def record_bound_unapplied(
        self, sienna_type: str, name: str, field_name: str, note: str
    ) -> None:
        """An energy bound of a sidecar record that the network does not apply."""
        attribute = f"{EXTENSIONS_PREFIX}{field_name}"
        self._not_mapped(
            sources=[self._source_field(sienna_type, name, attribute, None)], note=note
        )

    def record_overnight_cost_unpriced(
        self, sienna_type: str, name: str, overnight_cost: float, missing_field: str
    ) -> None:
        """An overnight cost the network leaves out, as the record states no rate or no life."""
        self._not_mapped(
            sources=[
                self._source_field(
                    sienna_type, name, _EXT_OVERNIGHT_COST_ATTR, overnight_cost, UNIT_DOLLARS_PER_MW
                )
            ],
            note=_UNPRICED_OVERNIGHT_COST_NOTE.format(missing_field=missing_field),
        )
