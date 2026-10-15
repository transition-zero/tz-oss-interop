"""The files one Sienna system consists of, and the one way a sink writes them.

A system JSON is readable only beside the HDF5 companion it names, and its extensions
sidecar sits beside it, so the sequence that writes all three lives here rather than in
each sink. The SDK writes the document itself.
"""

from __future__ import annotations

import tempfile
import warnings
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

from power_openapi_models.document import (
    PortfolioDocument,
    SystemDocument,
    write_document,
    write_portfolio_document,
)

from interop.core.pipeline import State
from interop.plugins.shared.extensions_sidecar import WritesExtensionsSidecar
from interop.plugins.shared.sienna_constants import SiennaSchemasSystem
from interop.plugins.sinks.emit_sienna_h5_sidecar import EmitSiennaH5Sidecar
from interop.ports.outbound.filesystem import Location, location_name

SYSTEM_JSON_FILENAME = "system.json"
_SCRATCH_FILENAME = "document.json"


class SiennaFilePaths(NamedTuple):
    """Where one system and the two companions it names are written."""

    system_json: Location
    h5: Location
    extensions: Location


class WritesSiennaFiles(WritesExtensionsSidecar):
    """The one way a sink writes a system and its two companions.

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
        self._fs.write_bytes(
            paths.system_json,
            serialise_system_document(payload, location_name(paths.h5), indent),
        )


def validate_refs(ref_col: str, needed: list[str], available: set[str], context: str) -> None:
    missing = set(needed) - available
    if missing:
        raise ValueError(
            f"{context}: {len(missing)} reference(s) in {ref_col!r} "
            f"not found in parent table: {sorted(missing)}"
        )


def serialise_system_document(
    payload: dict[str, Any], time_series_storage_file: str | None, indent: int
) -> bytes:
    """The system document as the SDK writes it: stamped, with its keys sorted.

    The association rows do not follow the SDK model yet. ``model_construct`` skips the
    validation they would fail, and the warning that the SDK serialiser raises for them is
    dropped.
    """
    document = SystemDocument.model_construct(
        components=payload[SiennaSchemasSystem.COMPONENTS],
        supplemental_attributes=[],
        supplemental_attribute_associations=[],
        plant_associations=[],
        combined_cycle_associations=[],
        service_associations=[],
        time_series_associations=payload[SiennaSchemasSystem.TIME_SERIES_ASSOCIATIONS],
        time_series_storage_file=time_series_storage_file,
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        return _read_written(lambda target: write_document(document, target, indent=indent))


def serialise_portfolio_document(payload: dict[str, Any], indent: int) -> bytes:
    """The portfolio document as the SDK writes it: validated, stamped, with its keys sorted."""
    document = PortfolioDocument(**payload)
    return _read_written(lambda target: write_portfolio_document(document, target, indent=indent))


def _read_written(write: Callable[[Path], None]) -> bytes:
    """Run an SDK writer into a scratch file and return what it wrote.

    The SDK writers take a path. A sink hands its output location to the filesystem port
    and to nothing else, so the bytes leave through ``self._fs``.
    """
    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory) / _SCRATCH_FILENAME
        write(target)
        return target.read_bytes()
