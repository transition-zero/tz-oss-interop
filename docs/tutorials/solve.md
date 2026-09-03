# Using the solve command

The `solve` command runs a translated model through an optimisation solver. Two model
types are supported:

- `sienna` loads a PowerSimulations.jl system JSON and runs economic dispatch via
  PowerSimulations.jl with the HiGHS solver.
- `pypsa` loads a PyPSA network (a single `.nc` file or a directory of them) and solves
  it directly with HiGHS, with no Julia dependency.

It is typically used after `translate` to test that a translated model is feasible and
produces a meaningful objective value.

## Prerequisites

The `pypsa` path needs nothing beyond interop's own Python dependencies (PyPSA, linopy,
and HiGHS via `highspy`).

The `sienna` path also needs Julia and PowerSimulations.jl. There is nothing to install
by hand: the first time you run `solve` with model type `sienna`, it downloads Julia
(unless a compatible Julia is already installed), installs the required Julia packages,
and compiles them.

When a download is needed, `solve` says so up front and asks for confirmation before
starting it. This first run requires an internet connection; download and compilation
progress is printed as it runs. Subsequent runs reuse the installed packages, start much
faster, and skip the confirmation entirely.

## Usage

Start the interop shell from your project directory (the folder you scaffolded with
`init`, containing `pipelines/`, `inputs/`, and `outputs/`):

```bash
uv run interop
```

Select **solve** from the menu. The first prompt, **Model type?**, chooses between
`sienna` and `pypsa`; the remaining prompts depend on which you pick.

### Sienna path

1. **Path to PowerSimulations.jl system JSON?** The path to a PowerSimulations-ready JSON file (e.g. `outputs/power_simulations_system.json`). Companion files (`*_time_series_storage.h5`, `*_metadata.json`) must be in the same directory.
2. **Network model?** Choose one of:
   - `dcp` (default): DC power flow with voltage-angle variables and KVL constraints; closest to PyPSA's Kirchhoff formulation.
   - `ptdf`: PTDF approximation of AC flows; faster than DCP on large networks.
   - `copperplate`: single-bus per AC subnetwork; fastest, ignores line flows.
3. **Unit commitment treatment?** Choose one of:
   - `exact` (default): each thermal generator's on/off state is a true binary decision, so the solve is a mixed-integer program. It applies the start-up cost and the minimum up and down times that the translation carries. It stops at a relative gap of 1%.
   - `linearised`: economic dispatch. It has no on/off variable, so it applies neither the start-up cost nor the time limits, and it solves much faster. PowerSimulations has no relaxed unit commitment formulation, so this answer means something different from the same answer on the PyPSA path.
4. **HiGHS solver algorithm?** `simplex` (default), `ipm`, or `pdlp`.
5. **Presolve?** `on`, `off`, or `choose` (default; lets HiGHS decide).
6. **Run crossover after IPM?** `on`, `off`, or `choose` (default); only applies to `ipm`.
7. **Time limit in seconds?** Leave blank for no limit.
8. **Output directory?** Where results will be written. Defaults to `solved/` alongside the input JSON.

If Julia or the solver packages are not installed yet, a notice and a
**Download and continue?** confirmation appear right after the model type prompt;
declining returns to the menu without solving.

Results are written to the chosen output directory (default: `solved/` alongside the input JSON):

- `solved/results/`: standard PSI result CSVs (long format, one file per result type)
- `solved/results_wide/`: wide-format CSVs (one file per variable/dual/parameter/expression, columns are components, rows are timesteps)
- `solved/interop_solve/`: solver log and optimisation container metadata

The command prints the solve status and objective value on completion:

```
[OK]  status=RunStatus.SUCCESSFULLY_FINALIZED  objective=1.23456e+06
```

A non-`SUCCESSFULLY` status is printed in red and indicates the solver did not converge.

For a worked end-to-end example (translate, solve, compare) see the
[user tutorial](user-tutorial.md).

### PyPSA path

1. **Path to PyPSA network?** A single `.nc` file, or a directory; every `.nc` file directly inside it is solved.
2. **Output directory?** Where solved networks are written, one file per input network under its original filename. Input networks are never overwritten.
3. **Start date?** `YYYY-MM-DD`, or blank to start at the network's own first snapshot.
4. **End date?** `YYYY-MM-DD`, or blank to end at the network's own last snapshot.
5. **Unit commitment treatment?** `exact` or `linearised` (see below).
6. **How much of the range does one solve cover?** `day`, `week`, `month` or `year`.
7. **Days to solve past the end of each window?** A whole number, blank for 14.

The date range is cut into windows of the length chosen at prompt 6. Each window is solved
on its own, extended by the look-ahead from prompt 7 so storage does not empty out just
because the window ends; only the window's own snapshots are kept in the output, and the
look-ahead's results are zeroed rather than dropped. The solved network's
`meta["reported_snapshots"]` lists exactly the snapshots that are genuine output, as
opposed to a zeroed-out look-ahead snapshot.

Nothing carries from one window to the next, so the choice matters: a shorter window
solves faster but resets storage more often, and a longer one keeps storage across more of
the range at the cost of a bigger program. Pick the one that matches how far the network's
storage actually cycles. The defaults, a calendar month with a fortnight of look-ahead,
follow what many production schedules use; they are a starting point, not something the
network states.

The objective printed and stored is the sum, across windows, of each window's own operating
cost restricted to its reported snapshots, not the raw solved-window objective, which
would double-count the days that consecutive windows' look-aheads share.

Solving a directory solves every network in it. A network that fails to solve for its own
reasons (a missing snapshot to resolve an open-ended range against, a malformed file, a
consistency error PyPSA itself raises) is reported by name as a warning and the run
continues to the next network. A bug in interop's own code still stops the run.

#### Reserves are not enforced

A solve holds back no reserve headroom. A source model's reserves are carried into the
extensions sidecar beside the network (see
[`Reserve` → extensions sidecar](../translation_mappings/translation-from-plexos-to-pypsa.md#reserve--extensions-sidecar))
and nothing in the solve reads them, so contributing units are free to run at full output
and dispatch is looser than in the source model, which tightens it by carrying reserves.
State this wherever a number from this pipeline is published.

An hour where capacity cannot cover load makes that window's solve **infeasible** rather
than producing a measured shortfall, for a network translated by `plexos-to-pypsa` or
`plexos-to-pypsa-monte-carlo`: those pipelines add no load-shedding resource, so loads keep
a fixed `p_set`. A replication that would have been a loss-of-load event therefore fails to
solve instead of reporting one. State this wherever a number from either of those two
pipelines is published.

A network translated by `plexos-to-pypsa-monte-carlo-reliability` carries a load-shedding
generator at every bus (see
[Load shedding](../translation_mappings/translation-from-plexos-to-pypsa.md#load-shedding)),
priced at the bus's Region `VoLL`. There the solve stays **optimal**, the shedding
generators' dispatch is the unserved energy, and the hours they run are the loss-of-load
hours.

#### Unit commitment

Thermal generators translated from PLEXOS keep their start-up cost, minimum up time, and
minimum down time, and remain `committable` in the PyPSA network. Unit commitment is not
turned off for the solve: each window is optimised as a mixed-integer program, not a
relaxed linear one. Expect a `pypsa` solve to take noticeably longer than a purely
energy-only dispatch, and expect that cost to compound across a long date range or a
directory of many networks.

The command prints the solve status and objective value on completion, the same as the
Sienna path:

```
[OK]  status=optimal  objective=1.23456e+06
```

A status other than `optimal` is printed in red.

## Developing against local Sienna checkouts

By default the Julia packages are installed from the Julia package registry,
pinned to the releases the solve pipeline was developed against. If you are
working on the Sienna packages themselves, point the solver at your local
checkouts in your project's `adapters.yaml`; each configured path is used in
place of the registry release (Julia's equivalent of an editable install):

```yaml
# adapters.yaml
adapters:
  julia_solver:
    powersystems_jl_path: /path/to/PowerSystems.jl
    powersimulations_jl_path: /path/to/PowerSimulations.jl
    hydropowersimulations_jl_path: /path/to/HydroPowerSimulations.jl
```

You can configure any subset; unconfigured packages stay on their registry
release.
