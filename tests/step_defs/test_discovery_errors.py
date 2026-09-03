from pathlib import Path

from interop_testing import write_project_plugin
from pytest_bdd import given, scenarios

FEATURE = Path(__file__).resolve().parents[1] / "features" / "discovery_errors.feature"
scenarios(str(FEATURE))


_BAD_SOURCE_PY = """\
from typing import ClassVar


class BadSource:
    name: ClassVar[str] = "bad_source"
"""


_BAD_ADAPTER_PY = """\
from typing import ClassVar


class BadAdapter:
    name: ClassVar[str] = "bad_adapter"
"""


@given('a project-local source plugin "bad_source" that does not inherit from Source')
def given_bad_source() -> None:
    write_project_plugin("sources", "bad_source", _BAD_SOURCE_PY)


@given('a project-local adapter plugin "bad_adapter" without a port attribute')
def given_bad_adapter() -> None:
    write_project_plugin("adapters", "bad_adapter", _BAD_ADAPTER_PY)
