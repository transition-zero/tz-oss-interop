from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, Field, ValidationError

from interop.core.pipeline import StagedSource
from interop.plugins.shared.osemosys_canonical.canonical_source import OsemosysCanonicalSource
from interop.plugins.shared.osemosys_canonical.raw_stage import RawTables
from interop.plugins.shared.osemosys_canonical.tz_document import TzModelDocument
from interop.plugins.shared.osemosys_canonical.tz_raw_tables import build_tz_raw_tables
from interop.ports.errors import MissingInputError, UserInputError
from interop.ports.outbound.filesystem import InputFile, Location

_MODEL_DESCRIPTION = "TZ-format model.json"


class StageTzOsemosysJsonParams(BaseModel):
    model_json_path: InputFile = Field(
        description="the model.json that tz-osemosys writes for one model"
    )


# The plugin inheritance lint follows bases in this directory only, so name StagedSource too.
class StageTzOsemosysJson(OsemosysCanonicalSource[StageTzOsemosysJsonParams], StagedSource):
    name: ClassVar[str] = "stage_tz_osemosys_json"
    params_schema: ClassVar[type[BaseModel] | None] = StageTzOsemosysJsonParams
    prefix: ClassVar[str] = "tz-osemosys"

    def _build_raw_tables(self, params: StageTzOsemosysJsonParams) -> RawTables:
        document = self._read_document(params.model_json_path)
        return build_tz_raw_tables(document, self._recorder)

    def _read_document(self, model_json_path: Location) -> TzModelDocument:
        if not self._fs.can_read(model_json_path):
            raise MissingInputError(self.name, _MODEL_DESCRIPTION, f"{model_json_path}")
        try:
            return TzModelDocument.model_validate_json(self._fs.read_bytes(model_json_path))
        except ValidationError as exc:
            raise UserInputError(
                f"The file at {model_json_path} is not a {_MODEL_DESCRIPTION}:\n{exc}"
            ) from exc
