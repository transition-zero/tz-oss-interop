# BDD test harnesses

Most scenarios drive the REPL in-process: a fixture stubs `questionary`
prompts to feed canned answers, then the step `When I run translate ...`
or `When I run init ...` dispatches the matching `Command` through the
interactive shell's `_dispatch` function. Use `capsys` (via the
`the printed output contains` step) and `caplog` (via `the log contains`)
to assert on what the surface emitted.

The Dishka container is built in-process per scenario, so step
definitions can swap providers (mock filesystem, in-memory job store,
etc.) before dispatching.

## subprocess (exception)

A real `subprocess.run([...])` is used when a fresh interpreter is
required: today, only the entry-point discovery scenario needs that
(an editable install's `.pth` isn't visible to the parent interpreter
mid-session). The subprocess invokes a small `python -c` script that
resolves `TranslateUseCase` from the container directly.

## Fast vs slow

The `@slow` tag marks scenarios whose per-mutant cost is too high to run
under the CI mutation job. pytest-bdd auto-converts Gherkin tags into pytest
markers, so `pytest -m "not slow"` (the default mutmut filter) excludes them.

Two scenario groups are slow for the same reason but with different remedies:

- The entry-point discovery scenario is a subprocess install smoke with no
  mutation value, so it carries `@slow` alone and stays excluded everywhere.
- Scenarios that run a Polars compute carry `@slow @fork_unsafe`, because a
  forked child that touches Polars deadlocks. `@fork_unsafe` tells
  `scripts/run_mutmut.py` to re-exec a fresh interpreter for the mutants they
  cover; `@slow` keeps that cost off the CI mutation job. `make mutation-full`
  (local) widens the filter to `not slow or fork_unsafe` so they rejoin the
  suite. See that script's docstring for the mechanism.

`scripts/lint_feature_tags.py` enforces both tags; everything else is fast by
default and needs no marker.
