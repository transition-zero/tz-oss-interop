"""A project-local sink that writes the Sienna system as one flat CSV per type.

The pipeline's intermediate `destination_tables` hold one polars frame per Sienna
component type, with nested struct columns (for example `operation_cost` or
`active_power_limits`). This sink flattens those structs into dotted column names
(`active_power_limits.max`, ...) and writes one CSV per component type. Time
series live outside `destination_tables` (in the HDF5 companion of the JSON
sink), so the CSVs here are the static components only.
"""

from pathlib import Path
from typing import ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import Sink, State
from interop.plugins.shared.sienna_constants import SiennaComponent
from interop.plugins.shared.staged_samples import ENSEMBLE_SAMPLES_TABLE
from interop.ports.outbound.filesystem import FilesystemPort, OutputDirectory

# The tables in destination_tables that are no Sienna component in their own right.
_AUX_TABLES = frozenset({SiennaComponent.TIME_SERIES_ASSOCIATION, ENSEMBLE_SAMPLES_TABLE})


class EmitSiennaCsvParams(BaseModel):
    output_dir: OutputDirectory = Path("outputs/sienna_csv")


class EmitSiennaCsv(Sink):
    name: ClassVar[str] = "emit_sienna_csv"
    params_schema: ClassVar[type[BaseModel] | None] = EmitSiennaCsvParams

    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def write(self, state: State, params: BaseModel | None) -> None:
        if not isinstance(params, EmitSiennaCsvParams):
            raise TypeError(
                f"{type(self).__name__} requires {EmitSiennaCsvParams.__name__}, "
                f"got {type(params).__name__}"
            )
        for component, table in state.destination_tables.items():
            if component in _AUX_TABLES or table.height == 0:
                continue
            csv = _flatten_structs(table).write_csv()
            self._fs.write_bytes(params.output_dir / f"{component}.csv", csv.encode("utf-8"))


def _flatten_structs(table: pl.DataFrame) -> pl.DataFrame:
    """Recursively unnest struct columns into dotted column names until the frame is flat."""
    while True:
        struct_columns = [
            name for name, dtype in table.schema.items() if isinstance(dtype, pl.Struct)
        ]
        if not struct_columns:
            return table
        for name in struct_columns:
            dtype = table.schema[name]
            assert isinstance(dtype, pl.Struct)
            table = table.with_columns(
                pl.col(name).struct.field(field.name).alias(f"{name}.{field.name}")
                for field in dtype.fields
            ).drop(name)
