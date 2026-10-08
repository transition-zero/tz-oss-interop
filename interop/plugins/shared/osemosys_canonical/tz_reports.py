"""How the TZ-format source names a part of a model.json, and reports the parts it leaves out."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import NamedTuple

from interop.core.reporting import EventRecorder
from interop.plugins.shared.tz_osemosys_fields import TzOwner
from interop.plugins.shared.warning_text import name_a_few

log = logging.getLogger(__name__)

_PATH_SEPARATOR = "."


class TzPath(NamedTuple):
    """The owner of an object or a field, and its name within the owner, outermost part first."""

    owner: TzOwner
    name: str

    @property
    def text(self) -> str:
        return _PATH_SEPARATOR.join(part for part in (self.owner, self.name) if part)


def build_tz_name(*parts: str) -> str:
    return _PATH_SEPARATOR.join(part for part in parts if part)


class TzPathReport(NamedTuple):
    """The event that one reason records for each part, and the words that complete the warning
    "N TZ-format <reason>, so the raw stage leaves each out"."""

    record: Callable[[EventRecorder, TzOwner, str, str], None]
    reason: str


def report_tz_paths(
    report: TzPathReport, notes: Mapping[TzPath, str], recorder: EventRecorder
) -> None:
    for path, note in notes.items():
        report.record(recorder, path.owner, path.name, note)
    if notes:
        log.warning(
            "%d TZ-format %s, so the raw stage leaves each out: %s",
            len(notes),
            report.reason,
            name_a_few(path.text for path in notes),
        )
