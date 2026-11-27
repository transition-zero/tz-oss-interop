"""The canonical parameter tables of the storages, and the events of each value.

Each value of the group names the parameter that holds it and the keys that name it, so one
writer serves them all: it groups the values by parameter and writes one row for each year of
the model where the parameter takes a year.

A value that equals the default of its parameter needs no row, because OSeMOSYS reads the
default where a model states nothing. So a storage that may empty writes no `MinStorageCharge`
row.
"""

from __future__ import annotations

from collections.abc import Sequence

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.osemosys_canonical.constants import REGION, YEAR
from interop.plugins.shared.osemosys_canonical.schema import load_canonical_schema
from interop.plugins.shared.sienna_osemosys_translations.constants import NAME_SEPARATOR
from interop.plugins.shared.sienna_osemosys_translations.destination import (
    ParameterRows,
    append_parameter_rows,
    build_rows_over_years,
)
from interop.plugins.shared.sienna_osemosys_translations.events import (
    build_derived,
    build_not_mapped,
    build_osemosys_parameter,
)
from interop.plugins.shared.sienna_osemosys_translations.storage_members import StorageValue
from interop.plugins.shared.sienna_osemosys_translations.storages import StorageSources


def set_storage_tables(
    state: State, sources: StorageSources, years: Sequence[int], recorder: ScopedRecorder
) -> None:
    """Write the energy of each storage, the two technologies that move it, and their flows."""
    for parameter in _list_parameters(sources):
        stated = [value for value in sources.values if _is_stated(value, parameter)]
        _append_rows(state, parameter, _list_rows(stated, years))
        _record_values(stated, recorder)
    _report_absent(sources, recorder)


def _list_parameters(sources: StorageSources) -> list[str]:
    """Each parameter that a value of the group fills, in the order that the values state it."""
    return list(dict.fromkeys(value.parameter for value in sources.values))


def _is_stated(value: StorageValue, parameter: str) -> bool:
    """Whether the value fills `parameter` with something that its default does not hold."""
    if value.parameter != parameter:
        return False
    default = load_canonical_schema().parameters[parameter].default
    return default is None or value.value != default


def _list_rows(stated: Sequence[StorageValue], years: Sequence[int]) -> ParameterRows:
    return [
        row
        for value in stated
        for row in build_rows_over_years(value.parameter, value.keys, value.value, years)
    ]


def _record_values(stated: Sequence[StorageValue], recorder: ScopedRecorder) -> None:
    """One event for each value, and not one for each year that the value holds in."""
    for value in stated:
        destination = build_osemosys_parameter(
            value.parameter, _build_name(value), value.value, value.unit
        )
        recorder.append(build_derived([value.source], [destination], value.derivation))


def _build_name(value: StorageValue) -> str:
    """A value is named by its region and by each other key that the schema names."""
    keys = [key for column, key in value.keys.items() if column not in (REGION, YEAR)]
    return NAME_SEPARATOR.join([value.keys[REGION], *keys])


def _report_absent(sources: StorageSources, recorder: ScopedRecorder) -> None:
    """One `NOT_MAPPED` event for each value of the group that no Sienna field states."""
    for absent in sources.absent:
        recorder.append(build_not_mapped([absent.source], absent.note))


def _append_rows(state: State, parameter: str, rows: ParameterRows) -> None:
    if rows:
        append_parameter_rows(state, parameter, rows)
