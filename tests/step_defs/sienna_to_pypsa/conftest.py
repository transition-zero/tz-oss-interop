from __future__ import annotations

from pathlib import Path

import pytest
from interop_testing.builders.sienna_documents import sienna_extensions_filename, sienna_h5_filename
from pytest_bdd import parsers, when

from tests.step_defs.conftest import invoke_translate


def _invoke_translate_sienna_to_pypsa(
    monkeypatch: pytest.MonkeyPatch,
    json_path: str,
    pipeline: str,
    nc_output: str,
) -> None:
    system_path = Path(json_path)
    invoke_translate(
        monkeypatch,
        "sienna",
        "pypsa",
        pipeline,
        source_system_json_path=str(system_path),
        source_time_series_h5_path=str(system_path.parent / sienna_h5_filename(system_path)),
        source_extensions_json_path=str(
            system_path.parent / sienna_extensions_filename(system_path)
        ),
        sink_0_output_path=nc_output,
    )


@when(
    parsers.parse(
        'I run translate against "{json_path}" pipeline "{pipeline}" writing PyPSA to "{nc_output}"'
    )
)
def run_translate_sienna_to_pypsa(
    monkeypatch: pytest.MonkeyPatch,
    json_path: str,
    pipeline: str,
    nc_output: str,
) -> None:
    _invoke_translate_sienna_to_pypsa(monkeypatch, json_path, pipeline, nc_output)


@when(
    parsers.parse(
        'I run translate against Sienna system "{system_path}" '
        'pipeline "{pipeline}" sink output "{nc_output}"'
    )
)
def run_translate_sienna_system_to_pypsa(
    monkeypatch: pytest.MonkeyPatch,
    system_path: str,
    pipeline: str,
    nc_output: str,
) -> None:
    _invoke_translate_sienna_to_pypsa(monkeypatch, system_path, pipeline, nc_output)
