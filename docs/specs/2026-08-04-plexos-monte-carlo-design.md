# Translating and running a PLEXOS Monte Carlo study

## The problem

The CAISO 2026 Summer Assessment PLEXOS model is a 500-replication Monte Carlo study.
PyPSA has no Monte Carlo concept: a network holds one number per component per hour.
PyPSA's scenario API (`n.set_scenarios`) is two-stage stochastic programming, which folds
every scenario into one optimisation with probability weights and returns a single hedged
plan. That collapses the distribution a reliability study exists to measure, so it cannot
do this job.

The idiomatic PyPSA answer is many networks. `pypsa.NetworkCollection` is built from a
list of file paths, and the PyPSA-Eur and PyPSA-Earth Monte Carlo workflows fan out one
network per sample. So the ensemble is N `.nc` files, solved independently.

## Where the replications live

The replications ship as data. Nothing is ever drawn randomly.

| Source | Shape |
| --- | --- |
| `CSVFiles/LoadProfile/Load_2026_0416.csv` | 8,760 rows, columns `1`…`500` |
| `CSVFiles/ISO RPS/*.csv` | system solar and wind, columns `1`…`500` |
| `CSVFiles/UnitsOut/Y2026 Units Out M**.csv` | per-unit outage counts, columns `1`…`500` |

CAISO's report confirms the four stochastic variables are load, solar, wind and outages.

The model is twelve monthly `Model` objects whose horizons tile 2026 exactly. They differ
in exactly two things: the horizon window, and one scenario each (`M01`…`M12`) that
selects that month's outage file. That is twelve `t_data` rows in the entire workspace.

## Scope

**In:**

1. A Monte Carlo translation pipeline with a sink that writes many `.nc` files.
2. `solve` grown to run an ensemble, over a caller-chosen date range.
3. Reserve constraints enforced during that solve.

**Out, deliberately:** LOLE, unserved-energy accounting, the subtract-capacity-until-50-
events curve, and anything touching `compare`. Validating output against CAISO is done ad
hoc, outside the tooling, so `compare` is neither changed by this work nor designed
around. See [What compare cannot do here](#what-compare-cannot-do-here) for why.

Also out: running a full 500-replication translation or solve. The deliverable is working
functionality, proven on a cut-down input over a single day.

## Piece 1: translating the ensemble

### No sample selection

`StagePlexosXmlParams.sample_index` is **removed**, with nothing replacing it. The user
hands us the data they want translated, and we translate all of it. Anyone wanting fewer
replications gives us CSVs with fewer columns.

The ensemble size is therefore discovered, not configured: it is the set of sample columns
present in **every** sampled CSV. A sample that some file is missing is skipped with a
warning, since a network built from a partial sample would be silently wrong. Nothing
raises here, per the project's convention that strictness belongs in the validators.

The single-network `plexos-to-pypsa` pipeline keeps today's behaviour by taking the lowest
sample present, which is what `sample_index`'s default of 1 did.

### The staged shape

`State.source_time_series` frames gain a `sample` column alongside `snapshot`,
`component` and `value`. A property whose CSV has no sampled columns (a per-name file
like `MaxCap Other.csv`) is staged once and shared across every sample rather than
duplicated 500 times.

### Statics come from a reference sample

Every network in the ensemble carries **identical static data**; only time series vary.
This matters because `p_nom` is derived from a profile peak for generators whose capacity
is carried by a profile, and one of those profiles (`Rating`) is sampled. Without a fixed
reference, the CAISO generators whose capacity comes from a sampled `Rating` profile would
each have a slightly different `p_nom` per network, which makes the ensemble incoherent
and `NetworkCollection` misleading.

So the mapping steps read one designated sample and stay sample-agnostic. All fan-out
happens in the sink.

### The pipeline and the sink

A new `plexos-to-pypsa-monte-carlo.yaml`, identical to `plexos-to-pypsa.yaml` except for
its sink:

```yaml
sinks:
  - name: emit_pypsa_network_ensemble
    params:
      output_dir: outputs/ensemble
      filename_template: "network_{sample:04d}.nc"
```

`emit_pypsa_network_ensemble` writes one network per sample. It reuses
`emit_pypsa_network`'s assembly for the static components and, per sample, resolves the
time-series metadata against that sample's slice of the source series. The sink makes no
translation decisions; it only formats what the state already holds, per the project's
sink rule.

## Piece 2: growing `solve`

`ModelType` gains `PYPSA` alongside `SIENNA`. The Sienna path and its Julia adapter are
untouched.

### Shape

`SolveUseCase.__call__` currently leads with `sienna_json_path` and a pile of HiGHS
keyword arguments. Adding a second model type to that signature would push it past the
project's argument-count guidance, so the call takes a request object per model type and
dispatches on it.

A new outbound `NetworkSolverPort` covers PyPSA solving, implemented by a linopy/HiGHS
adapter. `SolverPort` (Julia) stays as it is.

### What a run does

Given a directory of networks and a date range:

1. Read each network.
2. Restrict its snapshots to the requested range.
3. Solve it in **calendar-month chunks**, each extended by a **two-week look-ahead**,
   keeping only the in-range results.
4. Write the solved network to a **separate output directory**, never back over the input,
   so a re-run cannot destroy what it was given.

The date range is what makes this testable and is what lets a caller point the runner at
2 September alone.

### Why monthly chunks with a look-ahead

Both come from the model rather than from preference.

PLEXOS runs the twelve months as independent models, so storage cannot carry charge
across a month boundary. Solving a year in one pass would let it, quietly making the
system look more reliable than CAISO's study says. `n.optimize(snapshots=...)` takes a
subset, results accumulate across calls, and state does not leak between them, so twelve
calls reproduce PLEXOS's boundaries exactly. Verified empirically: solving day 1 then
day 2 preserved day 1's results and started day 2 from `state_of_charge_initial` rather
than day 1's closing level.

PyPSA ships `optimize_with_rolling_horizon`, which is the wrong tool here twice over: its
`horizon` is a fixed *number of snapshots* and calendar months are unequal, and it
deliberately copies each chunk's closing storage level into the next chunk's opening
level, which is the linked year we must not produce.

Each `M**_2026` horizon carries `Look-ahead Indicator = -1`, `Step Count = 2`,
`Step Type = 3` (weeks). So PLEXOS optimises each month plus a fortnight and reports only
the month. Extending each chunk and discarding the tail reproduces that. This is what
stops storage being dumped at a month end, and it is why no warm-up period should be
discarded: CAISO's own loss-of-load hours fall in hours ending 19 and 20, so their results
carry no start-of-month artefact to imitate.

### Reserves

PyPSA has no reserve component, and a reserve requirement cannot be stored in a `.nc`
file. It is a constraint added at solve time through `optimize`'s `extra_functionality`
hook, which is code rather than data. That is why the translation carries reserves to
`reserves.json` and why enforcement belongs here rather than in the translator.

The sidecar already holds what is needed: each reserve's type, requirement, `VoRS` (the
value of reserve shortage) and its full list of contributing generators.

For each reserve and snapshot, the spare headroom on contributing generators must cover
the requirement:

```
sum over contributing g of (available_g,t - dispatch_g,t) + shortfall_r,t >= requirement_r,t
```

`shortfall` is priced at that reserve's `VoRS`, so a shortage is a measured quantity
rather than an infeasible model. This mirrors CAISO's own priority order, in which
shortfall lands on load-following first and only reaches unserved energy last.

One constraint per reserve per snapshot is roughly 35,000 constraints over a year, which
is negligible beside the existing LP. The per-generator formulation would be more precise
about ramp limits and costs about two million extra variables; it is not worth it.

## Testing

BDD only, through the user surface, per the project's rules.

- Translation: a cut-down PLEXOS XML with two samples and a short horizon, asserting that
  two `.nc` files are written, that their static data is identical, and that their
  availability time series differ.
- Solve: a small network over a one-day range, asserting the solve succeeds, that results
  land only inside the range, and that a reserve shortfall is priced rather than fatal.
- Chunk boundaries: a two-month fixture asserting storage does not carry charge across the
  boundary.

The builder gains sampled-column support; it already has Variables, Data Files and
End Effects from the outage work.

## Consequences worth stating

### What compare cannot do here

The intended workflow is translate, solve, then compare our solution against the source
model's solution. CAISO cannot be solved without a PLEXOS licence, so the reference has to
be numbers from their published report. Those numbers are thinner than they look.

**The committed reference is the wrong study.** The report contains two separate
assessments. Section 1.1 is the 500-sample probabilistic study. Section 1.2 is a
deterministic multi-hour stack analysis over five summer peak days, using the 1-in-2
planning forecast, NQC values as availability, and battery discharge placed by a rule of
thumb ("distributing the battery energy to maintain a constant percent surplus across the
tightest hours") rather than optimised. What sits in `interop/data/caiso_plexos/` is
section 1.2. The only Monte Carlo content in it is the constant 2,547 MW subtracted in the
two `at 0.1 LOLE` columns.

**The published Monte Carlo results are two scalars and a shape:** 9 loss-of-load events
across 500 samples, an LOLE of 0.018 days per year, a surplus of 2,547 MW at the 0.1
target, and loss-of-load hours falling in hours ending 19 to 21. The hour-of-day
distribution exists only as charts. Nothing per-hour, per-resource or per-replication is
published.

So an ensemble comparison is a two-number check rather than a per-component join, and it
does not fit the results format without scalar variables and a second reference dataset
transcribed from the report's prose. Comparison against CAISO is therefore done ad hoc and
`compare` is left alone.

### Our LOLE will not be CAISO's LOLE

CAISO counts a loss-of-load day when the system cannot serve load *or hold
regulation-up, spinning or non-spinning reserves*, and they co-optimise with mixed-integer
unit commitment. Enforcing reserves closes the first gap. Thermal generators keep their
unit-commitment behaviour (committable, with start-up cost and minimum up/down time), so
each month is solved as a mixed-integer program, and that cost must be stated wherever a
number is published.

### Translation cost

Each translation reads the twelve outage files, currently once per
plant rather than once per file, at about 2.5 minutes per month-sized run. Generating 500
networks by running the translator 500 times would be the dominant cost of the whole
exercise. The ensemble sink avoids this by translating once and fanning out, which is why
the fan-out belongs in the sink rather than in a loop over `translate`.

## Open questions

None. The reserve requirement's exact provenance is the one thing to confirm before
estimating that task: `Spin` and `Non-Spin` carry `Min Provision` as fractions of load
(0.012 and 0.048, summing to the 6 percent the report describes), and a
`Reserve/Min Provision` time series is also staged. Which of the two applies per reserve,
and what the fraction is a fraction of, needs reading before the constraint is written.
