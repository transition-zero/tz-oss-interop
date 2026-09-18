# Interop Project — Common Context

## Project purpose

Translation tooling for energy-system model formats. The project supports multiple workstreams: PyPSA ↔ Sienna translation, Plexos and OSeMOSYS parsers/converters, a SiennaGridDB-based hub-and-spoke architecture, and a translator UI. Scope is broad; specific deliverables and milestones are tracked in project documentation.

## Repositories (two-repo split)

- **This repo (`github.com/transition-zero/tz-oss-interop`) is the open-source one** — the interop library and package. Build: hatchling + uv; installable and importable as `interop`; ships the `interop init` templates as package data.
- A separate closed-source repo imports this one as a **git dependency** and holds the `interop init` project skeleton that runs as a batch job. Nothing here may depend on it.

## Terminology and aliases

When the following terms appear in prompts or docs, they refer to:

- **Breakthrough / BTE** — Breakthrough Energy, whose grant funds the PyPSA → Sienna translation. That work runs offline, over electricity-only PyPSA networks, and its output is consumed by PowerSimulations.jl.
- **Sienna** — NLR's (née NREL's) open-source power systems modelling ecosystem. Primary packages: PowerSystems.jl (data model), PowerSimulations.jl (simulation framework), SiennaSchemas (JSON schemas).
- **SiennaGridDB** — NLR's canonical domain model. Intended as the hub in the hub-and-spoke architecture.

## Scope assumptions (current, v1)

Unless overridden in a specific prompt:

### PyPSA to Sienna

- **Electricity-only networks.** All buses are AC or DC. Non-electricity carriers (hydrogen, heat, gas) are out of scope and handled in Deferred sections of documentation.
- The authoritative translation mapping lives at `./docs/translation_mappings/translation-from-pypsa-to-sienna.md`. Consult it before making decisions about field mappings, defaults, or scope questions. When adding new mappings, extend the document rather than deriving mappings from scratch. The doc is the single source of truth for translation design decisions. Open questions flagged in the doc take precedence over inferences from code or schemas.

### Sienna to PyPSA

- **Input contract is a SiennaSchemas system, and only that.** The Sienna source (`stage_sienna_system_json`) consumes the SiennaSchemas target shape defined in `./docs/translation_mappings/translation-from-pypsa-to-sienna.md`: a top-level JSON object mapping each Sienna type name to a list of that type's objects (`{ "ACBus": [...], "ThermalStandard": [...] }`), each a flat object with an integer `id`, integer references (`bus`/`area`/`owner_id`), and no `__metadata__`/`internal`/`ext` envelope. Time series are a sibling `TimeSeriesAssociation` list (keyed by integer `owner_id`) whose value arrays live in an HDF5 companion keyed by `time_series_uuid`. PyPSA round-trip fields with no SiennaSchemas home travel in a companion `extensions.json` sidecar, a document keyed by kind whose records are identified by `name`. The sidecar is an optional input, since only this translator writes one.
- **Out of scope as input:** the PowerSystems.jl `to_json` envelope (a flat `data.components` list, `__metadata__`/`internal.uuid`, `{"value": "<uuid>"}` references, an embedded SQLite association store). Do not add handling for it.
- Field-level mappings and the document shape both follow the authoritative doc and SiennaSchemas.

## Repository layout

Commands are executed from the `interop-project/` directory unless otherwise stated.

## Sienna-side ground truth

**SiennaSchemas (JSON) is authoritative** for Sienna field names, types, required/optional status, enum values, the nested shape *within a component*, and the document shape (the type→list container, integer references, the `TimeSeriesAssociation` records). Check `../SiennaSchemas/` first for any Sienna-side claim.

PowerSystems.jl source (`../PowerSystems.jl/src/models/generated/`) is a secondary reference — useful for semantics, but not authoritative on field structure or the document shape.

If a *field* isn't in SiennaSchemas, it isn't in scope for the translator output. PyPSA fields with no SiennaSchemas home are carried in the `extensions.json` sidecar, not on the components.

## Sienna package split

- **PowerSystems.jl** — data model. Defines what a `System` is. Serialises to/from JSON.
- **PowerSimulations.jl** — simulation framework. Takes a `System`, runs optimisation (economic dispatch, UC, PCM). Requires an external solver.
- **HiGHS** — the default open-source solver used in this project.

"Running a Sienna model" requires PowerSimulations.jl, not PowerSystems.jl alone.

## Inbound adapters vs use cases vs ports

Several terms collide here. Keep them distinct.

- **Use cases** are what the application does: `translate`, `solve`, `compare`. They live under `interop/core/use_cases/`. Each is a class that takes its dependencies (factories, outbound ports) via constructor injection and exposes a single `__call__` entry point. Adapters do not call `interop/core/runner.py` or factory helpers directly; they resolve the use-case port from the Dishka container and call it. `TranslateUseCase` is the worked example.
- **Inbound ports** are use-case *interfaces* the core defines (e.g. `TranslateUseCase`). They live under `interop/ports/inbound/`. The core *implements* them in `interop/core/use_cases/`; adapters *call* them via Dishka resolution.
- **Outbound ports** are interfaces the core declares for things it needs from the outside (e.g. `ModelReader`, `ModelWriter`). Adapters implement them; the core calls them. They live under `interop/ports/outbound/`.
- **Inbound adapters** are delivery mechanisms that translate external input into use-case calls. The questionary REPL at `interop/adapters/inbound/interactive_cli/` is the only inbound adapter today. New adapters live under `interop/adapters/inbound/`.

The REPL menu entry for an action resolves the matching use-case port from the Dishka container and calls it: the "translate" menu choice resolves `TranslateUseCase` and invokes it. Adapters do not call other adapters and do not reach into `interop/core/runner.py` or factory helpers directly.

`interop/main.py` builds the container and launches the REPL. When a new adapter joins (REST, file-watcher, etc.), it gets its own entry in `main.py`. There is deliberately no config-driven plugin loader; in-code wiring is verified by mypy and visible to refactoring tools.

## Coding conventions

- Python 3.11+.
- `uv` for Python environment management.
- `ruff` for linting and formatting.
- Typed (mypy strict) where practical.
- Never fail silently, but prefer reporting to stopping. See "A model's data never stops a translation" below.
- Names come from the closed verb table in "Names" below. A function or a method takes a verb from that table, and never a noun.
- Prose (docstrings, comments, PR descriptions) uses plain English: say what something is or does directly, in short sentences, rather than dense or convoluted phrasing.
- Never write comments or docstrings that explain or refer to an issue, ticket, or unit of work. Code prose describes the code as it stands: it must not mention issue/ticket identifiers (e.g. `ISSUE-186`, `ENG-7311`), must not say "this ticket" or "component tickets", and must not justify what a given issue owns, defers, or leaves to another issue. Delete such comments outright rather than rephrasing them; the code stands on its own and the rationale belongs in the PR description. For example, never write "Buses are the real subject of ISSUE-186; this maps only what a bus-referencing component needs … it leaves the node's region location and voltage to ISSUE-186 and applies PyPSA's defaults meanwhile."
- Never name a specific real-world model in the general translator. This is a general-purpose translator: no behaviour, default, constant, threshold, prompt, docstring, comment, or test fixture in the shared translation path may be described, justified, or illustrated by one particular model, utility, or ISO (e.g. CAISO, ERCOT, NEM). Say what the code does in the source format's own vocabulary and explain a value by the property it comes from, never by the model it was observed in. Never write "exact = true mixed-integer, matches CAISO" or "the CAISO model ties Spin to 0.012"; write what the option does and where the number comes from. A named plugin that reads one publisher's format is the one exception, and its name belongs in the plugin, not in the shared path.
- Prefer a small named object (a `NamedTuple` or dataclass with named fields) over a bare tuple when the tuple's positions are not self-evident at the call site.

## Names

This section holds the whole name vocabulary. A name must tell the reader what a call
does, and what happens when the thing that the name states is absent.

### The verb table

Each row answers two questions. What does the call do? What happens when the thing that
it names is absent? `no absent case` means the call looks nothing up, so nothing can be
absent. That column does not say whether the call can fail for another reason. A call
that touches the disk can still raise.

| Verb | Means | When absent | Do not use for |
| --- | --- | --- | --- |
| `stage_` | A source copies external input into `staging_dir` and builds a `State` | raises | a step, which changes a `State` in memory |
| `read_` | Bytes, rows or fields from a named source | raises | an in-memory projection |
| `load_` | A whole model or config from a source, parsed and checked | raises | raw bytes, which is `read_` |
| `parse_` | Text or a raw mapping into an object | raises | a call that opens a file, which is `read_` |
| `get_` | One existing thing, by key | **raises** | a read that can answer nothing, which is `find_` |
| `find_` | One thing, by key | **returns `None`** | a read whose absence is a fault |
| `list_` | Every known member, as a `list` | empty list | one member; a scalar |
| `choose_` | The winner among candidates, by a stated rule | returns `None` | a read by key, which is `get_` or `find_` |
| `build_` | Assemble a value or a wired object, in memory | no absent case | a destination column, which is `map_` or `derive_` |
| `map_` | Translate source rows into destination rows, and record one event for each | no absent case | a value with no event behind it |
| `derive_` | Compute one destination value from source values, and record the event | no absent case | a value the source states directly, which is `map_` |
| `convert_` | The same quantity, in different units | no absent case | a different quantity, which is `derive_` |
| `enrich_` | Add computed columns to a table, and keep its rows | no absent case | a table with different rows, which is `reshape_` |
| `reshape_` | The same values, in a different table shape | no absent case | a change to a value |
| `express_` | Build a `pl.Expr` that a later `with_columns`, `filter` or `select` evaluates | no absent case | a value the call computes itself, which is `build_` or `derive_` |
| `add_` | Attach a new member to a container that exists | raises on a duplicate | the container itself, which is `build_` |
| `set_` | Replace the value of a named slot, in memory | writes it anyway | a file, which is `write_` |
| `fill_` | Give a value to each empty slot | no absent case | a slot that already states a value |
| `drop_` | Take rows or columns out of a table | returns, never raises | a file, which is `delete_` |
| `write_` | Persist bytes or an object to a named place | no absent case | an in-memory change, which is `set_` |
| `delete_` | Remove a file or a directory | raises | a container in memory, which is `drop_` |
| `copy_` | Duplicate a file or a directory | raises | a copy in memory |
| `record_` | Append a `TranslationEvent` through the recorder | no absent case | the console, which is `warn_` |
| `warn_` | Write one `log.warning`, and name at most three components | no absent case | the audit trail, which is `record_` |
| `report_` | Record the events **and** write the warning | no absent case | one of the two alone |
| `reject_` | A guard. Raises when the named condition holds | no absent case | a call that returns a value |
| `require_` | **Return the thing**, or raise | raises | a guard that returns nothing, which is `reject_` |
| `is_` / `has_` / `can_` / `wants_` | A predicate, returning `bool` | answers `False` | a call that raises; a call that returns a `pl.Expr`, which is `express_` |
| `normalise_` | The canonical form of a value | raises | a check that returns nothing |
| `serialise_` | A model, in its wire or storage shape | no absent case | a read back, which is `parse_` |
| `render_` | A report, in its output format, through a report port | no absent case | data a later node reads |

A domain verb is not in the table. A name can use a domain verb when it names an action
of the domain: `solve`, `translate`, `compare`, `discover` and `init`. Every other verb
must come from the table.

### The words that leave the vocabulary

| Out | Use |
| --- | --- |
| `make_`, `assemble_`, `construct_` | `build_` |
| `select_`, `resolve_`, `locate_`, `lookup_`, `fetch_`, `retrieve_` | `get_`, `find_` or `choose_` |
| `check_`, `verify_`, `refuse_` | `reject_`, or a predicate |
| `collect_` | `build_` or `list_`, because Polars owns `.collect()` |
| `emit_` | `write_` in Python. The sink plugin names keep `emit_`. |
| `save_` | `write_` |

### The nouns

- A `pl.DataFrame` or a `pl.LazyFrame` is a **table**. Do not call it a frame.
- A `list[dict]` is **rows**.
- A `FilesystemPort` value is a **location**. `interop/ports/outbound/filesystem.py`
  states the type `Location`.
- A name that stands for data in `State` keeps the `source_` or `destination_` prefix
  that `State` uses.
- Do not name a type `...Set` unless it holds a `set`.

### A property against a method

- A property takes a noun name. A property that answers `bool` takes `is_` or `has_`.
- A call with parentheses takes a verb. The test is what the caller writes, and not what
  the signature holds. `run.status` is right and `run.status()` is wrong.
- A method with a noun name has two ways out. Make it a property when it answers a
  question, takes no argument, costs almost nothing and changes nothing. Give it a verb
  in every other case.

### A name must not abbreviate

Write the whole word. A single letter is for a small loop and for nothing else. A name
that mirrors an external vocabulary is not ours to rename. PyPSA states the attribute
`idx` and `argparse` states the keyword `dest`, so both keep their form.

### A factory must say that it builds

A classmethod called `of(...)` or `at(...)` reads as a setting on the class. It does not
tell the reader that a new object comes back. A call that makes an object in memory
starts with `build_`. The rest of the name says what the call makes.

### How to add a verb

The table is the whole vocabulary. Add a new verb to the table in the same pull request
that first uses it. Never use a new verb first and write it down later, because the next
author reads the table and not the code. A new verb must earn its row:

1. No verb in the table already holds that meaning.
2. The new row can say what happens when the thing is absent.

Fill in all four columns. Then say in the pull request which verb you rejected, and why.

### The exceptions

A rule with no written exception gets broken quietly. These names disagree with the rules
above, and they are correct as they stand.

- **A plugin `name` is a published key.** A pipeline YAML file and a downstream project
  both name it. `stage_plexos_xml`, `plexos_to_pypsa_map_buses` and
  `emit_power_simulations_system_json` are three of them. A validator named for the
  component that it checks, such as `pypsa_generators`, is correct.
- **The plugin protocols keep their method names.** `Source.load`,
  `StagedSource.load_into_state`, `TranslationStep.run`, `Sink.write` and
  `Validator.validate` are the contract in `interop/core/pipeline.py`. A downstream
  project implements them.
- **The outbound ports keep their method names.** `FilesystemPort.read_bytes`,
  `open_read`, `can_read`, `locate` and `resolve`, and `ReportingPort.render`, are the
  contract that an adapter implements. `locate` and `resolve` both build a location and
  neither one reads a file, so the table would rename them. An adapter outside this
  repository implements the port, so they stay.
- **`fs` keeps its short form.** It names the `FilesystemPort` value. "Quality gates"
  below states `self._fs`, and `interop/lints/plugin_filesystem.py` holds the constant
  `FS_ATTRIBUTE = "_fs"`, so the lint fails a rename. Use `fs` for this one type, and
  write the whole word everywhere else.
- **The Dishka container names a provider for the type that it gives.**
  `interop/di/container.py` holds `@provide` methods such as `filesystem` and `solver`.
  Dishka reads the return type, and no reader calls the method.
- **`Translation.make_events` keeps its name.** "Translation utilities" below documents
  it, and every translation module states it. It changes everywhere at once, or not at
  all.
- **A pydantic validator keeps `_validate_...`.** Pydantic calls it, and no reader calls
  it. `model_post_init` and every pydantic field name also keep their form.
- **The shared utility surface keeps its names.**
  `interop/plugins/shared/translation_runner.py` publishes `Translation`, `make_events`,
  `apply_translations`, `filter_component`, `finalise`, `SkipReport` and `SkipRule`.
  "Translation utilities" below documents all seven, and every translation module states
  them.
- **A BDD step function is named for its Gherkin phrase.**
  `libs/interop-testing/src/interop_testing/steps/` holds `given_` and `assert_`
  functions. Each one takes its name from the scenario line that it binds, so
  `given_env_var_set` is correct.

### What a rename must not change

No published name changes. A plugin `name`, a pipeline YAML key and a params field all
stay as they are. A column name in a destination table and a key in `extensions.json`
also stay.

## A model's data never stops a translation

Finding a problem in the input is the validators' job, not translation's. Validators
(`interop/plugins/validators/`) run separately from translate and solve and can be as
demanding as they like. Translation gets the user everything that did translate, plus a
list of what did not.

So **never raise over anything a source model says**. However wrong the value is, the
translation runs to completion:

- **Leave out what cannot be used, and say so.** A generator whose minimum output sits
  above its ceiling, a Battery stating no rated power, a profile whose length does not fit
  the snapshot window: drop that one component or that one profile, keep the rest.
- **Record it through the reporting port, and warn.** Both, always. The event goes through
  a reporter on `ScopedRecorder` so `decisions.md` carries it per component:
  `COMPONENT_SKIPPED` where a whole component is left out, `NOT_MAPPED` where the component
  survives but one attribute does not. The source field carries the *source's* value (the
  PLEXOS `Min Stable Level` in MW), never the derived one; put the derived numbers in the
  note. The `log.warning` alongside it is what reaches the console, and what
  `the log contains "…"` asserts.
- **Cap what you name.** A real model puts hundreds of components on one warning; name
  three and count the rest.
- **Prefer dropping to guessing.** Where a reading is recognisably wrong (Region Loads that
  are participation shares, not MW), leave it out rather than write a value nobody meant.
  Silently writing the wrong number is the one outcome worse than stopping.

Raise only for what the code genuinely cannot proceed past, none of which is model data:
a file that will not parse, a missing required parameter, a programming error.

## PyPSA → Sienna pipeline conventions

These apply to every component translation ticket (buses, generators, loads, lines, …).

- **Sink makes no decisions.** `emit_system_json` only formats data from intermediate tables, no translation events should be emitted.
- **Per-event emission within a single loop.** Each step uses one `iter_rows()` pass, selecting only the columns needed. One event = one row in the translation mapping table, keeping each transformation auditable against the doc.
- **Full computation graph.** Never collapse event chains: if a value flows X→Y→Z, emit two events (X→Y and Y→Z), not one (X→Z).
- **No magic strings.** Use constants or enums from `interop/plugins/shared/pypsa_sienna_constants.py` instead of bare string literals for component names, column names, table keys, framework names, and numeric thresholds. Add a new constant to the shared file rather than repeating a value.
- **Lazy time-series.** As per the `State` docstring, only call `.collect()` on aggregated data (e.g. after `.group_by().agg()`) or a column-subset (`.limit(N)`, `.select([col])`). Never call `.collect()` directly on a `source_time_series` LazyFrame — those frames can be billions of rows on real networks. Source topology tables (`State.source_topology`) are component-scale (one row per component) and always safe to collect in full.

## Translation utilities

Optional shared utilities in `interop/plugins/shared/translation_runner.py` for steps that translate tabular source data into a destination schema with a full audit trail. Used by the PyPSA → Sienna pipeline; available to any pipeline step.

**`Translation`** — pairs a Polars column expression with an event factory:
```python
@dataclass
class Translation:
    exprs: list[pl.Expr]  # column expressions; empty list = event-only
    make_events: Callable[[dict, dict], Sequence[TranslationEvent]]
```
`make_events(old_row, new_row)`: `old_row` is the table state before the current batch; `new_row` is after. Define as module-level constants — no closures over runtime data.

**`apply_translations(table, translations, recorder)`** — one `with_columns` batch + one `iter_rows` pass emitting events.

**`filter_component(table, condition, report, recorder)`** — splits into `(passing, skipped)`, emits `COMPONENT_SKIPPED` for each skipped row, and logs one warning naming a few of them. `report` is a `SkipReport`, which states one reason a filter drops rows and builds both the event and the warning from it:
```python
@dataclass(frozen=True)
class SkipReport:
    pipeline: str  # "pypsa-to-sienna"
    framework: str  # the source framework the event names
    component: str  # "Generator"
    name_col: str  # the column holding the component name
    reason: str  # completes "N Generator(s) <reason>, so each is left out"
    counted_noun: str  # what stands where "Generator(s)" does, already plural
    note: str | Callable[[dict], str]  # what decisions.md carries against the component
```
Two optional fields cover the rows that need them: `listed` makes the warning list a column other than `name_col`, under a word of its own, and `attribute_col` names the one source attribute a drop turns on. `SkipRule` pairs a keep expression with a `SkipReport` where a step applies several in a row.

**`finalise(table, schema, recorder, component, name_col)`** — null-initialises unmapped schema columns with `NOT_MAPPED` events, then selects to the pure destination schema. `EventKind.NOT_MAPPED` is filterable in user-facing views; a schema column with no event at all is a detectable gap.

The source table passed to `apply_translations` can be enriched with any pre-computed columns (e.g. time-series aggregates, representative-row lookups) that `make_events` needs — these are dropped by `finalise`. See `interop/plugins/shared/pypsa_sienna_translations/` for worked examples across buses, loads, and areas.

## Quality gates

- **Import contracts** (`uv run lint-imports`) enforce the hexagonal layering: inbound adapters are mutually independent, core does not depend on adapters/DI/main, ports do not depend on adapters/core/DI/main. Contracts live in `pyproject.toml` under `[tool.importlinter]`. If you need to change them, do so in a dedicated commit explaining why.
- **Mutation testing** (`uv run python scripts/run_mutmut.py run`) gauges whether tests actually exercise the code paths they cover. Run locally before adding a test you expect to gate behaviour. See `docs/developer_documentation/mutation-testing.md`. On macOS the `scripts/run_mutmut.py` wrapper is required (mutmut v3's setproctitle call crashes in a forked child); on Linux it is a transparent passthrough.
- **Test decoupling** (`uv run python scripts/lint_test_decoupling.py`) forbids `interop.*` imports in BDD step files (`tests/step_defs/*.py`, except `conftest.py`). BDD scenarios describe behavior from the user's perspective: drive translate through the REPL via the helpers in `conftest.py` (`run_translate`, `write_pipeline`, `write_project_plugin`) and assert on `printed_messages` or files on disk.
- **Plugin filesystem abstraction** (`uv run interop-lint-plugin-filesystem plugins interop/plugins interop/templates/init/plugins interop/templates/examples/pypsa/plugins`) keeps plugins behind the `FilesystemPort`. Sinks and sources may hand a params path (or anything derived from one) only to `self._fs.*` (`read_bytes`/`write_bytes`/`open_read`/`open_write`), never to `open`/`Path`/library calls taking a path; `staging_dir` scratch is exempt for sources. Steps and validators must not touch the filesystem at all (no `open`, no `Path(...)`, no `staging_dir` writes) since they transform in-memory `State`. Reading a netCDF network through a stream goes via `interop/plugins/shared/netcdf.py` (`netcdf_engine` picks scipy vs h5netcdf from the magic bytes).
- **Plugin inheritance** (`uv run interop-lint-plugin-inheritance plugins interop/plugins interop/templates/init/plugins interop/templates/examples/pypsa/plugins --adapters-dir interop/adapters/outbound`) requires a class declaring `name = "..."` under a plugin category to actually inherit its Protocol — `Source`/`StagedSource`, `TranslationStep`, `Validator`, `Sink`, or the port it names in `port = ...`. Structural typing lets mypy pass a class discovery rejects at registration time. Both plugin lints live in `interop/lints/` and ship as console scripts, so a downstream project runs the same contracts over its own `plugins/`; see `docs/developer_documentation/extending.md`.
- **No committed data** (`uv run python scripts/lint_committed_data.py`) fails a tracked file in a data format (`.csv`, `.nc`, `.parquet`, `.xlsx`, …) outside `interop/templates/`. interop redistributes no model data: a test fixture comes from an `interop-testing` builder, and a case study says where to download the model and which columns a reference file needs. `ALLOWED_DIRECTORIES` in the script records the one exception and its reason.
- **BDD-only tests** (`uv run python scripts/lint_bdd_only.py`) forbids plain pytest in this project. Every `tests/**/test_*.py` (other than `conftest.py`) must bind its tests through pytest-bdd: either `scenarios("<file>.feature")` to bind every scenario in a feature file, or `@scenario("<file>.feature", "<title>")` on individual functions. A bare `def test_*()` with no `@scenario` decorator is a violation — if a behavior cannot be expressed as a scenario driven through the user surface, defer the test until the user surface exists rather than adding a unit test.

## Testing conventions
- **Builder fixtures for pipeline BDD tests.** Source fixtures should be created via a reusable builder class, not inline helpers or a pipeline-specific conftest. Builders live in the separate `interop-testing` package (`libs/interop-testing/src/interop_testing/`): one plain-Python module per framework under `builders/`, with its BDD `Given` steps — and the `Then` steps asserting on that framework's output — in the matching `steps/` module. `tests/conftest.py` registers the lot with `pytest_plugins = ["interop_testing.steps"]`. A new source format follows the same pattern: add both modules and list the steps one in `steps/__init__.py`.
- **A feature that runs a Polars compute is tagged `@slow @fork_unsafe`.** That covers every feature file in a `tests/features/<pipeline>/` subdirectory, and any top-level feature driving a real compute (`compare_summary.feature`). `@fork_unsafe` tells `scripts/run_mutmut.py` to re-exec the mutants it covers in a fresh interpreter, because a forked child that touches Polars deadlocks at any pool size; `@slow` keeps that re-exec out of the CI mutation run, where it costs seconds per mutant. `uv run python scripts/lint_feature_tags.py` enforces that a subdirectory feature carries `@slow`, and that `@fork_unsafe` never appears without it; it cannot tell that a scenario runs a Polars compute, so a missing `@fork_unsafe` still surfaces as a mutation timeout rather than a lint failure. The Test job applies no marker filter, so the scenarios still run on every push, and `make mutation-full` runs them under mutation locally.
- **What stays out of the harness.** `interop-testing` is the surface a downstream project tests its own pipelines against, so it holds nothing specific to this repo's pipelines: questionary/REPL stubbing, the `invoke_*` helpers, per-pipeline driver glue and inline plugin-source fixtures all stay in `tests/step_defs/`. Step files may import `interop_testing` directly (the decoupling lint exempts it); every other `interop.*` import still routes through `tests/step_defs/conftest.py`.

## Design specs

- **Every approved design is committed.** After the brainstorming skill presents a design and the user approves it, write the spec to `docs/specs/YYYY-MM-DD-<topic>-design.md` and commit it on the branch that implements it. Give it its own commit, before the first code commit.
- **A spec is a dated record of one decision, not a description of current behaviour.** Never edit a spec after its branch merges. When a later change replaces the design, write a new dated spec and name the spec it replaces in the first line.
- **Current behaviour lives in `docs/developer_documentation/`.** Where a spec and the developer documentation disagree, the developer documentation is correct and the spec is history. Do not copy a spec into the documentation tree, and do not point a reader at a spec for how the code works today.
- **The implementation plan stays out of git.** Write it to `.context/plans/YYYY-MM-DD-<feature-name>.md`, which git already excludes. The plan is a task list for one branch and has no value after the branch merges.

## PR review

- When addressing PR review comments, reply to each comment thread to confirm it has been addressed, briefly noting how (and the commit, if useful). Do this for every comment you act on, not just a subset.
