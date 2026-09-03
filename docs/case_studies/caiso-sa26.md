# CAISO 2026 Summer Assessment

## The model

CAISO makes a Summer Loads and Resources Assessment each year. The assessment tests if the
generators in California can supply the demand at the summer peak. CAISO publishes the
PLEXOS model for the assessment.

The model does 500 chronological replications of the year. Each replication has different
values for the load, the solar output, the wind output and the outages. The published
report gives the load and the surplus for five summer peak days.

These properties make the model a good test. The model has a large number of real
generators. It uses the Monte Carlo path of the translator. Also, the publisher gives
values that you can compare against your own output.

## Get the input

Download the model archive from the
[CAISO 2026 Summer Loads and Resources Assessment public stochastic model](https://www.caiso.com/documents/2026-summer-loads-and-resources-assessment-public-stochastic-model.zip).

| | |
| --- | --- |
| File | `CAISOSA26 20260429.xml`, and its `CSVFiles/` trace directory |
| SHA-256 of the XML file | `9bc961aa56ca47d6396da2cf9732c05a9a65b1a7874b61f385f87647a7b0cc2b` |
| Download size | 204 MB (195 MiB) as one zip file |
| Size on disk | 13 MB for the XML file, and 4.1 GB with the traces |
| Put it in | `case_study_inputs/caiso-sa26/` |

Do not change the directory layout of the archive. The XML file gives a relative path for
each trace file.

To make sure that you have the correct XML file, do this command:

```bash
shasum -a 256 "case_study_inputs/caiso-sa26/CAISOSA26 20260429.xml"
```

## Get the reference data

interop can compare a translated network against the numbers CAISO publishes. Those
numbers are not in this repository. You make two CSV files from the published documents,
and you name each file at a prompt.

| | |
| --- | --- |
| Source of the stack model | Section 1.2, Multi-hour Stack Analysis, of the [2026 Summer Loads and Resources Assessment](https://www.caiso.com/documents/2026-summer-loads-and-resources-assessment.pdf). Figure 1.8 gives the peak days from May to August, and Figure 1.9 gives the September peak day. |
| Source of the appendix | Table 2.1, Probabilistic assessment modeled capacity (MW) by month and fuel type (2026), in the [technical appendix](https://www.caiso.com/documents/2026-summer-loads-and-resources-assessment-technical-appendix.pdf). |
| Put them in | `case_study_inputs/caiso-sa26/` |

CAISO draws the stack analysis as charts, so you read the series behind each chart and
write them out as rows. Only the columns below matter. Any value you can read gives you a
comparison; the closer your figures are to the published ones, the more the comparison
tells you.

### The stack model CSV

Write one row for each hour of each peak day, and a second row for the same hour with the
battery charging load folded into the demand. Five peak days over 24 hours in both
scenarios is 240 rows.

Give the file these column headers. Spell each one as CAISO spells it.

| Column | What it holds |
| --- | --- |
| `MONTH` | the month of the peak day, 5 to 9 |
| `Day` | the day of the month of the peak day |
| `HOUR (PDT)` | the hour ending, 1 to 24 |
| `2025 IEPR Forecast` | the demand of that hour, in MW |
| `Charging Load (Y/N)` | `Y` where the row folds the battery charging load into the demand, `N` where it does not |
| `Natural Gas`, `Nuclear`, `Hydro`, `Other`, `Other Renewables`, `Solar`, `Wind`, `Imports` | the available capacity of that category in that hour, in MW |
| `Battery Storage`, `Demand Response` | the dispatch of that category in that hour, in MW |
| `Surplus MW` | the surplus of that hour, in MW |

The file can carry other columns. interop reads the columns above and ignores the rest.

interop reads the rows where `Charging Load (Y/N)` is `Y`, and drops the others.

`HOUR (PDT)` is an hour ending. interop subtracts one hour from it, so hour ending 18
becomes the snapshot that starts at 17:00. PyPSA labels a snapshot by the start of its
interval, and this makes the two line up. The file states no year, and interop reads every
row as 2026.

### The appendix CSV

Write one row for each fuel type. Give the file a `Fuel type` column, and one column for
each month headed `Jan` to `Dec`. Copy Table 2.1 as it stands, including the `Total` row
and the `Net Import Limit*` row.

interop reads May to September and ignores the other seven months. It rolls the finer
fuels up to the categories that the stack model uses, and drops any row whose fuel is not
in the table below — the `Total` check figure among them.

| Appendix fuel | Category |
| --- | --- |
| `Biogas`, `Biomass`, `Geothermal` | `Other Renewables` |
| `Hybrid` | `Other` |
| `Net Import Limit*` | `Imports` |
| every other fuel | a category of the same name |

## Translate and solve

If you did not install interop, install it now. Refer to
[Install](../../README.md#install). The solver needs no other software.

Start interop:

```bash
uv run interop
```

Select `translate`. Then give these answers to the prompts:

| Prompt | Answer |
| --- | --- |
| Source framework | `plexos` |
| Destination framework | `pypsa` |
| Pipeline | `plexos-to-pypsa-monte-carlo` |
| the PLEXOS `<MasterDataSet>` input XML | `case_study_inputs/caiso-sa26/CAISOSA26 20260429.xml` |
| which PLEXOS Model to translate | `M09Y2026 SA26` |
| a four-digit year such as 2026 | Leave empty. Then the Horizon of the Model gives the snapshots, and each dated value is the value in force when that Horizon starts. |
| directory to hold the ensemble | `outputs/caiso-m09` |
| names each network in the ensemble | Keep the default, `network_{sample}.nc` |
| the extensions sidecar | `outputs/extensions.json` |

The translator writes 500 networks, from `network_1.nc` to `network_500.nc`. This operation
takes approximately 1.8 GiB of disk space.

You can translate the other summer months in the same way. Give the Model name
`M05Y2026 SA26`, `M06Y2026 SA26`, `M07Y2026 SA26` or `M08Y2026 SA26`.

Then select `solve`. Give the model type `pypsa` and the network
`outputs/caiso-m09/network_1.nc`. Select an output directory. Leave the start date and the
end date empty, because the solve must cover the full month. Give the unit commitment
`exact`. Keep the default window and the default look-ahead. For more data about these two
prompts, refer to [the solve tutorial](../tutorials/solve.md#pypsa-path).

Each objective in the table below is the objective of replication 1. If you solve the full
directory, you get 500 objectives.

If you want a measurement of the unserved energy, do the translation again with the
`plexos-to-pypsa-monte-carlo-reliability` pipeline. That pipeline adds a load shedding
generator at each bus. The price of each load shedding generator is the value of lost load
of its region. Give the same answers to the prompts, but write to
`outputs/caiso-m09-reliability`. Then solve `outputs/caiso-m09-reliability/network_1.nc`
with the start date `2026-09-01`, the end date `2026-09-30` and the unit commitment
`linearised`.

### The Sienna path

The same model also translates to an ensemble of Sienna systems, which is what a partner
running PowerSimulations.jl needs. PowerSimulations solves no Monte Carlo forecast, so the
ensemble is one whole system per replication rather than one system holding every
replication. That translation is a run of its own, with its own mappings file.

Write `inputs/plexos_user_mappings.yaml` in PLEXOS words. This model has 18 Fuel objects and
15 generator categories, and every one of them needs a row.
[The mapping document](../translation_mappings/translation-from-plexos-to-sienna.md#the-carrier-mappings-file)
states the shape of a row.

Two of the categories need a decision. `CIPB`, `CIPV`, `CISC`, `CISD` and `OOS` carry imports
into the system; Sienna has no import component, so give each one `ThermalStandard` with the
fuel `OTHER`, and the solve can then draw on the energy they bring. A generator in the
`CA Hydro` category is a hydro plant rather than a Storage, so give it `RenewableDispatch`
with the prime mover `HY`, not `HydroDispatch`, which this translation reaches only from a
Storage. Leaving either group out costs the system 17 generators and about 5 GW, and the
September solve then has no solution at all.

**Cut the ensemble down first.** Every sampled CSV under `case_study_inputs/caiso-sa26/CSVFiles`
holds 500 numbered value columns, one per replication. Keep the first three of them in each
file and delete the rest. Then a run gives a three-replication ensemble, which is what the
numbers below cover. The full 500-replication claim in this page covers the PyPSA path only.

Select `translate`. Then give these answers:

| Prompt | Answer |
| --- | --- |
| Source framework | `plexos` |
| Destination framework | `sienna` |
| Pipeline | `plexos-to-sienna-monte-carlo` |
| User mappings file | `inputs/plexos_user_mappings.yaml` |
| the PLEXOS `<MasterDataSet>` input XML | `case_study_inputs/caiso-sa26/CAISOSA26 20260429.xml` |
| which PLEXOS Model to translate | `M09Y2026 SA26` |
| a four-digit year such as 2026 | Leave empty, as for the PyPSA run above. |
| directory to hold the ensemble | `outputs/caiso-m09-sienna` |
| names each replication's directory | Keep the default, `{sample}` |

That run writes one directory per replication, `1`, `2` and `3`, each holding four files:
`system.json`, its HDF5 companion `system_time_series_storage.h5`, `extensions.json`, and the
`reserves.parquet` that the reserve records point at. Those files are the product.

Each system holds 6 `ACBus`, 6 `Area`, 9 `Arc`, 5 `PowerLoad`, 267 `ThermalStandard`, 144
`RenewableDispatch`, 246 `EnergyReservoirStorage` and 9 `TwoTerminalGenericHVDCLine`
components, over 720 hourly snapshots, with 392 time-series associations. Every replication
states the same components and the same associations, and the three differ only in the values
their HDF5 companions hold.

All seven CAISO reserves reach `extensions.json`, and the six whose requirement changes each
snapshot reach `reserves.parquet` beside it. Nothing applies them.

The run warns that 4 generators carry an outage profile in some of the three replications but
not in all of them, and leaves those four profiles out. Refer to
[the gap analysis](../translation_mappings/plexos-to-sienna-gap-analysis.md#a-profile-that-reaches-only-some-replications).

To prove that a system dispatches, run `translate` a second time over one replication:

| Prompt | Answer |
| --- | --- |
| Source framework | `sienna` |
| Destination framework | `power-simulations` |
| Pipeline | `sienna-to-power-simulations` |
| the SiennaSchemas system.json | `outputs/caiso-m09-sienna/1/system.json` |
| the HDF5 time-series sidecar | `outputs/caiso-m09-sienna/1/system_time_series_storage.h5` |
| the extensions sidecar | `outputs/caiso-m09-sienna/1/extensions.json` |
| the PowerSystems.jl system.json | `outputs/ps/power_simulations_system.json` |
| the HDF5 time-series sidecar | `outputs/ps/power_simulations_system_time_series.h5` |

Then select `solve`. Give the model type `sienna` and the system
`outputs/ps/power_simulations_system.json`. Give the network model `copperplate`, the unit
commitment `linearised`, and the HiGHS defaults. Leave the time limit empty. For more data
about these prompts, refer to [the solve tutorial](../tutorials/solve.md#sienna-path).

The Sienna solve takes no date range, so it covers every snapshot in the system, which is the
whole of September 2026.

### Unserved energy on the Sienna path

`plexos-to-sienna-monte-carlo` writes a `PowerLoad` for each region, which a solve must serve
in full. Run `plexos-to-sienna-monte-carlo-reliability` instead to get a load a solve may cut.
Give the same answers, writing to `outputs/caiso-m09-reliability`.

Each region's load then becomes an `InterruptiblePowerLoad` whose `operation_cost` holds the
value of lost load of its region. Four of the five regions state $2,000/MWh. `LFD` states
none, so it takes PLEXOS's own default of $10,000/MWh, which is the price the PyPSA side of
the same run sheds at.

Read the unserved energy from the solve output. The power each load was asked for is in
`results/parameters/ActivePowerTimeSeriesParameter__InterruptiblePowerLoad.csv`, in per-unit
of the 100 MVA system base; the power the solve served is in
`results_wide/variables/ActivePowerVariable__InterruptiblePowerLoad.csv`, in MW. Multiply the
first by 100, subtract the second, and sum over the month. No report collects it for you.
Refer to
[the gap analysis](../translation_mappings/plexos-to-sienna-gap-analysis.md#a-reliability-solve-reports-its-unserved-energy-in-the-results-files).

## Compare against the published stack model

Solve a network first. The comparison reads the solved network.

Select `compare`. Then give these answers to the prompts:

| Prompt | Answer |
| --- | --- |
| First result's framework | `pypsa` |
| Second result's framework | `caiso-plexos` |
| `pypsa.path` | the solved network, such as `outputs/caiso-m09/network_1.nc` |
| `pypsa.extensions_json_path` | Leave empty. The comparison needs nothing from the sidecar. |
| `caiso-plexos.stack_model_path` | `case_study_inputs/caiso-sa26/stack_model.csv` |
| `caiso-plexos.appendix_path` | `case_study_inputs/caiso-sa26/appendix_capacity_by_fuel_month.csv` |
| Output path for summary report | `outputs/comparison_summary.md` |

The two `caiso-plexos` prompts offer those paths as their defaults. Press Enter for each
one if you gave your files those names.

The report holds two tables. The first gives the coverage of each variable: what each side
reports, and what only one side reports. The second gives the error where both sides state
the same variable at the same timestamp.

The comparison joins the two sides on the timestamp, so it only reports on the hours that
your solved network and the peak days have in common.

## The headline number

**What you can check by yourself.** All five summer months solve. Four months solve with
exact unit commitment. May needs the linearised relaxation.

The reliability pipeline for September gives zero unserved energy. That is, the load
shedding generators supply no energy. To get this result, solve from 2026-09-01 to
2026-09-30 with linearised unit commitment.

The translator writes a `decisions.md` file adjacent to the network. That file gives each
source field, the destination field for it, and each component that the translator did not
translate.

| Month | Unit commitment | Status | Objective |
| --- | --- | --- | --- |
| May | linearised | optimal | $1.36776 × 10⁸ |
| June | exact | optimal | $1.78179 × 10⁸ |
| July | exact | optimal | $3.79643 × 10⁸ |
| August | exact | optimal | $4.58935 × 10⁸ |
| September | exact | optimal | $3.96131 × 10⁸ |
| September, reliability pipeline | linearised | optimal | $3.95285 × 10⁸ |

If you give the unit commitment `exact` for May, the solver reaches its 600 second cap and
finds no integer solution. Give `linearised` for May. We do not know why May is the month that
fails. The model states a reservoir volume in GWh and a Natural Inflow in MW, so HELMS pumped
storage holds 184,500 MWh, which is about 453 hours of storage, and it refills across the
month. But the other four months hold the same reservoirs and each one solves.

**The Sienna path, on three replications of September.** The reliability system solves, and
it reports where the month is short.

| Replication | Chain | Unit commitment | Network model | Status | Objective |
| --- | --- | --- | --- | --- | --- |
| 1 | `plexos-to-sienna-monte-carlo` | linearised | copperplate | infeasible | none |
| 2 | `plexos-to-sienna-monte-carlo` | linearised | copperplate | infeasible | none |
| 1 | `plexos-to-sienna-monte-carlo-reliability` | linearised | copperplate | optimal | −$7.72762 × 10¹⁰ |

The reliability solve cuts 7,467 MWh, all of it at `SDGE_load`, in 2 of the month's 720
hours, and the deepest hour is 4,089 MW short. That shortfall is why the plain chain does not
solve: a `PowerLoad` must be served in full, so a system that cannot serve it has no solution
at all. Two replications behave the same way, so the shortfall belongs to the month rather
than to one draw. Run the reliability chain for September. This is the loss
[the gap analysis](../translation_mappings/plexos-to-sienna-gap-analysis.md#load-shedding-on-a-plain-run)
describes, seen on a real model.

The Sienna objective is negative because a `LoadCost` prices the load that is served rather
than the load that is cut, and PowerSimulations applies it with a negative multiplier. Do not
compare it against a PyPSA objective; refer to
[the gap analysis](../translation_mappings/plexos-to-sienna-gap-analysis.md#a-sienna-objective-and-a-pypsa-objective-do-not-compare).

The PyPSA path reports zero unserved energy for the same month, so the two paths disagree
here. Three differences could account for it, and we did not measure which: PLEXOS's import
categories become plain thermal units on the Sienna path and keep their own representation on
the PyPSA path; the Sienna ensemble leaves out the 4 outage profiles that reach only some
replications; and the Sienna solve applies `ThermalBasicDispatch`, which is not the
relaxation PyPSA applies for `linearised`.

**What we measured.** We compared the translation against the published CAISO stack model.

The September load has no bias. Across all 500 replications, it is 0.8% more than the
published value for the peak hour. But the daily peak of the load occurs one hour too
early in three of the five months. This is a known problem.

The firm capacity is near to the published value for all categories except one. For three
categories, the difference agrees with the CAISO definition of qualifying capacity. The
exception is Other Renewables. Our value is 1,185 MW, and the reference value is 1,637 MW.
Our value is 27.6% less, and we cannot explain this difference.

You cannot compare the solar capacity or the wind capacity. Two PLEXOS categories each
contain both technologies, and the model has no data that divides them.

You cannot compare the imports. The CAISO value for imports is a transfer limit, not the
capacity of a generator.

The demand response is absent. No demand response carrier goes into the translated
network. Thus there is nothing to compare against the 822 MW that CAISO gives.

We measured these values on 2026-08-18, on branch `caiso-compare-dataset-v2`, at interop
version 0.1.0. The software that measured them is not in this repository, so these exact
figures are not reproducible here. You can do the solves above again, and you can run the
comparison above against your own copy of the published numbers.

## What the number does not cover

A solve keeps no reserve headroom, on either path. The translator puts the CAISO reserves in
a sidecar file, but nothing applies them. Thus the generators can supply their full output,
and the dispatch is less constrained than the dispatch in the source model. On the Sienna
path the reserves reach `extensions.json` beside each replication's system, and the six
whose requirement changes each snapshot reach `reserves.parquet` beside that; they are still
unapplied.

Neither `plexos-to-pypsa-monte-carlo` nor `plexos-to-sienna-monte-carlo` adds a load shedding
resource. Thus if the capacity is less than the load in one hour, that window does not solve.
Only the two reliability pipelines measure the unserved energy.

The numbers on the Sienna path cover three replications, not 500. The 500-replication figures
above are the PyPSA path alone.

## What it costs

The download is 204 MB (195 MiB), and it unpacks to 4.1 GB. The translation of each month
writes approximately 1.8 GiB of networks.

The solve takes the most time. One replication of one month is quick, but all 500
replications take much longer. Start with one replication of one month.

The Sienna path costs less on disk and more in the solve. A three-replication ensemble of
September writes 13 MB: 1.42 MB of `system.json`, 2.82 MB of HDF5 companion, 92 KB of
`extensions.json` and 40 KB of `reserves.parquet` for each replication. The validation run
over one replication is quick.

The solve is the expensive step. HiGHS dominates the run on the reliability replication, and
loading the system, building the model and exporting the results add to it. An infeasible
replication is much quicker, because HiGHS stops as soon as it proves there is no solution.
The first solve of a session also downloads Julia and the PowerSimulations.jl packages.
