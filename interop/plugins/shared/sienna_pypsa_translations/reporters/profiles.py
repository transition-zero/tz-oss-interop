"""The events of a staged Sienna series that the hop leaves off the network."""

from __future__ import annotations

from interop.plugins.shared.sienna_pypsa_translations.reporters._base import SiennaToPypsaReporter

# Stands in for the values of a staged series, which are the numbers rather than one value.
_PROFILE = "profile"


class ProfileReporter(SiennaToPypsaReporter):
    """Records a staged Sienna series left off the network, whatever component owns it.

    Names only its source, so it needs no destination component: the whole point is that
    the values reached no PyPSA column.
    """

    def record_dropped(self, owner_type: str, name: str, series: str, note: str) -> None:
        self._not_mapped(
            sources=[self._source_field(owner_type, name, series, _PROFILE)], note=note
        )
