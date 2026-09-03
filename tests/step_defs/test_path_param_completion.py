from pathlib import Path

import pytest
from interop_testing import write_pipeline
from pytest_bdd import given, parsers, scenarios, then, when

from tests.step_defs.conftest import invoke_translate

FEATURE = Path(__file__).resolve().parents[1] / "features" / "path_param_completion.feature"
scenarios(str(FEATURE))


_NEEDS_PATH_PIPELINE_YAML = """\
source_framework: noop
destination_framework: noop
source:
  name: echo_path
sinks:
  - name: emit_json
    params:
      output_path: {output_path}
"""


@given(parsers.parse('a pipeline "{name}" reading a path field and writing to "{output_path}"'))
def given_needs_path_pipeline(name: str, output_path: str) -> None:
    write_pipeline(name, _NEEDS_PATH_PIPELINE_YAML.format(output_path=output_path))


@when(parsers.parse('I translate "{pipeline}" answering source path "{src_path}"'))
def when_translate_answering_source_path(
    monkeypatch: pytest.MonkeyPatch, pipeline: str, src_path: str
) -> None:
    invoke_translate(monkeypatch, "noop", "noop", pipeline, source_path=src_path)


@then(parsers.parse('the path prompt for "{field}" told me to press Tab to list files'))
def then_path_prompt_invites_tab(path_prompts: list[str], field: str) -> None:
    matching = [message for message in path_prompts if message.startswith(field)]
    assert matching, f"no path prompt for {field!r} in {path_prompts!r}"
    assert any("Tab to list files" in message for message in matching), (
        f"expected a Tab hint in the path prompt for {field!r}, got {matching!r}"
    )
