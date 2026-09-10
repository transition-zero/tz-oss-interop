from pathlib import Path

import pytest
from pytest_bdd import parsers, scenarios, when

from tests.step_defs.conftest import PLEXOS_MAPPINGS_PATH, invoke_translate

scenarios("../features/plexos_to_sienna_investments.feature")


@when(
    parsers.parse(
        'I run the plexos-to-sienna-investments chain against "{xml_path}" '
        'writing "{portfolio_path}"'
    )
)
def run_plexos_to_sienna_investments(
    monkeypatch: pytest.MonkeyPatch, xml_path: str, portfolio_path: str
) -> None:
    invoke_translate(
        monkeypatch,
        "plexos",
        "sienna",
        "plexos-to-sienna-investments",
        user_mappings_path=PLEXOS_MAPPINGS_PATH,
        source_path=str(Path(xml_path)),
        sink_1_output_path=portfolio_path,
    )
