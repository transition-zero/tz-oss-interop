from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pytest_bdd import parsers, when

from tests.step_defs.conftest import invoke_validate


@pytest.fixture(autouse=True)
def pipeline_user_mappings() -> None:
    """Provide a minimal user_mappings.yaml for the validator runs.

    The pypsa-to-sienna pipeline's translation step declares a CarrierMappings requirement, so
    `validate` loads a user mappings file even though the validators themselves do not use it.
    A minimal file satisfies the loader; validate never runs the translation step.
    """
    Path("user_mappings.yaml").write_text(
        yaml.dump(
            {
                "carriers": [
                    {
                        "pypsa_carrier": "coal",
                        "sienna_component_type": "ThermalStandard",
                        "sienna_fuel_type": "COAL",
                        "sienna_prime_mover_type": "ST",
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


@when(parsers.parse('I run validate against "{nc_path}" pipeline "{pipeline}"'))
def run_validate_pypsa(
    monkeypatch: pytest.MonkeyPatch,
    nc_path: str,
    pipeline: str,
) -> None:
    invoke_validate(
        monkeypatch,
        "pypsa",
        "sienna",
        pipeline,
        user_mappings_path="user_mappings.yaml",
        source_path=str(Path(nc_path)),
    )
