# What a PLEXOS model states that Sienna has no home for

## What this document is for

tz-oss-interop translates a PLEXOS model into a Sienna one. Two pipelines do it, and this document
covers both:

- `plexos-to-sienna` writes a **dispatch system**. That is a `system.json` file holding the
  buses, the generators, the lines and the loads that a solve dispatches over a year.
- `plexos-to-sienna-investments` writes the same system, and a **portfolio** beside it. A
  portfolio is a `portfolio.json` file holding the technologies a plan may build, and the
  policy limits the plan must meet.

A PLEXOS model states more than either file can hold. This document answers one question
about the difference:

> Which things does a PLEXOS model state that these runs do not translate, **because Sienna
> itself has nowhere to put them**?

Read it before you trust a Sienna system built from your PLEXOS model. A row here is a thing
your model says that no version of this translator can carry, so you must account for it
some other way.

## The words this document uses

| Word | What it means |
| --- | --- |
| A PLEXOS **class** | A kind of object in your model. `Generator`, `Line` and `Constraint` are three classes. This document calls a loss at this level an **object-level** loss. |
| A PLEXOS **property** | A named value on one object, such as `Max Capacity` on a generator. This document calls a loss at this level a **property-level** loss. |
| **SiennaSchemas** | The published definition of what a Sienna file may hold. Refer to [Where the evidence comes from](#where-the-evidence-comes-from). |
| **A dispatch** | What `plexos-to-sienna` writes, and what PowerSimulations.jl then solves. |
| **A portfolio** | What `plexos-to-sienna-investments` writes beside the system, for an expansion plan. |
| `extensions.json` | A file tz-oss-interop writes beside `system.json`. It holds values that tz-oss-interop reads and Sienna has no field for, so that a later run of ours can read them back. Sienna never reads it. |
| `decisions.md` | A file tz-oss-interop writes beside the output of every run. It holds one row for each component and each field the run left out, with the reason. |

## What counts as a row here

A row is here only when both of these are true:

1. **SiennaSchemas holds no type and no field for the thing.** A citation proves it.
2. **One of the three published models states it.** A run proves it. A loss nobody's model
   states is a guess, and a guess does not go in.

## What this document does not hold

Two other kinds of loss exist. Neither is a limit of Sienna, so neither is here.

| The loss | Where it belongs |
| --- | --- |
| SiennaSchemas holds the thing, and this translation does not write it yet | A ticket. The pull request that wrote this document lists each one. The route through a PyPSA network is our choice, so a value that route loses is a ticket too. |
| PowerSimulations.jl solves a different problem from the one PLEXOS solves | [The solve tutorial](../tutorials/solve.md) and the case studies |

### A worked example of the difference

Both a `Reserve` object and a `Constraint` object end up in the same place today: the
`extensions.json` file beside your `system.json`. Neither becomes a Sienna component. So the
two look like one kind of loss, and they are not. What SiennaSchemas states tells them apart.

**A `Reserve` is not in this document.** Say your model asks for 75 MW of spinning reserve
and names the 40 generators that can supply it. SiennaSchemas has a shape for exactly that.
The schema for a spinning reserve, `Operations/Service/OnlineReserve.json`, states a
`requirement` field in MW and a `reserve_direction` field that takes `UP`. The schema that
joins a device to a service, `Operations/Associations/ServiceAssociation.json`, gives one row
for each of the 40 generators. Every part of what your model said has somewhere to go. This
translation does not write it yet, which makes it our defect and a ticket.

**A `Constraint` is in this document.** Say your model holds 0.5 times the output of one unit,
plus 1.0 times the output of another, at or below 250 MW. No SiennaSchemas type anywhere
holds a weight against one component. So however well we write the translator, that
constraint has nowhere to go. That is a limit of Sienna, and it is a row below.

The sidecar changes neither answer. `extensions.json` is our own file, and Sienna does not
read it, so a record in it is not a Sienna home.

For what the translation does keep, refer to
[Translation from PLEXOS to Sienna](translation-from-plexos-to-sienna.md) and to
[Translation from PLEXOS to a Sienna investments portfolio](translation-from-plexos-to-sienna-investments.md).

## Where the evidence comes from

### SiennaSchemas, and how to check a citation

SiennaSchemas is the published definition of what a Sienna file may hold. It is a set of JSON
Schema files at [github.com/NREL-Sienna/SiennaSchemas](https://github.com/NREL-Sienna/SiennaSchemas).
One file states one Sienna type: the name of each field, the type each field takes, and which
fields a document must state. If a value has no field in those files, then no Sienna system
can carry it, whatever a translator does. That is why this document tests every claim against
them and not against the Julia packages that read them.

**Every claim below is against one version.** The repository's own README says it is pre-1.0,
that any release may change the schemas incompatibly, and that a reader must pin an exact
tag. Its change log already records one type that went: `TopologyMapping.json`. So a sentence
about SiennaSchemas is only true against a stated version. Every claim below is against commit
`0057d603d697f616e19ee863db527117ededf470`, of 2026-09-18.

**How to read a citation.** A citation names the file, and then the field inside that file
after a `#`. So `Operations/Service/OnlineReserve.json#/properties/time_frame` means: open the
file `Operations/Service/OnlineReserve.json`, and read the `time_frame` entry in its
`properties` block. To check one yourself:

```bash
git clone https://github.com/NREL-Sienna/SiennaSchemas.git
cd SiennaSchemas
git checkout 0057d603d697f616e19ee863db527117ededf470
```

Some rows below name no file, because they state that nothing holds the value. Such a row
rests on a search of every field name in the repository at that commit, which is 823 distinct
names across the five namespaces. Where a row gives that number, it is naming the set that was
searched.

### The three runs

Each run used tz-oss-interop 0.1.0, and the model and the pipeline below. Each case study under
[`docs/case_studies/`](../case_studies/) gives the download and the checksum of its model.

| Model | Pipeline | What it gives this document |
| --- | --- | --- |
| CAISO 2026 Summer Assessment | `plexos-to-sienna` | A `Decision Variable`, the solver instructions on a generator, and a daily energy budget |
| SEM 2024-2032 | `plexos-to-sienna` | The settlement rules of a market, a wheeling charge, and a fuel blend |
| AEMO 2024 ISP Step Change | `plexos-to-sienna-investments` | An `MLF`, a `Purchaser`, the loss terms on a line, and every portfolio row |

## How to read a table

Every table below has the same three columns.

| Column | What it holds |
| --- | --- |
| What your model states | The PLEXOS class or the PLEXOS property, and what it means |
| Why Sienna has no home | The SiennaSchemas evidence. A named file, or the set that was searched. |
| Seen in | The model a run found it in, and how many |

A count in **Seen in** counts one of two things. For a class, it counts the objects of that
class in the model: `CAISO 373` means that model holds 373 `Constraint` objects. For a
property, it counts the rows that state the property: `AEMO 744` means 744 rows state a
`Marginal Loss Factor`. One object can state a property on several rows, because PLEXOS gives
a property one row for each date band or scenario it applies under.

---

## The object level, for a dispatch

A `plexos-to-sienna` run builds no Sienna component from any class below, and no version of
it could.

| What your model states | Why Sienna has no home | Seen in |
| --- | --- | --- |
| `Constraint`. A limit your model writes itself: a weighted sum over objects you name, held above or below a right-hand side. | SiennaSchemas states no generic constraint. No type in any of its five namespaces (`Core/`, `Operations/`, `Investments/`, `TimeSeries/` and `Dynamics/`) holds a field that weights one component inside a sum. The nearest things are the seven policy types under `Investments/Requirements/`, and each of those is one fixed form, such as a carbon cap in tonnes or a capacity floor in MW. Each one either covers the whole portfolio, or names its members through one row of `Investments/Associations/RequirementAssociation.json` for each member. No row holds a weight. | CAISO 373, AEMO 186, SEM 18 |
| `Decision Variable`. A variable you add to the optimisation yourself, with an upper bound, a lower bound and a coefficient in the objective. | SiennaSchemas states no user variable. No type holds a bound or an objective coefficient that a user writes. | CAISO 3 |
| `Timeslice`. A named set of periods, such as "summer weekday evenings", which you then state a value against. | SiennaSchemas states no timeslice. A time series record names its time axis by a start, a resolution and a length, so every period is the same length and no period carries a name. | AEMO 29, SEM 18, CAISO 3 |
| `Company`. The owner of a plant. | SiennaSchemas states no owner type and no owner field. The one field named `owner_id` belongs to a time series record, where it names the component the series belongs to, and not a company. | SEM 36, AEMO 4 |
| `MLF`. A marginal loss factor, written as an intercept and a flow coefficient, which derates what a generator delivers to the market. | SiennaSchemas states no loss factor on any component. The schema for an AC line, `Operations/Branch/Line.json`, holds resistance, reactance, susceptance, conductance, three ratings and its angle limits, and no loss term. | AEMO 6 |
| The run settings: `Model`, `Horizon`, `PASA`, `MT Schedule`, `ST Schedule`, `Production`, `Competition`, `Performance`, `Diagnostic`, `Report` and `Transmission`. | These tell PLEXOS how to run a study. A SiennaSchemas document states a system, and never a run. PowerSimulations.jl takes the settings of a solve from its own code, and reads none of them from the system file. | All three models |

## The object level, for a portfolio

Every row above is also absent from a portfolio. One row differs, because a portfolio holds
policy limits that a dispatch system does not.

| What your model states | Why Sienna has no home | Seen in |
| --- | --- | --- |
| A `Constraint` that weights a named subset of your model, such as "count each wind farm once and each solar farm at 0.6". | The seven types under `Investments/Requirements/` hold a cap, a floor, a share and a reserve margin. Each one names its members through one row of `Investments/Associations/RequirementAssociation.json` for each member, and that row states a `requirement_id` and an `entity_id` and nothing else. No field anywhere holds a weight for a member. So a constraint whose members carry different coefficients cannot be written. | AEMO 84 of 186 |

---

## The property level, for a dispatch

Each property below sits on a component that does translate. The component reaches Sienna and
this one value does not.

### On a `Generator`

| What your model states | Why Sienna has no home | Seen in |
| --- | --- | --- |
| `Marginal Loss Factor`. The factor that derates what a unit delivers, to account for the losses between it and the market. | No Sienna type holds a loss factor. None of the 823 field names in SiennaSchemas is one. | AEMO 744, SEM 107 |
| `Aux Incr`. The auxiliary load a unit draws for each MW it makes, such as the power its own pumps and fans use. | The schema for a thermal generator, `Operations/StaticInjection/ThermalStandard.json`, holds no auxiliary load and no parasitic load. No other type holds one either. | AEMO 748 |
| `Firm Capacity`. The share of a unit's capacity that counts towards a reserve margin. | SiennaSchemas states no firm capacity and no derating factor. The reserve margin type, `Investments/Requirements/CapacityReserveMargin.json`, states one fraction for the whole requirement, and nothing per unit. | AEMO 8480 |
| `Max Capacity Factor`, `Min Capacity Factor`, `Min Capacity Factor Year`. Bounds on the share of the year a unit may run at. | SiennaSchemas states no capacity factor limit on a plant that runs. The build candidate type, `Investments/Technologies/SupplyTechnology.json`, holds a `min_generation_fraction`, and no operations type holds the same bound. | AEMO 12, 44 and 222 |
| `Max Energy Day`, `Max Starts Day`. How much a unit may make in one day, and how often it may start in one day. | SiennaSchemas holds no energy budget and no start budget over a period you choose. It states two period limits, and neither fits: a weekly energy limit that applies to an import cost alone (`Core/common.json#/$defs/ImportExportCost`), and a count of storage cycles in a year (`EnergyReservoirStorage.cycle_limits`). | CAISO 6 and 18 |
| `Max Replacement`. How much plant a maintenance schedule may take out at once. | The planned outage type, `Operations/SupplementalAttributes/PlannedOutage.json`, holds an outage schedule and no limit on how much plant that schedule may cover. | CAISO 67 |
| `Run Up Rate`. The rate a unit takes from zero up to its minimum stable level, which is slower than its ramp rate above that level. | The thermal generator type holds one `ramp_limits` field, giving one up rate and one down rate. SiennaSchemas states no separate rate for synchronising. | CAISO 591 |
| `Offer Quantity Format`, `Max Heat Rate Tranches`. How many bands PLEXOS reads a curve in, and in what form. | A SiennaSchemas curve states its own points: the piecewise type `Core/common.json#/$defs/PiecewiseStepData` holds the breakpoints and the rate in each band. So the curve carries its own shape, and a count of bands tells a reader nothing more. | SEM 113 and 86 |
| The solver instructions: `Random Number Seed`, `Unit Commitment Optimality`, `Min Up Time Penalty`, `Max Ramp Up Penalty` and `Max Ramp Down Penalty`. | These tune the PLEXOS solve, and are not properties of the plant. A SiennaSchemas document states a system, and no penalty a solve charges for breaking a constraint. | CAISO 453, 231, 201, 2 and 2 |

### On a `Region` or a `Node`

| What your model states | Why Sienna has no home | Seen in |
| --- | --- | --- |
| `Price of Dump Energy`. What it costs to spill electricity the system cannot use. | SiennaSchemas prices no spilled electricity. No field name in the repository holds `dump`. The one nearby field, `spillage_cost` on a hydro reservoir, prices spilled water. | CAISO 5, SEM 1 |
| `Allow Dump Energy`, `Allow Unserved Energy`. Two switches that let a solve spill energy, or fail to serve a load. | Sienna states a resource, not a switch. A system either holds a sheddable load (`Operations/StaticInjection/InterruptiblePowerLoad.json`) or does not, and that is the whole answer. | SEM 1 and 1 |
| `Price Cap`, `Price Floor`. The highest and lowest price the market may settle at. | SiennaSchemas bounds no market price. No field name holds `price_cap`. | SEM 2 and 1 |
| `Pool Type`, `Generator Settlement Model`, `Load Settlement Model`, `Uplift Enabled`, `Uplift Compatibility`, `Uplift Detect Active Ramp Constraints`, `Uplift Detect Active Min Stable Level Constraints`. | These state how a market settles a dispatch, and pays generators on top of the energy price. SiennaSchemas states the physical system and its costs, and holds no settlement rule. | SEM 12 rows, CAISO 10 rows |
| `Load Risk`, `Maintenance Factor`. Two inputs that scale a reliability study. | SiennaSchemas holds outage data on each component, through the forced outage type `Operations/SupplementalAttributes/GeometricDistributionForcedOutage.json`. It holds no factor that scales a whole study. | CAISO 8 and 48 |
| `Load Includes Losses`, `Load Metering Point`. Where in the network the model measures a load. | A Sienna load states the bus it sits on, and nothing about where it was metered. | AEMO 5 and 5 |

### On a `Line`

| What your model states | Why Sienna has no home | Seen in |
| --- | --- | --- |
| `Wheeling Charge`, `Wheeling Charge Back`. What it costs to move a MW along the line, in each direction. | The AC line type, `Operations/Branch/Line.json`, prices no flow. It holds resistance, reactance, susceptance, conductance, three ratings and its angle limits, and no cost field. The limited variant, `MonitoredLine.json`, adds flow limits and still no cost. | SEM 20,736 rows each |
| `Loss Allocation`, `Loss Incr`, `Loss Incr Back`, `Loss Incr2`, `Loss Incr2 Back`, `Loss Base`, `Loss Base Back`, `Marginal Loss Factor`, `Marginal Loss Factor Back`. The loss curve of the line, as a base term and one or two incremental terms per direction. | A Sienna AC line carries no loss term of any kind. A loss field does exist on the HVDC types and on the transport technology a plan may build, and on no AC line. | AEMO 18, 5, 5, 5, 5, 3, 3, 3 and 3 |
| `Max Capacity Reserves`, `Min Capacity Reserves`. What the line contributes to a capacity reserve, which is a measure of whether enough plant exists to meet the peak. | The `Operations/` namespace holds no capacity reserve requirement at all, so nothing there could read a contribution to one. The operating reserve types hold MW of headroom during a dispatch, which is a different quantity. | AEMO 111 each |

### On a `Storage` or a `Battery`

| What your model states | Why Sienna has no home | Seen in |
| --- | --- | --- |
| `Max Cycles Day`. How many times the unit may charge and discharge in one day. | The storage type, `Operations/StaticInjection/EnergyReservoirStorage.json`, holds a `cycle_limits` field, and its own description states that the number counts cycles per year. SiennaSchemas holds no daily limit. | AEMO 24 |
| `Balance Period`, `Decomposition Method`. How PLEXOS splits the horizon when it solves the storage. | These describe a solve, and not the unit. A SiennaSchemas document states a system. | AEMO 18, CAISO 6 |

### On a `Reserve`

A reserve requirement itself is **not** in this document, because SiennaSchemas states three
reserve types and we simply do not write them yet. Refer to
[A worked example of the difference](#a-worked-example-of-the-difference). One property of a
reserve has no home even after we do write them.

| What your model states | Why Sienna has no home | Seen in |
| --- | --- | --- |
| `Mutually Exclusive`. That a unit may serve this reserve or another one, and never both at once. | The two reserve types, `Operations/Service/OnlineReserve.json` and `OfflineReserve.json`, hold no exclusion between one service and another. A unit joins a service through one `Operations/Associations/ServiceAssociation.json` row, which states the service and the unit and nothing more. | CAISO 7 reserves |

### On a `Fuel`

| What your model states | Why Sienna has no home | Seen in |
| --- | --- | --- |
| `Ratio`. The share of the heat input that one fuel gives, where a unit burns several at once. | A Sienna fuel curve (`Core/common.json#/$defs/FuelCurve`) states one fuel price for one curve, and a thermal generator names one fuel. A blend does have a home on a build candidate, in `SupplyTechnology.cofire_level_limits`, and no type holds a blend for a plant that already runs. | SEM 29 |
| `Tax`. A tax on the fuel a unit burns. | SiennaSchemas taxes an emission, through `Investments/Requirements/CarbonTax.json`, and taxes no fuel. | AEMO 82 |

### On a `Purchaser`

A purchaser is an entity that buys energy under an obligation. The object itself is not in
this document, because SiennaSchemas holds demand-side types that suit it. Two of its
properties have no home.

| What your model states | Why Sienna has no home | Seen in |
| --- | --- | --- |
| `Max Energy Month`, `Min Energy Month`. The band of energy the purchaser must take in a month. | SiennaSchemas holds no monthly energy band. No field name in the repository holds `month`. The nearest field states one week, and applies to an import cost alone. | AEMO 5040 each |
| `Load Obligation`. The share of a region's load this purchaser must serve. | SiennaSchemas states no obligation to serve a share of a load. | AEMO 15 |

### On a `Waterway`

A waterway is the route that carries water from one reservoir to the next. The object itself
is not in this document, because a Sienna reservoir names the reservoir above it, which gives
a cascade a home. One property of the route has no home.

| What your model states | Why Sienna has no home | Seen in |
| --- | --- | --- |
| `Max Flow Penalty`. What it costs to push more water down the route than the route allows. | The reservoir type, `Operations/StaticInjection/HydroReservoir.json`, holds spillage limits and a spillage cost, which price spilled water at one reservoir. No type prices a flow above a limit on the route between two of them. | CAISO 1 |

---

## The property level, for a portfolio

A portfolio holds the technologies a plan may build and the policy limits it must meet. Every
row above still applies, because the portfolio names the dispatch system it sits beside. This
section holds only what the portfolio itself cannot state.

| What your model states | Why Sienna has no home | Seen in |
| --- | --- | --- |
| A `Constraint` that holds its weighted sum to an equality, rather than to a ceiling or a floor. | Each type under `Investments/Requirements/` states one side only. `MaximumCapacityRequirements.json` states a ceiling in MW, `MinimumCapacityRequirements.json` a floor in MW, `CarbonCaps.json` a ceiling in tonnes, and `EnergyShareRequirements.json` a floor as a fraction of generation. No type states two sides together, and none states an equality. | AEMO 3 of 186 |
| `RHS Day`, `RHS Hour` on a `Constraint`. A right-hand side that applies again in each day, or in each hour, rather than once over the horizon. | Each type under `Investments/Requirements/` states one limit and one `target_year`, which is the year the limit applies in. SiennaSchemas states no limit that repeats over a shorter span. | `RHS Day`: AEMO 354, CAISO 211, SEM 48. `RHS Hour`: SEM 1 |
| `RHS Custom` on a `Constraint`. A right-hand side over a span you define yourself. | A custom span is a span the schema does not name, and each requirement type states a `target_year` and nothing else. | AEMO 21 |

---

## What a row here does not say

A row says that SiennaSchemas has no home for the thing. It does not say that the thing is
unimportant, and it does not say that a solve gives a wrong answer without it. The two differ
by a lot: a `Constraint` that caps the emissions of a fleet changes a dispatch, and a
`Generator Settlement Model` does not.

Two places say what each loss does to your numbers:

- The case study of your model, under [`docs/case_studies/`](../case_studies/). Each one
  states what its run measured, and what the measurement does not cover.
- The `decisions.md` file the run writes beside its output. It names every component and every
  field the run left out, one row each, with the reason.
