from pathlib import Path

from interop_testing import write_pipeline, write_project_plugin
from pytest_bdd import given, parsers, scenarios

FEATURE = Path(__file__).resolve().parents[1] / "features" / "testing_harness.feature"
scenarios(str(FEATURE))


_COUNT_BUSES_SINK_PY = """\
import json
from typing import ClassVar

from pydantic import BaseModel

from interop.core.pipeline import Sink, State
from interop.ports.outbound.filesystem import FilesystemPort, Location


class _CountBusesParams(BaseModel):
    output_path: Location


class _CountBuses(Sink):
    name: ClassVar[str] = "count_buses"
    params_schema: ClassVar[type[BaseModel] | None] = _CountBusesParams

    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def write(self, state: State, params: BaseModel | None) -> None:
        assert isinstance(params, _CountBusesParams)
        buses = state.source_topology["buses"].collect()
        self._fs.write_bytes(
            params.output_path, json.dumps({"buses": buses.height}).encode("utf-8")
        )
"""


_COUNT_BUSES_PIPELINE_YAML = """\
source_framework: pypsa
destination_framework: noop
source:
  name: stage_pypsa_network_file
sinks:
  - name: count_buses
"""


@given(parsers.parse('a project pipeline "{name}" reading a PyPSA network and counting its buses'))
def given_count_buses_pipeline(name: str) -> None:
    write_project_plugin("sinks", "count_buses", _COUNT_BUSES_SINK_PY)
    write_pipeline(name, _COUNT_BUSES_PIPELINE_YAML)
