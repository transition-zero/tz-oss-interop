from pathlib import Path

import pytest
from interop_testing import write_project_plugin
from pytest_bdd import given, parsers, scenarios, then, when

from tests.step_defs.conftest import invoke_translate

scenarios("../features/translate_staging.feature")


@when(
    parsers.parse(
        'I run translate with source "{src}", destination "{dst}", '
        'pipeline "{pipeline}", step out "{out}"'
    )
)
def run_translate_with_step_out(
    monkeypatch: pytest.MonkeyPatch, src: str, dst: str, pipeline: str, out: str
) -> None:
    invoke_translate(monkeypatch, src, dst, pipeline, step_0_out=out)


_STAGING_PROBE_VALIDATOR_PY = """\
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel

from interop.core.pipeline import State, Validator


class _StagingProbeValidator(Validator):
    name: ClassVar[str] = "staging_probe_validator"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def validate(self, state: State, params: BaseModel | None) -> None:
        out = Path("outputs/staging-path.txt")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(str(state.staging_dir), encoding="utf-8")
"""


@given("a staging probe validator plugin")
def given_staging_probe_validator_plugin() -> None:
    write_project_plugin("validators", "staging_probe_validator", _STAGING_PROBE_VALIDATOR_PY)


@then(parsers.parse('the directory recorded in "{path}" exists'))
def assert_recorded_dir_exists(path: str) -> None:
    recorded = Path(path).read_text(encoding="utf-8").strip()
    assert Path(recorded).is_dir(), f"expected staging dir {recorded!r} to exist, but it does not"


@then(parsers.parse('the directory recorded in "{path}" does not exist'))
def assert_recorded_dir_not_exists(path: str) -> None:
    recorded = Path(path).read_text(encoding="utf-8").strip()
    assert not Path(recorded).exists(), (
        f"expected staging dir {recorded!r} to be cleaned up, but it still exists"
    )
