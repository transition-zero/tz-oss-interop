from pathlib import Path

from interop_testing import write_adapters_config, write_pipeline, write_project_plugin
from pytest_bdd import given, parsers, scenarios

FEATURE = Path(__file__).resolve().parents[1] / "features" / "local_filesystem_round_trip.feature"
scenarios(str(FEATURE))


_FILE_READER_SOURCE_PY = """\
from pathlib import Path
from typing import ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import StagedSource, State
from interop.ports.outbound.filesystem import FilesystemPort


class _FileReaderParams(BaseModel):
    path: Path


class _FileReader(StagedSource):
    name: ClassVar[str] = "file_reader"
    params_schema: ClassVar[type[BaseModel] | None] = _FileReaderParams
    prefix: ClassVar[str] = "filereader"

    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def load_into_state(self, params: BaseModel | None, staging_dir: Path) -> State:
        assert isinstance(params, _FileReaderParams)
        data = self._fs.read_bytes(params.path)
        return State(
            staging_dir=staging_dir,
            destination_tables={
                "payload": pl.DataFrame({"data": [data]}, schema={"data": pl.Binary})
            },
        )
"""


_FILE_WRITER_SINK_PY = """\
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel

from interop.core.pipeline import Sink, State
from interop.ports.outbound.filesystem import FilesystemPort


class _FileWriterParams(BaseModel):
    path: Path


class _FileWriter(Sink):
    name: ClassVar[str] = "file_writer"
    params_schema: ClassVar[type[BaseModel] | None] = _FileWriterParams

    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def write(self, state: State, params: BaseModel | None) -> None:
        assert isinstance(params, _FileWriterParams)
        data: bytes = state.destination_tables["payload"]["data"][0]
        self._fs.write_bytes(params.path, data)
"""


_ROUNDTRIP_PIPELINE_TEMPLATE = """\
source_framework: noop
destination_framework: noop
source:
  name: file_reader
  params:
    path: {input_path}
sinks:
  - name: file_writer
    params:
      path: {output_path}
"""


@given(parsers.parse('an input file "{path}" containing "{content}"'))
def given_input_file(path: str, content: str) -> None:
    full_path = Path.cwd() / path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content, encoding="utf-8")


@given(
    parsers.parse(
        'a round-trip pipeline "{pipeline_name}" copying "{input_path}" to "{output_path}"'
    )
)
def given_roundtrip_pipeline(pipeline_name: str, input_path: str, output_path: str) -> None:
    write_project_plugin("sources", "file_reader", _FILE_READER_SOURCE_PY)
    write_project_plugin("sinks", "file_writer", _FILE_WRITER_SINK_PY)
    write_pipeline(
        pipeline_name,
        _ROUNDTRIP_PIPELINE_TEMPLATE.format(input_path=input_path, output_path=output_path),
    )


@given(parsers.parse('I add an adapters.yaml configuring local_filesystem with root "{root}"'))
def given_adapters_yaml_with_local_fs_root(root: str) -> None:
    write_adapters_config(
        "bindings:\n  filesystem: local_filesystem\n"
        f"adapters:\n  local_filesystem:\n    root: {root}\n"
    )
