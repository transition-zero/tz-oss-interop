# Developer Tutorial

Interop is built for *extending* a translation. A pipeline is
a list of steps, and a step is a small plugin you drop under `plugins/steps/` and
reference by name. This works in a freshly scaffolded project, so you do not need
to change core interop code in order to write or edit your own pipelines.

This tutorial builds on the [Setting up a project](user-tutorial.md#setting-up-a-project) section of the [user tutorial](user-tutorial.md): it assumes you have
installed interop and scaffolded the `pypsa` example project. It extends that same
example with a new pipeline (`pipelines/pypsa-to-sienna-normalised.yaml`), a new
custom step (`plugins/steps/normalise_carrier.py`), and a deliberately messy
network (`inputs/pypsa_inconsistent_carrier_names.nc`).

## The problem: inconsistent PyPSA carrier names

As you may have noticed from the user tutorial, `user_mappings.yaml` is keyed on exact carrier strings,
and the carrier mapping leaves out any generator whose carrier it does not recognise.
Real networks are not always tidy: the same fuel shows up as `CCGT`, `gas_cc`, or `ccgt `,
and PyPSA treats `carrier` as optional free-text metadata, so nothing upstream guarantees consistency. The
shipped `pypsa_inconsistent_carrier_names.nc` has three generators carrying `gas_cc`,
`OCGT ` (trailing space), and `Coal`. Run the *base* pipeline against it (pick
`translate`, pipeline `pypsa-to-sienna`, and point `source.path` at
`inputs/pypsa_inconsistent_carrier_names.nc`) and it writes a system with no generators
in it, and a `decisions.md` naming all three.

## The step

A step is a class implementing `TranslationStep`: it receives the in-memory
`State`, transforms it, and returns it. We have a new `normalise_carrier` step that
resolves the aformentioned problem by staging the PyPSA
generators, rewriting their `carrier` column to canonical forms, and recording each
rewrite so it lands in the decisions report:

```python
class NormaliseCarrier(TranslationStep):
    name: ClassVar[str] = "normalise_carrier"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def run(self, state: State, params: BaseModel | None) -> State:
        generators = state.source_topology["generators"].collect()
        rewrite = {c: _normalise(c) for c in generators["carrier"].unique().to_list()}
        # ... append a VALUE_DERIVED event for each changed carrier ...
        state.source_topology["generators"] = generators.with_columns(
            pl.col("carrier").replace(rewrite).alias("carrier")
        ).lazy()
        return state
```

`_normalise` applies *rules*, not a fixed list: trim whitespace, resolve a small
alias map (`gas_cc` becomes `CCGT`), then match a canonical carrier
case-insensitively (`ocgt` becomes `OCGT`, `Coal` becomes `coal`). The `recorder`
is injected by name from interop's container, the same way the built-in steps get
theirs. Note what the step does *not* do: it never touches the filesystem (steps
only transform `State`; sources and sinks own I/O), and it leaves carriers it does
not recognise untouched so the mapping still drops and reports genuinely unknown ones. See
`plugins/steps/normalise_carrier.py` for the full step.

## The pipeline

`pypsa-to-sienna-normalised.yaml` is the same as the original base pipeline with one line added:
`normalise_carrier` runs first, ahead of the standard mapping.

```yaml
steps:
  - name: normalise_carrier
  - name: pypsa_to_sienna_map_components
  - name: pypsa_to_sienna_relate_components
```

Pick `translate` and the `pypsa-to-sienna-normalised` pipeline, and the same messy
network now succeeds: the three generators translate to `ThermalStandard`s, and
`outputs/decisions.md` shows the carrier rewrites as audited `VALUE_DERIVED`
events, right beside the decisions the built-in mappings made.

## Another problem: different input and output formats

Steps are not the only pluggable piece. A pipeline also has a *source* (reads
external data from a specific format into the `State`)
and a *sink* (writes the result out in a specific format). So far we
have read PyPSA from netCDF and written Sienna as JSON, but those are just the
default source and sink: your input might arrive as PyPSA's CSV-folder export
rather than a `.nc`, or your downstream tooling might want CSV rather than JSON.
Both are solved the same way as the step was: write a plugin and reference it by name in a
pipeline.

### Writing a source

A source implements `StagedSource.load_into_state`: it reads external data and
returns a `State` whose `source_topology` (one frame per component) and
`source_time_series` (long `snapshot/component/value` frames) are what the rest of
the pipeline expects. Make those match the netCDF source's output lazy frames and every step
and sink downstream can remain unchanged. A source can carry more columns than that baseline
when its own data needs them: the PLEXOS source adds a `sample` column so a Monte Carlo
study's replications stay distinct, null for every value that is not replicated.

Now to handle the case of the PyPSA CSV representation, which consist of one CSV per component (with a `name` index
column) plus a wide CSV per time-varying attribute (rows are snapshots, columns
are components). We need to read each CSV through the filesystem port, reshape the wide
time-series frames to long, and stage every frame to parquet under `staging_dir` (parquet allows us to
later stream the timeseries results rather than loading them in memory,
and use the often more memory-efficient method of predicate pushdown),
exactly as the built-in source does:

```python
class StagePypsaCsv(StagedSource):
    name: ClassVar[str] = "stage_pypsa_csv"
    params_schema: ClassVar[type[BaseModel] | None] = StagePypsaCsvParams

    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def load_into_state(self, params: BaseModel | None, staging_dir: Path) -> State:
        folder = Path(params.path)
        snapshots = self._read_snapshots(folder)

        topology: dict[str, pl.LazyFrame] = {}
        for component in _COMPONENTS:
            frame = self._read_csv(folder / f"{component}.csv")
            if frame is not None:
                topology[component] = self._stage(
                    frame, staging_dir / "topology" / f"{component}.parquet"
                )

        time_series: dict[tuple[str, str], pl.LazyFrame] = {}
        for component, attribute in _TIME_SERIES:
            reshaped = self._read_time_series(folder, component, attribute, snapshots)
            if reshaped is not None:
                time_series[(component, attribute)] = self._stage(
                    reshaped, staging_dir / "time_series" / component / f"{attribute}.parquet"
                )

        return State(
            staging_dir=staging_dir, source_topology=topology, source_time_series=time_series
        )

    def _stage(self, frame: pl.DataFrame, out: Path) -> pl.LazyFrame:
        out.parent.mkdir(parents=True, exist_ok=True)
        frame.write_parquet(out)
        return pl.scan_parquet(out)  # the steps scan this lazily
```

Each component CSV is read as a stream through `self._fs` (sources own I/O, and
must go through the filesystem port); the wide time-series frame is reshaped to
long with a single `unpivot`:

```python
frame.select(component_columns)
    .with_columns(snapshots)                       # attach the datetime snapshots
    .unpivot(index="snapshot", variable_name="component", value_name="value")
```

Staging to parquet (rather than returning the frames read into memory) is what the
built-in source does too: the steps scan the parquet lazily, so a large time
series is never held in memory in full.

The pipeline is the base PyPSA-to-Sienna pipeline with only the source swapped:

```yaml
# pipelines/pypsa-csv-to-sienna.yaml
source_framework: pypsa
destination_framework: sienna
source:
  name: stage_pypsa_csv
  params:
    path: inputs/pypsa_network_csv
steps:
  - name: pypsa_to_sienna_map_components
  - name: pypsa_to_sienna_relate_components
sinks:
  - name: emit_sienna_files
    params:
      output_system_json_file_path: outputs/system.json
```

The steps and JSON sink are unchanged, and the Sienna system comes out identical.
See `plugins/sources/stage_pypsa_csv.py` for the full source.

Try it: launch `interop` and pick `translate`:

```
interop            # pick: translate
```

Answer the prompts (each is prefilled with the value shown, so you can press
Enter through them):

1. **Source framework?** `pypsa`
2. **Destination framework?** `sienna`
3. **Pipeline?** `pypsa-csv-to-sienna`
4. **source.path?** `inputs/pypsa_network_csv`
5. **sink[0].output_system_json_file_path?** `outputs/system.json`
6. **sink[0].output_h5_file_path?** `outputs/system_time_series_storage.h5`
7. **sink[0].output_extensions_file_path?** `outputs/extensions.json`
8. **sink[0].indent?** `2`
9. **User mappings file?** `inputs/user_mappings.yaml`

It writes the same `outputs/system.json` the netCDF run produced in the
[user tutorial](user-tutorial.md): the input format changed, the result did not.

### Writing a sink

A sink implements `Sink.write`: it reads the finished `destination_tables` (one
frame per Sienna component type) and writes them out however you need. Whereas
the original sink for Sienna wrote JSON, we now want to write CSV (largely
for the purposes of this tutorial). The catch
for CSV is that those frames hold nested struct columns (`operation_cost`,
`active_power_limits`) that do not fit a flat file, so flatten them first:

```python
class EmitSiennaCsv(Sink):
    name: ClassVar[str] = "emit_sienna_csv"
    params_schema: ClassVar[type[BaseModel] | None] = EmitSiennaCsvParams

    def write(self, state: State, params: BaseModel | None) -> None:
        for component, table in state.destination_tables.items():
            if component in _AUX_TABLES or table.height == 0:
                continue
            csv = _flatten_structs(table).write_csv()
            self._fs.write_bytes(params.output_dir / f"{component}.csv", csv.encode("utf-8"))
```

`_flatten_structs` unnests struct columns repeatedly until the frame is flat,
naming each leaf by its dotted path (`active_power_limits.max`):

```python
def _flatten_structs(table: pl.DataFrame) -> pl.DataFrame:
    while True:
        structs = [name for name, dtype in table.schema.items() if isinstance(dtype, pl.Struct)]
        if not structs:
            return table
        for name in structs:
            fields = table.schema[name].fields
            table = table.with_columns(
                pl.col(name).struct.field(f.name).alias(f"{name}.{f.name}") for f in fields
            ).drop(name)
```

The pipeline is the base pipeline with only the sink swapped:

```yaml
# pipelines/pypsa-to-sienna-csv.yaml
source_framework: pypsa
destination_framework: sienna
source:
  name: stage_pypsa_network_file
  params:
    path: inputs/pypsa_network.nc
steps:
  - name: pypsa_to_sienna_map_components
  - name: pypsa_to_sienna_relate_components
sinks:
  - name: emit_sienna_csv
    params:
      output_dir: outputs/sienna_csv
```

It writes `outputs/sienna_csv/<Type>.csv`, one file per component type.
Time-series values are not in `destination_tables` (the JSON sink writes them to
an HDF5 companion), so these CSVs hold the static components only. See
`plugins/sinks/emit_sienna_csv.py`.

Try it: launch `interop` and pick `translate`:

```
interop            # pick: translate
```

Answer the prompts (each is prefilled with the value shown, so you can press
Enter through them):

1. **Source framework?** `pypsa`
2. **Destination framework?** `sienna`
3. **Pipeline?** `pypsa-to-sienna-csv`
4. **source.path?** `inputs/pypsa_network.nc`
5. **sink[0].output_dir?** `outputs/sienna_csv`
6. **User mappings file?** `inputs/user_mappings.yaml`

Instead of a single `system.json`, look under `outputs/sienna_csv/`: there is one
CSV per component type. Open `outputs/sienna_csv/ThermalStandard.csv` and you will
see the struct fields flattened into dotted columns, for example
`active_power_limits.max`.

## Why this is the shape

Across all three pieces (a step, a source, and a sink) we extended interop without
editing its core: a `.py` under `plugins/<category>/`, a pipeline YAML that
references it by name, and, for the step, every decision recorded in the same
audit trail as the built-in mappings.
