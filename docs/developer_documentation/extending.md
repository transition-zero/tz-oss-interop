# Extending interop

`interop` pipelines are built from five plugin categories:

- **Sources** load the initial `State` (`interop.core.pipeline.StagedSource`).
- **Steps** transform `State` (`interop.core.pipeline.TranslationStep`).
- **Validators** inspect the loaded source `State` and flag issues without changing it (`interop.core.pipeline.Validator`).
- **Sinks** consume the final `State` (`interop.core.pipeline.Sink`).
- **Outbound adapters** implement an outbound port (e.g. `interop.ports.outbound.filesystem.FilesystemPort`) so sources, sinks, and use cases can talk to the outside world without depending on a concrete I/O backend.

A pipeline can also be built out of other pipelines rather than out of nodes; see
[composing pipelines](pipeline-composition.md) for the composed manifest shape, how a leg's
input is wired to an earlier leg's output, and how mapping pipelines derive the user
mappings files a chain's legs consume.

`State` (`interop.core.pipeline.State`) is a dataclass, not a free-form dict. A Source populates `source_topology` (one `pl.LazyFrame` per component class) and `source_time_series` (long `snapshot/component/value` frames, plus any further columns a source's own values need; the PLEXOS source adds a `sample` column, null except where a value comes from a Monte Carlo replication), staged to parquet under `staging_dir`. Steps transform those frames and build up `destination_tables` (one `pl.DataFrame` per output component type). A Sink reads `destination_tables` and writes it out. Per-node configuration lives in `params_schema`, a Pydantic `BaseModel` (or `None`); per-invocation values like input/output paths flow from the pipeline YAML through `params` to the node at run time. For a full worked example of a custom source, step, and sink against the PyPSA to Sienna example, see the [developer tutorial](../tutorials/developer-tutorial.md); this guide is the reference for the plugin contracts and discovery.

Discovery scans three locations on every run, in this order:

1. Built-ins shipped inside `interop/plugins/<category>/` and `interop/adapters/outbound/`.
2. Entry points declared by installed packages (`interop.sources`, `interop.steps`, `interop.validators`, `interop.sinks`, `interop.adapters` groups).
3. Project-local files under `./plugins/<category>/` at the current working directory.

A plugin is registered under its `name` attribute. Names must be unique within a category but can repeat across categories (a Source named `"stage"` and a Step named `"stage"` are fine).

## 1. Project-local plugin

A project that ran `interop init <project>` ships with empty `plugins/sources/`, `plugins/steps/`, `plugins/sinks/`, and `plugins/adapters/` directories. Drop a `.py` file into the matching directory, inherit the Protocol, declare `name` and `params_schema`, and reference the plugin by `name` from a pipeline YAML in `pipelines/`. The init skeleton does not yet include a `plugins/validators/` directory; create it yourself and discovery will scan it on the next run, exactly like the others.

### Source

Subclass `StagedSource` and implement `load_into_state(params, staging_dir)`. The
base class creates `staging_dir` and cleans it up afterwards; your job is to read
the input and return a `State`. Stage each frame to parquet under `staging_dir` and
scan it lazily, so a large input is never held in memory in full.

`plugins/sources/csv_reader.py`:

```python
from pathlib import Path
from typing import ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import StagedSource, State
from interop.ports.outbound.filesystem import FilesystemPort


class CsvReaderParams(BaseModel):
    path: str  # a directory of component CSVs


class CsvReader(StagedSource):
    name: ClassVar[str] = "csv_reader"
    params_schema: ClassVar[type[BaseModel] | None] = CsvReaderParams
    prefix: ClassVar[str] = "csv"

    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def load_into_state(self, params: BaseModel | None, staging_dir: Path) -> State:
        assert isinstance(params, CsvReaderParams)
        frame = pl.read_csv(self._fs.read_bytes(Path(params.path) / "buses.csv"))
        out = staging_dir / "topology" / "buses.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        frame.write_parquet(out)
        return State(staging_dir=staging_dir, source_topology={"buses": pl.scan_parquet(out)})
```

A Source's `__init__` may take a `fs: FilesystemPort` to read through the
configured outbound adapter rather than touching the disk directly (it hands paths
only to `self._fs`). Sources that need no I/O omit the parameter.

In a pipeline YAML:

```yaml
source:
  name: csv_reader
  params:
    path: inputs/network_csv
```

### Step

A step reads frames off the `State`, transforms them, and returns the `State`.

`plugins/steps/rename_bus_carrier.py`:

```python
from typing import ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep


class RenameBusCarrier(TranslationStep):
    name: ClassVar[str] = "rename_bus_carrier"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def run(self, state: State, params: BaseModel | None) -> State:
        buses = state.source_topology["buses"].collect()
        state.source_topology["buses"] = buses.with_columns(
            pl.col("carrier").str.to_uppercase()
        ).lazy()
        return state
```

Steps never receive a `FilesystemPort`: they only transform the in-memory `State`. Any I/O they need must be carried on the `State` by a Source or written out by a Sink. The lint-imports contract `Steps do not read or write filesystem` enforces this.

In a pipeline YAML:

```yaml
steps:
  - name: rename_bus_carrier
```

A step with `params_schema = None` takes no `params` block. Supplying one is an error.

#### Emitting translation decisions

Steps may declare an optional `recorder: ScopedRecorder` parameter in `__init__` to record `TranslationEvent`s that surface in the decisions report. Steps that don't declare `recorder` are unaffected: the factory filters out parameters a step doesn't accept.

`plugins/steps/default_bus_voltage.py`:

```python
from typing import ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.ports.outbound.reporting import (
    DestinationField,
    EventKind,
    TranslationEvent,
)


class DefaultBusVoltage(TranslationStep):
    name: ClassVar[str] = "default_bus_voltage"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def run(self, state: State, params: BaseModel | None) -> State:
        buses = state.source_topology["buses"].collect()
        if buses["v_nom"].null_count():
            buses = buses.with_columns(pl.col("v_nom").fill_null(380.0))
            self._recorder.append(
                TranslationEvent(
                    kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
                    destinations=[
                        DestinationField(
                            framework="pypsa",
                            component="Bus",
                            name="all",
                            attribute="v_nom",
                            value=380.0,
                            unit="kV",
                        )
                    ],
                    note="v_nom missing; using translator default 380 kV",
                )
            )
            state.source_topology["buses"] = buses.lazy()
        return state
```

`recorder` is the only auto-injected dependency available to steps. The factory tags every recorded event with the step's `name` before it reaches the reporter, so the report's `Step` column populates without further effort. See `interop/ports/outbound/reporting.py` for the full `TranslationEvent` field set.

### Validator

A validator reads the loaded source `State` and flags data-quality issues on it, without transforming it. Validators run **once, before any step**, and each issue is recorded on the `State` via `self.emit_validation_error(...)` — a validator does not mutate the frames, and does not raise to report a finding. The accumulated issues are written to a standalone `validation-report.md`.

Two commands run validators:

- `interop validate` runs a pipeline's validators against its source and writes the report, **without translating** — so input problems surface before committing to a translate-then-solve. Reporting is its whole job, so it never stops on a finding.
- `interop translate` runs the same validators first and writes the report, then **stops if any finding is CRITICAL** — reaching no step or sink, and exiting non-zero.

Implement `validate(state, params)` and return `None`. Each `emit_validation_error` call takes a `ValidationSeverity`, the offending `component`/`name`, a `message`, and optional `attribute`/`value`; every issue is stamped with the validator's `name` automatically.

Pick the severity by what it means for the translation, since `translate` acts on it:

- **`CRITICAL`** — the input cannot be translated. Every validator that completes runs before anything stops, so one CRITICAL finding does not hide the others and the report names everything to fix.
- **`WARNING`** — the input is unusual but translatable, including anything the pipeline recovered from itself. A run carries on.

**Severity is a property of the finding, not of who found it.** A source may append to `state.validation_errors` while loading — `stage_plexos_xml` records dangling references it dropped — and `translate` treats those exactly like a validator's. So a source reporting a condition it recovered from wants `WARNING`; a `CRITICAL` from a source halts the run just as one from a validator does.

Raising from `validate` is not how a validator reports a bad input — it means the validator itself is broken. It is never recorded as a finding, and it fails the run. It does **not** stop the validators after it: a bug in one check would otherwise hide every real problem the others would have reported. Crashes are collected, the report is written as usual, and they are then raised together as an `ExceptionGroup` naming each validator that failed.

`plugins/validators/non_negative_generator_capacity.py`:

```python
from typing import ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import State, Validator
from interop.ports.outbound.validation import ValidationSeverity


class NonNegativeGeneratorCapacity(Validator):
    name: ClassVar[str] = "non_negative_generator_capacity"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def validate(self, state: State, params: BaseModel | None) -> None:
        # Source topology is component-scale (one row per component), so a
        # full collect is safe here — unlike source_time_series, which is not.
        generators = state.source_topology["generators"].collect()
        for row in generators.filter(pl.col("p_nom") < 0).iter_rows(named=True):
            self.emit_validation_error(
                state,
                ValidationSeverity.CRITICAL,
                component="Generator",
                name=row["name"],
                message="p_nom is negative; capacity cannot be below zero",
                attribute="p_nom",
                value=row["p_nom"],
            )
```

In a pipeline YAML:

```yaml
validators:
  - name: non_negative_generator_capacity
```

Like steps, validators with `params_schema = None` take no `params` block. A pipeline may list any number of validators; each runs in order.

#### Consuming a user mapping

A validator whose `__init__` declares a parameter typed as a `UserMappings` subclass is handed that mapping, parsed from the project's `user_mappings.yaml`. This is the same mechanism steps use — the factory injects the parsed mapping and filters out parameters a validator doesn't declare. `interop validate` prompts for the mappings file **only when a validator consumes one** (a mapping needed solely by a step is irrelevant to validation), and reports a clear error if a required mapping is missing.

`plugins/validators/carrier_allowlist.py`:

```python
from typing import ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import State, Validator
from interop.core.user_mappings import UserMappings
from interop.ports.outbound.validation import ValidationSeverity


class CarrierAllowlist(UserMappings):
    allowed_carriers: list[str]


class CarrierValidator(Validator):
    name: ClassVar[str] = "carrier_validator"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, mapping: CarrierAllowlist) -> None:
        self._allowed = set(mapping.allowed_carriers)

    def validate(self, state: State, params: BaseModel | None) -> None:
        buses = state.source_topology["buses"].collect()
        for row in buses.filter(~pl.col("carrier").is_in(list(self._allowed))).iter_rows(
            named=True
        ):
            self.emit_validation_error(
                state,
                ValidationSeverity.WARNING,
                component="Bus",
                name=row["name"],
                message=f"carrier {row['carrier']!r} is not in the configured allowlist",
                attribute="carrier",
                value=row["carrier"],
            )
```

`user_mappings.yaml`:

```yaml
allowed_carriers: [AC, DC]
```

`recorder` (the decisions reporter) is **not** injected into validators — their output is the validation report, not the translation-decisions report. A `UserMappings` subclass is the only auto-injected dependency available to a validator.

Sources take a mapping the same way, alongside their `fs`, which is how a mapping pipeline reads the user's own file without needing a path param for it. A sink does not consume mappings but may declare that the file it *writes* is one, with `writes_user_mappings`; see [composing pipelines](pipeline-composition.md#mapping-pipelines).

### Sink

A sink reads the finished `destination_tables` (one `pl.DataFrame` per output component type) and writes them out.

A sink also reads `destination_time_series` (one `pl.LazyFrame` per key): output a step derived but left unevaluated, because it scales with the number of snapshots rather than with component count. The sink is the only place it is collected — do that once, in a streaming pass (`pl.LazyFrame.sink_parquet` or `collect(engine="streaming")`). Sinks that only read `destination_tables` are unaffected.

`plugins/sinks/csv_writer.py`:

```python
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel

from interop.core.pipeline import Sink, State
from interop.ports.outbound.filesystem import FilesystemPort


class CsvWriterParams(BaseModel):
    component: str
    path: Path


class CsvWriter(Sink):
    name: ClassVar[str] = "csv_writer"
    params_schema: ClassVar[type[BaseModel] | None] = CsvWriterParams

    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def write(self, state: State, params: BaseModel | None) -> None:
        assert isinstance(params, CsvWriterParams)
        table = state.destination_tables[params.component]
        self._fs.write_bytes(params.path, table.write_csv().encode("utf-8"))
```

In a pipeline YAML:

```yaml
sinks:
  - name: csv_writer
    params:
      component: ACBus
      path: outputs/acbus.csv
```

### Outbound adapter

`plugins/adapters/s3_filesystem.py`:

```python
from pathlib import Path
from typing import ClassVar

from interop.ports.outbound.filesystem import FilesystemPort


class S3Filesystem(FilesystemPort):
    name: ClassVar[str] = "s3_filesystem"

    def read_bytes(self, path: Path) -> bytes: ...

    def write_bytes(self, path: Path, data: bytes) -> None: ...
```

A project-local outbound adapter is discovered and registered alongside the built-in `local_filesystem`. The core uses a specific adapter only when something (currently the default in `interop/di/container.py:DEFAULT_FILESYSTEM`) binds the port to that adapter's `name`.

## 2. Publishing a plugin as a Python package

A package can ship plugin classes to anyone who installs it. Declare the entry points in your package's `pyproject.toml`:

```toml
[project]
name = "interop-plexos-adapter"
version = "0.1.0"

[project.entry-points."interop.sources"]
plexos_xml = "interop_plexos_adapter:PlexosXmlSource"

[project.entry-points."interop.steps"]
plexos_to_sienna = "interop_plexos_adapter:PlexosToSiennaStep"

[project.entry-points."interop.validators"]
plexos_capacity_check = "interop_plexos_adapter:PlexosCapacityValidator"

[project.entry-points."interop.sinks"]
sienna_json = "interop_plexos_adapter:SiennaJsonSink"
```

Each entry's right-hand side is `<module>:<attr>`, where the attribute is the plugin class. The class itself looks exactly like the project-local examples above (inherit the Protocol, declare `name` and `params_schema`).

A user installs the package and uses the plugins immediately:

```bash
uv add interop-plexos-adapter
# or: pip install interop-plexos-adapter
```

```yaml
source:
  name: plexos_xml
  params:
    path: inputs/plexos.xml
steps:
  - name: plexos_to_sienna
sinks:
  - name: sienna_json
    params:
      path: outputs/sienna.json
```

No edits to interop's source tree, no files dropped into the user's `plugins/`. Entry-point discovery uses Python's standard `importlib.metadata`.

## 3. Contributing a plugin upstream

Built-in plugins live in:

- `interop/plugins/sources/<name>.py`
- `interop/plugins/steps/<name>.py`
- `interop/plugins/validators/<name>.py`
- `interop/plugins/sinks/<name>.py`
- `interop/adapters/outbound/<name>.py`

The class structure is identical to the project-local examples above. Open a PR adding the file. The contracts under `[tool.importlinter]` and the plugin-contract lints (see below) will run in CI.

## 4. Testing your plugins with `interop-testing`

`interop-testing` is a separate, optional package (`libs/interop-testing/`) publishing
the harness this repo tests itself with, so a project that ships its own plugins can
write BDD scenarios against them without copying anything:

```toml
[dependency-groups]
dev = ["interop", "interop-testing"]

[tool.uv.sources]
interop = { git = "https://github.com/transition-zero/tz-oss-interop", rev = "<sha>" }
interop-testing = { git = "https://github.com/transition-zero/tz-oss-interop", subdirectory = "libs/interop-testing", rev = "<sha>" }
```

Declare **both**, from the same revision. `interop-testing` requires `interop`, but the
name `interop` on PyPI belongs to an unrelated project (Illumina's InterOp), so a
consumer that names only `interop-testing` resolves that dependency to the wrong
package and fails at import with `No module named 'interop.adapters'`. Naming `interop`
directly is what makes the source above apply to it. Pinning both to one revision also
keeps them in lockstep, which matters because the assertion vocabulary describes
interop's output formats.

Put them in a dev group: `interop-testing` depends on `interop`, never the reverse, so
it should never become a runtime dependency. It pulls in `pypsa`, `pandas`, `pytest`
and `pytest-bdd`. Three things come with it.

**Fixture builders** assemble a source document component by component and serialise
it once, so a scenario's input is readable Gherkin rather than a binary fixture
checked into the repo:

| Builder | Writes |
| --- | --- |
| `PyPSANetworkBuilder` | a `pypsa.Network` as netCDF |
| `SiennaSystemBuilder` | a SiennaSchemas system, its HDF5 time-series companion and its kind-keyed `extensions.json` sidecar |
| `SiennaResultsBuilder` | a PowerSimulations.jl solve output (wide CSVs plus `optimizer_stats.csv`) |
| `PlexosModelBuilder` | a PLEXOS `<MasterDataSet>` XML |

**Project scaffolding** — `write_project_plugin`, `write_project_plugin_in_subdir`,
`write_pipeline` and `write_adapters_config` write into the current working
directory, which is where plugin and pipeline discovery looks.

**`interop_testing.run_pipeline`** runs one pipeline in-process through the headless
CLI and returns its exit code. Nothing is raised on failure; a bad pipeline or a
failing translate comes back as a non-zero exit code with the reason logged, exactly
what the command-line caller sees.

```python
from interop_testing import run_pipeline

exit_code = run_pipeline(
    "my-pipeline",
    overrides=["source.path=inputs/network.nc", "sink[0].output_path=outputs/out.json"],
)
```

### The step vocabulary

Nothing registers itself on install: putting `interop_testing` on the path is not
enough, because each step is a pytest fixture on its defining module and pytest only
looks for those in registered plugins. Importing the module from a conftest does not
do it either. Declare it as a plugin instead:

```python
# tests/conftest.py
pytest_plugins = ["interop_testing.steps"]
```

That has to be the conftest beside your `testpaths` (or at the repo root) — pytest
fails collection with `Defining 'pytest_plugins' in a non-top-level conftest is no
longer supported` for one deeper in the tree. `-p interop_testing.steps` in `addopts`
is the equivalent for a project that would rather not have a root conftest.

That registers every module below. They can be listed individually instead if only
part of the vocabulary is wanted — a project that never touches Plexos need not
register its words.

| Module | Provides |
| --- | --- |
| `interop_testing.steps.isolation` | The autouse `isolated_cwd` fixture, plus the working-directory and environment-variable steps. |
| `interop_testing.steps.files` | Assertions on a file's existence, its text, and values inside a JSON document. |
| `interop_testing.steps.pipeline` | `When I run the pipeline …`, `Then the pipeline exit code is …`, and `Then the log contains …`. |
| `interop_testing.steps.reports` | Assertions on the results parquet, its manifest, and the decisions report. |
| `interop_testing.steps.pypsa_network` | Given: build and save a network. Then: assert on a written one. |
| `interop_testing.steps.sienna_system` | Given: build and save a system. Then: assert on the system JSON, its HDF5 companion and its extensions sidecar. |
| `interop_testing.steps.sienna_results` | Given: build a solve-results directory. |
| `interop_testing.steps.plexos_model` | Given: build and save a PLEXOS model. |
| `interop_testing.steps.power_simulations` | Then: assert on an emitted PowerSimulations.jl system and its H5 sidecar. |

A framework has Given steps only if a pipeline can read it, and Then steps only if a
pipeline can write it — hence no Then steps for Plexos, and no Given steps for
PowerSimulations.

The decisions report records what each step did to each field, so the assertions in
`steps.reports` are how a scenario shows a translation lost nothing on the way
through.

`isolated_cwd` is autouse: loading `interop_testing.steps.isolation` runs every test
in an empty directory with a baseline `adapters.yaml`, so scenarios write plugins,
pipelines and outputs without touching the working tree. It is a separate module so a
project that manages its own working directory can take the rest of the vocabulary
without it.

Behind each step module sits a plain-Python one under `interop_testing.builders`
(`pypsa_networks`, `sienna_systems`, `sienna_documents`, `sienna_results`,
`plexos_models`), holding that framework's builder and the readers its assertions use
— `read_network`, `find_sienna_component`, `sienna_time_series_uuid`, and so on. A
project needing a check the vocabulary does not cover writes its own `@then` against
those readers rather than parsing the artefact afresh. The PowerSimulations readers
are the exception: nothing builds a PS.jl system as input, so they sit alongside their
assertions in `interop_testing.steps.power_simulations`.

A scenario then reads end-to-end, against a project's own plugins:

```gherkin
Scenario: a two-bus hourly network runs through our pipeline
  Given a PyPSA network
  And the network has 24 snapshots at 60 minute intervals
  And the network contains bus "north" carrier "AC" v_nom 380.0
  And the network contains bus "south" carrier "AC" v_nom 380.0
  And the network contains load "demand" on "south" with static p_set 100.0
  And the network is saved as "inputs/network.nc"
  When I run the pipeline "my-pipeline" with overrides "source.path=inputs/network.nc"
  Then the pipeline exit code is 0
  And the file "outputs/out.json" parses as valid JSON
```

Steps the project needs beyond this vocabulary — writing its own pipeline YAML,
asserting on its own output format — go in its `step_defs`, calling the scaffolding
helpers directly. `tests/features/testing_harness.feature` in this repo is a worked
example that uses nothing but the published surface.

## Adapters config

`adapters.yaml` at the project root binds outbound ports to adapter names and configures the bound adapters. The file is read by `interop.core.adapters_config.load_adapters_config` and validated against `AdaptersConfig` (Pydantic). Unknown top-level keys are rejected.

| Key | Shape | Purpose |
| --- | --- | --- |
| `bindings` | `dict[str, str]` | Bind a key to a single adapter `name`. |
| `multi_bindings` | `dict[str, list[str]]` | Bind a key to a list of adapter names; the DI layer fans calls out to each. Only `reporter` is supported today. |
| `adapters` | `dict[str, dict]` | Per-adapter config, keyed by adapter `name`. Each value is validated against the adapter's `config_schema`. |
| `observability.log_level` | `str` | Root log level. Default `INFO`. |

A binding key not present in either `bindings` or `multi_bindings` falls back to its built-in default. A single-value entry under `bindings` and a list entry under `multi_bindings` for the same key are mutually exclusive; `multi_bindings` wins.

### Built-in binding keys

| Key | Port | Shipped adapters | Default |
| --- | --- | --- | --- |
| `filesystem` | `FilesystemPort` | `local_filesystem` | `local_filesystem` |
| `reporter` | `ReportingPort` | `markdown_report`, `csv_report`, `noop_report` | `markdown_report` |

Custom outbound adapters under `plugins/adapters/` (see section 1) register their `name` against the port they implement and become valid values for the matching binding key.

### Per-adapter config

Each adapter declares a `config_schema` class attribute pointing at a Pydantic model. Shipped adapter configs:

| Adapter | Field | Type | Default |
| --- | --- | --- | --- |
| `local_filesystem` | `root` | `Path` or `None` | `None` (paths used as-is) |
| `markdown_report` | `output_path` | `Path` | `decisions.md` |
| `csv_report` | `output_path` | `Path` | `decisions.csv` |

`noop_report` takes no config.

### Example: write both markdown and csv decisions reports

To produce `outputs/decisions.md` and `outputs/decisions.csv` on every translate run:

```yaml
multi_bindings:
  reporter: [markdown_report, csv_report]

adapters:
  markdown_report:
    output_path: outputs/decisions.md
  csv_report:
    output_path: outputs/decisions.csv
```

## Import-boundary contracts

`uv run lint-imports` enforces the hexagonal layering. The contracts (in `pyproject.toml` under `[tool.importlinter]`):

| Contract | What it prevents |
| --- | --- |
| Outbound adapters are independent | A future S3 adapter cannot reach into the local filesystem adapter. |
| Core does not depend on adapters, plugins, DI, or main | The domain logic stays portable. |
| Ports do not depend on adapters, core, DI, or main | Port Protocols are pure interface definitions. |
| Inbound adapters do not import outbound adapters directly | Adapters interact through ports, not concrete implementations. |
| Plugins depend only on core and ports | A plugin must not reach for DI internals or adapters. |
| Steps do not read or write the filesystem | Side effects live in sources and sinks only. |
| The plugin lints depend on nothing else in interop | The published checks stay installable and runnable on a base install. |

If a contract fails, the error message names the offending import path. The fix is almost always "move the shared code into core (a helper) or into a port / use case (a Protocol)".

### Contracts for a project's own layering

A project can enforce its own layering the same way. `import-linter` is a dev dependency configured entirely in `pyproject.toml`, so there is no interop API to call: write contracts against your own package. Three transfer to any project that embeds interop — plugins are leaves, steps stay side-effect-free, and nothing production-side reaches for the test harness.

```toml
[dependency-groups]
dev = ["import-linter>=2.13"]

[tool.importlinter]
root_packages = ["my_project"]

[[tool.importlinter.contracts]]
# Plugins are leaves: a step must not reach sideways into a sink, and none of
# them may reach into wiring. Shared logic moves down into my_project.domain.
name = "Plugins depend only on the domain"
type = "forbidden"
source_modules = ["my_project.plugins"]
forbidden_modules = ["my_project.container", "my_project.cli"]

[[tool.importlinter.contracts]]
name = "Steps do not read or write the filesystem"
type = "forbidden"
source_modules = ["my_project.plugins.steps"]
forbidden_modules = [
    "my_project.plugins.sources",
    "my_project.plugins.sinks",
    "interop.ports.outbound.filesystem",
]

[[tool.importlinter.contracts]]
name = "Nothing depends on the test harness"
type = "forbidden"
source_modules = ["my_project"]
forbidden_modules = ["interop_testing"]
```

Run it with `uv run lint-imports`. The remaining contracts in the table above describe the `core` / `ports` / `adapters` / `di` split of a hexagonal application; copy those only if the project is laid out the same way.

## Plugin-contract lints

Two checks ship with interop as console scripts. They are pure-stdlib `ast` walks over a directory tree — they import nothing, execute nothing, and need no dependency beyond `interop` itself — so a project gets both from a base install and points them at its own `plugins/`:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: plugin-inheritance
        name: plugin classes inherit their Protocol
        entry: uv run interop-lint-plugin-inheritance
        language: system
        pass_filenames: false
        types: [python]

      - id: plugin-filesystem
        name: plugins reach the filesystem only through FilesystemPort
        entry: uv run interop-lint-plugin-filesystem
        language: system
        pass_filenames: false
        types: [python]
```

Both take the directories to scan as positional arguments and default to `plugins`, the layout `interop init` writes and discovery reads, so the hooks above need no arguments. Each argument is a directory holding the *category* subdirectories (`sources`, `steps`, `validators`, `sinks`, and for the inheritance check `adapters`); a category that isn't there is skipped, and each is walked recursively so per-framework subpackages are covered. Pass more than one root to lint several trees in a single run, as this repo does for `plugins` and `interop/plugins`. Both print one line per violation to stderr and exit 1.

**`interop-lint-plugin-inheritance`** catches `class MySource: name = "foo"; def load(...)` declarations that *look* like a Source but don't inherit `Source` from `interop.core.pipeline`. Structural typing in mypy lets that pass; the discovery layer rejects it at registration time. A class reaches its Protocol through a shared base declared elsewhere in the same category, the way `discover()` resolves an `__mro__`, but only through bare-name bases — `class Foo(pipeline.Source)` is rejected, because a static AST cannot tell that attribute apart from an unrelated class of the same name. Under `adapters` the required base is instead the port each class names in its `port = SomePort` declaration. An adapter category that doesn't sit under a plugin root — interop's own live at `interop/adapters/outbound/` — is named with `--adapters-dir`, which is repeatable.

**`interop-lint-plugin-filesystem`** enforces `FilesystemPort`. It is a per-function taint analysis: a `params` field whose name contains `path`, and everything derived from it, may only be handed to a method on `self._fs`. Passing it to `open`, `h5py.File`, `Path.mkdir` or a library export call writes the local disk directly, which breaks the moment the port is backed by a root remap or remote storage. f-strings don't propagate taint, so a path may still appear in an error message, and scratch derived from `staging_dir` is exempt in a source because it is process-local by contract. Steps and validators are held to a stricter rule — no `open`, no `Path(...)`, no `staging_dir` — because they transform in-memory `State` and have nothing to read or write. Outbound adapters are not checked: implementing the port is what they are for.

Both are also importable, for a project that would rather drive them from its own test suite than from pre-commit:

```python
from interop.lints import check_plugin_filesystem, check_plugin_inheritance

assert check_plugin_inheritance([Path("plugins")]) == []
assert check_plugin_filesystem([Path("plugins")]) == []
```

In this repo the hooks are installed by `uv run pre-commit install` and run on every
commit.
