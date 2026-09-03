import io
import shlex
import sys
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any, NamedTuple

import pytest
import questionary
import requests
import yaml
from interop_testing import (
    write_adapters_config,
)
from pytest_bdd import given, parsers, then, when

from interop.adapters.inbound.interactive_cli.app import Command, _dispatch, run
from interop.di.container import make_container
from interop.lints import plugin_filesystem, plugin_inheritance
from interop.main import app as run_main
from interop.ports.inbound.init_project import InitProjectUseCase
from interop.ports.inbound.translate import HANDOFF_WRITES_LABEL, PROJECT_WRITES_LABEL


@pytest.fixture(autouse=True)
def isolated_history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    # Point History.load()/save() at a per-test XDG path so tests neither read
    # nor pollute the developer's real ~/.local/share/interop history.
    xdg_root = tmp_path / "_xdg"
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_root))
    return xdg_root / "interop" / "interactive_history.json"


_recorded_selects: list[dict[str, Any]] = []


@pytest.fixture(autouse=True)
def recorded_selects() -> Iterator[list[dict[str, Any]]]:
    """One record per select prompt: its message, default, and choice titles."""
    _recorded_selects.clear()
    yield _recorded_selects


def _choice_title(choice: Any) -> str:
    title = getattr(choice, "title", None)
    if isinstance(title, str):
        return title
    return str(choice)


def stub_questionary_attr(
    monkeypatch: pytest.MonkeyPatch, attribute: str, returns: Iterator[Any]
) -> None:
    class _StubPrompt:
        def ask(self) -> Any:
            return next(returns)

    def stub(*args: Any, **kwargs: Any) -> _StubPrompt:
        _recorded_selects.append(
            {
                "message": args[0] if args else kwargs.get("message"),
                "default": kwargs.get("default"),
                "choice_titles": [
                    _choice_title(choice) for choice in (kwargs.get("choices") or [])
                ],
            }
        )
        return _StubPrompt()

    monkeypatch.setattr(questionary, attribute, stub)


def stub_requests(monkeypatch: pytest.MonkeyPatch, store: dict[str, bytes]) -> None:
    """In-memory GET/PUT stub for requests, keyed by URL. Mirrors the
    questionary stubs above: intercept the exact boundary the adapter
    calls, rather than pulling in a mocking library."""

    class _StubResponse:
        def __init__(self, content: bytes = b"") -> None:
            self.content = content
            self.raw = io.BytesIO(content)

        def raise_for_status(self) -> None:
            pass

    def stub_get(url: str, **kwargs: Any) -> _StubResponse:
        return _StubResponse(store[url])

    def stub_put(url: str, data: Any = b"", **kwargs: Any) -> _StubResponse:
        store[url] = data.read() if hasattr(data, "read") else data
        return _StubResponse()

    monkeypatch.setattr(requests, "get", stub_get)
    monkeypatch.setattr(requests, "put", stub_put)


@pytest.fixture
def http_store(monkeypatch: pytest.MonkeyPatch) -> dict[str, bytes]:
    store: dict[str, bytes] = {}
    stub_requests(monkeypatch, store)
    return store


@given(parsers.parse('adapters.yaml binds filesystem to "{name}"'))
def given_filesystem_binding(name: str) -> None:
    write_adapters_config(
        f"bindings:\n  filesystem: {name}\nadapters: {{}}\nobservability:\n  log_level: INFO\n"
    )


@given(parsers.parse('an http source at "{url}" containing "{content}"'))
def given_http_source_content(http_store: dict[str, bytes], url: str, content: str) -> None:
    http_store[url] = content.encode("utf-8")


@then(parsers.parse('the http destination "{url}" reads back as "{expected}"'))
def assert_http_destination_reads_back_as(
    http_store: dict[str, bytes], url: str, expected: str
) -> None:
    assert url in http_store, f"expected {url!r} in stubbed HTTP store, got {list(http_store)!r}"
    actual = http_store[url].decode("utf-8")
    assert actual == expected, f"expected {expected!r} at {url}, got {actual!r}"


@then(parsers.parse('the select prompt "{message}" offered default "{value}"'))
def assert_select_offered_default(message: str, value: str) -> None:
    defaults = [record["default"] for record in _recorded_selects if record["message"] == message]
    assert value in defaults, f"select {message!r} defaults were {defaults}, expected {value!r}"


@then(parsers.parse('the select prompt "{message}" offered exactly "{choices}"'))
def assert_select_offered_exactly(message: str, choices: str) -> None:
    expected = [choice.strip() for choice in choices.split(",")]
    offered = [
        record["choice_titles"] for record in _recorded_selects if record["message"] == message
    ]
    assert offered, f"select {message!r} was never asked; asked: {_recorded_selects}"
    assert expected in offered, f"select {message!r} offered {offered}, expected {expected}"


@then(parsers.parse('the history menu lists an entry containing "{text}"'))
def assert_history_menu_entry(text: str) -> None:
    titles = [
        title
        for record in _recorded_selects
        if record["message"] == "Re-run which past invocation?"
        for title in record["choice_titles"]
    ]
    assert any(text in title for title in titles), (
        f"no history entry contains {text!r}; entries: {titles}"
    )


@then("the REPL was not launched")
def assert_repl_not_launched(recorded_selects: list[dict[str, Any]]) -> None:
    assert recorded_selects == [], f"expected no REPL menu prompt, got {recorded_selects}"


def _kwarg_to_prompt(kwarg: str) -> str:
    """Map a kwarg name to the REPL prompt label it answers (without the trailing '?').

    `source_<field>`  -> `source.<field>`
    `step_<i>_<field>` -> `step[<i>].<field>`
    `sink_<i>_<field>` -> `sink[<i>].<field>`
    """
    head, _, rest = kwarg.partition("_")
    if head == "source":
        return f"source.{rest}"
    if head in ("step", "sink"):
        idx, _, field = rest.partition("_")
        return f"{head}[{idx}].{field}"
    return kwarg


def _prompt_matches(prompt: str, key: str) -> bool:
    """Whether a REPL prompt is the one a stub key answers.

    A prompt reads ``<label>?`` or ``<label> (<description>)?``, and a path widget appends a
    Tab hint; match on the label, tolerating a description or hint suffix. A key that already
    carries its own ``?`` (a literal prompt like ``User mappings file?``) matches exactly.
    """
    return prompt == key or prompt.startswith(f"{key}?") or prompt.startswith(f"{key} ")


_recorded_prompt_defaults: list[tuple[str, str]] = []


@pytest.fixture(autouse=True)
def prompt_defaults() -> Iterator[list[tuple[str, str]]]:
    """(message, default) pairs offered by text and path prompts during a run."""
    _recorded_prompt_defaults.clear()
    yield _recorded_prompt_defaults


@then(parsers.parse('the prompt "{message}" offered default "{value}"'))
def assert_prompt_offered_default(message: str, value: str) -> None:
    defaults = [d for m, d in _recorded_prompt_defaults if m.startswith(message)]
    assert value in defaults, f"prompt {message!r} defaults were {defaults}, expected {value!r}"


def _stub_questionary_text_by_prompt(
    monkeypatch: pytest.MonkeyPatch, answers_by_prompt: Mapping[str, str | list[str]]
) -> None:
    """Stub questionary.text: return the named answer, else the prompt's default.

    Falling back to the default mirrors the real widget, where pressing Enter
    submits the prefilled text.
    """

    class _StubPrompt:
        def __init__(self, prompt: str, *_args: Any, default: str = "", **_kwargs: Any) -> None:
            self._prompt = prompt
            self._default = default
            _recorded_prompt_defaults.append((prompt, default))

        def ask(self) -> str:
            for key, answer in answers_by_prompt.items():
                if _prompt_matches(self._prompt, key):
                    assert isinstance(answer, str), f"text prompt {self._prompt!r} got {answer!r}"
                    return answer
            return self._default

    monkeypatch.setattr(questionary, "text", _StubPrompt)


_recorded_path_prompts: list[str] = []
_recorded_path_rejections: list[tuple[str, str]] = []


@pytest.fixture(autouse=True)
def path_prompts() -> Iterator[list[str]]:
    """Messages shown by the path widget during a translate, for hint assertions."""
    _recorded_path_prompts.clear()
    yield _recorded_path_prompts


@pytest.fixture(autouse=True)
def path_rejections() -> Iterator[list[tuple[str, str]]]:
    """(answer, message) pairs the path widget's validator rejected during a translate."""
    _recorded_path_rejections.clear()
    yield _recorded_path_rejections


def _stub_questionary_path_by_prompt(
    monkeypatch: pytest.MonkeyPatch, answers_by_prompt: Mapping[str, str | list[str]]
) -> None:
    """Stub questionary.path: record each prompt and return its named answer.

    The path widget appends a Tab hint to the field prompt, so answers are
    matched by prefix against the bare `<node>.<field>?` key. With no named
    answer the prompt's default is returned, mirroring the real widget where
    pressing Enter submits the prefilled text. Like the real widget, a
    validator rejection re-asks: a list of answers is consumed in order until
    one passes, and each rejection is recorded with its message.
    """

    class _StubPrompt:
        def __init__(
            self,
            message: str,
            *_args: Any,
            default: str = "",
            validate: Callable[[str], bool | str] | None = None,
            **_kwargs: Any,
        ) -> None:
            self._message = message
            self._default = default
            self._validate = validate
            _recorded_prompt_defaults.append((message, default))

        def ask(self) -> str:
            _recorded_path_prompts.append(self._message)
            for key, answers in answers_by_prompt.items():
                if _prompt_matches(self._message, key):
                    return self._first_valid_answer(answers)
            return self._first_valid_answer(self._default)

        def _first_valid_answer(self, answers: str | list[str]) -> str:
            candidates = [answers] if isinstance(answers, str) else answers
            for candidate in candidates:
                verdict = True if self._validate is None else self._validate(candidate)
                if verdict is True:
                    return candidate
                _recorded_path_rejections.append((candidate, str(verdict)))
            raise AssertionError(f"every answer for {self._message!r} was rejected: {candidates}")

    monkeypatch.setattr(questionary, "path", _StubPrompt)


@then(parsers.parse('the path prompt rejected "{answer}" with a message containing "{text}"'))
def assert_path_answer_rejected(answer: str, text: str) -> None:
    matching = [message for rejected, message in _recorded_path_rejections if rejected == answer]
    assert matching, (
        f"no path-prompt rejection recorded for {answer!r}; got {_recorded_path_rejections}"
    )
    assert any(text in message for message in matching), (
        f"no rejection message for {answer!r} contains {text!r}; got {matching}"
    )


def invoke_translate(
    monkeypatch: pytest.MonkeyPatch,
    src: str,
    dst: str,
    pipeline: str,
    user_mappings_path: str | None = None,
    **prompt_answers: str | list[str],
) -> None:
    """Stub the framework/pipeline selects and the params prompts, then dispatch."""
    stub_questionary_attr(monkeypatch, "select", iter([src, dst, pipeline]))
    field_answers = {_kwarg_to_prompt(k): v for k, v in prompt_answers.items()}
    _stub_questionary_text_by_prompt(monkeypatch, field_answers)
    path_answers = (
        {"User mappings file?": user_mappings_path, **field_answers}
        if user_mappings_path is not None
        else field_answers
    )
    _stub_questionary_path_by_prompt(monkeypatch, path_answers)
    _dispatch(Command.TRANSLATE, make_container())


def invoke_validate(
    monkeypatch: pytest.MonkeyPatch,
    src: str,
    dst: str,
    pipeline: str,
    user_mappings_path: str | None = None,
    **prompt_answers: str | list[str],
) -> None:
    """Stub the framework/pipeline selects and source params prompts, then dispatch validate."""
    stub_questionary_attr(monkeypatch, "select", iter([src, dst, pipeline]))
    field_answers = {_kwarg_to_prompt(k): v for k, v in prompt_answers.items()}
    _stub_questionary_text_by_prompt(monkeypatch, field_answers)
    path_answers = (
        {"User mappings file?": user_mappings_path, **field_answers}
        if user_mappings_path is not None
        else field_answers
    )
    _stub_questionary_path_by_prompt(monkeypatch, path_answers)
    _dispatch(Command.VALIDATE, make_container())


def invoke_solve(
    monkeypatch: pytest.MonkeyPatch,
    sienna_json_path: str,
    network_model: str,
    output_dir: str = "solved",
    model_type: str = "sienna",
    download_consent: bool = True,
    unit_commitment: str = "exact",
    solver: str = "simplex",
    presolve: str = "choose",
    run_crossover: str = "choose",
    time_limit_seconds: str = "",
) -> None:
    """Stub every solve prompt (selects, download consent, paths, text), then dispatch solve."""
    stub_questionary_attr(monkeypatch, "path", iter([sienna_json_path, output_dir]))
    stub_questionary_attr(
        monkeypatch,
        "select",
        iter([model_type, network_model, unit_commitment, solver, presolve, run_crossover]),
    )
    stub_questionary_attr(monkeypatch, "confirm", iter([download_consent]))
    stub_questionary_attr(monkeypatch, "text", iter([time_limit_seconds]))
    _dispatch(Command.SOLVE, make_container())


def invoke_solve_pypsa(
    monkeypatch: pytest.MonkeyPatch,
    network_path: str,
    output_dir: str,
    start: str = "",
    end: str = "",
    unit_commitment: str = "exact",
    window: str = "month",
    look_ahead_days: str = "",
) -> None:
    """Stub the pypsa solve prompts (model type, paths, dates, UC, window), then dispatch."""
    stub_questionary_attr(monkeypatch, "select", iter(["pypsa", unit_commitment, window]))
    stub_questionary_attr(monkeypatch, "path", iter([network_path, output_dir]))
    stub_questionary_attr(monkeypatch, "text", iter([start, end, look_ahead_days]))
    _dispatch(Command.SOLVE, make_container())


def invoke_init(
    monkeypatch: pytest.MonkeyPatch,
    target: str,
    example: str = "none",
) -> None:
    """Stub the target text prompt and the example select, then dispatch init."""
    stub_questionary_attr(monkeypatch, "text", iter([target]))
    stub_questionary_attr(monkeypatch, "select", iter([example]))
    _dispatch(Command.INIT, make_container())


def invoke_compare(
    monkeypatch: pytest.MonkeyPatch,
    *,
    framework_a: str,
    framework_b: str,
    path_answers: dict[str, str],
) -> None:
    """Stub the two framework selects and the per-side path prompts, then dispatch compare."""
    stub_questionary_attr(monkeypatch, "select", iter([framework_a, framework_b]))
    _stub_questionary_path_by_prompt(monkeypatch, path_answers)
    _dispatch(Command.COMPARE, make_container())


def invoke_translate_cancel_at_destination(
    monkeypatch: pytest.MonkeyPatch, source_framework: str
) -> None:
    """Dispatch translate, choose the source framework, then cancel at the destination prompt.

    Cancelling records the destination select's offered choices without running a pipeline.
    """
    stub_questionary_attr(monkeypatch, "select", iter([source_framework, None]))
    _dispatch(Command.TRANSLATE, make_container())


def invoke_compare_cancel_at_first_framework(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dispatch compare and cancel at the first-framework prompt, recording its offered choices."""
    stub_questionary_attr(monkeypatch, "select", iter([None]))
    _dispatch(Command.COMPARE, make_container())


def invoke_compare_run(
    monkeypatch: pytest.MonkeyPatch,
    *,
    framework_a: str,
    framework_b: str,
    path_answers: dict[str, str],
) -> None:
    """Run compare from the REPL main menu, recording prompt defaults."""
    stub_questionary_attr(
        monkeypatch, "select", iter([Command.COMPARE, framework_a, framework_b, Command.QUIT])
    )
    _stub_questionary_path_by_prompt(monkeypatch, path_answers)
    run(make_container())


def replay_compare_run(
    monkeypatch: pytest.MonkeyPatch, recorded_invocation: dict[str, Any]
) -> None:
    """Replay a recorded compare invocation from history (path prompts accept their defaults)."""
    details = recorded_invocation["details"]
    stub_questionary_attr(
        monkeypatch,
        "select",
        iter(
            [
                Command.HISTORY,
                recorded_invocation,
                details["side_a_framework"],
                details["side_b_framework"],
                Command.QUIT,
            ]
        ),
    )
    _stub_questionary_path_by_prompt(monkeypatch, {})
    run(make_container())


def invoke_run(
    monkeypatch: pytest.MonkeyPatch,
    choices: list[Any],
    user_mappings_path: str | None = None,
    extra_path_answers: dict[str, str] | None = None,
    **prompt_answers: str,
) -> None:
    """Stub select with `choices` and text prompts with `prompt_answers`, then enter run()."""
    stub_questionary_attr(monkeypatch, "select", iter(choices))
    field_answers = {_kwarg_to_prompt(k): v for k, v in prompt_answers.items()}
    _stub_questionary_text_by_prompt(monkeypatch, field_answers)
    combined: dict[str, str | list[str]] = dict(field_answers)
    if user_mappings_path is not None:
        combined["User mappings file?"] = user_mappings_path
    if extra_path_answers:
        combined.update(extra_path_answers)
    _stub_questionary_path_by_prompt(monkeypatch, combined)
    run(make_container())


def invoke_main(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> int:
    """Run interop.main.app() with sys.argv=["interop", *argv], returning its exit code.

    HeadlessCli.run and main.py's own unknown-adapter branch both call
    sys.exit, so app() always raises SystemExit here; that's caught and
    turned into a plain int so scenarios can assert on it directly.

    questionary.select is stubbed to an empty sequence: this entrypoint is
    exercised only with argv that should dispatch to headless_cli or fail
    to resolve an adapter, and either way the REPL's menu prompt must never
    be reached. If it is, this raises StopIteration on the first ask() call
    (a fittingly loud failure) rather than silently answering a human
    prompt with a canned value.
    """
    stub_questionary_attr(monkeypatch, "select", iter([]))
    monkeypatch.setattr(sys, "argv", ["interop", *argv])
    try:
        run_main()
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1
    return 0


def capture_main_menu_labels(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Enter run(), record the labels rendered in the top-level menu, then quit.

    Returns the Choice titles presented at the "What would you like to do?"
    prompt so scenarios can assert the description shown beside each command.
    """
    labels: list[str] = []

    class _RecordingPrompt:
        def __init__(self, *_args: Any, choices: list[Any] | None = None, **_kwargs: Any) -> None:
            self._choices = choices or []

        def ask(self) -> Any:
            labels.extend(choice.title for choice in self._choices)
            return Command.QUIT

    monkeypatch.setattr(questionary, "select", _RecordingPrompt)
    run(make_container())
    return labels


@pytest.fixture(autouse=True)
def printed_messages(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    messages: list[str] = []

    def stub_print(message: str, *_args: Any, **_kwargs: Any) -> None:
        messages.append(message)

    monkeypatch.setattr(questionary, "print", stub_print)
    return messages


def join_printed_messages(printed_messages: list[str]) -> str:
    """Everything the REPL printed, as one string for a substring assertion."""
    return "\n".join(printed_messages)


@then(parsers.parse('the printed output contains "{expected}"'))
def assert_printed_output_contains(printed_messages: list[str], expected: str) -> None:
    haystack = join_printed_messages(printed_messages)
    assert expected in haystack, f"expected {expected!r} in printed output, got {haystack!r}"


@then(parsers.parse('the printed output does not contain "{unexpected}"'))
def assert_printed_output_lacks(printed_messages: list[str], unexpected: str) -> None:
    haystack = join_printed_messages(printed_messages)
    assert unexpected not in haystack, (
        f"expected {unexpected!r} absent from printed output, got {haystack!r}"
    )


class _ReportedWrite(NamedTuple):
    path: Path
    is_handoff: bool


def _summary_writes(caplog: pytest.LogCaptureFixture) -> list[_ReportedWrite]:
    """Every file the run summaries said they wrote, each with the kind the summary gave it."""
    return [
        write
        for line in caplog.text.replace("\\", "/").splitlines()
        for write in _parse_summary(line)
    ]


def _parse_summary(line: str) -> Iterator[_ReportedWrite]:
    for group in line.split("; ")[1:]:
        for label, is_handoff in ((HANDOFF_WRITES_LABEL, True), (PROJECT_WRITES_LABEL, False)):
            if group.startswith(f"{label} "):
                entries = group.removeprefix(f"{label} ").split(", ")
                yield from (_ReportedWrite(_written_path(entry), is_handoff) for entry in entries)
                break


def _written_path(entry: str) -> Path:
    """One summary entry is a path followed by its size, as `outputs/a.json (12 Bytes)`."""
    return Path(entry.rsplit(" (", 1)[0])


def _reported_writes(
    caplog: pytest.LogCaptureFixture, filename: str, *, is_handoff: bool
) -> list[Path]:
    return [
        write.path
        for write in _summary_writes(caplog)
        if write.is_handoff is is_handoff and _is_named(write.path, filename)
    ]


def _is_named(path: Path, filename: str) -> bool:
    """Matched as text, since a Path prints Windows separators the feature file never uses."""
    written = str(path).replace("\\", "/")
    return written == filename or written.endswith(f"/{filename}")


def _one_handoff(caplog: pytest.LogCaptureFixture, filename: str) -> Path:
    reported = _reported_writes(caplog, filename, is_handoff=True)
    assert len(reported) == 1, (
        f"expected one hand-off file named {filename!r}, got {reported}: {caplog.text}"
    )
    return reported[0]


@then(parsers.parse('the run reported a hand-off file "{filename}" and it is still there'))
def assert_handoff_file_kept(caplog: pytest.LogCaptureFixture, filename: str) -> None:
    reported = _one_handoff(caplog, filename)
    assert reported.is_file(), f"expected {reported} to survive keep_staging, but it is gone"


@then(parsers.parse('the run reported a hand-off file "{filename}" and it is now cleaned up'))
def assert_handoff_file_cleaned_up(caplog: pytest.LogCaptureFixture, filename: str) -> None:
    reported = _one_handoff(caplog, filename)
    assert not reported.exists(), f"expected {reported} to be cleaned up, but it is still there"


@then(
    parsers.parse('the run reported {count:d} hand-off files named "{filename}", all still there')
)
def assert_distinct_handoff_files(
    caplog: pytest.LogCaptureFixture, count: int, filename: str
) -> None:
    reported = {str(path): path for path in _reported_writes(caplog, filename, is_handoff=True)}
    assert len(reported) == count, (
        f"expected {count} hand-off files named {filename!r}, got {reported}: {caplog.text}"
    )
    missing = [str(path) for path in reported.values() if not path.is_file()]
    assert not missing, f"expected every hand-off {filename!r} to survive keep_staging: {missing}"


@then(parsers.parse('the run wrote "{filename}" into the project exactly once'))
def assert_written_into_project_once(caplog: pytest.LogCaptureFixture, filename: str) -> None:
    into_project = _reported_writes(caplog, filename, is_handoff=False)
    assert len(into_project) == 1, (
        f"expected one project write of {filename!r}, got {into_project}: {caplog.text}"
    )


@given(parsers.parse('adapters.yaml binds solver to "{name}"'))
def given_solver_binding(name: str) -> None:
    write_adapters_config(
        f"bindings:\n  solver: {name}\nadapters: {{}}\nobservability:\n  log_level: INFO\n"
    )


@given(parsers.parse('I have run init at "{target}"'))
def given_have_run_init(target: str) -> None:
    with make_container()() as scope:
        scope.get(InitProjectUseCase)(Path(target))


@given("the working directory has no adapters.yaml")
def given_no_adapters_yaml() -> None:
    (Path.cwd() / "adapters.yaml").unlink(missing_ok=True)


@when(
    parsers.parse('I run translate with source "{src}" destination "{dst}" pipeline "{pipeline}"')
)
def run_translate(monkeypatch: pytest.MonkeyPatch, src: str, dst: str, pipeline: str) -> None:
    invoke_translate(monkeypatch, src, dst, pipeline)


@when(parsers.parse('I run validate with source "{src}" destination "{dst}" pipeline "{pipeline}"'))
def run_validate(monkeypatch: pytest.MonkeyPatch, src: str, dst: str, pipeline: str) -> None:
    invoke_validate(monkeypatch, src, dst, pipeline)


@when(parsers.parse('I run init with target "{target}"'))
def run_init(monkeypatch: pytest.MonkeyPatch, target: str) -> None:
    invoke_init(monkeypatch, target)


@when(parsers.parse('I run init with target "{target}" and example "{example}"'))
def run_init_with_example(monkeypatch: pytest.MonkeyPatch, target: str, example: str) -> None:
    invoke_init(monkeypatch, target, example)


class LintResult(NamedTuple):
    exit_code: int
    output: str


@when("I run the plugin-inheritance lint", target_fixture="lint_result")
def run_plugin_inheritance_lint(capsys: pytest.CaptureFixture[str]) -> LintResult:
    # No arguments, so the scenario also pins the default project layout the
    # console script scans when a project drops it into pre-commit as-is.
    exit_code = plugin_inheritance.main([])
    return LintResult(exit_code, capsys.readouterr().err)


@when("I run the plugin-filesystem lint", target_fixture="lint_result")
def run_plugin_filesystem_lint(capsys: pytest.CaptureFixture[str]) -> LintResult:
    exit_code = plugin_filesystem.main([])
    return LintResult(exit_code, capsys.readouterr().err)


@then(parsers.parse("the lint exit code is {code:d}"))
def assert_lint_exit_code(lint_result: LintResult, code: int) -> None:
    assert lint_result.exit_code == code, f"lint output was: {lint_result.output!r}"


@then(parsers.parse('the lint output contains "{text}"'))
def assert_lint_output_contains(lint_result: LintResult, text: str) -> None:
    assert text in lint_result.output, f"lint output was: {lint_result.output!r}"


@when(parsers.parse('I run interop with argv "{argv_str}"'), target_fixture="headless_exit_code")
def run_interop_with_argv(
    monkeypatch: pytest.MonkeyPatch, argv_str: str, capsys: pytest.CaptureFixture[str]
) -> int:
    # capsys is requested here (unused) so its sys.stderr capture is installed
    # before this step prints to stderr, not lazily when a later Then step
    # first asks for the fixture — otherwise readouterr() would see nothing.
    del capsys
    return invoke_main(monkeypatch, shlex.split(argv_str))


@then(parsers.parse("the headless exit code is {code:d}"))
def assert_headless_exit_code(headless_exit_code: int, code: int) -> None:
    assert headless_exit_code == code, f"expected exit code {code}, got {headless_exit_code}"


@when(
    parsers.parse('I run solve on "{network_path}" from "{start}" to "{end}" into "{output_dir}"')
)
def run_solve_pypsa(
    monkeypatch: pytest.MonkeyPatch, network_path: str, start: str, end: str, output_dir: str
) -> None:
    invoke_solve_pypsa(monkeypatch, network_path, output_dir, start, end)


@when(
    parsers.parse(
        'I run solve on "{network_path}" from "{start}" to "{end}" in "{window}" windows '
        'with a {look_ahead_days:d} day look-ahead into "{output_dir}"'
    )
)
def run_solve_pypsa_in_windows(
    monkeypatch: pytest.MonkeyPatch,
    network_path: str,
    start: str,
    end: str,
    window: str,
    look_ahead_days: int,
    output_dir: str,
) -> None:
    invoke_solve_pypsa(
        monkeypatch,
        network_path,
        output_dir,
        start,
        end,
        window=window,
        look_ahead_days=str(look_ahead_days),
    )


@when(parsers.parse('I run solve on "{network_path}" from "{start}" onward into "{output_dir}"'))
def run_solve_pypsa_onward(
    monkeypatch: pytest.MonkeyPatch, network_path: str, start: str, output_dir: str
) -> None:
    invoke_solve_pypsa(monkeypatch, network_path, output_dir, start, end="")


@when(
    parsers.parse(
        'I run solve on "{network_path}" from "{start}" to "{end}" '
        'with unit commitment "{unit_commitment}" into "{output_dir}"'
    )
)
def run_solve_pypsa_with_unit_commitment(
    monkeypatch: pytest.MonkeyPatch,
    network_path: str,
    start: str,
    end: str,
    unit_commitment: str,
    output_dir: str,
) -> None:
    invoke_solve_pypsa(
        monkeypatch, network_path, output_dir, start, end, unit_commitment=unit_commitment
    )


@then(parsers.parse('the solved network "{path}" has dispatch for {count:d} snapshots'))
def assert_solved_network_has_dispatch(path: str, count: int) -> None:
    import pypsa

    network = pypsa.Network(path)
    dispatched = int((network.generators_t["p"] != 0).any(axis=1).sum())
    assert dispatched == count, f"expected dispatch for {count} snapshots, got {dispatched}"


@then(parsers.parse('the solved network "{path}" has generator "{name}" dispatch {values}'))
def assert_solved_network_generator_dispatch(path: str, name: str, values: str) -> None:
    import pypsa

    network = pypsa.Network(path)
    expected = [float(v) for v in values.split()]
    actual = [float(v) for v in network.generators_t["p"][name]]
    assert len(actual) == len(expected), (
        f"expected {len(expected)} dispatch values for {name!r}, got {len(actual)}: {actual}"
    )
    paired = enumerate(zip(actual, expected, strict=True))
    mismatches = [(i, a, e) for i, (a, e) in paired if abs(a - e) > 1e-6]
    assert not mismatches, (
        f"generator {name!r} dispatch mismatch at {mismatches}; expected {expected}, got {actual}"
    )


@then(parsers.parse('the solved network "{path}" has no dispatch on "{day}"'))
def assert_no_dispatch_on(path: str, day: str) -> None:
    import pandas as pd
    import pypsa

    network = pypsa.Network(path)
    dispatch = network.generators_t.p
    on_day = dispatch[dispatch.index.normalize() == pd.Timestamp(day)]
    assert (on_day == 0).all(axis=None), f"expected no dispatch on {day} in {path}; found {on_day}"


@then(parsers.parse('the solved network "{path}" has no bus price on "{day}"'))
def assert_no_bus_price_on(path: str, day: str) -> None:
    import pandas as pd
    import pypsa

    network = pypsa.Network(path)
    price = network.buses_t.marginal_price
    on_day = price[price.index.normalize() == pd.Timestamp(day)]
    assert (on_day == 0).all(axis=None), f"expected no bus price on {day} in {path}; found {on_day}"


@then(parsers.parse('the solved network "{path}" marks "{day}" as reported'))
def assert_day_marked_reported(path: str, day: str) -> None:
    import pandas as pd
    import pypsa

    network = pypsa.Network(path)
    reported = pd.DatetimeIndex(network.meta.get("reported_snapshots", []))
    on_day = reported[reported.normalize() == pd.Timestamp(day)]
    assert not on_day.empty, f"expected {day} marked reported in {path}; reported={list(reported)}"


@then(parsers.parse('the solved network "{path}" marks "{day}" as not reported'))
def assert_day_not_marked_reported(path: str, day: str) -> None:
    import pandas as pd
    import pypsa

    network = pypsa.Network(path)
    reported = pd.DatetimeIndex(network.meta.get("reported_snapshots", []))
    on_day = reported[reported.normalize() == pd.Timestamp(day)]
    assert on_day.empty, f"expected {day} not marked reported in {path}; found {list(on_day)}"


@then("the solve reported success")
def assert_solve_reported_success(printed_messages: list[str]) -> None:
    combined = "\n".join(printed_messages)
    assert "[OK]" in combined, f"expected a successful solve summary, got: {combined!r}"


PLEXOS_MAPPINGS_PATH = "user_mappings.yaml"


@given("a PLEXOS mappings file:", target_fixture="plexos_mappings_file")
def given_plexos_mappings_file(datatable: list[list[str]]) -> Path:
    header, *rows = datatable
    carriers = [
        {field: value for field, value in zip(header, row, strict=True) if value} for row in rows
    ]
    path = Path(PLEXOS_MAPPINGS_PATH)
    path.write_text(yaml.dump({"carriers": carriers}, sort_keys=False), encoding="utf-8")
    return path


@when(
    parsers.parse('I run the validation chain over "{system_json_path}" writing "{ps_json_path}"')
)
def run_sienna_to_power_simulations(
    monkeypatch: pytest.MonkeyPatch, system_json_path: str, ps_json_path: str
) -> None:
    system = Path(system_json_path)
    invoke_translate(
        monkeypatch,
        "sienna",
        "power-simulations",
        "sienna-to-power-simulations",
        source_system_json_path=str(system),
        source_time_series_h5_path=str(system.parent / "system_time_series_storage.h5"),
        source_extensions_json_path=str(system.parent / "extensions.json"),
        sink_0_system_json_filepath=ps_json_path,
        sink_0_h5_output_path=str(
            Path(ps_json_path).parent / "power_simulations_system_time_series.h5"
        ),
    )
