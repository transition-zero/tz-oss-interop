import json
from pathlib import Path

import pytest
from interop_testing import write_pipeline, write_project_plugin
from pytest_bdd import given, parsers, scenarios, then, when

from tests.step_defs.conftest import invoke_translate

FEATURE = (
    Path(__file__).resolve().parents[2]
    / "features"
    / "pypsa_to_sienna"
    / "stage_pypsa_network_file.feature"
)
scenarios(str(FEATURE))


_RECORD_MANIFEST_STEP_PY = """\
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep


class _RecordManifestParams(BaseModel):
    out: Path


class _RecordManifest(TranslationStep):
    name: ClassVar[str] = "record_manifest"
    params_schema: ClassVar[type[BaseModel] | None] = _RecordManifestParams

    def run(self, state: State, params: BaseModel | None) -> State:
        assert isinstance(params, _RecordManifestParams)
        params.out.parent.mkdir(parents=True, exist_ok=True)
        relpaths = sorted(
            p.relative_to(state.staging_dir).as_posix()
            for p in Path(state.staging_dir).rglob("*")
            if p.is_file()
        )
        params.out.write_text("\\n".join(relpaths), encoding="utf-8")
        return state
"""


_RECORD_EXTENSIONS_STEP_PY = """\
import json
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel

from interop.core.extensions import (
    NETWORK_RECORD_NAME,
    ExtensionKind,
    record_for,
)
from interop.core.pipeline import State, TranslationStep


class _RecordExtensionsParams(BaseModel):
    out: Path


class _RecordExtensions(TranslationStep):
    name: ClassVar[str] = "record_extensions"
    params_schema: ClassVar[type[BaseModel] | None] = _RecordExtensionsParams

    def run(self, state: State, params: BaseModel | None) -> State:
        assert isinstance(params, _RecordExtensionsParams)
        params.out.parent.mkdir(parents=True, exist_ok=True)
        record = record_for(state.source_extensions, ExtensionKind.NETWORK, NETWORK_RECORD_NAME)
        stated = {} if record is None else record.model_dump(exclude_none=True)
        params.out.write_text(json.dumps(stated), encoding="utf-8")
        return state
"""


_PYPSA_STAGE_TEST_PIPELINE_YAML = """\
source_framework: pypsa
destination_framework: sienna
source:
  name: stage_pypsa_network_file
steps:
  - name: record_manifest
sinks:
  - name: emit_json
"""


_PYPSA_ATTRS_TEST_PIPELINE_YAML = """\
source_framework: pypsa
destination_framework: sienna
source:
  name: stage_pypsa_network_file
steps:
  - name: record_extensions
sinks:
  - name: emit_json
"""


@given('a step plugin "record_manifest" that lists the staging directory contents to a file')
def given_record_manifest_step_plugin() -> None:
    write_project_plugin("steps", "record_manifest", _RECORD_MANIFEST_STEP_PY)


@given(
    parsers.parse(
        'a project-local pipeline "{name}" using stage_pypsa_network_file, '
        "record_manifest, and emit_json"
    )
)
def given_project_local_pypsa_stage_pipeline(name: str) -> None:
    write_pipeline(name, _PYPSA_STAGE_TEST_PIPELINE_YAML)


@given('a step plugin "record_extensions" that writes the network extensions record to a file')
def given_record_extensions_step_plugin() -> None:
    write_project_plugin("steps", "record_extensions", _RECORD_EXTENSIONS_STEP_PY)


@given(
    parsers.parse(
        'a project-local pipeline "{name}" using stage_pypsa_network_file, '
        "record_extensions, and emit_json"
    )
)
def given_project_local_pypsa_attrs_pipeline(name: str) -> None:
    write_pipeline(name, _PYPSA_ATTRS_TEST_PIPELINE_YAML)


@then(parsers.parse('the manifest "{path}" lists "{relative}"'))
def assert_manifest_lists(path: str, relative: str) -> None:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    assert relative in lines, f"expected {relative!r} in manifest {path}; got {lines!r}"


@when(
    parsers.parse(
        'I run translate against "{source}" with pipeline "{pipeline}", '
        'step out "{step_out}", sink output "{sink_output}"'
    )
)
def run_translate_pypsa_source(
    monkeypatch: pytest.MonkeyPatch,
    source: str,
    pipeline: str,
    step_out: str,
    sink_output: str,
) -> None:
    invoke_translate(
        monkeypatch,
        "pypsa",
        "sienna",
        pipeline,
        source_path=source,
        step_0_out=step_out,
        sink_0_output_path=sink_output,
    )


@then(parsers.parse('the network extensions "{path}" record "{field}" as "{value}"'))
def assert_network_extensions_value(path: str, field: str, value: str) -> None:
    record = json.loads(Path(path).read_text(encoding="utf-8"))
    assert record.get(field) == value, f"expected {field!r} of {value!r} in {path}; got {record!r}"


@then(parsers.parse('the network extensions "{path}" record a "{field}"'))
def assert_network_extensions_record(path: str, field: str) -> None:
    record = json.loads(Path(path).read_text(encoding="utf-8"))
    assert record.get(field), f"expected a non-empty {field!r} in {path}; got {record!r}"


@then(parsers.parse('the network extensions "{path}" record no "{field}"'))
def assert_network_extensions_omit(path: str, field: str) -> None:
    record = json.loads(Path(path).read_text(encoding="utf-8"))
    assert field not in record, f"expected no {field!r} in {path}; got {record!r}"
