# Running a capacity expansion

A translation's product is the SiennaSchemas portfolio document that
`pypsa-to-sienna-investments`, `plexos-to-sienna-investments` or
`osemosys-csv-to-sienna-investments` writes. `PowerSystemsInvestmentsPortfolios.jl` does not read
that shape, so a second leg turns it into the shape the package does read, and the `solve`
command runs the result.

```
network.nc ──pypsa-to-sienna-investments──▶ portfolio.json  (SiennaSchemas)
                                            system.json
                                                  │
                        sienna-to-power-systems-investments
                                                  │
                                                  ▼
                                            portfolio.json              the envelope
                                            portfolio_base_system.json  the fleet that runs
                                            portfolio_base_system_time_series.h5
                                            portfolio_series.json       the profiles
                                                  │
                                      solve, model type sienna-investments
```

## Which Julia packages run it

Neither package has a release that runs. `PowerSystemsInvestments` is not in the General
registry, and its `main` branch asks for PowerSystems 4 while the registered
`PowerSystemsInvestmentsPortfolios` 0.1.0 asks for 5.3 or later, so the resolver refuses the
pair. `interop/adapters/outbound/julia_packages.py` therefore pins a URL and a commit each:

| Package | Branch | Commit |
|---|---|---|
| PowerSystemsInvestments.jl | `al/storage_integer` | `8bfed9f` |
| PowerSystemsInvestmentsPortfolios.jl | `main` | `d72d61c` |

`al/storage_integer` is the only branch of the solver package that calls nothing the data
package's `main` defines. The two newer branches, `jp/capex` and `cb/inv_compat`, each need a
data package that nobody has published. Both pins resolve beside the dispatch solver, so one
Julia environment serves dispatch and expansion.

The pin of the solver package was `f68d202`. An upstream rewrite of `al/storage_integer`
removed that commit, so the pin is now `8bfed9f`, the head of the rewritten branch. Both
commits have the author date 3 August 2026.

## The envelope

The package reads one flat `components` list under `data`, and a `__metadata__` block on
every component naming the Julia module and type to build. A technology is parametric on a
PowerSystems type, so its block names that type as well:

```json
{"name": "REZ_Solar", "id": 1, "region": [1],
 "__metadata__": {"module": "PowerSystemsInvestmentsPortfolios", "type": "SupplyTechnology",
                  "parameters": ["RenewableDispatch"], "construct_with_parameters": true}}
```

Four things the step settles, because the two documents differ on them:

- **A region becomes a Zone.** A technology names its region by integer id, and the package
  resolves that id against the regions the portfolio itself holds. An area of the base system
  therefore becomes a `Zone` component of the portfolio.
- **A capital cost becomes a value curve.** SiennaSchemas wraps the curve in a `CapitalCost`
  beside an interconnection cost; the package's field holds the curve alone. A storage
  technology's one struct becomes three curves, one per capacity a plan may add. The
  interconnection cost reaches nothing, and the decisions report says so.
- **A nested structure names its concrete type.** Every cost, every value curve and the rates
  a technology is financed at carry their own `__metadata__` block, because the reader picks
  a type by that tag and not by the fields.
- **A field the reader rejects as null states an empty value.** The reader resolves a list of
  ids, iterates a map and indexes a pair by name, and a null stops each of the three. So
  `fuel`, `requirements` and `region` state `[]`, `co2` and the cofire limits state `{}`, and
  the ramp and time limits state a pair of ones, which means no limit.

Four more things the step settles, because the package reads a field in a different way
from the schema:

- **A limit stated once for each year becomes one limit.** The package holds one `MinMax`. It
  bounds the installed capacity of every investment period by `max`, and the capacity that each
  period builds by `min`. So a `MinMaxByKey` limit becomes the largest yearly maximum, which
  every plan that the yearly limits allow also keeps. A year with no maximum leaves no maximum.
  No yearly minimum reaches the package, because it is a floor on the installed capacity and
  not on what one period builds. The decisions report records each minimum as not mapped.
- **A limit or a size that a source does not state takes the package's own default.** The
  reader rejects a null, and indexes both bounds of a limit by name. So an absent capacity limit
  states `{"min": 0.0, "max": 1e8}`, a limit with one bound gets the other from that default,
  and an absent transport `unit_size` states `1.0`.
- **A storage duration becomes hours.** SiennaSchemas states `duration_limits` in minutes. The
  package reads hours: it bounds the stored energy by `duration_limits.max` × the discharge
  power. So the step divides each stated bound by 60, and records the value in both units. An
  absent duration takes the package's default of `{"min": 0.0, "max": 1000.0}` hours.
- **A transport technology is lossless and flows both ways.** An `AggregateTransportTechnology` names its start and
  end regions by id, and the package resolves each against the Zones. It flows both ways, and
  the package takes the loss from the energy that reaches the end region. A flow from the end
  to the start therefore delivers more energy than it takes. So the step writes `line_loss`
  `0.0`, records the stated loss as not mapped, and warns. The direction that the source
  states does not bound the flow, and the step records and warns that too. Every transport
  technology is built as `AggregateTransportTechnology{ACBranch}`, which is the type the adapter
  sets a model for, and its `power_systems_type` states `ACBranch`.

### What the reader derives, and never reads from a field

The base system's filename. For `portfolio.json` the reader opens
`portfolio_base_system.json` in the same directory. The sink writes that name, so the pair
moves together.

## Why the portfolio carries no time series

The package reads a component through a generated struct with no field for a UUID. A
component therefore gets a fresh UUID on the way in, while the association rows still name
the old one, and every series the document carried is lost. A written portfolio states no
`time_series_storage_file` and writes no companion for itself, because a document naming a
file it cannot use is worse than one naming none.

The series travel in `portfolio_series.json` instead, and the adapter attaches each one to
the component that came off disk. Each record names:

| Field | What it is |
|---|---|
| `series_name` | `ops_variable_cap_factor` on a supply technology, `ops_demand` on a demand requirement |
| `year` | the calendar year of the slice, which the model looks the series up by |
| `rep_day` | the index of the slice among the slices of every year, in order from 1, which the model looks the series up by |
| `weight` | how many times the slice occurs in the year |

The names are the package's own, one per technology type, so a document stating any other
name reaches a model that finds nothing. The model reads `ops_variable_cap_factor` for a
`RenewableDispatch` and a `HydroDispatch` only, so the step writes no record for a supply
technology of another type. It records the profile as not mapped and warns.

The companion also holds `existing_devices`: one entry for each technology that already holds
capacity, with `component_type`, `component_name` and `devices`. The adapter attaches each as
an `ExistingDevices` attribute after the read, because the envelope cannot carry an attribute.

### The fleet that already runs

The model counts the capacity that a technology already holds through its `ExistingDevices`:
the names of base system components of the technology's PowerSystems type, at their rating
in MW. The step reads the `ExistingDevices` attributes of the portfolio and settles four things:

- **A name the base system does not hold under the type is left out.** The model stops on a
  name that it cannot find. The step records each such name as not mapped, and warns.
- **A limit holds at least the existing devices.** The model bounds existing plus built
  capacity by `max`, so the step lifts a `max` below the rating of the devices to that rating.
- **A minimum loses the existing devices.** The model bounds the capacity that each period
  builds by `min`, and a source minimum, such as PyPSA `p_nom_min`, bounds the total. So the step
  lowers `min` by the rating of the devices, down to 0.
- **An existing plant that no technology names becomes a technology of its own.** It has the
  plant's name, type, Zone and operation cost, `capacity_limits` of `{min: 0, max: rating}`,
  no capital cost, and the plant as its one existing device. A `RenewableDispatch` or a
  `HydroDispatch` of this kind takes its base system profile, split into the representative
  days of every year. A `HydroDispatch` of this kind loses its `hydro_budget`, and the step
  records and warns that. When a technology already has the plant's name, the plant's own
  technology takes the name with `/existing`. Its finance is all equity over one year, at the
  portfolio's rate, else the highest rate of a technology, else a fixed rate of 0.05, so the
  capital recovery factor stays defined. An existing component of another type, such as a
  storage or a `RenewableNonDispatch`, is left out, recorded and warned.
- **An existing link cannot attach.** The model looks the existing device of a transport
  technology up as an `ACBranch`, and the base system holds a `TwoTerminalGenericHVDCLine`. The
  step records and warns each one.

The model holds existing capacity constant over every investment period and reads no
retirement. The step records that once and warns.

### A portfolio that states its own series by year

A portfolio can state one series for each technology and each year, in its own
`time_series_associations` and its own HDF5 companion. Each association has the feature
`year` and the name `max_active_power`: MW for a `DemandRequirement`, per unit for a
`SupplyTechnology`. `osemosys-csv-to-sienna-investments` writes such a portfolio. The source
reads the companion from `portfolio_time_series_h5_path`, or from the file that the portfolio
names beside it.

Each series runs over the representative days of the base system in order. The
`representative_period` records of `extensions.json` give each day its first hour, its length
and its weight. So the step splits the series of each year into one record for each day:

| Field | Value |
|---|---|
| `year` | the `year` feature of the series |
| `rep_day` | the index of the slice among the slices of every year, from 1, in year order |
| `weight` | the `weight` of the representative period |
| `initial_timestamp` | the hour of the series at the offset of the day in its year |

The model looks a slice up by its index among all the slices of the plan, not by its index in
its year, so `rep_day` counts on across the years. The step writes one investment period for
each year.

Two kinds of technology need a series in every slice, and the portfolio can state none:

- A `RenewableDispatch` or `HydroDispatch` technology with no series takes its base system
  profile, split into the representative days of every year. With no base system profile,
  each of its slices states `1.0`, and the step warns.
- A `DemandRequirement` with no series in a year has no demand in that year. Each slice of
  that year states `0.0`, and the step warns.

With no `representative_period` records, the series of each year is one slice, weighted so
that its hours stand for the whole year. The step warns.

The model reads a series for every technology in every slice. So a day that one series does
not reach is left out of the plan for every technology. The step records the short series and
the day, and warns.

### One representative day

This applies to a portfolio that states no series of its own. A SiennaSchemas system states one
profile per component over the whole snapshot window, and no representative days at all. A
`RenewableDispatch` or `HydroDispatch` technology that the system states no profile for gets
1.0 for every hour of the slice, and the step warns. The step therefore takes **the first 24 snapshots** as
representative day 1. The weight is 8760 over the hours that the slice covers, so an hourly
slice weighs 365 and a half-hourly slice weighs 730. The step derives one investment period per
year the slices fall in, running that whole year. Clustering a real year into several representative
days is not done here.

A demand profile is multiplied by the load's own `max_active_power`, because a SiennaSchemas
system stores it per unit of that peak and the model reads `ops_demand` as MW.

## An OSeMOSYS portfolio

`osemosys-csv-to-sienna-investments` and `tz-osemosys-to-sienna-investments` write a portfolio
over every year in scope.
[Translation from OSeMOSYS to a Sienna Investments Portfolio](../translation_mappings/translation-from-osemosys-to-sienna-investments.md)
gives each field. The leg reads such a portfolio with the rules above. This section collects
what each rule does to an OSeMOSYS plan.

| Part of the portfolio | What the leg does |
| --- | --- |
| `SupplyTechnology.capacity_limits`, keyed by year | One limit: the largest yearly maximum, and no minimum. Each minimum is recorded as not mapped. |
| The series of each year, with the feature `year` | Split into the representative days of the `representative_period` records, one investment period for each year. |
| `AggregateTransportTechnology` | Built between two Zones as `AggregateTransportTechnology{ACBranch}`, lossless, in both directions. The stated loss and the direction are recorded as not mapped. |
| `CarbonCaps`, one for each year | Passed with its `target_year`. The model builds no constraint from it. |
| `StorageTechnology.duration_limits`, in minutes | Divided by 60, because the model reads hours. |
| A limit or a unit size that the portfolio does not state | The default of the package. |
| The `ExistingDevices` of a candidate | Attached after the read. The model holds that capacity constant over every period. |

### The existing fleet of an OSeMOSYS plan

An OSeMOSYS candidate holds one existing device at most: the component of the base system
with its own name. A plant of the base system that is not a candidate is in no technology of
the portfolio. So the leg adds such a plant as a technology of its own, as
[The fleet that already runs](#the-fleet-that-already-runs) describes. Without the existing
fleet, the plan builds the whole fleet again in the first period.

The leg applies these rules to an existing plant:

- **The finance of a technology that the leg adds.** It is all equity, and its recovery period
  is one year. Its rate is the discount rate of the portfolio, else the highest rate of a
  technology, else 0.05. The technology builds nothing, so the rate prices nothing.
- **A plant whose name a technology holds, when that technology does not list the plant.** The
  plant's own technology takes the name with `/existing`. When the plan also holds that name,
  the plant is left out. The step records each plant and warns.
- **A `capacity_limits.min` and the existing devices.** The model reads `min` as a floor on
  the build of each period. So the step lowers `min` by the rating of the devices, down to 0.
  The leg writes no minimum for an OSeMOSYS candidate, so this rule changes no OSeMOSYS limit.

### What an OSeMOSYS plan loses in the expansion

[The gap analysis](../translation_mappings/osemosys-to-sienna-gap-analysis.md#the-expansion-solve)
gives one entry for each loss, with its effect. In short: no cap binds, trade has no loss, the
fleet does not retire, a thermal candidate has no availability profile, and the years between
two periods carry no operations.

## Running it

The `solve` command's model type `sienna-investments` takes the portfolio path and two
answers the data does not state:

- **the balance model**: `single-region`, `multi-region` or `nodal`;
- **the investment treatment**: `continuous` builds any amount of capacity, `integer` builds
  whole units only and is much slower.

Everything else the portfolio states. The adapter names one formulation triple per technology
type the portfolio holds, and none for a type it does not:

| Technology type | Investment | Operations |
|---|---|---|
| `DemandRequirement{PowerLoad}` | `StaticLoadInvestment` | `BasicDispatch` |
| `SupplyTechnology{T}` | the run's treatment | `BasicDispatch` |
| `StorageTechnology{EnergyReservoirStorage}` | the run's treatment | `CyclicalStorageDispatch` |
| `AggregateTransportTechnology{ACBranch}` | the run's treatment | `BasicDispatch` |

### The discount rate

A portfolio written from a source that states no rate of its own leaves the portfolio-wide
discount rate at zero. The capital recovery factor divides by that rate, so every capital
cost becomes NaN and the build stops. Give a rate on the run instead; it outranks the
portfolio's, and a rate of zero is refused with a message naming the field.

## Reading the results

The adapter writes one long CSV for each variable under `results_wide/variables`, one for each
stored expression under `results_wide/expressions`, and `results/optimizer_stats.csv`. The
results pipeline `power-systems-investments-to-results` reads them with the series document,
`portfolio_series.json`, which gives each investment period its year and each hour its weight.
It writes these rows, each at 1 January of its year:

| Variable | From |
|---|---|
| `new_capacity` | `BuildCapacity`, or `BuildPowerCapacity` of a storage technology |
| `installed_capacity` | `CumulativeCapacity`, or `CumulativePowerCapacity` of a storage technology |
| `production` | Σ of `ActivePowerVariable`, `ActiveOutPowerVariable` of a storage technology, or the absolute `FlowActivePowerVariable` of a transport technology, × hours × the weight of the day |
| `objective` | `objective_value` of the solve |

A component keeps the name of its technology in the portfolio, so `interop compare` joins the
rows with those of the model that the portfolio came from. The solve states no category.

## What does not work

- **A renewable candidate with no profile runs at full availability, and the step warns.**
  A candidate that holds no capacity today is dropped from the operations system as retired,
  so its profile never reaches either document. The step then writes 1.0 for every hour of the
  slice, so the plan can build the candidate at full output in each hour. Give the candidate
  the capacity it already holds, and its profile reaches the plan.
- **Existing capacity never retires.** See "The fleet that already runs".
- **The years between the periods have no operations.** The model counts the operations of
  each period's own year only, while it amortises capital over the whole recovery period. The
  step records and warns the years between the periods, and does not change the weights.
- **A carbon cap limits nothing.** At the pinned commit the model builds a constraint from an
  `EnergyShareRequirements` only. A `CarbonCaps` reaches the portfolio with its `target_year`,
  and the step warns.
- **The availability of a thermal candidate is lost.** The model reads a profile for a
  `RenewableDispatch` and a `HydroDispatch` only. A `ThermalStandard` runs up to its capacity in
  every hour.
- **A type with no model is left out.** The adapter sets a model for the types in the table
  above only. A `SupplyTechnology{RenewableNonDispatch}`, for example, is not in the plan, and
  the adapter warns with its name. The leg step records the same technologies as not mapped, so
  the decisions report names them too. Both read the one list of modelled types,
  `MODELLED_TECHNOLOGIES`.
- **`ColocatedSupplyStorageTechnology` cannot be read at all.** Its generated struct declares
  three fields as a plain map where the real struct wants a pair of numbers, so the read stops
  with a `convert` error. This translation writes no such component.

## What replaces this

`PowerSystemsInvestmentsPortfolios` branch `jd/psip-parity-zero` deletes the generated code
this envelope depends on and adds `from_file`, which reads the SiennaSchemas portfolio
document directly. That is the document `emit_sienna_portfolio` already writes. When that
work becomes installable, this leg and its sink stop being needed and the adapter reads the
SiennaSchemas document instead. It is not installable today: it pins `PowerSystems#psy6`,
`InfrastructureSystems#IS4`, an unpublished `PowerOpenAPIModels` monorepo, and `InfraStore`
0.13.1, which the General registry does not carry.
