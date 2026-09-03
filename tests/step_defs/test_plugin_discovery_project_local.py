from pathlib import Path

from interop_testing import write_pipeline, write_project_plugin, write_project_plugin_in_subdir
from pytest_bdd import given, parsers, scenarios

FEATURE = (
    Path(__file__).resolve().parents[1] / "features" / "plugin_discovery_project_local.feature"
)
scenarios(str(FEATURE))


_STEP_TEMPLATE = """\
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep


class _MarkerParams(BaseModel):
    path: Path


class MarkerStep(TranslationStep):
    name: ClassVar[str] = "{step_name}"
    params_schema: ClassVar[type[BaseModel] | None] = _MarkerParams

    def run(self, state: State, params: BaseModel | None) -> State:
        assert isinstance(params, _MarkerParams)
        params.path.parent.mkdir(parents=True, exist_ok=True)
        params.path.write_text("marker step ran", encoding="utf-8")
        return state
"""


# `from __future__ import annotations` turns every annotation into a string, so whatever
# reads them later has to resolve the name through the module it was written in. The
# failure this catches is `@dataclass`: it looks up `sys.modules[cls.__module__].__dict__`
# to tell a `ClassVar` annotation from a field, and finds nothing unless the module is
# registered under the name it was loaded as. Pydantic params models in this template do
# not hit that path on their own; `_Marker` is what makes the import fail without the fix.
_POSTPONED_ANNOTATIONS_STEP_TEMPLATE = """\
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep


@dataclass(frozen=True)
class _Marker:
    path: Path


class _MarkerParams(BaseModel):
    path: Path


class PostponedAnnotationsStep(TranslationStep):
    name: ClassVar[str] = "{step_name}"
    params_schema: ClassVar[type[BaseModel] | None] = _MarkerParams

    def run(self, state: State, params: BaseModel | None) -> State:
        assert isinstance(params, _MarkerParams)
        marker = _Marker(path=params.path)
        marker.path.parent.mkdir(parents=True, exist_ok=True)
        marker.path.write_text("marker step ran", encoding="utf-8")
        return state
"""


_PIPELINE_TEMPLATE = """\
source_framework: noop
destination_framework: noop
source:
  name: noop
steps:
  - name: {step_name}
    params:
      path: {marker_path}
sinks:
  - name: noop
"""


@given(
    parsers.parse('a project-local step "{step_name}" that writes "{marker_path}"'),
    target_fixture="marker_path",
)
def given_project_local_step(step_name: str, marker_path: str) -> str:
    write_project_plugin("steps", f"{step_name}_step", _STEP_TEMPLATE.format(step_name=step_name))
    return marker_path


@given(
    parsers.parse(
        'a project-local step "{step_name}" using postponed annotations, writing "{marker_path}"'
    ),
    target_fixture="marker_path",
)
def given_project_local_postponed_annotations_step(step_name: str, marker_path: str) -> str:
    write_project_plugin(
        "steps",
        f"{step_name}_step",
        _POSTPONED_ANNOTATIONS_STEP_TEMPLATE.format(step_name=step_name),
    )
    return marker_path


@given(
    parsers.parse(
        'a project-local step "{step_name}" under sub-directory "{subdir}" '
        'writing to "{marker_path}"'
    ),
    target_fixture="marker_path",
)
def given_project_local_step_in_subdir(step_name: str, subdir: str, marker_path: str) -> str:
    write_project_plugin_in_subdir(
        "steps", subdir, f"{step_name}_step", _STEP_TEMPLATE.format(step_name=step_name)
    )
    return marker_path


@given(parsers.parse('a project-local pipeline "{pipeline_name}" using the "{step_name}" step'))
def given_project_local_pipeline(pipeline_name: str, step_name: str, marker_path: str) -> None:
    write_pipeline(
        pipeline_name,
        _PIPELINE_TEMPLATE.format(step_name=step_name, marker_path=marker_path),
    )
