# Translation from PLEXOS to Sienna

This document tells you what each part of your PLEXOS model becomes in the Sienna system.
It gives the source of each field.

> **Scope:** the translator accepts electricity-only models, and the `plexos-to-sienna`
> pipeline translates them for dispatch. It writes no capacity expansion: what your plan may
> build becomes a Sienna investments portfolio instead, which
> [the `plexos-to-sienna-investments` pipeline](translation-from-plexos-to-sienna-investments.md)
> writes. This pipeline does not translate custom constraints. Refer to
> [Not translated](#not-translated) and to
> [the gap analysis](plexos-to-sienna-gap-analysis.md), which names each thing a PLEXOS model
> states that SiennaSchemas holds no type and no field for.

The `plexos-to-sienna` pipeline is one step. It reads the PLEXOS tables the source stages
and writes the Sienna tables the sink needs, and no PyPSA file and no PyPSA table sits in
the middle. So this document states the mapping as one step, which is what you give and
what you get.

---

## What becomes what

| PLEXOS | Sienna |
| --- | --- |
| [`Node`](#node--acbus) | `ACBus`, and an `Arc` for each pair of nodes a branch joins |
| [`Region`](#region--area) | `Area`. It also gives a `PowerLoad`. |
| [`Zone`](#zone--loadzone) | `LoadZone` |
| [Region `Load` property](#region-load--powerload) | `PowerLoad` |
| [`Load` object](#load-object--powerload) | `PowerLoad` |
| [`Line`](#line--line-or-twoterminalgenerichvdcline) | `Line` if it has impedance, or `TwoTerminalGenericHVDCLine` if it has none |
| [`Generator`](#generator--thermalstandard), thermal | `ThermalStandard` |
| [`Generator`](#generator--renewabledispatch), renewable | `RenewableDispatch`, or `RenewableNonDispatch` where your mappings file says so |
| [`Generator`](#hydro--hydroturbine-and-hydroreservoir), reservoir hydro | `HydroTurbine`, or `HydroDispatch` where your mappings file says so |
| [`Storage` and `Waterway`](#hydro--hydroturbine-and-hydroreservoir), the head reservoir of a reservoir-hydro turbine | `HydroReservoir` |
| [`Generator` and two `Storage`](#pumped-storage--energyreservoirstorage), pumped storage | One `EnergyReservoirStorage` |
| [`Battery`](#battery--energyreservoirstorage) | `EnergyReservoirStorage` |
| [`Fuel`](#fuel) | No component. It names the carrier your mappings file turns into `fuel` and `prime_mover_type`, and it sets part of `operation_cost`. |
| [`Emission`](#emission) | No component. It adds a carbon term to `operation_cost`. |
| [`Market`](#market--thermalstandard) | An import `ThermalStandard` |
| [`Reserve`](#reserve--onlinereserve-or-offlinereserve) | `OnlineReserve`, or `OfflineReserve` for a replacement reserve, and one service association for each unit that supplies it. The record also reaches `extensions.json`. |
| [`Forced Outage Rate` and `Mean Time to Repair`](#forced-outage--geometricdistributionforcedoutage) on a `Generator` or a `Battery` | A `GeometricDistributionForcedOutage` supplemental attribute of the unit |
| Region `VoLL` | Nothing. `decisions.md` names it as dropped, because Sienna has no home for a region `VoLL`. |
| `Interface`, `Transformer`, `Constraint`, `Decision Variable` | [Not translated](#not-translated). A `Constraint` reaches the sidecar, but nothing applies it. |
| `Transmission`, `ST`/`MT Schedule`, `PASA`, `Production`, `Performance`, `Stochastic`, `Report`, `Diagnostic`, `System`, `List` | Not translated. These are solver settings, not model data. |

## Reading the tables

| Mapping | Meaning |
| --- | --- |
| `direct` | The translator uses your PLEXOS value without a change. |
| `derived` | The translator calculates the value from your values, with the formula that the table gives. |
| `default` | PLEXOS has no such data. The translator supplies this value. |
| `dropped` | Sienna has no equivalent. The value does not go into the system. |
| `mapped by you` | Your carrier mappings file gives the value. |

## Across all components

- **You write one mappings file, in PLEXOS words.** It names each `Fuel` and each generator
  category, and the Sienna type each becomes. Refer to
  [The carrier mappings file](#the-carrier-mappings-file).
- **A component whose carrier your file does not name is left out.** The run completes and
  `decisions.md` names each one.
- **A build the plan has yet to decide is not a plant.** A `Generator`, a `Battery` or a
  turbine that states `Max Units Built` and runs no units yet is a build and nothing else, and
  a dispatch system has no capacity for one, so it is left out and `decisions.md` names it. One
  that already runs keeps the capacity it runs, and only the build it may add is left out.
- **One scenario only.** The Model you select applies its own Scenario overlays. The
  translator reads no other scenario.
- **One calendar year at a time.** The year you give narrows the Horizon of the Model. Every
  dated value is the one in force during that year.
- **Sienna keeps one value where PLEXOS keeps several.** Refer to
  [Special business rules](#special-business-rules).
- **Profiles go into the time-series sidecar.** A `Rating` profile, an outage profile and a demand
  profile all become a row of `time_series_associations` whose values live in the
  InfraStore sidecar `system_time_series_storage.h5`.
- **Each component states its unit basis.** A generator, a load and a `TwoTerminalGenericHVDCLine`
  state `NATURAL_UNITS`, so each power value is in MW or MVA. A `Line` and an
  `EnergyReservoirStorage` state `COMPONENT_BASE`, so each of their power values is per unit on
  its `base_power`. A `Line` states a `base_power` of 100 MVA.
- **A profile Sienna states no field for goes into a parquet beside the sidecar.** A
  storage unit's units-out derate and the cost a dated `Fuel` makes have no Sienna field,
  static or varying, so each one rides a column of `storage.parquet` or `generators.parquet`.
  The record in `extensions.json` names the file it rides in. A reservoir inflow also rides
  `storage.parquet`, because the PyPSA hop reads it from there. A `HydroReservoir` states it
  as well.

---

## The carrier mappings file

A Sienna generator states a `prime_mover_type`, and a thermal one also states a `fuel`.
Both are closed lists. PLEXOS states neither, so you tell the translator what each of your
own words becomes. You give one file, at the `User mappings file?` prompt.

```yaml
carriers:
  - plexos_concept: fuel
    plexos_name: Natural Gas
    sienna_component_type: ThermalStandard
    sienna_fuel_type: NATURAL_GAS
    sienna_prime_mover_type: CC
  - plexos_concept: category
    plexos_name: Solar
    sienna_component_type: RenewableDispatch
    sienna_prime_mover_type: PVe
```

| `plexos_concept` | What `plexos_name` names |
| --- | --- |
| `fuel` | The name of a `Fuel` object. A generator that burns a fuel and states a heat rate takes this row. |
| `category` | The PLEXOS category of a generator that burns no fuel. |
| `storage_kind` | One of `reservoir_hydro`, `pumped_storage` and `battery`. These units take a Sienna type that no string in your model names. |

The translator supplies a row for each of the three storage kinds, so your file needs one
only to change a default:

| Storage kind | Sienna type | Prime mover |
| --- | --- | --- |
| `reservoir_hydro` | `HydroTurbine` | `HY` |
| `pumped_storage` | `EnergyReservoirStorage` | `PS` |
| `battery` | `EnergyReservoirStorage` | `BA` |

A `Fuel` and a generator category that share a name become one entry. Give them one Sienna
type, or the run stops and names the word.

---

## `Node` → `ACBus`

| Sienna field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | `Node.name` | `direct` |
| `base_voltage` | kV | `Node.Voltage` | `direct` |
| `bustype` | | `REF` if `Is Slack Bus` is true. If not, `PQ`. | `derived` |
| `area` | | The `Area` of the Region that contains the node | `derived` |
| `number` | | The position of the node | `derived` |
| `available` | | `True` | `default` |
| `angle` / `magnitude` | | `0.0` / `1.0` | `default` |
| `voltage_limits` | | PLEXOS states no voltage limit. | `default` |
| `load_zone` | | The `LoadZone` of the Zone that contains the node. A node in no Zone keeps a null `load_zone`. | `derived` |

Each `Node` becomes one `ACBus`. PLEXOS marks no node AC or DC, so every bus is AC. A node
that a branch touches also gives an `Arc`, which is the Sienna object holding the two ends of
a `Line` or an HVDC line.

A `Voltage` can read a data file. If that file does not stage, the XML holds only a
placeholder, such as `0`. The translator does not use the placeholder. `base_voltage` takes
the default of 1.0, and `decisions.md` records the `Voltage` as `NOT_MAPPED`. One warning
names three such nodes and counts the rest.

## `Region` → `Area`

Each Region becomes one `Area`, and each of its nodes points at that Area. Its `Load`
property becomes a [`PowerLoad`](#region-load--powerload). The `Area` carries a name only:
its `peak_active_power`, `peak_reactive_power` and `load_response` all take zero, because
PLEXOS states none of them on a Region.

`Price of Dump Energy` is `dropped`. So is `VoLL`, because a `PowerLoad` prices no
shortfall.

## `Zone` → `LoadZone`

A Node names the Zone it sits in through its `Zone` collection. Each Zone that a node names
becomes one `LoadZone`, and the `load_zone` of each bus in it is the id of that `LoadZone`.

| Sienna field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | `Zone.name` | `direct` |
| `id` | | The position of the zone, after the ids of earlier components | `default` |
| `peak_active_power` | MW | `0.0`. PLEXOS states no peak on a Zone. | `default` |
| `peak_reactive_power` | MVAR | `0.0` | `default` |
| `base_power` | MVA | The system base of 100 MVA | `default` |
| `power_units` | | `NATURAL_UNITS` | `default` |

A Zone that no node names gives no `LoadZone`.

## Region `Load` → `PowerLoad`

The translator writes one `PowerLoad` for each region that has a demand, on the bus of that
region.

| Sienna field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | `<Region>_load` | `derived` |
| `bus` | | The node of the region | `derived` |
| `max_active_power` | MW | `Region.Load`, or the peak of its profile | `derived` |
| `active_power` | MW | `Region.Load` at the first snapshot | `derived` |
| `base_power` | MVA | The peak demand | `derived` |
| `reactive_power` | MVAR | `0.0` | `default` |
| `max_reactive_power` | MVAR | `0.0` | `default` |
| `conformity` | | `UNDEFINED` | `default` |
| `available` | | `True` | `default` |

A demand that reads a data file becomes a `TimeSeriesAssociation` on `max_active_power`.
The translator divides the profile by its peak. The store holds that shape times the peak,
which is the profile in MW. A profile that peaks at 0 MW and falls below it has no peak to
scale it back. The translation leaves that profile out, records the gap and writes a warning.

A region `Load` stated as a participation share, not as megawatts, stops the translation
rather than reading a share as a quantity of power.

A region that contains more than one node is not translated, because a Sienna `PowerLoad`
sits on one bus.

## `Load` object → `PowerLoad`

An object of the PLEXOS `Load` class states its own `Load`, and joins one `Node` through the
`Load.Node` collection. The translator writes one `PowerLoad` for each `Load` object, on the
bus of that node.

| Sienna field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | The name of the `Load` object | `derived` |
| `bus` | | The node that the `Load` object joins | `derived` |
| `max_active_power` | MW | `Load.Load`, or the peak of its profile | `derived` |
| `active_power` | MW | `Load.Load` at the first snapshot | `derived` |
| `base_power` | MVA | The peak demand | `derived` |
| `reactive_power` | MVAR | `0.0` | `default` |
| `max_reactive_power` | MVAR | `0.0` | `default` |
| `conformity` | | `UNDEFINED` | `default` |
| `available` | | `True` | `default` |

A `Load` that reads a data file becomes a `TimeSeriesAssociation` on `max_active_power`, in
the same way as a region `Load`.

The translator leaves out a `Load` object in two cases. `decisions.md` names each one, and
the run writes one warning for each case:

- The `Load` object joins no node that became a bus.
- Another load already has the name of the `Load` object. Sienna gives each `PowerLoad` one
  name, and a region load or a node load comes first.

## `Line` → `Line` or `TwoTerminalGenericHVDCLine`

The properties of the line control which component it becomes:

| Your line | Becomes |
| --- | --- |
| It has flow limits and no impedance | `TwoTerminalGenericHVDCLine` |
| It has a `Resistance` value or a `Reactance` value | `Line` |
| It has an HVDC mark | `TwoTerminalGenericHVDCLine` |

A line must have a `Node From` membership and a `Node To` membership. A line without both
connects nothing, so the translator leaves it out and records it.

### Lines with impedance → `Line`

| Sienna field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | `Line.name` | `direct` |
| `arc` | | The `Arc` of `Node From` and `Node To` | `derived` |
| `r` | pu | `Resistance` ÷ the base impedance of the bus voltage | `derived` |
| `x` | pu | `Reactance` ÷ the base impedance of the bus voltage | `derived` |
| `b` | pu | `Susceptance` × the base impedance, split evenly across the two ends | `derived` |
| `rating` | pu | `Max Rating`, or `Max Flow` where the model states no rating, in per unit on 100 MVA | `derived` |
| `angle_limits` | rad | `(-1.5708, 1.5708)`, because PLEXOS states no voltage-angle limit | `default` |
| `available` | | `True` | `default` |
| `Wheeling Charge` | | A Sienna `Line` prices no flow. | `dropped` |

### Lines without impedance → `TwoTerminalGenericHVDCLine`

| Sienna field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | `Line.name` | `direct` |
| `arc` | | The `Arc` of `Node From` and `Node To` | `derived` |
| `operational_flow_limit.from_to_max` | MW | `Max Flow` | `derived` |
| `operational_flow_limit.to_from_max` | MW | `-Min Flow` where `Min Flow` is negative, else `0.0` | `derived` |
| `operational_flow_limit.from_to_min` / `.to_from_min` | MW | `0.0` | `default` |
| `rating` | MW | The larger of `from_to_max` and `to_from_max` | `derived` |
| `rating_from` / `rating_to` | | not written, because PLEXOS states no converter rating | `dropped` |
| `reactive_power_limits_from` / `_to` | MVAR | `(0.0, 0.0)` | `default` |
| `loss` | | A `LossCurve` with a zero-loss curve, so the line has no loss | `default` |
| `available` | | `True` | `default` |
| `Wheeling Charge` | | The HVDC type prices no flow. | `dropped` |

A line that flows in two directions has a negative `Min Flow`, so its lower limit is
negative. A line that flows one way has a lower limit of zero.

### A line value in a data file that did not stage

A `Resistance`, a `Reactance`, a `Max Rating` or a `Max Flow` can read a data file. If that
file does not stage, the XML holds only a placeholder, such as `0` for a reactance or `1e30`
for a rating. The translator does not use the placeholder:

| Field | What the translator writes |
| --- | --- |
| `r` or `x` | `0.0`, as for a line that states no such value |
| `rating` of a `Line` | `0.0`, as for a line that states no rating |
| `operational_flow_limit` and `rating` of a `TwoTerminalGenericHVDCLine` | `0.0` |

`decisions.md` records each such value as `NOT_MAPPED`, with the note `<property> is in a
data file that did not stage`. One warning for each property names three lines and counts
the rest.

A line that states a `Resistance` or a `Reactance` in such a file still states impedance. So
it stays a `Line`, and it does not become a `TwoTerminalGenericHVDCLine`.

## `Generator` → `ThermalStandard`

A generator becomes a `ThermalStandard` when it burns a `Fuel`, states a heat rate, and your
mappings file gives that fuel the type `ThermalStandard`.

| Sienna field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | `Generator.name` | `direct` |
| `bus` | | The `Node` of the generator | `direct` |
| `fuel` | | The `Fuel` of the generator, through your mappings file | `mapped by you` |
| `prime_mover_type` | | The `Fuel` of the generator, through your mappings file | `mapped by you` |
| `base_power` | MVA | `Max Capacity × Units`, or the static `Rating` where that is higher | `derived` |
| `rating` | MVA | `base_power` × the availability, which is 1.0 unless an outage or a `Rating` derates it | `derived` |
| `power_units` | | `NATURAL_UNITS` | `default` |
| `active_power_limits` | MW | `(Min Stable Level, the available capacity)` | `derived` |
| `active_power` | MW | `Min Stable Level` | `derived` |
| `ramp_limits` | MW/min | `Max Ramp Up` / `Max Ramp Down`, held to the rate that covers the whole capacity in one snapshot. A generator that states no `Max Ramp Down` takes the rate that covers the whole capacity in one snapshot, which never binds (`ramp_limits.down` is a `default` event). A generator that states only `Max Ramp Down` gets no `ramp_limits`, because SiennaSchemas needs both directions | `derived` |
| `time_limits` | h | `Min Up Time` / `Min Down Time` | `direct` |
| `time_at_status` | h | `10000.0`, because PLEXOS states no prior on-time | `default` |
| `must_run` | | not written | `dropped` |
| `status` | | `ONLINE` | `default` |
| `operation_cost.variable_operation_cost` | $/MWh | `fuel price × Heat Rate + VO&M Charge`, and the carbon term if there is one | `derived` |
| `operation_cost.start_up` | $ | `Start Cost`, the cold start band | `direct` |
| `operation_cost.shut_down` | $ | `0.0`, because PLEXOS prices only starts | `default` |
| `operation_cost.fixed` | $ | `0.0` | `default` |
| `reactive_power` / `reactive_power_limits` | MVAR | PLEXOS states no reactive data. | `default` |

An availability that changes with time becomes a `TimeSeriesAssociation` on
`max_active_power`. That is the name PowerSimulations reads an availability forecast under.
The translator divides the profile by its peak. The store holds that shape times
`active_power_limits.max`, in MW.

**The translator does not translate five cases.** It records each one as a skipped
component:

| Case | Cause |
| --- | --- |
| The generator has no `Node` | There is no bus to connect it to. |
| The generator has no `Units` at any time in the horizon | The unit is retired. |
| The generator states `Max Units Built` and runs no units yet | It is a build to decide, not capacity to dispatch. |
| `Max Capacity` comes from a data file | There is no single capacity to divide the per-unit fields by. |
| The capacity is 0 | The generator can never dispatch. |

`committable` is not a Sienna field. Whether a thermal generator is unit-committed is a
choice you make at the solve, not data in the system. Refer to
[The unit commitment answer](#the-unit-commitment-answer).

## `Generator` → `RenewableDispatch`

A generator becomes a `RenewableDispatch` when it burns no fuel and your mappings file gives
its category the type `RenewableDispatch`.

| Sienna field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | `Generator.name` | `direct` |
| `bus` | | The `Node` of the generator | `direct` |
| `prime_mover_type` | | The category of the generator, through your mappings file | `mapped by you` |
| `base_power` | MVA | `Max Capacity × Units`, or the peak of the profile that supplies the capacity | `derived` |
| `rating` | MVA | `base_power` × the availability | `derived` |
| `power_units` | | `NATURAL_UNITS` | `default` |
| `active_power` | MW | The available capacity | `derived` |
| `power_factor` | | `1.0` | `default` |
| `operation_cost.variable_operation_cost` | $/MWh | `VO&M Charge`, or `0.0` | `derived` |
| `reactive_power` / `reactive_power_limits` | MVAR | PLEXOS states no reactive data. | `default` |

A `Rating` profile or a `Rating Factor` profile becomes a `TimeSeriesAssociation` on
`max_active_power`. A generator whose profile never changes gets no association, and the
validation run gives it a flat one so PowerSimulations can read the whole fleet.

`RenewableNonDispatch` takes the same mapping, minus `operation_cost`, which that type does
not have. A `VO&M Charge` on such a generator is `dropped`.

## Hydro → `HydroTurbine` and `HydroReservoir`

| Your unit | Becomes |
| --- | --- |
| It has a `Head Storage` membership | `HydroTurbine`, and its head `Storage` becomes a `HydroReservoir` |
| Your mappings file names `HydroDispatch` for `reservoir_hydro` | `HydroDispatch`, with no `HydroReservoir` |
| It has a `Head Storage` and a `Tail Storage`, states no pump, and a `Waterway` leaves the tail | `HydroTurbine`, because it releases water down a cascade and cannot lift it back |
| It has a `Tail Storage` and no `Head Storage` | Not translated |
| It has no storage at all | An ordinary generator, from the `category` or `fuel` row its carrier names |
| It has a `Head Storage`, and your mappings file names its carrier as `ThermalStandard` | A `ThermalStandard`. Its `Storage` holds fuel, and Sienna states no fuel store, so the `Storage` is left out and `decisions.md` says why. |

### The turbine

A `HydroTurbine` and a `HydroDispatch` take the same fields from your model.

A `HydroTurbine` also states `conversion_factor`, the energy that one cubic metre of water
gives. Your `Efficiency Incr`, in MW for each m³/s, gives it as
`Efficiency Incr / 3600 / base_power`. A turbine that states no `Efficiency Incr` keeps
the Sienna default of 1.0.

| Sienna field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | The `Generator.name` of the turbine | `direct` |
| `bus` | | The `Node` of the turbine | `direct` |
| `prime_mover_type` | | `HY` | `mapped by you` |
| `base_power` | MVA | `Max Capacity × Units` | `derived` |
| `rating` | MVA | `base_power` × the availability | `derived` |
| `power_units` | | `NATURAL_UNITS` | `default` |
| `active_power_limits` | MW | `(0, the available capacity)` | `derived` |
| `operation_cost.variable_operation_cost` | $/MWh | `VO&M Charge`, or `0.0` | `derived` |
| `ramp_limits`, `time_limits`, `status`, `time_at_status` | | The type carries them, and the chain supplies none. | `dropped` |
| `efficiency`, `conversion_factor`, `outflow_limits`, `turbine_type`, `travel_time` | | Not written, so a reader takes the SiennaSchemas default. The translator reads no PLEXOS property for them. | `default` |

### The reservoir

Each `Storage` of a cascade becomes one `HydroReservoir`, named for the `Storage`. A
cascade holds the head and the tail `Storage` of each `HydroTurbine`, and each `Storage`
that a `Waterway` joins to one of them. A reservoir names the turbines whose head it is in
`downstream_turbines`, and the turbines whose tail it is in `upstream_turbines`. The unit
that the `Storage` states its volumes in sets `level_data_type`, and so the unit of every
level and of the inflow.

| Your volumes are stated in | `level_data_type` | Levels | Inflow |
| --- | --- | --- | --- |
| `MWh`, `GWh`, or no unit | `ENERGY` | MWh | MW |
| `CMD` (one m³/s for one day, 86,400 m³) or `m3` | `USABLE_VOLUME` | m³ | m³/s, from `cumec` or `m3/s` |

| Sienna field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | The `Storage.name` | `direct` |
| `available` | | `True` | `default` |
| `level_data_type` | | The unit of the volumes, from the table above | `derived` |
| `storage_level_limits.max` | MWh or m³ | `Max Volume` | `derived` |
| `storage_level_limits.min` | MWh or m³ | `Min Volume`, or `0.0` | `derived` |
| `initial_level` | MWh or m³ | `Initial Volume`, held between the two limits, or the floor | `derived` |
| `inflow` | MW or m³/s | `Natural Inflow`, or the peak of its profile, or `0.0` | `derived` |
| `outflow` | MW or m³/s | `0.0`, because the turbines draw the water | `default` |
| `intake_elevation` | m | `0.0` | `default` |
| `head_to_volume_factor` | | A linear function with both terms `0.0` | `default` |
| `operation_cost` | | A `HydroReservoirCost` with every cost `0.0` | `default` |
| `downstream_turbines` | | The `HydroTurbine`s that name the `Storage` as their `Head Storage` | `derived` |
| `upstream_turbines` | | `[]` | `default` |
| `upstream_reservoirs` | | The `Storage From` of each `Waterway` whose `Storage To` is this `Storage` | `derived` |

A `Natural Inflow` that reads a data file becomes a `TimeSeriesAssociation` named `inflow`
on the reservoir. The store holds the profile as the model states it, in the unit of the
reservoir.

A reservoir is left out, and `decisions.md` and the log name it, in these cases:

- The `Storage` states its volumes in a unit that converts to neither MWh nor m³.
- `Max Volume` comes from a data file rather than a value.
- The `Storage` states no `Max Volume`.

The turbine still translates.

A `Natural Inflow` in a unit that does not match the volumes gives an `inflow` of `0.0`, and
`decisions.md` says so.

### The waterway

A `Waterway` makes its `Storage To` name its `Storage From` among its
`upstream_reservoirs`. Sienna states no route between two reservoirs, so every property of a
`Waterway`, such as `Max Flow` and `Min Flow`, is `dropped`. A `Waterway` that does not join
two reservoirs of the system is also `dropped`.

### In a solve

The solve template gives a `HydroDispatch` the `HydroDispatchRunOfRiverBudget`
formulation, and it states no formulation for a `HydroTurbine` or a `HydroReservoir`. So the
`sienna-to-power-simulations` pipeline writes each `HydroTurbine` as a `HydroDispatch`, and it
leaves each `HydroReservoir` out. `decisions.md` names both.

## Pumped storage → `EnergyReservoirStorage`

The turbine, its head reservoir and its tail reservoir become **one**
`EnergyReservoirStorage`, named for the turbine.

| Sienna field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | The `Generator.name` of the turbine | `direct` |
| `bus` | | The `Node` of the turbine | `direct` |
| `prime_mover_type` | | `PS` | `mapped by you` |
| `storage_technology_type` | | `OTHER_MECH`, because the Sienna list has no pumped storage value | `default` |
| `base_power` | MVA | `Max Capacity × Units` | `derived` |
| `rating` | pu | The turbine capacity as a fraction of `base_power` | `derived` |
| `storage_capacity` | MWh | The `Max Volume` of the head reservoir, where the model gives it in MWh | `derived` |
| `storage_level_limits` | pu | `(0.0, 1.0)`, so the whole capacity is usable | `default` |
| `initial_storage_capacity_level` | pu | The `Initial Volume` of the head reservoir ÷ the energy capacity, held between 0 and 1 | `derived` |
| `input_active_power_limits` | pu | `(0.0, the pump capacity)` | `derived` |
| `output_active_power_limits` | pu | `(0.0, the turbine capacity)` | `derived` |
| `efficiency` | | `√(Pump Efficiency)` for the charge and for the discharge | `derived` |
| `cycle_limits` | | `10000`, so the cycling limit never binds and the storage target does the work | `default` |
| `operation_cost.charge_variable_cost` | $/MWh | `0.0` | `default` |
| `operation_cost.discharge_variable_cost` | $/MWh | `VO&M Charge`, or `0.0` | `derived` |

The head reservoir and the tail reservoir do not become components of their own. The
elevation, an efficiency that changes with the level, and a `Max Volume` stated in water are
`dropped`.

## `Battery` → `EnergyReservoirStorage`

| Sienna field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | `Battery.name` | `direct` |
| `bus` | | The `Node` of the battery | `direct` |
| `prime_mover_type` | | `BA` | `mapped by you` |
| `storage_technology_type` | | `OTHER_MECH` | `default` |
| `base_power` | MVA | `Max Power` | `direct` |
| `rating` | pu | `1.0` | `default` |
| `storage_capacity` | MWh | `Capacity`, or `Duration × Max Power` | `derived` |
| `initial_storage_capacity_level` | pu | `Initial SoC % × Capacity` ÷ the energy capacity, held between 0 and 1 | `derived` |
| `input_active_power_limits` / `output_active_power_limits` | pu | `(0.0, 1.0)` for each | `default` |
| `efficiency` | | `√(Charge Efficiency)` for the charge and for the discharge | `derived` |
| `operation_cost.charge_variable_cost` | $/MWh | `0.0` | `default` |
| `operation_cost.discharge_variable_cost` | $/MWh | `0.0` | `default` |

`Min SoC`, `Max SoC` and `Discharge Efficiency` are `dropped`. The whole energy capacity is
usable, and the round trip efficiency splits evenly across the two directions.

## `Fuel`

A `Fuel` becomes no component. It does two things:

- It names the carrier that your mappings file turns into `fuel` and
  `prime_mover_type`.
- Its `Price` sets the fuel term of `operation_cost.variable_operation_cost`, which is `price × heat rate`.

The translator carries your fuel names as your model spells them, so two fuels that are one
chemistry at two regional prices need two rows in your mappings file. Give both the same
Sienna type.

A generator that burns more than one fuel keeps its first fuel. The rest are `dropped`, and
`decisions.md` names each one.

## `Emission`

An `Emission` becomes no component. Its `Price` and the `Production Rate` of the fuel add a
carbon term to `operation_cost.variable_operation_cost`, which is `price × production rate × heat rate`.

An emission cap is `dropped`. Only the price reaches the cost.

## `Reserve` → `OnlineReserve` or `OfflineReserve`

The PLEXOS `Type` of a reserve chooses the Sienna service:

| PLEXOS `Type` | Sienna service | `reserve_direction` |
| --- | --- | --- |
| 1 Raise, 3 Regulation Raise | `OnlineReserve` | `UP` |
| 2 Lower, 4 Regulation Lower | `OnlineReserve` | `DOWN` |
| 7 Regulation | `OnlineReserve` | `SYMMETRIC` |
| 5 Replacement | `OfflineReserve` | An `OfflineReserve` states no direction. |
| 6 Operational, or a code the translator does not know | No service | |
| 8 Inertia | No service, because an inertia reserve is not a quantity of MW | |

| Sienna field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | The `Reserve` name | `direct` |
| `available` | | `Is Enabled`, else `True` | `derived` or `default` |
| `requirement` | MW | `Min Provision` in MW, or the peak of a requirement that varies | `derived` |
| `time_frame` | min | `60.0`, one hourly snapshot | `default` |
| `sustained_time` | min | `Duration` in seconds / 60, else `60.0` | `derived` or `default` |
| `max_output_fraction` | | `1.0` | `default` |
| `max_participation_factor` | | `1.0` | `default` |
| `deployed_fraction` | | `0.0` | `default` |
| `reserve_direction` | | The `Type`, as the table above gives | `derived` |

A requirement that varies becomes a `TimeSeriesAssociation` on `requirement`. The store holds
the requirement in MW at each snapshot, and `requirement` states its peak.

Each generator in the `Generators` collection of the reserve, and each battery in its
`Batteries` collection, becomes one row of the document's `service_associations` list. A
unit that the Sienna system does not hold joins no service. `decisions.md` names each one.

A reserve with no requirement in MW becomes no service. `Mutually Exclusive` is `dropped`,
because a Sienna service has no field for it. `VoRS` is `dropped`, because the translator
writes no demand curve to the `variable` field of the service. The record in
`extensions.json` keeps both.

## `Market` → `ThermalStandard`

A `Market` becomes one import generator on the node where it trades, priced at the purchase
price of the market. It takes the `ThermalStandard` mapping. The export side of the market is
`dropped`.

---

## Forced outage → `GeometricDistributionForcedOutage`

A `Generator` or a `Battery` that translates, and that states a `Forced Outage Rate` above
0, gets one `GeometricDistributionForcedOutage` supplemental attribute. A
`supplemental_attribute_associations` row joins the attribute to the Sienna component of
the unit.

PLEXOS states the share of the time that the unit is out, as a percentage, and the hours
that one repair takes. Sienna states the minutes that one recovery takes, and the chance in
each minute that a unit in service fails. In a model with two states, the share of the time
out is `p / (p + 1 / T)` for a chance `p` and a recovery time `T`. So the chance is
`r / (1 - r) / T` for a share `r`.

| Sienna field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `mean_time_to_recovery` | min | `Mean Time to Repair` in hours × 60 | `derived` |
| `outage_transition_probability` | | `Forced Outage Rate / 100 / (1 - Forced Outage Rate / 100) / mean_time_to_recovery` | `derived` |
| `identifier` | | The PLEXOS name of the unit | `derived` |
| `monitored_components` | | An empty list. PLEXOS names no component that an outage watches. | `default` |
| `id` | | The position of the attribute, after the ids of all components | `default` |

The unit keeps no forced outage, and `decisions.md` records a `NOT_MAPPED` row, in these
cases:

| The case | The reason |
| --- | --- |
| `Forced Outage Rate` is 100 % or more | The unit has no time in service to fail from. |
| `Mean Time to Repair` is absent, or 0 or less | The recovery time and the chance cannot be stated. |
| `Forced Outage Rate` comes from a data file | A forced outage states one rate. |

The run also writes one warning that names three of the units and counts the rest. A
`Mean Time to Repair` on a unit with no `Forced Outage Rate` above 0 has nothing to belong to,
so `decisions.md` records it as `NOT_MAPPED`.

The `sienna-to-power-simulations` pipeline writes no supplemental attribute and no
`LoadZone`. Each bus there takes a null `load_zone`, and `decisions.md` records each one. The
`sienna-to-pypsa` pipeline reads neither.

## The unit commitment answer

The system holds the start cost and the minimum up and down times of every thermal
generator. Whether the solve applies them is your answer at the `Unit commitment treatment?`
prompt:

| Your answer | The formulation | What it applies |
| --- | --- | --- |
| `exact` | `ThermalStandardUnitCommitment` | The on/off decision as a true binary, the start cost, and the minimum up and down times. The solve is a mixed-integer program and stops at a relative gap of 1%. |
| `linearised` | `ThermalBasicDispatch` | Neither the start cost nor the time limits. There is no on/off variable at all. |

PowerSimulations has no relaxed unit commitment formulation, so the answer `linearised` means
something different here from what it means on the PyPSA path. On the PyPSA path, `linearised`
keeps the start cost and the minimum up and down times, and relaxes the on/off variable to a
number between 0 and 1. Here it drops all three. Answer `exact` to keep them.

---

## Special business rules

PLEXOS holds some data in a form that a simple property-by-property reading gets wrong.
These rules control how the translator reads those values.

### Properties holding several values

| Property | Value used |
| --- | --- |
| `Heat Rate` in bands | The average. Sienna gets one linear cost curve. |
| `Max Flow` in bands | The lowest. |
| `Start Cost` in bands | The cold start band. |
| `Fuels` on one generator | The first. |

### Which entry applies when

A property stamped with dates takes the value in force when the year you translate opens. A
value that changes during that year becomes a time series over the snapshots.

| Property | Meaning |
| --- | --- |
| `Units` | The quantity of units in service. `0` at every date is a retired unit, unless the object also states `Max Units Built`, which makes it a candidate. |
| `Max Capacity` | The capacity of one unit. |

### Availability and outages

| Property | Capacity available |
| --- | --- |
| `Outage Factor` | That percentage of the capacity |
| `Outage Rating` | The capacity less that quantity of MW |
| Neither property, but the model has outage data | None. This is a full outage. |
| The model has no outage data | The full capacity |

A generator that states `Units Out` takes no derate from these properties. `Units Out`
says when its units are out, so the capacity during an outage belongs to those units and
not to the units that run.

A `Rating` profile and an outage derate **multiply**. A static `Rating` above `Max Capacity ×
Units` is the capacity of the generator, so `base_power` takes the `Rating`.

`Units Out` gives the quantity of units unavailable at each snapshot, so it becomes a derate
of `1 - Units Out / Units`.

### Unit conversions

| Value | Read in |
| --- | --- |
| `Heat Rate`, `Heat Rate Incr` | GJ/MWh |
| Fuel `Price` | currency/GJ |
| Emission `Price` | currency/tonne |
| `Max Capacity`, `Rating`, `Min Stable Level`, `Max Flow` | MW |
| `Max Ramp Up`, `Max Ramp Down` | MW/min |
| `Min Up Time`, `Min Down Time` | h |
| `VO&M Charge` | currency/MWh |

A currency symbol has no conversion, so a model in euros reads as a model in dollars.

| Value | Becomes |
| --- | --- |
| `Min Stable Factor`, `Rating Factor`, `Outage Factor` | The percentage ÷ 100 |
| `Max Ramp Up` / `Max Ramp Down` | Sienna holds a ramp in MW/min, the unit PLEXOS states. A rate that covers the whole capacity within one snapshot reads back as the rate that covers exactly that, because neither rate ever binds. SiennaSchemas requires both directions, so a generator that states only `Max Ramp Up` gets the non-binding rate for down. |
| Impedance | Ω into per unit, on the base of the bus voltage and 100 MVA |

### Storage

| `Model` | Volume is in |
| --- | --- |
| `ENERGY` | MWh, so the volume becomes `storage_capacity` |
| `LEVEL` | Metres, which is not an energy |
| `VOLUME` | Cubic metres, which is not an energy |

A volume that is not an energy is `dropped`, and `decisions.md` gives the unit the model
used. That storage unit then takes a capacity of one hour of its own power, which is far less
energy than your model gives it.

---

## Not translated

| PLEXOS | Effect |
| --- | --- |
| A `Reserve` with no direction, an inertia `Reserve`, or a `Reserve` with no requirement in MW | No Sienna service. The record still reaches `extensions.json`. Refer to [`Reserve` → `OnlineReserve` or `OfflineReserve`](#reserve--onlinereserve-or-offlinereserve). |
| A pumped-storage reservoir `Natural Inflow` | The value reaches `extensions.json`, and one that changes reaches `storage.parquet` beside it, but Sienna's `EnergyReservoirStorage` states no inflow, so nothing refills the reservoir. A reservoir-hydro `Natural Inflow` reaches the `HydroReservoir`. |
| A storage unit's `Units Out` | The derate reaches `storage.parquet`, but Sienna states one rating and no series against it, so the unit discharges at full power all year. |
| A `Fuel` priced by date | The cost it makes at each snapshot reaches `generators.parquet`, but a Sienna cost curve states one price, so the generator pays the price in force at the start of the year. |
| Region `VoLL` | The system has no load shedding resource, so a window short of capacity does not solve and no run reports the unserved energy. |
| `Interface` | Nothing applies the group flow limits, so a transfer can go above a limit your model obeys. |
| `Transformer` | The translator does not carry it. |
| `Constraint` | The record reaches `extensions.json`, but nothing applies the custom constraints, which include the RPS targets and the emission targets. |
| `Waterway` properties | `Max Flow`, `Min Flow` and the penalties are lost, because Sienna states no route between two reservoirs. The route itself reaches `upstream_reservoirs`. |
| `Decision Variable` | The translator does not carry it. |
| Emission caps | Nothing applies them. Only the carbon price reaches the cost. |
| Market exports | Refer to [`Market`](#market--thermalstandard). |
| More than one scenario | The translator uses the values of the selected Model only. |
| Gas, heat and water networks | The translator accepts electricity only. |

## Assumptions worth checking against your model

The translator reads these values in a particular way. If your model uses a different
convention, the translator gives wrong values.

| Value | Assumed as |
| --- | --- |
| `Outage Factor`, `Rating Factor`, `Min Stable Factor` | A percentage |
| `Charge Efficiency`, `Pump Efficiency` | A round trip value, split evenly across the two directions |
| `Max Ramp Up`, `Max Ramp Down` | MW per minute |
| `Start Cost` | A cost for one start, not a cost per MW |
| A `Fuel` name | One technology. Two names are two carriers, even where they are one chemistry. |
| `Region.Load` | A demand in MW, not a participation share |
