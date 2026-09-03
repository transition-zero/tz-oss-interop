import json
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from tests.step_defs.conftest import invoke_compare_run, invoke_run, replay_compare_run

FEATURE = Path(__file__).resolve().parents[1] / "features" / "history.feature"
scenarios(str(FEATURE))


_RECORDED_TRANSLATE: dict[str, str] = {
    "command": "translate",
    "timestamp": "2026-05-20T12:00:00+00:00",
}


def _write_history(isolated_history: Path, invocations: list[dict[str, Any]]) -> None:
    isolated_history.parent.mkdir(parents=True, exist_ok=True)
    isolated_history.write_text(json.dumps({"invocations": invocations}), encoding="utf-8")


@given("a recorded translate invocation in my history")
def given_recorded_translate(isolated_history: Path) -> None:
    _write_history(isolated_history, [_RECORDED_TRANSLATE])


@given(
    parsers.parse(
        'a recorded translate of pipeline "{pipeline}" with sink output "{output}" in my history'
    ),
    target_fixture="recorded_invocation",
)
def given_recorded_detailed_translate(
    isolated_history: Path, pipeline: str, output: str
) -> dict[str, Any]:
    invocation: dict[str, Any] = {
        "command": "translate",
        "timestamp": "2026-05-20T12:00:00+00:00",
        "details": {
            "source_framework": "noop",
            "destination_framework": "noop",
            "pipeline_name": pipeline,
            "source_overrides": {},
            "step_overrides": {},
            "sink_overrides": {"0": {"output_path": output}},
        },
    }
    _write_history(isolated_history, [invocation])
    return invocation


@given(
    parsers.parse('a recorded init of target "{target}" in my history'),
    target_fixture="recorded_invocation",
)
def given_recorded_init(isolated_history: Path, target: str) -> dict[str, Any]:
    invocation: dict[str, Any] = {
        "command": "init",
        "timestamp": "2026-05-20T12:00:00+00:00",
        "details": {"target": target},
    }
    _write_history(isolated_history, [invocation])
    return invocation


@when("I open the history menu with no previous runs")
def when_open_history_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    invoke_run(monkeypatch, ["history", "quit"])


@when(
    parsers.parse(
        'I re-run the recorded translate with source "{src}" '
        'destination "{dst}" pipeline "{pipeline}"'
    )
)
def when_rerun_recorded_translate(
    monkeypatch: pytest.MonkeyPatch, src: str, dst: str, pipeline: str
) -> None:
    invoke_run(
        monkeypatch,
        [
            "history",
            _RECORDED_TRANSLATE,
            src,
            dst,
            pipeline,
            "quit",
        ],
    )


@when(
    parsers.parse(
        'I run from the menu a translate with source "{src}" destination "{dst}" '
        'pipeline "{pipeline}" sink output "{output}"'
    )
)
def when_run_translate_from_menu(
    monkeypatch: pytest.MonkeyPatch, src: str, dst: str, pipeline: str, output: str
) -> None:
    invoke_run(
        monkeypatch,
        ["translate", src, dst, pipeline, "quit"],
        sink_0_output_path=output,
    )


@when("I view the history menu")
def when_view_history_menu(monkeypatch: pytest.MonkeyPatch) -> None:
    invoke_run(monkeypatch, ["history", None, "quit"])


@when(
    parsers.parse(
        'I replay the recorded translate accepting source "{src}" '
        'destination "{dst}" pipeline "{pipeline}"'
    )
)
def when_replay_recorded_translate(
    monkeypatch: pytest.MonkeyPatch,
    recorded_invocation: dict[str, Any],
    src: str,
    dst: str,
    pipeline: str,
) -> None:
    invoke_run(monkeypatch, ["history", recorded_invocation, src, dst, pipeline, "quit"])


@when("I replay the recorded init invocation")
def when_replay_recorded_init(
    monkeypatch: pytest.MonkeyPatch, recorded_invocation: dict[str, Any]
) -> None:
    # The replayed init re-prompts target (text) then the example (select);
    # "none" answers the example prompt before the menu loop's final "quit".
    invoke_run(monkeypatch, ["history", recorded_invocation, "none", "quit"])


@given(
    parsers.parse('a recorded solve of "{path}" with network model "{model}" in my history'),
    target_fixture="recorded_invocation",
)
def given_recorded_solve(isolated_history: Path, path: str, model: str) -> dict[str, Any]:
    invocation: dict[str, Any] = {
        "command": "solve",
        "timestamp": "2026-05-20T12:00:00+00:00",
        "details": {
            "sienna_json_path": path,
            "network_model": model,
            "output_dir": "solved",
        },
    }
    _write_history(isolated_history, [invocation])
    return invocation


_COMPARE_PYPSA_PATH = "inputs/network.nc"
_COMPARE_SYSTEM_PATH = "inputs/system.json"
_COMPARE_EXTENSIONS_PATH = "inputs/system_extensions.json"
_COMPARE_RESULTS_DIR = "inputs/results"
_COMPARE_OUTPUT_PATH = "outputs/comparison_summary.md"


def _setup_compare_files() -> None:
    """Create the source paths the compare prompts validate against.

    The compare flow validates each side's source paths before it runs, so the files
    only need to exist for the prompts to accept them. The translate compare then
    drives is expected to fail on these placeholder inputs; the REPL reports that
    without taking the shell down, so history still records the answers and replays
    the recorded prompt defaults.
    """
    Path("inputs").mkdir(parents=True, exist_ok=True)
    Path(_COMPARE_PYPSA_PATH).write_bytes(b"")
    Path(_COMPARE_SYSTEM_PATH).write_text("{}", encoding="utf-8")
    Path(_COMPARE_EXTENSIONS_PATH).write_text("[]", encoding="utf-8")
    Path(_COMPARE_RESULTS_DIR).mkdir(parents=True, exist_ok=True)


def _compare_details() -> dict[str, Any]:
    return {
        "side_a_framework": "pypsa",
        "side_a_pipeline": "pypsa-to-results",
        "side_a_params": {"path": _COMPARE_PYPSA_PATH},
        "side_b_framework": "sienna",
        "side_b_pipeline": "sienna-to-results",
        "side_b_params": {
            "system_json_path": _COMPARE_SYSTEM_PATH,
            "extensions_json_path": _COMPARE_EXTENSIONS_PATH,
            "results_dir": _COMPARE_RESULTS_DIR,
        },
        "output_path": _COMPARE_OUTPUT_PATH,
    }


@given("a compare-ready working directory")
def given_compare_ready() -> None:
    _setup_compare_files()


@given(
    "a recorded compare of pypsa against sienna in my history",
    target_fixture="recorded_invocation",
)
def given_recorded_compare(isolated_history: Path) -> dict[str, Any]:
    invocation: dict[str, Any] = {
        "command": "compare",
        "timestamp": "2026-05-20T12:00:00+00:00",
        "details": _compare_details(),
    }
    _write_history(isolated_history, [invocation])
    return invocation


@when(parsers.parse('I run solve from the menu for "{path}" with network model "{model}"'))
def when_run_solve_from_menu(monkeypatch: pytest.MonkeyPatch, path: str, model: str) -> None:
    invoke_run(
        monkeypatch,
        ["solve", "sienna", model, "exact", "simplex", "choose", "choose", "quit"],
        extra_path_answers={
            "Path to PowerSimulations.jl system JSON?": path,
            "Output directory?": "solved",
        },
    )


@when("I replay the recorded solve invocation")
def when_replay_recorded_solve(
    monkeypatch: pytest.MonkeyPatch, recorded_invocation: dict[str, Any]
) -> None:
    invoke_run(
        monkeypatch,
        [
            "history",
            recorded_invocation,
            "sienna",
            "dcp",
            "exact",
            "simplex",
            "choose",
            "choose",
            "quit",
        ],
    )


@when("I run from the menu a compare of pypsa against sienna")
def when_run_compare_from_menu(monkeypatch: pytest.MonkeyPatch) -> None:
    invoke_compare_run(
        monkeypatch,
        framework_a="pypsa",
        framework_b="sienna",
        path_answers={
            "side_a.path": _COMPARE_PYPSA_PATH,
            "side_b.system_json_path": _COMPARE_SYSTEM_PATH,
            "side_b.extensions_json_path": _COMPARE_EXTENSIONS_PATH,
            "side_b.results_dir": _COMPARE_RESULTS_DIR,
            "Output path for summary report?": _COMPARE_OUTPUT_PATH,
        },
    )


@when("I replay the recorded compare invocation")
def when_replay_compare(
    monkeypatch: pytest.MonkeyPatch, recorded_invocation: dict[str, Any]
) -> None:
    replay_compare_run(monkeypatch, recorded_invocation)


def _last_invocation(isolated_history: Path, command: str) -> dict[str, Any]:
    invocations: list[dict[str, Any]] = json.loads(isolated_history.read_text(encoding="utf-8"))[
        "invocations"
    ]
    matching = [invocation for invocation in invocations if invocation["command"] == command]
    assert matching, f"no {command!r} invocation in history; got {invocations}"
    return matching[-1]


@then(
    parsers.parse(
        'the history file records a "{command}" invocation with detail "{key}" set to "{value}"'
    )
)
def assert_history_detail(isolated_history: Path, command: str, key: str, value: str) -> None:
    details = _last_invocation(isolated_history, command).get("details", {})
    assert _answers_match(details.get(key), value), (
        f"expected detail {key}={value!r}, got {details}"
    )


def _answers_match(recorded: Any, expected: str) -> bool:
    """A recorded path answer carries the platform's own separator."""
    if recorded == expected:
        return True
    return isinstance(recorded, str) and Path(recorded) == Path(expected)


@then(
    parsers.parse(
        'the history file records a "{command}" invocation with sink param "{key}" set to "{value}"'
    )
)
def assert_history_sink_param(isolated_history: Path, command: str, key: str, value: str) -> None:
    details = _last_invocation(isolated_history, command).get("details", {})
    sink_overrides = details.get("sink_overrides", {}).get("0", {})
    assert sink_overrides.get(key) == value, (
        f"expected sink param {key}={value!r}, got {sink_overrides}"
    )
