# Mutation testing

We use [mutmut](https://mutmut.readthedocs.io/) to gauge how well our test suite catches behavioural changes. Mutation testing rewrites a function's body in small, deliberately broken ways (a "mutant") and re-runs the tests. If the tests pass against the mutant, the mutant "survived" and the tests are missing coverage for that piece of behaviour. If the tests fail, the mutant was "killed".

## Run it locally

```bash
uv run python scripts/run_mutmut.py run
uv run python scripts/run_mutmut.py results --all true
uv run python scripts/run_mutmut.py show <mutant-id>
```

The wrapper script is needed on macOS only: mutmut v3 calls `setproctitle()` inside a forked child, which crashes against CoreFoundation on Darwin. The wrapper no-ops `setproctitle` on macOS before importing mutmut. On Linux it is a transparent passthrough.

To target a single function or file, append the dotted name (or path) as a positional argument:

```bash
uv run python scripts/run_mutmut.py run interop.adapters.inbound.interactive_cli.app
```

mutmut writes everything under `mutants/`: the copied working tree, its stats (`mutmut-stats.json`), and per-file results (`<file>.py.meta`) that let a rerun skip mutants it has already evaluated. The directory is gitignored. CI starts each run from an empty `mutants/`.

## What CI mutates

- A push to `main` mutates every file that mutmut can mutate.
- A pull request mutates only the files that it changes. `scripts/mutation_scope.py` reads the changed paths from `git diff` and keeps each Python file under `interop/` that neither `do_not_mutate` nor the list of modules that only slow tests cover excludes.
- If the pull request changes no such file, or if the changed files hold no mutant, the job runs no mutation test. The PR comment says that the job skipped the run by choice, and the check passes.
- If mutmut checks no mutant for a different reason, the report step fails. An example is a test that fails in the `mutants/` sandbox before mutmut starts.

A test that reads a file by its path from the repository root needs that directory in `also_copy` in `pyproject.toml`. If the directory is not there, the test fails in the sandbox, and mutmut checks no mutant.

To do the same targeted run locally:

```bash
git diff --name-only --diff-filter=d origin/main...HEAD | uv run python scripts/mutation_scope.py > mutation_targets.txt
MUTATION_TARGETS_FILE=mutation_targets.txt uv run python scripts/run_mutmut.py run
```

`run_mutmut.py` stops if `mutation_targets.txt` is empty, because an empty `only_mutate` makes mutmut mutate every file.

## Reading the score

The mutation workflow posts a sticky comment on every PR with a table:

```
| 🎉 Killed | n |
| 🙁 Survived | n |
| 🫥 No tests | n |
| ⏰ Timeout | n |
| 🤔 Suspicious | n |
| 🔇 Skipped | n |
```

The headline score is `killed / (killed + survived)`. Mutants under "no tests" mean mutmut found no test covering that mutation, which is a coverage gap, not a tests-don't-catch-it gap. Improving the score generally means either adding tests for surviving mutants or marking a mutant as equivalent (genuinely behaviourally identical to the original).

## Investigating a surviving mutant

```bash
uv run python scripts/run_mutmut.py show <mutant-id>
```

prints the diff. Decide:

- **The mutant changes behaviour but no test catches it.** Add a test that asserts on the behaviour the mutation breaks.
- **The mutant produces the same observable behaviour as the original** (equivalent mutant). These are real but rare; document or restructure the code if it shows up repeatedly.
