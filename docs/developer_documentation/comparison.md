# Comparison workflow: PyPSA → Sienna → PowerSimulations → compare

This guide walks through the full end-to-end workflow for comparing PyPSA dispatch results against PowerSimulations.jl dispatch results using the `compare` command.

## Prerequisites

- Python dependencies installed (`uv sync`)
- A first `solve` run completed, so Julia and PowerSimulations.jl are installed (see [solve.md](../tutorials/solve.md))
- An interop project directory with an `adapters.yaml` (created by `interop init` or manually)

## Overview

1. Build a PyPSA network and save it as a `.nc` file
2. Solve the network and save the solved results to a second `.nc` file
3. Configure the reporter to emit a `decisions.csv` alongside translation
4. Translate: **pypsa → sienna** (SiennaSchemas format)
5. Translate: **sienna → power-simulations** (PowerSystems.jl format)
6. Solve with PowerSimulations via the `solve` command
7. Run `compare` to produce a side-by-side Markdown report

The `compare` command reads dispatch values directly from the solved PyPSA `.nc` file and from the wide-format CSVs written by `solve`, then maps components via the `decisions.csv` produced during the first translation step.

---

## Step 1: Build the PyPSA network

The network must include at least one **time-varying component** (a load or generator with a `p_set` or `p_max_pu` time series). A purely static network produces no `SingleTimeSeries` in the Sienna output and will cause the PowerSimulations solve step to fail — see [Common pitfalls](#common-pitfalls).

```python
import pandas as pd
import pypsa

n = pypsa.Network()
snapshots = pd.date_range("2020-01-01", periods=2, freq=pd.Timedelta(minutes=60))
n.set_snapshots(list(snapshots))

# 1 AC bus at 380 kV
n.add("Bus", "bus1", v_nom=380.0, carrier="AC", location="region1")

# 1 gas generator (becomes ThermalStandard after translation)
n.add(
    "Generator",
    "gen1",
    bus="bus1",
    carrier="gas",
    p_nom=100.0,
    p_min_pu=0.0,
    p_max_pu=1.0,
    marginal_cost=10.0,
)

# 1 load with a time-varying profile (required — a scalar p_set won't work)
n.add(
    "Load",
    "load1",
    bus="bus1",
    p_set=pd.Series([50.0, 50.0], index=n.snapshots),
)

n.export_to_netcdf("inputs/network.nc")
```

---

## Step 2: Solve the PyPSA network

The `compare` command reads solved dispatch from the PyPSA `.nc` file (`generators_t.p`, `loads_t.p_set`), so the network must be solved and the results saved before translation.

```python
import pypsa

n = pypsa.Network("inputs/network.nc")
n.optimize()
n.export_to_netcdf("outputs/network_solved.nc")
```

---

## Step 3: Configure the reporter to write decisions.csv

The `compare` command needs a `decisions.csv` to map PyPSA component names to their Sienna counterparts. The default reporter writes `decisions.md`; enable the CSV reporter in `adapters.yaml`:

```yaml
# adapters.yaml
multi_bindings:
  reporter: [markdown_report, csv_report]

adapters:
  csv_report:
    output_path: outputs/decisions.csv
```

Or bind `csv_report` exclusively if the Markdown report isn't needed:

```yaml
bindings:
  reporter: csv_report

adapters:
  csv_report:
    output_path: outputs/decisions.csv
```

---

## Step 4: Translate PyPSA → Sienna

Run `interop`, select **translate**, and provide:

- Source framework: **pypsa** / Destination framework: **sienna**
- Pipeline: **pypsa-to-sienna**
- Source input path: `outputs/network_solved.nc`
- Sink output path: `outputs/system.json`

The pipeline writes three companion files alongside `outputs/system.json`:

| File | Contents |
| --- | --- |
| `outputs/system.json` | SiennaSchemas component graph (integer refs, flat objects) |
| `outputs/system_time_series_storage.h5` | HDF5 arrays for each `SingleTimeSeries`, keyed by UUID |
| `outputs/extensions.json` | PyPSA fields with no SiennaSchemas home (e.g. `carrier`), keyed by kind |

The companion filenames are fixed — always `system_time_series_storage.h5` and `extensions.json` regardless of the `output_path` stem. The CSV reporter also writes `outputs/decisions.csv`.

---

## Step 5: Translate Sienna → PowerSimulations

Run `interop`, select **translate**, and provide:

- Source framework: **sienna** / Destination framework: **power-simulations**
- Pipeline: **sienna-to-power-simulations**
- Source: `outputs/system.json`, `outputs/system_time_series_storage.h5`, `outputs/extensions.json`
- Sink output path: `outputs/psi_system.json`

The pipeline writes two files:

| File | Contents |
| --- | --- |
| `outputs/psi_system.json` | PowerSystems.jl `to_json` envelope (UUID refs, `__metadata__`, nested cost structs) |
| `outputs/psi_system_time_series_storage.h5` | HDF5 data + embedded SQLite time-series association sidecar |

> The sidecar filename is derived automatically from the JSON output stem (`{stem}_time_series_storage.h5`). Do not rename or move the `.h5` file independently — PowerSystems.jl looks it up by stem at load time.

---

## Step 6: Solve with PowerSimulations

Run `interop`, select **solve**, and provide:

- **Model type?** → `sienna` (`pypsa` also exists, for solving a PyPSA network directly; see [solve.md](../tutorials/solve.md))
- **Path to PowerSimulations.jl system JSON?** → `outputs/psi_system.json`
- **Network model?** → see table below
- **HiGHS solver algorithm? / Presolve? / Run crossover after IPM? / Time limit?** → accept the defaults (see [solve.md](../tutorials/solve.md))
- **Output directory?** → `outputs/sienna_results`

Results are written to `outputs/sienna_results/results_wide/` as wide-format CSVs.

### Choosing the network model

| Model | When to use |
| --- | --- |
| `copperplate` | No transmission lines — all buses share a single power balance |
| `dcp` | Network has transmission lines **and** at least one bus with `control="Slack"` (i.e. bustype REF) |
| `ptdf` | Network has transmission lines; faster than DCP on large networks |

For a single-bus network like the example above, always use `copperplate`. Using `dcp` without a REF bus causes `build!` to fail — see [Common pitfalls](#common-pitfalls).

---

## Step 7: Compare results

Run `interop`, select **compare**, and provide:

- **Path to PyPSA network (.nc)?** → `outputs/network_solved.nc`
- **Path to Sienna output directory?** → `outputs/sienna_results`
- **Path to decisions CSV?** → `outputs/decisions.csv`
- **Output path for summary report?** → `outputs/comparison_summary.md`

The command writes a Markdown report with six sections:

1. Objective comparison (PyPSA `network__objective` vs Sienna `optimizer_stats.objective_value`)
2. Snapshot alignment check
3. Coverage table — which PyPSA components matched Sienna components
4. Per-component-type diff statistics (MAE, RMSE, max |diff|, energy totals)
5. Per-carrier thermal energy breakdown
6. Top 20 worst-offending (snapshot, component) pairs by |diff|

A **green** status line means the load passthrough check passed: load dispatch values match between PyPSA and Sienna within 1 × 10⁻³ MW, confirming the load time series was translated without sign error or scaling. **Yellow** means a mismatch worth investigating.

---

## Common pitfalls

### Purely static network fails at the PowerSimulations solve step

PowerSimulations.jl calls `transform_single_time_series!` before building the optimisation problem. If the translated system contains no `SingleTimeSeries`, this call raises an error. A load or generator with a scalar value (not a time series) produces no `SingleTimeSeries` in the Sienna output. Fix: use a time-varying `p_set` Series on at least one load or generator, as shown in step 1.

### DCP fails with "no reference bus"

`DCPPowerModel` requires at least one bus with `bustype = REF`. A PyPSA bus without `control="Slack"` comes through as `bustype = PQ`. For a single-bus network with no lines, use `copperplate` — it imposes no bus-topology requirements. If you want DCP on a multi-bus network, add `control="Slack"` to the reference bus.

### Wrong paths for companion files in step 4

The pypsa-to-sienna sink writes companion files under fixed names (`system_time_series_storage.h5`, `extensions.json`) in the same directory as `system.json` — the names do not derive from the JSON stem. When providing the source paths for the sienna-to-power-simulations translation, use these fixed names rather than any path derived from the source JSON filename. The extensions path is optional; leave it blank for a system that has no sidecar.

### Sidecar gone missing after renaming

PowerSystems.jl resolves the sidecar path from the JSON stem at load time. If you copy or rename `psi_system.json` without also moving `psi_system_time_series_storage.h5` to the same directory under the matching stem name, `System(path)` will fail. Keep the two files together and use consistent stems.
