from __future__ import annotations

from importlib.metadata import version
from pathlib import Path
from typing import Any, cast

from pytest_bdd import given, parsers, scenarios, then, when

from tests.step_defs.conftest import load_script

FEATURE = Path(__file__).resolve().parents[1] / "features" / "release_wheel_smoke.feature"
scenarios(str(FEATURE))

REPOSITORY = Path(__file__).resolve().parents[2]

smoke_wheel = load_script("smoke_wheel", REPOSITORY / ".github" / "scripts" / "smoke_wheel.py")


@given("the templates the release smoke names", target_fixture="named_templates")
def given_named_templates() -> tuple[str, ...]:
    return cast(tuple[str, ...], smoke_wheel.REQUIRED_TEMPLATES)


@given(parsers.parse('the installed version of "{distribution}"'), target_fixture="distribution")
def given_installed_version(distribution: str) -> str:
    return distribution


@when("the release smoke reads them from the installed package", target_fixture="refusal")
def when_read_templates(named_templates: tuple[str, ...]) -> str:
    templates = smoke_wheel.files("interop") / "templates"
    try:
        for name in named_templates:
            smoke_wheel.reject_unreadable_template(templates, name)
    except SystemExit as refusal:
        return str(refusal)
    return ""


@when("the release smoke counts the files under templates", target_fixture="count")
def when_count_templates() -> int:
    return cast(int, smoke_wheel.count_templates(smoke_wheel.files("interop") / "templates"))


@when(parsers.parse('the release smoke compares it with "{expected}"'), target_fixture="refusal")
def when_compare_with(distribution: str, expected: str) -> str:
    return _compare(distribution, expected)


@when("the release smoke compares it with the same version", target_fixture="refusal")
def when_compare_with_itself(distribution: str) -> str:
    return _compare(distribution, version(distribution))


def _compare(distribution: str, expected: str) -> str:
    try:
        cast(Any, smoke_wheel).reject_wrong_version(distribution, expected)
    except SystemExit as refusal:
        return str(refusal)
    return ""


@then("each one is readable")
def then_each_template_is_readable(refusal: str) -> None:
    assert not refusal, refusal


@then("the count matches the files in the repository")
def then_count_matches_repository(count: int) -> None:
    on_disk = sum(1 for path in (REPOSITORY / "interop" / "templates").rglob("*") if path.is_file())
    assert count == on_disk, f"the smoke counted {count} templates, the repository holds {on_disk}"


@then("the comparison is refused")
def then_comparison_is_refused(refusal: str) -> None:
    assert refusal, "the smoke accepted a version that is not the tag"


@then("the comparison passes")
def then_comparison_passes(refusal: str) -> None:
    assert not refusal, refusal
