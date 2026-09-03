import pytest
from pytest_bdd import parsers, scenarios, when

from tests.step_defs.conftest import (
    invoke_compare_cancel_at_first_framework,
    invoke_translate_cancel_at_destination,
)

scenarios("../features/results_pipeline_discovery.feature")


@when(parsers.parse('I start translate and choose source framework "{framework}"'))
def start_translate_choose_source(monkeypatch: pytest.MonkeyPatch, framework: str) -> None:
    invoke_translate_cancel_at_destination(monkeypatch, framework)


@when("I start compare")
def start_compare(monkeypatch: pytest.MonkeyPatch) -> None:
    invoke_compare_cancel_at_first_framework(monkeypatch)
