"""Write one Sienna system per replication a staged PyPSA ensemble carries.

PowerSimulations solves no Monte Carlo forecast, so an ensemble is many systems rather than
one system holding many samples. Every replication shares its components and its time-series
association rows, and differs only in the values its HDF5 companion holds. Each replication
gets a directory of its own, so its system.json names its companions by the same bare
filenames a single-system translation writes.
"""

from __future__ import annotations

import logging
from typing import ClassVar

from pydantic import BaseModel, Field

from interop.core.pipeline import Sink, State
from interop.plugins.shared.sienna_constants import SiennaCompanionFilename
from interop.plugins.shared.staged_samples import samples_to_write
from interop.plugins.sinks._sienna_files import (
    SYSTEM_JSON_FILENAME,
    SiennaFilePaths,
    WritesSiennaFiles,
)
from interop.plugins.sinks.emit_sienna_system_json import EmitSiennaSystemJson
from interop.ports.outbound.filesystem import FilesystemPort, OutputDirectory

log = logging.getLogger(__name__)

_NO_REPLICATIONS = (
    "the translation recorded no replication to write, so the ensemble holds no system: "
    "either no staged profile names a replication, in which case the source is reading a "
    "model that is not pre-sampled, or the mapping step left every replication out and says "
    "which and why"
)


class EmitSiennaFilesEnsembleParams(BaseModel):
    output_dir: OutputDirectory = Field(
        description=(
            "directory to hold the ensemble: one subdirectory of Sienna files per replication"
        )
    )
    subdirectory_template: str = Field(
        default="{sample}",
        description="names each replication's directory; {sample} becomes the replication label",
    )
    indent: int = Field(default=2, description="JSON indent width")

    def replication_paths(self, sample: str) -> SiennaFilePaths:
        """The three files one replication's own directory holds."""
        directory = self.output_dir / self.subdirectory_template.format(sample=sample)
        return SiennaFilePaths(
            system_json=directory / SYSTEM_JSON_FILENAME,
            h5=directory / SiennaCompanionFilename.TIME_SERIES_H5,
            extensions=directory / SiennaCompanionFilename.EXTENSIONS_JSON,
        )


class EmitSiennaFilesEnsemble(WritesSiennaFiles, Sink):
    name: ClassVar[str] = "emit_sienna_files_ensemble"
    params_schema: ClassVar[type[BaseModel] | None] = EmitSiennaFilesEnsembleParams

    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def write(self, state: State, params: BaseModel | None) -> None:
        if not isinstance(params, EmitSiennaFilesEnsembleParams):
            raise TypeError(
                f"{type(self).__name__} requires {EmitSiennaFilesEnsembleParams.__name__}, "
                f"got {type(params).__name__}"
            )
        samples = samples_to_write(state)
        if not samples:
            log.warning(_NO_REPLICATIONS)
            return
        # Every field of the system JSON is the same in each replication, the time-series
        # UUIDs among them, so the whole document is built once and written many times.
        payload = EmitSiennaSystemJson.build_payload(state)
        for sample in samples:
            self._write_sienna_files(
                params.replication_paths(sample), state, payload, params.indent, sample
            )
