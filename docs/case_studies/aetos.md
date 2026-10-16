# AETOS

## The model

AETOS (Africa–Europe Energy Transition OSeMOSYS) is an open-source OSeMOSYS model of 78
countries: 48 in Africa and 30 in Europe. It models electricity and natural gas, and the trade
of both between the countries. Its years are 2021 to 2055.

AETOS has one OSeMOSYS region, `REGION1`. Each technology name and each fuel name starts with
the two-letter code of its country, for example `DZNGCCPH1` and `DZE1`.

The size makes this model a good test of the canonical stage. The model has 224 CSV files, 3158
technologies and 804 fuels.

## Get the input

The authors publish AETOS version `v2.0.0` in two places: the
[GitHub tag `v2.0.0`](https://github.com/ekousoulos/AETOS-model/tree/v2.0.0) and the
[Zenodo record 18479411](https://doi.org/10.5281/zenodo.18479411). The model is licensed under
the MIT licence. Cite it as the AETOS `README.md` says.

The repository holds the model inputs, so you can clone the tag:

```sh
git clone --depth 1 --branch v2.0.0 https://github.com/ekousoulos/AETOS-model.git case_study_inputs/aetos
rm -rf case_study_inputs/aetos/.git
```

You can also download the archive from Zenodo:

```sh
curl -L -o /tmp/aetos-v2.0.0.zip "https://zenodo.org/records/18479411/files/ekousoulos/AETOS-model-v2.0.0.zip?download=1"
md5sum /tmp/aetos-v2.0.0.zip
```

The checksum must be `76bcfbe64fe92f36d7dffc2993f50a9f`. Extract the archive. Then move the
top-level directory of the archive to `case_study_inputs/aetos/`.

| | |
| --- | --- |
| Download size | 98.4 MB for the Zenodo archive |
| Size on disk | 444 MB, of which the CSV files are 40 MB |
| Put it in | `case_study_inputs/aetos/` |

Do not change the directory layout of the publisher. The run reads two paths in
`case_study_inputs/aetos/AETOS_Runner/`:

- `config_otoole_AETOS.yaml` is the otoole configuration.
- `CSVFiles/` holds one CSV file for each OSeMOSYS set and parameter.

## The mappings file

Make a project in the repository root. The command of tz-oss-interop is `interop`:

```bash
uv run interop
```

Select `init`. Then give these answers:

| Prompt | Answer |
| --- | --- |
| `Target directory?` | `aetos` |
| `Scaffold an example?` | `none` |

Then copy this text into `aetos/inputs/aetos_mappings.yaml`:

```yaml
osemosys:
  units: {capacity: GW, energy: PJ, currency: million USD, currency_year: 2021, emissions: Mt}
  objects:
    fuels:
      - match: "^(?P<country>[A-Z]{2})E[123]$"
        carrier: electricity
        location: "{country}"
      - match: "^(?P<country>[A-Z]{2})NG$"
        carrier: natural-gas
        location: "{country}"
    technologies:
      - {match: "^[A-Z]{2}NGCC", category: gas-combined-cycle}
      - {match: "^[A-Z]{2}NG(GC|HPF)", category: gas-turbine}
      - {match: "^[A-Z]{2}NG(CHP|STP)", category: gas-steam}
      - {match: "^[A-Z]{2}(CO|LI)", category: coal}
      - {match: "^[A-Z]{2}NU", category: nuclear}
      - {match: "^[A-Z]{2}(BM|BF)", category: biomass}
      - {match: "^[A-Z]{2}WS", category: waste}
      - {match: "^[A-Z]{2}(DS|LF)", category: oil-engine}
      - {match: "^[A-Z]{2}HF", category: oil-steam}
      - {match: "^[A-Z]{2}(DG|RG)", category: other-gas}
      - {match: "^[A-Z]{2}GO", category: geothermal}
      - {match: "^[A-Z]{2}HYD[MR]", category: hydro}
      - {match: "^[A-Z]{2}SOST", category: solar-thermal}
      - {match: "^[A-Z]{2}SO", category: solar}
      - {match: "^[A-Z]{2}WI(ON|ND)", category: wind-onshore}
      - {match: "^[A-Z]{2}WIOF", category: wind-offshore}
      - {match: "^[A-Z]{2}(TID|OCWV)", category: marine}
      - {match: "^[A-Z]{2}BACKSTOP$", category: backstop}
      - {match: "^[A-Z]{2}HYDS", category: pumped-storage}
      - {match: "^[A-Z]{2}BATT", category: battery}
carriers:
  - {osemosys_category: gas-combined-cycle, sienna_component_type: ThermalStandard, sienna_fuel_type: NATURAL_GAS, sienna_prime_mover_type: CC}
  - {osemosys_category: gas-turbine, sienna_component_type: ThermalStandard, sienna_fuel_type: NATURAL_GAS, sienna_prime_mover_type: GT}
  - {osemosys_category: gas-steam, sienna_component_type: ThermalStandard, sienna_fuel_type: NATURAL_GAS, sienna_prime_mover_type: ST}
  - {osemosys_category: coal, sienna_component_type: ThermalStandard, sienna_fuel_type: COAL, sienna_prime_mover_type: ST}
  - {osemosys_category: nuclear, sienna_component_type: ThermalStandard, sienna_fuel_type: NUCLEAR, sienna_prime_mover_type: ST}
  - {osemosys_category: biomass, sienna_component_type: ThermalStandard, sienna_fuel_type: OTHER_BIOMASS_SOLIDS, sienna_prime_mover_type: ST}
  - {osemosys_category: waste, sienna_component_type: ThermalStandard, sienna_fuel_type: MUNICIPAL_WASTE, sienna_prime_mover_type: ST}
  - {osemosys_category: oil-engine, sienna_component_type: ThermalStandard, sienna_fuel_type: DISTILLATE_FUEL_OIL, sienna_prime_mover_type: IC}
  - {osemosys_category: oil-steam, sienna_component_type: ThermalStandard, sienna_fuel_type: RESIDUAL_FUEL_OIL, sienna_prime_mover_type: ST}
  - {osemosys_category: other-gas, sienna_component_type: ThermalStandard, sienna_fuel_type: OTHER_GAS, sienna_prime_mover_type: GT}
  - {osemosys_category: geothermal, sienna_component_type: ThermalStandard, sienna_fuel_type: GEOTHERMAL, sienna_prime_mover_type: BT}
  - {osemosys_category: backstop, sienna_component_type: ThermalStandard, sienna_fuel_type: OTHER, sienna_prime_mover_type: OT}
  - {osemosys_category: hydro, sienna_component_type: HydroDispatch, sienna_prime_mover_type: HY}
  - {osemosys_category: solar, sienna_component_type: RenewableDispatch, sienna_prime_mover_type: PVe}
  - {osemosys_category: solar-thermal, sienna_component_type: RenewableDispatch, sienna_prime_mover_type: CP}
  - {osemosys_category: wind-onshore, sienna_component_type: RenewableDispatch, sienna_prime_mover_type: WT}
  - {osemosys_category: wind-offshore, sienna_component_type: RenewableDispatch, sienna_prime_mover_type: WS}
  - {osemosys_category: marine, sienna_component_type: RenewableDispatch, sienna_prime_mover_type: OT}
  - {osemosys_category: pumped-storage, sienna_component_type: EnergyReservoirStorage, sienna_prime_mover_type: PS}
  - {osemosys_category: battery, sienna_component_type: EnergyReservoirStorage, sienna_prime_mover_type: BA}
```

The file has three parts:

- `units:` gives the units of the values.
- `objects:` gives each fuel a carrier and a location, and each technology a category.
- `carriers:` gives each category its Sienna type.

The [OSeMOSYS mappings tutorial](../tutorials/osemosys-mappings.md) teaches `units:` and
`objects:`.
[The carrier mappings file](../translation_mappings/translation-from-osemosys-to-sienna.md#the-carrier-mappings-file)
gives each field of a `carriers:` row.

### The units

The AETOS `README.md` gives GW for capacity, PJ for flows, MtCO₂ for emissions and 2021 USD for
costs. The cost values are in million USD, and not in USD. For example, the 2021 `CapitalCost`
of `DENGCCPH1` is 707.86. That value is 707.86 million USD for each GW, which is 707.86 USD for
each kW, a plausible cost for a combined-cycle gas plant.

With `currency: USD`, the translation reads 707.86 USD for each GW. Then each cost is one
million times too small, and every plant is almost free. With `currency: million USD`, the
2021 `EmissionsPenalty` of 66.19 for `ATCO2` becomes 66.19 USD for each tonne of CO2.

`currency_year: 2021` gives the cost year of the portfolio.

### The objects

The two `fuels:` rows give each electricity fuel and each natural gas fuel its carrier. They
give the country code as its location.

Each `technologies:` row gives a category to the technologies whose names agree with its
pattern. The pattern reads the technology code after the country code, for example `NGCC` in
`DENGCCPH1`. The first row that matches a technology wins. Thus the row for `SOST`, which is
solar thermal, must come before the row for `SO`, which is solar.

### The carriers

Each `carriers:` row gives one category a Sienna component type and a prime mover. A
`ThermalStandard` row also gives a fuel. Every thermal fuel of the model, and the backstop, is
a `ThermalStandard`.

The last two rows are for storage. `pumped-storage` and `battery` are categories of the
technology that discharges a storage. Their `EnergyReservoirStorage` rows give the storage its
type. A technology whose category has no row is left out, and `decisions.md` names it.

## Stage the model

Do this command in the `aetos` directory:

```bash
INTEROP_LOG_LEVEL=WARNING uv run interop headless_cli --pipeline osemosys-csv-to-canonical \
  --override 'source.config_path=../case_study_inputs/aetos/AETOS_Runner/config_otoole_AETOS.yaml' \
  --override 'source.csv_dir=../case_study_inputs/aetos/AETOS_Runner/CSVFiles' \
  --user-mappings-path inputs/aetos_mappings.yaml
```

The run writes the canonical stage to `outputs/canonical/`, and the console shows two warnings:

```
WARNING ... 159 raw table(s) match no canonical parameter by name and key, so each stays an extension table: ATReserveMarginTagTechnology, BEReserveMarginTagTechnology, BGReserveMarginTagTechnology and 156 more
WARNING ... no kind fits 213 technology(ies) in their region, so each keeps an empty kind: REGION1/DZSO00I00, REGION1/EGSO00I00, REGION1/EGWI00I00 and 210 more
```

## What the run gives

We did this run on 2026-10-13. A second run on 2026-10-16, with the mappings file above, gave
the same counts and the same two warnings.

| Part of the canonical stage | Count |
| --- | --- |
| Sets | 11 |
| Parameters | 54, with 1,024,108 rows in total |
| Extension tables | 159 |
| Technologies with a kind | 2945 of 3158 |
| Fuels with a carrier | 333 of 804: 248 electricity and 85 natural gas |

The canonical schema has no parameter with the name of an extension table, so each of these
tables stays as the model states it:

- 78 tables are `ReserveMarginTagTechnology`, split by country, for example
  `ATReserveMarginTagTechnology`.
- 78 tables are `YearlyPeak`, split by country, for example `YearlyPeakAT`.
- 3 tables are `StorageChargeDuration`, `StorageTag` and `TradeRoute`.

Of the 213 technologies with no kind, 132 are solar, wind and hydro plants. Their names end in
`SO00I00`, `WI00I00` and `HY00I00`. The other 81 are gas pipelines between two countries, for
example `ATNGDEPI0`. A technology with no kind has no Sienna component, even when a row in
`objects:` gives it a category.

## Translate the model into a Sienna system

We did each run from this section to the end on 2026-10-16, on the branch
`osemosys-to-sienna` of tz-oss-interop.

Start tz-oss-interop in the `aetos` directory:

```bash
cd aetos
uv run interop
```

Select `translate`. Then give these answers:

| Prompt | Answer |
| --- | --- |
| `Source framework?` | `osemosys` |
| `Destination framework?` | `sienna` |
| `Pipeline?` | `osemosys-csv-to-sienna` |
| `source.config_path` | `../case_study_inputs/aetos/AETOS_Runner/config_otoole_AETOS.yaml` |
| `source.csv_dir` | `../case_study_inputs/aetos/AETOS_Runner/CSVFiles` |
| `step[0].locations` | Leave it empty. |
| `step[0].years` | Leave it empty. |
| `step[1].year` | `2021` |
| `step[3].documents` | Keep the default, `operations`. |
| `sink[0].output_system_json_file_path` | `outputs/operations/system.json` |
| `sink[0].output_h5_file_path` | Leave it empty. |
| `sink[0].output_extensions_file_path` | Leave it empty. |
| `sink[0].indent` | Keep the default, `2`. |
| `User mappings file?` | `inputs/aetos_mappings.yaml` |

Each prompt of a parameter also gives a description of the parameter. An empty answer at a
companion prompt writes that file beside `system.json`.

The system holds the fleet of 2021, which is the first model year. The run writes three files
to `outputs/operations/`: `system.json`, `system_time_series_storage.h5` and
`extensions.json`. It writes `decisions.md` and `validation-report.md` to the `aetos`
directory. Move the two reports to `outputs/operations/` before the next run, because the next
run writes them again.

| Sienna type | Count |
| --- | --- |
| `ACBus` | 92 |
| `Area` | 92 |
| `PowerLoad` | 78 |
| `ThermalStandard` | 567 |
| `RenewableDispatch` | 132 |
| `HydroDispatch` | 89 |
| `EnergyReservoirStorage` | 26 |
| `TwoTerminalGenericHVDCLine` | 113 |
| `Arc` | 113 |

Each of the 78 countries has a bus and a load. The other 14 buses are countries outside the
model, for example `UA` and `TR`. A line reaches each of them.

The console shows 27 warnings. Each warning names three components at most. `decisions.md`
names each component and gives the reason. These warnings tell you the most:

- 1165 supply technologies have no residual capacity in 2021. Most of them are plants that the
  plan can build in a later year.
- 156 technologies convert one electricity fuel into another at one location. The system has no
  component for them.
- 495 technologies supply a fuel that is not electricity.
- 21 transport technologies state an operating mode that is not the flow back. Each one is an
  import from outside the model, and the line does not hold it.
- 14 warnings each name one parameter that no step applies, for example
  `total_technology_annual_activity_lower_limit` and `capital_cost`.

## Translate the model into a Sienna Investments Portfolio

Select `translate` again. Then give these answers:

| Prompt | Answer |
| --- | --- |
| `Source framework?` | `osemosys` |
| `Destination framework?` | `sienna` |
| `Pipeline?` | `osemosys-csv-to-sienna-investments` |
| `source.config_path` | `../case_study_inputs/aetos/AETOS_Runner/config_otoole_AETOS.yaml` |
| `source.csv_dir` | `../case_study_inputs/aetos/AETOS_Runner/CSVFiles` |
| `step[0].locations` | Leave it empty. |
| `step[0].years` | Leave it empty. |
| `step[1].year` | Keep the default, `earliest`. |
| `step[4].documents` | Keep the default, `investments`. |
| `sink[0].output_system_json_file_path` | `outputs/investments/system.json` |
| `sink[1].output_path` | `outputs/investments/portfolio.json` |
| `User mappings file?` | `inputs/aetos_mappings.yaml` |

Keep the default at every other prompt. Move `decisions.md` and `validation-report.md` to
`outputs/investments/`.

The run writes the three files of a Sienna system, `portfolio.json` and
`portfolio_time_series_storage.h5` to `outputs/investments/`. The portfolio covers every model
year, 2021 to 2055. Its discount rate is 0.075, which is the default of `DiscountRate` in the
otoole configuration. Its base year is 2021.

| Portfolio type | Count |
| --- | --- |
| `SupplyTechnology` | 1166 |
| `StorageTechnology` | 93 |
| `AggregateTransportTechnology` | 86 |
| `DemandRequirement` | 78 |
| Time series associations | 38,080 |

The console shows 21 warnings. One of them names 78 pollutants. Each country has its own CO2
pollutant, for example `ATCO2`, and an emission limit on it. A `CarbonCaps` limits the whole
portfolio, so it cannot hold a limit for one country. `extensions.json` holds each limit.

## Solve the dispatch

### Make the PowerSimulations.jl system

Select `translate`. Then give these answers:

| Prompt | Answer |
| --- | --- |
| `Source framework?` | `sienna` |
| `Destination framework?` | `power-simulations` |
| `Pipeline?` | `sienna-to-power-simulations` |
| `source.system_json_path` | `outputs/operations/system.json` |
| `source.time_series_h5_path` | `outputs/operations/system_time_series_storage.h5` |
| `source.extensions_json_path` | `outputs/operations/extensions.json` |
| `sink[0].system_json_filepath` | `outputs/power_simulations/system.json` |
| `sink[0].h5_output_path` | `outputs/power_simulations/system_time_series_storage.h5` |

Keep the default at the three prompts after them: `system_name`, `base_power` and `frequency`.
Move `decisions.md` and `validation-report.md` to `outputs/power_simulations/`.

### Solve the system

Select `solve`. Then give these answers:

| Prompt | Answer |
| --- | --- |
| `Model type?` | `sienna` |
| `Path to PowerSimulations.jl system JSON?` | `outputs/power_simulations/system.json` |
| `Network model?` | `copperplate` |
| `Unserved energy?` | `penalised` |
| `Unit commitment treatment?` | `linearised` |
| `HiGHS solver algorithm?` | `simplex` |
| `Presolve?` | `choose` |
| `Run crossover after IPM?` | `choose` |
| `Time limit in seconds?` | Leave it empty. |
| `Output directory?` | `outputs/solved` |

If Julia and the PowerSimulations.jl packages are not installed, the prompt
`Download and continue?` comes before the path prompt. Answer yes. The first solve then
downloads and compiles the packages.

The system has no AC line, so use the network model `copperplate`. The network model `dcp`
needs AC branches. The fleet of 2021 is short of the peak load in two countries. The answer
`penalised` at the `Unserved energy?` prompt lets the solve leave that load unserved.

The solve covers 96 hours: four representative days of 24 hours, one for each season of 2021.
The run gives this result:

| Item | Value |
| --- | --- |
| Run status | `SUCCESSFULLY_FINALIZED` |
| HiGHS model status | `Optimal` |
| Objective | 1,533,573,058 USD, which is 1.53357 × 10⁹ |
| Unserved energy | 1,141.06 MWh: 1,121.94 MWh in `MR` and 19.12 MWh in `GW` |

The objective is the cost of the 96 hours, and it gives no weight to the days. It does not
compare with the objective of the published results, which is the discounted cost of 35 years.

## Compare the dispatch with the published results

The AETOS authors publish the results of their scenarios in `AETOS_Runner/results/`. This case
study compares the dispatch with the file `20260123_UNNZv2.csv`.

Select `compare`. Then give these answers:

| Prompt | Answer |
| --- | --- |
| `First result's framework?` | `aetos` |
| `Second result's framework?` | `sienna` |
| `aetos.config_path` | `../case_study_inputs/aetos/AETOS_Runner/config_otoole_AETOS.yaml` |
| `aetos.csv_dir` | `../case_study_inputs/aetos/AETOS_Runner/CSVFiles` |
| `aetos.results_csv_path` | `../case_study_inputs/aetos/AETOS_Runner/results/20260123_UNNZv2.csv` |
| `aetos.first_year` | `2021` |
| `User mappings file for aetos?` | `inputs/aetos_mappings.yaml` |
| `sienna.system_json_path` | `outputs/operations/system.json` |
| `sienna.extensions_json_path` | `outputs/operations/extensions.json` |
| `sienna.results_dir` | `outputs/solved` |
| `Output path for summary report?` | `outputs/comparison/comparison_summary.md` |

The console shows `compared results: diffs=1,931`. The report is
`outputs/comparison/comparison_summary.md`.

The compare runs the two results pipelines internally. To keep the two results tables, run the
pipelines by themselves:

```bash
INTEROP_LOG_LEVEL=WARNING uv run interop headless_cli --pipeline sienna-to-results \
  --override 'source.system_json_path=outputs/operations/system.json' \
  --override 'source.extensions_json_path=outputs/operations/extensions.json' \
  --override 'source.results_dir=outputs/solved' \
  --override 'sink[0].output_dir=outputs/results_sienna'

INTEROP_LOG_LEVEL=WARNING uv run interop headless_cli --pipeline aetos-to-results \
  --override 'source.config_path=../case_study_inputs/aetos/AETOS_Runner/config_otoole_AETOS.yaml' \
  --override 'source.csv_dir=../case_study_inputs/aetos/AETOS_Runner/CSVFiles' \
  --override 'source.results_csv_path=../case_study_inputs/aetos/AETOS_Runner/results/20260123_UNNZv2.csv' \
  --override 'source.first_year=2021' \
  --override 'sink[0].output_dir=outputs/results_aetos' \
  --user-mappings-path inputs/aetos_mappings.yaml
```

Each pipeline writes `results.parquet` to its output directory. This Python code gives the 2021
totals. A row with no category is a line, or a pollutant for `emissions`:

```python
import polars as pl

for side in ("results_aetos", "results_sienna"):
    table = pl.read_parquet(f"outputs/{side}/results.parquet")
    print(side, table.filter(pl.col("timestamp").dt.year() == 2021)
          .group_by("variable", pl.col("category").is_null().alias("has_no_category"))
          .agg(pl.col("value").sum()).sort("variable", "has_no_category"))
```

The values are in MW, MWh and t. These are the 2021 totals:

| Item | Published | Sienna dispatch |
| --- | --- | --- |
| Installed capacity of the generators and the storages | 1,397.2 GW | 1,384.7 GW |
| Installed capacity of the lines | 171.0 GW | 171.0 GW |
| Production of the generators and the storages | 4,102.8 TWh | 3,732.6 TWh |
| Trade, which is the production of the lines | 389.5 TWh | 815.2 TWh |
| Emissions | 1,459.1 Mt | 847.3 Mt |

The Sienna dispatch covers 96 hours. The results pipeline multiplies each hour by the weight of
its day, so each Sienna value is a value for the year.

These are the production totals of the categories with the largest differences:

| Category | Published | Sienna dispatch |
| --- | --- | --- |
| `gas-combined-cycle` | 547.9 TWh | 217.9 TWh |
| `coal` | 568.2 TWh | 735.1 TWh |
| `gas-steam` | 118.2 TWh | 58.4 TWh |
| `oil-steam` | 102.4 TWh | 45.2 TWh |
| `nuclear` | 943.8 TWh | 942.8 TWh |
| `hydro` | 748.8 TWh | 742.7 TWh |
| `wind-onshore` | 452.7 TWh | 446.0 TWh |
| `solar` | 209.8 TWh | 209.4 TWh |
| `pumped-storage` | 0.05 TWh | 8.87 TWh |

[What the numbers do not cover](#what-the-numbers-do-not-cover) gives the cause of each large
difference.

## Expand the portfolio

### The full model

Make the document that PowerSystemsInvestments.jl reads. Do this command:

```bash
INTEROP_LOG_LEVEL=WARNING uv run interop headless_cli --pipeline sienna-to-power-systems-investments \
  --override 'source.portfolio_json_path=outputs/investments/portfolio.json' \
  --override 'source.system_json_path=outputs/investments/system.json' \
  --override 'source.time_series_h5_path=outputs/investments/system_time_series_storage.h5' \
  --override 'source.extensions_json_path=outputs/investments/extensions.json' \
  --override 'sink[0].portfolio_path=outputs/investments_psi/portfolio.json' \
  --override 'sink[0].h5_output_path=outputs/investments_psi/portfolio_base_system_time_series.h5'
```

The run writes `portfolio.json`, its base system and `portfolio_series.json` to
`outputs/investments_psi/`. Then select `solve`, and give the answers of
[A subset of the model](#a-subset-of-the-model) below, with three changes:

- At `Path to the PowerSystemsInvestments portfolio JSON?`, give
  `outputs/investments_psi/portfolio.json`.
- At `Time limit in seconds?`, give `3600`.
- At `Output directory?`, give `outputs/investments_expanded`.

The full model does not solve in 16 GB of memory. We tried it one time, with the answers
above:

- The solve read the portfolio and started to build the problem 11 minutes after the start.
- The build of the problem took 2,543 seconds, which is 42 minutes. The memory then held 9.8 GB.
- After the build, the memory went up by about 3 GB each minute. We stopped the run at 14.5 GB,
  after 55 minutes, to keep the computer usable. The peak memory was 15.1 GB.
- HiGHS did not start. Thus the time limit of 3600 seconds did not apply.

The problem holds 35 investment periods, one for each model year, and 1,345 candidate
technologies. The subset below holds 3 periods and 5 countries. To expand the full model, use a
computer with much more memory, or give fewer years at the `step[0].years` prompt of the
portfolio translation.

### A subset of the model

This subset holds five countries, `DE`, `FR`, `ES`, `IT` and `PT`, and three years, 2025, 2030
and 2035. Select `translate`. Give the answers of
[the portfolio translation](#translate-the-model-into-a-sienna-investments-portfolio), with
these changes:

| Prompt | Answer |
| --- | --- |
| `step[0].locations` | `DE, FR, ES, IT, PT` |
| `step[0].years` | `2025, 2030, 2035` |
| `sink[0].output_system_json_file_path` | `outputs/subset/system.json` |
| `sink[1].output_path` | `outputs/subset/portfolio.json` |

The portfolio holds 92 `SupplyTechnology`, 2 `AggregateTransportTechnology` and 5
`DemandRequirement`. The two transport technologies are `ESELFRPH1` and `ESELPTPH1`.

Select `translate` again. Then give these answers:

| Prompt | Answer |
| --- | --- |
| `Source framework?` | `sienna` |
| `Destination framework?` | `power-systems-investments` |
| `Pipeline?` | `sienna-to-power-systems-investments` |
| `source.portfolio_json_path` | `outputs/subset/portfolio.json` |
| `source.system_json_path` | `outputs/subset/system.json` |
| `source.time_series_h5_path` | `outputs/subset/system_time_series_storage.h5` |
| `source.extensions_json_path` | `outputs/subset/extensions.json` |
| `source.portfolio_time_series_h5_path` | Leave it empty. |
| `sink[0].portfolio_path` | `outputs/subset_psi/portfolio.json` |
| `sink[0].h5_output_path` | `outputs/subset_psi/portfolio_base_system_time_series.h5` |

Keep the default at every other prompt. The console shows eight warnings. They say that the
package holds the existing capacity of 120 technologies constant, reads no profile for 60
thermal plants, and gives no operations to the 8 years between the periods.

Select `solve`. Then give these answers:

| Prompt | Answer |
| --- | --- |
| `Model type?` | `sienna-investments` |
| `Path to the PowerSystemsInvestments portfolio JSON?` | `outputs/subset_psi/portfolio.json` |
| `Balance model?` | `multi-region` |
| `Investment treatment?` | `continuous` |
| `Discount rate?` | Leave it empty. The solve then uses the rate of the portfolio, 0.075. |
| `HiGHS solver algorithm?` | `simplex` |
| `Presolve?` | `choose` |
| `Run crossover after IPM?` | `choose` |
| `Time limit in seconds?` | Leave it empty. |
| `Output directory?` | `outputs/subset_expanded` |

If the PowerSystemsInvestments.jl packages are not installed, the prompt
`Download and continue?` comes first. Answer yes.

The solve gives the run status `SUCCESSFULLY_FINALIZED` and the objective 31,774,548,823 USD,
which is 3.17745 × 10¹⁰.

Turn the solve into the results format:

```bash
INTEROP_LOG_LEVEL=WARNING uv run interop headless_cli --pipeline power-systems-investments-to-results \
  --override 'source.results_dir=outputs/subset_expanded' \
  --override 'source.series_json_path=outputs/subset_psi/portfolio_series.json' \
  --override 'sink[0].output_dir=outputs/results_expansion_subset'
```

Then select `compare`, and give these answers:

| Prompt | Answer |
| --- | --- |
| `First result's framework?` | `power-systems-investments` |
| `Second result's framework?` | `aetos` |
| `power-systems-investments.results_dir` | `outputs/subset_expanded` |
| `power-systems-investments.series_json_path` | `outputs/subset_psi/portfolio_series.json` |
| `aetos.config_path` | `../case_study_inputs/aetos/AETOS_Runner/config_otoole_AETOS.yaml` |
| `aetos.csv_dir` | `../case_study_inputs/aetos/AETOS_Runner/CSVFiles` |
| `aetos.results_csv_path` | `../case_study_inputs/aetos/AETOS_Runner/results/20260123_UNNZv2.csv` |
| `aetos.first_year` | `2021` |
| `User mappings file for aetos?` | `inputs/aetos_mappings.yaml` |
| `Output path for summary report?` | `outputs/comparison_expansion/comparison_summary.md` |

The console shows `compared results: diffs=1,899`.

The totals below come from `outputs/results_expansion_subset/results.parquet` and
`outputs/results_aetos/results.parquet`. They are the totals of the 211 components that the
expansion results name. The published values are the values of the same components in the
published results:

| Item | Year | Published | Expansion |
| --- | --- | --- | --- |
| Installed capacity | 2025 | 684.7 GW | 532.1 GW |
| Installed capacity | 2030 | 809.9 GW | 542.5 GW |
| Installed capacity | 2035 | 948.8 GW | 542.5 GW |
| New capacity | 2025 | 43.3 GW | 23.7 GW |
| New capacity | 2030 | 56.1 GW | 10.4 GW |
| New capacity | 2035 | 48.6 GW | 0.0 GW |
| Production | 2025 | 1,740.8 TWh | 1,649.7 TWh |
| Production | 2030 | 2,042.3 TWh | 1,942.4 TWh |
| Production | 2035 | 2,158.4 TWh | 2,068.6 TWh |

Over the three years, the published solve builds 64.8 GW of onshore wind and 64.8 GW of
solar in the five countries. The expansion builds 25.3 GW and 8.9 GW of two biomass
technologies, and almost nothing else. The published solve optimises all 78 countries over 35
years, so these totals are an observation and not a test of the translation.

## What the numbers do not cover

[The gap analysis](../translation_mappings/osemosys-to-sienna-gap-analysis.md) gives one entry
for each thing that the translation or the solve loses, with its cause and its effect. These
are the entries that explain the large differences above:

- **The production is 370 TWh lower in the dispatch.** About 400 TWh of the published
  production is the loss of the conversions between two electricity fuels of one country. The
  system has no component for a conversion. Refer to
  [What the system has no component for](../translation_mappings/osemosys-to-sienna-gap-analysis.md#what-the-system-has-no-component-for).
- **Gas makes less and coal makes more.** The model gives 24 gas plants a lower limit on their
  energy in 2021, about 450 TWh. A Sienna system has no field for a limit on the energy of a
  year, so the dispatch does not apply it. Refer to
  [Limits on activity and energy](../translation_mappings/osemosys-to-sienna-gap-analysis.md#limits-on-activity-and-energy).
- **The trade is two times the published trade.** A line has no cost in the system, and the
  solve applies no loss. The 21 imports from outside the model do not happen. Refer to
  [Costs and prices](../translation_mappings/osemosys-to-sienna-gap-analysis.md#costs-and-prices)
  and [Operating modes](../translation_mappings/osemosys-to-sienna-gap-analysis.md#operating-modes).
- **The emissions are 612 Mt lower in the dispatch.** The published emissions also count the
  CO2 of the gas that enters a country, and two transit countries have negative emissions. The
  Sienna emissions are those of the power plants only. Refer to
  [Differences that are not a loss](../translation_mappings/osemosys-to-sienna-gap-analysis.md#differences-that-are-not-a-loss).
- **Pumped storage has 8.8 GW less capacity and makes 8.8 TWh more.** Sienna rates a storage on
  its electricity output, and the dispatch runs the days in time order. Refer to
  [Storage](../translation_mappings/osemosys-to-sienna-gap-analysis.md#storage).
- **Two countries have unserved energy.** The published solve builds about 3 GW in 2021. The
  system holds the residual capacity of 2021 only, so `MR` and `GW` are short of their peak.
  Refer to [The four structural losses](../translation_mappings/osemosys-to-sienna-gap-analysis.md#the-four-structural-losses).
- **The expansion builds biomass, and the published solve builds wind and solar.** The package
  reads no availability profile for a thermal candidate, so a biomass plant can run at its full
  capacity in every hour. No emission limit binds, and the existing fleet does not retire. We
  did not measure the effect of each cause by itself. Refer to
  [The expansion solve](../translation_mappings/osemosys-to-sienna-gap-analysis.md#the-expansion-solve).

The two objectives of each comparison do not compare. The dispatch objective is the cost of 96
hours. The published objective is the discounted cost of the whole model and of every year.

## What it costs

We measured each run with `/usr/bin/time -v` on a computer with 8 cores and 16 GB of memory.
The time of a solve does not include the download and the compilation of the Julia packages.

| Run | Status | Objective | Time | Peak memory |
| --- | --- | --- | --- | --- |
| `osemosys-csv-to-canonical` | exit 0, 2 warnings | none | 2.5 s | 0.40 GB |
| `osemosys-csv-to-sienna`, year 2021 | exit 0, 27 warnings | none | 3.5 s | 0.42 GB |
| `osemosys-csv-to-sienna-investments`, every year | exit 0, 21 warnings | none | 18.8 s | 0.55 GB |
| `sienna-to-power-simulations` | exit 0 | none | 3.4 s | 0.26 GB |
| Dispatch solve | `SUCCESSFULLY_FINALIZED` | 1.53357 × 10⁹ USD | 3 min 1 s | 2.23 GB |
| `sienna-to-results` | exit 0 | none | 1.6 s | 0.28 GB |
| `aetos-to-results` | exit 0, 7 warnings | none | 3.3 s | 0.69 GB |
| Compare of the dispatch | exit 0, 1,931 differences | none | 4.6 s | 0.78 GB |
| `sienna-to-power-systems-investments`, full model | exit 0, 8 warnings | none | 47.6 s | 1.59 GB |
| Expansion solve, full model | stopped at 14.5 GB, HiGHS did not start | none | 55 min 9 s | 15.1 GB |
| `osemosys-csv-to-sienna-investments`, subset | exit 0, 16 warnings | none | 3.7 s | 0.42 GB |
| `sienna-to-power-systems-investments`, subset | exit 0, 8 warnings | none | 2.2 s | 0.25 GB |
| Expansion solve, subset | `SUCCESSFULLY_FINALIZED` | 3.17745 × 10¹⁰ USD | 2 min 41 s | 2.10 GB |
| `power-systems-investments-to-results`, subset | exit 0 | none | 0.7 s | 0.14 GB |
| Compare of the expansion | exit 0, 1,899 differences | none | 3.4 s | 0.76 GB |

The time of each REPL run includes the start of tz-oss-interop. The canonical stage is 1.6 MB on
disk. The `decisions.md` of the operations translation is 12 MB. The `decisions.md` of the full
expansion leg is 18 MB.
