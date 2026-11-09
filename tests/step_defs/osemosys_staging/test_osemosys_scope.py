from __future__ import annotations

from interop_testing import write_pipeline
from pytest_bdd import given, parsers, scenarios

scenarios("osemosys_staging/osemosys_scope.feature")

_SCOPE_PIPELINE_YAML = """\
source_framework: osemosys
destination_framework: osemosys-canonical
source:
  name: stage_osemosys_csv
steps:
  - name: osemosys_canonical_drop_outside_scope
    params:
      locations: [{locations}]
      years: [{years}]
sinks:
  - name: emit_osemosys_canonical_parquet
"""


@given(
    parsers.re(
        r'a pipeline "(?P<name>[^"]+)" that stages an otoole model and keeps the locations '
        r'"(?P<locations>[^"]*)" and the years "(?P<years>[^"]*)"'
    )
)
def given_scope_pipeline(name: str, locations: str, years: str) -> None:
    write_pipeline(
        name,
        _SCOPE_PIPELINE_YAML.format(
            locations=", ".join(locations.split()), years=", ".join(years.split())
        ),
    )
