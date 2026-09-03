"""The files one Sienna system consists of, and the one way a sink writes them.

A system JSON is readable only beside the two companions it names, so the sequence that
writes all three and names two of them in the third lives here rather than in each sink.
"""

from __future__ import annotations

import json
from typing import Any, NamedTuple

from interop.core.pipeline import State
from interop.plugins.shared.extensions_sidecar import WritesExtensionsSidecar
from interop.plugins.shared.sienna_constants import SiennaSchemasSystem
from interop.plugins.sinks.emit_sienna_h5_sidecar import EmitSiennaH5Sidecar
from interop.ports.outbound.filesystem import Location, location_name

SYSTEM_JSON_FILENAME = "system.json"


class SiennaFilePaths(NamedTuple):
    """Where one system and the two companions it names are written."""

    system_json: Location
    h5: Location
    extensions: Location


class WritesSiennaFiles(WritesExtensionsSidecar):
    """The one way a sink writes a system and the two companions it names.

    A mixin for the same reason as ``WritesExtensionsSidecar``: the plugin filesystem lint
    lets a sink hand a params path to ``self.<method>`` and to nothing else.
    """

    def _write_sienna_files(
        self,
        paths: SiennaFilePaths,
        state: State,
        payload: dict[str, Any],
        indent: int,
        sample: str | None = None,
    ) -> None:
        with self._fs.open_write(paths.h5) as stream:
            EmitSiennaH5Sidecar.write_h5(state, stream, sample)
        self._write_extensions_sidecar(paths.extensions, state, indent)
        self._fs.write_bytes(paths.system_json, _serialise(paths, payload, indent))


def _serialise(paths: SiennaFilePaths, payload: dict[str, Any], indent: int) -> bytes:
    """The system JSON, naming its companions by the bare filenames a reader expects."""
    named = {
        **payload,
        SiennaSchemasSystem.TIME_SERIES_STORAGE_FILENAME: location_name(paths.h5),
        SiennaSchemasSystem.EXTENSIONS_FILENAME: location_name(paths.extensions),
    }
    return json.dumps(named, indent=indent, default=str).encode("utf-8")
