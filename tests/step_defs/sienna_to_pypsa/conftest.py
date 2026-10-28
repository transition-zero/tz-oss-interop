from __future__ import annotations

from pathlib import Path

import pytest
from interop_testing import write_pipeline, write_project_plugin
from interop_testing.builders.sienna_documents import sienna_extensions_filename, sienna_h5_filename
from pytest_bdd import given, parsers, when

from tests.step_defs.conftest import invoke_translate


def _invoke_translate_sienna_to_pypsa(
    monkeypatch: pytest.MonkeyPatch,
    json_path: str,
    pipeline: str,
    nc_output: str,
) -> None:
    system_path = Path(json_path)
    invoke_translate(
        monkeypatch,
        "sienna",
        "pypsa",
        pipeline,
        source_system_json_path=str(system_path),
        source_time_series_h5_path=str(system_path.parent / sienna_h5_filename(system_path)),
        source_extensions_json_path=str(
            system_path.parent / sienna_extensions_filename(system_path)
        ),
        sink_0_output_path=nc_output,
    )


@when(
    parsers.parse(
        'I run translate against "{json_path}" pipeline "{pipeline}" writing PyPSA to "{nc_output}"'
    )
)
def run_translate_sienna_to_pypsa(
    monkeypatch: pytest.MonkeyPatch,
    json_path: str,
    pipeline: str,
    nc_output: str,
) -> None:
    _invoke_translate_sienna_to_pypsa(monkeypatch, json_path, pipeline, nc_output)


@when(
    parsers.parse(
        'I run translate against Sienna system "{system_path}" '
        'pipeline "{pipeline}" sink output "{nc_output}"'
    )
)
def run_translate_sienna_system_to_pypsa(
    monkeypatch: pytest.MonkeyPatch,
    system_path: str,
    pipeline: str,
    nc_output: str,
) -> None:
    _invoke_translate_sienna_to_pypsa(monkeypatch, system_path, pipeline, nc_output)


_READ_CARRIER_ONLY_STEP_PY = """\
from typing import ClassVar

from pydantic import BaseModel

from interop.core.extensions import ExtensionKind
from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder


class ReadCarrierOnly(TranslationStep):
    name: ClassVar[str] = "{step}"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def run(self, state: State, params: BaseModel | None) -> State:
        generators = state.extension_reader(self._recorder).read(ExtensionKind.GENERATOR)
        for record in generators.list_records():
            generators.get_fields(record.name, ["carrier"])
        return state
"""

_READ_CARRIER_ONLY_PIPELINE_YAML = """\
source_framework: sienna
destination_framework: pypsa
source:
  name: stage_sienna_system_json
steps:
  - name: {step}
sinks:
  - name: emit_extensions_json
"""


@given(
    parsers.parse(
        'a project step "{step}" that maps the carrier of each generator record and relays nothing'
    )
)
def given_project_step_reading_carrier_only(step: str) -> None:
    write_project_plugin("steps", step, _READ_CARRIER_ONLY_STEP_PY.format(step=step))


@given(parsers.parse('a project pipeline "{name}" that runs the step "{step}"'))
def given_project_pipeline_running_step(name: str, step: str) -> None:
    write_pipeline(name, _READ_CARRIER_ONLY_PIPELINE_YAML.format(step=step))
