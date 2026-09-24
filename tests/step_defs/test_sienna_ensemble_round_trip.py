"""Binds the Sienna ensemble round-trip feature.

The model-building steps come from the interop_testing plugin; this module holds the two
translate drivers, one per hop.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pytest_bdd import parsers, scenarios, when

from tests.step_defs.conftest import PLEXOS_MAPPINGS_PATH, invoke_translate

scenarios("../features/sienna_ensemble_round_trip.feature")


@when(parsers.parse('I run the {pipeline} chain against "{xml_path}" writing "{output_dir}"'))
def run_plexos_to_sienna_ensemble(
    monkeypatch: pytest.MonkeyPatch, pipeline: str, xml_path: str, output_dir: str
) -> None:
    invoke_translate(
        monkeypatch,
        "plexos",
        "sienna",
        pipeline,
        user_mappings_path=PLEXOS_MAPPINGS_PATH,
        source_path=str(Path(xml_path)),
        sink_0_output_dir=output_dir,
    )


@when(parsers.parse('I run sienna-to-pypsa-ensemble against "{system_dir}" writing "{output_dir}"'))
def run_sienna_to_pypsa_ensemble(
    monkeypatch: pytest.MonkeyPatch, system_dir: str, output_dir: str
) -> None:
    invoke_translate(
        monkeypatch,
        "sienna",
        "pypsa",
        "sienna-to-pypsa-ensemble",
        source_system_dir=system_dir,
        sink_0_output_dir=output_dir,
    )
