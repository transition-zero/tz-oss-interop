# AEMO 2024 ISP

## The model

The Australian Energy Market Operator makes the Integrated System Plan. This plan covers
twenty-eight years of the National Electricity Market. AEMO publishes the PLEXOS models
for the plan.

The plan has three scenarios: Step Change, Progressive Change and Green Energy Exports.
Each scenario is a different model. The scenarios have different rates of demand growth
and different dates for the shutdown of the coal generators.

The time series make this model a good test. Each model has half-hourly traces for a full
financial year, for twelve sub-regions.

## Get the input

Download the files from the
[AEMO 2024 Integrated System Plan page](https://www.aemo.com.au/energy-systems/major-publications/integrated-system-plan-isp/2024-integrated-system-plan-isp).

One archive contains all three scenarios. Three more archives contain the wind traces, the
solar traces and the timeslice traces. All three scenarios use the same traces.

| Archive | Contents |
| --- | --- |
| [2024 ISP Model](https://www.aemo.com.au/-/media/files/major-publications/isp/2024/supporting-materials/2024-isp-model.zip?la=en) | One folder for each scenario. Each folder has the PLEXOS XML file for that scenario, and its demand traces, hydro traces and load subtractor traces. |
| [2024 ISP Solar traces](https://www.aemo.com.au/-/media/files/major-publications/isp/2024/supporting-materials/2024-isp-solar-traces.zip?la=en) | The solar generation traces. All three scenarios use them. |
| [2024 ISP Wind traces](https://www.aemo.com.au/-/media/files/major-publications/isp/2024/supporting-materials/2024-isp-wind-traces.zip?la=en) | The wind generation traces. All three scenarios use them. |
| [2024 ISP Timeslice traces](https://www.aemo.com.au/-/media/files/major-publications/isp/2024/supporting-materials/2024-isp-timeslice-traces.zip?la=en) | The timeslice specifications. All three scenarios use them. |

Download the four archives with a browser. The AEMO content delivery network sends the
error 403 to a command-line program, even if that program sends the headers of a browser.

Unpack the model archive first. It gives one folder for each scenario. Each of these
folders has a `Traces/` folder that contains the `demand` folder, the `hydro` folder and
the `load_subtractor` folder.

Then unpack the three trace archives. Copy the `solar` folder, the `wind` folder and the
`timeslice` folder into the `Traces/` folder of each scenario. Each scenario must then have
all six folders.

| Scenario | File | SHA-256 of the XML file |
| --- | --- | --- |
| Step Change | `2024 ISP Step Change Model.xml` | `afb6473dace48f378a02e6a82832827bdc400aa9d7c18fe67889067909513c01` |
| Progressive Change | `2024 ISP Progressive Change Model.xml` | `379e20409d66d7e78f0b1511d7c52b6efb0c0e7c1c2f63c171fa3c529257c0b7` |
| Green Energy Exports | `2024 ISP Green Energy Exports Model.xml` | `d99ba7754627def9149aaa566f5df937d7c5b9d513155642824a5154dbc3830f` |

Each XML file is approximately 29 MB. Each scenario increases to approximately 1.8 GB when
it has its own copy of the traces. Put the three scenario folders in
`case_study_inputs/aemo-isp-2024/`.

To make sure that you have the correct XML file, do this command:

```bash
shasum -a 256 "case_study_inputs/aemo-isp-2024/2024 ISP Step Change Model.xml"
```

## Translate and solve

If you did not install interop, install it now. Refer to
[Install](../../README.md#install).

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
| the PLEXOS `<MasterDataSet>` input XML | `case_study_inputs/aemo-isp-2024/2024 ISP Step Change Model.xml` |
| which PLEXOS Model to translate | `Step Change` |
| a four-digit year such as 2026 | Leave empty. Then the snapshots are the chronology of the Model. |
| Output | `outputs/isp-step-change.nc` |
| the extensions sidecar | `outputs/extensions.json` |

The XML file of each scenario contains one PLEXOS Model. The name of that Model is the name
of the scenario. Thus you must give `Step Change`, `Progressive Change` or
`Green Energy Exports` at the Model prompt. Give the name that agrees with the XML file
that you selected.

Do not leave the Model prompt empty. The Model applies the overlays of the scenario, and
the Horizon of the Model gives the snapshots to the network. If you give no Model, the
network gets no snapshots.

The chronology of each Model is 2024-07-01 to 2025-06-30. This period is the first
financial year of the twenty-eight year horizon.

Then select `solve`. Give the model type `pypsa` and the network
`outputs/isp-step-change.nc`. Select an output directory. Give the start date `2025-01-01`
and the end date `2025-01-31`. Give the unit commitment `linearised`. Keep the default
window and the default look-ahead. For more data about these prompts, refer to
[the solve tutorial](../tutorials/solve.md#pypsa-path).

### The Sienna path

The same model also translates to a Sienna system, which is what a partner running
PowerSimulations.jl needs. That translation is a run of its own, with its own mappings file.
This section covers the Step Change scenario. The other two follow the same steps.

Write `inputs/plexos_user_mappings.yaml` in PLEXOS words. This model has 63 Fuel objects,
each named for a power station, and 54 generator categories, so the file is long.
[The mapping document](../translation_mappings/translation-from-plexos-to-sienna.md#the-carrier-mappings-file)
states the shape of a row.

Name only the categories that are power plants. The categories `2023 REZ NSW`,
`Group REZ Augmentation`, `REZ Augmentation`, `New Entrants NSW`, `LTESA Projects`,
`Policy Projects` and `VRET Projects` and their siblings are transmission augmentations and
project placeholders, not plants. Leave them out of your file and the run leaves those 170
generators out, naming each one in `decisions.md`.

Select `translate`. Then give these answers:

| Prompt | Answer |
| --- | --- |
| Source framework | `plexos` |
| Destination framework | `sienna` |
| Pipeline | `plexos-to-sienna` |
| User mappings file | `inputs/plexos_user_mappings.yaml` |
| the PLEXOS `<MasterDataSet>` input XML | `case_study_inputs/aemo-isp-2024/2024 ISP Step Change Model.xml` |
| which PLEXOS Model to translate | `Step Change` |
| a four-digit year such as 2026 | `2025` |
| the SiennaSchemas system.json | `outputs/system.json` |

Give the year `2025` here, unlike the PyPSA run above, which leaves the year empty. The
chronology of the Model is 2024-07-01 to 2025-06-30, so the year 2025 narrows it to
2025-01-01 to 2025-06-30, which is 8,688 half-hourly snapshots. The Sienna solve takes no
date range, so it covers every snapshot in the system, and the year prompt is the only way to
give it a shorter window. Six months already makes a large program; refer to
[What it costs](#what-it-costs).

That run writes three files: `outputs/system.json`, its HDF5 companion
`outputs/system_time_series_storage.h5`, and `outputs/extensions.json`. Those three files
are the product. The system holds 12 `ACBus`, 5 `Area`, 12 `PowerLoad`, 252
`ThermalStandard`, 240 `RenewableDispatch`, 158 `EnergyReservoirStorage` and 16
`TwoTerminalGenericHVDCLine` components.

To prove that the system dispatches, run `translate` a second time over those three files:

| Prompt | Answer |
| --- | --- |
| Source framework | `sienna` |
| Destination framework | `power-simulations` |
| Pipeline | `sienna-to-power-simulations` |
| the SiennaSchemas system.json | `outputs/system.json` |
| the HDF5 time-series sidecar | `outputs/system_time_series_storage.h5` |
| the extensions sidecar | `outputs/extensions.json` |
| the PowerSystems.jl system.json | `outputs/power_simulations_system.json` |
| the HDF5 time-series sidecar | `outputs/power_simulations_system_time_series.h5` |

Then select `solve`. Give the model type `sienna` and the system
`outputs/power_simulations_system.json`. Give the network model `dcp`, the unit commitment
`linearised`, and the HiGHS defaults. Leave the time limit empty. For more data about these
prompts, refer to [the solve tutorial](../tutorials/solve.md#sienna-path).

## The headline number

**What you can check by yourself.** All three scenarios translate. All three solves give
the status `optimal` for January 2025. The translator writes a `decisions.md` file adjacent
to each network. That file gives each source field, the destination field for it, and each
component that the translator did not translate.

The Sienna path solves the Step Change scenario over the first half of 2025 as a linear
program. HiGHS reports the model status `Optimal` with the objective 2.64408 × 10⁹, with the
network model `dcp` and the unit commitment `linearised`. Three runs gave that objective.

The run reports the run status `SUCCESSFULLY_FINALIZED` and writes the result tables to
`outputs/solved/results` and `outputs/solved/results_wide`. Each variable, auxiliary
variable, dual, parameter and expression gets one CSV file.

The PyPSA numbers below cover January 2025 and the Sienna number covers January to June
2025, so the two do not compare.

| Scenario | Status | Objective | Demand in the month | Generation |
| --- | --- | --- | --- | --- |
| Step Change | optimal | 4.74465 × 10⁸ | 15.763 TWh | 15.764 TWh |
| Progressive Change | optimal | 4.74905 × 10⁸ | 15.724 TWh | 15.724 TWh |
| Green Energy Exports | optimal | 4.96785 × 10⁸ | 16.257 TWh | 16.257 TWh |

In each scenario, the generation agrees with the demand to within 0.01%.

**What we measured.** The translation keeps the demand exactly. There is no error in any of
the 210,240 half-hourly values, in all three scenarios.

We measured this value on 2026-08-18, on branch `caiso-compare-dataset-v2`, at interop
version 0.1.0.
The software that makes this comparison is not in this repository. Thus you cannot do this
comparison again from this repository. But you can do the solves above again.

We can find no AEMO publication that gives the ISP results as values. Thus you cannot
compare the dispatch or the price against a published value. The objectives above are
observations only. They are not a result of a comparison.

## What the number does not cover

The network covers the first year of a twenty-eight year horizon. The solve covers one
month of that year.

**The hydro fleet neither stores nor receives water.** Two limits combine, so do not use any
number from this case study that depends on hydro.

These models state a `Max Volume` in 1000 m³, which is water. The translator has no conversion
from cubic metres into MWh, so it leaves each of those volumes out. Thus 66 of the 184 storage
units take the PyPSA default of one hour, and those 66 hold 5,670 MW of the 7,569 MW. Water
blocks 64 of those 66.
`decisions.md` states the cause for each volume.

Also, the network carries no `inflow` series, so a hydro reservoir receives no water. Across
January the storage fleet discharges 0.127 TWh against its rating of 7,569 MW. That is 2.3% of
what the rating allows over the month. We do not know yet why no inflow reaches the network.

The demand result above does not depend on hydro, so it stands.

**The Sienna path has no hydro reservoir at all.** Every `Natural Inflow` in this model is in
cumec, which is water, and the energy budget a Sienna `HydroDispatch` is dispatched against
is its inflow. A unit with no budget would run at full output every snapshot, so the
translation leaves all 31 reservoir units out and names each one in `decisions.md`.
[The gap analysis](../translation_mappings/plexos-to-sienna-gap-analysis.md) lists every
other thing the Sienna path loses.

The Sienna path also keeps no reserves file at all, because the first leg of the chain writes
that file inside the run's scratch space. Run `plexos-to-pypsa` on its own if you want the
reserves.

A solve keeps no reserve headroom. Thus the dispatch is less constrained than the dispatch
in the source model.

The network has no load shedding resource. Thus you cannot measure the unserved energy. If
the capacity is less than the load, the window does not solve. The important result is that
all three scenarios solve.

## What it costs

The four archives are 655 MB in total: 183 MB for the model archive, 173 MB for the solar
traces, 299 MB for the wind traces and 12 KB for the timeslice traces. You download these
archives one time only. The quantity of scenarios that you use does not change the download
size.

Each scenario is approximately 1.8 GB on disk after you unpack it and copy the traces into
it. Thus the three scenarios together are approximately 5.4 GB on disk.

The Sienna path takes more compute than the PyPSA path, because the Sienna solve takes no
date range and therefore covers the whole six months in one program. The solve uses the
network model `dcp`. Use `copperplate` for a faster answer that ignores the line flows.

The result tables are 440 MB on disk. The solve also writes `problem_results.bin`, which is
330 MB.
