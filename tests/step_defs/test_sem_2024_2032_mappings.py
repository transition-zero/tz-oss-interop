"""Binds the sem_2024_2032_mappings feature.

The case study ships its carrier mappings twice, as a YAML block a reader copies and as a
JSON file a reader points the translator at. These scenarios keep the two in step and keep
both inside the Sienna vocabulary.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from pytest_bdd import given, parsers, scenarios, then, when

from tests.step_defs.conftest import parse_plexos_carrier_mappings

FEATURE = Path(__file__).resolve().parents[1] / "features" / "sem_2024_2032_mappings.feature"
scenarios(str(FEATURE))

REPO_ROOT = Path(__file__).resolve().parents[2]
CASE_STUDY_PAGE = REPO_ROOT / "docs" / "case_studies" / "sem-2024-2032.md"
SHIPPED_MAPPINGS = REPO_ROOT / "docs" / "case_studies" / "sem-2024-2032-user-mappings.json"

_YAML_FENCE = "```yaml"
_FENCE = "```"


def read_one_yaml_block(path: Path) -> dict[str, Any]:
    """The one fenced YAML block of a Markdown page, parsed.

    A second block would make "the block the page shows" ambiguous, so this refuses one.
    """
    blocks: list[str] = []
    collected: list[str] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if collected is None:
            if line.strip() == _YAML_FENCE:
                collected = []
            continue
        if line.strip() == _FENCE:
            blocks.append("\n".join(collected))
            collected = None
            continue
        collected.append(line)
    assert collected is None, f"{path} leaves a fenced yaml block unclosed"
    assert len(blocks) == 1, f"{path} holds {len(blocks)} fenced yaml blocks, expected 1"
    parsed = yaml.safe_load(blocks[0])
    assert isinstance(parsed, dict), f"the yaml block of {path} is not a mapping"
    return parsed


@given("the carrier mappings the SEM 2024-2032 page shows", target_fixture="shown_document")
def given_shown_mappings() -> dict[str, Any]:
    return read_one_yaml_block(CASE_STUDY_PAGE)


@given("the carrier mappings the SEM 2024-2032 page ships", target_fixture="shipped_document")
def given_shipped_mappings() -> dict[str, Any]:
    parsed = json.loads(SHIPPED_MAPPINGS.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict), f"{SHIPPED_MAPPINGS} is not a mapping"
    return parsed


@then("the shown carriers and the shipped carriers are the same")
def assert_shown_and_shipped_agree(
    shown_document: dict[str, Any], shipped_document: dict[str, Any]
) -> None:
    shown = shown_document["carriers"]
    shipped = shipped_document["carriers"]
    assert shown == shipped, (
        f"{CASE_STUDY_PAGE.name} shows {len(shown)} carrier(s) and {SHIPPED_MAPPINGS.name} "
        f"holds {len(shipped)}, and the rows differ"
    )


@when(
    parsers.parse("interop parses the carrier mappings the SEM 2024-2032 page {verb}"),
    target_fixture="parsed_carriers",
)
def when_interop_parses_the_mappings(verb: str) -> list[dict[str, Any]]:
    readers = {"shows": given_shown_mappings, "ships": given_shipped_mappings}
    assert verb in readers, f"no carrier mappings document for {verb!r}"
    return parse_plexos_carrier_mappings(readers[verb]())


@then("interop accepts every carrier row")
def assert_every_carrier_row_is_accepted(parsed_carriers: list[dict[str, Any]]) -> None:
    assert parsed_carriers, "the mappings document names no carrier"
    unnamed = [row for row in parsed_carriers if not row.get("sienna_component_type")]
    assert not unnamed, f"{len(unnamed)} carrier row(s) name no Sienna component type"
