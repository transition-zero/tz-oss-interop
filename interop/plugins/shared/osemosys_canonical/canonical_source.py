from __future__ import annotations

from pathlib import Path
from typing import Generic, TypeVar, cast

from pydantic import BaseModel

from interop.core.pipeline import StagedSource, State
from interop.core.reporting import EventRecorder
from interop.plugins.shared.osemosys_canonical.canonical_stage import build_canonical_stage
from interop.plugins.shared.osemosys_canonical.mappings import OsemosysCanonicalMappings
from interop.plugins.shared.osemosys_canonical.raw_stage import RawTables, write_raw_stage
from interop.plugins.shared.osemosys_canonical.raw_values import normalise_raw_tables
from interop.ports.outbound.filesystem import FilesystemPort

Params = TypeVar("Params", bound=BaseModel)


class OsemosysCanonicalSource(StagedSource, Generic[Params]):
    """A source of the canonical OSeMOSYS stage; a subclass reads one file format into raw
    tables."""

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
        raw_tables = self._build_raw_tables(self._require_params(params))
        raw = write_raw_stage(normalise_raw_tables(raw_tables, self._recorder), staging_dir)
        return build_canonical_stage(raw, self._mappings.osemosys, self._recorder, staging_dir)

    def _require_params(self, params: BaseModel | None) -> Params:
        expected = self.params_schema
        if expected is None or not isinstance(params, expected):
            raise TypeError(
                f"{type(self).__name__} requires {getattr(expected, '__name__', None)}, "
                f"got {type(params).__name__}"
            )
        return cast(Params, params)

    def _build_raw_tables(self, params: Params) -> RawTables:
        raise NotImplementedError
