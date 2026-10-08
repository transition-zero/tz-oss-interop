import sys
from pathlib import Path
from typing import NamedTuple, cast

from pytest_bdd import given, parsers, scenarios, then, when

from tests.step_defs.conftest import load_script

FEATURE = Path(__file__).resolve().parents[1] / "features" / "ci_python_matrix.feature"
scenarios(str(FEATURE))


python_versions = load_script(
    "python_versions",
    Path(__file__).resolve().parents[2] / ".github" / "scripts" / "python_versions.py",
)


class Derivation(NamedTuple):
    versions: list[str]
    refusal: str


@given(parsers.parse('the requires-python specifier "{specifier}"'), target_fixture="specifier")
def given_specifier(specifier: str) -> str:
    return specifier


@given("the requires-python specifier this project declares", target_fixture="specifier")
def given_projects_own_specifier() -> str:
    return cast(str, python_versions.read_requires_python())


@when("CI derives the Python matrix", target_fixture="derivation")
def when_derive_matrix(specifier: str) -> Derivation:
    try:
        versions = cast(list[str], python_versions.derive_supported_versions(specifier))
    except ValueError as refusal:
        return Derivation(versions=[], refusal=str(refusal))
    return Derivation(versions=versions, refusal="")


@then(parsers.parse('the matrix is "{matrix}"'))
def then_matrix_is(derivation: Derivation, matrix: str) -> None:
    assert derivation.versions == matrix.split(", "), (
        f"expected matrix {matrix!r}, got {derivation.versions!r} ({derivation.refusal!r})"
    )


@then("the matrix is not empty")
def then_matrix_is_not_empty(derivation: Derivation) -> None:
    assert derivation.versions, f"no matrix derived: {derivation.refusal!r}"


@then(parsers.parse('the newest supported version is "{latest}"'))
def then_newest_version_is(derivation: Derivation, latest: str) -> None:
    assert derivation.versions[-1] == latest, (
        f"expected newest {latest!r}, got {derivation.versions!r}"
    )


@then(parsers.parse('the derivation is refused with "{reason}"'))
def then_derivation_is_refused(derivation: Derivation, reason: str) -> None:
    assert reason in derivation.refusal, (
        f"expected refusal mentioning {reason!r}, got {derivation.refusal!r} "
        f"(matrix {derivation.versions!r})"
    )


@then("the matrix names the version the tests are running on")
def then_matrix_names_running_version(derivation: Derivation) -> None:
    running = f"{sys.version_info.major}.{sys.version_info.minor}"
    assert running in derivation.versions, (
        f"CI runs {running}, which requires-python does not admit: {derivation.versions!r}"
    )
