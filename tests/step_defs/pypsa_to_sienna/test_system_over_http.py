from __future__ import annotations

import json
from pathlib import Path

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from tests.step_defs.conftest import invoke_translate

scenarios("../features/pypsa_to_sienna/system_over_http.feature")


@given(parsers.parse('the file "{path}" is served at "{url}"'))
def given_file_served(http_store: dict[str, bytes], path: str, url: str) -> None:
    http_store[url] = Path(path).read_bytes()


@when(
    parsers.parse(
        'I run translate against "{source_url}" with user mappings "{mappings_url}" '
        'writing the system to "{system_url}", the time series to "{h5_url}" '
        'and the extensions to "{extensions_url}"'
    )
)
def run_translate_to_http(
    monkeypatch: pytest.MonkeyPatch,
    source_url: str,
    mappings_url: str,
    system_url: str,
    h5_url: str,
    extensions_url: str,
) -> None:
    invoke_translate(
        monkeypatch,
        "pypsa",
        "sienna",
        "pypsa-to-sienna",
        user_mappings_path=mappings_url,
        source_path=source_url,
        sink_0_output_system_json_file_path=system_url,
        sink_0_output_h5_file_path=h5_url,
        sink_0_output_extensions_file_path=extensions_url,
    )


@then(parsers.parse('the http destination "{url}" parses as JSON with "{key}" set to "{expected}"'))
def assert_http_json_value(http_store: dict[str, bytes], url: str, key: str, expected: str) -> None:
    assert url in http_store, f"expected {url!r} in the stubbed store, got {list(http_store)!r}"
    actual = json.loads(http_store[url])[key]
    assert actual == expected, f"expected {key!r} to be {expected!r} at {url}, got {actual!r}"
