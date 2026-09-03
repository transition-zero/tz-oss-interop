from __future__ import annotations

from pathlib import Path

import pypsa
import pytest
from interop_testing import write_pipeline
from interop_testing.builders.sienna_documents import sienna_extensions_filename, sienna_h5_filename
from pytest_bdd import given, parsers, scenarios, then, when

from tests.step_defs.conftest import invoke_translate

scenarios("../features/sienna_to_pypsa/path_validation.feature")

_PIPELINE_WITH_YAML_SYSTEM_JSON_PATH = """\
source_framework: sienna
destination_framework: pypsa
source:
  name: stage_sienna_system_json
  params:
    system_json_path: {system_json_path}
steps:
  - name: sienna_to_pypsa_map_components
  - name: sienna_to_pypsa_relate_components
sinks:
  - name: emit_pypsa_network
"""


@given(parsers.parse('an existing directory "{name}"'))
def given_existing_directory(name: str) -> None:
    Path(name).mkdir(parents=True, exist_ok=True)


@given(
    parsers.parse('a project-local pipeline "{name}" whose source system_json_path is "{value}"')
)
def given_pipeline_with_yaml_system_json_path(name: str, value: str) -> None:
    write_pipeline(name, _PIPELINE_WITH_YAML_SYSTEM_JSON_PATH.format(system_json_path=value))


def _companion_answers(system_path: Path) -> dict[str, str]:
    return {
        "source_time_series_h5_path": str(system_path.parent / sienna_h5_filename(system_path)),
        "source_extensions_json_path": str(
            system_path.parent / sienna_extensions_filename(system_path)
        ),
    }


@when(
    parsers.parse(
        'I run translate answering "{first}" then "{second}" for the system JSON, '
        'pipeline "{pipeline}", sink output "{nc_output}"'
    )
)
def run_translate_with_system_json_retry(
    monkeypatch: pytest.MonkeyPatch,
    first: str,
    second: str,
    pipeline: str,
    nc_output: str,
) -> None:
    system_path = Path(second)
    invoke_translate(
        monkeypatch,
        "sienna",
        "pypsa",
        pipeline,
        source_system_json_path=[first, second],
        **_companion_answers(system_path),
        sink_0_output_path=nc_output,
    )


@when(
    parsers.parse(
        'I run translate against Sienna system "{system}" pipeline "{pipeline}" '
        'answering "{first}" then "{second}" for the sink output'
    )
)
def run_translate_with_sink_output_retry(
    monkeypatch: pytest.MonkeyPatch,
    system: str,
    pipeline: str,
    first: str,
    second: str,
) -> None:
    system_path = Path(system)
    invoke_translate(
        monkeypatch,
        "sienna",
        "pypsa",
        pipeline,
        source_system_json_path=str(system_path),
        **_companion_answers(system_path),
        sink_0_output_path=[first, second],
    )


@when(
    parsers.parse(
        'I run translate with companions for "{system}" pipeline "{pipeline}" '
        'sink output "{nc_output}"'
    )
)
def run_translate_leaving_system_json_to_yaml(
    monkeypatch: pytest.MonkeyPatch,
    system: str,
    pipeline: str,
    nc_output: str,
) -> None:
    system_path = Path(system)
    invoke_translate(
        monkeypatch,
        "sienna",
        "pypsa",
        pipeline,
        # An explicit empty answer clears the prefilled YAML value so the run falls
        # back to the YAML param itself, which is what this scenario exercises.
        source_system_json_path="",
        **_companion_answers(system_path),
        sink_0_output_path=nc_output,
    )


@then(parsers.parse('the PyPSA network "{path}" has {count:d} bus'))
@then(parsers.parse('the PyPSA network "{path}" has {count:d} buses'))
def assert_network_bus_count(path: str, count: int) -> None:
    network = pypsa.Network(path)
    assert len(network.buses) == count, (
        f"expected {count} buses in {path}, got {len(network.buses)}: {list(network.buses.index)}"
    )


@given(parsers.parse('an extensions sidecar for "{system}" in the old list format'))
def given_legacy_extensions_sidecar(system: str) -> None:
    system_path = Path(system)
    (system_path.parent / sienna_extensions_filename(system_path)).write_text(
        '[{"owner_type": "ACBus", "owner_id": 1, "ext": {"carrier": "AC"}}]', encoding="utf-8"
    )


@when(
    parsers.parse(
        'I run translate against Sienna system "{system}" pipeline "{pipeline}" '
        'with no extensions sidecar, sink output "{nc_output}"'
    )
)
def run_translate_without_extensions(
    monkeypatch: pytest.MonkeyPatch, system: str, pipeline: str, nc_output: str
) -> None:
    system_path = Path(system)
    invoke_translate(
        monkeypatch,
        "sienna",
        "pypsa",
        pipeline,
        source_system_json_path=str(system_path),
        source_time_series_h5_path=str(system_path.parent / sienna_h5_filename(system_path)),
        # A blank answer leaves the optional sidecar unset.
        source_extensions_json_path="",
        sink_0_output_path=nc_output,
    )


@when(
    parsers.parse(
        'I run translate against Sienna system "{system}" pipeline "{pipeline}" '
        'sink output "{nc_output}"'
    )
)
def run_translate_with_companions(
    monkeypatch: pytest.MonkeyPatch, system: str, pipeline: str, nc_output: str
) -> None:
    system_path = Path(system)
    invoke_translate(
        monkeypatch,
        "sienna",
        "pypsa",
        pipeline,
        source_system_json_path=str(system_path),
        **_companion_answers(system_path),
        sink_0_output_path=nc_output,
    )
