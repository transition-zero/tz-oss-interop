"""Drives translate for the sienna → power-simulations pipeline through the REPL.

Assertions on the emitted PS.jl system and its H5 sidecar are published
vocabulary, in ``interop_testing.steps.power_simulations``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from interop_testing.builders.sienna_documents import sienna_extensions_filename, sienna_h5_filename
from pytest_bdd import parsers, when

from tests.step_defs.conftest import invoke_translate


def _invoke_sienna_to_psi(
    monkeypatch: pytest.MonkeyPatch,
    system_path: str,
    pipeline: str,
    json_output: str,
    h5_output: str,
) -> None:
    path = Path(system_path)
    invoke_translate(
        monkeypatch,
        "sienna",
        "power-simulations",
        pipeline,
        source_system_json_path=str(path),
        source_time_series_h5_path=str(path.parent / sienna_h5_filename(path)),
        source_extensions_json_path=str(path.parent / sienna_extensions_filename(path)),
        sink_0_system_json_filepath=json_output,
        sink_0_h5_output_path=h5_output,
    )


@when(
    parsers.parse(
        'I run translate against Sienna system "{system_path}" '
        'pipeline "{pipeline}" json output "{json_output}" h5 output "{h5_output}"'
    )
)
def run_translate_sienna_to_psi(
    monkeypatch: pytest.MonkeyPatch,
    printed_messages: list[str],
    system_path: str,
    pipeline: str,
    json_output: str,
    h5_output: str,
) -> None:
    _invoke_sienna_to_psi(monkeypatch, system_path, pipeline, json_output, h5_output)
    errors = [m for m in printed_messages if "translate failed" in m]
    assert not errors, errors[0]
