from __future__ import annotations

from pathlib import Path

import polars as pl
from interop_testing import write_pipeline, write_project_plugin
from pytest_bdd import given, parsers, scenarios, then

scenarios("osemosys_staging/otoole_staging.feature")

_DEFAULTS_TABLE = Path("metadata") / "defaults.parquet"
_PARAMETER_COLUMN = "parameter"

_STATE_PROBE_STEP_PY = """\
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep


class _StateProbeParams(BaseModel):
    out: Path


class _StateProbe(TranslationStep):
    name: ClassVar[str] = "state_probe"
    params_schema: ClassVar[type[BaseModel] | None] = _StateProbeParams

    def run(self, state: State, params: BaseModel | None) -> State:
        assert isinstance(params, _StateProbeParams)
        lines = [f"time series {kind}/{name}" for kind, name in state.source_time_series]
        lines += [f"topology {key}" for key in state.source_topology]
        params.out.parent.mkdir(parents=True, exist_ok=True)
        params.out.write_text("\\n".join(sorted(lines)) + "\\n", encoding="utf-8")
        return state
"""

_PROBE_PIPELINE_YAML = """\
source_framework: osemosys
destination_framework: osemosys-canonical
source:
  name: stage_osemosys_csv
steps:
  - name: state_probe
    params:
      out: {out}
sinks:
  - name: emit_osemosys_canonical_parquet
"""


@given(
    parsers.parse(
        'a pipeline "{name}" that stages an otoole model and writes the keys of its state to '
        '"{out}"'
    )
)
def given_state_probe_pipeline(name: str, out: str) -> None:
    write_project_plugin("steps", "state_probe", _STATE_PROBE_STEP_PY)
    write_pipeline(name, _PROBE_PIPELINE_YAML.format(out=out))


@then(parsers.parse('the canonical defaults in "{directory}" have the rows:'))
def assert_canonical_defaults(directory: str, datatable: list[list[str]]) -> None:
    """Compare only the rows whose parameter the table names; an empty cell is a null."""
    header, *expected = datatable
    defaults = pl.read_parquet(Path(directory) / _DEFAULTS_TABLE)
    names = [row[header.index(_PARAMETER_COLUMN)] for row in expected]
    found = defaults.filter(pl.col(_PARAMETER_COLUMN).is_in(names)).select(header)
    actual = [["" if cell is None else str(cell) for cell in row] for row in found.rows()]
    assert sorted(actual) == sorted(expected), f"expected defaults {expected}, got {actual}"
