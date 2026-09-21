# Running a capacity expansion

A translation's product is the SiennaSchemas portfolio document that
`pypsa-to-sienna-investments` writes. `PowerSystemsInvestmentsPortfolios.jl` does not read
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
| PowerSystemsInvestments.jl | `al/storage_integer` | `f68d202` |
| PowerSystemsInvestmentsPortfolios.jl | `main` | `d72d61c` |

`al/storage_integer` is the only branch of the solver package that calls nothing the data
package's `main` defines. The two newer branches, `jp/capex` and `cb/inv_compat`, each need a
data package that nobody has published. Both pins resolve beside the dispatch solver, so one
Julia environment serves dispatch and expansion.

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
| `rep_day` | the index of the slice within that year, which the model looks the series up by |
| `weight` | how many days of the year the slice stands for |

The names are the package's own, one per technology type, so a document stating any other
name reaches a model that finds nothing.

### One representative day

A SiennaSchemas system states one profile per component over the whole snapshot window, and
no representative days at all. The step therefore takes **the first 24 snapshots** as
representative day 1 and weights it 365 days, and derives one investment period per year the
slices fall in, running that whole year. Clustering a real year into several representative
days is not done here.

A demand profile is multiplied by the load's own `max_active_power`, because a SiennaSchemas
system stores it per unit of that peak and the model reads `ops_demand` as MW.

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

## What does not work

- **A renewable candidate with no profile cannot be solved.** `BasicDispatch` reads
  `ops_variable_cap_factor` for a `SupplyTechnology{RenewableDispatch}`, and stops where a
  technology states none. A candidate that holds no capacity today is dropped from the
  operations system as retired, so its profile never reaches either document. Give the
  candidate the capacity it already holds, or its profile will not be there.
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
