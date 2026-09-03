from pathlib import Path

from interop_testing import write_pipeline
from pytest_bdd import given, parsers, scenarios

FEATURE = Path(__file__).resolve().parents[1] / "features" / "pipeline_validation_errors.feature"
scenarios(str(FEATURE))


_NOOP_WITH_PARAMS_PIPELINE = """\
source_framework: noop
destination_framework: noop
source:
  name: noop
  params:
    unused: value
sinks:
  - name: noop
"""


@given(
    parsers.parse(
        'a project-local pipeline "{pipeline_name}" that supplies params to its noop source'
    )
)
def given_pipeline_with_source_params(pipeline_name: str) -> None:
    write_pipeline(pipeline_name, _NOOP_WITH_PARAMS_PIPELINE)
