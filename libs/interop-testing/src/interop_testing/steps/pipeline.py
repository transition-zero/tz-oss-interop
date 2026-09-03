"""pytest-bdd vocabulary for running a pipeline and asserting on its exit code.

The When step runs the pipeline in-process through ``run_pipeline`` and exposes
its exit code as the ``pipeline_exit_code`` fixture. Overrides and a user
mappings file are optional clauses on the same step:

    When I run the pipeline "pypsa-to-sienna" with overrides "source.path=in.nc"
    When I run the pipeline "my-pipeline" with user mappings "user_mappings.yaml"
"""

from __future__ import annotations

import shlex

import pytest
from pytest_bdd import parsers, then, when

from interop_testing.pipeline_driver import run_pipeline


@when(
    parsers.re(
        r'I run the pipeline "(?P<pipeline>[^"]+)"'
        r'(?: with overrides "(?P<overrides>[^"]*)")?'
        r'(?: with user mappings "(?P<user_mappings_path>[^"]*)")?$'
    ),
    target_fixture="pipeline_exit_code",
)
def run_the_pipeline(pipeline: str, overrides: str | None, user_mappings_path: str | None) -> int:
    return run_pipeline(
        pipeline,
        overrides=shlex.split(overrides) if overrides else (),
        user_mappings_path=user_mappings_path,
    )


@then(parsers.parse("the pipeline exit code is {code:d}"))
def assert_pipeline_exit_code(pipeline_exit_code: int, code: int) -> None:
    assert pipeline_exit_code == code, f"expected exit code {code}, got {pipeline_exit_code}"


@then(parsers.parse('the log contains "{expected}"'))
def assert_log_contains(caplog: pytest.LogCaptureFixture, expected: str) -> None:
    # A failing run reports itself through the log, so this is how a scenario
    # reads the reason behind a non-zero exit code.
    # Logged paths carry the platform's own separator, so compare in one style.
    logged = caplog.text.replace("\\", "/")
    assert expected in logged, f"expected {expected!r} in log, got {caplog.text!r}"
