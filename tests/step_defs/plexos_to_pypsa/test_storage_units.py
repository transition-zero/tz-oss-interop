from pathlib import Path

from pytest_bdd import scenarios

FEATURE = (
    Path(__file__).resolve().parents[2] / "features" / "plexos_to_pypsa" / "storage_units.feature"
)
scenarios(str(FEATURE))
