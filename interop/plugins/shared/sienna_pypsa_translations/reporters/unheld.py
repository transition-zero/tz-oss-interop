"""The events of a part of a Sienna system that a PyPSA network cannot hold."""

from __future__ import annotations

from interop.plugins.shared.sienna_pypsa_translations.reporters._base import SiennaToPypsaReporter

_NO_COUNTERPART_NOTE = (
    "PyPSA has no component of the type {sienna_type}, so the network leaves it out"
)
_RESERVOIR_NOTE = (
    "PyPSA holds a reservoir only on a StorageUnit, so the HydroReservoir is left out; a hydro "
    "StorageUnit reads its reservoir from the storage record of extensions.json, where one exists"
)
_RESERVOIR_VALUE_NOTE = "the HydroReservoir is left out, so no StorageUnit reads its {attribute}"
_SERVICE_MEMBER_NOTE = (
    "PyPSA has no service of the type {service_type}, so the contribution to {service_name} "
    "is left out"
)
_ATTRIBUTE_NOTE = (
    "PyPSA has no attribute of the type {attribute_type}, so the network leaves it out"
)
# Stands in for the values of a staged series, which are the numbers rather than one value.
_PROFILE = "profile"


class UnheldReporter(SiennaToPypsaReporter):
    """Records each part of a Sienna system that no PyPSA component holds.

    Names only its source, because the whole point is that the value reached no PyPSA column.
    """

    def record_component_skipped(self, sienna_type: str, name: str) -> None:
        self._skipped(
            sources=[self._source_field(sienna_type, name, None, None)],
            note=_NO_COUNTERPART_NOTE.format(sienna_type=sienna_type),
        )

    def record_reservoir_skipped(self, sienna_type: str, name: str) -> None:
        self._skipped(
            sources=[self._source_field(sienna_type, name, None, None)], note=_RESERVOIR_NOTE
        )

    def record_reservoir_value(
        self, sienna_type: str, name: str, attribute: str, value: object
    ) -> None:
        self._not_mapped(
            sources=[self._source_field(sienna_type, name, attribute, value)],
            note=_RESERVOIR_VALUE_NOTE.format(attribute=attribute),
        )

    def record_reservoir_series(self, sienna_type: str, name: str, series: str) -> None:
        self._not_mapped(
            sources=[self._source_field(sienna_type, name, series, _PROFILE)],
            note=_RESERVOIR_VALUE_NOTE.format(attribute=series),
        )

    def record_service_member(
        self, member_type: str, member: str, service_type: str, service_name: str
    ) -> None:
        self._not_mapped(
            sources=[self._source_field(member_type, member, service_type, service_name)],
            note=_SERVICE_MEMBER_NOTE.format(service_type=service_type, service_name=service_name),
        )

    def record_attribute(self, owner_type: str, owner: str, attribute_type: str) -> None:
        self._not_mapped(
            sources=[self._source_field(owner_type, owner, attribute_type, None)],
            note=_ATTRIBUTE_NOTE.format(attribute_type=attribute_type),
        )
