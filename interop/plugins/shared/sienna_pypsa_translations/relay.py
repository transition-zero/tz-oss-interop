"""Carrying the sidecar records that PyPSA has no attribute for on to the PyPSA sidecar.

A record reaches the Sienna sidecar because Sienna had nowhere to put it. Where PyPSA has
nowhere either, the record travels on unchanged, so a later hop with a home for it can still
read it. Each field that travels records one event, so the report says where it went.
"""

from __future__ import annotations

from collections.abc import Sequence

from interop.core.extensions import (
    ExtensionKind,
    ExtensionRecord,
    append_extensions,
    build_stated_fields,
    names_companion_series,
)
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.sienna_pypsa_translations.reporters import ExtensionRelayReporter


def relay_records(
    state: State,
    kind: ExtensionKind,
    records: Sequence[ExtensionRecord],
    recorder: ScopedRecorder,
) -> None:
    """Add each record that states a field to the PyPSA sidecar, and record each field.

    A record that names a companion parquet states no value of its own, so the series
    travels with it.
    """
    stated = [record for record in records if record.has_any_value()]
    if not stated:
        return
    append_extensions(state.destination_extensions, kind, stated)
    reporter = ExtensionRelayReporter(recorder, kind)
    for record in stated:
        for field_name, value in build_stated_fields(record).items():
            reporter.record_relayed(record.name, field_name, _shown(value))
    series = state.source_extension_series.get(kind)
    if series is not None and names_companion_series(kind, stated):
        state.destination_extension_series[kind] = series


def _shown(value: object) -> object:
    """The value the report shows: a number, a string or a flag, and nothing longer."""
    return value if isinstance(value, str | int | float | bool) else None
