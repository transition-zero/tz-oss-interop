"""Shared steps for the OSeMOSYS staging BDD scenarios.

Each ``test_<topic>.py`` here binds ``tests/features/osemosys_to_pypsa/<topic>.feature``.
Model-building steps come from the ``interop_testing`` harness; this module holds the
translate driver and the assertions on what the source staged.

A scenario drives a project-local pipeline that stages the model, dumps the staged state to
JSON, and writes the dump path through the shipped ``emit_json`` sink.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from interop_testing import write_pipeline, write_project_plugin
from pytest_bdd import given, parsers, then, when

from tests.step_defs.conftest import invoke_translate

# A dump_state step writes both staged buckets as JSON, so scenarios can assert which bucket
# a frame landed in, what its columns are typed as, and what it holds, without importing
# interop into the step definitions. It collects every frame, which only a fixture this small
# allows: a production step never collects a source_time_series frame.
_DUMP_STATE_STEP_PY = """\
import json
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep


class _DumpStateParams(BaseModel):
    out: Path


def _dump(frame):
    collected = frame.collect()
    return {
        "columns": {name: str(dtype) for name, dtype in collected.schema.items()},
        "rows": collected.to_dicts(),
    }


class _DumpState(TranslationStep):
    name: ClassVar[str] = "dump_state"
    params_schema: ClassVar[type[BaseModel] | None] = _DumpStateParams

    def run(self, state: State, params: BaseModel | None) -> State:
        assert isinstance(params, _DumpStateParams)
        dumped = {
            "topology": {name: _dump(frame) for name, frame in state.source_topology.items()},
            "time_series": {
                f"{owner}/{series}": _dump(frame)
                for (owner, series), frame in state.source_time_series.items()
            },
        }
        params.out.parent.mkdir(parents=True, exist_ok=True)
        params.out.write_text(json.dumps(dumped, default=str), encoding="utf-8")
        return state
"""


_STAGE_PIPELINE_YAML = """\
source_framework: osemosys
destination_framework: pypsa
source:
  name: stage_osemosys_csv
steps:
  - name: dump_state
sinks:
  - name: emit_json
"""


@given('a step plugin "dump_state" that writes the staged state to JSON')
def given_dump_state_step_plugin() -> None:
    write_project_plugin("steps", "dump_state", _DUMP_STATE_STEP_PY)


@given(parsers.parse('a project-local pipeline "{name}" that stages osemosys and dumps the state'))
def given_osemosys_stage_pipeline(name: str) -> None:
    write_pipeline(name, _STAGE_PIPELINE_YAML)


@when(
    parsers.parse(
        'I stage the folder "{folder}" with config "{config}" through "{pipeline}" '
        'dumping to "{out}" with system output "{system_output}"'
    )
)
def run_stage_osemosys(
    monkeypatch: pytest.MonkeyPatch,
    folder: str,
    config: str,
    pipeline: str,
    out: str,
    system_output: str,
) -> None:
    invoke_translate(
        monkeypatch,
        "osemosys",
        "pypsa",
        pipeline,
        source_path=folder,
        source_config_path=config,
        step_0_out=out,
        sink_0_output_path=system_output,
    )


@then(parsers.parse('the state dump "{path}" stages topology table "{table}"'))
def assert_stages_topology_table(path: str, table: str) -> None:
    assert table in _topology(path), (
        f"expected {table!r} staged in {path}; got {_table_names(path)}"
    )


@then(parsers.parse('the state dump "{path}" stages no topology table "{table}"'))
def assert_stages_no_topology_table(path: str, table: str) -> None:
    assert table not in _topology(path), (
        f"expected no {table!r} in {path}; got {_table_names(path)}"
    )


@then(parsers.parse('the state dump "{path}" stages time series "{owner}"/"{series}"'))
def assert_stages_time_series(path: str, owner: str, series: str) -> None:
    keys = _time_series(path)
    assert f"{owner}/{series}" in keys, f"expected {owner}/{series} in {path}; got {list(keys)}"


@then(parsers.parse('the state dump "{path}" stages no time series "{owner}"/"{series}"'))
def assert_stages_no_time_series(path: str, owner: str, series: str) -> None:
    keys = _time_series(path)
    assert f"{owner}/{series}" not in keys, f"expected no {owner}/{series} in {path}"


@then(parsers.parse('the topology table "{table}" in "{path}" has columns "{columns}"'))
def assert_topology_columns(table: str, path: str, columns: str) -> None:
    expected = [column.strip() for column in columns.split(",")]
    actual = list(_topology(path)[table]["columns"])
    assert actual == expected, f"expected columns {expected} in {table}; got {actual}"


@then(parsers.parse('the topology table "{table}" in "{path}" types "{column}" as "{dtype}"'))
def assert_topology_column_type(table: str, path: str, column: str, dtype: str) -> None:
    actual = _topology(path)[table]["columns"][column]
    assert actual == dtype, f"expected {table}.{column} typed {dtype}; got {actual}"


@then(parsers.parse('the topology table "{table}" in "{path}" has {count:d} rows'))
def assert_topology_row_count(table: str, path: str, count: int) -> None:
    rows = _topology(path)[table]["rows"]
    assert len(rows) == count, f"expected {count} rows in {table}; got {len(rows)}"


@then(parsers.parse('the topology table "{table}" in "{path}" holds "{values}"'))
def assert_topology_row(table: str, path: str, values: str) -> None:
    expected = [value.strip() for value in values.split(",")]
    rows = [[str(value) for value in row.values()] for row in _topology(path)[table]["rows"]]
    assert expected in rows, f"expected row {expected} in {table}; got {rows}"


@then(parsers.parse('the time series "{owner}"/"{series}" in "{path}" has {count:d} rows'))
def assert_time_series_row_count(owner: str, series: str, path: str, count: int) -> None:
    rows = _time_series(path)[f"{owner}/{series}"]["rows"]
    assert len(rows) == count, f"expected {count} rows in {owner}/{series}; got {len(rows)}"


@then(parsers.parse('the time series "{owner}"/"{series}" in "{path}" has columns "{columns}"'))
def assert_time_series_columns(owner: str, series: str, path: str, columns: str) -> None:
    expected = [column.strip() for column in columns.split(",")]
    actual = list(_time_series(path)[f"{owner}/{series}"]["columns"])
    assert actual == expected, f"expected columns {expected} in {owner}/{series}; got {actual}"


@then(parsers.parse('the declarations in "{path}" give "{name}" the default {default:g}'))
def assert_declared_default(path: str, name: str, default: float) -> None:
    actual = _declaration(path, name)["default"]
    assert actual == default, f"expected {name} to default to {default}; got {actual}"


@then(parsers.parse('the declarations in "{path}" mark "{name}" as staged'))
def assert_declared_staged(path: str, name: str) -> None:
    assert _declaration(path, name)["is_staged"], f"expected {name} staged"


@then(parsers.parse('the declarations in "{path}" mark "{name}" as not staged'))
def assert_declared_not_staged(path: str, name: str) -> None:
    assert not _declaration(path, name)["is_staged"], f"expected {name} not staged"


def _dumped(path: str) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))
    return loaded


def _topology(path: str) -> dict[str, Any]:
    topology: dict[str, Any] = _dumped(path)["topology"]
    return topology


def _time_series(path: str) -> dict[str, Any]:
    time_series: dict[str, Any] = _dumped(path)["time_series"]
    return time_series


def _table_names(path: str) -> list[str]:
    return sorted(_topology(path))


def _declaration(path: str, name: str) -> dict[str, Any]:
    rows = _topology(path)["declarations"]["rows"]
    matches = [row for row in rows if row["name"] == name]
    assert matches, f"expected a declaration of {name!r}; got {[row['name'] for row in rows]}"
    return dict(matches[0])
