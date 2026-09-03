from pathlib import Path

import pytest
from interop_testing import write_project_plugin
from pytest_bdd import given, parsers, scenarios, then

FEATURE = Path(__file__).resolve().parents[1] / "features" / "headless_cli.feature"
scenarios(str(FEATURE))


_ECHO_MAPPING_STEP_PY = """\
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep
from interop.core.user_mappings import UserMappings


class _EchoMapping(UserMappings):
    label: str


class _EchoMappingParams(BaseModel):
    out: Path


class _EchoMappingStep(TranslationStep):
    name: ClassVar[str] = "echo_mapping"
    params_schema: ClassVar[type[BaseModel] | None] = _EchoMappingParams

    def __init__(self, mapping: _EchoMapping) -> None:
        self._mapping = mapping

    def run(self, state: State, params: BaseModel | None) -> State:
        assert isinstance(params, _EchoMappingParams)
        params.out.parent.mkdir(parents=True, exist_ok=True)
        params.out.write_text(self._mapping.label, encoding="utf-8")
        return state
"""


@given('a step plugin "echo_mapping" that writes its user mapping to a file')
def given_echo_mapping_step_plugin() -> None:
    write_project_plugin("steps", "echo_mapping", _ECHO_MAPPING_STEP_PY)


@then(parsers.parse('the stderr output contains "{expected}"'))
def assert_stderr_contains(capsys: pytest.CaptureFixture[str], expected: str) -> None:
    captured = capsys.readouterr()
    assert expected in captured.err, f"expected {expected!r} in stderr, got {captured.err!r}"
