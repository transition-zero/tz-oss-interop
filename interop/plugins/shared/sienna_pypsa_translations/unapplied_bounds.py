"""The energy bounds of the sidecar records that the network does not apply.

A PyPSA Link and a PyPSA StorageUnit have no `e_sum_min` or `e_sum_max`, so each energy bound
of a record that became one travels on in the sidecar and binds nothing. A Generator takes only
the annual bounds, so a bound over the horizon binds nothing either. Each bound gets a
NOT_MAPPED event, and one warning for each kind of component names three.
"""

from __future__ import annotations

import logging
from collections.abc import Collection
from typing import NamedTuple

from interop.core.extensions import ActivityExtension, ExtensionKind, ExtensionReader
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.pypsa_constants import (
    PyPSADestinationTable,
    PyPSAGeneratorCol,
    PyPSALinkCol,
    PyPSAStorageUnitCol,
)
from interop.plugins.shared.pypsa_destination import list_destination_names
from interop.plugins.shared.sienna_constants import SiennaTable
from interop.plugins.shared.sienna_pypsa_translations.mapped_fields import (
    ANNUAL_BOUND_FIELDS,
    HORIZON_BOUND_FIELDS,
)
from interop.plugins.shared.sienna_pypsa_translations.mapping import find_source_types
from interop.plugins.shared.sienna_pypsa_translations.reporters import (
    GeneratorReporter,
    LinkReporter,
    StorageUnitReporter,
)
from interop.plugins.shared.warning_text import name_a_few

log = logging.getLogger(__name__)


class _BoundText(NamedTuple):
    """What the report says about the bounds of one kind of component."""

    note: str
    warning: str


_LINK_TEXT = _BoundText(
    note=(
        "a PyPSA Link has no e_sum_min or e_sum_max, so the network does not bound the energy "
        "of the link; extensions.json keeps the bound"
    ),
    warning=(
        "%d energy bound(s) of a link stay in extensions.json and bind nothing, because a PyPSA "
        "Link has no e_sum_min or e_sum_max: %s"
    ),
)
_STORAGE_TEXT = _BoundText(
    note=(
        "a PyPSA StorageUnit has no e_sum_min or e_sum_max, so the network does not bound the "
        "energy of the unit; extensions.json keeps the bound"
    ),
    warning=(
        "%d energy bound(s) of a storage unit stay in extensions.json and bind nothing, because "
        "a PyPSA StorageUnit has no e_sum_min or e_sum_max: %s"
    ),
)
_HORIZON_TEXT = _BoundText(
    note=(
        "this hop maps only the annual bounds onto e_sum_min and e_sum_max, so the bound over "
        "the horizon binds nothing; extensions.json keeps it"
    ),
    warning=(
        "%d energy bound(s) over the horizon of a generator stay in extensions.json and bind "
        "nothing, because this hop maps only the annual bounds onto e_sum_min and e_sum_max: %s"
    ),
)
_ALL_BOUND_FIELDS = ANNUAL_BOUND_FIELDS | HORIZON_BOUND_FIELDS


class _BoundOwner(NamedTuple):
    """A record whose bounds the network does not apply, and the source type the report names."""

    source_type: str
    record: ActivityExtension


class _BoundGroup(NamedTuple):
    """The records of one kind of component, the bound fields to check, and the report text."""

    reporter: LinkReporter | StorageUnitReporter | GeneratorReporter
    owners: list[_BoundOwner]
    fields: Collection[str]
    text: _BoundText


def report_unapplied_bounds(
    state: State, reader: ExtensionReader, recorder: ScopedRecorder
) -> None:
    """Record each energy bound that the network does not apply, and warn once for each kind."""
    _report_group(_build_link_group(state, reader, recorder))
    _report_group(_build_storage_group(state, reader, recorder))
    _report_group(_build_horizon_group(state, reader, recorder))


def _report_group(group: _BoundGroup) -> None:
    bounds = [
        (owner, field_name)
        for owner in group.owners
        for field_name in sorted(group.fields)
        if getattr(owner.record, field_name) not in (None, {})
    ]
    for owner, field_name in bounds:
        group.reporter.record_bound_unapplied(
            owner.source_type, owner.record.name, field_name, group.text.note
        )
    if bounds:
        labels = sorted(f"{owner.record.name}.{field_name}" for owner, field_name in bounds)
        log.warning(group.text.warning, len(labels), name_a_few(labels))


def _build_link_group(
    state: State, reader: ExtensionReader, recorder: ScopedRecorder
) -> _BoundGroup:
    """The records of the TwoTerminalGenericHVDCLines and of the conversions that became Links."""
    links = set(list_destination_names(state, PyPSADestinationTable.LINKS, PyPSALinkCol.NAME))
    line_types = find_source_types(state, SiennaTable.LINKS) or {}
    lines = links & set(line_types)
    owners = [
        *(
            _BoundOwner(line_types[record.name], record)
            for record in reader.read(ExtensionKind.CONTROLLABLE_LINE).list_records()
            if record.name in lines
        ),
        *(
            _BoundOwner(ExtensionKind.CONVERSION, record)
            for record in reader.read(ExtensionKind.CONVERSION).list_records()
            if record.name in links - lines
        ),
    ]
    return _BoundGroup(LinkReporter(recorder), owners, _ALL_BOUND_FIELDS, _LINK_TEXT)


def _build_storage_group(
    state: State, reader: ExtensionReader, recorder: ScopedRecorder
) -> _BoundGroup:
    """The storage and the generator records of the StorageUnits, as a hydro unit has both."""
    units = set(
        list_destination_names(state, PyPSADestinationTable.STORAGE_UNITS, PyPSAStorageUnitCol.NAME)
    )
    types = {
        **(find_source_types(state, SiennaTable.GENERATORS) or {}),
        **(find_source_types(state, SiennaTable.STORAGE) or {}),
    }
    records = [
        *reader.read(ExtensionKind.STORAGE).list_records(),
        *reader.read(ExtensionKind.GENERATOR).list_records(),
    ]
    owners = [
        _BoundOwner(types.get(record.name, ExtensionKind.STORAGE), record)
        for record in records
        if record.name in units
    ]
    return _BoundGroup(StorageUnitReporter(recorder), owners, _ALL_BOUND_FIELDS, _STORAGE_TEXT)


def _build_horizon_group(
    state: State, reader: ExtensionReader, recorder: ScopedRecorder
) -> _BoundGroup:
    """The generator records of the Generators, whose bounds over the horizon bind nothing."""
    generators = set(
        list_destination_names(state, PyPSADestinationTable.GENERATORS, PyPSAGeneratorCol.NAME)
    )
    types = find_source_types(state, SiennaTable.GENERATORS) or {}
    owners = [
        _BoundOwner(types.get(record.name, ExtensionKind.GENERATOR), record)
        for record in reader.read(ExtensionKind.GENERATOR).list_records()
        if record.name in generators
    ]
    return _BoundGroup(GeneratorReporter(recorder), owners, HORIZON_BOUND_FIELDS, _HORIZON_TEXT)
