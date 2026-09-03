"""Reading the extensions sidecar a previous hop wrote.

Every source takes the file as an optional input: only this translator writes one, so a
model that came from anywhere else does not have it, and an absent sidecar behaves as a
model where no component had a record. The source opens the file through its own
``FilesystemPort`` and hands the stream here, so no path leaves the port.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import IO, ClassVar

import polars as pl

from interop.core.extensions import (
    ExtensionKind,
    StagedExtensions,
    StagedExtensionSeries,
    build_extensions,
    companion_filename,
    dump_extensions,
    names_companion_series,
    parse_extensions,
    stage_extensions,
)
from interop.core.pipeline import State
from interop.ports.errors import MissingInputError
from interop.ports.outbound.filesystem import FilesystemPort, Location


def read_extensions_sidecar(sidecar: IO[bytes]) -> StagedExtensions:
    """The records the sidecar states, keyed by kind."""
    return stage_extensions(parse_extensions(json.load(sidecar)))


@dataclass(frozen=True)
class ExtensionsPayload:
    """Everything a sidecar write consists of, decided in one place.

    A sink may hand a params path only to its own ``FilesystemPort`` (the plugin filesystem
    lint), so the writing itself stays in the sink. What the document says, and which
    companions the records point at, are decided here so two sinks cannot drift: any sink
    holding a payload has the companions in hand and cannot write the sidecar without them.
    """

    document: bytes
    companions: dict[str, pl.LazyFrame]


def extensions_payload(state: State, indent: int) -> ExtensionsPayload:
    """The sidecar bytes, and the companion series each keyed by its filename."""
    document = build_extensions(state.destination_extensions)
    companions = {
        companion_filename(kind): series
        for kind, series in state.destination_extension_series.items()
    }
    return ExtensionsPayload(
        document=dump_extensions(document, indent).encode("utf-8"), companions=companions
    )


class StagesExtensionsSidecar:
    """The one way a source stages the sidecar a previous hop wrote.

    A mixin for the same reason as the writer below: a source may hand a params path to
    ``self._fs.<method>`` or ``self.<method>`` and nothing else, so the shared step cannot
    be a free function taking the path. Absent means the hop before wrote none; named but
    unreadable is an error, and the same one a required input gives.
    """

    _fs: FilesystemPort
    name: ClassVar[str]

    def _stage_extensions_sidecar(self, sidecar_path: Location | None) -> StagedExtensions:
        if sidecar_path is None:
            return {}
        if not self._fs.can_read(sidecar_path):
            raise MissingInputError(self.name, "extensions sidecar", f"{sidecar_path}")
        with self._fs.open_read(sidecar_path) as sidecar:
            return read_extensions_sidecar(sidecar)

    def _stage_extension_companions(
        self, sidecar_path: Location | None, staged: StagedExtensions
    ) -> StagedExtensionSeries:
        """The companion parquet each staged kind names, beside the sidecar that names it.

        A kind whose records state only scalars names no companion, so nothing is read for
        it. A companion the sidecar names but that is not there is an error: the pair was
        written together, so one without the other is a broken input rather than an absence.
        """
        if sidecar_path is None:
            return {}
        return {
            kind: self._read_companion(sidecar_path, kind)
            for kind, records in staged.items()
            if names_companion_series(kind, records)
        }

    def _read_companion(self, sidecar_path: Location, kind: ExtensionKind) -> pl.LazyFrame:
        companion_path = self._fs.resolve(sidecar_path, companion_filename(kind))
        if not self._fs.can_read(companion_path):
            raise MissingInputError(self.name, f"{kind} companion series", f"{companion_path}")
        with self._fs.open_read(companion_path) as companion:
            return pl.read_parquet(companion).lazy()


class WritesExtensionsSidecar:
    """The one way a sink writes the sidecar and the companions its records point at.

    A mixin rather than a free function because the plugin filesystem lint lets a sink hand
    a params path to ``self.<method>`` but not to anything else; that is what keeps the two
    sinks from drifting apart on which files a sidecar write consists of.
    """

    _fs: FilesystemPort

    def _write_extensions_sidecar(self, sidecar_path: Location, state: State, indent: int) -> None:
        payload = extensions_payload(state, indent)
        self._fs.write_bytes(sidecar_path, payload.document)
        for filename, series in payload.companions.items():
            with self._fs.open_write(self._fs.resolve(sidecar_path, filename)) as stream:
                series.collect(engine="streaming").write_parquet(stream)
