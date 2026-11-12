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

The XML file holds nine `Model` objects. This page translates `MT_base4s`. Its horizon,
`RP-56w`, starts on 2026-09-01 and runs 56 weeks, which is the period of the programme.

Do not translate `PRGMEN_Base` for this period. Its horizon, `Coordinador_mensual`, starts on
2023-05-01, and the data files start on 2026-09-01.

**What is left out is what Sienna has no home for.** Every class and property below that the
system does not hold is a thing that no SiennaSchemas 0.2 type or field can hold. Refer to
[What Sienna has no home for](#what-sienna-has-no-home-for).

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
  --override 'source.model=MT_base4s' \
  --override 'sink[0].output_system_json_file_path=outputs/system.json' \
  --user-mappings-path inputs/plexos_user_mappings.yaml
```

Give no `source.horizon_year`. Then the window is the whole horizon, from 2026-09-01, and
each dated value is the one in force on that day.

To see the warnings on the console, set `INTEROP_LOG_LEVEL=INFO`.

The run takes about 5 minutes. It writes `outputs/system.json`, the time series store,
`outputs/extensions.json`, `outputs/storage.parquet` and `decisions.md`, 44 MB in all.

## What the translation writes

| What the model states | What the Sienna system holds |
| --- | --- |
| 241 `Node` objects | 241 `ACBus` |
| 2 `Region` objects | 2 `Area` |
| 16 `Zone` objects | 16 `LoadZone`, which each bus names |
| 340 `Line` objects | 340 `Line`. 339 state a reactance, and one states none. |
| 420 `Load` objects | 420 `PowerLoad`, with a peak of 14,093 MW in all |
| 766 thermal `Generator` objects | 766 `ThermalStandard` |
| 1,170 solar, wind and hydro `Generator` objects with no head `Storage` | 1,169 `RenewableDispatch`. One unit states a capacity of 0 MW. |
| 58 hydro `Generator` objects with a head `Storage` | 58 `HydroTurbine`, 5,636 MW in all |
| 161 `Storage` objects | 67 `HydroReservoir`. The other 94 are below. |
| 206 `Waterway` objects | The routes between the reservoirs, as `upstream_reservoirs` |
| 144 `Battery` objects | 144 `EnergyReservoirStorage` |
| 13 `Reserve` objects | 3 `OnlineReserve`, with 1,192 service associations. All 13 reach `extensions.json`. |
| The data files | 1,840 time series |

The numbers come from tz-oss-interop with pull request #176, and Polars 2.0.0.

### The PLEXOS rules that the translation applies

The translator applies the rules below. Each one is a general rule of PLEXOS, and not a rule
of this model.

| The rule | What it gave this model |
| --- | --- |
| A data file header reads without letter case. | The files headed `NAME`, `YEAR` and `VALUE` stage. |
| A file headed `Name`, `Year`, `Month`, `Day` and `Value` gives dated property values. | Every capacity, rating, cost, heat rate and line impedance |
| A chronology step type of 3 is a week. | The snapshots of the horizon |
| A value by pattern expands onto the snapshots, with the whole PLEXOS timeslice grammar. | The demand and the rating factors |
| A `Load` object becomes a `PowerLoad` on the bus of its node. | The 420 loads |
| A `Variable` that a property row names escalates the row's data file values. | The demand growth factors of `Load_Escalator.csv` |
| A data file row matches its object without letter case, and by the `Variable` it reads through. | The rows of `Var_StoInitialVolume.csv`, and four lines such as `Ohiggins220_Farellon220` |
| A membership property's row is named after both of its objects, in either order. | The reserve response limits and the constraint coefficients |
| A generator that states `Units Out` takes its outage from `Units Out` alone. | 102 thermal units that the old rule gave a ceiling of 0 |
| A thermal unit that draws on a `Storage` stays thermal, and the `Storage` is a fuel store. | 506 gas units that were turbines before |
| A unit pumps only when it states a `Pump Load` above 0 MW. A unit with a head and a tail `Storage` and no `Pump Load` is a turbine. | The model states no `Pump Load`, so its 41 units with a head and a tail are turbines. |
| A unit written `m³` is the same unit as `m3`. | The `Efficiency Incr` of the 58 turbines, in `MW/m³/s`, gives their `conversion_factor`. |
| Every `Storage` of a cascade is a reservoir. | 67 reservoirs, joined by their turbines and routes |

### No forced outage in `MT_base4s`

The model states its `Forced Outage Rate` and `Mean Time to Repair` only in the scenarios
`ForcedOutage` and `ForcedOutageGN`. `MT_base4s` reads neither, so the system holds no
`GeometricDistributionForcedOutage`. The `RP_base4s` models read them.

---

## What Sienna has no home for

Each row below is a thing the model states that no SiennaSchemas 0.2 type or field can hold.
The evidence is the `power-openapi-models` 0.2.0 package. Its `core`, `operations` and
`investments` modules hold 481 distinct field names.

The [gap analysis](../translation_mappings/plexos-to-sienna-gap-analysis.md) gives the
evidence for the rows that it already holds, from three other models.

### The object level

| What the model states | Why Sienna has no home | Seen in this model |
| --- | --- | --- |
| `Constraint` | Refer to [the gap analysis](../translation_mappings/plexos-to-sienna-gap-analysis.md#the-object-level-for-a-dispatch). 441 of them reach `extensions.json`. [The custom constraints of the CEN model](cen-po12meses-2026-09-constraints.md) classifies each one. | 509 objects |
| `Decision Variable` | The same section of the gap analysis | 46 objects |
| `Timeslice` | The same section. The values that a pattern gives against a `Timeslice` do reach the system, as time series. | 101 objects |
| `Company` | The same section | 143 objects |
| The run settings: `Horizon`, `MT Schedule`, `ST Schedule`, `Stochastic` and the others | The same section | 9 `Model` objects |
| A fuel store: a `Storage` that only thermal units draw on, such as a tank of liquefied gas | No type holds a stock of fuel. The fields that name a fuel are `fuel`, `fuel_cost`, `fuel_cost_time_series`, `start_fuel_mmbtu_per_mw` and `startup_fuel_offtake`, and each one is a type or a price. | 83 `Storage` objects |
| A `Storage` that no turbine draws on and no `Waterway` joins to a cascade | A `HydroReservoir` holds water that a turbine or a route uses. This `Storage` takes part in neither. | 11 `Storage` objects |

### The combined-cycle plants

The model states each operating mode and each fuel of a combined-cycle plant as a
`Generator` of its own. Eight of them, `KELAR-TG1+TG2+TV_GN_A` to `KELAR-TG1+TG2+TV_GNL_D`,
state 521.71 MW each. Every `KELAR` mode takes part in 11 to 18 `Constraint` objects, which
join the modes of the plant. Sienna holds no `Constraint`, so nothing stops two modes of one
plant from running at once. The 766 `ThermalStandard` units therefore state 120,042 MW in all,
which counts each mode of a plant as a plant of its own.

The units of 0.01 MW in the category `Thermal Gen X` take part in the same constraints.
Sienna has a `CombinedCycleBlock` type, but PLEXOS states no plant that a block can name. The
plant exists only in the `Constraint` objects.

### On a `Generator`

| What the model states | Why Sienna has no home | Seen in this model |
| --- | --- | --- |
| `Unit Commitment Optimality` | Refer to [On a `Generator`](../translation_mappings/plexos-to-sienna-gap-analysis.md#on-a-generator) | 2,793 rows |
| `Aux Base`. The fixed auxiliary load of a unit while it runs. | No field name holds `aux`. The gap analysis already holds `Aux Incr`. | 707 rows |
| `Max Capacity Factor Day`. A limit on the share of a day that a unit may run at. | No field name holds `day`. The nearest limit, `energy_import_weekly_limit`, applies to an import cost alone. | 128 rows on 117 units |

### On a `Battery` or a `Storage`

| What the model states | Why Sienna has no home | Seen in this model |
| --- | --- | --- |
| `Max Cycles Day` on a `Battery` | Refer to [On a `Storage` or a `Battery`](../translation_mappings/plexos-to-sienna-gap-analysis.md#on-a-storage-or-a-battery) | 130 rows |
| `Capacity Degradation`, `Power Degradation` and `Initial Age` on a `Battery` | No field name holds `degrad`, and `EnergyReservoirStorage` states no age. | 130 rows each |
| `Unit Commitment Optimality` and `End Effects Method` on a `Battery` | These tune a solve, and are not properties of the plant. | 288 and 144 rows |
| `Balance Period` on a `Storage` | Refer to the same section of the gap analysis | 88 rows |
| `Non-physical Inflow Penalty`, `Non-physical Spill Penalty` and `Target Penalty` on a `Storage` | These are penalties that a PLEXOS solve charges. A SiennaSchemas document states a system. | 14, 10 and 4 rows |

### On a `Waterway`

A `Waterway` reaches the system as the link between two reservoirs, in
`upstream_reservoirs`. 128 routes name no `Storage To`, so they leave the cascade. In all,
135 routes link no two reservoirs that the system holds. The properties of a route have no
home.

| What the model states | Why Sienna has no home | Seen in this model |
| --- | --- | --- |
| `Max Flow Penalty` | Refer to [On a `Waterway`](../translation_mappings/plexos-to-sienna-gap-analysis.md#on-a-waterway) | 190 objects |
| `Max Flow`, `Min Flow` | No type states a route between two reservoirs. `spillage_limits` belongs to one reservoir, and `outflow_limits` to one turbine. | 200 and 191 objects |
| `Min Flow Penalty` | The same evidence as `Max Flow Penalty` | 185 objects |

### On a `Reserve`

| What the model states | Why Sienna has no home | Seen in this model |
| --- | --- | --- |
| `Mutually Exclusive` | Refer to [On a `Reserve`](../translation_mappings/plexos-to-sienna-gap-analysis.md#on-a-reserve) | 12 reserves |
| `Max Response` and `Max Charge Response` of one unit for one reserve | A unit joins a service through one `ServiceAssociation` row, which states the service and the unit and nothing more. `max_participation_factor` is one share for the whole service. | 3,631 rows on generators, and 56 and 56 on batteries |
| The requirement of the six reserves `CPF_LW_BESS` to `CTF_RS_BESS` | These reserves state no `Min Provision` above 0. Each one takes part in 15 to 40 `Constraint` objects, and Sienna holds no `Constraint`. So they become no service, and their records reach `extensions.json`. | 6 reserves |

### On a `Region`

| What the model states | Why Sienna has no home | Seen in this model |
| --- | --- | --- |
| `Load Metering Point` | Refer to [On a `Region` or a `Node`](../translation_mappings/plexos-to-sienna-gap-analysis.md#on-a-region-or-a-node) | 2 rows |

---

## What this page does not cover

- **No solve.** The combined-cycle modes can all run at once, so a solve overstates the
  thermal capacity. A solve needs the `Constraint` objects first.
- **One model of nine.** The `RP_base4s` models read the forced outage scenarios, and use
  horizons of 2-hour periods.
- **Four items that need a decision.** tz-oss-interop can hold each of them, but each one
  changes a contract or a solve. Until then, each is left out with a warning.
  - The model names `Res_Timeslice.csv`, and the package holds `Res_TimeSlice.csv`. On Linux
    the source cannot find it, so four reserves (`CSF_LW`, `CSF_RS`, `CTF_LW`, `CTF_RS`) read
    no requirement. A lookup that ignores letter case needs a way to list a folder, which is a
    new method on `FilesystemPort`, a published contract.
  - `VoRS` can become the demand curve of a reserve, `OnlineReserve.variable`. That makes the
    requirement a priced curve, not a hard limit, which changes what PowerSimulations solves.
  - The 2 `Flow Control` objects state the angle range of a phase shifter on a line. Sienna
    holds that in `TransformerCircuit.phase_angle_limits`, so the line would become a
    transformer.
  - The 2 `Region` objects state a `VoLL`. An `InterruptiblePowerLoad` at that price could
    hold it, but that adds a load shedding resource to the solve.
- **No reference data.** CEN publishes a report in `po12meses_sep26.zip`, and this page does
  not compare against it.
