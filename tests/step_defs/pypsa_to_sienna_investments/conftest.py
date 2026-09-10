from __future__ import annotations

from pathlib import Path

import pytest
from pytest_bdd import parsers, when

from tests.step_defs.conftest import invoke_translate, write_user_mappings

_MAPPINGS_PATH = "user_mappings.yaml"

# carrier -> (sienna_component_type, sienna_prime_mover_type) for the non-thermal targets.
_PRIME_MOVER_CARRIERS: dict[str, tuple[str, str]] = {
    "solar": ("RenewableDispatch", "PVe"),
    "onwind": ("RenewableDispatch", "WT"),
    "hydro": ("HydroDispatch", "HY"),
    "PHS": ("EnergyReservoirStorage", "PS"),
}

# carrier -> (sienna_fuel_type, sienna_prime_mover_type) for the thermal targets.
_THERMAL_CARRIERS: dict[str, tuple[str, str]] = {"CCGT": ("NATURAL_GAS", "CC")}


@pytest.fixture(autouse=True)
def carrier_mappings_file() -> None:
    write_user_mappings(_THERMAL_CARRIERS, prime_mover=_PRIME_MOVER_CARRIERS)


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
