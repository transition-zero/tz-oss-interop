from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from tests.step_defs.conftest import join_printed_messages
from tests.step_defs.solve_steps import invoke_expand, invoke_expand_cancelling, invoke_solve

scenarios("../features/solve.feature")


@when(parsers.parse('I dispatch the solve command for "{path}" with network model "{model}"'))
def when_dispatch_solve(monkeypatch: pytest.MonkeyPatch, path: str, model: str) -> None:
    invoke_solve(monkeypatch, path, model)


@when(
    parsers.parse(
        'I dispatch the solve command for "{path}" with network model "{model}" '
        'output directory "{output_dir}" unserved energy "{unserved_energy}" '
        'unit commitment "{unit_commitment}" '
        'solver "{solver}" presolve "{presolve}" '
        'crossover "{crossover}" time limit "{time_limit}"'
    )
)
def when_dispatch_solve_with_every_answer(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    model: str,
    output_dir: str,
    unserved_energy: str,
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
        unserved_energy=unserved_energy,
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


@when(parsers.parse('I dispatch the expand command for "{path}" accepting the download'))
def when_dispatch_expand_accepting_download(monkeypatch: pytest.MonkeyPatch, path: str) -> None:
    invoke_expand(monkeypatch, path, download_consent=True)


@when(parsers.parse('I dispatch the expand command for "{path}" declining the download'))
def when_dispatch_expand_declining_download(monkeypatch: pytest.MonkeyPatch, path: str) -> None:
    invoke_expand(monkeypatch, path, download_consent=False)


@when(
    parsers.parse('I dispatch the expand command for "{path}" and cancel the balance model prompt')
)
def when_expand_cancelling_balance_model(monkeypatch: pytest.MonkeyPatch, path: str) -> None:
    invoke_expand_cancelling(monkeypatch, path, [])


@when(parsers.parse('I dispatch the expand command for "{path}" and cancel the solver prompt'))
def when_expand_cancelling_solver(monkeypatch: pytest.MonkeyPatch, path: str) -> None:
    invoke_expand_cancelling(monkeypatch, path, ["multi-region", "continuous"])


@then(parsers.parse('no prompt follows the select prompt "{message}"'))
def assert_last_prompt(recorded_selects: list[dict[str, Any]], message: str) -> None:
    asked = [record["message"] for record in recorded_selects]
    assert asked and asked[-1] == message, f"expected {message!r} as the last prompt, got {asked}"


_JULIA_CODE_IN_A_DATE = '2030-01-01"); run(`touch pwned`); Date("2030-01-01'


def _write_series_companion(path: str, start: str) -> None:
    companion = Path(path)
    companion.parent.mkdir(parents=True, exist_ok=True)
    document = {"periods": [{"start": start, "end": "2030-12-31"}], "records": []}
    companion.write_text(json.dumps(document), encoding="utf-8")


@given(parsers.parse('a series companion "{path}" whose first period starts with Julia code'))
def given_series_companion_with_julia_code(path: str) -> None:
    _write_series_companion(path, _JULIA_CODE_IN_A_DATE)


@given(parsers.parse('a series companion "{path}" with one period of 2030'))
def given_series_companion_of_2030(path: str) -> None:
    _write_series_companion(path, "2030-01-01")
