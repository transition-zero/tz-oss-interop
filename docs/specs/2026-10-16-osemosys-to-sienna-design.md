# OSeMOSYS to Sienna: an operations system and an investments portfolio

## The problem

The canonical stage holds a whole OSeMOSYS model in the SiennaSchemas vocabulary. No step reads
it yet. `osemosys-csv-to-sienna` stages a model and writes a Sienna system with no components.

An OSeMOSYS model is a capacity expansion model over many years. Sienna holds two forms of a
model:

- An operations system holds one fixed fleet. PowerSimulations.jl dispatches it.
- An investments portfolio holds the technologies that a plan can build, the demand that they
  must meet, and the caps that they run under. PowerSystemsInvestments.jl solves it.

This design adds a pipeline for each form. Neither pipeline runs a PyPSA step or builds a PyPSA
table, because Sienna is the hub.

## The pipelines

| Pipeline | Steps | Writes |
| --- | --- | --- |
| `osemosys-csv-to-sienna` | scope, operations | `system.json`, its HDF5 companion, `extensions.json` |
| `osemosys-csv-to-sienna-investments` | scope, operations, portfolio | the same three files, and `portfolio.json` |
| `tz-osemosys-to-sienna` | as `osemosys-csv-to-sienna` | as `osemosys-csv-to-sienna` |
| `tz-osemosys-to-sienna-investments` | as `osemosys-csv-to-sienna-investments` | as `osemosys-csv-to-sienna-investments` |

```yaml
source_framework: osemosys
destination_framework: sienna
source:
  name: stage_osemosys_csv
steps:
  - name: osemosys_canonical_drop_outside_scope
  - name: osemosys_to_sienna_map_components
  - name: sienna_relate_components
  - name: osemosys_to_sienna_investments_map_technologies   # investments only
sinks:
  - name: emit_sienna_files
  - name: emit_sienna_portfolio                            # investments only
```

All steps read the canonical stage and not the CSV folder. So the TZ-format pipelines differ
only in their source.

## Decisions

The owner took each decision below on 2026-10-16.

### 1. A new step writes the portfolio

`osemosys_to_sienna_investments_map_technologies` reads the canonical stage and the base system
tables. It reuses the builders in `interop/plugins/shared/pypsa_sienna_investments_translations/`
for demand, caps and the associations. `pypsa_to_sienna_investments_map_technologies` uses the
same pattern.

The shared step `sienna_investments_map_technologies` does not change. It knows only one value
for each candidate, but OSeMOSYS costs and limits change by year. A year dimension in it would
also change the PLEXOS output.

### 2. The operations year is a required parameter

`osemosys_to_sienna_map_components` takes the parameter `year`, with no default. If the year is
not a member of `set/year`, the run stops and lists the model years. The fleet is the
`residual_capacity` of that year. A technology with zero residual capacity in that year is left
out, and `decisions.md` names it.

In the investments pipeline, the base system is the fleet at the start of the plan. So the two
investments manifests give the operations step `year: earliest`, which is the earliest year in
scope after step 6. The word is in the manifest, so it is not a hidden default. The portfolio
step takes the same year as its base system year.

### 3. A mappings row gives the Sienna operations type of a category

The user mappings file gets `carriers:` rows keyed by `osemosys_category`. The right half of the
row is the Sienna half that PyPSA and PLEXOS rows share (`interop/plugins/shared/sienna_carrier_targets.py`).

```yaml
carriers:
  - osemosys_category: gas-combined-cycle
    sienna_component_type: ThermalStandard
    sienna_fuel_type: NATURAL_GAS
    sienna_prime_mover_type: CC
```

A `SupplyTechnology` whose category has no row is left out and reported. The step does not infer
a type from the data.

### 4. A timeslice becomes an hour of a representative day

The step builds one representative day of 24 hours for each season and day type. It uses
`timeslice_in_season`, `timeslice_in_day_type`, `timeslice_in_daily_time_bracket` and
`day_split`. A daily bracket lasts `day_split × 8760` hours. The days follow each other from
1 January of the operations year. So the series is chronological and hourly.

Each day has a weight: the number of days of the year that it represents. The weight is
`year_split` of a timeslice divided by `day_split` of its bracket. The weights go to
`extensions.json` as records of a new extension kind.

A bracket within 0.05 h of a whole number of hours is rounded to it, and the event records the
rounding. AETOS gives 6.999, 10.004, 4.003 and 2.996 h. If the model does not state that
structure, or a bracket is further from a whole hour, each timeslice becomes one hour, in set
order. The step reports that it used this fallback.

Demand in MW for a timeslice is the annual demand, multiplied by its profile, divided by the
hours of the timeslice:

```
demand_mw = specified_annual_demand × specified_demand_profile / (year_split × 8760 h)
```

`specified_annual_demand` is first converted from the model's energy unit to MWh.

### 5. The portfolio keeps every year in scope

SiennaSchemas has no field for investment periods. PowerSystemsInvestments.jl takes them as
arguments of the solve template. So the portfolio states each value that changes by year in a
field that has a year:

- `capacity_limits` uses the by-key form, keyed by the year (`{"2030.0": {"min": 0, "max": 5000}}`).
- A pollutant that decision 10 allows gets one `CarbonCaps` for each year that states a limit,
  with `target_year`.
- The demand of each year is a time series of the portfolio, with the feature `year`.

A value with no year field goes to `extensions.json`, keyed by year. Capital cost and fixed cost
by year are examples. The `capital_costs` field holds the value of the earliest year in scope
in which the technology can be built and states a cost. The earliest year in scope can state a
cost of 0 for a technology that the model opens later, and a cost of 0 would make it free.

### 6. A step takes a subset of the model

`osemosys_canonical_drop_outside_scope` runs before the operations step. Its parameters are
`locations` and `years`. It drops the canonical rows outside the scope. It also drops a transport
technology with an end outside the scope. An empty parameter keeps everything.

### 7. The investments solve stacks on #42

PR #42 adds the expansion leg (`sienna-to-power-systems-investments`) and the `solve` model type
that runs PowerSystemsInvestments.jl. This work stacks on that branch. A change that an
OSeMOSYS portfolio needs in the leg goes into this branch.

### 8. The results format gets four annual variables

| Variable | Unit | Timestamp |
| --- | --- | --- |
| `installed_capacity` | MW | 1 January of the year |
| `new_capacity` | MW | 1 January of the year |
| `production` | MWh in the year | 1 January of the year |
| `emissions` | t in the year | 1 January of the year |

Trade compares as the `production` of a transport technology: the energy that it delivers at
its far end in the year. A new results pipeline reads the published AETOS results CSV. The
published CSV has no `ProductionByTechnology` and no `Trade` rows. So its reader calculates both
from `TotalAnnualTechnologyActivityByMode` and the model's `OutputActivityRatio`.

### 9. Electricity only, one bus for each location

- Each location of an electricity fuel becomes one `ACBus` and one `Area`. Two or more
  electricity fuels at one location share the bus.
- A `conversion` technology between two electricity fuels at one location is left out. Its loss
  is a gap analysis entry. The demand stays at the value that the model states.
- A technology on a fuel that is not electricity is left out and reported.
- A thermal plant takes its fuel cost and its emission rate from the cheapest `fuel_supply`
  technology that makes its input fuel at its location. A pipeline is not a `fuel_supply`
  technology, so the rule ignores it. When the cheapest source has a limit, the true price is
  higher, and a gap analysis entry records that. The owner chose this rule on 2026-10-16, in
  place of "no fuel cost when two or more technologies make the fuel".

### 10. A pollutant cap reaches the portfolio only when it covers the whole model

`CarbonCaps` has no field for a region or a pollutant, so one cap limits the whole portfolio.
A pollutant covers the whole model when every technology that emits a pollutant emits it. Only
such a pollutant gets a `CarbonCaps` for each year that states a limit. The limits of every
other pollutant go to `extensions.json` as `constraint` records, and `decisions.md` names
each one. The PLEXOS rule for a scoped `Constraint` is the same. The owner chose this rule on
2026-10-16.

## Calls made during the design

These calls were not put to the owner. Each one is recorded in the mapping documents.

- An `AggregateTransportTechnology` becomes a `TwoTerminalGenericHVDCLine` in the operations
  system, rated at its residual capacity, with the loss `1 − output_activity_ratio`. In the
  portfolio, it becomes an `AggregateTransportTechnology`. `emit_sienna_portfolio` learns to
  write that type.
- For a technology with two or more modes, operating mode `1` sets the operations values. A
  storage technology takes its charge mode from `technology_to_storage` and its discharge mode
  from `technology_from_storage`. The values of other modes go to `extensions.json`, and the gap
  analysis records the loss.
- The `units:` part of the user mappings file states the units. The step converts capacity to
  MW, energy to MWh and emissions to t. A currency may state a scale, for example
  `million USD`. When a unit that a conversion needs is absent, the run stops and names the
  field of `units:`. That is a missing parameter, not model data.
- The emission rate of a plant is its own `emission_rate`, plus its input ratio multiplied by
  the rate of the producer of its fuel. A plant with carbon capture keeps a negative rate.
- `annual_exogenous_emission` is subtracted from `annual_emission_limit`, because OSeMOSYS adds
  it to the emissions that the limit holds.
- A `StorageTechnology` becomes an `EnergyReservoirStorage`. A technology that charges and
  discharges a storage gives its power rating. `residual_storage_capacity` gives its energy
  rating.

## Decisions taken during the build

The builder took these decisions after the design was approved. Each one follows from a fact
that the build found.

- **Trade is a production, not a flow.** The published results are annual, and `flow` is MW at
  a timestamp. So trade compares as the `production` of a transport technology.
- **A line flows both ways when the model states a return mode.** A transport technology whose
  other operating mode carries electricity from B to A becomes one line with limits in both
  directions.
- **The carrier of a generator record is its category.** The `carriers:` row key is the user's
  word for the technology, as the PLEXOS row key is.
- **The emission penalty is a dispatch cost.** OSeMOSYS charges `emission_penalty` on activity,
  so the variable cost of a plant and of a candidate adds rate × penalty.
- **Each pipeline reports the parameters that it does not apply.** A last step,
  `osemosys_to_sienna_report_unapplied_parameters`, records them in `decisions.md`.
- **A candidate is priced in its first buildable year.** See decision 5.
- **An existing plant belongs to the candidate of its own name.** OSeMOSYS gives each technology
  its own residual capacity, so one plant must not count under several candidates.
- **The scope step reads its lists as text separated by commas.** No list parameter existed, and
  the REPL and `--override` give text.
- **The Sienna solve can allow unserved energy at a penalty.** A fleet of residual capacity can
  be short at one location, which makes the whole dispatch infeasible. The option uses the
  network balance slacks of PowerSimulations and is off by default.
- **A system with no AC line solves with the `copperplate` network model.** `dcp` needs AC
  branches.
- **Three defects in shared code are fixed.** The PowerSimulations leg divided a per-unit
  generator `rating` again, and wrote HVDC limits in MW where PowerSystems reads per unit of
  the system base. `sienna-to-results` wrote `load` with a negative sign. These fixes change
  the PLEXOS and PyPSA dispatch results too.
- **The expansion leg passes the existing fleet to PowerSystemsInvestments for every source.**
  Before, every technology started from zero capacity.

## The benchmark

AETOS `v2.0.0` proves the work on a real model. Both pipelines translate the full model. Each
solve may use a subset that step 6 takes, and the case study names it.

The comparison runs through `interop compare`. Each difference from the published results gets
an entry in `docs/translation_mappings/osemosys-to-sienna-gap-analysis.md` that names one cause:

- the translation loses something;
- the two models state different mathematics;
- the solver found a different optimum among equal ones.

## Documents

- `docs/translation_mappings/translation-from-osemosys-to-sienna.md`
- `docs/translation_mappings/translation-from-osemosys-to-sienna-investments.md`
- `docs/translation_mappings/osemosys-to-sienna-gap-analysis.md`
- `docs/case_studies/aetos.md` gets the translate runs, the solves and the comparison.

## Left to the builder

- The field-level mapping of each Sienna type, within the rules above.
- The names of the new extension kinds and their fields.
- How the expansion leg of #42 reads the representative days and the years of an OSeMOSYS
  portfolio.
