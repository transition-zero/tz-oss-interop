"""Binds the plexos_to_pypsa map_components feature.

Steps live in the shared PLEXOS builder plugin (Given), the plexos_to_pypsa conftest
(the translate driver and PyPSA-network assertions), and the root conftest (generic
file assertions); this module only wires the scenarios.
"""

from __future__ import annotations

from pathlib import Path

from pytest_bdd import scenarios

FEATURE = (
    Path(__file__).resolve().parents[2] / "features" / "plexos_to_pypsa" / "map_components.feature"
)
scenarios(str(FEATURE))
