"""BDD step definitions for comparing a PyPSA network against the CAISO PLEXOS stack model."""

from __future__ import annotations

import pytest
from pytest_bdd import parsers, scenarios, when

from tests.step_defs.conftest import invoke_compare

scenarios("../features/caiso_plexos_compare.feature")

_OUTPUT_PATH = "outputs/comparison_summary.md"

# Where the feature's Given steps write the two CSVs the stack-model source now asks for.
_STACK_MODEL_PATH = "inputs/stack_model.csv"
_APPENDIX_PATH = "inputs/appendix.csv"


def _path_answers(nc: str) -> dict[str, str]:
    """The path prompts both sides of the comparison ask, whichever way round it runs."""
    return {
        "pypsa.path": nc,
        "caiso-plexos.stack_model_path": _STACK_MODEL_PATH,
        "caiso-plexos.appendix_path": _APPENDIX_PATH,
        "Output path for summary report?": _OUTPUT_PATH,
    }


@when(parsers.parse('I compare the pypsa network in "{nc}" against the CAISO PLEXOS stack model'))
def when_compare_pypsa_against_caiso(monkeypatch: pytest.MonkeyPatch, nc: str) -> None:
    invoke_compare(
        monkeypatch,
        framework_a="pypsa",
        framework_b="caiso-plexos",
        path_answers=_path_answers(nc),
    )


@when(parsers.parse('I compare the CAISO PLEXOS stack model against the pypsa network in "{nc}"'))
def when_compare_caiso_against_pypsa(monkeypatch: pytest.MonkeyPatch, nc: str) -> None:
    """The same comparison the other way round, so the PyPSA leg runs last.

    Both legs write decisions.md to the same path, so only the last one's decisions
    survive; this order is what lets a scenario read the PyPSA leg's own.
    """
    invoke_compare(
        monkeypatch,
        framework_a="caiso-plexos",
        framework_b="pypsa",
        path_answers=_path_answers(nc),
    )
