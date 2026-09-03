from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pytest_bdd import given, parsers, when

from tests.step_defs.conftest import invoke_translate

_STANDARD_CARRIER_MAP: dict[str, tuple[str, str]] = {
    "nuclear": ("NUCLEAR", "ST"),
    "coal": ("COAL", "ST"),
    "lignite": ("COAL", "ST"),
    "CCGT": ("NATURAL_GAS", "CC"),
    "OCGT": ("NATURAL_GAS", "GT"),
    "gas": ("NATURAL_GAS", "CC"),
    "oil": ("DISTILLATE_FUEL_OIL", "GT"),
    "geothermal": ("GEOTHERMAL", "BT"),
    "biomass": ("OTHER_BIOMASS_SOLIDS", "ST"),
    "bioenergy": ("OTHER_BIOMASS_SOLIDS", "ST"),
    "waste": ("MUNICIPAL_WASTE", "ST"),
    "hydrogen": ("OTHER_GAS", "FC"),
}

# carrier -> (sienna_component_type, sienna_prime_mover_type) for the non-thermal generator and
# storage targets translated from the user carrier mapping.
_STANDARD_PRIME_MOVER_MAP: dict[str, tuple[str, str]] = {
    "solar": ("RenewableDispatch", "PVe"),
    "solar-utility": ("RenewableDispatch", "PVe"),
    "onwind": ("RenewableDispatch", "WT"),
    "on-wind": ("RenewableDispatch", "WT"),
    "offwind-ac": ("RenewableDispatch", "WS"),
    "offwind-dc": ("RenewableDispatch", "WS"),
    "off-wind": ("RenewableDispatch", "WS"),
    "solar-rooftop": ("RenewableNonDispatch", "PVe"),
    "hydro": ("HydroDispatch", "HY"),
    "PHS": ("EnergyReservoirStorage", "PS"),
}


def write_user_mappings(
    thermal: dict[str, tuple[str, str]],
    path: Path = Path("user_mappings.yaml"),
    *,
    prime_mover: dict[str, tuple[str, str]] | None = None,
    skipped: dict[str, str] | None = None,
) -> None:
    entries: list[dict[str, str]] = [
        {
            "pypsa_carrier": carrier,
            "sienna_component_type": "ThermalStandard",
            "sienna_fuel_type": fuel_type,
            "sienna_prime_mover_type": prime_mover_type,
        }
        for carrier, (fuel_type, prime_mover_type) in thermal.items()
    ]
    for carrier, (component_type, prime_mover_type) in (prime_mover or {}).items():
        entries.append(
            {
                "pypsa_carrier": carrier,
                "sienna_component_type": component_type,
                "sienna_prime_mover_type": prime_mover_type,
            }
        )
    for carrier, component_type in (skipped or {}).items():
        entries.append({"pypsa_carrier": carrier, "sienna_component_type": component_type})
    path.write_text(yaml.dump({"carriers": entries}, sort_keys=False), encoding="utf-8")


@pytest.fixture(autouse=True)
def default_user_mappings() -> None:
    write_user_mappings(_STANDARD_CARRIER_MAP, prime_mover=_STANDARD_PRIME_MOVER_MAP)


@given("a user mappings file with all standard carriers")
def given_standard_mapping() -> None:
    write_user_mappings(_STANDARD_CARRIER_MAP, prime_mover=_STANDARD_PRIME_MOVER_MAP)


@given(parsers.parse('a user mappings file covering only carrier "{carrier}"'))
def given_mapping_single_carrier(carrier: str) -> None:
    write_user_mappings({carrier: _STANDARD_CARRIER_MAP[carrier]})


@when(
    parsers.parse(
        'I run translate against "{nc_path}" pipeline "{pipeline}" sink output "{sink_output}"'
    )
)
def run_translate_pypsa_to_sienna(
    monkeypatch: pytest.MonkeyPatch,
    nc_path: str,
    pipeline: str,
    sink_output: str,
) -> None:
    invoke_translate(
        monkeypatch,
        "pypsa",
        "sienna",
        pipeline,
        user_mappings_path="user_mappings.yaml",
        source_path=str(Path(nc_path)),
        sink_0_output_system_json_file_path=sink_output,
    )


@when(
    parsers.parse(
        'I run translate against "{nc_path}" with sidecar "{extensions_path}" '
        'pipeline "{pipeline}" sink output "{sink_output}"'
    )
)
def run_translate_with_sidecar(
    monkeypatch: pytest.MonkeyPatch,
    nc_path: str,
    extensions_path: str,
    pipeline: str,
    sink_output: str,
) -> None:
    invoke_translate(
        monkeypatch,
        "pypsa",
        "sienna",
        pipeline,
        user_mappings_path="user_mappings.yaml",
        source_path=str(Path(nc_path)),
        source_extensions_json_path=str(Path(extensions_path)),
        sink_0_output_system_json_file_path=sink_output,
    )
