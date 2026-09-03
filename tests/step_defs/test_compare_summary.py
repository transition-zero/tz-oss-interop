"""Binds the compare_summary feature.

Compare's own logic — running each side into a scratch directory, reading the two
tables back and joining them — needs nothing more than two frameworks that each have
a results pipeline. The plugins below give it exactly that, so the flow runs end to
end without a PyPSA network or a Sienna system in sight.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import NamedTuple

import polars as pl
import pytest
from interop_testing import write_project_plugin, write_results_pipeline
from pytest_bdd import given, parsers, scenarios, when

from tests.step_defs.conftest import invoke_compare_run

FEATURE = Path(__file__).resolve().parents[1] / "features" / "compare_summary.feature"
scenarios(str(FEATURE))


_WRITE_RESULTS_SINK_PY = """\
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel

from interop.core.pipeline import Sink, State
from interop.ports.outbound.filesystem import FilesystemPort


class _WriteResultsParams(BaseModel):
    output_dir: Path


class _WriteResults(Sink):
    name: ClassVar[str] = "write_results"
    params_schema: ClassVar[type[BaseModel] | None] = _WriteResultsParams

    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def write(self, state: State, params: BaseModel | None) -> None:
        assert isinstance(params, _WriteResultsParams)
        with self._fs.open_write(params.output_dir / "results.parquet") as stream:
            state.destination_tables["results"].write_parquet(stream)
"""


# The rows are staged as parquet rather than baked into this source, so the template
# interpolates a path instead of Python literals.
_RESULTS_SOURCE_TEMPLATE = """\
from pathlib import Path
from typing import ClassVar

import polars as pl

from pydantic import BaseModel

from interop.core.pipeline import StagedSource, State


class _{class_name}(StagedSource):
    name: ClassVar[str] = "{plugin_name}"
    params_schema: ClassVar[type[BaseModel] | None] = None
    prefix: ClassVar[str] = "{plugin_name}"

    def load_into_state(self, params: BaseModel | None, staging_dir: Path) -> State:
        return State(
            staging_dir=staging_dir,
            destination_tables={{"results": pl.read_parquet("{rows_path}")}},
        )
"""

_RESULTS_SCHEMA = {
    "variable": pl.String,
    "component": pl.String,
    "category": pl.String,
    "timestamp": pl.Datetime,
    "value": pl.Float64,
}

_HOURS = (datetime(2026, 1, 1, 0, 0), datetime(2026, 1, 1, 1, 0))

_RESULTS_PIPELINE_TEMPLATE = """\
source_framework: {framework}
destination_framework: results
source:
  name: {source}
sinks:
  - name: write_results
"""


class ResultsFixture(NamedTuple):
    plugin_name: str
    dispatch_by_component: dict[str, list[float]]
    objective: float


def _build_results_frame(fixture: ResultsFixture) -> pl.DataFrame:
    """Two hourly dispatch rows per component, plus one objective row.

    The objective row carries no component, category or timestamp, which is what makes
    it a scalar for the whole run rather than a measurement of something in it.
    """
    rows: list[tuple[str, str | None, str | None, datetime | None, float]] = [
        ("dispatch", component, "coal", hour, value)
        for component, values in fixture.dispatch_by_component.items()
        for hour, value in zip(_HOURS, values, strict=True)
    ]
    rows.append(("objective", None, None, None, fixture.objective))
    return pl.DataFrame(rows, schema=_RESULTS_SCHEMA, orient="row")


def _stage_results_rows(fixture: ResultsFixture) -> Path:
    rows_path = Path.cwd() / "fixtures" / f"{fixture.plugin_name}.parquet"
    rows_path.parent.mkdir(parents=True, exist_ok=True)
    _build_results_frame(fixture).write_parquet(rows_path)
    return rows_path


def _write_results_source(fixture: ResultsFixture) -> None:
    """Write a source plugin that reads its results table back from a staged parquet."""
    rows_path = _stage_results_rows(fixture)
    write_project_plugin(
        "sources",
        fixture.plugin_name,
        _RESULTS_SOURCE_TEMPLATE.format(
            class_name=fixture.plugin_name.title().replace("_", ""),
            plugin_name=fixture.plugin_name,
            rows_path=rows_path.as_posix(),
        ),
    )


def _read_dispatch_table(datatable: list[list[str]]) -> dict[str, list[float]]:
    """A `| component | first | second |` table, as the dispatch values per component."""
    _header, *rows = datatable
    return {component: [float(first), float(second)] for component, first, second in rows}


@given(parsers.parse('a results sink plugin "{name}" writing results.parquet to its output_dir'))
def given_results_sink_plugin(name: str) -> None:
    write_project_plugin("sinks", name, _WRITE_RESULTS_SINK_PY)


@given(parsers.parse('a results source plugin "{name}" costing {objective:f} dispatching:'))
def given_results_source_plugin(name: str, objective: float, datatable: list[list[str]]) -> None:
    _write_results_source(ResultsFixture(name, _read_dispatch_table(datatable), objective))


@given(
    parsers.parse('a results pipeline "{name}" for framework "{framework}" with source "{source}"')
)
def given_results_pipeline(name: str, framework: str, source: str) -> None:
    body = _RESULTS_PIPELINE_TEMPLATE.format(framework=framework, source=source)
    write_results_pipeline(name, body)


@when(
    parsers.parse(
        'I run from the menu a compare of {framework_a} against {framework_b} writing "{output}"'
    )
)
def when_run_compare(
    monkeypatch: pytest.MonkeyPatch, framework_a: str, framework_b: str, output: str
) -> None:
    invoke_compare_run(
        monkeypatch,
        framework_a=framework_a,
        framework_b=framework_b,
        path_answers={"Output path for summary report?": output},
    )
