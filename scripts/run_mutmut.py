"""Wrapper around the mutmut CLI that also disables string-literal mutations.

Three patches applied before mutmut starts:

1. The string-literal and string-method-swap mutation operators are stripped
   from `mutmut.mutation.mutators.mutation_operators`. They generate many low-
   signal mutants (mostly `"foo"` -> `"XXfooXX"` on exception messages and
   log lines that tests don't assert on), inflating mutant count without
   matching test-quality gain. This is a hardcoded patch against an internal
   mutmut API: if mutmut renames or refactors those symbols on upgrade, the
   import below fails loud.

2. `PytestRunner.run_tests` re-execs the per-mutant test run in a fresh
   interpreter for mutants covered by a `fork_unsafe` test. mutmut forks one
   child per mutant without exec, from a parent that has already run the
   covering tests in-process. A test that runs a Polars compute makes the
   parent build a Rayon thread pool; those worker threads do not survive
   `fork()`, so a child that then runs a Polars op inherits a permanently
   locked pool and deadlocks (mutmut kills it at the CPU-time limit -> a
   `timeout`). Polars exposes no pool-reset API, `--max-children 1` does not
   help because the hang is per-fork rather than per-concurrency, and
   `POLARS_MAX_THREADS=1` does not help either: a one-thread pool is still a
   pool. Re-execing pytest in a subprocess gives the child a fresh process.

   The `fork_unsafe` pytest marker (see pyproject) names the tests that run a
   Polars compute. Only mutants whose covering tests intersect that set pay the
   subprocess cost; everything else keeps the cheap in-process fork. A child
   running a non-Polars test is safe even though the parent's pool is poisoned,
   because the deadlock is on Polars *use*, not on import or a forked-in pool.
   The marked-test node ids are collected once in the parent and inherited by
   every fork.

3. On the default (`not slow`) run only, the translation plugin layer (every
   step/source/sink plus the shared recipe code, and the Julia solver adapter)
   is added to `do_not_mutate`. Those modules are exercised only by the
   `@slow @fork_unsafe` pipeline tests, which the `not slow` filter excludes, so
   under the default filter they have no covering test and every one of their
   mutants is a "no tests" non-result: zero signal. They are the bulk of the
   mutant set, and their slow tail is what pushed the CI job past its timeout.
   They stay mutable under `MUTATION_INCLUDE_FORK_UNSAFE` (`make mutation-full`),
   where the fresh-interpreter re-exec of patch 2 lets the `@slow` suite actually
   kill them. The generic `noop`/`emit_json` plugins are not excluded: non-slow
   tests cover them for real.

Which tests carry which tag, and why, is enforced by `scripts/lint_feature_tags.py`.
Setting `MUTATION_INCLUDE_FORK_UNSAFE` (the `make mutation-full` target does this)
widens the default `-m "not slow"` filter to `-m "not slow or fork_unsafe"`, so the
Polars tests rejoin the mutation suite locally; the genuinely heavy `@slow` tests
(the subprocess install smoke) stay excluded either way.

Usage: `uv run python scripts/run_mutmut.py <args>` (e.g. `run`, `results`, `show <id>`).
"""

from __future__ import annotations

import os
import subprocess
import sys


def main() -> None:
    from mutmut import configuration
    from mutmut.mutation import mutators

    skipped_string_ops = {
        mutators.operator_string,
        mutators.operator_symmetric_string_methods_swap,
        mutators.operator_unsymmetrical_string_methods_swap,
    }
    mutators.mutation_operators = [
        op for op in mutators.mutation_operators if op[1] not in skipped_string_ops
    ]

    include_fork_unsafe = bool(os.environ.get("MUTATION_INCLUDE_FORK_UNSAFE"))

    # The translation plugin layer (every step/source/sink plus the shared recipe code, and
    # the Julia solver adapter) is exercised only by the @slow @fork_unsafe pipeline tests,
    # which the default `not slow` filter excludes. Under that filter these modules have no
    # covering test, so every one of their mutants is a "no tests" non-result: zero signal,
    # but mutmut still generates and iterates them. They are ~83% of the mutant set, and the
    # slow tail of them is what pushes the CI job past its timeout. Exclude them from the
    # default run; the fork-unsafe run (`make mutation-full`) keeps them mutable, where the
    # patch-2 fresh-interpreter re-exec lets the @slow suite actually kill them. The generic
    # noop/emit_json plugins are *not* excluded: non-slow tests cover them for real.
    translation_layer_only_covered_by_slow = [
        "interop/plugins/steps/*",
        "interop/plugins/shared/*",
        "interop/plugins/sources/stage_*",
        "interop/plugins/sinks/_extensions_json.py",
        "interop/plugins/sinks/emit_pypsa_*",
        "interop/plugins/sinks/emit_sienna_*",
        "interop/plugins/sinks/emit_power_simulations_*",
        "interop/plugins/sinks/emit_results_parquet.py",
        "interop/adapters/outbound/julia_solver.py",
        "interop/templates/*",
    ]

    # mutmut loads its config lazily the first time Config.get() needs it; wrap the loader so
    # the adjustments reach both stats collection and the per-mutant runs (the filter is read
    # once into PytestRunner._pytest_add_cli_args). This must be patched before mutmut.__main__
    # is imported below: importing it pulls in safe_setproctitle, which calls Config.get() at
    # module scope and would otherwise load (and cache) the unpatched config first.
    original_load_config = configuration._load_config

    def load_config_for_run():  # type: ignore[no-untyped-def]
        config = original_load_config()
        if include_fork_unsafe:
            config.pytest_add_cli_args = ["-m", "not slow or fork_unsafe"]
        else:
            config.do_not_mutate = [*config.do_not_mutate, *translation_layer_only_covered_by_slow]
        return config

    configuration._load_config = load_config_for_run

    from mutmut.__main__ import BadTestExecutionCommandsException, PytestRunner, cli

    run_tests_in_process = PytestRunner.run_tests

    # Collected once in the parent (the clean run, mutant_name=None) and inherited
    # by every fork. None until collected; a (possibly empty) set afterwards.
    fork_unsafe_nodeids: set[str] | None = None

    def collect_fork_unsafe_nodeids() -> set[str]:
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q", "-m", "fork_unsafe"],
            cwd="mutants",
            env=os.environ,
            capture_output=True,
            text=True,
        )
        return {line.strip() for line in completed.stdout.splitlines() if "::" in line}

    def run_tests_fork_safe(self, *, mutant_name, tests):  # type: ignore[no-untyped-def]
        nonlocal fork_unsafe_nodeids
        if fork_unsafe_nodeids is None:
            fork_unsafe_nodeids = collect_fork_unsafe_nodeids()

        covering_tests = set(tests or ())
        mutant_needs_fresh_interpreter = mutant_name is not None and bool(
            covering_tests & fork_unsafe_nodeids
        )
        if not mutant_needs_fresh_interpreter:
            return run_tests_in_process(self, mutant_name=mutant_name, tests=tests)

        selection = list(tests) if tests else self._pytest_add_cli_args_test_selection
        params = [
            "--rootdir=.",
            "--tb=native",
            "-x",
            "-q",
            "-p",
            "no:randomly",
            "-p",
            "no:random-order",
            *selection,
            *self._pytest_add_cli_args,
        ]
        # mutmut's in-process runner wraps each per-mutant run in CatchOutput();
        # killed mutants are failing tests by design, so their pytest tracebacks
        # must be swallowed here too. Only the exit code is consumed.
        exit_code = subprocess.run(
            [sys.executable, "-m", "pytest", *params],
            cwd="mutants",
            env=os.environ,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        if exit_code == 4:
            raise BadTestExecutionCommandsException(params)
        return exit_code

    # Monkeypatching a method is the whole point of the wrapper, so mypy's
    # blanket objection to it does not apply.
    PytestRunner.run_tests = run_tests_fork_safe  # type: ignore[method-assign]

    cli()


if __name__ == "__main__":
    main()
