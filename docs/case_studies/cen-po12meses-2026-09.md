# CEN 12-month operation programme, September 2026

## The model

The Coordinador Eléctrico Nacional (CEN) is the system operator of Chile. Each month, CEN
publishes the PLEXOS model of its operation programme. The programme covers the next 12
months of the Sistema Eléctrico Nacional (SEN), the national grid of Chile.

This page uses the programme of September 2026. It covers September 2026 to August 2027.

The model is a large hydro-thermal system:

| PLEXOS class | Objects |
| --- | --- |
| `Generator` | 1,994 |
| `Constraint` | 509 |
| `Load` | 420 |
| `Line` | 340 |
| `Node` | 241 |
| `Waterway` | 206 |
| `Storage` | 161 |
| `Battery` | 144 |
| `Company` | 143 |
| `Timeslice` | 101 |
| `Decision Variable` | 46 |
| `Zone` | 16 |
| `Reserve` | 13 |
| `Region` | 2 |

The XML file holds nine `Model` objects. This page translates `PRGMEN_Base`, which uses the
horizon `Coordinador_mensual`.

**Today, the translation keeps almost none of this model.** The Sienna system holds 0.59 MW
of generation, no load and no time series. This page says why, and what it
costs to close each gap. Refer to [What the translation writes today](#what-the-translation-writes-today).

## Get the input

CEN publishes the model on the page
[Programación Mensual 2026](https://www.coordinador.cl/operacion/documentos/estudios-de-la-programacion-de-la-operacion/programacion-mensual/2026-programacion-mensual/).
The site does a browser check, so a download with `curl` gets HTTP 403. Use a web browser.

1. Open the page.
2. Download `PLEXOS202609_mensual.zip`, the PLEXOS archive of September 2026.
3. Extract `Datos_Men202609.zip` from that archive.
4. Extract all of `Datos_Men202609.zip` into `case_study_inputs/cen-po12meses-2026-09/`.
5. You do not need `Res_Men202609.zip`. It holds the PLEXOS solution, and the translator does not read it.

| | |
| --- | --- |
| File | `DBSEN_202609_PO12meses.xml`, and its data files |
| SHA-256 of the XML file | `cd07bc76ce8061c1c22b986b85e8d82c730a6d8119c0c47d3287345a7b8939cc` |
| SHA-256 of `PLEXOS202609_mensual.zip` | `1cb87f921037edfa96bc9555b3f6cacb22a74a7ad8aaf506ac7d2226ce27836e` |
| SHA-256 of `Datos_Men202609.zip` | `ee5f3a4f2b599ad5ee3a0a7e7cdf400ae78c046cb73c0bbed2bb9d48540a4166` |
| Download size | 886 MB for `PLEXOS202609_mensual.zip` |
| Size on disk | 29 MB for the XML file, and 58 MB with the data files |
| Put it in | `case_study_inputs/cen-po12meses-2026-09/` |

The same page also holds `po12meses_sep26.zip`. That archive holds the CEN report and a
spreadsheet, and no PLEXOS model.

The XML file looks for its data files beside it, and for four of them in a `Params/` folder.
Keep the layout of the archive.

To make sure that you have the correct XML file, do this command:

```bash
shasum -a 256 case_study_inputs/cen-po12meses-2026-09/DBSEN_202609_PO12meses.xml
```

## The carrier mappings file

This model states no `Fuel` object. Each thermal unit states its own `Fuel Price` and
`Heat Rate`. So every generator takes its Sienna type from its PLEXOS category.
[The mapping document](../translation_mappings/translation-from-plexos-to-sienna.md#the-carrier-mappings-file)
states the shape of a row.

The model states 17 generator categories. The file below gives one row to each of them.
Copy it into `inputs/plexos_user_mappings.yaml`.

```yaml
carriers:
  - plexos_concept: category
    plexos_name: Solar PV Farms
    sienna_component_type: RenewableDispatch
    sienna_prime_mover_type: PVe
  - plexos_concept: category
    plexos_name: Solar CSP Farms
    sienna_component_type: RenewableDispatch
    sienna_prime_mover_type: CP
  - plexos_concept: category
    plexos_name: Wind Farms
    sienna_component_type: RenewableDispatch
    sienna_prime_mover_type: WT
  - plexos_concept: category
    plexos_name: Hydro Gen Run-of-River
    sienna_component_type: RenewableDispatch
    sienna_prime_mover_type: HY
  - plexos_concept: category
    plexos_name: Hydro Gen Impoundment
    sienna_component_type: RenewableDispatch
    sienna_prime_mover_type: HY
  - plexos_concept: category
    plexos_name: Hydro Gen Others
    sienna_component_type: RenewableDispatch
    sienna_prime_mover_type: HY
  - plexos_concept: category
    plexos_name: Thermal Gen GNL
    sienna_component_type: ThermalStandard
    sienna_fuel_type: NATURAL_GAS
    sienna_prime_mover_type: CC
  - plexos_concept: category
    plexos_name: Thermal Gen Gas
    sienna_component_type: ThermalStandard
    sienna_fuel_type: NATURAL_GAS
    sienna_prime_mover_type: CC
  - plexos_concept: category
    plexos_name: Thermal Gen Diesel
    sienna_component_type: ThermalStandard
    sienna_fuel_type: DISTILLATE_FUEL_OIL
    sienna_prime_mover_type: IC
  - plexos_concept: category
    plexos_name: Thermal Gen Fuel Oil
    sienna_component_type: ThermalStandard
    sienna_fuel_type: RESIDUAL_FUEL_OIL
    sienna_prime_mover_type: ST
  - plexos_concept: category
    plexos_name: Thermal Gen Coal
    sienna_component_type: ThermalStandard
    sienna_fuel_type: COAL
    sienna_prime_mover_type: ST
  - plexos_concept: category
    plexos_name: Thermal Gen Biomass
    sienna_component_type: ThermalStandard
    sienna_fuel_type: OTHER_BIOMASS_SOLIDS
    sienna_prime_mover_type: ST
  - plexos_concept: category
    plexos_name: Thermal Gen Biogas
    sienna_component_type: ThermalStandard
    sienna_fuel_type: OTHER_BIOMASS_GAS
    sienna_prime_mover_type: IC
  - plexos_concept: category
    plexos_name: Thermal Gen GLP
    sienna_component_type: ThermalStandard
    sienna_fuel_type: PROPANE
    sienna_prime_mover_type: IC
  - plexos_concept: category
    plexos_name: Thermal Gen X
    sienna_component_type: ThermalStandard
    sienna_fuel_type: OTHER
    sienna_prime_mover_type: OT
  - plexos_concept: category
    plexos_name: Thermal Gen Others
    sienna_component_type: ThermalStandard
    sienna_fuel_type: OTHER
    sienna_prime_mover_type: OT
  - plexos_concept: category
    plexos_name: Geothermal Gen
    sienna_component_type: ThermalStandard
    sienna_fuel_type: GEOTHERMAL
    sienna_prime_mover_type: BT
```

These rows are a first choice for this page. CEN did not check them.

## Translate

The command of tz-oss-interop is `interop`. Do this command in a project that `interop init`
made. Replace `<repository>` with the path of your tz-oss-interop clone.

The bare command `interop` needs the uv tool install in the README. If you use `uv sync`
only, put `uv run` before `interop`.

```bash
interop headless_cli --pipeline plexos-to-sienna \
  --override 'source.path=<repository>/case_study_inputs/cen-po12meses-2026-09/DBSEN_202609_PO12meses.xml' \
  --override 'source.model=PRGMEN_Base' \
  --override 'source.horizon_year=2026' \
  --override 'sink[0].output_system_json_file_path=outputs/system.json' \
  --user-mappings-path inputs/plexos_user_mappings.yaml
```

`source.horizon_year=2026` translates calendar year 2026 only, from 2026-01-01 up to
2027-01-01. The months of the programme in 2027 are outside this run.

To see the warnings on the console, set `INTEROP_LOG_LEVEL=INFO`.

The run completes in about 5 seconds. It writes `outputs/system.json`,
`outputs/extensions.json`, the time series store and `decisions.md`.

## What the translation writes today

The numbers below come from tz-oss-interop at commit `7bdd194`, with Polars 2.0.0.

| What the model states | What the Sienna system holds |
| --- | --- |
| 241 `Node` objects | 241 `ACBus` |
| 2 `Region` objects | 2 `Area` |
| 340 `Line` objects | 340 `Line`, each with `r` 0, `x` 0 and `rating` 1e+28 |
| 1,994 `Generator` objects | 59 `ThermalStandard`, each rated 0.01 MW |
| 144 `Battery` objects | 14 `EnergyReservoirStorage` |
| 161 `Storage` objects and 206 `Waterway` objects | Nothing |
| 420 `Load` objects | Nothing |
| 13 `Reserve` objects | 13 records in `extensions.json` |
| 509 `Constraint` objects | 432 records in `extensions.json` |
| 87 `Data File` objects | No time series |

The 59 thermal units that translate are all in the category `Thermal Gen X`. Their names,
such as `ATA_CC1_TGA_GNL`, are the operating modes of combined-cycle plants. The 14 batteries
that translate are the `_AUX` batteries, such as `BAT_ARICA_2_AUX`.

`decisions.md` holds 2,091 `COMPONENT_SKIPPED` rows:

| Component | Rows | The reason that `decisions.md` gives |
| --- | --- | --- |
| `Generator` | 1,371 | `Max Capacity comes from a data file rather than a value` |
| `Generator` with a head `Storage` | 564 | `Max Capacity comes from a data file rather than a value` |
| `Battery` | 130 | `Max Power comes from a data file rather than a value` |
| `Storage` | 26 | `no Generator names this Storage as a head or tail` |

So a Sienna solve of this system has 0.59 MW of generation and no demand to meet. Do not use
this system for a study.

---

## Why so little translates

Four causes stop nearly all of the model. Each one is a gap in tz-oss-interop, and not a
limit of Sienna. Cause 1 blocks each value that a dated data file supplies. Cause 2 sets no
snapshots, so no data file gives a time series.

### 1. The translator cannot read a dated value in a data file

65 of the data files in this package use one layout. Each row gives one object, one date and
the value that holds from that date:

```
NAME,YEAR,MONTH,DAY,VALUE
LOS_CONDORES,2026,9,1,150.00
LA_MINA,2026,9,1,36.73
```

The source does not read this layout. It writes one warning for each file, such as
`plexos: deferring Data File with unsupported layout: Gen_MaxCapacity.csv`. Then the
translator has no value for the property.

The layout carries the core data of the model:

| What it carries | Data files |
| --- | --- |
| The capacity, rating, outages, costs and heat rate of each generator | `Gen_MaxCapacity.csv`, `Gen_Rating.csv`, `Gen_UnitsOut.csv`, `Gen_OutageRating.csv`, `Gen_FuelCost.csv`, `Gen_HeatRate.csv`, `Gen_VOMCharge.csv` |
| The power, energy, efficiency and state of charge of each battery | `Bat_MaxPower.csv`, `Bat_Capacity.csv`, `Bat_ChargeEfficiency.csv`, `Bat_MinSOC.csv` and 23 more |
| The rating and impedance of each line | `Lin_MaxRating.csv`, `Lin_MinRating.csv`, `Lin_Reactance.csv`, `Lin_Resistance.csv`, `Lin_UnitsOut.csv` |
| The volume limits of each reservoir | `Sto_MaxVolume.csv`, `Sto_MinVolume.csv`, `Sto_InitialVolume.csv` |
| The flow limits of each waterway | `Wat_MaxFlow.csv`, `Wat_MinFlow.csv` |

`Params/Gen_StartCost.csv`, `Params/Gen_ShutDownCost.csv` and `Gas_Inflow.csv` add a
`PERIOD` column to the same layout.

A dated value in a data file means the same thing as a dated `t_data` row in the XML file.
The source already reads a dated `t_data` row in
`interop/plugins/sources/plexos_dated_properties.py`. It takes the value in force when the
window opens, and the steps inside the window. So the new code reads the CSV rows into that
same form.

**Size:** a new layout reader in `plexos_csv_layouts.py` that hands its rows to
`plexos_dated_properties.py`. About 150 to 250 lines in two or three files, and four BDD
scenarios. About one hour for a coding agent.

### 2. The horizon steps in weeks, and the translator reads only days

The model `PRGMEN_Base` uses the horizon `Coordinador_mensual`. That horizon states
`Chrono Step Type` 3 and `Chrono Step Count` 53. The source reads only step type 2, a day.
For any other step type, it writes this warning and sets no snapshots:

```
plexos: horizon step type 3 is not a day chronology; snapshots not set
```

With no snapshots, no profile can stage. So even a data file in a layout that the source
reads gives no time series.

53 steps of a week cover about one year, which agrees with a 12-month programme. PLEXOS
documentation is not in this repository, so this page does not state the code of a week as a
fact.

The horizon also states `Chrono Date From` 45047, which is 2023-05-01. The data files start
on 2026-09-01. The `source.horizon_year` override chooses the year that the translator reads,
so this difference does not stop the run.

**Size:** `plexos_horizon.py` maps each step type to a step length. About 30 to 60 lines in
one file, and two BDD scenarios. About 20 minutes.

### 3. The translator makes a load only from a `Region` or a `Node`

This model states its demand on 420 objects of the PLEXOS `Load` class. Each object joins one
`Node` through the `Load.Node` collection and states one `Load` property. The objects come in
threes on 140 nodes, with the suffixes `_R`, `_L` and `_LD`, such as `Coronel066_R`.

The translator reads demand only from a `Load` property on a `Region` or on a `Node`. It
does not read the `Load` class. It also does not translate a region load when the region
holds more than one node. This model has two regions over 241 nodes. So the Sienna system
holds no `PowerLoad`, and `decisions.md` holds no row that says so.

Sienna has a home: a `PowerLoad` names its `bus`. One `PowerLoad` for each `Load` object, on
the bus of its node, keeps the demand at the node where the model states it.

The `Load` property reads `Load_Load.csv`, in the timeslice layout of
[cause 4](#4-the-translator-cannot-read-a-value-by-timeslice-pattern). So a `PowerLoad`
needs cause 4 for its profile.

**Size:** a new mapping from the `Load` class to `PowerLoad` in
`plexos_sienna_translations/_loads.py`, beside the region load. About 150 to 250 lines in two
files, and three BDD scenarios. About 45 minutes, after cause 4.

### 4. The translator cannot read a value by timeslice pattern

Two important data files give one value for each object and each pattern:

```
NAME,PATTERN,VALUE
Coronel066_R,"DO_01,H1",35.61602
JUNCALITO,"M1,H1",0
```

| Data file | Rows | What it carries | The patterns |
| --- | --- | --- | --- |
| `Load_Load.csv` | 483,840 | The demand of each of the 420 `Load` objects | 48 named day types, each with the hours `H1` to `H24` |
| `Gen_RatingFactor.csv` | 298,944 | The available share of 1,038 generators, such as solar and wind | 288 patterns, `M1,H1` to `M12,H24`: a month and an hour |

A pattern such as `M1,H1` names a month and an hour of the day. A pattern such as `DO_01,H1`
names a `Timeslice` object and an hour. `Load_TimeSlice.csv` says which day belongs to which
`Timeslice`. It gives one row for each day from 2026-09-01 to 2027-09-27. It gives one column
for each of the 48 day types: `DO`, `LU`, `SA` and `TR`, each with a number from `01` to `12`.

So the translator can build an hourly series for each snapshot. It finds the day type of the
date, then reads the value for that day type and that hour.

Add the 420 loads in each of the 1,152 pattern slots. The mean of those totals is about
8,987 MW, before the growth factors. `Load_Escalator.csv` gives a weekly growth factor for each
of the three load groups, which three `Variable` objects read.

**Size:** a new pattern reader that expands a month or `Timeslice` pattern onto the
snapshots, and reads the `Timeslice` `Include` file. About 250 to 400 lines in a new source
module and `plexos_csv_layouts.py`, and five BDD scenarios. About one and a half hours.

---

## The other gaps that tz-oss-interop can close

Sienna has a home for each row below, and the translator does not write it yet. The Sienna
types come from `power-openapi-models` 0.2.0, the SiennaSchemas 0.2 package.

| What the model states | The Sienna home | Seen in this model | Size |
| --- | --- | --- | --- |
| The hydro cascade: 161 `Storage` objects, 564 generators that name a head storage, and 206 `Waterway` objects | `HydroReservoir`, with `upstream_reservoirs`, `upstream_turbines` and `downstream_turbines`, and `HydroTurbine` | 161, 564 and 206 objects | A new hydro module. About 500 to 800 lines, and eight BDD scenarios. About three hours. |
| The combined-cycle plants, stated as one generator for each operating mode, such as `ATA_CC1_TGA_GNL` | `CombinedCycleBlock` and `CombinedCycleAssociation` | 59 units in `Thermal Gen X` | Not sized. This page did not find how the model joins the modes of one plant. |
| `Zone`, which groups the nodes | `LoadZone`, which `ACBus.load_zone` names | 16 zones over 241 nodes | About 80 to 120 lines, and two BDD scenarios. About 30 minutes. |
| `Reserve`, with its contributors | `OnlineReserve` and `ServiceAssociation` | 13 reserves, and 3,633 generator memberships | About 300 lines, and four BDD scenarios. About one and a half hours. |
| `Forced Outage Rate` and `Mean Time to Repair` | `GeometricDistributionForcedOutage` | 1,427 generators and 130 batteries | About 150 lines, and two BDD scenarios. About 45 minutes. |
| `Units Out`, which takes units out on dates | `PlannedOutage` | 1,935 generators, 130 batteries and 340 lines | About 150 lines, and two BDD scenarios. About 45 minutes, after cause 1. |

The `Reserve` row is already a known gap. Refer to the
[gap analysis](../translation_mappings/plexos-to-sienna-gap-analysis.md#a-worked-example-of-the-difference).

## The gaps that Sienna has no home for

The [gap analysis](../translation_mappings/plexos-to-sienna-gap-analysis.md) already holds
most of these rows, from three other models. This model also states them:

| What the model states | Seen in this model | The row in the gap analysis |
| --- | --- | --- |
| `Constraint` | 509 objects | [The object level, for a dispatch](../translation_mappings/plexos-to-sienna-gap-analysis.md#the-object-level-for-a-dispatch) |
| `Decision Variable` | 46 objects | The same section |
| `Timeslice` | 101 objects | The same section. Cause 4 above expands the patterns into series, so the values can still reach Sienna. |
| `Company` | 143 objects | The same section |
| The run settings, such as `Horizon`, `MT Schedule`, `ST Schedule` and `Stochastic` | 9 `Model` objects | The same section |
| `Unit Commitment Optimality` | 2,793 rows on generators, 288 rows on batteries | [On a `Generator`](../translation_mappings/plexos-to-sienna-gap-analysis.md#on-a-generator) |
| `Max Cycles Day` on a `Battery` | 130 rows | [On a `Storage` or a `Battery`](../translation_mappings/plexos-to-sienna-gap-analysis.md#on-a-storage-or-a-battery) |
| `Balance Period` on a `Storage` | 88 rows | The same section |
| `Mutually Exclusive` on a `Reserve` | 12 rows | [On a `Reserve`](../translation_mappings/plexos-to-sienna-gap-analysis.md#on-a-reserve) |
| `Max Flow Penalty` on a `Waterway` | 373 rows | [On a `Waterway`](../translation_mappings/plexos-to-sienna-gap-analysis.md#on-a-waterway) |
| `Load Metering Point` on a `Region` | 2 rows | [On a `Region` or a `Node`](../translation_mappings/plexos-to-sienna-gap-analysis.md#on-a-region-or-a-node) |

The rows below are not in the gap analysis. The evidence is a search of the field names in
the `core`, `operations` and `investments` modules of `power-openapi-models` 0.2.0. Those
modules hold 481 distinct field names.

| What the model states | Why Sienna has no home | Seen in this model |
| --- | --- | --- |
| `Aux Base` on a `Generator`. The fixed auxiliary load of a unit while it runs. | No field name holds `aux`. The gap analysis already lists `Aux Incr`, the auxiliary load for each MW. | 707 rows |
| `Max Capacity Factor Day` on a `Generator`. A limit on the share of a day that a unit may run at. | No field name holds `day`. The nearest limit, `energy_import_weekly_limit`, applies to an import cost alone. | 128 rows on 117 generators |
| `Capacity Degradation`, `Power Degradation` and `Initial Age` on a `Battery`. How a battery loses energy and power as it ages. | No field name holds `degrad`, and `EnergyReservoirStorage` states no age. | 130 rows each |
| `Min Flow Penalty` on a `Waterway`. What it costs to send less water down a route than the route needs. | No type prices a flow below a limit on the route between two reservoirs. This is the same evidence as the `Max Flow Penalty` row. | 192 rows |
| `Non-physical Inflow Penalty`, `Non-physical Spill Penalty` and `Target Penalty` on a `Storage`. Penalties that a PLEXOS solve charges. | These tune a solve, and are not properties of the plant. A SiennaSchemas document states a system. | 14, 10 and 4 rows |

---

## Faults that this model found in the translator

These are defects, and not missing features.

| The fault | What a user sees | Size |
| --- | --- | --- |
| A line whose `Reactance`, `Resistance` or `Max Rating` comes from a data file takes the placeholder value of the XML file: 0 or 1e+30. | All 340 lines get `r` 0, `x` 0 and `rating` 1e+28. `decisions.md` records each as `VALUE_DERIVED`, so nothing tells the user that the numbers are wrong. A line with `x` 0 is not a valid DC power flow branch. | About 40 to 80 lines, and two BDD scenarios. The line must drop the value and record it, as a generator does now. About 30 minutes. |
| The drop warnings name one component each. | The run writes 2,091 warnings, one for each unit. The rule is one warning that names three components and counts the rest. | About 20 to 40 lines in `plexos_pypsa_translations/decisions.py`. About 15 minutes. |
| The source finds a data file only when the letter case of its name agrees. | The XML file names `Res_Timeslice.csv`, and the package holds `Res_TimeSlice.csv`. On Linux, the source leaves the file out and writes a warning. A Windows file system ignores letter case, so PLEXOS on Windows finds the file. | About 20 lines in `stage_plexos_xml.py`, and one BDD scenario. About 15 minutes. |
| A reserve stopped the run when the model stated a property on a class that `PlexosClass` does not list, such as `Load`. | `translate failed: conversion from str to enum failed in column 'child_class'`, with Polars 1.44.1. Issue #142 reported it, and PR #174 fixes it. | Done in PR #174 |

## What this page does not cover

- **No solve.** The system holds no demand and only 0.59 MW of generation, so a solve tells
  you nothing.
  This page will give a solve and a comparison when causes 1 to 4 are closed.
- **One model of nine.** The `RP_base4s` models use other horizons and more scenarios. They
  can find more gaps.
- **No reference data.** CEN publishes a report in `po12meses_sep26.zip`. A comparison against
  the report needs the translation first.
