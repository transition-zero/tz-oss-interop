# Translation from PLEXOS to PyPSA

This document tells you what each part of your PLEXOS model becomes in the PyPSA network.
It gives the source of each field.

> **Scope:** the translator accepts electricity-only models, and it translates them for
> dispatch. It does not translate capacity expansion, custom constraints or hydro cascades.
> It carries the reserves to a sidecar file, but it does not apply them. Refer to
> [Reserves](#reserve--extensions-sidecar) and [Not translated](#not-translated). The
> `plexos-to-pypsa-monte-carlo-reliability` pipeline also adds a load shedding generator at
> each bus. Refer to [Load shedding](#load-shedding).

---

## What becomes what

| PLEXOS | PyPSA |
| --- | --- |
| [`Node`](#node--bus) | `Bus` |
| [`Region`](#region) | No component. It gives the bus `location` and a `Load`. |
| [Region `Load` property](#region-load--load) | `Load` |
| [`Line`](#line--link-or-line) | `Link` if it has no impedance, or `Line` if it has impedance |
| [`Generator`](#generator--generator), thermal or renewable | `Generator` |
| [`Generator`](#hydro--storageunit-or-generator), reservoir hydro | `StorageUnit` with the carrier `hydro` |
| [`Generator`](#hydro--storageunit-or-generator), run-of-river | `Generator` with the carrier its `Fuel` or category names |
| [`Generator` and two `Storage`](#pumped-storage--storageunit), pumped storage | One `StorageUnit` with the carrier `PHS` |
| [`Battery`](#battery--storageunit) | `StorageUnit` with the carrier `battery` |
| [`Fuel`](#fuel) | No component. It sets the generator `carrier` and part of the `marginal_cost`. |
| [`Emission`](#emission) | No component. It adds a carbon term to the `marginal_cost`. |
| [`Market`](#market--generator) | An import `Generator` |
| [`Reserve`](#reserve--extensions-sidecar) | No component. The translator carries it to the reserves sidecar, but nothing applies it. |
| [Region `VoLL`](#load-shedding) | No component in the two faithful pipelines. In `plexos-to-pypsa-monte-carlo-reliability`, a load shedding `Generator` at each bus. |
| `Zone`, `Interface`, `Transformer`, `Constraint`, `Waterway`, `Decision Variable` | [Not translated](#not-translated) |
| `Transmission`, `ST`/`MT Schedule`, `PASA`, `Production`, `Performance`, `Stochastic`, `Report`, `Diagnostic`, `System`, `List` | Not translated. These are solver settings, not model data. |

## Reading the tables

| Mapping | Meaning |
| --- | --- |
| `direct` | The translator uses your PLEXOS value without a change. |
| `derived` | The translator calculates the value from your values, with the formula that the table gives. |
| `default` | PLEXOS has no such data. The translator supplies this value. |
| `dropped` | PyPSA has no equivalent. The value does not go into the network. |

## Across all components

- **One scenario only.** The values come from the PLEXOS Model that you select. The
  translator applies the scenario overrides of that Model, one entry at a time. Refer to
  [How scenario overrides resolve](#how-scenario-overrides-resolve). The translator does
  not carry the other scenarios. To get them, do the translation again with a different
  Model.
- **Profiles go into the network.** A property that reads from a Data File CSV becomes a
  PyPSA time series. This applies to the demand, the generator availability and the hydro
  inflow. The translator extracts the modelled horizon only.
- **Each replication becomes a network.** A Data File CSV can have numbered columns. Each
  column is one replication of a Monte Carlo study. The `plexos-to-pypsa` pipeline reads
  the lowest column. The `plexos-to-pypsa-monte-carlo` pipeline writes one network for each
  replication into a directory. The quantity of replications comes from the data, not from
  a setting. If one profile does not have a replication, the translator does not write that
  replication and it gives a warning.
- **PyPSA keeps one value where PLEXOS keeps several.** For a piecewise heat rate curve,
  the translator uses the lowest band. For a start cost that has hot, warm and cold values,
  it uses the cold start value. PLEXOS writes no band number on the first band of a
  property. Thus a value that has no band is that lowest band. It is not certain that the
  lowest band is the correct single value for a linear marginal cost. The lowest band is
  the incremental rate at the bottom of the range. It is not the average across the range.
- **The translator applies a capacity schedule. It does not optimise the capacity.** The
  translator applies the builds, the retirements and the derates that your model gives with
  dates. But it does not ask PyPSA to select a capacity.
- **The translator interprets some values.** It does not copy them. This applies to
  properties that hold several values, to dated entries, to timeslice entries, to ratings,
  to outages and to storage volumes. Refer to
  [Special business rules](#special-business-rules).

---

## `Node` → `Bus`

| PyPSA field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | `Node.name` | `direct` |
| `v_nom` | kV | `Node.Voltage` | `direct` |
| `carrier` | | `AC` | `default` |
| `control` | | `Slack` if `Is Slack Bus` is true. If not, `PQ`. | `derived` |
| `location` | | The name of the Region that contains the node | `derived` |

Each `Node` becomes a bus. You select the name of a node. Thus the translator does not read
a meaning from any name. A node with the name `External` or `Import` becomes a bus, the
same as all the other nodes.

PLEXOS has no AC or DC input on a node. Thus each bus is `AC`. The translator does not set
the bus coordinates, because PLEXOS has no coordinate property.

A node where a `Market` trades is a bus, the same as all the other nodes. The model puts
real generators on such a node, and it gives ratings to the lines that touch it. If the
translator did not write that bus, it would lose both. The generators would have the name
of a bus that does not exist. Also, the translator would remove each line that touches the
node, because one end of the line would not be a bus.

## `Region`

A Region does not become a PyPSA component. It gives its name to the `location` of each of
its buses. Its `Load` property becomes a [`Load`](#region-load--load).

`Price of Dump Energy` is `dropped`. The two faithful pipelines, `plexos-to-pypsa` and
`plexos-to-pypsa-monte-carlo`, also drop `VoLL`. The
`plexos-to-pypsa-monte-carlo-reliability` pipeline reads `VoLL`. Refer to
[Load shedding](#load-shedding).

## Region `Load` → `Load`

The translator writes one `Load` for each region that has a demand. It puts that `Load` on
the bus of the region.

| PyPSA field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | `<Region>_load` | `derived` |
| `bus` | | The node of the region | `derived` |
| `p_set` | MW | `Region.Load` | `direct` |

`Region.Load` has two possible meanings. If it is a demand in MW, the translator uses it
directly. If it is a participation fraction, the demand of the region is the system profile
multiplied by the fraction. A participation fraction is a share of one demand profile for
the full system, and the fractions of the regions have the total 1.0.

**Deferred.** Version 1 reads the MW form only. A model is a participation fraction model
if two conditions are true. First, each of its region `Load` values is more than 0 and not
more than 1. Second, the total of those values is 1.0. For such a model the translation
stops. If it did not stop, it would read the shares as megawatts. The network would then
have a demand of one megawatt.

A PyPSA load is on one bus. Thus version 1 translates a region only if that region contains
one node. If a region has a `Load` and contains more than one node, the translation stops.
A region can contain no node, or its node can be a node that the translator did not write
as a bus. In both of these conditions, the translator does not write the load. It records
this result.

The reactive demand is `dropped`.

## `Line` → `Link` or `Line`

The properties of the line control which component it becomes:

| Your line | Becomes |
| --- | --- |
| It has flow limits and no impedance | `Link` |
| It has a `Resistance` value or a `Reactance` value | `Line` |
| It has an HVDC mark | `Link`. Also, the buses at its two ends become `DC`. |

This rule is the rule of PLEXOS. The PLEXOS documentation says: "Modelling DC lines in
PLEXOS simply involves omitting their reactance", and "lines that do not have reactance
defined are controllable DC lines"
([Line class](https://portal.energyexemplar.com/unified-help/plexos-desktop/Main.Line.html)).
A line that has no impedance has no power flow to calculate. The optimiser selects the flow
of such a line, between its limits. A PyPSA `Link` operates in the same way. The translator
uses the properties of each line only. It does not read a line name or a node name as a
mark of an HVDC line or of a trade path.

The translator does **not** read the `Line.Type` property. That property sets the
technology that LT Plan uses when it expands a line: `0` for AC and `1` for DC. It does not
set the operation of a line that exists. Version 1 translates dispatch only.

A line must have a `Node From` membership and a `Node To` membership. If a line does not
have both, it connects nothing. The translator does not write it, and it records this.

### Lines without impedance → `Link`

| PyPSA field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | `Line.name` | `direct` |
| `bus0` / `bus1` | | `Node From` / `Node To` | `direct` |
| `p_nom` | MW | `Max Flow` | `direct` |
| `p_min_pu` | | `Min Flow / Max Flow` | `derived` |
| `p_max_pu` | | `1.0` | `default` |
| `efficiency` | | `1.0`. The link has no losses. | `default` |
| `marginal_cost` | $/MWh | `Wheeling Charge`. If there is none, `0.0`. | `direct` |
| `active` | | `True` | `default` |
| `carrier` | | `AC` | `default` |

A line that operates in two directions has a negative `Min Flow`. Such a line gets
`p_min_pu = -1`. A line that operates in one direction gets `0`.

`Wheeling Charge` becomes the `marginal_cost` of the link. Thus one MWh of flow across the
link costs the value that PLEXOS gives. A line that has impedance becomes a PyPSA `Line`. A
PyPSA `Line` has no cost for its flow. Thus for such a line the charge is `not mapped`.

### Lines with impedance → `Line`

| PyPSA field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | `Line.name` | `direct` |
| `bus0` / `bus1` | | `Node From` / `Node To` | `direct` |
| `r` | Ω | `Resistance` | `direct` |
| `x` | Ω | `Reactance` | `direct` |
| `b` | S | `Susceptance` | `direct` |
| `g` | S | `0.0` | `default` |
| `s_nom` | MVA | `Max Rating`. If there is none, `Max Flow`. | `direct` |
| `num_parallel` | | `Circuits` | `direct` |
| `length` | km | `Length` | `direct` |
| `active` | | `True` | `default` |
| `carrier` | | `AC` | `default` |
| `s_nom_extendable` | | `False`. Version 1 dispatches only. | `default` |
| `v_ang_min` / `v_ang_max` | | PLEXOS states no voltage-angle limit. | `not mapped` |

`s_nom` is one rating for the two directions. Thus if the forward limit and the reverse
limit of a line are different, the translator keeps the forward limit only. A
[`Rating`](#availability-and-outages) on a line decreases its capacity across time.

## `Generator` → `Generator`

This mapping applies to each unit in the PLEXOS Generator class. But hydro units and pumped
storage units become storage. Refer to [Hydro](#hydro--storageunit-or-generator) and to
[Pumped storage](#pumped-storage--storageunit).

PLEXOS models some supply objects that are not power plants. A model can show demand
response as a generator that has a high trigger price and a rating in the evening only. A
model can show an ancillary service as a generator that offers into a reserve product. The
translator translates each of these as a usual generator. It keeps the cost, the capacity
and the availability window. The translator does not use the name of a unit or its category
to select a route. Thus if you do not want such a unit in the PyPSA network, remove it from
your PLEXOS model.

### Carrier

PLEXOS does not record the technology of a generator. Thus the carrier is your own name for
the technology, and the translator copies it without a change:

| Your generator | Carrier |
| --- | --- |
| It burns a fuel and has a heat rate | The name of its `Fuel` |
| All other generators | The name of its PLEXOS category |

A carrier holds one of these two names. Thus the translator also writes the PLEXOS category
of each generator to the `extensions.json` file, with the generator name as the key. A
program that reads the output can then group the generators by the fuel or by the category.

The PyPSA `carrier` field accepts any text. Thus the translator loses nothing when it
copies your names, and nothing must interpret them. If your model gives one fuel for each
region, you get one carrier for each region. `NG_Cal_SoCalGas` and `NG_AZ_North` stay
separate. They do not both become `CCGT`. A program that reads the output can group them,
because you know which of your names are the same technology.

The translator uses a different test to find a **thermal** unit. It does not read a name. A
generator is thermal if it has a `Fuel` and a heat rate. A thermal generator is
`committable`, it has an `efficiency`, and its `marginal_cost` comes from the fuel price. A
generator that is not thermal takes a flat VO&M charge.

### Fields

| PyPSA field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | `Generator.name` | `direct` |
| `bus` | | The `Node` of the generator | `direct` |
| `carrier` | | Refer to the section above | `derived` |
| `p_nom` | MW | `Max Capacity × Units`, or the static `Rating` where that is higher, or the peak of the profile that supplies the capacity | `derived` |
| `p_min_pu` | | [Minimum generation](#minimum-generation) | `derived` |
| `p_max_pu` | | `1.0`, or the [`Rating` and the outage derates](#availability-and-outages) | `derived` |
| `marginal_cost` | $/MWh | `fuel price × Heat Rate Incr + VO&M`, and the carbon term if there is one | `derived` |
| `efficiency` | | From the [heat rate](#unit-conversions) | `derived` |
| `committable` | | `True` for a thermal generator. If not, `False`. | `derived` |
| `min_up_time` / `min_down_time` | snapshots | `Min Up Time` / `Min Down Time` | `derived` |
| `ramp_limit_up` / `ramp_limit_down` | per unit per hour | `Max Ramp Up` / `Max Ramp Down` × 60 ÷ `p_nom` | `derived` |
| `start_up_cost` | $ | `Start Cost`, the cold start band | `derived` |
| `shut_down_cost` | $ | `0.0` | `default` |
| `up_time_before` | snapshots | `0` | `default` |

**The translator does not translate four cases.** It records each one as a skipped
component:

| Case | Cause |
| --- | --- |
| The generator has no `Node` | There is no bus to connect the generator to. |
| The generator has no [`Units`](#which-entry-applies-when) at any time in the horizon | The unit is retired. |
| `Max Capacity` comes from a data file | There is no single `p_nom`. Thus the translator cannot set the size of the generator, and it cannot calculate the availability per unit. |
| `p_nom` is 0 | The generator can never dispatch. |

The repair rates, the unit commitment solver options and the energy budgets are `dropped`.

**Demand response is a generator.** PLEXOS has no demand response object. A model shows the
resource as a generator that has a very high trigger price and a high heat rate on an
expensive fuel. That generator is available only in the hours when the operator can call
it. Nothing marks the generator as demand response, and the translator needs no such mark.
The price and the availability window go into the network through the mapping above. Thus
the resource keeps its position in the capacity stack, with the cost and the window that
your model gives it.

The carrier of a generator comes from its [fuel](#technology-and-fuel). A generator that
has more than one fuel uses its primary fuel.

## `Battery` → `StorageUnit`

| PyPSA field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | `Battery.name` | `direct` |
| `bus` | | The `Node` of the battery | `direct` |
| `carrier` | | `battery` | `default` |
| `p_nom` | MW | `Max Power` | `direct` |
| `max_hours` | h | The energy capacity divided by `p_nom` | `derived` |
| `p_max_pu` / `p_min_pu` | | `1.0` / `-1.0` | `default` |
| `efficiency_store` / `efficiency_dispatch` | | `√(Charge Efficiency)` for each | `derived` |
| `state_of_charge_initial` | MWh | `Initial SoC % × Capacity` | `derived` |
| `cyclic_state_of_charge` | | `True` if `End Effects Method` is `RECYCLE`, or if the model gives no `Initial SoC` | `derived` |
| `marginal_cost` | $/MWh | `0.0` | `default` |

The energy capacity of a battery is its `Capacity`. If the model gives a duration in place
of a capacity, the energy capacity is `Duration × Max Power`. `max_hours` and
`state_of_charge_initial` both read that one value. Thus they cannot disagree about the
energy of the battery.

`Charge Efficiency` is a round trip value. The translator divides it equally between the
charge and the discharge. Thus the round trip value does not change. `Min SoC` and `Max
SoC` are `dropped`, and the full energy capacity is available.

A `Battery` or a turbine can have a rated power of zero. For example, `Units 0` puts a unit
into storage. Such a unit cannot dispatch. The translator does not write it, and it makes a
`COMPONENT_SKIPPED` event that gives the name of the unit.

## Pumped storage → `StorageUnit`

The turbine, its head reservoir and its tail reservoir become **one** `StorageUnit`. The
name of the turbine is the name of that `StorageUnit`.

| PyPSA field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | The `Generator.name` of the turbine | `direct` |
| `bus` | | The `Node` of the turbine | `direct` |
| `carrier` | | `PHS` | `default` |
| `p_nom` | MW | `Max Capacity × Units`, or the static `Rating` where that is higher, or the peak of the profile that supplies the capacity | `derived` |
| `max_hours` | h | The `Max Volume` of the head reservoir divided by `p_nom`, if the model gives that volume in MWh | `derived` |
| `p_max_pu` / `p_min_pu` | | `1.0` / `-1.0` | `default` |
| `efficiency_store` / `efficiency_dispatch` | | `√(Pump Efficiency)` for each | `derived` |
| `state_of_charge_initial` | MWh | The `Initial Volume` of the head reservoir, if the model gives it in MWh. The translator holds the value between 0 and `p_nom × max_hours`. | `derived` |
| `cyclic_state_of_charge` | | `True` if `End Effects Method` is `RECYCLE` | `derived` |
| `marginal_cost` | $/MWh | `VO&M Charge`. If there is none, `0.0`. | `derived` |
| `inflow` | MW | The `Natural Inflow` of the head reservoir, if the model gives it in a unit that converts to MW. A `Natural Inflow` that reads a data file becomes a time series. | `derived` |

The turbine finds its reservoirs through its `Head Storage` membership and its
`Tail Storage` membership. The translator never compares the names of the reservoirs. The
`StorageUnit` takes its bus from its turbine. Refer to [Storage](#storage) for the
conversion from a volume to an energy. A `LEVEL` model or a `VOLUME` model does not give a
volume that is equal to an energy.

The translator drops the separate head reservoir and tail reservoir, the elevation of the
reservoir, and any efficiency that changes with the level. It does not translate a
reservoir that has no turbine.

The translator reads `End Effects Method` on a battery. A battery that recycles its level
gets `cyclic_state_of_charge = True`. A battery that states no `End Effects Method` and no
`Initial SoC` also cycles, because a battery that starts empty invents a shortfall in the
first hour of every horizon. A battery that states an `Initial SoC` starts at that level and
does not cycle. Pumped storage gets `True`. Reservoir hydro gets `False`, because reservoir
hydro follows its inflow.

The translator drops these properties of a storage class, and reports each one: the volumes
of the tail reservoir, and the `Min SoC`, the `Max SoC` and the `Discharge Efficiency` of a
battery. It splits `Charge Efficiency` evenly across the charge side and the discharge side,
which is why it drops `Discharge Efficiency`. It treats the whole energy capacity as usable,
which is why it drops `Min SoC` and `Max SoC`.

## Hydro → `StorageUnit` or `Generator`

| Your unit | Becomes |
| --- | --- |
| It has a `Head Storage` membership | A `StorageUnit` with the carrier `hydro` |
| It has an inflow profile and no reservoir | Version 1 does not translate it |
| It has no storage, and its output follows a profile | A `Generator` with the carrier its `Fuel` or category names |

The translator identifies a turbine by its `Head Storage` membership only. Thus the
translator does not translate a hydro unit if its only storage signal is a `Natural Inflow`
profile. To translate such a unit, give it a reservoir membership.

**An inflow goes to PyPSA only in a unit that converts to MW.** PLEXOS measures an inflow in
the unit that the model selects. A `Natural Inflow` in GW or in kW converts, so the value
reaches `inflow`. A `Natural Inflow` in cumec or in m³/day is a flow of water, and to make it
a power needs the head of the reservoir and the efficiency of the turbine. The translator
reads neither, so it does not write such an inflow. `inflow` then takes the PyPSA default of
0.0, and the report gives the unit that the model used.

Reservoir hydro uses the [pumped storage](#pumped-storage--storageunit) mapping, but it
cannot pump. Thus `p_min_pu = 0`. Its energy comes in as `inflow`. Run-of-river uses the
[generator](#generator--generator) mapping, with its profile on `p_max_pu` and no fuel
cost.

If a hydro unit has a fuel that is a placeholder, the translator drops that fuel.

## `Fuel`

A Fuel does not become a PyPSA component. It sets two values:

- The **carrier** of each generator that burns it.
- The **fuel term** of the `marginal_cost` of that generator, which is `price × heat rate`.

The translator carries the fuel names as your model spells them. Thus if your model has
several fuels that are the same chemistry at different regional prices, you get **several
carriers**, one for each fuel name. A model that has `Gas SoCal` and `Gas PG&E` gives two
gas carriers, not one. Group them when you compare or aggregate the output. Do not group
them here, because you are the only person who knows which of your fuel names are the same
thing.

The translator makes a fuel price that changes with time into one value. It drops a fuel
that has no generator.

## `Emission`

An Emission does not become a PyPSA component. The translator adds a carbon term to the
`marginal_cost` of each thermal generator that burns a fuel with an emission:

```
carbon price ($/tonne) × production rate (kg/GJ) × heat rate (GJ/MWh) ÷ 1000
```

Thus the carbon changes the merit order. The translator drops the emission caps.

## `Market` → `Generator`

The translator writes one import generator for each trading region, at the bus of that
region. A trading region is a region whose node is a member of a `Market`. That membership
identifies the trade. The name of a node or of a line does not identify the trade.

**Deferred.** Version 1 does not translate `Market`. A node where a `Market` trades is a
usual bus, and the lines that reach it are usual lines. Thus the generators that the model
puts on that node do supply it. They supply it at their own cost and the `Wheeling Charge`
of the line. The market itself is absent. That is, there is no price at which the network
can buy or sell without a generator.

**The lines for this mapping are not yet decided.** PLEXOS has a `Market` class. Thus a
market is a named object that has its own memberships, and the mapping will read those
memberships. Some models also give the name `External` to the far end of a trade path. But
the name of a node is your own text, and it will decide nothing here. Before we write this
mapping, we must examine a real model to find the memberships that connect a `Market` to
its lines and its regions.

| PyPSA field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | `<Region>_import` | `derived` |
| `bus` | | The node of the trading region | `derived` |
| `carrier` | | `import` | `default` |
| `p_nom` | MW | The `Max Flow` of the purchase line | `direct` |
| `marginal_cost` | $/MWh | The market price and the `Wheeling Charge` of that line | `derived` |
| `committable` | | `False` | `default` |

**The translator does not translate the exports.** Thus the network can buy from the
market, but it cannot sell to the market. A region that exports in your PLEXOS results will
curtail in the PyPSA network. The translator makes a market price that changes with time
into one value.

## `Reserve` → extensions sidecar

A PyPSA network file has no reserve component. Thus a reserve cannot go into the network.
The translator writes each reserve to an `extensions.json` file adjacent to the network, as
a `reserve` record in framework-neutral terms. The contract is in
`interop/core/extensions.py`. Nothing applies the requirement, in the network or in the
solve. Thus the generators that contribute to a reserve can supply their full output. The
sidecar carries the requirement for a program that decides to use it, and for a later hop
into a framework that does have reserves.

| Sidecar field | From |
| --- | --- |
| `name` | `Reserve.name` |
| `contributing_generators` | The generators in the `Generators` collection of the reserve |
| `requirement_mw` | `Min Provision`, lowest band, in MW, when it holds at every snapshot |
| `requirement_series` | `reserves.parquet`, when the requirement changes over the horizon |
| `direction` | The direction part of `Type` |
| `kind` | The product part of `Type` |
| `sustained_time_seconds` | `Duration`, which PLEXOS states in seconds |
| `is_available` | `Is Enabled` |
| `shortage_price` | `VoRS`, lowest band. Absent if PLEXOS gives none. |
| `is_mutually_exclusive` | `Mutually Exclusive`. `Auto` leaves the choice to PLEXOS, so the sidecar states nothing. |

### The requirement is always megawatts

A field carries one quantity in one unit, and each hop converts at its own edge. `Min
Provision` is megawatts, so the sidecar states megawatts. Where the requirement holds at
every snapshot, `requirement_mw` is that number. Where it changes over the horizon,
`requirement_series` names a companion parquet beside the sidecar, whose rows are
`snapshot`, `name` and `requirement_mw`.

The meaning of a `Min Provision` value depends on the tag of its `t_data` row.

A `Min Provision` that has no tag is a quantity of reserve in megawatts. The sidecar gives
it as `requirement_mw`.

A `Min Provision` can have a tag to a `Variable`. The Profile of that `Variable` can point
at a load file. The network can also build its `Load` components from that same file. If
both of these conditions are true, the value is the share of that profile for this reserve.
A share of system load is a rule for computing megawatts, not a different quantity, so the
hop that holds the load resolves it: the staged series is the profile multiplied by the
share, and the sidecar points at the companion parquet holding it.

A `Min Provision` can also have a tag to a profile that the `Load` components do not read.
The value is then a share of something that has no megawatt meaning here. The translator
writes the reserve without a requirement. It does not write a value that has no clear
meaning. The report gives the name of the file.

A `Min Provision` can have a tag straight to a Data File that carries its own megawatt
columns. The property then holds no value of its own, or only the placeholder `0` that
PLEXOS writes in its place, and the file is the requirement. The sidecar points at the
companion parquet.

`Min Provision` can also hold the placeholder `0` with no file behind it at all. The
translator writes the reserve without a requirement. It does not give the zero as the
requirement. The report records the reserve and the absent requirement.

A published model routinely ships its traces as separate downloads. Where the file behind a
`Min Provision` is not in the package, there is no series to state the requirement from. The
translator writes the reserve without a requirement, rather than a reference to a companion
parquet that it will not write.

### `Type` names the direction and the product

PLEXOS packs both into one integer. The decode table is the `input_mask` that a PLEXOS
model file carries on the property itself.

| `Type` | PLEXOS name | `direction` | `kind` |
| --- | --- | --- | --- |
| 1 | Raise | `up` | `unknown` |
| 2 | Lower | `down` | `unknown` |
| 3 | Regulation Raise | `up` | `regulating` |
| 4 | Regulation Lower | `down` | `regulating` |
| 5 | Replacement | `unknown` | `replacement` |
| 6 | Operational | `unknown` | `operating` |
| 7 | Regulation | `symmetric` | `regulating` |
| 8 | Inertia | `unknown` | `inertia` |

`Raise` and `Lower` name a direction only, so the product stays `unknown`. A code that is
not in this table gives `unknown` for both. Thus a later hop can tell "we do not know which
kind of reserve this is" from "there is no reserve here".

---

## Load shedding

A PyPSA `Load` has a fixed `p_set`. Thus a PyPSA network sheds nothing. If the capacity is
less than the load in one hour, the solve does not complete. It does not report the
unserved energy.

The `plexos-to-pypsa-monte-carlo-reliability` pipeline adds a load shedding generator. Thus
a reliability study can measure a shortfall. If it did not, the study would lose that
replication to a solve that does not complete. The two faithful pipelines,
`plexos-to-pypsa` and `plexos-to-pypsa-monte-carlo`, do not do this step. Their networks
have no load shedding generator.

The pipeline adds one `Generator` at each `Bus`, with the name `<bus>_load_shedding`:

| PyPSA field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | `<bus>_load_shedding` | `derived` |
| `bus` | | The bus itself | `derived` |
| `p_nom` | MW | The total peak load of the network, which is the total of the peak of each load | `derived` |
| `carrier` | | `load_shedding` | `default` |
| `marginal_cost` | $/MWh | The `VoLL` of the Region that contains the bus. If there is none, `10000`. | `derived` / `default` |
| `p_min_pu` / `p_max_pu` | | `0.0` / `1.0` | `default` |
| `committable` | | `False` | `default` |
| `p_nom_extendable` | | `False` | `default` |

The `p_nom` value is large, and this is intentional. It is the total of the peak megawatts
of each load. Thus the shedding generator at one bus can supply the full demand of the
network. This gives more capacity than necessary. But a shedding generator that is too
small cannot absorb a shortfall.

If a Region gives no `VoLL`, the translator uses `10000` $/MWh. That value is the declared
default of PLEXOS for that property. It is not a value that this translation invents. The
decisions output records the price of each shedding generator.

---

## Special business rules

PLEXOS holds some data in a form that a simple property-by-property reading gets wrong.
These rules control how the translator reads those values. They apply at each location
where those values occur.

### How scenario overrides resolve

When you activate a Scenario, PLEXOS does not replace one set of values with another set.
PLEXOS reads the union of two groups: each entry that has a tag for an active scenario, and
each entry that has no tag. An entry that has a tag replaces an entry that has no tag only
if the two entries describe the same entry.

Two entries are the same entry if they have the same object, the same property, the same
band and the same time scope. Thus an override applies to one entry, not to a full
property. If a scenario changes the first band of a heat rate curve, the other bands do not
change:

| Band | Base | `HighEfficiency` | Read when `HighEfficiency` is active |
| --- | --- | --- | --- |
| 1 | 10500 | 9500 | 9500, because the entry with the tag wins |
| 2 | 9200 | none | 9200, because nothing replaced it |
| 3 | 8800 | none | 8800, because nothing replaced it |

More than one active scenario can describe the same entry. The entry with the highest
`Read Order` then wins. `Read Order` is zero if you do not set it. If two scenarios have
the same `Read Order`, PLEXOS reads them in alphabetical order.

Source: [Scenario Class](https://portal.energyexemplar.com/unified-help/plexos-desktop/Main.Scenario.html)
("Data from Scenarios overrides untagged data") and
[Scenario Read Order](https://portal.energyexemplar.com/unified-help/plexos-desktop/Scenario.ReadOrder.html).

**Open question.** A scenario can supply a banded property that has fewer bands than the
base. This rule then keeps the extra bands of the base. The result is a curve that is in
neither the base nor the scenario. This result follows from the documented rule, but the
documentation does not give it directly. Energy Exemplar has not confirmed it.

### Properties holding several values

Bands, values per unit, heat rate segments and timeslice values all export as one list.
They do not export as separate properties. The property controls which value the translator
uses:

| Property | Value used |
| --- | --- |
| A capacity across more than one unit | The total |
| Heat rate segments | The average, across equal power segments |
| `Max Flow`, `Max Rating` | The lowest |
| `Min Flow`, `Min Rating` | The highest |
| `Resistance`, `Reactance` | The first |

### Values that are a share of a shared profile

A property value that has a tag to a `Variable` is not the value itself. It is the
**share** of this object in the profile that the `Variable` names. The translator
multiplies the two. For example, a solar plant can have a `Rating` of `0.00003865` against
a solar trace for the full system. That plant takes that fraction of the trace, not the
full trace. The shares of the plants that use one trace have the total 1.

| Where the value comes from | What it means |
| --- | --- |
| A tag to a `Data File` | The CSV holds the full value. |
| A tag to a `Variable` | The value is a share. The translator multiplies it by the profile of the `Variable`. |
| A share written as a percentage | The translator divides it by 100 first. Thus a share of `100` gives a multiplier of one. |
| A share of `0` | This is a placeholder, not a multiplier. The translator uses the profile without a change. |

A `Variable` names its profile directly, or through a `Data File` object. The second form
lets a model divide one trace into twelve monthly files, and the active scenario selects
the file.

`Max Capacity`, `Min Stable Level`, `Rating`, `Rating Factor`, `Units Out` and a Region
`Load` can all come to the translation in this form.

### Which entry applies when

A property can have a base value and more entries. Each of the other entries has a scope,
which is a `date_from` value and a `date_to` value, or a timeslice. For each snapshot, the
translator applies these rules:

1. **An entry with a time scope wins.** An entry has a time scope if it has a date bound or
   a timeslice tag. A date bound includes the end date.
2. **The base value fills the gaps.** It applies only at the snapshots that no entry with a
   time scope covers.
3. **A default fills the remainder,** where neither of the first two rules applies.

Two properties use dated entries as a schedule. They do not use them as corrections:

| Property | Meaning |
| --- | --- |
| `Units` | A capacity that starts, retires or partly derates. A static value above zero with a later entry of zero is a **retirement**. A static zero, or no value, with a later entry above zero is a **new build**. |
| `Max Capacity` | A capacity expansion schedule. The translator applies the entry that is in force at the snapshot. Where it needs one value, it uses the entry that is in force at the start of the model. |

### Timeslice patterns

A timeslice can be a pattern, for example `M6-9,H16-22`.

| Symbol | Means |
| --- | --- |
| `H` | Hour |
| `W` | Day of the week |
| `D` | Day of the month |
| `M` | Month |
| `Q` | Quarter |
| `K` | ISO week |
| `P` | Trading period |

The operators are `,` for and, `;` for or, and `!` for not.

- `H1` is the interval from midnight to 01:00. That is, PLEXOS hour *h* is the hour that
  starts at *(h−1)*.
- `W1` is Sunday.
- `P` uses the trading periods for each day that the Horizon sets. The default is 24.
- A comma before a letter starts a new condition. A comma before a digit continues the
  previous range. Thus `M4-9,H1-3,24` means April to September, at the hours 1, 2, 3 and
  24.
- A timeslice with a name from `M1` to `M12`, and with no definition of its own, means that
  month.

### Availability and outages

`Rating` and `Rating Factor` give an availability that changes with time. They **replace**
the static `Max Capacity` on a generator, or the static `Max Flow` on a line.
`Rating Factor` is a percentage. `Rating` is in MW.

A static `Rating` above `Max Capacity × Units` is the capacity of the generator, not an
availability above its own nameplate. The translator gives that generator a `p_nom` equal to
its `Rating`, so `p_max_pu` is 1 and every other per-unit field divides by the capacity the
unit can reach.

The translator takes the capacity during an outage from the first of these properties that
the model has:

| Property | Capacity available |
| --- | --- |
| `Outage Factor` | That percentage of the capacity |
| `Outage Rating` | The capacity less that quantity of MW |
| Neither property, but the model has outage data | None. This is a full outage. |
| The model has no outage data | The full capacity |

`Units Out` gives the quantity of units that are not available at each snapshot. Thus it
becomes a derate of `1 - Units Out / Units`. It applies to generators and to batteries. On
a battery, it limits the discharge. A generator can also have a `Rating` profile or a
`Rating Factor` profile. The translator then **multiplies** the two: `p_max_pu` is the
rating multiplied by the outage derate. It is not the value that the translator read last.

The minimum output of a generator cannot be more than its lowest availability. PLEXOS
applies `Min Stable Level` only while a unit is committed. Thus the translator limits
`p_min_pu` to the lowest availability across the horizon. A generator that has a full
outage at any time has no minimum.

### Technology and fuel

The generator does not record its technology. The technology comes from the fuel that the
generator has. A generator that has more than one fuel exports a list of fuels. The
translator removes the duplicates and uses the first remaining fuel as the primary fuel. It
records the other fuels as discarded.

### Generators on several nodes

The `Nodes` collection of a generator can name more than one node. The translator then
connects the generator to the first node. This is the same rule that it uses for the fuels.
The translator drops the other nodes. Thus if a model divides a unit between nodes, the
translator puts the full unit on one bus.

This is not bad input. PLEXOS lets a unit be at more than one node, and models use this
function to divide one physical plant between parts of the network. But a PyPSA generator
has one `bus` field. Thus there is no location for the second node.

The staged data has no allocation column. Thus the quantity of the unit at each node does
not come to the translation. Before we can do either option below, we must read the
participation factors from the PLEXOS XML.

The correct option depends on the commitment of the unit.

**Option 1: one generator for each node.** Give each node its own PyPSA generator. Divide
`p_nom` between them with the participation factors. Each generator stays a generator, and
nothing else in the translation changes.

The cost of this option is the unit commitment. Each new generator gets its own on and off
decision, its own start cost, and its own minimum up time and down time. A unit of 500 MW
that the translator divides in two could operate one half and stop the other half. The
PLEXOS model does not permit this. Thus this option is correct for a unit that has no
commitment attributes. It is wrong for a unit that has them.

**Option 2: a fuel bus and a link with more than two ports.** Make a bus for the fuel of
the unit. Put the supply and the cost of the fuel on that bus. Then run one link from that
bus to each node that the unit reaches. A PyPSA link accepts `bus2`, `bus3` and more, and
each of these has an `efficiency2`, an `efficiency3` and so on. The flow at a port is the
efficiency of that port multiplied by the flow at `bus0`. One link has one capacity and one
on and off decision across each port. Thus the commitment stays complete. The efficiencies
fix the division, and the division cannot change with the dispatch.

The cost of option 2 is that the unit is no longer a PyPSA generator. Its marginal cost
moves to the fuel supply. Its availability profile moves from the generators table to the
links table. Also, the reserve sidecar gives it as a contributing generator when it is not
a generator. Thus the same PLEXOS class makes two different PyPSA shapes, and the quantity
of nodes controls which shape.

Option 2 also needs a decision that is not part of this translation. The PyPSA to Sienna
direction does not translate a link that has more than two ports. Thus if the translator
writes such a link, that pipeline drops it.

### Minimum generation

The translator takes the minimum from the first of these properties that the model has. If
the model has none of them, the minimum is `0`.

1. `Min Stable Factor`, which is a percentage
2. `Min Stable Level`, which is in MW
3. `Min Pump Load`, which is in MW

A minimum that is more than the static availability limit gives a generator that PyPSA
cannot dispatch. The translation then stops with an error that gives the name of the
generator. A limit that comes from a profile changes across the horizon, and the translator
does not do this test on it.

### Unit conversions

A PLEXOS model declares the unit of each property, in the `t_unit` table joined to the
`t_property` table. PLEXOS writes the energy unit of the model as `~`. The `Units` row of
the `t_config` table gives the meaning of `~`: it is GJ for a Metric model, and MMBTU for
an Imperial model.

The translator reads each value below out of the unit that the model gives, and into the
unit that each mapping uses. It does this conversion as it stages the value. If interop has
no conversion for a unit, it stages the value as the model wrote it and it gives a warning.
The translator converts a value that the model states. Where the values come from a CSV,
the translator does not rescale the profile. It gives a warning instead.

| Value | Read in |
| --- | --- |
| `Heat Rate`, `Heat Rate Incr` | GJ/MWh |
| `Heat Rate Base` | GJ/h |
| Fuel `Price` | currency/GJ |
| Fuel `Production Rate` | kg/GJ |
| Emission `Price` | currency/tonne |
| `Max Capacity`, `Rating`, `Min Stable Level`, `Max Flow`, `Min Flow` | MW |
| `Max Ramp Up`, `Max Ramp Down` | MW/min |
| `Min Up Time`, `Min Down Time` | h |
| `VO&M Charge`, `Wheeling Charge` | currency/MWh |

A currency symbol has no conversion. Thus a model in euros reads as a model in dollars.
Then the translator converts these PLEXOS values. It does not copy them:

| Value | Becomes |
| --- | --- |
| `Max Ramp Up` / `Max Ramp Down` | From MW/min to a fraction of the capacity for one snapshot: × the snapshot minutes ÷ capacity. A rate that covers the whole capacity within one snapshot becomes 1, because PyPSA holds no larger value. |
| `Min Stable Factor`, `Rating Factor`, `Outage Factor` | The percentage ÷ 100 |
| `Min Stable Level`, `Min Pump Load`, `Rating` | MW ÷ `p_nom`, that is, ÷ (`Max Capacity × Units`) |
| Efficiency | `(capacity ÷ fuel) × 3.6`, where `fuel = Heat Rate Base + Heat Rate Incr × capacity` |
| Marginal cost | `fuel price × Heat Rate Incr + VO&M Charge` |

A generator that has no fuel takes the VO&M charge only. Wind, solar, hydro and storage
units have no fuel.

### Storage

The `Model` property of the storage sets the measurement of its volume:

| `Model` | Volume is in |
| --- | --- |
| `ENERGY` | GWh |
| `LEVEL` | Height |
| `VOLUME` | CMD or acre-feet |

A `LEVEL` volume and a `VOLUME` volume are not equal to an energy. To convert them to an
energy, you need the head and the efficiency.

`End Effects Method` sets the boundary condition. `RECYCLE` makes the storage cyclic, and
the level at the end is equal to the initial level. `FREE` lets the optimiser select the
level at the end.

A volume goes to PyPSA unless the model names a unit that is not MWh. PLEXOS measures a
reservoir in the unit that the model selects. Thus a `Max Volume` in cubic metres or in
acre-feet is a quantity of water, not a quantity of energy. If the translator wrote that
value as MWh, it would give the plant more hours of storage than the plant has. The
translator does not write such a volume.

A model can name no unit at all for a volume, and a published export does this. The
translator then uses the value as the model wrote it. `max_hours` and `state_of_charge_initial` then take their PyPSA
defaults, and the report gives the unit that the model used.

The initial state of charge is the `Initial Volume` of the head reservoir, in MWh. The
translator holds this value between 0 and `p_nom × max_hours`, because PyPSA cannot start a
unit above the capacity that it applies.

Usually a storage reaches the network through its generator, not through a node of its own.
If a storage has no node, its bus comes from its generator. A turbine finds its reservoirs
through its `Head Storage` membership and its `Tail Storage` membership. The translator
never compares the names of the reservoirs. Thus a head reservoir and a tail reservoir need
no name convention. If no generator names a `Storage`, the translator does not write it and
it makes a `COMPONENT_SKIPPED` event. It does the same for a turbine that has a tail
reservoir and no head reservoir.

---

## Not translated

| PLEXOS | Effect |
| --- | --- |
| `Zone` | The zonal group is lost. The regional group still goes to the bus `location`. |
| `Interface` | Nothing applies the group flow limits. Thus the dispatch can be more than a transfer limit that your PLEXOS model obeys. |
| `Transformer` | The translator does not carry it. |
| `Reserve` requirements | Nothing applies them. The generators that contribute can operate at full output. The translator does carry the reserves. Refer to [`Reserve`](#reserve--extensions-sidecar). |
| `Constraint` | Nothing applies the custom constraints. This includes the RPS targets and the emission targets. |
| `Waterway` | The cascade route between reservoirs is lost. Each reservoir is independent. |
| `Decision Variable` | The translator does not carry it. |
| Emission caps | Nothing applies them. Only the carbon price goes into the cost. |
| Market exports | Refer to [Market](#market--generator). |
| More than one scenario | The translator uses the values of the selected model only. |
| Ancillary service and demand response pseudo-generators | The translator skips nothing. Refer to [`Generator`](#generator--generator). |
| Gas, heat and water networks | The translator accepts electricity only. |

## Assumptions worth checking against your model

The translator reads these values in a particular way. If your model uses a different
convention, the translator will give wrong values.

| Value | Assumed as |
| --- | --- |
| `Resistance`, `Reactance`, `Susceptance` | Physical units, that is, ohms and siemens |
| `Node.Voltage` | kV |
| `Region.Load` | MW. But if the values of the regions have the total 1.0, the translator reads them as fractions. |
