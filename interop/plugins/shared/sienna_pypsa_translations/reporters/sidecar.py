"""The events of a sidecar record that travels on to the PyPSA sidecar."""

from __future__ import annotations

from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import EXTENSIONS_PREFIX
from interop.plugins.shared.sienna_pypsa_translations.reporters._base import SiennaToPypsaReporter

_RELAYED_DERIVATION = "relayed unchanged to extensions.json, as PyPSA has no attribute for it"
RELAYED_BY_YEAR_DERIVATION = (
    "relayed unchanged to extensions.json with every year that it states, as a PyPSA Generator "
    "holds the bound of one year at most"
)
RELAYED_TO_LINK_DERIVATION = (
    "relayed unchanged to extensions.json; where the network holds the bus of each fuel of the "
    "plant, the plant becomes a PyPSA Link that also maps it"
)


class ExtensionRelayReporter(SiennaToPypsaReporter):
    """Records each field of a sidecar record that the hop carries on to the PyPSA sidecar."""

    def __init__(self, recorder: ScopedRecorder, kind: str) -> None:
        super().__init__(recorder)
        self.destination_component = kind

    def record_relayed(
        self, name: str, field_name: str, value: object, derivation: str = _RELAYED_DERIVATION
    ) -> None:
        """A field that travels on unchanged; a field that also maps in part names how."""
        attribute = f"{EXTENSIONS_PREFIX}{field_name}"
        self._derived(
            sources=[self._source_field(self.destination_component, name, attribute, value)],
            destinations=[self._destination(name, attribute, value)],
            derivation=derivation,
        )
