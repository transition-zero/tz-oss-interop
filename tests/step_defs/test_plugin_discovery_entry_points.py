from __future__ import annotations

import subprocess
import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path

import pytest
from interop_testing import write_pipeline
from pytest_bdd import given, parsers, scenarios, then, when

FEATURE = Path(__file__).resolve().parents[1] / "features" / "plugin_discovery_entry_points.feature"
scenarios(str(FEATURE))


_FIXTURE_PKG_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "interop_entry_point_pkg"
_FIXTURE_PKG_DIST = "interop-ep-test-pkg"


@pytest.fixture
def installed_entry_point_pkg() -> Iterator[None]:
    # Function-scoped because mid-session editable installs aren't visible to
    # the already-running interpreter via .pth, but their dist-info IS visible
    # to importlib.metadata. Other in-process tests would find the entry point
    # in metadata and crash on ep.load(). Uninstalling before the next test
    # keeps the registry clean. The subprocess this scenario actually
    # exercises starts fresh and reads .pth, so it sees the install correctly.
    subprocess.run(
        ["uv", "pip", "install", "-e", str(_FIXTURE_PKG_DIR)],
        check=True,
        capture_output=True,
        text=True,
    )
    try:
        yield
    finally:
        subprocess.run(
            ["uv", "pip", "uninstall", _FIXTURE_PKG_DIST],
            check=False,
            capture_output=True,
            text=True,
        )


_PIPELINE_WITH_STEP_TEMPLATE = """\
source_framework: noop
destination_framework: noop
source:
  name: noop
steps:
  - name: {step_name}
sinks:
  - name: noop
"""


_HEADLESS_TRANSLATE_SCRIPT = textwrap.dedent("""\
    from interop.di.container import make_container
    from interop.ports.inbound.overrides import NodeOverrides
    from interop.ports.inbound.translate import TranslateUseCase

    with make_container()() as scope:
        use_case = scope.get(TranslateUseCase)
        use_case({src!r}, {dst!r}, {pipeline!r}, overrides=NodeOverrides())
""")


@given("the entry-point fixture package is installed")
def given_entry_point_pkg_installed(installed_entry_point_pkg: None) -> None:
    return None


@given(
    parsers.parse('a project-local pipeline "{pipeline_name}" referencing the "{step_name}" step')
)
def given_pipeline_referencing_step(pipeline_name: str, step_name: str) -> None:
    write_pipeline(pipeline_name, _PIPELINE_WITH_STEP_TEMPLATE.format(step_name=step_name))


@when(
    parsers.parse(
        'I run translate in a subprocess with source "{src}" destination "{dst}" '
        'pipeline "{pipeline}"'
    ),
    target_fixture="subprocess_result",
)
def run_translate_subprocess(src: str, dst: str, pipeline: str) -> subprocess.CompletedProcess[str]:
    script = _HEADLESS_TRANSLATE_SCRIPT.format(src=src, dst=dst, pipeline=pipeline)
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(Path.cwd()),
        capture_output=True,
        text=True,
    )


@then(parsers.parse("the subprocess exit code is {code:d}"))
def assert_subprocess_exit_code(
    subprocess_result: subprocess.CompletedProcess[str], code: int
) -> None:
    assert subprocess_result.returncode == code, (
        f"subprocess exited {subprocess_result.returncode}; "
        f"stdout={subprocess_result.stdout!r} stderr={subprocess_result.stderr!r}"
    )
