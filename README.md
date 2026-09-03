# interop

[![Lint](https://github.com/transition-zero/tz-oss-interop/actions/workflows/lint.yml/badge.svg?branch=main)](https://github.com/transition-zero/tz-oss-interop/actions/workflows/lint.yml?query=branch%3Amain)
[![Test](https://github.com/transition-zero/tz-oss-interop/actions/workflows/test.yml/badge.svg?branch=main)](https://github.com/transition-zero/tz-oss-interop/actions/workflows/test.yml?query=branch%3Amain)
[![Mutation](https://github.com/transition-zero/tz-oss-interop/actions/workflows/mutation.yml/badge.svg?branch=main)](https://github.com/transition-zero/tz-oss-interop/actions/workflows/mutation.yml?query=branch%3Amain)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

Translation tooling for energy-system model formats (PyPSA, Sienna, Plexos, OSeMOSYS). Pipelines compose source / step / sink plugins discovered from built-ins, project-local files, and installed third-party packages.

interop is beta software. It runs end to end on published models, and the plugin interfaces and pipeline YAML shape are settled enough to build on, but they still change between versions.

## Install

interop is managed with [`uv`](https://docs.astral.sh/uv/); if you do not already have it, follow uv's [installation instructions](https://docs.astral.sh/uv/getting-started/installation/). Then sync the environment:

```bash
uv sync
```

This creates `.venv/`, installs runtime and dev dependencies, and registers the `interop` console script. Prefix each command with `uv run`, and run it from the repository, so that uv finds this environment.

To get `interop` as a command that runs from any directory, install it as a uv tool instead:

```bash
uv tool install git+https://github.com/transition-zero/tz-oss-interop
```

If your shell does not find `interop`, run `uv tool update-shell`. Then open a new terminal.

The tool install is a copy of the repository at the time you install it. Run `uv tool upgrade interop` to get a newer version. Run `uv tool uninstall interop` to remove it. The tool install does not give you the dev dependencies, so use `uv sync` to work on interop itself.

## Quickstart

`interop` launches a questionary-driven interactive shell. From the
shell, pick `init` to scaffold a project, `cd` into it, then re-launch
`interop` and pick `translate` to run the example pipeline:

```bash
uv run interop      # pick: init, target = my-interop-project
cd my-interop-project
uv run interop      # pick: translate, source = noop, destination = noop, pipeline = example
```

The scaffolded layout is:

```
my-interop-project/
  pipelines/example.yaml           # YAML pipelines, one per file
  adapters.yaml                    # bindings of outbound ports to adapter names
  plugins/
    sources/  steps/  sinks/  adapters/
  inputs/   outputs/               # your data in, results out
  README.md
```

`translate` resolves the pipeline by name (`pipelines/<name>.yaml`), runs every node in order, and logs a summary line (duration, plus each output file's size) on completion. The `noop` source, step, and sink let you exercise the pipeline machinery without a real translation; replace any of them with project-local plugins in `plugins/<category>/` or with a third-party package shipping the same plugin protocols.

The interactive shell needs a real terminal (keypresses, cursor control).
Beyond `translate`, the shell also offers `solve` (run a translated Sienna
system through PowerSimulations.jl; the first run installs Julia and the solver
packages automatically, see `docs/tutorials/solve.md`) and `compare` (diff a
Sienna solve against a PyPSA solve). For a
worked end-to-end example, `docs/tutorials/user-tutorial.md` walks through `translate -> solve
-> compare` against the network `interop init` scaffolds with its `pypsa` example.

## Case studies

We ran interop against three published PLEXOS models. Each page below says where to download
the model, and exactly what to answer at the prompts.

| Model | Published by | Headline | Reproduce |
| --- | --- | --- | --- |
| SEM 2024-2032 | SEM Committee | The peak demand of each year, and the rating of each of the four interconnectors, match the published report to the digit. The average wholesale price that we calculate is 8.9% below the report in 2026. In 2032 it is 10.9% below. | [sem-2024-2032.md](docs/case_studies/sem-2024-2032.md) |
| CAISO 2026 Summer Assessment | CAISO | All five summer months reach an optimal solve. Four of the five hold each generator strictly on or off. May solves only when that rule relaxes. We also solved September with a network that can cut customer load at a price. It cut none, so the generators covered every hour of demand. | [caiso-sa26.md](docs/case_studies/caiso-sa26.md) |
| AEMO 2024 ISP | AEMO | The translation changes no demand value. All 210,240 half-hourly values match the demand traces of the model exactly, in each of the three scenarios. The hydro does not translate: the model measures its reservoirs in water, and the translator reads energy. | [aemo-isp-2024.md](docs/case_studies/aemo-isp-2024.md) |

You can translate and solve these models from this repository. We measured each figure that a
publisher's own report gives on 2026-08-18, with the translator on branch
`caiso-compare-dataset-v2`. The tooling that took those particular measurements is not in this
repository, so those exact figures are not reproducible here. No publisher's data is
redistributed with interop: a case study page says where to download the model, and where a
comparison needs the numbers from a report, which columns to write them out in.

Two limits apply to every figure above.

- **No solve holds back reserve.** A source model keeps spare capacity in hand, to cover a
  generator that fails. The translator writes those reserve requirements to a sidecar file
  beside the network, and nothing applies them. Thus our dispatch is freer than the dispatch
  of the source model.
- **Most of these networks cannot report a shortage.** They hold no generator that supplies an
  hour the other generators cannot cover. Thus such an hour makes the solve fail, and it gives
  no quantity for the energy that the network did not serve. The CAISO reliability pipeline is
  the one exception. It adds such a generator at each bus, priced at the value of lost load of
  that bus, so a shortage becomes a number.

## Extending

`docs/developer_documentation/extending.md` walks through writing a project-local plugin (drop a `.py` file under `plugins/<category>/`), publishing one as a Python package (declare `[project.entry-points."interop.<category>"]` in your package's `pyproject.toml`), and contributing one upstream into `interop/plugins/<category>/`.

## Testing your pipelines

```bash
uv add --group dev "interop" "interop-testing"
```

`interop-testing` is a separate, optional package (`libs/interop-testing/`) publishing the harness interop tests itself with: fixture builders for every framework it reads, assertion vocabulary for every one it writes, project scaffolding, and an in-process pipeline driver, wrapped in a pytest-bdd step vocabulary. It depends on `interop`, never the reverse, so it never becomes a runtime dependency of anything. A project writes BDD scenarios against its own pipelines without copying any of it. Nothing registers itself on install; `docs/developer_documentation/extending.md` covers the one line that registers the steps, then the full vocabulary.

## Headless invocation

`interop headless_cli` runs a single translate pipeline non-interactively —
no prompts, no menu — for use as a container entrypoint (e.g. a GCP Batch
job). Success exits `0`; any failure exits non-zero with a clear message on
stderr/logs.

Like the interactive shell, headless resolves the project (`pipelines/`,
`adapters.yaml`) from the current working directory — `cwd` is the project
root, exactly as it is for `interop`:

```bash
cd my-model
interop headless_cli --pipeline example
```

`--pipeline` is the only required argument; the source/destination
framework pair is derived automatically from the pipeline YAML, so it's
never passed on the command line.

Per-node parameters are supplied as `--override` flags, using the same
`node.field` prefixes as the interactive prompts (but without the trailing `?`),
e.g. `source.file_path`, `step[0].scenario`, `sink[0].output_path`:

```bash
interop headless_cli --pipeline example \
  --override 'source.file_path=inputs/network.nc' \
  --override 'step[0].scenario=high_demand' \
  --override 'sink[0].output_path=outputs/result.json'
```

- `source.<field>=<value>` overrides a field on the pipeline's source node.
- `step[<n>].<field>=<value>` / `sink[<n>].<field>=<value>` override a field
  on the step/sink at that 0-based position in the pipeline YAML (steps and
  sinks are indexed independently — `step[0]` and `sink[0]` refer to
  unrelated nodes).
- `--override` can be repeated for multiple fields.
- `--user-mappings-path <value>` supplies the user mappings file, for
  pipelines that need one.
- `--keep-staging` preserves the staging directory after a successful run
  (off by default).

The same overrides can be set via environment variables instead of flags —
useful when the caller (e.g. a Batch job's container config) sets
environment rather than a command line:

```bash
INTEROP_PIPELINE=example \
INTEROP_OVERRIDE_SOURCE__file_path=inputs/network.nc \
INTEROP_OVERRIDE_STEP_0__scenario=high_demand \
INTEROP_OVERRIDE_SINK_0__output_path=outputs/result.json \
INTEROP_USER_MAPPINGS_PATH=inputs/user_mappings.yaml \
interop headless_cli
```

Flags and environment variables can be combined; where both set the same
field, the flag wins.

Override values are plain strings, passed through exactly as given — the
same as the interactive prompts' free-text answers. Type validation (e.g.
numbers, booleans, enum values) happens downstream against each node's own
parameter schema, so a malformed value surfaces as a translate failure with
a schema-validation message, not a headless-specific error.

`headless_cli` reads and writes through whatever `FilesystemPort` is
configured in `adapters.yaml` — `local_filesystem` by default, or
`http_filesystem` (reading/writing via signed URLs instead of local paths)
when that's what a deployment binds. Override values are location strings
either way; which adapter is bound determines whether they're interpreted
as local paths or URLs.

## Running interop in a container

A `Dockerfile` in the repo root builds a generic image whose entrypoint is
the headless CLI (see "Headless invocation" above) — no project baked in.
The specific project (`pipelines/`, `adapters.yaml`, etc.) is supplied at
run time, mounted into the container.

### Build the image

```bash
docker build -t interop:local .
```

This is a multi-stage build: a builder stage installs the package and its
runtime dependencies with `uv` into a virtualenv; the final image copies
just that virtualenv into a minimal `python:3.13-slim` base, so build
tooling and dev/test dependencies never ship in the runtime image.

### Run it locally against a project

Mount an existing project directory (one scaffolded with `interop init`,
or a real deployment's project) to `/project` — this becomes the
container's working directory, exactly as `cwd` does for a local
`interop headless_cli` invocation:

```bash
docker run -v $(pwd)/my-model:/project interop:local --pipeline example
```

Anything after the image name is passed straight through to `headless_cli`,
so the same `--override`/`INTEROP_OVERRIDE_*` flags and environment
variables documented above work identically here — for env vars, pass them
with `-e`:

```bash
docker run \
  -e INTEROP_PIPELINE=example \
  -e INTEROP_OVERRIDE_SOURCE__file_path=inputs/network.nc \
  -v $(pwd)/my-model:/project \
  interop:local
```

Output files land back on the host filesystem through the same mount,
since the container writes through the mounted volume, not to its own
ephemeral filesystem — `ls my-model/outputs/` after a run shows the real
result.

### Reproducing a failure off-cloud

Because the image and its entrypoint are identical to what a cloud job (e.g., GCP batch)
runs, a failure seen in the cloud can be reproduced locally by running the
same image against the same (or an equivalent) project and override values
— no cloud access needed to debug a translate failure.



## Contributing

Contributions are welcome — bug reports, case studies, translation mappings, and code alike. [`CONTRIBUTING.md`](CONTRIBUTING.md) covers the setup, the conventions, and the quality gates a pull request has to pass. Every commit carries a [Developer Certificate of Origin](DCO) sign-off (`git commit -s`); there is no contributor agreement to sign.

### Develop

| Task | Command |
| --- | --- |
| Lint | `uv run ruff check .` |
| Format check | `uv run ruff format --check .` |
| Auto-format | `uv run ruff format .` |
| Type-check (strict) | `uv run mypy interop libs tests .github/scripts scripts` |
| Import contracts | `uv run lint-imports` |
| Tests (pytest-bdd) | `uv run pytest` |
| Mutation tests | `uv run python scripts/run_mutmut.py run` (see [`docs/developer_documentation/mutation-testing.md`](docs/developer_documentation/mutation-testing.md)) |
| Install pre-commit hook (once) | `uv run pre-commit install` |

The pre-commit hook runs ruff (autofix + format), mypy strict, `lint-imports`, a plugin-inheritance check, and basic file-hygiene checks (trailing whitespace, EOF newlines, YAML/TOML validity) on every `git commit`. Config: `.pre-commit-config.yaml`.

CI runs the lint, test, and mutation suites on every push to a PR branch targeting `main` (`.github/workflows/lint.yml`, `test.yml`, `mutation.yml`). The mutation workflow posts a sticky kill-score comment on the PR.

### Layout

```
interop/                              # Python package (importable as `interop`)
  main.py                             # composition root: builds container, launches REPL
  core/
    use_cases/                        # use case implementations (Translate, InitProject)
    factories.py  pipeline.py  runner.py
    plugin_errors.py
  ports/
    inbound/                          # use case Protocols (TranslateUseCase, InitProjectUseCase)
    outbound/                         # outbound port Protocols (FilesystemPort)
  adapters/
    inbound/
      interactive_cli/                # questionary REPL (the only inbound surface)
    outbound/                         # outbound adapter implementations (local_filesystem)
  di/                                 # Dishka container, plugin discovery, factories
  plugins/{sources,steps,sinks}/      # built-in plugins shipped inside the package
  plugins/shared/                     # utilities shared between plugins
  pipelines/                          # built-in pipeline YAMLs (e.g. noop, noop-chain)
  templates/init/                     # project skeleton copied by `interop init`
  logging_setup.py
tests/
  features/                           # .feature files and harness README
  step_defs/                          # pytest-bdd step implementations
  fixtures/                           # test-fixture packages (e.g. entry-point demo)
docs/                                 # design docs, translation mapping, extending guide
```

Hexagonal invariants enforced by `lint-imports` (see `[tool.importlinter]` in `pyproject.toml`):

- Outbound adapters do not import each other.
- Core does not import adapters, plugins, DI, or main.
- Ports do not import adapters, core, DI, or main.
- Inbound adapters do not import outbound adapters directly.
- Plugins depend only on core and ports.
- Steps do not read or write the filesystem (only sources and sinks do, via `FilesystemPort`).

Use cases live under `interop/core/use_cases/`, each implementing a Protocol port under `interop/ports/inbound/`. Adapters resolve the port from the Dishka container; they never reach into runner or factory helpers directly.

## Documentation

- `docs/tutorials/user-tutorial.md` is the end-to-end walkthrough: `translate -> solve -> compare` against the network `interop init` scaffolds with its `pypsa` example.
- `docs/tutorials/developer-tutorial.md` extends that example with a custom pipeline step (writing your own translation logic).
- `docs/tutorials/solve.md` covers the `solve` command (Julia and PowerSimulations.jl install automatically on first run).
- `docs/case_studies/` holds one page per published model interop has been run against: where to download it, what to answer at the prompts, and what the run measured.
- `docs/developer_documentation/comparison.md` covers the `compare` command and the report it produces.
- `docs/developer_documentation/extending.md` shows how to write project-local plugins, ship plugin packages, and contribute upstream plugins.
- `docs/translation_mappings/translation-from-pypsa-to-sienna.md` is the authoritative mapping reference for PyPSA / Sienna field translation.
- `docs/translation_mappings/translation-from-plexos-to-pypsa.md` states what each part of a PLEXOS model becomes in PyPSA.
- `docs/translation_mappings/translation-from-plexos-to-sienna.md` states the same for Sienna, and `plexos-to-sienna-gap-analysis.md` beside it states what that translation loses and what each loss does to a dispatch.
- `docs/developer_documentation/mutation-testing.md` covers the mutmut workflow.
- `tests/features/README.md` explains the in-process REPL-driven BDD harness and when subprocess is needed.

## Community

- [Discussions](https://github.com/transition-zero/tz-oss-interop/discussions) — questions, ideas, and showing what you have run interop against. Start here rather than with an issue if you are not sure something is a bug.
- [Issues](https://github.com/transition-zero/tz-oss-interop/issues) — bug reports and feature requests.
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — how to set up, what a change needs, and how it gets merged.
- [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) — the Contributor Covenant, and how to report a problem.
- [`SECURITY.md`](SECURITY.md) — how to report a vulnerability privately.

## Acknowledgements

Development of this tool would not have been possible without the funding from [Breakthrough Energy](https://www.breakthroughenergy.org/).

interop builds on [PyPSA](https://pypsa.org/) and on NREL's [Sienna](https://www.nrel.gov/analysis/sienna.html) ecosystem, and would not exist without the work of both communities.

## License

Apache License 2.0 — see [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).

Copyright 2026 TransitionZero. TransitionZero is a company limited by guarantee registered in England and Wales, company number 12914740 and registered charity number 1194424, whose registered office is at 7 Bell Yard, London, WC2A 2JR.
