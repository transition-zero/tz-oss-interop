"""The plugin sources a scenario writes into a project, and the Given steps that write them.

Each constant is the text of a project-local plugin: a source, sink, step or outbound
adapter small enough to state inline, standing in for a real one so a scenario can
exercise the surface around it. Kept out of `conftest.py`, which holds the fixtures and
the questionary stubbing, so neither file mixes the two.

Registered as a pytest plugin from `tests/conftest.py`.
"""

from interop_testing import (
    write_noop_pipeline,
    write_noop_validator_pipeline,
    write_pipeline,
    write_project_plugin,
)
from pytest_bdd import given, parsers

_EMIT_BARE_PIPELINE_YAML = """\
source_framework: noop
destination_framework: noop
source:
  name: noop
sinks:
  - name: emit_json
"""


_EMIT_WITH_OUTPUT_PIPELINE_YAML = """\
source_framework: noop
destination_framework: noop
source:
  name: noop
sinks:
  - name: emit_json
    params:
      output_path: {output_path}
"""


# The date column has no JSON representation of its own, so a sink that serialises this
# table has to say how a value it cannot encode should be rendered.
_ECHO_VALUE_SOURCE_PY = """\
from datetime import date
from pathlib import Path
from typing import ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import StagedSource, State


class _EchoValueParams(BaseModel):
    value: str


class _EchoValue(StagedSource):
    name: ClassVar[str] = "echo_value"
    params_schema: ClassVar[type[BaseModel] | None] = _EchoValueParams
    prefix: ClassVar[str] = "echo"

    def load_into_state(self, params: BaseModel | None, staging_dir: Path) -> State:
        assert isinstance(params, _EchoValueParams)
        return State(
            staging_dir=staging_dir,
            destination_tables={
                "echo": pl.DataFrame(
                    {"value": [params.value], "as_of": [date(2026, 1, 2)]}
                )
            },
        )
"""


_ECHO_VALUE_PIPELINE_YAML = """\
source_framework: noop
destination_framework: noop
source:
  name: echo_value
sinks:
  - name: emit_json
"""


@given(parsers.parse('a pipeline "{name}" with source "noop" and sink "emit_json" (no params)'))
def given_pipeline_emit_bare(name: str) -> None:
    write_pipeline(name, _EMIT_BARE_PIPELINE_YAML)


@given(
    parsers.parse(
        'a pipeline "{name}" with source "noop" and sink "emit_json" writing to "{output_path}"'
    )
)
def given_pipeline_emit_writing(name: str, output_path: str) -> None:
    write_pipeline(name, _EMIT_WITH_OUTPUT_PIPELINE_YAML.format(output_path=output_path))


@given('a source plugin "echo_value" with a required string field "value"')
def given_echo_value_source_plugin() -> None:
    write_project_plugin("sources", "echo_value", _ECHO_VALUE_SOURCE_PY)


_ECHO_PATH_SOURCE_PY = """\
from pathlib import Path
from typing import ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import StagedSource, State


class _EchoPathParams(BaseModel):
    path: Path


class _EchoPath(StagedSource):
    name: ClassVar[str] = "echo_path"
    params_schema: ClassVar[type[BaseModel] | None] = _EchoPathParams
    prefix: ClassVar[str] = "echo"

    def load_into_state(self, params: BaseModel | None, staging_dir: Path) -> State:
        assert isinstance(params, _EchoPathParams)
        return State(
            staging_dir=staging_dir,
            destination_tables={"echo": pl.DataFrame({"path": [str(params.path)]})},
        )
"""


@given('a source plugin "echo_path" with a required path field "path"')
def given_echo_path_source_plugin() -> None:
    write_project_plugin("sources", "echo_path", _ECHO_PATH_SOURCE_PY)


@given(
    parsers.parse('a pipeline "{name}" with source "echo_value" and sink "emit_json" (no params)')
)
def given_pipeline_echo_value(name: str) -> None:
    write_pipeline(name, _ECHO_VALUE_PIPELINE_YAML)


_HTTP_READER_SOURCE_PY = """\
from pathlib import Path
from typing import ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import StagedSource, State
from interop.ports.outbound.filesystem import FilesystemPort, Location


class _HttpReaderParams(BaseModel):
    path: Location


class _HttpReader(StagedSource):
    name: ClassVar[str] = "http_reader"
    params_schema: ClassVar[type[BaseModel] | None] = _HttpReaderParams
    prefix: ClassVar[str] = "httpreader"

    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def load_into_state(self, params: BaseModel | None, staging_dir: Path) -> State:
        assert isinstance(params, _HttpReaderParams)
        data = self._fs.read_bytes(params.path)
        return State(
            staging_dir=staging_dir,
            destination_tables={
                "payload": pl.DataFrame({"data": [data]}, schema={"data": pl.Binary})
            },
        )
"""


_HTTP_WRITER_SINK_PY = """\
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel

from interop.core.pipeline import Sink, State
from interop.ports.outbound.filesystem import FilesystemPort, Location


class _HttpWriterParams(BaseModel):
    path: Location


class _HttpWriter(Sink):
    name: ClassVar[str] = "http_writer"
    params_schema: ClassVar[type[BaseModel] | None] = _HttpWriterParams

    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def write(self, state: State, params: BaseModel | None) -> None:
        assert isinstance(params, _HttpWriterParams)
        data: bytes = state.destination_tables["payload"]["data"][0]
        self._fs.write_bytes(params.path, data)
"""


_HTTP_ROUNDTRIP_PIPELINE_TEMPLATE = """\
source_framework: noop
destination_framework: noop
source:
  name: http_reader
  params:
    path: {input_url}
sinks:
  - name: http_writer
    params:
      path: {output_url}
"""


_HTTP_ROUNDTRIP_BARE_PIPELINE_YAML = """\
source_framework: noop
destination_framework: noop
source:
  name: http_reader
sinks:
  - name: http_writer
"""


@given(
    parsers.parse(
        'an http round-trip pipeline "{pipeline_name}" copying "{input_url}" to "{output_url}"'
    )
)
def given_http_roundtrip_pipeline(pipeline_name: str, input_url: str, output_url: str) -> None:
    write_project_plugin("sources", "http_reader", _HTTP_READER_SOURCE_PY)
    write_project_plugin("sinks", "http_writer", _HTTP_WRITER_SINK_PY)
    write_pipeline(
        pipeline_name,
        _HTTP_ROUNDTRIP_PIPELINE_TEMPLATE.format(input_url=input_url, output_url=output_url),
    )


@given(parsers.parse('an http round-trip pipeline "{pipeline_name}" with no baked-in paths'))
def given_http_roundtrip_pipeline_bare(pipeline_name: str) -> None:
    write_project_plugin("sources", "http_reader", _HTTP_READER_SOURCE_PY)
    write_project_plugin("sinks", "http_writer", _HTTP_WRITER_SINK_PY)
    write_pipeline(pipeline_name, _HTTP_ROUNDTRIP_BARE_PIPELINE_YAML)


_FAKE_SOLVER_TEMPLATE = """\
from pathlib import Path
from typing import ClassVar

from interop.ports.outbound.network_solver import UnitCommitmentTreatment
from interop.ports.outbound.solver import HiGHSCrossover, HiGHSPresolve, HiGHSSolver, SolverPort


class FakeSolverAdapter(SolverPort):
    name: ClassVar[str] = "fake_solver"
    port: ClassVar[type] = SolverPort

    def is_provisioned(self) -> bool:
        return {provisioned}

    def solve(
        self,
        sienna_json_path: Path,
        network_model: str,
        output_dir: Path | None = None,
        *,
        unit_commitment: UnitCommitmentTreatment = UnitCommitmentTreatment.EXACT,
        solver: HiGHSSolver = HiGHSSolver.SIMPLEX,
        presolve: HiGHSPresolve = HiGHSPresolve.CHOOSE,
        run_crossover: HiGHSCrossover = HiGHSCrossover.CHOOSE,
        time_limit_seconds: float | None = None,
    ) -> tuple[str, float]:
        Path("outputs").mkdir(parents=True, exist_ok=True)
        # Posix form, so a scenario can name a path the same way on every platform.
        recorded_json_path = sienna_json_path.as_posix()
        recorded_output_dir = output_dir.as_posix() if output_dir else output_dir
        Path("outputs/solver-call.txt").write_text(
            "\\n".join(
                [
                    f"sienna_json_path={{recorded_json_path}}",
                    f"network_model={{network_model}}",
                    f"output_dir={{recorded_output_dir}}",
                    f"unit_commitment={{unit_commitment}}",
                    f"solver={{solver}}",
                    f"presolve={{presolve}}",
                    f"run_crossover={{run_crossover}}",
                    f"time_limit_seconds={{time_limit_seconds}}",
                ]
            ),
            encoding="utf-8",
        )
        return ("SUCCESSFULLY_FINALIZED", 123.456)
"""


def _fake_solver_py(*, provisioned: bool) -> str:
    return _FAKE_SOLVER_TEMPLATE.format(provisioned=provisioned)


@given("a fake solver adapter in project plugins")
def given_fake_solver_plugin() -> None:
    write_project_plugin("adapters", "fake_solver", _fake_solver_py(provisioned=True))


@given("a fake solver adapter in project plugins that is not provisioned")
def given_unprovisioned_fake_solver_plugin() -> None:
    write_project_plugin("adapters", "fake_solver", _fake_solver_py(provisioned=False))


_STAGING_PROBE_STEP_PY = """\
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep


class _StagingProbeParams(BaseModel):
    out: Path


class _StagingProbe(TranslationStep):
    name: ClassVar[str] = "staging_probe"
    params_schema: ClassVar[type[BaseModel] | None] = _StagingProbeParams

    def run(self, state: State, params: BaseModel | None) -> State:
        assert isinstance(params, _StagingProbeParams)
        params.out.parent.mkdir(parents=True, exist_ok=True)
        params.out.write_text(str(state.staging_dir), encoding="utf-8")
        return state
"""


@given("a staging probe step plugin")
def given_staging_probe_step_plugin() -> None:
    write_project_plugin("steps", "staging_probe", _STAGING_PROBE_STEP_PY)


def _split_names(names: str) -> list[str]:
    return [name.strip() for name in names.split(",")]


@given(parsers.parse('a pipeline "{name}" running steps "{steps}"'))
def given_noop_pipeline(name: str, steps: str) -> None:
    write_noop_pipeline(name, _split_names(steps))


@given(parsers.parse('a pipeline "{name}" running validators "{validators}"'))
def given_noop_validator_pipeline(name: str, validators: str) -> None:
    write_noop_validator_pipeline(name, _split_names(validators))
