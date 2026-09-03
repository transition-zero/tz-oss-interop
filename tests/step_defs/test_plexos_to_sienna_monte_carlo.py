from pathlib import Path

import pytest
from pytest_bdd import parsers, scenarios, when

from tests.step_defs.conftest import PLEXOS_MAPPINGS_PATH, invoke_translate

scenarios("../features/plexos_to_sienna_monte_carlo.feature")


@when(
    parsers.parse(
        'I run the {pipeline} chain against "{xml_path}" writing "{output_dir}"',
    )
)
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
