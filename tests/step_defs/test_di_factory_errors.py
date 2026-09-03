from pathlib import Path

from interop_testing import write_pipeline
from pytest_bdd import given, parsers, scenarios

FEATURE = Path(__file__).resolve().parents[1] / "features" / "di_factory_errors.feature"
scenarios(str(FEATURE))


_PIPELINE_TEMPLATE = """\
source_framework: noop
destination_framework: noop
source:
  name: noop
steps:
  - name: {step_name}
sinks:
  - name: noop
"""


@given(parsers.parse('a project-local pipeline "{pipeline_name}" referencing step "{step_name}"'))
def given_pipeline_referencing_step(pipeline_name: str, step_name: str) -> None:
    write_pipeline(pipeline_name, _PIPELINE_TEMPLATE.format(step_name=step_name))
