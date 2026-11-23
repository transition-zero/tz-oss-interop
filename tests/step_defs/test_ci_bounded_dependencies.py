from __future__ import annotations

from pathlib import Path
from typing import cast

from pytest_bdd import given, parsers, scenarios, then, when

from tests.step_defs.conftest import load_script

FEATURE = Path(__file__).resolve().parents[1] / "features" / "ci_bounded_dependencies.feature"
scenarios(str(FEATURE))

REPOSITORY = Path(__file__).resolve().parents[2]

bounded_dependencies = load_script(
    "bounded_dependencies", REPOSITORY / ".github" / "scripts" / "bounded_dependencies.py"
)


@given(parsers.parse('the dependency "{dependency}"'), target_fixture="dependencies")
def given_dependency(dependency: str) -> list[str]:
    return [dependency]


@given("the dependencies this project declares", target_fixture="dependencies")
def given_projects_own_dependencies() -> list[str]:
    return cast(list[str], bounded_dependencies.read_dependencies())


@when("CI lists the capped dependencies", target_fixture="capped")
def when_list_capped(dependencies: list[str]) -> list[str]:
    return cast(list[str], bounded_dependencies.list_capped_dependencies(dependencies))


@then(parsers.parse('the list names "{name}"'))
def then_list_names(capped: list[str], name: str) -> None:
    assert capped == [name], f"expected only {name!r}, got {capped!r}"


@then("the list is empty")
def then_list_is_empty(capped: list[str]) -> None:
    assert capped == [], f"expected no capped dependency, got {capped!r}"


@then("the list is not empty")
def then_list_is_not_empty(capped: list[str]) -> None:
    assert capped, "this project declares an upper bound, so the list must name it"


@then("every name it gives carries an upper bound in pyproject.toml")
def then_every_name_is_capped(capped: list[str], dependencies: list[str]) -> None:
    for name in capped:
        declared = next(raw for raw in dependencies if raw.startswith(name))
        assert "<" in declared, f"{name!r} was listed as capped, but {declared!r} has no '<'"
