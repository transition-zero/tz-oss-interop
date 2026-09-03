from pathlib import Path

import pytest
from interop_testing import write_pipeline, write_project_plugin
from pytest_bdd import given, parsers, scenarios, when

from tests.step_defs.conftest import invoke_validate

FEATURE = Path(__file__).resolve().parents[1] / "features" / "validate.feature"
scenarios(str(FEATURE))


_EMIT_TEST_VALIDATION_ERRORS_PY = """\
from typing import ClassVar

from pydantic import BaseModel

from interop.core.pipeline import State, Validator
from interop.core.user_mappings import UserMappings
from interop.ports.outbound.validation import ValidationSeverity


class _CriticalComponents(UserMappings):
    critical_components: list[str]


class _EmitTestValidationErrors(Validator):
    name: ClassVar[str] = "emit_test_validation_errors"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, critical: _CriticalComponents) -> None:
        self._critical = critical

    def validate(self, state: State, params: BaseModel | None) -> None:
        issues = [
            ("Generator", "gen-1", "p_nom", -100.0, "p_nom must be non-negative"),
            ("Load", "load-2", "p_set", 0.0, "p_set is zero; load contributes nothing"),
        ]
        for component, name, attribute, value, message in issues:
            severity = (
                ValidationSeverity.CRITICAL
                if component in self._critical.critical_components
                else ValidationSeverity.WARNING
            )
            self.emit_validation_error(
                state, severity, component, name, message, attribute=attribute, value=value
            )
"""


_VALIDATE_PIPELINE_YAML = """\
source_framework: noop
destination_framework: noop
source:
  name: noop
validators:
  - name: emit_test_validation_errors
"""


_NO_VALIDATORS_PIPELINE_YAML = """\
source_framework: noop
destination_framework: noop
source:
  name: noop
"""


_FLAG_ONE_ISSUE_PY = """\
from typing import ClassVar

from pydantic import BaseModel

from interop.core.pipeline import State, Validator
from interop.ports.outbound.validation import ValidationSeverity


class _FlagOneIssue(Validator):
    name: ClassVar[str] = "flag_one_issue"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def validate(self, state: State, params: BaseModel | None) -> None:
        self.emit_validation_error(
            state,
            ValidationSeverity.CRITICAL,
            "Generator",
            "gen-1",
            "p_nom must be non-negative",
            attribute="p_nom",
            value=-100.0,
        )
"""


_FLAG_ONE_WARNING_PY = """\
from typing import ClassVar

from pydantic import BaseModel

from interop.core.pipeline import State, Validator
from interop.ports.outbound.validation import ValidationSeverity


class _FlagOneWarning(Validator):
    name: ClassVar[str] = "flag_one_warning"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def validate(self, state: State, params: BaseModel | None) -> None:
        self.emit_validation_error(
            state,
            ValidationSeverity.WARNING,
            "Generator",
            "gen-1",
            "p_nom is unusually large",
            attribute="p_nom",
            value=-100.0,
        )
"""


_TRANSLATE_WITH_VALIDATOR_PIPELINE_YAML = """\
source_framework: noop
destination_framework: noop
source:
  name: noop
validators:
  - name: flag_one_issue
sinks:
  - name: emit_json
    params:
      output_path: outputs/system.json
"""


_TRANSLATE_WITH_WARNING_PIPELINE_YAML = """\
source_framework: noop
destination_framework: noop
source:
  name: noop
validators:
  - name: flag_one_warning
sinks:
  - name: emit_json
    params:
      output_path: outputs/system.json
"""


_STEP_NEEDS_MAPPING_PY = """\
from typing import ClassVar

from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep
from interop.core.user_mappings import UserMappings


class _StepMapping(UserMappings):
    threshold: float


class _NeedsMappingStep(TranslationStep):
    name: ClassVar[str] = "needs_mapping_step"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, mapping: _StepMapping) -> None:
        self._mapping = mapping

    def run(self, state: State, params: BaseModel | None) -> State:
        return state
"""


_STEP_NEEDS_MAPPING_PIPELINE_YAML = """\
source_framework: noop
destination_framework: noop
source:
  name: noop
steps:
  - name: needs_mapping_step
validators:
  - name: flag_one_issue
"""


_SOURCE_NEEDS_MAPPING_PY = """\
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel

from interop.core.pipeline import StagedSource, State
from interop.core.user_mappings import UserMappings


class _SourceMapping(UserMappings):
    critical_components: list[str]


class _NeedsMappingSource(StagedSource):
    name: ClassVar[str] = "needs_mapping_source"
    params_schema: ClassVar[type[BaseModel] | None] = None
    prefix: ClassVar[str] = "needsmapping"

    def __init__(self, mapping: _SourceMapping) -> None:
        self._mapping = mapping

    def load_into_state(self, params: BaseModel | None, staging_dir: Path) -> State:
        return State(staging_dir=staging_dir)
"""


_SOURCE_NEEDS_MAPPING_PIPELINE_YAML = """\
source_framework: noop
destination_framework: noop
source:
  name: needs_mapping_source
validators:
  - name: flag_one_issue
"""


_BOOM_STEP_PY = """\
from typing import ClassVar

from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep


class _BoomStep(TranslationStep):
    name: ClassVar[str] = "boom_step"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def run(self, state: State, params: BaseModel | None) -> State:
        raise RuntimeError("boom: step failed on purpose")
"""


_TRANSLATE_BOOM_PIPELINE_YAML = """\
source_framework: noop
destination_framework: noop
source:
  name: noop
validators:
  - name: flag_one_warning
steps:
  - name: boom_step
sinks:
  - name: emit_json
    params:
      output_path: outputs/system.json
"""


_BOOM_VALIDATOR_PY = """\
from typing import ClassVar

from pydantic import BaseModel

from interop.core.pipeline import State, Validator
from interop.ports.outbound.validation import ValidationSeverity


class _BoomValidator(Validator):
    name: ClassVar[str] = "{name}"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def validate(self, state: State, params: BaseModel | None) -> None:
        raise RuntimeError("boom: {name} failed on purpose")
"""


_BOOM_THEN_FLAG_PIPELINE_YAML = """\
source_framework: noop
destination_framework: noop
source:
  name: noop
validators:
  - name: boom_validator
  - name: flag_one_issue
"""


_FLAG_THEN_BOOM_PIPELINE_YAML = """\
source_framework: noop
destination_framework: noop
source:
  name: noop
validators:
  - name: flag_one_issue
  - name: boom_validator
"""


_TWO_BOOMS_PIPELINE_YAML = """\
source_framework: noop
destination_framework: noop
source:
  name: noop
validators:
  - name: boom_validator
  - name: other_boom_validator
"""


_PIPE_VALIDATOR_PY = """\
from typing import ClassVar

from pydantic import BaseModel

from interop.core.pipeline import State, Validator
from interop.ports.outbound.validation import ValidationSeverity


class _PipeValidator(Validator):
    name: ClassVar[str] = "pipe_validator"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def validate(self, state: State, params: BaseModel | None) -> None:
        self.emit_validation_error(
            state,
            ValidationSeverity.CRITICAL,
            "Generator",
            "gen-1",
            "carrier must be one of AC|DC",
            attribute="carrier",
            value="AC|DC",
        )
"""


_PIPE_VALIDATOR_PIPELINE_YAML = """\
source_framework: noop
destination_framework: noop
source:
  name: noop
validators:
  - name: pipe_validator
"""


@given(
    parsers.parse(
        'a validator plugin "emit_test_validation_errors" that flags a generator and a load, '
        "taking severity from a user mapping"
    )
)
def given_emit_test_validation_errors() -> None:
    write_project_plugin(
        "validators", "emit_test_validation_errors", _EMIT_TEST_VALIDATION_ERRORS_PY
    )


@given(parsers.parse('a user mappings file "{path}" marking "{component}" as critical'))
def given_user_mappings_file(path: str, component: str) -> None:
    Path(path).write_text(f"critical_components:\n  - {component}\n", encoding="utf-8")


@given(
    parsers.parse(
        'a project-local pipeline "{name}" with the emit_test_validation_errors validator'
    )
)
def given_validate_pipeline(name: str) -> None:
    write_pipeline(name, _VALIDATE_PIPELINE_YAML)


@given(parsers.parse('a project-local pipeline "{name}" with source noop and no validators'))
def given_no_validators_pipeline(name: str) -> None:
    write_pipeline(name, _NO_VALIDATORS_PIPELINE_YAML)


@given(parsers.parse('a validator plugin "flag_one_issue" that records a single CRITICAL error'))
def given_flag_one_issue() -> None:
    write_project_plugin("validators", "flag_one_issue", _FLAG_ONE_ISSUE_PY)


@given(
    parsers.parse(
        'a project-local pipeline "{name}" that emits JSON and runs the flag_one_issue validator'
    )
)
def given_translate_with_validator_pipeline(name: str) -> None:
    write_pipeline(name, _TRANSLATE_WITH_VALIDATOR_PIPELINE_YAML)


@given(parsers.parse('a validator plugin "flag_one_warning" that records a single WARNING'))
def given_flag_one_warning() -> None:
    write_project_plugin("validators", "flag_one_warning", _FLAG_ONE_WARNING_PY)


@given(
    parsers.parse(
        'a project-local pipeline "{name}" that emits JSON and runs the flag_one_warning validator'
    )
)
def given_translate_with_warning_pipeline(name: str) -> None:
    write_pipeline(name, _TRANSLATE_WITH_WARNING_PIPELINE_YAML)


@given(parsers.parse('a step plugin "{name}" whose constructor consumes a user mapping'))
def given_step_needs_mapping(name: str) -> None:
    write_project_plugin("steps", name, _STEP_NEEDS_MAPPING_PY)


@given(
    parsers.parse(
        'a project-local pipeline "{name}" running that mapping-consuming step '
        "and the flag_one_issue validator"
    )
)
def given_step_needs_mapping_pipeline(name: str) -> None:
    write_pipeline(name, _STEP_NEEDS_MAPPING_PIPELINE_YAML)


@given(parsers.parse('a source plugin "{name}" whose constructor consumes a user mapping'))
def given_source_needs_mapping(name: str) -> None:
    write_project_plugin("sources", name, _SOURCE_NEEDS_MAPPING_PY)


@given(
    parsers.parse(
        'a project-local pipeline "{name}" whose source consumes a mapping '
        "and whose validators do not"
    )
)
def given_source_needs_mapping_pipeline(name: str) -> None:
    write_pipeline(name, _SOURCE_NEEDS_MAPPING_PIPELINE_YAML)


@given(parsers.parse('a step plugin "{name}" that raises when it runs'))
def given_boom_step(name: str) -> None:
    write_project_plugin("steps", name, _BOOM_STEP_PY)


@given(
    parsers.parse(
        'a project-local pipeline "{name}" that runs the flag_one_warning validator '
        "then the failing step"
    )
)
def given_translate_boom_pipeline(name: str) -> None:
    write_pipeline(name, _TRANSLATE_BOOM_PIPELINE_YAML)


@given(parsers.parse('a validator plugin "{name}" that raises when it runs'))
def given_boom_validator(name: str) -> None:
    write_project_plugin("validators", name, _BOOM_VALIDATOR_PY.format(name=name))


@given(
    parsers.parse(
        'a project-local pipeline "{name}" that runs the failing validator '
        "then the flag_one_issue validator"
    )
)
def given_boom_then_flag_pipeline(name: str) -> None:
    write_pipeline(name, _BOOM_THEN_FLAG_PIPELINE_YAML)


@given(
    parsers.parse(
        'a project-local pipeline "{name}" that runs the flag_one_issue validator '
        "then the failing validator"
    )
)
def given_flag_then_boom_pipeline(name: str) -> None:
    write_pipeline(name, _FLAG_THEN_BOOM_PIPELINE_YAML)


@given(parsers.parse('a project-local pipeline "{name}" that runs both failing validators'))
def given_two_booms_pipeline(name: str) -> None:
    write_pipeline(name, _TWO_BOOMS_PIPELINE_YAML)


@given(parsers.parse('a validator plugin "{name}" whose message and value contain pipe characters'))
def given_pipe_validator(name: str) -> None:
    write_project_plugin("validators", name, _PIPE_VALIDATOR_PY)


@given(parsers.parse('a project-local pipeline "{name}" with the pipe_validator validator'))
def given_pipe_validator_pipeline(name: str) -> None:
    write_pipeline(name, _PIPE_VALIDATOR_PIPELINE_YAML)


@given(parsers.parse('a user mappings file "{path}" that omits the critical_components field'))
def given_user_mappings_missing_field(path: str) -> None:
    Path(path).write_text("unrelated_key: value\n", encoding="utf-8")


@when(
    parsers.parse(
        'I run validate with source "{src}" destination "{dst}" pipeline "{pipeline}" '
        'with user mappings "{path}"'
    )
)
def run_validate_with_mappings(
    monkeypatch: pytest.MonkeyPatch, src: str, dst: str, pipeline: str, path: str
) -> None:
    invoke_validate(monkeypatch, src, dst, pipeline, user_mappings_path=path)
