"""Binds the caiso_sa26_mappings feature.

The case study page and the JSON file beside it hold the same carrier mappings, one for
a reader to copy and one for a reader to point the translator at. Reading the page's
YAML block out of the markdown is what keeps the two from drifting apart.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from pytest_bdd import given, parsers, scenarios, then, when

from tests.step_defs.conftest import invoke_translate

FEATURE = Path(__file__).resolve().parents[1] / "features" / "caiso_sa26_mappings.feature"
scenarios(str(FEATURE))

CASE_STUDIES_DIR = Path(__file__).resolve().parents[2] / "docs" / "case_studies"
PAGE_PATH = CASE_STUDIES_DIR / "caiso-sa26.md"
MAPPINGS_PATH = CASE_STUDIES_DIR / "caiso-sa26-user-mappings.json"
CARRIERS_KEY = "carriers"

_FENCED_YAML = re.compile(r"^```yaml\n(.*?)^```", re.DOTALL | re.MULTILINE)


def _read_page_carriers() -> list[dict[str, Any]]:
    """The carriers in the one fenced YAML block of the page that states them."""
    blocks = [
        block
        for block in _FENCED_YAML.findall(PAGE_PATH.read_text(encoding="utf-8"))
        if f"{CARRIERS_KEY}:" in block
    ]
    assert len(blocks) == 1, f"expected one carriers block in {PAGE_PATH}, found {len(blocks)}"
    carriers = yaml.safe_load(blocks[0])[CARRIERS_KEY]
    assert isinstance(carriers, list) and carriers, f"no carriers in the block of {PAGE_PATH}"
    return carriers


@given("the carriers the CAISO case study page shows", target_fixture="page_carriers")
def given_page_carriers() -> list[dict[str, Any]]:
    return _read_page_carriers()


@given("the carriers the CAISO case study file holds", target_fixture="file_carriers")
def given_file_carriers() -> list[dict[str, Any]]:
    return json.loads(MAPPINGS_PATH.read_text(encoding="utf-8"))[CARRIERS_KEY]


@then("the page and the file name the same carriers")
def assert_same_carriers(
    page_carriers: list[dict[str, Any]], file_carriers: list[dict[str, Any]]
) -> None:
    assert page_carriers == file_carriers, (
        f"{PAGE_PATH.name} and {MAPPINGS_PATH.name} state different carriers"
    )


@given(parsers.parse('the CAISO case study page\'s carriers, written to "{path}"'))
def given_page_carriers_written(path: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        yaml.safe_dump({CARRIERS_KEY: _read_page_carriers()}, sort_keys=False), encoding="utf-8"
    )


@given(parsers.parse('the CAISO case study file, copied to "{path}"'))
def given_case_study_file_copied(path: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(MAPPINGS_PATH, target)


@when(parsers.parse('I derive the carrier mappings from "{mappings}" into "{output}"'))
def when_derive_carrier_mappings(
    monkeypatch: pytest.MonkeyPatch, mappings: str, output: str
) -> None:
    invoke_translate(
        monkeypatch,
        "plexos",
        "sienna",
        "derive-plexos-sienna-mappings",
        user_mappings_path=mappings,
        sink_0_output_path=output,
    )


@then(parsers.parse('the derived file "{path}" names {count:d} carriers'))
def assert_derived_carrier_count(path: str, count: int) -> None:
    derived = yaml.safe_load(Path(path).read_text(encoding="utf-8"))[CARRIERS_KEY]
    assert len(derived) == count, f"expected {count} carriers in {path}, got {len(derived)}"
