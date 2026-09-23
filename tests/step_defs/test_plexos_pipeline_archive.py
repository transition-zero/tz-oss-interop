"""Binds the archived PLEXOS pipelines feature.

The model-building steps come from the interop_testing plugin and the file assertions
from the root conftest; this module holds the two translate drivers and the menu step.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pytest_bdd import parsers, scenarios, when

from tests.step_defs.conftest import (
    PLEXOS_MAPPINGS_PATH,
    invoke_translate,
    invoke_translate_cancel_at_pipeline,
)

scenarios("../features/plexos_pipeline_archive.feature")


@when(
    parsers.parse(
        'I start translate and choose source framework "{source}" '
        'destination framework "{destination}"'
    )
)
def start_translate_choose_pair(
    monkeypatch: pytest.MonkeyPatch, source: str, destination: str
) -> None:
    invoke_translate_cancel_at_pipeline(monkeypatch, source, destination)


@when(parsers.parse('I run the archived chain against "{xml_path}" writing "{system_json_path}"'))
def run_archived_chain(
    monkeypatch: pytest.MonkeyPatch, xml_path: str, system_json_path: str
) -> None:
    invoke_translate(
        monkeypatch,
        "plexos",
        "sienna",
        "plexos-to-sienna-via-pypsa",
        user_mappings_path=PLEXOS_MAPPINGS_PATH,
        source_path=str(Path(xml_path)),
        sink_0_output_system_json_file_path=system_json_path,
    )


@when(
    parsers.parse(
        'I run the archived direct pipeline against "{xml_path}" writing "{network_path}"'
    )
)
def run_archived_direct(monkeypatch: pytest.MonkeyPatch, xml_path: str, network_path: str) -> None:
    invoke_translate(
        monkeypatch,
        "plexos",
        "pypsa",
        "plexos-to-pypsa-direct",
        source_path=str(Path(xml_path)),
        sink_0_output_path=network_path,
    )
