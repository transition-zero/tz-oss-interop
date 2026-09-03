from pathlib import Path

import pytest
from interop_testing import write_pipeline, write_project_plugin
from pytest_bdd import given, parsers, scenarios, when

from tests.step_defs.conftest import invoke_translate

FEATURE = Path(__file__).resolve().parents[1] / "features" / "directory_param_prompt.feature"
scenarios(str(FEATURE))


_ECHO_DIR_SOURCE_PY = """\
from pathlib import Path
from typing import ClassVar

import polars as pl
from pydantic import BaseModel, DirectoryPath

from interop.core.pipeline import StagedSource, State


class _EchoDirParams(BaseModel):
    dir_path: DirectoryPath


class _EchoDir(StagedSource):
    name: ClassVar[str] = "echo_dir"
    params_schema: ClassVar[type[BaseModel] | None] = _EchoDirParams
    prefix: ClassVar[str] = "echo-dir"

    def load_into_state(self, params: BaseModel | None, staging_dir: Path) -> State:
        assert isinstance(params, _EchoDirParams)
        return State(
            staging_dir=staging_dir,
            destination_tables={"echo": pl.DataFrame({"dir": [str(params.dir_path)]})},
        )
"""


_NEEDS_DIR_PIPELINE_YAML = """\
source_framework: noop
destination_framework: noop
source:
  name: echo_dir
sinks:
  - name: emit_json
    params:
      output_path: {output_path}
"""


@given('a source plugin "echo_dir" with a required directory field "dir_path"')
def given_echo_dir_source_plugin() -> None:
    write_project_plugin("sources", "echo_dir", _ECHO_DIR_SOURCE_PY)


@given(
    parsers.parse('a pipeline "{name}" reading a directory field and writing to "{output_path}"')
)
def given_needs_dir_pipeline(name: str, output_path: str) -> None:
    write_pipeline(name, _NEEDS_DIR_PIPELINE_YAML.format(output_path=output_path))


@given(parsers.parse('a directory "{path}" exists'))
def given_directory_exists(path: str) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)


@when(
    parsers.parse(
        'I translate "{pipeline}" answering source directory with "{first}" then "{second}"'
    )
)
def when_translate_answering_source_directory(
    monkeypatch: pytest.MonkeyPatch, pipeline: str, first: str, second: str
) -> None:
    invoke_translate(monkeypatch, "noop", "noop", pipeline, source_dir_path=[first, second])
