import pytest
from interop_testing import write_pipeline, write_project_plugin
from pytest_bdd import given, parsers, scenarios, when

from tests.step_defs.conftest import invoke_translate

scenarios("../features/translate_dynamic_params.feature")


_TAGGER_STEP_PY = """\
from typing import ClassVar

import polars as pl
from pydantic import BaseModel, Field

from interop.core.pipeline import State, TranslationStep


class _TaggerParams(BaseModel):
    label: str
    count: int = Field(default=1, ge=1)


class _Tagger(TranslationStep):
    name: ClassVar[str] = "tagger"
    params_schema: ClassVar[type[BaseModel] | None] = _TaggerParams

    def run(self, state: State, params: BaseModel | None) -> State:
        assert isinstance(params, _TaggerParams)
        state.destination_tables["row"] = pl.DataFrame(
            {"label": [params.label], "count": [params.count]}
        )
        return state
"""


_TAGGER_PIPELINE = """\
source_framework: noop
destination_framework: noop
source:
  name: noop
steps:
  - name: tagger
sinks:
  - name: emit_json
"""


_FANOUT_PIPELINE = """\
source_framework: noop
destination_framework: noop
source:
  name: noop
sinks:
  - name: emit_json
  - name: emit_json
"""


@given('a step plugin "tagger" with required fields "label" (string) and "count" (int >= 1)')
def given_tagger_step_plugin() -> None:
    write_project_plugin("steps", "tagger", _TAGGER_STEP_PY)


@given(
    parsers.parse(
        'a pipeline "{name}" with source "noop", step "tagger", and sink "emit_json" (no params)'
    )
)
def given_pipeline_tagged(name: str) -> None:
    write_pipeline(name, _TAGGER_PIPELINE)


@given(
    parsers.parse('a pipeline "{name}" with source "noop" and two "emit_json" sinks (no params)')
)
def given_pipeline_fanout(name: str) -> None:
    write_pipeline(name, _FANOUT_PIPELINE)


@when(
    parsers.parse(
        'I run translate with source "{src}", destination "{dst}", '
        'pipeline "{pipeline}", sink output "{output}"'
    )
)
def run_translate_with_sink_output(
    monkeypatch: pytest.MonkeyPatch, src: str, dst: str, pipeline: str, output: str
) -> None:
    invoke_translate(monkeypatch, src, dst, pipeline, sink_0_output_path=output)


@when(
    parsers.parse(
        'I run translate with source "{src}", destination "{dst}", '
        'pipeline "{pipeline}", source value "{value}", sink output "{output}"'
    )
)
def run_translate_with_source_and_sink(
    monkeypatch: pytest.MonkeyPatch, src: str, dst: str, pipeline: str, value: str, output: str
) -> None:
    invoke_translate(
        monkeypatch,
        src,
        dst,
        pipeline,
        source_value=value,
        sink_0_output_path=output,
    )


@when(
    parsers.parse(
        'I run translate with source "{src}", destination "{dst}", '
        'pipeline "{pipeline}", step label "{label}", step count "{count}", '
        'sink output "{output}"'
    )
)
def run_translate_with_step_params(
    monkeypatch: pytest.MonkeyPatch,
    src: str,
    dst: str,
    pipeline: str,
    label: str,
    count: str,
    output: str,
) -> None:
    invoke_translate(
        monkeypatch,
        src,
        dst,
        pipeline,
        step_0_label=label,
        step_0_count=count,
        sink_0_output_path=output,
    )


@when(
    parsers.parse(
        'I run translate with source "{src}", destination "{dst}", '
        'pipeline "{pipeline}", first sink output "{out1}", second sink output "{out2}"'
    )
)
def run_translate_with_two_sinks(
    monkeypatch: pytest.MonkeyPatch, src: str, dst: str, pipeline: str, out1: str, out2: str
) -> None:
    invoke_translate(
        monkeypatch,
        src,
        dst,
        pipeline,
        sink_0_output_path=out1,
        sink_1_output_path=out2,
    )
