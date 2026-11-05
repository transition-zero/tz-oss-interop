"""Carrying the sidecar records that PyPSA has no attribute for on to the PyPSA sidecar.

A record reaches the Sienna sidecar because Sienna had nowhere to put it. Where PyPSA has
nowhere either, the record travels on unchanged, so a later hop with a home for it can still
read it. Each field that travels records one event, so the report says where it went.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from interop.core.extensions import (
    ExtensionLookup,
    ExtensionRecord,
    RecordT,
    append_extensions,
    get_record_kind,
    names_companion_series,
)
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.sienna_pypsa_translations.mapped_fields import (
    ANNUAL_BOUND_FIELDS,
    FIXED_CHARGE_FIELD,
)
from interop.plugins.shared.sienna_pypsa_translations.reporters import ExtensionRelayReporter
from interop.plugins.shared.sienna_pypsa_translations.reporters.sidecar import (
    RELAYED_BY_YEAR_DERIVATION,
    RELAYED_FIXED_CHARGE_DERIVATION,
)


def relay_records(
    state: State,
    lookup: ExtensionLookup[RecordT],
    names: Iterable[str],
    recorder: ScopedRecorder,
    *,
    partly_mapped: Mapping[str, str] | None = None,
) -> None:
    """Relay the fields of each named record that no mapping maps, with their companion series.

    A field in ``partly_mapped`` also maps in part, so its event takes the derivation that the
    mapping gives it, which says what the network holds.
    """
    partly_mapped = partly_mapped or {}
    stated = [record for record in map(lookup.build_relayed, names) if record.has_any_value()]
    if not stated:
        return
    kind = get_record_kind(type(stated[0]))
    append_extensions(state.destination_extensions, kind, stated)
    reporter = ExtensionRelayReporter(recorder, kind)
    for record in stated:
        for field_name, value in _build_report_values(record).items():
            if field_name in partly_mapped:
                reporter.record_relayed_in_part(
                    record.name, field_name, value, partly_mapped[field_name]
                )
            else:
                reporter.record_relayed(record.name, field_name, value)
    series = state.source_extension_series.get(kind)
    if series is not None and names_companion_series(kind, stated):
        state.destination_extension_series[kind] = series


# The fields that a later step maps in part, with what each relay event says of them.
FIXED_CHARGE_IN_PART: dict[str, str] = {FIXED_CHARGE_FIELD: RELAYED_FIXED_CHARGE_DERIVATION}
GENERATOR_IN_PART: dict[str, str] = {
    **dict.fromkeys(ANNUAL_BOUND_FIELDS, RELAYED_BY_YEAR_DERIVATION),
    **FIXED_CHARGE_IN_PART,
}


def _build_report_values(record: ExtensionRecord) -> dict[str, object]:
    """Each stated field of a record, in the shape that extensions.json writes it."""
    return record.model_dump(mode="json", exclude={"name"}, exclude_none=True, exclude_unset=True)
