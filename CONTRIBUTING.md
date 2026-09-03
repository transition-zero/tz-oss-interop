# Contributing to interop

Thanks for your interest in interop. This guide covers how to get set up, what
the project expects of a change, and how to get that change merged.

By taking part you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).

## What interop is, and is not

interop translates between energy-system model formats. A pipeline composes a
source, a series of steps, and a sink, each of them a plugin discovered from the
built-ins, from a project's own files, or from an installed package. PyPSA,
Sienna, PLEXOS and OSeMOSYS are the formats in the tree today.

It is not a solver and not a modelling framework. It reads one publisher's
format, translates it, and writes another, keeping an audit trail of every
decision it made along the way. Anything that belongs upstream in PyPSA or in
Sienna belongs there, not here.

The project is beta. The plugin interfaces and the pipeline YAML shape are
settled enough to build on, but they still change between versions, and there is
no deprecation window yet.

## Ways to contribute

Code is one of several. Also useful, and easier to start with:

- Run interop over a published model and write up what happened, as a page in
  `docs/case_studies/`.
- Fill a gap in a translation mapping. `docs/translation_mappings/` records what
  each source field becomes, and each mapping doc has open questions in it.
- Improve the tutorials in `docs/tutorials/`.
- Triage issues: reproduce a report, or narrow one down to a smaller input.
- Answer a question in [Discussions](https://github.com/transition-zero/tz-oss-interop/discussions).

## Getting set up

interop is managed with [uv](https://docs.astral.sh/uv/). Install uv, then:

```bash
git clone https://github.com/transition-zero/tz-oss-interop.git
cd tz-oss-interop
uv sync --all-groups
uv run pre-commit install
```

That creates `.venv/`, installs the runtime and dev dependencies, registers the
`interop` console script, and wires the git hook. Run every command through
`uv run`, from the repository root, so uv finds that environment.

Check it works:

```bash
uv run pytest
uv run interop
```

`solve` additionally installs Julia and PowerSimulations.jl on first use, which
takes a while and needs network access. See
[`docs/tutorials/solve.md`](docs/tutorials/solve.md).

New to the codebase? [`docs/tutorials/user-tutorial.md`](docs/tutorials/user-tutorial.md)
walks a translate/solve/compare run end to end, and
[`docs/tutorials/developer-tutorial.md`](docs/tutorials/developer-tutorial.md)
extends it with a step of your own. Issues labelled `good first issue` are the
ones we think are self-contained.

## Reporting a bug

Search the open issues first. If it is new, open one with:

- What you ran, and what happened instead of what you expected.
- The interop version or commit, your Python version, and your OS.
- A minimal input that reproduces it. A model file that has been cut down to
  the components that matter is worth far more than a large one, and you can
  usually attach it. Say so if the model is not yours to share, and describe its
  shape instead.
- The console output, including the warnings. interop warns rather than stops
  when a model's data cannot be used, so the warnings often name the problem.

For a security problem, do not open an issue. See [SECURITY.md](SECURITY.md).

## Proposing a change

Small fixes can go straight to a pull request. For anything that changes a
translation's output, adds a format, or moves an interface, open an issue or a
Discussion first and agree the approach — it is much cheaper than finding out at
review that the mapping was already decided somewhere else.

Design decisions of any size get written down. A dated spec in `docs/specs/`
records one decision on the branch that implements it; see
[`docs/specs/README.md`](docs/specs/README.md). Specs are history and are never
edited after they merge. How the code behaves today lives in
`docs/developer_documentation/`.

## Making the change

### Workflow

Fork the repository, branch from `main`, and open a pull request back to `main`.
Branches are named `issue-<number>-<short-slug>`, or a short slug alone when
there is no issue.

Keep a pull request to one subject. Rebase on `main` rather than merging it in,
so the history stays linear.

### Sign your commits off

Every commit must carry a `Signed-off-by` trailer. It certifies that you wrote
the change, or otherwise have the right to submit it under this project's
licence — the full text is the [Developer Certificate of Origin](DCO) 1.1 in
this repository. There is no separate contributor agreement to sign.

That licence is the [Apache License 2.0](LICENSE). Your contribution goes out
under the same terms as the rest of the project, and you keep the copyright in
what you wrote.

`git commit -s` adds the trailer using your configured name and email:

```
Signed-off-by: Jane Developer <jane@example.com>
```

Use a real name and an address you read. CI checks every commit in a pull
request and fails if one is missing a sign-off. To fix a branch you have already
written, `git rebase --signoff main` adds it to each commit.

### Commit messages

The subject line says what the change does, in the imperative and under about
70 characters: `Skip the JuMP model export so a large Sienna solve finishes`.
The body says why. Do not put an issue identifier in code comments or
docstrings — the rationale for a change belongs in its commit message and pull
request, and the code has to stand on its own without them.

### Code standards

Python 3.11 or newer, formatted and linted with ruff, and typed to mypy's strict
mode wherever it is practical. Beyond what a tool checks:

- Functions and methods are named as verb phrases — `build_x`, `stage_y`,
  `read_z` — not as nouns. Boolean queries may start `is_`, `has_` or `wants_`.
- Prose in docstrings and comments is plain English, in short sentences.
- The general translator never names a real-world model, utility or ISO. Explain
  a default by the property it comes from, in the source format's own
  vocabulary. A plugin that reads one publisher's format is the exception, and
  the name belongs inside that plugin.
- Prefer a `NamedTuple` or a dataclass to a bare tuple whose positions are not
  obvious at the call site.

### A model's data never stops a translation

This is the rule most worth knowing before you write a translation step.
Whatever a source model says, however wrong, the translation runs to completion
and reports what it could not use. So:

- Leave out the one component or the one profile that cannot be used, and keep
  the rest.
- Record it through the reporting port *and* log a warning. `COMPONENT_SKIPPED`
  where a whole component goes, `NOT_MAPPED` where the component survives but an
  attribute does not. The event carries the source's own value; derived numbers
  go in the note.
- Name at most three components on a warning and count the rest. A real model
  will put hundreds on one.
- Where a reading is recognisably wrong, drop it rather than guess. Writing a
  number nobody meant is worse than writing nothing.

Raise only for what the code cannot proceed past at all: a file that will not
parse, a missing required parameter, a programming error. Finding fault with a
model is the job of a validator under `interop/plugins/validators/`, which runs
separately and can be as demanding as it likes.

### Tests

Tests are BDD, driven through pytest-bdd, and they describe behaviour from the
user's point of view. A `.feature` file lives in `tests/features/` and its steps
in `tests/step_defs/`; step files drive the REPL through the helpers in
`tests/step_defs/conftest.py` rather than importing `interop` themselves.

`scripts/lint_bdd_only.py` enforces this: a plain `def test_*()` with no
`@scenario` binding fails the lint. If a behaviour cannot be expressed as a
scenario through the user surface, wait until that surface exists rather than
adding a unit test underneath it.

Source fixtures come from the builders in the `interop-testing` package
(`libs/interop-testing/`), one module per framework, not from helpers written
inline. That package is also what a downstream project uses to test its own
pipelines, so it holds nothing specific to this repository's pipelines.

A feature that runs a Polars compute is tagged `@slow @fork_unsafe`. That covers
every feature under a `tests/features/<pipeline>/` subdirectory.

### No data files

interop redistributes no model data. Anything committed here travels in the git
history, the source distribution and the container image, under whatever terms
its publisher set. Build a fixture with a builder instead, and where a case
study needs a published model, say where to download it and which columns a
reference file needs. `scripts/lint_committed_data.py` fails a commit that adds
a file in a data format outside `interop/templates/`, which holds the synthetic
network the tutorial translates.

### Translation mappings

`docs/translation_mappings/` is the source of truth for what a source field
becomes. Consult it before deciding a mapping, and extend it when you add one
rather than deriving the mapping from scratch. Where the doc flags an open
question, the doc wins over anything inferred from code or schemas.

On the Sienna side, [SiennaSchemas](https://github.com/NREL-Sienna/SiennaSchemas)
is authoritative for field names, types, and the document shape. If a field is
not in SiennaSchemas it is not in scope for the output, and a PyPSA field with
no home there travels in the `extensions.json` sidecar instead.

Adding a plugin — a source, step, validator or sink — is covered in
[`docs/developer_documentation/extending.md`](docs/developer_documentation/extending.md),
including the section on contributing one upstream.

## Before you open the pull request

Run the gates. `make lint` runs everything pre-commit does, over all files:

```bash
make lint
make test
```

The full set, and what each one is for:

| Command | What it checks |
| --- | --- |
| `make lint` | Every pre-commit hook over all files |
| `make test` | The pytest-bdd suite |
| `make coverage` | The suite with a coverage report |
| `make mutation` | Whether the tests actually exercise what they cover |
| `make maintainability` | Complexity report, the one CI comments on a PR |

Individual checks, when you want to run just one:

| Command | What it enforces |
| --- | --- |
| `uv run ruff check .` / `uv run ruff format --check .` | Lint and formatting |
| `uv run mypy interop libs tests .github/scripts scripts` | Strict typing |
| `uv run lint-imports` | The hexagonal import contracts in `[tool.importlinter]` |
| `uv run interop-lint-plugin-inheritance …` | A class declaring `name = "…"` inherits its Protocol |
| `uv run interop-lint-plugin-filesystem …` | Plugins reach the filesystem only through `FilesystemPort` |
| `uv run python scripts/lint_bdd_only.py` | Every test binds through pytest-bdd |
| `uv run python scripts/lint_test_decoupling.py` | Step files do not import `interop.*` |
| `uv run python scripts/lint_feature_tags.py` | Feature files carry the mutation-budget tags |
| `uv run python scripts/lint_committed_data.py` | No data file is committed outside `interop/templates/` |
| `scripts/check_action_pins.sh` | Every workflow `uses:` is pinned to a commit SHA |

The two plugin lints take the plugin roots as arguments; `.pre-commit-config.yaml`
has the full invocation, and both ship as console scripts so a downstream project
can run the same contracts over its own `plugins/`.

Mutation testing is worth running locally before you add a test you expect to
gate behaviour —
[`docs/developer_documentation/mutation-testing.md`](docs/developer_documentation/mutation-testing.md)
explains reading the score and investigating a survivor. CI runs it too and
posts the kill score on your pull request.

## Review and merge

CI runs lint, tests across the supported Python versions on Linux and Windows,
mutation testing, a maintainability report, a secret scan, and the DCO check.
All of them must pass.

A maintainer reviews from there. Expect questions about the translation
decisions in particular — a wrong number written silently is the outcome the
project most wants to avoid, so reviewers will ask where a default came from.

Reply to each review comment as you address it, saying briefly how. Pull
requests are squash-merged, so the pull request title becomes the commit
subject on `main`; the sign-off trailers are preserved.

## Glossary

- **Bus** — a node in the network. Components attach to one.
- **Carrier** — the energy carrier a component moves or converts. Electricity
  only, for now; see the scope notes in the mapping docs.
- **Snapshot** — one timestep of the modelled period. A time series has one
  value per snapshot.
- **Source, step, sink** — the three plugin kinds a pipeline composes: read a
  model in, transform the intermediate tables, write a model out.
- **Sienna** — the open-source power-systems modelling ecosystem from NREL.
  PowerSystems.jl holds the data model, PowerSimulations.jl runs the
  optimisation.

## Related projects

- [PyPSA](https://pypsa.org/) — Python for Power System Analysis.
- [Sienna](https://www.nrel.gov/analysis/sienna.html) —
  [PowerSystems.jl](https://github.com/NREL-Sienna/PowerSystems.jl),
  [PowerSimulations.jl](https://github.com/NREL-Sienna/PowerSimulations.jl),
  [SiennaSchemas](https://github.com/NREL-Sienna/SiennaSchemas).
- [OSeMOSYS](http://www.osemosys.org/) — the open-source energy modelling system.
