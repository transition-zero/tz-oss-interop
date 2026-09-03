from pathlib import Path

import pytest
from pytest_bdd import parsers, scenarios, when

from tests.step_defs.conftest import PLEXOS_MAPPINGS_PATH, invoke_translate

scenarios("../features/plexos_to_sienna.feature")


@when(
    parsers.parse(
        'I run the plexos-to-sienna chain against "{xml_path}" writing "{system_json_path}"'
    )
)
def run_plexos_to_sienna(
    monkeypatch: pytest.MonkeyPatch, xml_path: str, system_json_path: str
) -> None:
    invoke_translate(
        monkeypatch,
        "plexos",
        "sienna",
        "plexos-to-sienna",
        user_mappings_path=PLEXOS_MAPPINGS_PATH,
        source_path=str(Path(xml_path)),
        sink_0_output_system_json_file_path=system_json_path,
    )
