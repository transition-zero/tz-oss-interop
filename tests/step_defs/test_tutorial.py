from pathlib import Path

import pytest
from pytest_bdd import given, parsers, scenarios, when

from tests.step_defs.conftest import invoke_init, invoke_translate

FEATURE = Path(__file__).resolve().parents[1] / "features" / "tutorial.feature"
scenarios(str(FEATURE))


@given(parsers.parse('I have scaffolded the pypsa example at "{target}"'))
def scaffold_pypsa_example(monkeypatch: pytest.MonkeyPatch, target: str) -> None:
    invoke_init(monkeypatch, target, "pypsa")


@when(parsers.parse('I translate the example network to "{sink_output}"'))
def translate_example_network(monkeypatch: pytest.MonkeyPatch, sink_output: str) -> None:
    invoke_translate(
        monkeypatch,
        "pypsa",
        "sienna",
        "pypsa-to-sienna",
        user_mappings_path="inputs/user_mappings.yaml",
        source_path="inputs/pypsa_network.nc",
        sink_0_output_system_json_file_path=sink_output,
    )


@when(parsers.parse('I translate "{source}" through the "{pipeline}" pipeline to "{sink_output}"'))
def translate_through_pipeline(
    monkeypatch: pytest.MonkeyPatch, source: str, pipeline: str, sink_output: str
) -> None:
    invoke_translate(
        monkeypatch,
        "pypsa",
        "sienna",
        pipeline,
        user_mappings_path="inputs/user_mappings.yaml",
        source_path=source,
        sink_0_output_system_json_file_path=sink_output,
    )


@when(parsers.parse('I run the "{pipeline}" pipeline writing CSVs to "{out_dir}"'))
def translate_example_to_csv(monkeypatch: pytest.MonkeyPatch, pipeline: str, out_dir: str) -> None:
    invoke_translate(
        monkeypatch,
        "pypsa",
        "sienna",
        pipeline,
        user_mappings_path="inputs/user_mappings.yaml",
        source_path="inputs/pypsa_network.nc",
        sink_0_output_dir=out_dir,
    )
