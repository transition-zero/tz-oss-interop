# User Tutorial

This tutorial walks through *using* interop to translate energy-system models:
turning a PyPSA network into a Sienna system, solving it with
PowerSimulations.jl, and comparing the two. If instead you want to *extend*
interop with your own translation logic (custom pipeline steps), see the
[developer tutorial](developer-tutorial.md).

## Installation

interop is a Python package managed with [`uv`](https://docs.astral.sh/uv/). If
you do not already have uv, follow its [installation
instructions](https://docs.astral.sh/uv/getting-started/installation/). Then
clone the repository and sync its environment:

```bash
git clone https://github.com/transition-zero/tz-oss-interop.git
cd tz-oss-interop
uv sync
```

`uv sync` creates a `.venv/` folder with everything interop needs and makes the
`interop` command available. From inside the interop project root, launch the
interactive shell with:

```bash
uv run interop
```

To call the bare `interop` command from any directory, install interop as a
standalone tool (run from the interop project root):

```bash
uv tool install .
```

This installs interop on its own, so the `interop` command works from any
directory.

### Setting up a project

interop works inside a *project directory*: a single folder that holds everything
for one piece of work. It has a place for the translations you can run
(`pipelines/`), your input data (`inputs/`), the results (`outputs/`), any custom
pieces you write yourself (`plugins/`), and a couple of configuration files
(`adapters.yaml`, `user_mappings.yaml`). Keeping each piece of work in its own
project directory keeps your models, settings, and results together, and separate
from interop's own code.

It is best not to scaffold an empty project inside the interop repository itself.
Create it outside, for example in the parent directory (alongside
the interop repo). That keeps your work clearly separate from the tool's source.

Taking that approach, the directory one level up will look like this:

```
workspace/
  interop/                  # the interop project root you cloned
  my-interop-project/       # your scaffolded project
```

Hence if you are in the root of the interop directory, then first execute:

```bash
cd ..
```

Now, scaffold a project with `init`: launch the shell, pick `init`, name a target
directory (we will assume `my-interop-project`), and choose `pypsa` to scaffold
the worked example used in the next section (or choose `none` for an empty
skeleton project):

```bash
interop             # pick: init, target = my-interop-project, example = pypsa
```

This creates:

```
my-interop-project/
  pipelines/
    pypsa-to-sienna.yaml             # translate a PyPSA .nc into a Sienna system
    pypsa-to-sienna-normalised.yaml  # same, with a carrier-normalisation step
    pypsa-to-sienna-csv.yaml         # emit the Sienna system as CSV
    pypsa-csv-to-sienna.yaml         # read a PyPSA CSV folder as the source
  adapters.yaml                      # output and reporting settings
  plugins/                           # custom pipeline pieces you add yourself
    sources/stage_pypsa_csv.py
    steps/normalise_carrier.py
    sinks/emit_sienna_csv.py
  inputs/
    pypsa_network.nc                 # the example network this tutorial translates
    pypsa_network_solved.nc          # PyPSA's own solve, read by `compare` in step 4
    user_mappings.yaml               # carrier mapping used by PyPSA translations
    plexos_user_mappings.yaml        # the same mapping in PLEXOS words, for plexos-to-sienna
  outputs/                           # results written here
  README.md
```

Choosing `none` instead gives the same layout without the example networks,
pypsa pipelines, or plugins: just a single no-op pipeline `pipelines/example.yaml`, the
empty `inputs/` and `outputs/` directories, and `user_mappings.yaml`.

Change directory to your project:

```bash
cd my-interop-project
```

Run `interop` from inside the project from now on; the built-in pipelines stay
available alongside any you add under `pipelines/`:

## Translating Models

This walkthrough runs a full translation on a small example network: translate a
PyPSA network into a Sienna system, solve that system with PowerSimulations.jl,
and compare the Sienna dispatch against PyPSA's own solve of the same network.
`interop init` ships the network and configuration as its built-in `pypsa`
example, so there is nothing to assemble by hand.

### 1. Translate (PyPSA to Sienna)

```bash
interop            # pick: translate
```

Answer the prompts:

- **Source framework?** `pypsa`
- **Destination framework?** `sienna`
- **Pipeline?** `pypsa-to-sienna`
- **source.path?** `inputs/pypsa_network.nc`
- **sink[0].output_system_json_file_path?** `outputs/system.json`
- **sink[0].output_h5_file_path?**  `outputs/system_time_series_storage.h5`
- **sink[0].output_extensions_file_path?** `outputs/extensions.json`
- **sink[0].indent?** `2`
- **User mappings file?** `inputs/user_mappings.yaml`

The **user mappings file** turns PyPSA's free-text `carrier` labels into
concrete Sienna component types. A PyPSA generator only declares that it is, say,
a `CCGT`; Sienna needs to know that means a `ThermalStandard` burning
`NATURAL_GAS` on a combined-cycle (`CC`) prime mover. `inputs/user_mappings.yaml`
spells that out, one entry per carrier:

```yaml
carriers:
  - pypsa_carrier: CCGT          # the carrier on this tutorial's generator
    sienna_component_type: ThermalStandard
    sienna_fuel_type: NATURAL_GAS
    sienna_prime_mover_type: CC
  - pypsa_carrier: solar         # renewables map to their own type, no fuel
    sienna_component_type: RenewableDispatch
    sienna_prime_mover_type: PVe
```

Thermal carriers map to `ThermalStandard` and carry a `sienna_fuel_type`;
renewable, hydro, and storage carriers map to their own Sienna types
(`RenewableDispatch`, `HydroDispatch`, `EnergyReservoirStorage`, ...) and omit
the fuel type. Every carrier in the network needs an entry: a component whose
carrier has no entry is left out rather than guessed at, and `decisions.md` names
it. The example ships mappings for the common PyPSA carriers, including the
`CCGT` this network uses.

On completion interop writes, under `outputs/`:

- `system.json` plus its companions (`system_time_series_storage.h5`,
  `extensions.json`) make up the Sienna system.
- `decisions.md` and `decisions.csv` record every translation decision.
  `compare` reads `decisions.csv` later to line PyPSA components up with their
  Sienna counterparts.

### 2. Prerequisite to Solve a Sienna Model: Translate (Sienna to PowerSimulations)

Step 1 wrote `outputs/system.json` in the standard **SiennaSchemas** format: the
common way to store and exchange a Sienna system as a file. PowerSimulations.jl,
though, does not read that format directly. To actually run a simulation it needs
a richer JSON layout (the one PowerSystems.jl produces), which carries extra
bookkeeping the interchange format leaves out: a format version, an identifier for
each component, and its own way of laying out time series. Hand step 1's
`system.json` straight to `solve` and it stops with an error about a missing
`data_format_version`, because that bookkeeping is not there.

So there is a second translation step, from the SiennaSchemas system to the
PowerSimulations one. Launch `interop` and pick `translate` again:

```
interop            # pick: translate
```

Answer the prompts:

- **Source framework?** `sienna`
- **Destination framework?** `power-simulations`
- **Pipeline?** `sienna-to-power-simulations`
- Using the outputs from the previous PyPSA to Sienna translation as the inputs for this one:
  - **source.system_json_path?** `outputs/system.json`
  - **source.time_series_h5_path?** `outputs/system_time_series_storage.h5`
  - **source.extensions_json_path?** `outputs/extensions.json` (blank if the system has no sidecar)
- **sink[0].system_json_filepath?** `outputs/power_simulations_system.json`
- **sink[0].h5_output_path?** `outputs/power_simulations_system_time_series.h5`
- **sink[0].system_name?** `SiennaSystem`
- **sink[0].base_power?** `100.0`
- **sink[0].frequency?** `50.0`

This reads the three companion files from step 1 and writes
`outputs/power_simulations_system.json` (plus its own `power_simulations_system_time_series.h5`),
the PowerSimulations-ready system that `solve` can load.

### 3. Solve (Sienna via PowerSimulations.jl)

Launch `interop` and pick `solve` (see [`docs/tutorials/solve.md`](solve.md)
for the full reference of this command):

```
interop            # pick: solve
```

***n.b., if you do not already have the pre-requisites to solve a system (e.g., for Sienna the Julia and the Sienna packages)
then you will be prompted whether you want to download them and continue. Choose yes.***

Next we must point the solve command at the PowerSimulations system from step 2, **not** the SiennaSchemas
`system.json` from step 1:

1. **Model type?** `sienna` (`pypsa` also exists, for solving a PyPSA network directly; see [`docs/tutorials/solve.md`](solve.md))
2. **Path to PowerSimulations.jl system JSON?** `outputs/power_simulations_system.json`
3. **Network model?** `copperplate` (options: `dcp`, `ptdf`, `copperplate`)
4. **HiGHS solver algorithm?** `simplex` (options: `simplex`, `ipm`, `pdlp`)
5. **Presolve?** `choose` (options: `on`, `off`, `choose`; `choose` lets HiGHS decide)
6. **Run crossover after IPM?** `choose` (options: `on`, `off`, `choose`; only applies to `ipm`)
7. **Time limit in seconds?** leave blank for no limit
8. **Output directory?** `outputs/solved`

If Julia and the solver packages are not installed yet, a notice and a
**Download and continue?** confirmation appear right after the model type
prompt; accept it to let interop set them up.

Prompts 4 to 7 are HiGHS tuning knobs; the values above are safe defaults for
this small problem, and `choose` hands the decision to HiGHS. Only the network
model matters for whether the model builds and runs.

Pick `copperplate` here because this example is a **single-bus** network: one
bus, no lines or links, and (since PyPSA leaves the bus as `PQ`) no reference
bus. `copperplate` (`CopperPlatePowerModel`) is a single nodal energy balance
that ignores line flows, so it needs neither branches nor a slack bus. The
`dcp` and `ptdf` models are DC power-flow formulations with voltage-angle
variables and KVL constraints; on a network with no branches and no reference
bus there is nothing for them to build, so `solve` fails to build the model.
Reach for `dcp` or `ptdf` only on multi-bus networks that carry transmission and
a slack bus.

The first solve downloads Julia and the solver packages and compiles them, which
needs an internet connection; later runs reuse the installed packages and start
much faster. On success interop prints the run status and objective
value, and writes results under `outputs/solved/`, including the
wide-format CSVs in `outputs/solved/results_wide/`, which `compare` reads.

### 4. Compare (Sienna solve against PyPSA solve)

Launch `interop` and pick `compare`:

```
interop            # pick: compare
```

Answer the prompts:

- **Path to PyPSA network (.nc)?** `inputs/pypsa_network_solved.nc`
- **Path to PowerSimulations.jl output directory?** `outputs/solved`
- **Path to decisions CSV?** `outputs/decisions.csv`
- **Output path for summary report?** `outputs/comparison_summary.md`

`compare` aligns the two solves by snapshot and component, then writes a Markdown
report (`outputs/comparison_summary.md`) covering the objective values, snapshot
alignment, component coverage, per-carrier energy totals, and the largest
dispatch differences. See [`docs/developer_documentation/comparison.md`](../developer_documentation/comparison.md) for how to read
each section.

## Extending interop

The built-in pipelines cover the common PyPSA to Sienna case, but real networks
have quirks: non-standard carrier names, fields the standard mapping does not
handle, component types you want translated differently. When the shipped
pipelines do not fit your data, you can write your own pipeline steps and compose
them with other built-in steps to create new pipelines, without changing interop's core. The
[developer tutorial](developer-tutorial.md) walks through exactly that, extending
this same example project with a custom step.
