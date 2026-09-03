"""pytest-bdd vocabulary for the working directory a test runs in.

Loading this plugin makes ``isolated_cwd`` autouse, so every test in the
session runs in an empty project of its own. Load it separately from
``interop_testing.steps.files`` if a project manages its own working directory
and wants the assertions without the fixture.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pytest_bdd import given, parsers

from interop_testing.projects import DEFAULT_ADAPTERS_YAML, write_adapters_config


@pytest.fixture(autouse=True)
def isolated_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Run each test in an empty project directory with a baseline adapters.yaml."""
    monkeypatch.chdir(tmp_path)
    write_adapters_config(DEFAULT_ADAPTERS_YAML)
    return tmp_path


@given(parsers.parse('I cd into "{path}"'))
def given_cd_into(path: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(Path(path))


@given(parsers.parse('the environment variable "{name}" is set to "{value}"'))
def given_env_var_set(name: str, value: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(name, value)
