import pytest
from pytest_bdd import parsers, scenarios, then, when

from tests.step_defs.conftest import invoke_expand, invoke_solve, join_printed_messages

scenarios("../features/solve.feature")


@when(parsers.parse('I dispatch the solve command for "{path}" with network model "{model}"'))
def when_dispatch_solve(monkeypatch: pytest.MonkeyPatch, path: str, model: str) -> None:
    invoke_solve(monkeypatch, path, model)


@when(
    parsers.parse(
        'I dispatch the solve command for "{path}" with network model "{model}" '
        'output directory "{output_dir}" unit commitment "{unit_commitment}" '
        'solver "{solver}" presolve "{presolve}" '
        'crossover "{crossover}" time limit "{time_limit}"'
    )
)
def when_dispatch_solve_with_every_answer(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    model: str,
    output_dir: str,
    unit_commitment: str,
    solver: str,
    presolve: str,
    crossover: str,
    time_limit: str,
) -> None:
    invoke_solve(
        monkeypatch,
        path,
        model,
        output_dir=output_dir,
        unit_commitment=unit_commitment,
        solver=solver,
        presolve=presolve,
        run_crossover=crossover,
        time_limit_seconds=time_limit,
    )


@when(parsers.parse('I dispatch the solve command for "{path}" accepting the download'))
def when_dispatch_solve_accepting_download(monkeypatch: pytest.MonkeyPatch, path: str) -> None:
    invoke_solve(monkeypatch, path, "dcp", download_consent=True)


@when(parsers.parse('I dispatch the solve command for "{path}" declining the download'))
def when_dispatch_solve_declining_download(monkeypatch: pytest.MonkeyPatch, path: str) -> None:
    invoke_solve(monkeypatch, path, "dcp", download_consent=False)


@then(parsers.parse('a user error is printed containing "{text}"'))
def then_user_error_contains(printed_messages: list[str], text: str) -> None:
    combined = join_printed_messages(printed_messages)
    assert text in combined, f"expected error {text!r} in printed output, got: {combined!r}"


@when(parsers.re(r'I dispatch the expand command for "(?P<path>[^"]+)"$'))
def when_dispatch_expand(monkeypatch: pytest.MonkeyPatch, path: str) -> None:
    invoke_expand(monkeypatch, path)


@when(
    parsers.re(
        r'I dispatch the expand command for "(?P<path>[^"]+)" '
        r'with balance model "(?P<balance_model>[^"]+)" '
        r'output directory "(?P<output_dir>[^"]+)" '
        r'investment treatment "(?P<investment_treatment>[^"]+)" '
        r'discount rate "(?P<discount_rate>[^"]*)" solver "(?P<solver>[^"]+)" '
        r'presolve "(?P<presolve>[^"]+)" crossover "(?P<crossover>[^"]+)" '
        r'time limit "(?P<time_limit>[^"]*)"'
    )
)
def when_dispatch_expand_with_every_answer(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    balance_model: str,
    output_dir: str,
    investment_treatment: str,
    discount_rate: str,
    solver: str,
    presolve: str,
    crossover: str,
    time_limit: str,
) -> None:
    invoke_expand(
        monkeypatch,
        path,
        balance_model=balance_model,
        output_dir=output_dir,
        investment_treatment=investment_treatment,
        discount_rate=discount_rate,
        solver=solver,
        presolve=presolve,
        run_crossover=crossover,
        time_limit_seconds=time_limit,
    )
