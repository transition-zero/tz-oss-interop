from pathlib import Path
from typing import NamedTuple, cast

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from tests.step_defs.conftest import load_script

FEATURE = Path(__file__).resolve().parents[1] / "features" / "mutation_scope.feature"
scenarios(str(FEATURE))

REPO_ROOT = Path(__file__).resolve().parents[2]


# mutmut_score imports mutation_scope by name, so mutation_scope must load first.
mutation_scope = load_script("mutation_scope", REPO_ROOT / "scripts" / "mutation_scope.py")
mutmut_score = load_script("mutmut_score", REPO_ROOT / "scripts" / "mutmut_score.py")


class Report(NamedTuple):
    markdown: str
    exit_code: int


def _split(listed: str) -> list[str]:
    return [item.strip() for item in listed.split(",") if item.strip()]


@given(parsers.parse('a pull request that changes "{changed}"'), target_fixture="changed")
def given_changed_files(changed: str) -> list[str]:
    return _split(changed)


@when("CI lists the mutation targets", target_fixture="targets")
def when_list_targets(monkeypatch: pytest.MonkeyPatch, changed: list[str]) -> list[str]:
    monkeypatch.delenv("MUTATION_INCLUDE_FORK_UNSAFE", raising=False)
    return cast(list[str], mutation_scope.list_targets(changed))


@then(parsers.re(r'the mutation targets are "(?P<expected>[^"]*)"'))
def then_targets_are(targets: list[str], expected: str) -> None:
    assert targets == _split(expected), f"expected {expected!r}, got {targets!r}"


@given("a pull request run with no mutation target")
def given_no_target(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_targets(monkeypatch, tmp_path, [])


@given(parsers.parse('a pull request run that targets "{targets}"'))
def given_targets(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, targets: str) -> None:
    _set_targets(monkeypatch, tmp_path, _split(targets))


@given("a run over every file")
def given_run_over_every_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MUTATION_TARGETS_FILE", raising=False)


def _set_targets(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, targets: list[str]) -> None:
    targets_file = tmp_path / "mutation_targets.txt"
    targets_file.write_text("".join(f"{target}\n" for target in targets), encoding="utf-8")
    monkeypatch.setenv("MUTATION_TARGETS_FILE", str(targets_file))


@given("mutmut results that list no mutant")
def given_no_mutant(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mutmut_score, "_run_results", lambda: "")


@given(parsers.parse('mutmut results with the statuses "{statuses}"'))
def given_statuses(monkeypatch: pytest.MonkeyPatch, statuses: str) -> None:
    lines = [
        f"interop.core.runner.x_run__mutmut_{number}: {status}"
        for number, status in enumerate(_split(statuses), start=1)
    ]
    monkeypatch.setattr(mutmut_score, "_run_results", lambda: "\n".join(lines))


@given(parsers.parse('mutmut wrote its mutation data for "{target}"'))
def given_mutation_data(tmp_path: Path, target: str) -> None:
    meta_file = tmp_path / "mutants" / f"{target}.meta"
    meta_file.parent.mkdir(parents=True)
    meta_file.write_text('{"exit_code_by_key": {}}', encoding="utf-8")


@given("no mutmut results")
def given_no_results(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mutmut_score, "_run_results", lambda: None)


@when("CI builds the mutation report", target_fixture="report")
def when_build_report(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Report:
    monkeypatch.chdir(tmp_path)
    report_file = tmp_path / "mutation_score.md"
    monkeypatch.setenv("MUTMUT_SCORE_FILE", str(report_file))
    monkeypatch.delenv("MUTATION_THRESHOLD", raising=False)
    exit_code = cast(int, mutmut_score.main())
    return Report(markdown=report_file.read_text(encoding="utf-8"), exit_code=exit_code)


@then(parsers.parse('the report says "{text}"'))
def then_report_says(report: Report, text: str) -> None:
    assert text in report.markdown, f"expected {text!r} in the report:\n{report.markdown}"


@then(parsers.parse('the report does not say "{text}"'))
def then_report_does_not_say(report: Report, text: str) -> None:
    assert text not in report.markdown, f"expected no {text!r} in the report:\n{report.markdown}"


@then("the report step passes")
def then_report_step_passes(report: Report) -> None:
    assert report.exit_code == 0, f"expected exit 0, got {report.exit_code}:\n{report.markdown}"


@then("the report step fails")
def then_report_step_fails(report: Report) -> None:
    assert report.exit_code != 0, f"expected a non-zero exit:\n{report.markdown}"
