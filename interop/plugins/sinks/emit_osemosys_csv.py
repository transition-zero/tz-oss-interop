"""Write the canonical OSeMOSYS stage as an otoole CSV model.

The model is a directory of CSV files, the otoole config YAML that declares them, and the
mappings file that states the units of the values. GNU MathProg refuses a datafile that sets a
parameter that its model file does not declare, so the written model holds the core OSeMOSYS
parameter set unless the run asks for every parameter.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, Field

from interop.core.pipeline import Sink, State
from interop.plugins.shared.osemosys_canonical.canonical_stage import (
    list_destination_canonical_tables,
)
from interop.plugins.shared.osemosys_canonical.mappings import build_mappings_document
from interop.plugins.shared.osemosys_canonical.otoole_config import (
    CSV_SUFFIX,
    build_otoole_config,
)
from interop.plugins.shared.osemosys_canonical.otoole_tables import (
    CORE_ORIGINS,
    OtooleFile,
    OtooleModel,
    build_otoole_model,
    build_schema_origins,
)
from interop.plugins.shared.warning_text import name_a_few
from interop.ports.outbound.filesystem import FilesystemPort, Location, OutputDirectory

log = logging.getLogger(__name__)

_LEFT_OUT_WARNING = (
    "%d parameter(s) come from outside the core OSeMOSYS parameter set, so the written model "
    "declares none of them: %s"
)


class EmitOsemosysCsvParams(BaseModel):
    output_config_path: Location = Field(
        description="the otoole config YAML that declares each set and parameter of the model"
    )
    output_csv_dir: OutputDirectory = Field(
        description="the directory to hold one CSV file for each set and parameter"
    )
    output_mappings_path: Location = Field(
        description="the mappings file that states the units of the written values"
    )
    wants_every_parameter: bool = Field(
        default=False,
        description=(
            "write every parameter of the canonical schema, and not only the ones that "
            "OSeMOSYS v1.0.1 declares"
        ),
    )


class EmitOsemosysCsv(Sink):
    name: ClassVar[str] = "emit_osemosys_csv"
    params_schema: ClassVar[type[BaseModel] | None] = EmitOsemosysCsvParams

    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def write(self, state: State, params: BaseModel | None) -> None:
        if not isinstance(params, EmitOsemosysCsvParams):
            raise TypeError(
                f"{type(self).__name__} requires {EmitOsemosysCsvParams.__name__}, "
                f"got {type(params).__name__}"
            )
        origins = build_schema_origins() if params.wants_every_parameter else CORE_ORIGINS
        tables = list_destination_canonical_tables(state)
        self._write_model(params, build_otoole_model(tables, origins))

    def _write_model(self, params: EmitOsemosysCsvParams, model: OtooleModel) -> None:
        for written in model.files:
            self._write_csv_file(params.output_csv_dir, written)
        entries = [written.entry for written in model.files]
        self._fs.write_bytes(params.output_config_path, build_otoole_config(entries))
        self._fs.write_bytes(params.output_mappings_path, build_mappings_document(model.units))
        _warn_left_out_parameters(model.left_out)

    def _write_csv_file(self, csv_dir: Path, written: OtooleFile) -> None:
        with self._fs.open_write(csv_dir / f"{written.stem}{CSV_SUFFIX}") as stream:
            written.table.sink_csv(stream)


def _warn_left_out_parameters(left_out: dict[str, str]) -> None:
    if not left_out:
        return
    labels = [f"{name} ({origin})" for name, origin in sorted(left_out.items())]
    log.warning(_LEFT_OUT_WARNING, len(labels), name_a_few(labels))
