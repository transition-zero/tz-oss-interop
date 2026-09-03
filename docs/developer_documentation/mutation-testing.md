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

mutmut writes everything under `mutants/`: the copied working tree, its stats (`mutmut-stats.json`), and per-file results (`<file>.py.meta`) that let a rerun skip mutants it has already evaluated. The directory is gitignored. The CI mutation job caches `mutants/` so each run resumes from the previous result set instead of re-evaluating every mutant from scratch.

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
