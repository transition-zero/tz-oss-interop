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

### Correct the dates in the gas price file

> [!IMPORTANT]
> You must correct the dates in `CSVFiles/FuelIndex/NG Prices.csv` before you translate.
> If you do not, the gas prices are incorrect for most months, and you get no error.

The file writes each date as month/day/year, for example `9/1/2026`. The translator cannot
tell this layout from day/month/year, so it reads `9/1/2026` as 9 January. Thus 233 of the
252 monthly prices go to an incorrect month. The translator cannot read the dates from
`5/31/2044`, so it leaves out the last 19 rows. The console shows only errors, so you
do not see this. Start interop with `INTEROP_LOG_LEVEL=WARNING uv run interop` to see the
warning:

```text
plexos: CSVFiles\FuelIndex\NG Prices.csv holds 190 row(s) whose date cannot be read as a point in time, so each is left out
```

The count is 190 because each of the 19 rows has prices for 10 fuels.

Do these commands to write each date as year-month-day. The command stops and does not
change the file if a date is not month/day/year.

```bash
cd "case_study_inputs/caiso-sa26/CSVFiles/FuelIndex"
cp "NG Prices.csv" "NG Prices.csv.orig"
awk '
BEGIN { FS = OFS = "," }
NR == 1 { print; next }
/^\r?$/ { print; next }
{
  n = split($1, d, "/")
  if (n != 3 || length(d[3]) != 4 || d[1] < 1 || d[1] > 12 || d[2] < 1 || d[2] > 31) {
    printf "line %d: \"%s\" is not month/day/year\n", NR, $1 > "/dev/stderr"
    exit 1
  }
  $1 = sprintf("%04d-%02d-%02d", d[3], d[1], d[2])
  print
}' "NG Prices.csv" > "NG Prices.csv.tmp" && mv "NG Prices.csv.tmp" "NG Prices.csv"
```

To make sure that the dates are correct, do this command. It must show `2025-01-01` and
then `2025-02-01`:

```bash
sed -n '2,3p' "NG Prices.csv" | cut -d, -f1
```

The command splits each line at each comma. This is safe for this file only, because the
file has no quoted values.

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
in the table below, the `Total` check figure among them.

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
| Pipeline | `plexos-to-pypsa` |
| the PLEXOS `<MasterDataSet>` input XML | `case_study_inputs/caiso-sa26/CAISOSA26 20260429.xml` |
| which PLEXOS Model to translate | `M09Y2026 SA26` |
| a four-digit year such as 2026 | Leave empty. Then the Horizon of the Model gives the snapshots, and each dated value is the value in force when that Horizon starts. |
| Output | `outputs/caiso-m09.nc` |
| the extensions sidecar | `outputs/extensions.json` |
| User mappings file | `docs/case_studies/caiso-sa26-user-mappings.json` |

`plexos-to-pypsa` translates through Sienna, so it reads the same carrier mappings file as the
Sienna path below. Refer to [The carrier mappings file](#the-carrier-mappings-file).

The translator writes one network, `outputs/caiso-m09.nc`. Every sampled trace of this model
holds 500 replications, and the translator reads replication 1, the lowest, and no other. Use
the trace files as the publisher gives them: do not cut the replication columns.

You can translate the other summer months in the same way. Give the Model name
`M05Y2026 SA26`, `M06Y2026 SA26`, `M07Y2026 SA26` or `M08Y2026 SA26`.

Then select `solve`. Give the model type `pypsa` and the network `outputs/caiso-m09.nc`.
Select an output directory. Leave the start date and the end date empty, because the solve
must cover the full month. Give the unit commitment `exact`. Keep the default window and the
default look-ahead. For more data about these two prompts, refer to
[the solve tutorial](../tutorials/solve.md#pypsa-path).

Each objective in the table below is the objective of replication 1.

No pipeline adds a load shedding resource, so this network cannot report unserved energy. An
hour without enough capacity makes the solve infeasible instead. Refer to
[What the number does not cover](#what-the-number-does-not-cover).

### The Sienna path

The same model also translates to a Sienna system, which is what a partner running
PowerSimulations.jl needs. It reads the same carrier mappings file as the PyPSA path above,
and replication 1 of each sampled trace, as that path does.

#### The carrier mappings file

A Sienna generator states a `prime_mover_type`, and a thermal one also states a `fuel_type`.
PLEXOS states neither, so you give the translator a file that says what each of your own
words becomes.
[The mapping document](../translation_mappings/translation-from-plexos-to-sienna.md#the-carrier-mappings-file)
states the shape of a row.

This model has 18 Fuel objects and 15 generator categories, and every one of them takes a
row. The block below gives all 33. Copy it into `inputs/plexos_user_mappings.yaml`.

```yaml
carriers:
  # --- Fuel objects ---------------------------------------------------------------
  - plexos_concept: fuel
    plexos_name: "NG_AZ/Cal_Blythe"
    sienna_component_type: ThermalStandard
    sienna_fuel_type: NATURAL_GAS
    sienna_prime_mover_type: OT
  - plexos_concept: fuel
    plexos_name: "NG_AZ_North"
    sienna_component_type: ThermalStandard
    sienna_fuel_type: NATURAL_GAS
    sienna_prime_mover_type: OT
  - plexos_concept: fuel
    plexos_name: "NG_AZ_North-South"
    sienna_component_type: ThermalStandard
    sienna_fuel_type: NATURAL_GAS
    sienna_prime_mover_type: OT
  - plexos_concept: fuel
    plexos_name: "NG_Cal_Kern"
    sienna_component_type: ThermalStandard
    sienna_fuel_type: NATURAL_GAS
    sienna_prime_mover_type: OT
  - plexos_concept: fuel
    plexos_name: "NG_Cal_PG&E BB"
    sienna_component_type: ThermalStandard
    sienna_fuel_type: NATURAL_GAS
    sienna_prime_mover_type: OT
  - plexos_concept: fuel
    plexos_name: "NG_Cal_PG&E LT"
    sienna_component_type: ThermalStandard
    sienna_fuel_type: NATURAL_GAS
    sienna_prime_mover_type: OT
  - plexos_concept: fuel
    plexos_name: "NG_Cal_Rosarito_CA"
    sienna_component_type: ThermalStandard
    sienna_fuel_type: NATURAL_GAS
    sienna_prime_mover_type: OT
  - plexos_concept: fuel
    plexos_name: "NG_Cal_SDG&E"
    sienna_component_type: ThermalStandard
    sienna_fuel_type: NATURAL_GAS
    sienna_prime_mover_type: OT
  - plexos_concept: fuel
    plexos_name: "NG_Cal_SoCalGas"
    sienna_component_type: ThermalStandard
    sienna_fuel_type: NATURAL_GAS
    sienna_prime_mover_type: OT
  - plexos_concept: fuel
    plexos_name: "NG_Nevada_South"
    sienna_component_type: ThermalStandard
    sienna_fuel_type: NATURAL_GAS
    sienna_prime_mover_type: OT
  - plexos_concept: fuel
    plexos_name: "NG_Oregon_Malin"
    sienna_component_type: ThermalStandard
    sienna_fuel_type: NATURAL_GAS
    sienna_prime_mover_type: OT
  - plexos_concept: fuel
    plexos_name: "NG_UT_Opal"
    sienna_component_type: ThermalStandard
    sienna_fuel_type: NATURAL_GAS
    sienna_prime_mover_type: OT
  - plexos_concept: fuel
    plexos_name: "Oil_DistillateFuel_2_CA"
    sienna_component_type: ThermalStandard
    sienna_fuel_type: DISTILLATE_FUEL_OIL
    sienna_prime_mover_type: OT
  - plexos_concept: fuel
    plexos_name: "Uranium"
    sienna_component_type: ThermalStandard
    sienna_fuel_type: NUCLEAR
    sienna_prime_mover_type: ST
  - plexos_concept: fuel
    plexos_name: "DR - High"
    sienna_component_type: ThermalStandard
    sienna_fuel_type: OTHER
    sienna_prime_mover_type: OT
  - plexos_concept: fuel
    plexos_name: "DR - Mid"
    sienna_component_type: ThermalStandard
    sienna_fuel_type: OTHER
    sienna_prime_mover_type: OT
  - plexos_concept: fuel
    plexos_name: "DefaultFuel"
    sienna_component_type: ThermalStandard
    sienna_fuel_type: OTHER
    sienna_prime_mover_type: OT
  - plexos_concept: fuel
    plexos_name: "Dummy"
    sienna_component_type: ThermalStandard
    sienna_fuel_type: OTHER
    sienna_prime_mover_type: OT
  # --- Generator categories -------------------------------------------------------
  - plexos_concept: category
    plexos_name: "CIPB"
    sienna_component_type: ThermalStandard
    sienna_fuel_type: OTHER
    sienna_prime_mover_type: OT
  - plexos_concept: category
    plexos_name: "CIPV"
    sienna_component_type: ThermalStandard
    sienna_fuel_type: OTHER
    sienna_prime_mover_type: OT
  - plexos_concept: category
    plexos_name: "CISC"
    sienna_component_type: ThermalStandard
    sienna_fuel_type: OTHER
    sienna_prime_mover_type: OT
  - plexos_concept: category
    plexos_name: "CISD"
    sienna_component_type: ThermalStandard
    sienna_fuel_type: OTHER
    sienna_prime_mover_type: OT
  - plexos_concept: category
    plexos_name: "OOS"
    sienna_component_type: ThermalStandard
    sienna_fuel_type: OTHER
    sienna_prime_mover_type: OT
  - plexos_concept: category
    plexos_name: "DR"
    sienna_component_type: ThermalStandard
    sienna_fuel_type: OTHER
    sienna_prime_mover_type: OT
  - plexos_concept: category
    plexos_name: "LFD"
    sienna_component_type: ThermalStandard
    sienna_fuel_type: OTHER
    sienna_prime_mover_type: OT
  - plexos_concept: category
    plexos_name: "CA Hydro"
    sienna_component_type: RenewableDispatch
    sienna_prime_mover_type: HY
  - plexos_concept: category
    plexos_name: "CA NonRPS PV"
    sienna_component_type: RenewableDispatch
    sienna_prime_mover_type: PVe
  - plexos_concept: category
    plexos_name: "HYBD_Solar"
    sienna_component_type: RenewableDispatch
    sienna_prime_mover_type: PVe
  - plexos_concept: category
    plexos_name: "CoLocatedSolarWind"
    sienna_component_type: RenewableDispatch
    sienna_prime_mover_type: OT
  - plexos_concept: category
    plexos_name: "ISORPS WindSolar"
    sienna_component_type: RenewableDispatch
    sienna_prime_mover_type: OT
  - plexos_concept: category
    plexos_name: "CA RPS"
    sienna_component_type: ThermalStandard
    sienna_fuel_type: OTHER
    sienna_prime_mover_type: OT
  - plexos_concept: category
    plexos_name: "GeoBio"
    sienna_component_type: ThermalStandard
    sienna_fuel_type: OTHER
    sienna_prime_mover_type: OT
  - plexos_concept: category
    plexos_name: "Pumped Storage"
    sienna_component_type: EnergyReservoirStorage
    sienna_prime_mover_type: PS
```

The same 33 rows sit beside this page as
[`caiso-sa26-user-mappings.json`](caiso-sa26-user-mappings.json). A mappings file is read as
YAML, and YAML reads JSON, so you can give that file to the `User mappings file?` prompt as
it stands.

#### The rows that need a decision

Most rows follow their own name. Six groups do not.

- **The import categories.** `CIPB`, `CIPV`, `CISC`, `CISD` and `OOS` carry imports into the
  system. Sienna has no import component, so each one takes `ThermalStandard` with the fuel
  `OTHER`, and the solve can then draw on the energy they bring.
- **`CA Hydro`.** A generator in this category is a hydro plant rather than a Storage, so it
  takes `RenewableDispatch` with the prime mover `HY`. It does not take `HydroDispatch`,
  which this translation reaches only from a Storage.
- **The gas hubs.** A Fuel name such as `NG_Cal_SoCalGas` names the hub the gas comes from,
  and not the technology of the unit that burns it. The model states no prime mover, so each
  of the 12 gas rows takes `OT`.
- **The mixed categories.** `CoLocatedSolarWind` and `ISORPS WindSolar` each hold both solar
  and wind. `GeoBio` and `CA RPS` each hold both geothermal and biomass. One row states one
  prime mover, so each of the four takes `OT`. `GeoBio` and `CA RPS` take `ThermalStandard`,
  because a geothermal plant and a biomass plant both run to a cost rather than to a weather
  profile.
- **`LFD`.** The three generators of this category sit on a node of their own, which holds a
  load of its own and no line to the rest of the system. They take `ThermalStandard` with the
  fuel `OTHER`, and they supply that one load.
- **The rows that reach no generator.** `DefaultFuel` and `Dummy` name no generator that the
  translation keeps. The `DR` category and the `DR - High` and `DR - Mid` fuels name the 18
  demand response generators, and the PLEXOS to PyPSA leg drops every one of them, because
  each states its Max Capacity in a data file rather than as a value. The five rows are here
  so that the file covers every word the model states.

Leaving the import group out costs the system 13 generators and 4,485 MW. Leaving `CA Hydro`
out costs another 4 generators and 7,570 MW. Both figures are the `p_nom` the PyPSA leg of
the same `M09Y2026 SA26` run writes.

Select `translate`. Then give these answers:

| Prompt | Answer |
| --- | --- |
| Source framework | `plexos` |
| Destination framework | `sienna` |
| Pipeline | `plexos-to-sienna` |
| the PLEXOS `<MasterDataSet>` input XML | `case_study_inputs/caiso-sa26/CAISOSA26 20260429.xml` |
| which PLEXOS Model to translate | `M09Y2026 SA26` |
| a four-digit year such as 2026 | Leave empty, as for the PyPSA run above. |
| the SiennaSchemas system.json | Keep the default |
| the HDF5 companion | Keep the default |
| the sidecar JSON | Keep the default |
| User mappings file | `docs/case_studies/caiso-sa26-user-mappings.json` |

Keep all three output paths at their defaults, or give all three the same directory. Each
default puts its file in `outputs/`, and the parquet files below follow the sidecar, so a
change to one path alone splits the product across two directories.

That run writes six files into `outputs/`:

| File | Holds |
| --- | --- |
| `system.json` | The components. |
| `system_time_series_storage.h5` | The values of each time series the system names. |
| `extensions.json` | Each value this model states that Sienna has no field for. |
| `reserves.parquet` | The megawatts each reserve requires at each snapshot. |
| `generators.parquet` | What each generator costs per MWh at each snapshot, where its fuel is priced by a data file. |
| `storage.parquet` | The share of its rating each storage unit reaches at each snapshot, where a units-out trace derates it. |

Those files are the product. The last two carry values that a Sienna component states no
field for, static or varying, so the sidecar names the file each one rides in.

The system holds 6 `ACBus`, 6 `Area`, 9 `Arc`, 5 `PowerLoad`, 267 `ThermalStandard`, 144
`RenewableDispatch`, 245 `EnergyReservoirStorage` and 9 `TwoTerminalGenericHVDCLine`
components, over 720 hourly snapshots, with 412 time-series associations.

All seven CAISO reserves reach `extensions.json`, and the six whose requirement changes each
snapshot reach `reserves.parquet` beside it. Nothing applies them.

To prove that the system dispatches, run `translate` a second time over it:

| Prompt | Answer |
| --- | --- |
| Source framework | `sienna` |
| Destination framework | `power-simulations` |
| Pipeline | `sienna-to-power-simulations` |
| the SiennaSchemas system.json | `outputs/system.json` |
| the HDF5 time-series sidecar | `outputs/system_time_series_storage.h5` |
| the extensions sidecar | `outputs/extensions.json` |
| the PowerSystems.jl system.json | `outputs/ps/power_simulations_system.json` |
| the HDF5 time-series sidecar | `outputs/ps/power_simulations_system_time_series.h5` |

Then select `solve`. Give the model type `sienna` and the system
`outputs/ps/power_simulations_system.json`. Give the network model `copperplate`, the unit
commitment `linearised`, and the HiGHS defaults. Leave the time limit empty. For more data
about these prompts, refer to [the solve tutorial](../tutorials/solve.md#sienna-path).

The Sienna solve takes no date range, so it covers every snapshot in the system, which is the
whole of September 2026.

### Unserved energy on the Sienna path

`plexos-to-sienna` writes a `PowerLoad` for each region, which a solve must serve in full. No
pipeline writes a load that a solve may cut, so the Sienna path cannot measure unserved energy.
An hour without enough capacity makes the solve infeasible instead.

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

> [!NOTE]
> We measured the figures in this section with the Monte Carlo pipelines, which interop no
> longer offers. The month table came from `plexos-to-pypsa-monte-carlo`, and the Sienna
> table from `plexos-to-sienna-monte-carlo` and its reliability variant. A row that names a
> removed pipeline cannot be reproduced. `plexos-to-pypsa` reads the same replication 1, but
> it now translates through Sienna, and we have not measured whether it gives the same
> objectives.

**What you can check by yourself.** All five summer months solve. Four months solve with
exact unit commitment. May needs the linearised relaxation.

The reliability pipeline for September gave zero unserved energy. That is, the load
shedding generators supplied no energy.

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
than to one draw. Only the reliability chain added a load shedding resource, and no
pipeline adds one now. A run drops the `VoLL` of each region, and `decisions.md` records each
drop, so the system it writes holds no resource the solve can cut.

The Sienna objective is negative because a `LoadCost` prices the load that is served rather
than the load that is cut, and PowerSimulations applies it with a negative multiplier. PyPSA
adds the cost of the energy it cuts, so the two numbers are not the same quantity. Do not
compare them.

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

No pipeline adds a load shedding resource. Thus if the capacity is less than the load in one
hour, that window does not solve, and no run measures the unserved energy.

Both paths read replication 1 of each sampled trace, and no other.

## What it costs

The download is 204 MB (195 MiB), and it unpacks to 4.1 GB. The translation of each month
writes approximately 1.8 GiB of networks.

The solve takes the most time. One replication of one month is quick, but all 500
replications take much longer. Start with one replication of one month.

The Sienna path costs less on disk and more in the solve. A run of September writes 4.64 MB:
1.43 MB of `system.json`, 2.96 MB of HDF5 companion, 195 KB of `extensions.json`, and 15 KB,
15 KB and 18 KB of `reserves.parquet`, `generators.parquet` and `storage.parquet`. The
validation run is quick.

The solve is the expensive step. HiGHS dominates the run on the reliability replication, and
loading the system, building the model and exporting the results add to it. An infeasible
replication is much quicker, because HiGHS stops as soon as it proves there is no solution.
The first solve of a session also downloads Julia and the PowerSimulations.jl packages.
