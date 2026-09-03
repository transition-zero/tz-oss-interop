# Translation from PLEXOS to Sienna

This document tells you what each part of your PLEXOS model becomes in the Sienna system.
It gives the source of each field.

> **Scope:** the translator accepts electricity-only models, and it translates them for
> dispatch. It does not translate capacity expansion, custom constraints or hydro cascades.
> It does not carry the reserves to a file you keep. Refer to
> [Not translated](#not-translated) and to
> [the gap analysis](plexos-to-sienna-gap-analysis.md), which states what each loss does to a
> dispatch.

The `plexos-to-sienna` pipeline runs through a PyPSA network on the way. This document does
not describe that network. It states the mapping as one step, because that is what you give
and what you get. Where the intermediate form loses something, this document says so as a
property of the PLEXOS to Sienna mapping.

---

## What becomes what

| PLEXOS | Sienna |
| --- | --- |
| [`Node`](#node--acbus) | `ACBus`, and an `Arc` for each pair of nodes a branch joins |
| [`Region`](#region--area) | `Area`. It also gives a `PowerLoad`. |
| [Region `Load` property](#region-load--powerload) | `PowerLoad`, or `InterruptiblePowerLoad` on a reliability run |
| [`Line`](#line--line-or-twoterminalgenerichvdcline) | `Line` if it has impedance, or `TwoTerminalGenericHVDCLine` if it has none |
| [`Generator`](#generator--thermalstandard), thermal | `ThermalStandard` |
| [`Generator`](#generator--renewabledispatch), renewable | `RenewableDispatch`, or `RenewableNonDispatch` where your mappings file says so |
| [`Generator`](#hydro--hydrodispatch), reservoir hydro | `HydroDispatch` |
| [`Generator` and two `Storage`](#pumped-storage--energyreservoirstorage), pumped storage | One `EnergyReservoirStorage` |
| [`Battery`](#battery--energyreservoirstorage) | `EnergyReservoirStorage` |
| [`Fuel`](#fuel) | No component. It names the carrier your mappings file turns into `fuel_type` and `prime_mover_type`, and it sets part of `operation_cost`. |
| [`Emission`](#emission) | No component. It adds a carbon term to `operation_cost`. |
| [`Market`](#market--thermalstandard) | An import `ThermalStandard` |
| `Reserve` | No component. The record reaches `extensions.json`. Refer to [Not translated](#not-translated). |
| [Region `VoLL`](#region-load--interruptiblepowerload) | The `operation_cost` of an `InterruptiblePowerLoad`, on a reliability run only. |
| `Zone`, `Interface`, `Transformer`, `Constraint`, `Waterway`, `Decision Variable` | [Not translated](#not-translated) |
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
- **One scenario only.** The Model you select applies its own Scenario overlays. The
  translator reads no other scenario.
- **One calendar year at a time.** The year you give narrows the Horizon of the Model. Every
  dated value is the one in force during that year.
- **Sienna keeps one value where PLEXOS keeps several.** Refer to
  [Special business rules](#special-business-rules).
- **Profiles go into the HDF5 companion.** A `Rating` profile, an outage profile and a demand
  profile all become a `TimeSeriesAssociation` record whose values live in
  `system_time_series_storage.h5`.

---

## The carrier mappings file

A Sienna generator states a `prime_mover_type`, and a thermal one also states a `fuel_type`.
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
| `reservoir_hydro` | `HydroDispatch` | `HY` |
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
| `load_zone` | | PLEXOS `Zone` is not translated. | `dropped` |

Each `Node` becomes one `ACBus`. PLEXOS marks no node AC or DC, so every bus is AC. A node
that a branch touches also gives an `Arc`, which is the Sienna object holding the two ends of
a `Line` or an HVDC line.

## `Region` → `Area`

Each Region becomes one `Area`, and each of its nodes points at that Area. Its `Load`
property becomes a [`PowerLoad`](#region-load--powerload). The `Area` carries a name only:
its `peak_active_power`, `peak_reactive_power` and `load_response` all take zero, because
PLEXOS states none of them on a Region.

`Price of Dump Energy` is `dropped`. So is `VoLL`, except on a reliability run, which prices
the region's load with it: refer to
[Region `Load` -> `InterruptiblePowerLoad`](#region-load--interruptiblepowerload).

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

A demand that reads a data file becomes a `TimeSeriesAssociation` on `max_active_power`,
whose stored shape peaks at 1.0 and scales back to MW through the peak.

A region `Load` stated as a participation share, not as megawatts, stops the translation
rather than reading a share as a quantity of power.

A region that contains more than one node is not translated, because a Sienna `PowerLoad`
sits on one bus.

## Region `Load` → `InterruptiblePowerLoad`

`plexos-to-sienna-monte-carlo-reliability` writes an `InterruptiblePowerLoad` in place of
every `PowerLoad`. It is the Sienna type a solve may cut, so a window short of capacity
returns a shortfall in MWh instead of failing to solve.

Which chain you run decides which type you get:

| The chain you run | The type each region's load becomes | What it prices |
| --- | --- | --- |
| `plexos-to-sienna` | `PowerLoad` | Nothing. The solve must serve every MW or fail. |
| `plexos-to-sienna-monte-carlo` | `PowerLoad` | Nothing, as above, once per replication. |
| `plexos-to-sienna-monte-carlo-reliability` | `InterruptiblePowerLoad` | The region's `VoLL`, per MWh cut. |

The type carries every field a `PowerLoad` carries, and one more:

| Sienna field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `operation_cost` | $/MWh | The containing Region's `VoLL` | `derived` |

A region that states no `VoLL` of its own takes PLEXOS's own declared default, $10,000/MWh,
which is the price the PyPSA side of the same run sheds at.

The cost is a `LoadCost` whose `variable` is a linear `CostCurve` in natural units, holding
the price as its proportional term. PowerSimulations applies that curve to the power the
solve serves rather than to the power it cuts, with a negative multiplier, so the objective
number it reports is not the same quantity as a PyPSA objective. Refer to
[the gap analysis](plexos-to-sienna-gap-analysis.md#a-sienna-objective-and-a-pypsa-objective-do-not-compare).

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
| `active_power_limits_from` | MW | `(Min Flow, Max Flow)` | `derived` |
| `active_power_limits_to` | MW | `(Min Flow, Max Flow)` | `derived` |
| `reactive_power_limits_from` / `_to` | MVAR | `(0.0, 0.0)` | `default` |
| `loss` | | A zero cost curve, so the line has no loss | `default` |
| `available` | | `True` | `default` |
| `Wheeling Charge` | | The HVDC type prices no flow. | `dropped` |

A line that flows in two directions has a negative `Min Flow`, so its lower limit is
negative. A line that flows one way has a lower limit of zero.

## `Generator` → `ThermalStandard`

A generator becomes a `ThermalStandard` when it burns a `Fuel`, states a heat rate, and your
mappings file gives that fuel the type `ThermalStandard`.

| Sienna field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | `Generator.name` | `direct` |
| `bus` | | The `Node` of the generator | `direct` |
| `fuel_type` | | The `Fuel` of the generator, through your mappings file | `mapped by you` |
| `prime_mover_type` | | The `Fuel` of the generator, through your mappings file | `mapped by you` |
| `base_power` | MVA | `Max Capacity × Units`, or the static `Rating` where that is higher | `derived` |
| `rating` | pu | The availability, which is 1.0 unless an outage or a `Rating` derates it | `derived` |
| `active_power_limits` | MW | `(Min Stable Level, the available capacity)` | `derived` |
| `active_power` | MW | `Min Stable Level` | `derived` |
| `ramp_limits` | MW/min | `Max Ramp Up` / `Max Ramp Down`, held to the rate that covers the whole capacity in one snapshot | `derived` |
| `time_limits` | h | `Min Up Time` / `Min Down Time` | `direct` |
| `time_at_status` | h | `10000.0`, because PLEXOS states no prior on-time | `default` |
| `must_run` | | `False` | `default` |
| `status` | | `True` | `default` |
| `operation_cost.variable` | $/MWh | `fuel price × Heat Rate + VO&M Charge`, and the carbon term if there is one | `derived` |
| `operation_cost.start_up` | $ | `Start Cost`, the cold start band | `direct` |
| `operation_cost.shut_down` | $ | `0.0`, because PLEXOS prices only starts | `default` |
| `operation_cost.fixed` | $ | `0.0` | `default` |
| `reactive_power` / `reactive_power_limits` | MVAR | PLEXOS states no reactive data. | `default` |

An availability that changes with time becomes a `TimeSeriesAssociation` on
`max_active_power`. That is the name PowerSimulations reads an availability forecast under.
The stored shape peaks at 1.0 and scales back to MW through `active_power_limits.max`.

**The translator does not translate four cases.** It records each one as a skipped
component:

| Case | Cause |
| --- | --- |
| The generator has no `Node` | There is no bus to connect it to. |
| The generator has no `Units` at any time in the horizon | The unit is retired. |
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
| `rating` | pu | The availability | `derived` |
| `active_power` | MW | The available capacity | `derived` |
| `power_factor` | | `1.0` | `default` |
| `operation_cost.variable` | $/MWh | `VO&M Charge`, or `0.0` | `derived` |
| `reactive_power` / `reactive_power_limits` | MVAR | PLEXOS states no reactive data. | `default` |

A `Rating` profile or a `Rating Factor` profile becomes a `TimeSeriesAssociation` on
`max_active_power`. A generator whose profile never changes gets no association, and the
validation run gives it a flat one so PowerSimulations can read the whole fleet.

`RenewableNonDispatch` takes the same mapping, minus `operation_cost`, which that type does
not have. A `VO&M Charge` on such a generator is `dropped`.

## Hydro → `HydroDispatch`

| Your unit | Becomes |
| --- | --- |
| It has a `Head Storage` membership | `HydroDispatch` |
| It has a `Tail Storage` and no `Head Storage` | Not translated |
| It has no storage at all | An ordinary generator, from the `category` or `fuel` row its carrier names |

| Sienna field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | The `Generator.name` of the turbine | `direct` |
| `bus` | | The `Node` of the turbine | `direct` |
| `prime_mover_type` | | `HY` | `mapped by you` |
| `base_power` | MVA | `Max Capacity × Units` | `derived` |
| `rating` | pu | The availability | `derived` |
| `active_power_limits` | MW | `(0, the available capacity)` | `derived` |
| `operation_cost.variable` | $/MWh | `VO&M Charge`, or `0.0` | `derived` |
| `ramp_limits`, `time_limits`, `status`, `time_at_status` | | The type carries them, and the chain supplies none. | `dropped` |

A `HydroDispatch` gets two time series: a flat `max_active_power`, which is its own limit,
and a `hydro_budget`, which is its `Natural Inflow` as an energy over the horizon. The solve
applies the budget through `HydroDispatchRunOfRiverBudget`. A `Natural Inflow` in cumec or in
m³/day is a flow of water rather than a power, so it does not reach the budget.

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
| `operation_cost.variable` | $/MWh | `VO&M Charge`, or `0.0` | `derived` |

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
| `operation_cost.variable` | $/MWh | `0.0` | `default` |

`Min SoC`, `Max SoC` and `Discharge Efficiency` are `dropped`. The whole energy capacity is
usable, and the round trip efficiency splits evenly across the two directions.

## `Fuel`

A `Fuel` becomes no component. It does two things:

- It names the carrier that your mappings file turns into `fuel_type` and
  `prime_mover_type`.
- Its `Price` sets the fuel term of `operation_cost.variable`, which is `price × heat rate`.

The translator carries your fuel names as your model spells them, so two fuels that are one
chemistry at two regional prices need two rows in your mappings file. Give both the same
Sienna type.

A generator that burns more than one fuel keeps its first fuel. The rest are `dropped`, and
`decisions.md` names each one.

## `Emission`

An `Emission` becomes no component. Its `Price` and the `Production Rate` of the fuel add a
carbon term to `operation_cost.variable`, which is `price × production rate × heat rate`.

An emission cap is `dropped`. Only the price reaches the cost.

## `Market` → `ThermalStandard`

A `Market` becomes one import generator on the node where it trades, priced at the purchase
price of the market. It takes the `ThermalStandard` mapping. The export side of the market is
`dropped`.

---

## The unit commitment answer

The system holds the start cost and the minimum up and down times of every thermal
generator. Whether the solve applies them is your answer at the `Unit commitment treatment?`
prompt:

| Your answer | The formulation | What it applies |
| --- | --- | --- |
| `exact` | `ThermalStandardUnitCommitment` | The on/off decision as a true binary, the start cost, and the minimum up and down times. The solve is a mixed-integer program and stops at a relative gap of 1%. |
| `linearised` | `ThermalBasicDispatch` | Neither the start cost nor the time limits. There is no on/off variable at all. |

PowerSimulations has no relaxed unit commitment formulation, so the answer `linearised` means
something different here from what it means on the PyPSA path. Refer to
[the gap analysis](plexos-to-sienna-gap-analysis.md#unit-commitment-relaxed).

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
| `Units` | The quantity of units in service. `0` at every date is a retired unit. |
| `Max Capacity` | The capacity of one unit. |

### Availability and outages

| Property | Capacity available |
| --- | --- |
| `Outage Factor` | That percentage of the capacity |
| `Outage Rating` | The capacity less that quantity of MW |
| Neither property, but the model has outage data | None. This is a full outage. |
| The model has no outage data | The full capacity |

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
| `Max Ramp Up` / `Max Ramp Down` | Sienna holds a ramp in MW/min, the unit PLEXOS states. A rate that covers the whole capacity within one snapshot reads back as the rate that covers exactly that, because neither rate ever binds. |
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
| `Reserve` requirements | The record reaches `extensions.json`, and a varying requirement reaches `reserves.parquet` beside it, but nothing applies them. Every generator can run at full output. |
| Region `VoLL`, other than on a reliability run | The system has no load shedding resource, so a window short of capacity does not solve and no run reports the unserved energy. |
| `Zone` | The zonal group is lost. The regional group still becomes an `Area`. |
| `Interface` | Nothing applies the group flow limits, so a transfer can go above a limit your model obeys. |
| `Transformer` | The translator does not carry it. |
| `Constraint` | Nothing applies the custom constraints, which include the RPS targets and the emission targets. |
| `Waterway` | The cascade route between reservoirs is lost. Each reservoir is independent. |
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
