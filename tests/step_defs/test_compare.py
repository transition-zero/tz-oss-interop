"""BDD step definitions for the compare command.

Compare runs each chosen framework's results pipeline (via translate) into the
results format and reports the differences. The PyPSA and Sienna sides are built
with the shared network / system / results builders, so compare is exercised
end-to-end through the real pipelines.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from interop_testing.builders.sienna_documents import sienna_extensions_filename
from pytest_bdd import parsers, scenarios, then, when

from tests.step_defs.conftest import invoke_compare

scenarios("../features/compare.feature")

_OUTPUT_PATH = "outputs/comparison_summary.md"


@when(
    parsers.parse(
        'I compare the pypsa network in "{nc}" against the sienna system in "{system}" '
        'with results in "{results_dir}"'
    )
)
def when_compare_pypsa_against_sienna(
    monkeypatch: pytest.MonkeyPatch, nc: str, system: str, results_dir: str
) -> None:
    extensions = str(Path(system).parent / sienna_extensions_filename(Path(system)))
    invoke_compare(
        monkeypatch,
        framework_a="pypsa",
        framework_b="sienna",
        path_answers={
            "pypsa.path": nc,
            "sienna.system_json_path": system,
            "sienna.extensions_json_path": extensions,
            "sienna.results_dir": results_dir,
            "Output path for summary report?": _OUTPUT_PATH,
        },
    )


@then(parsers.parse('the second-framework prompt did not offer "{framework}"'))
def then_second_framework_excluded(recorded_selects: list[dict[str, Any]], framework: str) -> None:
    second = [
        record for record in recorded_selects if record["message"] and "Second" in record["message"]
    ]
    assert second, (
        f"no second-framework select recorded; selects: "
        f"{[record['message'] for record in recorded_selects]}"
    )
    titles = second[-1]["choice_titles"]
    assert framework not in titles, f"second-framework prompt offered {framework!r}: {titles}"
