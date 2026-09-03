"""Binds the user_mappings feature.

Two steps taking different UserMappings subclasses are what it takes to show the
loader gathers every schema a pipeline asks for rather than the last one it saw.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from interop_testing import write_project_plugin
from pytest_bdd import given, parsers, scenarios, when

from tests.step_defs.conftest import invoke_translate

FEATURE = Path(__file__).resolve().parents[1] / "features" / "user_mappings.feature"
scenarios(str(FEATURE))


_MAPPING_STEP_TEMPLATE = """\
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep
from interop.core.user_mappings import UserMappings


class _{class_name}Mapping(UserMappings):
    {field}: {field_type}


class _{class_name}Params(BaseModel):
    out: Path


class _{class_name}Step(TranslationStep):
    name: ClassVar[str] = "{plugin_name}"
    params_schema: ClassVar[type[BaseModel] | None] = _{class_name}Params

    def __init__(self, mapping: _{class_name}Mapping) -> None:
        self._mapping = mapping

    def run(self, state: State, params: BaseModel | None) -> State:
        assert isinstance(params, _{class_name}Params)
        params.out.parent.mkdir(parents=True, exist_ok=True)
        params.out.write_text(str(self._mapping.{field}), encoding="utf-8")
        return state
"""


_FIELD_TYPES = {"label": "str", "threshold": "float"}


@given(parsers.parse('a step plugin "{plugin_name}" taking a "{field}" user mapping'))
def given_mapping_step_plugin(plugin_name: str, field: str) -> None:
    write_project_plugin(
        "steps",
        plugin_name,
        _MAPPING_STEP_TEMPLATE.format(
            class_name=field.title(),
            plugin_name=plugin_name,
            field=field,
            field_type=_FIELD_TYPES[field],
        ),
    )


@when(
    parsers.parse(
        'I run translate pipeline "{pipeline}" with mappings "{mappings}" writing "{first_out}"'
    )
)
def when_translate_with_one_mapping(
    monkeypatch: pytest.MonkeyPatch, pipeline: str, mappings: str, first_out: str
) -> None:
    invoke_translate(
        monkeypatch,
        "noop",
        "noop",
        pipeline,
        user_mappings_path=mappings,
        step_0_out=first_out,
    )


@when(
    parsers.parse(
        'I run translate pipeline "{pipeline}" with mappings "{mappings}" '
        'writing "{first_out}" and "{second_out}"'
    )
)
def when_translate_with_two_mappings(
    monkeypatch: pytest.MonkeyPatch,
    pipeline: str,
    mappings: str,
    first_out: str,
    second_out: str,
) -> None:
    invoke_translate(
        monkeypatch,
        "noop",
        "noop",
        pipeline,
        user_mappings_path=mappings,
        step_0_out=first_out,
        step_1_out=second_out,
    )
