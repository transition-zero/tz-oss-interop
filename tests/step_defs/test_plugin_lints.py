from pathlib import Path

from interop_testing import write_project_plugin
from pytest_bdd import given, parsers, scenarios

FEATURE = Path(__file__).resolve().parents[1] / "features" / "plugin_lints.feature"
scenarios(str(FEATURE))


_SINK_TEMPLATE = """\
from typing import ClassVar

from pydantic import BaseModel

from interop.core.pipeline import Sink, State


class CountBuses{bases}:
    name: ClassVar[str] = "{name}"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def write(self, state: State, params: BaseModel | None) -> None:
        print(state.source_topology["buses"].collect().height)
"""


_FILESYSTEM_TOUCHING_STEP = """\
from typing import ClassVar

from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep


class WriteReport(TranslationStep):
    name: ClassVar[str] = "{name}"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def run(self, state: State, params: BaseModel | None) -> State:
        with open("report.txt", "w", encoding="utf-8") as handle:
            handle.write(", ".join(state.destination_tables))
        return state
"""


_IN_MEMORY_STEP = """\
from typing import ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep


class WriteReport(TranslationStep):
    name: ClassVar[str] = "{name}"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def run(self, state: State, params: BaseModel | None) -> State:
        state.destination_tables["report"] = pl.DataFrame(
            {{"table": sorted(state.destination_tables)}}
        )
        return state
"""


@given(parsers.parse('a project-local sink "{name}" that declares a name but inherits nothing'))
def given_non_inheriting_sink(name: str) -> None:
    write_project_plugin("sinks", name, _SINK_TEMPLATE.format(bases="", name=name))


@given(parsers.parse('a project-local sink "{name}" that inherits Sink'))
def given_inheriting_sink(name: str) -> None:
    write_project_plugin("sinks", name, _SINK_TEMPLATE.format(bases="(Sink)", name=name))


@given(parsers.parse('a project-local step "{name}" that opens a file directly'))
def given_filesystem_touching_step(name: str) -> None:
    write_project_plugin("steps", name, _FILESYSTEM_TOUCHING_STEP.format(name=name))


@given(parsers.parse('a project-local step "{name}" that only transforms state'))
def given_in_memory_step(name: str) -> None:
    write_project_plugin("steps", name, _IN_MEMORY_STEP.format(name=name))
