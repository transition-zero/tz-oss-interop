"""Binds the plexos_to_pypsa pipeline_assembly feature.

Steps live in the interop_testing plugin (the PLEXOS builder and the PyPSA-network
assertions), the plexos_to_pypsa conftest (the translate driver), and the root conftest
(generic file assertions); this module only wires the scenarios.
"""

from __future__ import annotations

from pathlib import Path

from pytest_bdd import scenarios

FEATURE = (
    Path(__file__).resolve().parents[2]
    / "features"
    / "plexos_to_pypsa"
    / "pipeline_assembly.feature"
)
scenarios(str(FEATURE))
