from pathlib import Path

from pytest_bdd import scenarios

FEATURE = Path(__file__).resolve().parents[1] / "features" / "translate_observability.feature"
scenarios(str(FEATURE))
