from pathlib import Path

from pytest_bdd import scenarios

FEATURE = Path(__file__).resolve().parents[1] / "features" / "multi_step_pipeline.feature"
scenarios(str(FEATURE))
