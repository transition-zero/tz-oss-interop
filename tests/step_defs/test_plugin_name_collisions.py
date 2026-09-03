from pathlib import Path

from interop_testing import write_pipeline, write_project_plugin
from pytest_bdd import given, parsers, scenarios

FEATURE = Path(__file__).resolve().parents[1] / "features" / "plugin_name_collisions.feature"
scenarios(str(FEATURE))


_SOURCE_TEMPLATE = """\
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel

from interop.core.pipeline import StagedSource, State


class _ProjectLocalSource(StagedSource):
    name: ClassVar[str] = "{source_name}"
    params_schema: ClassVar[type[BaseModel] | None] = None
    prefix: ClassVar[str] = "projlocal"

    def load_into_state(self, params: BaseModel | None, staging_dir: Path) -> State:
        return State(staging_dir=staging_dir)
"""


_SIMPLE_STEP_TEMPLATE = """\
from typing import ClassVar

from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep


class _ProjectLocalStep(TranslationStep):
    name: ClassVar[str] = "{step_name}"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def run(self, state: State, params: BaseModel | None) -> State:
        return state
"""


_PIPELINE_WITH_SOURCE_STEP_TEMPLATE = """\
source_framework: noop
destination_framework: noop
source:
  name: {source_name}
steps:
  - name: {step_name}
sinks:
  - name: noop
"""


@given(parsers.parse('a project-local source "{name}" at "{path}"'))
def given_project_local_source_at(name: str, path: str) -> None:
    full_path = Path.cwd() / path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(_SOURCE_TEMPLATE.format(source_name=name), encoding="utf-8")


@given(parsers.parse('a project-local source "{name}"'))
def given_project_local_source(name: str) -> None:
    write_project_plugin("sources", f"{name}_source", _SOURCE_TEMPLATE.format(source_name=name))


@given(parsers.parse('a project-local step "{name}"'))
def given_project_local_step_simple(name: str) -> None:
    write_project_plugin("steps", f"{name}_step", _SIMPLE_STEP_TEMPLATE.format(step_name=name))


@given(
    parsers.parse(
        'a project-local pipeline "{pipeline_name}" '
        'using the "{source_name}" source and the "{step_name}" step'
    )
)
def given_project_local_pipeline_with_source_and_step(
    pipeline_name: str, source_name: str, step_name: str
) -> None:
    write_pipeline(
        pipeline_name,
        _PIPELINE_WITH_SOURCE_STEP_TEMPLATE.format(source_name=source_name, step_name=step_name),
    )
