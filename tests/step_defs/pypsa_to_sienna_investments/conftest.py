from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pytest_bdd import parsers, when

from tests.step_defs.conftest import invoke_translate

_MAPPINGS_PATH = "user_mappings.yaml"

# carrier -> (sienna_component_type, sienna_prime_mover_type) for the non-thermal targets.
_PRIME_MOVER_CARRIERS: dict[str, tuple[str, str]] = {
    "solar": ("RenewableDispatch", "PVe"),
    "onwind": ("RenewableDispatch", "WT"),
    "hydro": ("HydroDispatch", "HY"),
    "PHS": ("EnergyReservoirStorage", "PS"),
}

# carrier -> (sienna_fuel_type, sienna_prime_mover_type) for the thermal targets.
_THERMAL_CARRIERS: dict[str, tuple[str, str]] = {
    "CCGT": ("NATURAL_GAS", "CC"),
    "coal": ("COAL", "ST"),
}


@pytest.fixture(autouse=True)
def carrier_mappings_file() -> None:
    entries: list[dict[str, str]] = [
        {
            "pypsa_carrier": carrier,
            "sienna_component_type": "ThermalStandard",
            "sienna_fuel_type": fuel,
            "sienna_prime_mover_type": prime_mover,
        }
        for carrier, (fuel, prime_mover) in _THERMAL_CARRIERS.items()
    ]
    entries += [
        {
            "pypsa_carrier": carrier,
            "sienna_component_type": component,
            "sienna_prime_mover_type": prime_mover,
        }
        for carrier, (component, prime_mover) in _PRIME_MOVER_CARRIERS.items()
    ]
    Path(_MAPPINGS_PATH).write_text(
        yaml.dump({"carriers": entries}, sort_keys=False), encoding="utf-8"
    )


@when(
    parsers.parse(
        'I run the pypsa investments translation against "{nc_path}" writing "{portfolio_path}"'
    )
)
def run_investments_translation(
    monkeypatch: pytest.MonkeyPatch, nc_path: str, portfolio_path: str
) -> None:
    invoke_translate(
        monkeypatch,
        "pypsa",
        "sienna",
        "pypsa-to-sienna-investments",
        user_mappings_path=_MAPPINGS_PATH,
        source_path=str(Path(nc_path)),
        sink_1_output_path=portfolio_path,
    )


@when(
    parsers.parse(
        'I run the pypsa investments translation with sidecar "{extensions_path}" '
        'against "{nc_path}" writing "{portfolio_path}"'
    )
)
def run_investments_translation_with_sidecar(
    monkeypatch: pytest.MonkeyPatch, nc_path: str, extensions_path: str, portfolio_path: str
) -> None:
    invoke_translate(
        monkeypatch,
        "pypsa",
        "sienna",
        "pypsa-to-sienna-investments",
        user_mappings_path=_MAPPINGS_PATH,
        source_path=str(Path(nc_path)),
        source_extensions_json_path=str(Path(extensions_path)),
        sink_1_output_path=portfolio_path,
    )
