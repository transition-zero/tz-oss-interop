from __future__ import annotations

from pathlib import Path

import pytest
from pytest_bdd import parsers, when

from tests.step_defs.conftest import (
    STANDARD_CARRIER_MAP,
    STANDARD_PRIME_MOVER_MAP,
    invoke_translate,
    write_user_mappings,
)

_MAPPINGS_PATH = "user_mappings.yaml"

# The five carriers these scenarios name, taken from the maps every PyPSA scenario shares.
_CARRIERS = ("solar", "onwind", "hydro", "PHS")
_THERMAL_CARRIER = "CCGT"


@pytest.fixture(autouse=True)
def carrier_mappings_file() -> None:
    write_user_mappings(
        {_THERMAL_CARRIER: STANDARD_CARRIER_MAP[_THERMAL_CARRIER]},
        prime_mover={carrier: STANDARD_PRIME_MOVER_MAP[carrier] for carrier in _CARRIERS},
    )


@when(
    parsers.re(
        r"I run the pypsa investments translation"
        r'(?: with sidecar "(?P<extensions_path>[^"]+)")?'
        r' against "(?P<nc_path>[^"]+)" writing "(?P<portfolio_path>[^"]+)"'
    )
)
def run_investments_translation(
    monkeypatch: pytest.MonkeyPatch,
    nc_path: str,
    portfolio_path: str,
    extensions_path: str | None,
) -> None:
    sidecar = {"source_extensions_json_path": str(Path(extensions_path))} if extensions_path else {}
    invoke_translate(
        monkeypatch,
        "pypsa",
        "sienna",
        "pypsa-to-sienna-investments",
        user_mappings_path=_MAPPINGS_PATH,
        source_path=str(Path(nc_path)),
        sink_1_output_path=portfolio_path,
        **sidecar,
    )
