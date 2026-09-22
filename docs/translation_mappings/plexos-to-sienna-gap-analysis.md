# What a PLEXOS model states that Sienna has no home for

This document answers one question. Which things does a PLEXOS model state that a
`plexos-to-sienna` run or a `plexos-to-sienna-investments` run does not translate, because
SiennaSchemas holds no type and no field for them?

A row is here only if both of these are true:

- SiennaSchemas holds no type and no field for the thing.
- One of the three published models in [the case studies](../case_studies/) states it.

## What this document does not hold

Two other kinds of loss exist. Neither of them is here.

| The loss | Where it belongs |
| --- | --- |
| SiennaSchemas holds the thing, and this translation does not write it yet | A ticket. The pull request that wrote this document lists each one. The route through a PyPSA network is our choice, so a value the route loses is a ticket too. |
| PowerSimulations.jl solves a different problem from the one PLEXOS solves | [The solve tutorial](../tutorials/solve.md) and the case studies |

The `extensions.json` sidecar carries each `Reserve` and each `Constraint` that the
translator can read. The sidecar is our own file, and Sienna does not read it, so a record in
it is not a Sienna home. The two objects go to the same file, and they are not the same kind
of loss. What SiennaSchemas states tells them apart:

- **A `Reserve` is not in this document.** Your model asks for 75 MW of spinning reserve, and
  names the generators that can supply it. `Operations/Service/OnlineReserve.json` states a
  `requirement` in MW and a `reserve_direction` of `UP`, and one
  `Operations/Associations/ServiceAssociation.json` row names each of those generators. Every
  part of what your model said has somewhere to go, and this translation does not write it
  yet, so it is a ticket.
- **A `Constraint` is in this document.** Your model holds 0.5 times the output of one unit,
  plus 1.0 times the output of another, at or below 250 MW. No SiennaSchemas type states a
  weight against one component, so no translation can write this constraint.

For what the translation keeps, refer to
[Translation from PLEXOS to Sienna](translation-from-plexos-to-sienna.md) and to
[Translation from PLEXOS to a Sienna investments portfolio](translation-from-plexos-to-sienna-investments.md).

## The evidence

Every row names a SiennaSchemas file, and the model that states the thing.

**SiennaSchemas.** Commit `0057d603d697f616e19ee863db527117ededf470`, 2026-09-18. The
repository makes no compatibility promise, so a citation with no commit goes stale. A
citation gives the file path, and the field after a `#`, such as
`Operations/Service/OnlineReserve.json#/properties/time_frame`.

**The runs.** Each one used the pipeline and the model below, at interop 0.1.0.

| Model | Pipeline | What it gives this document |
| --- | --- | --- |
| CAISO 2026 Summer Assessment | `plexos-to-sienna` | A `Decision Variable`, the solver instructions on a generator, and a daily energy budget |
| SEM 2024-2032 | `plexos-to-sienna` | The settlement rules of a market, a wheeling charge, and a fuel blend |
| AEMO 2024 ISP Step Change | `plexos-to-sienna-investments` | An `MLF`, a `Purchaser`, the loss terms on a line, and every portfolio row |

A count in the **Seen in** column is the quantity of objects of that class, or the quantity
of rows that state that property, in that model.

## How to read a row

| Column | What it holds |
| --- | --- |
| What your model states | The PLEXOS class or the PLEXOS property |
| Why Sienna has no home | The SiennaSchemas evidence for the absence |
| Seen in | The published model that states it, and how many |

---

## The object level, for a dispatch

A `plexos-to-sienna` run builds no Sienna component from any class below.

| What your model states | Why Sienna has no home | Seen in |
| --- | --- | --- |
| `Constraint`. A weighted sum over named objects, held above or below a right-hand side. | SiennaSchemas states no generic constraint. No type in `Core/`, `Operations/`, `Investments/`, `TimeSeries/` or `Dynamics/` holds a field that weights one component inside a sum. The seven `Investments/Requirements/` types are fixed policy forms. Each one holds the whole portfolio, or takes one `Investments/Associations/RequirementAssociation.json` row for each member, and no row holds a weight. | CAISO 373, AEMO 186, SEM 18 |
| `Decision Variable`. A variable of the user's own, with an upper bound, a lower bound and a coefficient in the objective. | SiennaSchemas states no user variable. No type holds a bound or an objective coefficient of the user's own. | CAISO 3 |
| `Timeslice`. A named set of periods, which a value is stated against. | SiennaSchemas states no timeslice. A `TimeSeriesAssociation` names a time axis by its start, its resolution and its length, and no type groups periods under a name. | AEMO 29, SEM 18, CAISO 3 |
| `Company`. The owner of a plant. | SiennaSchemas states no owner type and no owner field. The `owner_id` field of a `TimeSeriesAssociation` names the component the series belongs to, and not a company. | SEM 36, AEMO 4 |
| `MLF`. A marginal loss factor, as an intercept and a flow coefficient. | SiennaSchemas states no loss factor on any component. A `Line` holds `r`, `x`, `b` and its ratings, and no loss term. | AEMO 6 |
| The run settings: `Model`, `Horizon`, `PASA`, `MT Schedule`, `ST Schedule`, `Production`, `Competition`, `Performance`, `Diagnostic`, `Report` and `Transmission`. | A SiennaSchemas document states a system. It states no run. PowerSimulations.jl holds the settings of a solve, and reads none of them from the system file. | All three models |

## The object level, for a portfolio

A `plexos-to-sienna-investments` run writes a portfolio beside the system. Each row of the
table above is also absent from the portfolio. One row differs.

| What your model states | Why Sienna has no home | Seen in |
| --- | --- | --- |
| A `Constraint` that weights a named subset of the model. | The `Investments/Requirements/` types hold a cap, a floor, a share and a reserve margin. Each one takes one `Investments/Associations/RequirementAssociation.json` row for each member, and that row states a `requirement_id` and an `entity_id` and nothing else. No field holds a per-member weight. So a constraint whose members carry different coefficients has no home. | AEMO 84 of 186 |

---

## The property level, for a dispatch

Each property below is on a component that does translate. The component reaches Sienna
and the property does not.

### On a `Generator`

| What your model states | Why Sienna has no home | Seen in |
| --- | --- | --- |
| `Marginal Loss Factor` | No Sienna type holds a loss factor. The 823 property names in SiennaSchemas hold none. | AEMO 744, SEM 107 |
| `Aux Incr`. The auxiliary load a unit draws for each MW it makes. | `Operations/StaticInjection/ThermalStandard.json` holds no auxiliary load and no parasitic load. No other type holds one. | AEMO 748 |
| `Firm Capacity`. The capacity that counts towards a reserve margin. | SiennaSchemas states no firm capacity and no derating factor. `Investments/Requirements/CapacityReserveMargin.json` states one fraction for the whole requirement, and no per-unit contribution. | AEMO 8480 |
| `Max Capacity Factor`, `Min Capacity Factor`, `Min Capacity Factor Year` | SiennaSchemas states no capacity factor limit. `Investments/Technologies/SupplyTechnology.json#/properties/min_generation_fraction` bounds a candidate technology, and no operations type holds the same bound. | AEMO 12, 44 and 222 |
| `Max Energy Day`, `Max Starts Day` | SiennaSchemas holds no energy budget and no start budget over a period. The only period limits are `Core/common.json#/$defs/ImportExportCost/properties/energy_import_weekly_limit`, which is one week and applies to an import cost alone, and `EnergyReservoirStorage.cycle_limits`, which counts cycles in a year. | CAISO 6 and 18 |
| `Max Replacement`. How much plant a maintenance schedule may replace. | `Operations/SupplementalAttributes/PlannedOutage.json` holds an `outage_schedule` and no replacement limit. | CAISO 67 |
| `Run Up Rate`. The rate a unit takes from zero to its minimum stable level. | `ThermalStandard.ramp_limits` holds one up rate and one down rate. SiennaSchemas states no separate synchronising rate. | CAISO 591 |
| `Offer Quantity Format` and `Max Heat Rate Tranches`. How PLEXOS reads the bands of a curve. | A SiennaSchemas curve states its own points. `Core/common.json#/$defs/PiecewiseStepData` holds the breakpoints and the rates, so a count of bands states nothing a reader needs. | SEM 113 and 86 |
| The solver instructions: `Random Number Seed`, `Unit Commitment Optimality`, `Min Up Time Penalty`, `Max Ramp Up Penalty` and `Max Ramp Down Penalty`. | A SiennaSchemas document states a system, and no penalty a solve applies to a relaxed constraint. | CAISO 453, 231, 201, 2 and 2 |

### On a `Region` or a `Node`

| What your model states | Why Sienna has no home | Seen in |
| --- | --- | --- |
| `Price of Dump Energy` | SiennaSchemas prices no spilled energy. No property name in the repository holds `dump`. `HydroReservoirCost.spillage_cost` prices spilled water on a reservoir, and nothing prices spilled electricity on an area. | CAISO 5, SEM 1 |
| `Allow Dump Energy`, `Allow Unserved Energy` | Sienna states a shortfall resource, and not a switch. A system either holds an `Operations/StaticInjection/InterruptiblePowerLoad.json` or does not. | SEM 1 and 1 |
| `Price Cap`, `Price Floor` | SiennaSchemas bounds no market price. No property name holds `price_cap`. | SEM 2 and 1 |
| `Pool Type`, `Generator Settlement Model`, `Load Settlement Model`, `Uplift Enabled`, `Uplift Compatibility`, `Uplift Detect Active Ramp Constraints`, `Uplift Detect Active Min Stable Level Constraints` | These state how a market settles a dispatch. SiennaSchemas states the physical system and the costs. It holds no settlement rule. | SEM 12 rows, CAISO 10 rows |
| `Load Risk`, `Maintenance Factor` | These scale a reliability study. SiennaSchemas holds outage data per component, in `Operations/SupplementalAttributes/GeometricDistributionForcedOutage.json`, and no study-wide factor. | CAISO 8 and 48 |
| `Load Includes Losses`, `Load Metering Point` | These state where the model measures a load. A Sienna `PowerLoad` states the bus it sits on and no metering point. | AEMO 5 and 5 |

### On a `Line`

| What your model states | Why Sienna has no home | Seen in |
| --- | --- | --- |
| `Wheeling Charge`, `Wheeling Charge Back` | `Operations/Branch/Line.json` prices no flow. It holds `r`, `x`, `b`, `g`, three ratings and its angle limits, and no cost field. `MonitoredLine` adds `flow_limits` and no cost. | SEM 20,736 rows each |
| `Loss Allocation`, `Loss Incr`, `Loss Incr Back`, `Loss Incr2`, `Loss Incr2 Back`, `Loss Base`, `Loss Base Back`, `Marginal Loss Factor`, `Marginal Loss Factor Back` | A Sienna AC `Line` carries no loss term. A loss field exists on the HVDC types and on `Investments/Technologies/AggregateTransportTechnology.json#/properties/line_loss`, and on no AC line. | AEMO 18, 5, 5, 5, 5, 3, 3, 3 and 3 |
| `Max Capacity Reserves`, `Min Capacity Reserves` | These state what a line contributes to a capacity reserve. `Operations/` holds no capacity reserve requirement, so nothing reads a contribution to one. | AEMO 111 each |

### On a `Storage` or a `Battery`

| What your model states | Why Sienna has no home | Seen in |
| --- | --- | --- |
| `Max Cycles Day` | `Operations/StaticInjection/EnergyReservoirStorage.json#/properties/cycle_limits` counts cycles in a year. SiennaSchemas holds no daily cycle limit. | AEMO 24 |
| `Balance Period`, `Decomposition Method` | These state how PLEXOS splits a solve. A SiennaSchemas document states a system, and not a solve. | AEMO 18, CAISO 6 |

### On a `Reserve`

A `Reserve` reaches the `extensions.json` sidecar, and SiennaSchemas holds three reserve
types, so the reserve itself is not in this document. One of its properties has no home.

| What your model states | Why Sienna has no home | Seen in |
| --- | --- | --- |
| `Mutually Exclusive`. That a unit may serve this reserve or another one, and not both. | `Operations/Service/OnlineReserve.json` and `OfflineReserve.json` hold no exclusion between two services. A unit joins a service through `Operations/Associations/ServiceAssociation.json`, which holds a service and an entity and nothing more. | CAISO 7 reserves |

### On a `Fuel`

| What your model states | Why Sienna has no home | Seen in |
| --- | --- | --- |
| `Ratio`. The share of the heat input one fuel gives, where a unit burns several. | A Sienna `Core/common.json#/$defs/FuelCurve` states one `fuel_cost` for one curve, and `ThermalStandard.fuel` names one fuel. `Investments/Technologies/SupplyTechnology.json#/properties/cofire_level_limits` holds a blend for a build candidate, and `Operations/` holds no blend for a plant that runs. | SEM 29 |
| `Tax`. A tax on the fuel a unit burns. | `Investments/Requirements/CarbonTax.json#/properties/tax_dollars_per_ton` taxes an emission. SiennaSchemas taxes no fuel. | AEMO 82 |

### On a `Purchaser`

A `Purchaser` buys energy under an obligation. SiennaSchemas holds demand-side types, so
the object is not in this document. Two of its properties have no home.

| What your model states | Why Sienna has no home | Seen in |
| --- | --- | --- |
| `Max Energy Month`, `Min Energy Month` | SiennaSchemas holds no monthly energy band. No property name holds `month`. The nearest field is the weekly import limit on `Core/common.json#/$defs/ImportExportCost`, which states one week and applies to an import cost alone. | AEMO 5040 each |
| `Load Obligation` | SiennaSchemas states no obligation to serve a share of a load. | AEMO 15 |

### On a `Waterway`

A `HydroReservoir` names the reservoir above it, so a cascade has a home and the
`Waterway` object is not in this document. One of its properties has no home.

| What your model states | Why Sienna has no home | Seen in |
| --- | --- | --- |
| `Max Flow Penalty`. The price of a flow above the limit of the route. | `Operations/StaticInjection/HydroReservoir.json` holds `spillage_limits` and `spillage_cost`, which price spilled water at a reservoir. No type prices a flow above a limit on the route between two reservoirs. | CAISO 1 |

---

## The property level, for a portfolio

A portfolio holds a technology a plan may build. Each row above applies to the system the
portfolio names in `base_system_file`, so this section holds only what the portfolio itself
cannot state.

| What your model states | Why Sienna has no home | Seen in |
| --- | --- | --- |
| A `Constraint` that holds its weighted sum to an equality. | Each `Investments/Requirements/` type states one side. `MaximumCapacityRequirements.json` states a ceiling in MW, `MinimumCapacityRequirements.json` states a floor in MW, `CarbonCaps.json` states a ceiling in tonnes, and `EnergyShareRequirements.json` states a floor as a fraction. No type states two sides together, and no type states an equality. | AEMO 3 of 186 |
| `Constraints.RHS Day`, `RHS Hour`. A right-hand side that applies again in each day, or in each hour. | Each `Investments/Requirements/` type states one limit and a `target_year`. SiennaSchemas states no right-hand side that repeats over a day or an hour. | `RHS Day`: AEMO 354, CAISO 211, SEM 48. `RHS Hour`: SEM 1 |
| `Constraints.RHS Custom` | A custom span is a span the schema does not name. Each requirement type states a `target_year` alone. | AEMO 21 |

---

## What a row here does not say

A row states that SiennaSchemas holds no home. It does not state that the value is
unimportant, and it does not state that a solve gives the wrong answer without it. A
`Constraint` that caps the emissions of a fleet changes a dispatch, and a
`Generator Settlement Model` does not.

Two documents say what each loss does to a number: the case study of each model under
[`docs/case_studies/`](../case_studies/), and the `decisions.md` file each run writes beside
its output. `decisions.md` names every component and every field the run left out, one row
each.
