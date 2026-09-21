# A Sienna investments portfolio runs a capacity expansion

## The problem

`emit_sienna_portfolio` writes a SiennaSchemas portfolio document, and
`pypsa-to-sienna-investments.yaml` produces one from a PyPSA network. Nothing reads that
document back into Julia. Nobody has shown that the Sienna packages accept what this
repository writes, and nobody has run a capacity expansion from it.

Four things stand in the way.

- **Neither Julia package installs as it stands.** `PowerSystemsInvestments.jl` is not in the
  General registry, so it installs by URL and commit. Its `main` branch asks for
  PowerSystems 4, while the registered `PowerSystemsInvestmentsPortfolios` 0.1.0 asks for
  PowerSystems 5.3 or later. The two demands contradict each other, and the resolver refuses.
- **The two packages only work together at certain commits.** A solver commit calls names that
  a data commit may not define.
- **The document shape differs.** `PowerSystemsInvestmentsPortfolios` does not read the
  SiennaSchemas shape. It reads its own: one flat `components` list under `data`, with a
  `__metadata__` block on each component and on each nested cost structure.
- **The file loses every time series.** A component is written and read through a generated
  struct that has no field for a UUID, so it gets a fresh one on the way back while the time
  series associations still name the old one.

## What runs, proved by running it

The design rests on seven probes against Julia 1.11.9. These are the two commits they used:

| Package | Branch | Commit | Date |
|---|---|---|---|
| PowerSystemsInvestments.jl | `al/storage_integer` | `f68d202694e17e7a0a0156490d2b7c2e9167bdb7` | 3 Aug 2026 |
| PowerSystemsInvestmentsPortfolios.jl | `main` | `d72d61c1be2f7cdd5d54d7464b902973eead77b3` | 6 Aug 2026 |

That pair came from comparing every name each solver branch calls on the data package against
every name the data package's `main` branch defines. Of 26 solver branches, 14 still ask for
PowerSystems 4 and 3 pin packages nobody has published. Of the 9 that remain,
`al/storage_integer` is the only one that calls nothing the data package's `main` lacks.

What the probes returned:

- The solver package's own test builds and solves on that pair, in two minutes.
- Every component type this translation writes survives the file, with its name, its integer
  id and its region.
- Every time series is lost across the file, and attaching each one again after the read
  restores it.
- A portfolio that went through the file built and solved: `BUILT`, then
  `SUCCESSFULLY_FINALIZED`, with an objective value.
- One Julia environment holds this pair beside the dispatch solver this repository already
  pins, on PowerSystems 5.9.1 and PowerSimulations 0.34.2.

Four contract facts came out of the same probes:

- **A portfolio with no time series writes no HDF5 file and reads back correctly.** The key
  `time_series_storage_file` is then absent. A document naming a file that is not present
  fails.
- **The base system may be empty.** A default `PSY.System(100.0)` holds no components, and the
  model still builds and solves.
- **The reader derives the base system's filename.** For `portfolio.json` it opens
  `portfolio_base_system.json` in the same directory. The document never names it.
- **`ColocatedSupplyStorageTechnology` cannot be read back.** Its generated struct declares
  three fields as a plain map where the real struct wants a pair of numbers. This translation
  does not write that type.

## The design

### The portfolio carries no time series

The envelope drops every series, so the portfolio does not try to carry one. It states no
`time_series_storage_file` and writes no HDF5 companion. A separate document,
`portfolio_series.json`, holds one record per series: the component type, the component name,
the series name, the `year` feature, the `rep_day` feature, the weight, the first timestamp,
the resolution and the values. The adapter attaches each record after the read.

This is the one decision the defect forces, and it is also the honest one. A file that carries
a series nobody can read is worse than a file that carries none.

### A separate leg reaches the solver

`sienna-to-power-systems-investments.yaml` runs on its own, as `sienna-to-power-simulations`
does. The product of a translation stays the SiennaSchemas document; this leg exists only to
reach a solver.

It reads both halves, because the reader opens both files. A new source,
`stage_sienna_portfolio_json`, reads the portfolio document and the operations system
document. The two existing `sienna_to_powersimulations_*` steps map the operations half, and a
new step maps the investments half. One sink writes all three files.

The new step does three things, which are the whole difference between the two shapes:

1. It puts every component in one flat list rather than a map keyed by type name.
2. It attaches a `__metadata__` block per component, naming the Julia module and type, plus
   `parameters` and `construct_with_parameters` where the type takes a PowerSystems parameter.
3. It turns each cost discriminator field into a nested `__metadata__` block. The Pydantic
   models in `power_simulations_schema.py` already build those blocks, so the new module
   imports them.

### The solve asks the user two questions

The portfolio answers the rest itself:

- the discount rate and the base year, from its own financial data;
- the representative days and their weights, from `portfolio_series.json`, because the series
  *are* the representative days;
- the investment periods, derived from the distinct years, each period running to the year
  before the next;
- which technology types take part, because `set_technology_model!` enumerates a type's
  technologies from the portfolio.

The two new questions are the balance model (`single-region`, `multi-region` or `nodal`) and
the investment treatment (`continuous` or `integer`). The solver, presolve, crossover and time
limit questions carry over from the dispatch path unchanged.

Deriving the periods rather than asking for them keeps the template and the data in agreement.
A period the user states and a series the data holds could otherwise disagree, and the model
would look up a series that is not there.

### One formulation triple per technology type

The adapter names types, never components.

| Technology type | Investment | Operations | Feasibility |
|---|---|---|---|
| `DemandRequirement{PowerLoad}` | `StaticLoadInvestment` | `BasicDispatch` | `BasicDispatchFeasibility` |
| `SupplyTechnology{T}` | from the request | `BasicDispatch` | `BasicDispatchFeasibility` |
| `StorageTechnology{EnergyReservoirStorage}` | from the request | `CyclicalStorageDispatch` | `BasicDispatchFeasibility` |
| `AggregateTransportTechnology{ACBranch}` | from the request | `BasicDispatch` | `BasicDispatchFeasibility` |

A type the portfolio does not hold gets no model.

### The surface is the existing solve command

`ModelType` gains `sienna-investments`, so one command covers dispatch and expansion. The
request is a new `SolveExpansionRequest`, and it returns the existing `SolveResult`, because an
expansion solve also has a status and an objective value. A new outbound port, `ExpansionPort`,
keeps the dispatch `SolverPort` signature untouched, and a new adapter implements it beside
`julia_solver.py`.

## Deferred

- **The newest solver branches.** `jp/capex` and `cb/inv_compat` are newer than the branch this
  pins, and each needs a data package that nobody has published.
- **`ColocatedSupplyStorageTechnology`**, which the package cannot read back.
- **Clustering of representative days.** The portfolio states the days it holds, so
  `ClusteredRepresentativeDays` is not used.

## What replaces this design later

`PowerSystemsInvestmentsPortfolios` branch `jd/psip-parity-zero`, of 17 September 2026, deletes
the generated code this envelope depends on and adds `from_file`, which reads the SiennaSchemas
portfolio document directly. That is the document `emit_sienna_portfolio` already writes. When
that work becomes installable, the leg and the sink this design adds become dead, and the
adapter reads our existing document instead. The solve does not change.

It is not installable today. It pins `PowerSystems#psy6`, `InfrastructureSystems#IS4`, an
unpublished `PowerOpenAPIModels` monorepo and `InfraStore` 0.13.1, which the General registry
does not carry.
