from pathlib import Path

from pytest_bdd import scenarios

FEATURE = Path(__file__).resolve().parents[1] / "features" / "http_filesystem_round_trip.feature"
scenarios(str(FEATURE))
