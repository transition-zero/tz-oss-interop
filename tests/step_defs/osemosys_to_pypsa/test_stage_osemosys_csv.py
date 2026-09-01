"""Binds the osemosys_to_pypsa stage_osemosys_csv feature.

Steps live in the interop_testing plugin (the OSeMOSYS builder), the osemosys_to_pypsa
conftest (the stage driver and the assertions on the staged state), and the root conftest
(generic printed-output and log assertions); this module only wires the scenarios.
"""

from __future__ import annotations

from pathlib import Path

from pytest_bdd import scenarios

FEATURE = (
    Path(__file__).resolve().parents[2]
    / "features"
    / "osemosys_to_pypsa"
    / "stage_osemosys_csv.feature"
)

scenarios(str(FEATURE))
