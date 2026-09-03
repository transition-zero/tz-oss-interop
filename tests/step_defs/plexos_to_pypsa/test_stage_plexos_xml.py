from pathlib import Path

import pytest
from interop_testing import write_pipeline, write_project_plugin
from pytest_bdd import given, parsers, scenarios, then, when

from tests.step_defs.conftest import invoke_translate

FEATURE = (
    Path(__file__).resolve().parents[2]
    / "features"
    / "plexos_to_pypsa"
    / "stage_plexos_xml.feature"
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


_PLEXOS_STAGE_TEST_PIPELINE_YAML = """\
source_framework: plexos
destination_framework: pypsa
source:
  name: stage_plexos_xml
steps:
  - name: record_manifest
sinks:
  - name: emit_json
"""


@given('a step plugin "record_manifest" that lists the staging directory contents to a file')
def given_record_manifest_step_plugin() -> None:
    write_project_plugin("steps", "record_manifest", _RECORD_MANIFEST_STEP_PY)


@given(
    parsers.parse(
        'a project-local pipeline "{name}" using stage_plexos_xml, record_manifest, and emit_json'
    )
)
def given_project_local_plexos_stage_pipeline(name: str) -> None:
    write_pipeline(name, _PLEXOS_STAGE_TEST_PIPELINE_YAML)


@when(
    parsers.parse(
        'I run stage translate against "{xml_path}" pipeline "{pipeline}" '
        'step out "{step_out}" sink output "{sink_output}"'
    )
)
def run_stage_translate(
    monkeypatch: pytest.MonkeyPatch,
    xml_path: str,
    pipeline: str,
    step_out: str,
    sink_output: str,
) -> None:
    invoke_translate(
        monkeypatch,
        "plexos",
        "pypsa",
        pipeline,
        source_path=str(Path(xml_path)),
        step_0_out=step_out,
        sink_0_output_path=sink_output,
    )


@then(parsers.parse('the manifest "{path}" lists "{relative}"'))
def assert_manifest_lists(path: str, relative: str) -> None:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    assert relative in lines, f"expected {relative!r} in manifest {path}; got {lines!r}"
