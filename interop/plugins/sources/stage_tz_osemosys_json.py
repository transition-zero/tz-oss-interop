"""Stage an OSeMOSYS model in the TZ format, one model.json, into the canonical OSeMOSYS stage."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import polars as pl
from pydantic import BaseModel, Field, ValidationError

from interop.core.pipeline import StagedSource, State
from interop.core.reporting import EventRecorder
from interop.plugins.shared.osemosys_canonical.canonical_stage import build_canonical_stage
from interop.plugins.shared.osemosys_canonical.constants import VALUE_COL
from interop.plugins.shared.osemosys_canonical.mappings import OsemosysCanonicalMappings
from interop.plugins.shared.osemosys_canonical.raw_stage import RawStage, write_raw_stage
from interop.plugins.shared.osemosys_canonical.tz_document import (
    TzModelDocument,
    list_tz_objects,
    list_tz_sets,
    report_unknown_fields,
)
from interop.plugins.shared.osemosys_canonical.tz_tables import (
    build_tz_declarations,
    map_tz_parameter_tables,
)
from interop.ports.errors import MissingInputError, UserInputError
from interop.ports.outbound.filesystem import FilesystemPort, InputFile, Location

_MODEL_DESCRIPTION = "TZ-format model.json"


class StageTzOsemosysJsonParams(BaseModel):
    model_json_path: InputFile = Field(
        description="the model.json that tz-osemosys writes for one model"
    )


class StageTzOsemosysJson(StagedSource):
    name: ClassVar[str] = "stage_tz_osemosys_json"
    params_schema: ClassVar[type[BaseModel] | None] = StageTzOsemosysJsonParams
    prefix: ClassVar[str] = "tz-osemosys"

    def __init__(
        self,
        fs: FilesystemPort,
        osemosys_mappings: OsemosysCanonicalMappings,
        recorder: EventRecorder,
    ) -> None:
        self._fs = fs
        self._mappings = osemosys_mappings
        self._recorder = recorder

    def load_into_state(self, params: BaseModel | None, staging_dir: Path) -> State:
        if not isinstance(params, StageTzOsemosysJsonParams):
            raise TypeError(
                f"{type(self).__name__} requires {StageTzOsemosysJsonParams.__name__}, "
                f"got {type(params).__name__}"
            )
        document = self._read_document(params.model_json_path)
        raw = self._stage_raw(document, staging_dir)
        return build_canonical_stage(raw, self._mappings.osemosys, self._recorder, staging_dir)

    def _read_document(self, model_json_path: Location) -> TzModelDocument:
        if not self._fs.can_read(model_json_path):
            raise MissingInputError(self.name, _MODEL_DESCRIPTION, f"{model_json_path}")
        try:
            return TzModelDocument.model_validate_json(self._fs.read_bytes(model_json_path))
        except ValidationError as exc:
            raise UserInputError(
                f"The file at {model_json_path} is not a {_MODEL_DESCRIPTION}:\n{exc}"
            ) from exc

    def _stage_raw(self, document: TzModelDocument, staging_dir: Path) -> RawStage:
        objects = list_tz_objects(document)
        report_unknown_fields(objects, self._recorder)
        sets = list_tz_sets(document, objects)
        return write_raw_stage(
            sets={name: _build_set_table(members) for name, members in sets.items()},
            parameters=map_tz_parameter_tables(objects, sets, self._recorder),
            declarations=build_tz_declarations(),
            staging_dir=staging_dir,
        )


def _build_set_table(members: list[str]) -> pl.DataFrame:
    return pl.DataFrame({VALUE_COL: members}, schema={VALUE_COL: pl.Utf8})
