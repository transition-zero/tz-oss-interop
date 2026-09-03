from interop_testing import write_pipeline, write_project_plugin
from pytest_bdd import given, parsers, scenarios

scenarios("../features/emit_results_parquet.feature")


_RESULTS_SOURCE_PY = """\
from datetime import datetime
from pathlib import Path
from typing import ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import StagedSource, State


class _ResultsFixture(StagedSource):
    name: ClassVar[str] = "results_fixture"
    params_schema: ClassVar[type[BaseModel] | None] = None
    prefix: ClassVar[str] = "results-fixture"

    def load_into_state(self, params: BaseModel | None, staging_dir: Path) -> State:
        results = pl.DataFrame(
            {
                "variable": ["dispatch", "load"],
                "component": ["gen_a", "load_a"],
                "category": ["coal", None],
                "timestamp": [datetime(2030, 1, 1), datetime(2030, 1, 1)],
                "value": [100.0, 80.0],
            }
        )
        return State(staging_dir=staging_dir, destination_tables={"results": results})
"""


_RESULTS_PIPELINE = """\
source_framework: noop
destination_framework: noop
source:
  name: results_fixture
sinks:
  - name: emit_results_parquet
    params:
      output_dir: outputs
      framework: pypsa
      label: demo run
      timezone: Europe/London
      source_artifact: network.nc
"""


@given('a source plugin "results_fixture" seeding a results table')
def given_results_fixture_source() -> None:
    write_project_plugin("sources", "results_fixture", _RESULTS_SOURCE_PY)


@given(
    parsers.parse(
        'a pipeline "{name}" with source "results_fixture" and sink "emit_results_parquet"'
    )
)
def given_results_pipeline(name: str) -> None:
    write_pipeline(name, _RESULTS_PIPELINE)
