# What a PLEXOS to Sienna translation loses

This document lists each thing a PLEXOS to Sienna run loses. Each part below names the run it
covers.

For what the translation keeps, refer to
[Translation from PLEXOS to Sienna](translation-from-plexos-to-sienna.md), and for the
portfolio to
[Translation from PLEXOS to a Sienna investments portfolio](translation-from-plexos-to-sienna-investments.md).

Each entry gives four things:

| Heading | Meaning |
| --- | --- |
| The PLEXOS data | What your model states |
| What happens to it | Where it goes, or that it goes nowhere |
| The cause | Why |
| The effect on the dispatch, or on the expansion | What the solve, or a plan built from the portfolio, then does differently from your PLEXOS model |

---

## What `plexos-to-sienna` loses from a dispatch

These entries cover the translation and the validation run that proves the system solves in
PowerSimulations.jl.

### Reserve requirements

**The PLEXOS data.** Each `Reserve` object, its type, its requirement in MW or as a share of
a profile, and the generators that can provide it.

**What happens to it.** The reserve reaches the `extensions.json` sidecar beside the system,
and a requirement that varies reaches the `reserves.parquet` companion beside that. No Sienna
component is built from it.

**The cause.** SiennaSchemas has `VariableReserve` and `ConstantReserve`, and this translation
writes neither yet. The record carries everything one needs, so the reserve is set aside
rather than lost.

**The effect on the dispatch.** The dispatch keeps no reserve headroom. Every generator can
run at full output, so the dispatch is less constrained than the dispatch in your PLEXOS
model, and a scarcity price your model shows does not appear.

---

### Load shedding, on a plain run

**The PLEXOS data.** Each Region states a `VoLL`, the value of lost load.

**What happens to it.** A `plexos-to-sienna` or `plexos-to-sienna-monte-carlo` run drops it,
and the system gets no resource a solve can cut. A `plexos-to-sienna-monte-carlo-reliability`
run keeps it: refer to
[Region `Load` -> `InterruptiblePowerLoad`](translation-from-plexos-to-sienna.md#region-load--interruptiblepowerload).

**The cause.** Only the reliability chain adds a load shedding resource, on both sides of the
PyPSA hub. The plain chains stay faithful to a model that states no such resource.

**The effect on the dispatch.** A window whose capacity is less than its load does not solve,
and no run reports the unserved energy. The solve returns a status that is not optimal rather
than a shortfall in MWh. Run the reliability chain to get the shortfall in MWh instead.

---

### Unit commitment, relaxed

**The PLEXOS data.** A start cost, a minimum up time and a minimum down time on each thermal
generator.

**What happens to it.** The translation carries all three onto `ThermalStandard`. The solve
applies them only when you answer `exact` at the unit commitment prompt. The answer
`linearised` selects `ThermalBasicDispatch`, which has no on/off variable, so it applies
neither.

**The cause.** PowerSimulations exposes no relaxed unit commitment formulation. Its thermal
formulations are either a true mixed-integer commitment or a dispatch with no commitment at
all. PyPSA has a relaxation, so the same answer keeps the start cost and the time limits on
that path and drops them here.

**The effect on the dispatch.** A `linearised` Sienna solve starts a generator for free and
holds it on for as little as one snapshot. It therefore costs less than the same window
solved as `exact`, and less than the same window solved in PyPSA with the answer
`linearised`. Sienna should expose a relaxed commitment formulation, and until it does the
two paths do not compare under that answer.

---

### Thermal availability where the model states none

**The PLEXOS data.** An `Outage Factor`, an `Outage Rating`, a `Rating` profile or a `Units
Out` profile on some of the thermal fleet, and nothing on the rest.

**What happens to it.** The translation gives an availability series only to a generator
whose availability changes with time. The validation run then gives a flat series at full
output to every other generator of that type, so the whole type carries one.

**The cause.** PowerSimulations binds an availability forecast for a whole component type or
for none of it. One generator without the series would stop every other generator's outage
profile from reaching the dispatch.

**The effect on the dispatch.** None on the generators that state an availability. A
generator that states none can run at its own static limit, which is what it could do
before. The flat series is redundant data in the PowerSimulations file, not a changed
number.

---

### A hydro unit whose inflow is water, not power

**The PLEXOS data.** A reservoir hydro turbine with a `Natural Inflow` stated in cumec or in
m³/day, or with no `Natural Inflow` at all.

**What happens to it.** The translation leaves that unit out. `decisions.md` names it, and
the log warns.

**The cause.** A `HydroDispatch` is dispatched against an energy budget, and the budget is
the inflow. Converting a flow of water into a power needs the head of the reservoir and the
efficiency of the turbine, and the translation reads neither. A unit with no budget would run
at full output every snapshot on water nobody stated.

**The effect on the dispatch.** That hydro capacity is absent, so the rest of the fleet
covers its output. Do not use a number from a model whose hydro states its inflow in water.
The AEMO 2024 ISP states every inflow in cumec, so its whole reservoir fleet is absent.

---

### A storage unit that states no energy

**The PLEXOS data.** A `Battery` with no `Capacity` and no `Duration`, or a pumped storage
head reservoir whose `Max Volume` is in water.

**What happens to it.** The translation leaves that unit out, and `decisions.md` names it.

**The cause.** A Sienna `EnergyReservoirStorage` holds a `storage_capacity`. A unit whose
capacity is zero can neither charge nor discharge, so writing it would add a device that does
nothing.

**The effect on the dispatch.** That storage capacity is absent, so nothing shifts energy
across the hours it would have covered.

---

### A generator that is not a power plant

**The PLEXOS data.** A generator whose category names a transmission augmentation, a policy
project or another pseudo-object rather than a technology.

**What happens to it.** Your carrier mappings file names the categories you want translated.
A generator whose category the file does not name is left out, and `decisions.md` names it.

**The cause.** PLEXOS models several things as generators, and only you know which of your
categories are power plants. The translation reads no meaning from a name.

**The effect on the dispatch.** A pseudo-object left out changes nothing, which is the point.
A real fleet left out by mistake is absent from the dispatch, so read `decisions.md` after
each run.

---

### Heat rate bands

**The PLEXOS data.** A `Heat Rate` stated as several bands, so the efficiency changes with
output.

**What happens to it.** The translation reads one average heat rate and writes one flat
`marginal_cost`, which becomes one linear `operation_cost.variable` cost curve on
`ThermalStandard`.

**The cause.** The chain goes through PyPSA, which holds one `marginal_cost` for each
generator. Sienna can hold a piecewise curve, but nothing reaches it through the hub.

**The effect on the dispatch.** A generator costs the same at every output, so the merit
order does not change as units load up. A model whose bands differ widely dispatches
differently.

---

### A generator that burns more than one fuel

**The PLEXOS data.** Several `Fuels` memberships on one generator.

**What happens to it.** The translation keeps the first fuel and drops the rest.
`decisions.md` names each dropped fuel.

**The cause.** A PyPSA generator carries one `carrier`, and a Sienna `ThermalStandard`
carries one `fuel`.

**The effect on the dispatch.** The generator always burns its first fuel, at that fuel's
price. A dual-fuel unit that your model switches to a cheaper fuel does not switch.

---

### A Fuel and a generator category of one name

**The PLEXOS data.** A `Fuel` and a generator category that share a name, for example a fuel
`HVO` and a category `HVO`.

**What happens to it.** Both become one PyPSA carrier, so both take one row of the carrier
mappings file. The run refuses to start when your mappings file gives that name two
different Sienna types.

**The cause.** A PyPSA `carrier` is free text with one namespace. The translation gives a
generator the name of its Fuel when it burns one and its category when it does not, so two
different PLEXOS concepts can produce one string.

**The effect on the dispatch.** None, once you state one Sienna type for the name. Both
groups of generators then take that type.

---

### Zones, interfaces and custom constraints

**The PLEXOS data.** `Zone` objects, `Interface` flow limits and `Constraint` objects, which
include energy budgets, running hour limits, RPS targets and emission caps.

**What happens to it.** The translation carries none of them. It does report every
`Constraint`, one entry for each right-hand side the constraint states, naming the sense
and every term of the weighted sum: the object, the class it belongs to, and the
coefficient weighting it.

**The cause.** The hub has no equivalent, and the Sienna types this translation writes have
none either. Nor does a PyPSA `GlobalConstraint`, which limits one carrier over the whole
horizon and cannot name a set of components.

**The effect on the dispatch.** Nothing applies a group flow limit, so a transfer your
PLEXOS model bounds can go higher. Nothing applies a renewable target or an emission cap.
Only the carbon price reaches the cost. Where a model caps the energy of a group of hydro
units, or the running hours of a group of peakers, with a `Constraint`, those resources are
free to run at nameplate over the whole horizon: read the reported entries before you trust
the dispatch.

---

### Hydro cascades and volumes in water

**The PLEXOS data.** `Waterway` objects joining reservoirs, and `Max Volume` and `Initial
Volume` stated in 1000 m³ or a `Natural Inflow` stated in cumec.

**What happens to it.** The translation drops the cascade route and leaves out a volume or
an inflow that it cannot convert into MWh. `decisions.md` names each one.

**The cause.** A conversion from a volume of water into an energy needs the head of the
reservoir and the efficiency of the turbine, and the translation reads neither.

**The effect on the dispatch.** Each reservoir is independent, so water released upstream
does not arrive downstream. A pumped storage unit whose `Max Volume` is dropped holds no
energy, so the translation leaves that unit out as well; refer to
[A storage unit that states no energy](#a-storage-unit-that-states-no-energy). Do not use a
number that depends on hydro.

---

### One solve, one window

**The PLEXOS data.** A Horizon, which can be many years long.

**What happens to it.** The translation writes one calendar year of snapshots at a time. The
Sienna solve then builds one optimisation covering every snapshot in the system.

**The cause.** The Sienna solve takes no date range, unlike the PyPSA solve. It reads the
length of the series and makes the horizon and the interval the whole of it.

**The effect on the dispatch.** A long series makes one very large program. The SEM
2024-2032 model is 66 thermal generators over 8,760 hourly snapshots. The AEMO 2024 ISP is
252 thermal generators over 8,688 half-hourly snapshots. As a linear program it takes much
more compute than the SEM 2024-2032 model does. To solve a shorter window, translate a
shorter year.

---

### Region Price of Dump Energy

**The PLEXOS data.** A Region `Price of Dump Energy`, the price of energy the system spills.

**What happens to it.** The translation drops it. `decisions.md` names it.

**The cause.** PyPSA has no home for it, and neither does the Sienna type this translation
writes for a Region.

**The effect on the dispatch.** Nothing prices spilled energy, so it does not appear in the
objective. The Region `VoLL` beside it does reach a reliability run: refer to
[Load shedding, on a plain run](#load-shedding-on-a-plain-run).

---

### Sienna holds no Monte Carlo forecast a solve reads

**The PLEXOS data.** A pre-sampled model states many values for one property at one snapshot,
one per replication, and a run over it draws a distribution of outcomes.

**What happens to it.** `plexos-to-sienna-monte-carlo` writes one whole Sienna system per
replication, each in a directory of its own, rather than one system holding every replication.

**The cause.** `InfrastructureSystems.jl` defines a `Scenarios` forecast, and PowerSimulations
refuses it: `add_parameters!` takes `AbstractDeterministic` and `StaticTimeSeries` and nothing
else. Attaching many same-named series to one component fails too, because a lookup by name
and type throws where it finds more than one. SiennaSchemas has no schema for either.

**The effect on the dispatch.** Each replication solves on its own, and nothing inside Sienna
counts how many of them lose load. Solve the replications and count the outcomes yourself.

---

### A Sienna objective and a PyPSA objective do not compare

**The PLEXOS data.** A Region `VoLL`, in a reliability run on both sides of the PyPSA hub.

**What happens to it.** PyPSA gets a shedding generator per bus whose marginal cost is the
`VoLL`. Sienna gets an `InterruptiblePowerLoad` per load whose `operation_cost` states the
same `VoLL`. Both shed the same energy at the same price.

**The cause.** The two frameworks price the same thing with opposite signs. A PyPSA shedding
generator adds `VoLL` times the shed MWh to the objective. PowerSimulations applies a
`LoadCost` to the load that is served, with a negative multiplier, so Sienna subtracts `VoLL`
times the supplied MWh instead.

**The effect on the dispatch.** None: the two dispatches match, because the two objectives
differ by a constant, and a constant changes no decision. But the two objective numbers are
not the same quantity and must not be compared or subtracted.

---

### A profile that reaches only some replications

**The PLEXOS data.** An outage draw that takes a unit out in one replication and leaves it
available through the whole window in another.

**What happens to it.** The ensemble leaves that unit's profile out of every replication, and
the unit keeps its static value throughout. The run warns and names a few of the units.

**The cause.** PyPSA writes no time-varying column for a component whose values never move off
the static value, so the unit has a profile in the replication that takes it out and none in
the replication that does not. One `system.json` serves the whole ensemble, so it states one
set of time-series associations, and a profile that does not reach every replication has no
place in them.

**The effect on the dispatch.** Those units are available throughout, in every replication, so
the replication that would have taken one out has more capacity than your PLEXOS model gives
it. On the CAISO 2026 Summer Assessment this covered 4 generators of the 411 the ensemble
holds.

---

### A reliability solve reports its unserved energy in the results files

**The PLEXOS data.** The energy a window cannot serve, which a reliability run prices at the
Region `VoLL`.

**What happens to it.** PowerSimulations writes the served power of each
`InterruptiblePowerLoad` to `results/.../variables/ActivePowerVariable__InterruptiblePowerLoad`.
The unserved energy is the load's `max_active_power` profile less that, summed over the window.

**The cause.** The results pipeline reads a load's dispatch from the parameter file
PowerSimulations writes for a `PowerLoad`. An interruptible load's served power is a decision
variable rather than a parameter, so it lands in a different file that the results pipeline
does not read yet.

**The effect on the dispatch.** None. The number is in the solve output; no report collects it
for you.

---

## What `plexos-to-sienna-investments` loses from an expansion

### A `Constraint` a cap cannot carry

**The PLEXOS data.** A `Constraint` holding a weighted sum over the objects it names to a
right-hand side: an emission cap over a group of plants, a target over one region, a budget
over one technology.

**What happens to it.** The portfolio writes a `CarbonCaps` only for a constraint that holds
its weighted sum to `<=`, states a right-hand side for a year or for the whole horizon, and
names every generator and storage object the base system and the portfolio hold. Every other
constraint is left out, `decisions.md` names it, and the log warns. Every constraint still
reaches the `extensions.json` sidecar, whether or not it became a cap.

**The cause.** `CarbonCaps` names no members and no region: a cap in a portfolio holds the
whole portfolio. A cap also states one ceiling over the whole run, so a constraint held to
`>=` or to `==`, and a constraint whose only right-hand side bounds a repeating window inside
the run, give it nothing to carry.

**The effect on the expansion.** Nothing bounds what the constraint names, so the plan may
build and run those objects up to their own limits. A model whose targets are all regional,
technology-scoped, or written as a floor reaches the portfolio with no cap at all. Read the
constraints in the sidecar before you trust what the plan builds.

---

### A candidate whose build nothing prices

**The PLEXOS data.** A `Generator`, a `Battery` or a pumped-storage turbine stating `Max Units
Built` but not all of `Build Cost`, `WACC` and `Economic Life`.

**What happens to it.** The PLEXOS leg leaves the build out. An object with nothing running
yet is its build and nothing else, so the whole object goes and `decisions.md` names it. An
object that already runs keeps the capacity it runs, and only the build it may add is
dropped. The second leg drops a candidate that reaches it with no finite upper bound on
capacity, no finite lifetime, no overnight cost or no discount rate, and names each one the
same way.

**The cause.** PyPSA annuitises an overnight cost with a discount rate over a lifetime. It
refuses a network that states an overnight cost and no discount rate, it prices a build with
no lifetime as a perpetuity, and it builds for free a candidate that states no overnight cost
at all. A Sienna technology states its own price and its own financing, and
`TechnologyFinancialData` requires both a return on equity and a capital recovery period.

**The effect on the expansion.** That candidate is not in the portfolio, so no plan built
from it can build that technology.

---

### Transmission a plan may build

**The PLEXOS data.** A `Line` or a transformer the plan may expand, and the `Line.Type` that
says which technology LT Plan expands it with.

**What happens to it.** Neither leg writes an expandable branch. The base system holds each
line and each link at the rating it already has, and the portfolio holds no technology for a
corridor.

**The cause.** SiennaSchemas states transport technologies of its own, and this translation
writes none of them. The PLEXOS leg fixes the capacity of every line and link, so nothing
reaches the hub for a second leg to read either.

**The effect on the expansion.** The network is fixed. A plan can put new capacity only where
the corridors that already exist can carry it, so it builds nearer to the demand than your
model would, and an expansion your model meets by reinforcing a corridor is met by generation
or not at all.

---

### The requirements a technology names

**The PLEXOS data.** The objects a `Constraint` names, and the coefficient weighting each
one.

**What happens to it.** The portfolio writes no `requirements`: the field is absent from every
`SupplyTechnology`, `StorageTechnology` and `DemandRequirement`, and `decisions.md` records it
as not mapped.

**The cause.** `requirements` holds the ids of the requirements a component is subject to.
The only requirement this translation writes is the cap above, which names no members, so no
component names it. SiennaSchemas states other requirement types beside it, and this
translation writes none of them.

**The effect on the expansion.** A consumer that applies a requirement to the technologies
naming it applies nothing to any of them.

---

### The year a cap applies in, and a cap on carbon intensity

**The PLEXOS data.** A `Constraint` right-hand side, stated for a year or over the whole
horizon, and the span it applies over.

**What happens to it.** The yearly right-hand side becomes `max_mtons`, the cap's limit in
million tonnes, and the horizon-wide one is read where the constraint states no yearly limit.
`CarbonCaps.target_year` and `CarbonCaps.max_tons_mwh` are left unmapped and are absent from
the document; `decisions.md` records both.

**The cause.** PLEXOS states the span a right-hand side applies over, not the year it applies
in, and it has no rate-based right-hand side for `max_tons_mwh` to carry.

**The effect on the expansion.** The cap applies to every year of the run, whichever year
your model stated it for. With `max_tons_mwh` absent, nothing limits the carbon intensity of
what it builds.

---

### A storage build that prices only its discharge

**The PLEXOS data.** The `Build Cost` of a `Battery`, or of a pumped-storage turbine, which
prices the unit by its power.

**What happens to it.** It becomes the technology's `capital_costs.discharge_capital_cost`.
The `charge_capital_cost` and the `energy_capital_cost` beside it are written as zero curves.

**The cause.** A Sienna storage technology adds charge power, discharge power and energy
independently and prices each of the three. PLEXOS prices the object by its power alone, and
PyPSA carries one overnight cost for a storage unit, so neither states the other two prices.

**The effect on the expansion.** A consumer that sizes the three parts separately takes the
largest energy and the largest charging power its limits allow for nothing, because nothing
prices either. The whole price of a storage build sits on its discharge capacity, which is
the right number only if you read the source's build cost as the price of a whole unit.

---

### The years a plan steps through

**The PLEXOS data.** The investment periods of an LT Plan, the years it steps through, and
the representative days and weights it samples each year with.

**What happens to it.** Neither reaches the portfolio. The portfolio states one expansion
problem, with no schedule of periods and no representative-day weighting.

**The cause.** A portfolio document holds the technologies, the requirements and the regions
of an expansion problem. The periods and the representative days are terms of the solve, so
they belong on the request that solves the portfolio rather than in it.

**The effect on the expansion.** Whoever solves the portfolio chooses the periods and the
sampling. A plan built over a different set of years, or against a different set of
representative days, from the ones your PLEXOS model uses builds a different fleet, so its
result and your model's LT Plan result are not the same quantity.
