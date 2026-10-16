# Translation from OSeMOSYS to Sienna

This document tells you what each part of your OSeMOSYS model becomes in the Sienna system.
It gives the source of each field.

> **Scope:** the translator accepts the electricity part of a model. The `osemosys-csv-to-sienna`
> pipeline writes the fleet of one model year for dispatch. It writes no capacity expansion.
> What your plan may build becomes a Sienna Investments Portfolio, which
> [the `osemosys-csv-to-sienna-investments` pipeline](translation-from-osemosys-to-sienna-investments.md)
> writes. A fuel that is not electricity has no component. Refer to
> [Not translated](#not-translated) and to [the gap analysis](osemosys-to-sienna-gap-analysis.md),
> which names each thing that the translation loses, and its effect.

## The pipelines

The command of tz-oss-interop is `interop`. Four pipelines read an OSeMOSYS model into Sienna:

| Pipeline | Reads | Writes |
| --- | --- | --- |
| `osemosys-csv-to-sienna` | an otoole model: a configuration YAML file and a directory of CSV files | `system.json`, its HDF5 companion and `extensions.json` |
| `tz-osemosys-to-sienna` | a TZ-format `model.json` file | the same three files |
| `osemosys-csv-to-sienna-investments` | an otoole model | the same three files, and `portfolio.json` |
| `tz-osemosys-to-sienna-investments` | a TZ-format `model.json` file | the same four files |

Each source writes the canonical stage first. The canonical stage is one fixed form of an
OSeMOSYS model. [The canonical OSeMOSYS stage](../developer_documentation/osemosys-canonical-format.md)
describes it. Every step after the source reads the canonical stage, and not the files of your
model. So the two source formats give the same system. No pipeline runs a PyPSA step or builds a
PyPSA table, because Sienna is the hub.

The operations pipelines run these nodes, in this order:

| Node | What it does |
| --- | --- |
| `stage_osemosys_csv` or `stage_tz_osemosys_json` | Writes the canonical stage. |
| `osemosys_canonical_drop_outside_scope` | Removes the locations and the years outside the scope that you give. |
| `osemosys_to_sienna_map_components` | Writes the buses, the loads, the generators, the storages and the lines of one model year. |
| `sienna_relate_components` | Writes one `Area` for each bus area, and one `Arc` for each line. |
| `osemosys_to_sienna_report_unapplied_parameters` | Records each parameter of the model that no step applies. |
| `emit_sienna_files` | Writes `system.json`, `system_time_series_storage.h5` and `extensions.json`. |

The investments pipelines add the step `osemosys_to_sienna_investments_map_technologies` and
the sink `emit_sienna_portfolio`.

This document uses these words:

- **The operations year** is the model year that the system holds.
- **The operations mode** is the operating mode whose values the system uses.
- **A representative day** is one day of 24 hours that stands for a number of days of the
  year. Its **weight** is that number of days.
- **A carriers row** is one row of the `carriers:` part of your mappings file.

---

## The structural decisions

OSeMOSYS is a capacity expansion model over many years. A Sienna system holds one fixed fleet
that PowerSimulations.jl dispatches. Six decisions bridge the two.

### Operations year

The system holds the fleet of one model year. You give that year as the parameter `year` of
the step `osemosys_to_sienna_map_components`. The parameter has no default, so the REPL asks
for it at the prompt `step[1].year`. In `headless_cli`, give it with
`--override 'step[1].year=2030'`. The value `earliest` selects the earliest model year in
scope.

A year that is not a member of the `year` set stops the run. The message lists the model years.

The fleet is the `ResidualCapacity` (`residual_capacity`) of that year. The canonical stage
reads no OSeMOSYS results, so the capacity that a solve of your model builds has no source. A
technology with no residual capacity in the operations year has no component, and
`decisions.md` names it.

### Technology

The kind of a technology controls what it becomes. The canonical stage gives each technology a
kind (refer to [How tz-oss-interop infers a kind](../tutorials/osemosys-mappings.md#how-tz-oss-interop-infers-a-kind)).

| Kind | In the system | In the portfolio |
| --- | --- | --- |
| `SupplyTechnology` | A generator, when its residual capacity in the operations year is above 0 | A `SupplyTechnology`, when a plan may build it |
| `StorageTechnology` | Through the storage that it charges or discharges | Through that storage, as a `StorageTechnology` |
| `AggregateTransportTechnology` | A `TwoTerminalGenericHVDCLine`, when its residual capacity is above 0 | An `AggregateTransportTechnology`, when a plan may build it |
| `fuel_supply`, `export`, `conversion`, or no kind | No component | No technology |

A technology can be in both documents. Its residual capacity is in the system, and the capacity
that a plan may add is in the portfolio.

A technology can state values for two or more operating modes. The system uses one mode for
each technology:

- A generator uses the operations mode. That is mode `1`, when the model holds it. Otherwise it
  is the first member of the `operating_mode` set.
- A storage takes its charge mode from `TechnologyToStorage` (`technology_to_storage`), and its
  discharge mode from `TechnologyFromStorage` (`technology_from_storage`).
- A line uses the operations mode. It also flows back when another mode carries electricity in
  the opposite direction. Refer to [Two-way lines](#two-way-lines).

The variable cost of another mode of a generator goes to `extensions.json`. Each other value of
another mode is lost, and `decisions.md` names it.

### Fuel and location

- A `FUEL` whose annotation states the carrier `electricity` gives a bus at its location. Two
  electricity fuels at one location share one bus.
- Each location of an electricity fuel becomes one `ACBus` and one `Area`.
- A technology between two locations has the location `A~B`. That location is not a bus.
- A fuel that is not electricity has no component. It still sets the fuel cost and the emission
  rate of a plant that burns it. Refer to [The fuel producer rule](#the-fuel-producer-rule).
- OSeMOSYS states no electrical network. So the system is a transport model with no impedance:
  each connection between two locations is a `TwoTerminalGenericHVDCLine`, and the system has no
  `Line`.

### Timeslice

An OSeMOSYS `TIMESLICE` is a share of a year, not an hour. PowerSimulations.jl dispatches over
hours in time order. So the step builds one representative day of 24 hours for each season
and day type. Refer to [The calendar](#the-calendar).

`YearSplit` (`year_split`) does two jobs:

- It converts the energy of a timeslice into MW. A timeslice lasts `year_split × 8760` hours.
- It gives the weight of a representative day: `year_split / day_split`. The weight goes to
  `extensions.json`, in one `representative_period` record for each day.

### Year

The system holds one year. The portfolio holds every year in scope. Refer to
[translation-from-osemosys-to-sienna-investments.md](translation-from-osemosys-to-sienna-investments.md#the-years-of-the-plan).

### Size

The step `osemosys_canonical_drop_outside_scope` takes a subset of the model. It has two
parameters:

| Parameter | Prompt | Value |
| --- | --- | --- |
| `locations` | `step[0].locations` | The locations to keep, separated by commas, for example `DE, FR`. Empty keeps every location. |
| `years` | `step[0].years` | The years to keep, separated by commas, for example `2025, 2030`. Empty keeps every year. |

The step removes each technology, fuel and storage outside the scope from its set, its
annotation table and every parameter table. A member is in scope when every part of its
location is in `locations`. So a technology at `DE~FR` needs both `DE` and `FR`. A member with
no location stays. The step also removes each year outside `years` from every table. A year
that the model does not hold has no effect. `decisions.md` names what the step removes, and one
warning names three of them.

The REPL shows a list that a pipeline file states as text separated by commas. Enter keeps it.

---

## What becomes what

| OSeMOSYS | Sienna |
| --- | --- |
| [The location of an electricity `FUEL`](#location--acbus) | `ACBus`, and an `Area` of the same name |
| [`SpecifiedAnnualDemand` of an electricity fuel](#demand--powerload) | `PowerLoad`, with an hourly time series |
| [`AccumulatedAnnualDemand` of an electricity fuel](#demand--powerload) | A second `PowerLoad`, flat in each hour |
| [`SupplyTechnology`](#supplytechnology--a-generator) | `ThermalStandard`, `RenewableDispatch`, `RenewableNonDispatch` or `HydroDispatch`, as its carriers row names |
| [`STORAGE` and the technologies that charge and discharge it](#storage--energyreservoirstorage) | One `EnergyReservoirStorage` |
| [`AggregateTransportTechnology`](#aggregatetransporttechnology--twoterminalgenerichvdcline) | `TwoTerminalGenericHVDCLine`, and an `Arc` |
| [`TIMESLICE`, `SEASON`, `DAYTYPE`, `DAILYTIMEBRACKET`](#the-calendar) | The hours of each time series, and one `representative_period` record for each day in `extensions.json` |
| [A `fuel_supply` technology](#the-fuel-producer-rule) | No component. It sets the fuel cost and part of the emission rate of each plant that burns its fuel. |
| [`EMISSION`](#the-emission-penalty) | No component. Its rate goes to `extensions.json`, and its penalty adds to the variable cost. |
| [`fuel_supply`, `export`, `conversion`, or no kind](#technologies-with-no-component) | No component. `decisions.md` names each one. |
| Each other parameter | Refer to [Not translated](#not-translated). `decisions.md` names each one that states a value. |

## Reading the tables

The **From** column gives the OSeMOSYS default name and then the canonical name in brackets,
for example `ResidualCapacity` (`residual_capacity`). Your model can use another name. Your
mappings file then maps it to the canonical name.

| Mapping | Meaning |
| --- | --- |
| `direct` | The translator uses your OSeMOSYS value without a change. |
| `derived` | The translator calculates the value from your values, with the formula that the table gives. |
| `default` | OSeMOSYS has no such data. The translator supplies this value. |
| `dropped` | Sienna has no equivalent. The value does not go into the system. |
| `mapped by you` | A carriers row of your mappings file gives the value. |

In each formula, a value is in the Sienna unit after the conversion of
[Units](#units). For example, "residual capacity in MW" is your `ResidualCapacity` multiplied by
the MW of one unit of `units: capacity`.

## Across all components

- **You write one mappings file.** Its `osemosys:` part puts your model into the canonical
  stage. Its `carriers:` part names the Sienna type of each technology category. Refer to
  [The carrier mappings file](#the-carrier-mappings-file).
- **A technology whose category has no carriers row is left out.** The run completes, and
  `decisions.md` names each one.
- **The data of a model never stops a translation.** A component that the system cannot hold is
  left out. `decisions.md` records it as `COMPONENT_SKIPPED`, and one warning names three of
  them. A value that the system cannot hold is recorded as `NOT_MAPPED`.
- **A missing parameter stops the run.** A `year` that is not a model year, and a unit that a
  conversion needs and that `units:` does not state, each stop the run with a message.
- **A name comes from the member.** A component takes the name of its technology, fuel or
  storage. When two regions hold a member of the same name, the name starts with
  `<region>/`.
- **The time series go into the HDF5 companion.** Each series is a `TimeSeriesAssociation`
  record whose values are in `system_time_series_storage.h5`.
- **A value with no Sienna field goes to `extensions.json`.** For example, the fixed cost and
  the emission rates of a generator. Sienna does not read the sidecar. A later tz-oss-interop
  step can read it.
- **The field names are the names that every Sienna translation of tz-oss-interop writes.**
  Two of them differ from the current SiennaSchemas. A `ThermalStandard` states `fuel_type`,
  which SiennaSchemas calls `fuel`. A `TwoTerminalGenericHVDCLine` states
  `active_power_limits_from` and `active_power_limits_to`, and SiennaSchemas now states
  `rating`, `rating_from`, `rating_to` and `operational_flow_limit`.

---

## The carrier mappings file

A Sienna generator states a `prime_mover_type`, and a thermal one also states a fuel. Both are
closed lists. OSeMOSYS states neither, so you tell the translator what each technology
category becomes. The `objects:` part of the file gives each technology its category. The
`carriers:` part gives each category its Sienna type:

```yaml
osemosys:
  units: {capacity: GW, energy: PJ, currency: million USD, currency_year: 2021, emissions: Mt}
  objects:
    fuels:
      - {match: "^(?P<country>[A-Z]{2})ELC$", carrier: electricity, location: "{country}"}
    technologies:
      - {match: "^[A-Z]{2}NGCC", category: gas-combined-cycle}
      - {match: "^[A-Z]{2}SOL", category: solar}
      - {match: "^[A-Z]{2}PHS", category: pumped-storage}
carriers:
  - osemosys_category: gas-combined-cycle
    sienna_component_type: ThermalStandard
    sienna_fuel_type: NATURAL_GAS
    sienna_prime_mover_type: CC
  - osemosys_category: solar
    sienna_component_type: RenewableDispatch
    sienna_prime_mover_type: PVe
  - osemosys_category: pumped-storage
    sienna_component_type: EnergyReservoirStorage
    sienna_prime_mover_type: PS
```

| Field | Value |
| --- | --- |
| `osemosys_category` | A category that `objects:` gives to a technology. One category takes one row. A category that two rows name stops the run. |
| `sienna_component_type` | `ThermalStandard`, `RenewableDispatch`, `RenewableNonDispatch` or `HydroDispatch` for a supply technology. `EnergyReservoirStorage` for the category of a technology that discharges a storage. |
| `sienna_fuel_type` | A `ThermalFuels` value. A `ThermalStandard` row must state it. |
| `sienna_prime_mover_type` | A `PrimeMovers` value. |

The translator infers no type from the data. A supply technology whose category names a type
that is not a generator is left out. A storage whose discharging technology has no row, or a
row that is not `EnergyReservoirStorage`, is left out. The category of a storage technology
needs a row of its own, because the translator supplies no default.

---

## Location → `ACBus`

| Sienna field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | The location of an electricity fuel | `direct` |
| `number` | | The position of the bus, from 1, in name order | `derived` |
| `area` | | The location. `sienna_relate_components` writes one `Area` of that name. | `derived` |
| `bustype` | | `PQ`, because OSeMOSYS states no slack bus | `default` |
| `angle` / `magnitude` | | `0.0` / `1.0` | `default` |
| `voltage_limits` | pu | `(0.9, 1.1)` | `default` |
| `base_voltage` | kV | `1.0`, because OSeMOSYS states no voltage | `default` |
| `available` | | `true` | `default` |

Each bus also gets a `bus` record in `extensions.json` with the carrier `AC`.

An electricity fuel with no location gets no bus. Its demand is lost, and `decisions.md`
names the fuel.

The `Area` of a location holds its name only. Its other fields take their defaults, because
OSeMOSYS states no peak and no load response for a region.

## Demand → `PowerLoad`

Each electricity fuel with a `SpecifiedAnnualDemand` above 0 in the operations year becomes
one `PowerLoad`. Each one with an `AccumulatedAnnualDemand` above 0 becomes a second
`PowerLoad`, named `<fuel>/accumulated`.

| Sienna field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | The fuel, or `<fuel>/accumulated` | `derived` |
| `bus` | | The location of the fuel | `derived` |
| `max_active_power` | MW | The peak hour of the time series | `derived` |
| `active_power` | MW | The first hour of the time series | `derived` |
| `base_power` | MVA | `max(max_active_power, 0.1)` | `derived` |
| `reactive_power` / `max_reactive_power` | MVAR | `0.0` | `default` |
| `conformity` | | `UNDEFINED` | `default` |
| `available` | | `true` | `default` |

The time series is a `TimeSeriesAssociation` on `max_active_power`. Its value in each hour is:

| Load | MW in each hour |
| --- | --- |
| Specified | `SpecifiedAnnualDemand` (`specified_annual_demand`) in MWh × `SpecifiedDemandProfile` (`specified_demand_profile`) of the timeslice of the hour / (`YearSplit` (`year_split`) of that timeslice × 8760 h) |
| Accumulated | `AccumulatedAnnualDemand` (`accumulated_annual_demand`) in MWh / 8760 h |

The step leaves out these demands, and `decisions.md` names each one:

- a demand for a fuel that is not electricity, or for a fuel with no location;
- a negative demand;
- a demand that gives no hour above 0 MW;
- the share of a demand in a timeslice whose `year_split` is 0, which holds no hour.

## `SupplyTechnology` → a generator

A technology of kind `SupplyTechnology` becomes the generator type that its carriers row
names. These checks leave a technology out, in this order:

| Check | Cause |
| --- | --- |
| Its `residual_capacity` in the operations year is 0 or less | The fleet holds none of it. |
| Its category has no carriers row, or it has no category | Nothing gives it a Sienna type. |
| Its carriers row names a type that is not a generator | A supply technology cannot become that type. |
| Its location is not the name of a bus | No bus can hold it. A technology at `A~B` is an example. |
| It puts out no electricity at the operations mode | It has no output to dispatch. |

### The fields of every generator type

| Sienna field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | The technology | `direct` |
| `bus` | | The location of the technology | `direct` |
| `prime_mover_type` | | The carriers row of the category | `mapped by you` |
| `base_power` | MVA | `ResidualCapacity` (`residual_capacity`) of the operations year in MW × the electricity `OutputActivityRatio` (`output_activity_ratio`) at the operations mode | `derived` |
| `rating` | pu | `1.0`. The generator rates at its whole base power, and its availability limits it in each hour. | `default` |
| `active_power` / `reactive_power` | MW / MVAR | `0.0` | `default` |
| `available` | | `true` | `default` |

The electricity output ratio is the sum of `output_activity_ratio` over the electricity fuels.
Each cost and each emission rate below is for each MWh of electricity output. So each one is
divided by that ratio.

### The availability of each hour

The share of its base power that a generator can use in an hour is:

```
CapacityFactor (capacity_factor) of the timeslice of the hour × AvailabilityFactor (availability_factor) of the year
```

OSeMOSYS states `availability_factor` as a limit on the energy of the year. The system applies
it as a derate in each hour. Refer to [Availability as a derate](#availability-as-a-derate).

| Type | Availability |
| --- | --- |
| `RenewableDispatch`, `RenewableNonDispatch`, `HydroDispatch` | A `max_active_power` time series, per unit of `base_power` |
| `ThermalStandard`, share the same in each hour | No time series. `active_power_limits.max` holds the share. |
| `ThermalStandard`, share not the same in each hour | A `max_active_power` time series, per unit of `base_power` |

### `ThermalStandard`

| Sienna field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `fuel_type` | | The carriers row of the category | `mapped by you` |
| `active_power_limits` | MW | `(0, base_power × the share)` when the share is the same in each hour, else `(0, base_power)` | `derived` |
| `operation_cost.variable` | $/MWh | A linear curve. Refer to [The variable cost](#the-variable-cost). | `derived` |
| `operation_cost.fixed` | $ | `0.0`. OSeMOSYS charges its fixed cost on capacity, so the fixed cost goes to `extensions.json`. | `default` |
| `operation_cost.start_up` / `shut_down` | $ | `0.0` | `default` |
| `status` / `must_run` | | `true` / `false` | `default` |
| `time_at_status` | h | `10000.0` | `default` |
| `ramp_limits` / `time_limits` | | None, because OSeMOSYS states no unit commitment data | `dropped` |
| `reactive_power_limits` | MVAR | None | `default` |

The lower limit is 0, because OSeMOSYS states no minimum stable level.

`ramp_limits`, `time_limits`, `status`, `must_run` and `time_at_status` each record
`NOT_MAPPED` with the note "OSeMOSYS states no unit commitment data". A solve with unit
commitment then has no start cost and no minimum up time to apply.

### `RenewableDispatch`

| Sienna field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `operation_cost.variable` | $/MWh | A linear curve. Refer to [The variable cost](#the-variable-cost). | `derived` |
| `operation_cost.fixed` | $ | `0.0` | `default` |
| `power_factor` | | `1.0` | `default` |
| `reactive_power_limits` | MVAR | None | `default` |

### `RenewableNonDispatch`

`RenewableNonDispatch` takes the same fields as `RenewableDispatch`, minus `operation_cost`,
which the type does not have. A variable cost above 0 is `dropped`, and `decisions.md`
records it.

### `HydroDispatch`

| Sienna field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `active_power_limits` | MW | `(0, base_power)` | `derived` |
| `operation_cost.variable` | $/MWh | A linear curve. Refer to [The variable cost](#the-variable-cost). | `derived` |
| `operation_cost.fixed` | $ | `0.0` | `default` |

A `HydroDispatch` gets two time series on the same per-unit values: `max_active_power` and
`hydro_budget`. OSeMOSYS states no energy budget, so the budget is the availability. It binds
nothing beyond the hourly limit.

### The variable cost

```
variable cost ($/MWh) = own cost + Σ over input fuels of the fuel term + Σ over pollutants of the emission penalty
```

| Part | Formula |
| --- | --- |
| Own cost | `VariableCost` (`variable_operation_cost`) at the operations mode, in $/MWh / the electricity output ratio |
| Fuel term of one fuel | `InputActivityRatio` (`input_activity_ratio`) of the fuel × the `VariableCost` of its producer / the `OutputActivityRatio` of the producer for the fuel, in $/MWh / the electricity output ratio of the plant |
| Emission penalty of one pollutant | The emission rate of the plant in t/MWh × `EmissionsPenalty` (`emission_penalty`) of the pollutant in the region of the plant, in $/t |

Refer to [The fuel producer rule](#the-fuel-producer-rule) and to
[The emission penalty](#the-emission-penalty). `decisions.md` records each fuel term and each
penalty as an event of its own, and the cost event reads them.

### The generator record in `extensions.json`

| Field | Unit | From |
| --- | --- | --- |
| `carrier`, `category` | | The category of the technology, which names its carriers row |
| `fom_charge_per_mw_year` | $/MW/yr | `FixedCost` (`fixed_cost`) of the operations year / the electricity output ratio |
| `emission_rates_t_per_mwh` | t/MWh | For each pollutant, (`EmissionActivityRatio` (`emission_rate`) at the operations mode + `input_activity_ratio` × the emission rate of the producer of each fuel for each unit of that fuel) / the electricity output ratio. A rate of 0 is left out. A negative rate stays. |
| `other_mode_variable_costs_per_mwh` | $/MWh | For each other mode that puts out electricity, `variable_operation_cost` of that mode / the electricity output ratio of that mode |
| `annual_output_lower_limit_mwh` | MWh | For each year, `TotalTechnologyAnnualActivityLowerLimit` (`total_technology_annual_activity_lower_limit`) in MWh × the electricity output ratio of that year. A limit of 0 is left out. |
| `annual_output_upper_limit_mwh` | MWh | For each year, `TotalTechnologyAnnualActivityUpperLimit` (`total_technology_annual_activity_upper_limit`) in MWh × the electricity output ratio of that year. A negative limit is left out. |

No step applies the two annual limits. A Sienna system has no field for a limit on the energy
of a year.

## `STORAGE` → `EnergyReservoirStorage`

A member of the `STORAGE` set becomes one `EnergyReservoirStorage`. Two technologies give it
its power:

- **The charging technology** names the storage in `technology_to_storage`, with a value above
  0. Its mode is the charge mode.
- **The discharging technology** names the storage in `technology_from_storage`, with a value
  above 0. Its mode is the discharge mode. It gives the bus, the category and the base power.

One technology can do both. These checks leave a storage out, in this order:

| Check | Cause |
| --- | --- |
| No technology charges it, or no technology discharges it | A Sienna storage takes its power from one of each. |
| Two or more technologies or modes charge it, or discharge it | The same. |
| Its `ResidualStorageCapacity` (`residual_storage_capacity`) in the operations year is 0 or less | It holds no energy. |
| The discharging technology, or the charging technology, has no residual capacity | It cannot discharge, or it cannot charge. |
| The category of the discharging technology has no carriers row | Nothing gives it a Sienna type. |
| That row is not `EnergyReservoirStorage` | The storage cannot become that type. |
| The location of the discharging technology is not a bus | No bus can hold it. |
| The discharging technology puts out no electricity at the discharge mode | It has no output. |
| The charging technology takes in no electricity at the charge mode | It has no input. |

| Sienna field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | The storage | `direct` |
| `bus` | | The location of the discharging technology | `direct` |
| `prime_mover_type` | | The carriers row of the category of the discharging technology | `mapped by you` |
| `storage_technology_type` | | `OTHER_MECH`, because OSeMOSYS states no storage technology | `default` |
| `base_power` | MVA | `residual_capacity` of the discharging technology in MW × its electricity `output_activity_ratio` at the discharge mode | `derived` |
| `rating` | pu | `1.0` | `default` |
| `output_active_power_limits` | pu | min = 0. max = the lower of `base_power` × the `availability_factor` of the discharging technology, and `StorageMaxDischargeRate` (`storage_max_discharge_rate`) in MWh / 8760 h. Then / `base_power`. | `derived` |
| `input_active_power_limits` | pu | min = 0. max = the lower of `residual_capacity` of the charging technology in MW × its electricity `input_activity_ratio` at the charge mode × its `availability_factor`, and `StorageMaxChargeRate` (`storage_max_charge_rate`) in MWh / 8760 h. Then / `base_power`. | `derived` |
| `efficiency.in` | | `technology_to_storage` / the electricity `input_activity_ratio` at the charge mode | `derived` |
| `efficiency.out` | | The electricity `output_activity_ratio` at the discharge mode / `technology_from_storage` | `derived` |
| `storage_capacity` | h | `residual_storage_capacity` of the operations year in MWh / `base_power` | `derived` |
| `storage_level_limits` | pu | `(MinStorageCharge (min_storage_charge), 1.0)`, held between 0 and 1 | `derived` |
| `initial_storage_capacity_level` | pu | `StorageLevelStart` (`storage_level_start`) in MWh / `residual_storage_capacity` in MWh, held between 0 and 1 | `derived` |
| `operation_cost` | $/MWh | A `StorageCost`. The charge cost is `variable_operation_cost` at the charge mode / the electricity input ratio. The discharge cost is `variable_operation_cost` at the discharge mode / the electricity output ratio. Every other cost is 0. | `derived` |
| `conversion_factor` | | `1.0`, because the energy and the level are both in MWh | `default` |
| `storage_target` | pu | `0.0` | `default` |
| `cycle_limits` | | `10000` | `default` |
| `active_power` / `reactive_power` | MW / MVAR | `0.0` | `default` |

A charge rate or a discharge rate of 0 states no limit, because 0 is the default of the
parameter. The fixed cost of the discharging technology goes to the `storage` record of
`extensions.json`, as `fom_charge_per_mw_year` in $/MW/yr.

The step does not apply the `capacity_factor` of a storage technology. `decisions.md` records
each technology that states a value other than 1, and one warning names three.

## `AggregateTransportTechnology` → `TwoTerminalGenericHVDCLine`

At the operations mode, a transport technology takes in electricity at one location and puts
it out at another. The line runs from the bus of the first to the bus of the second. The sink
writes the `Arc` of the two buses. These checks leave a technology out:

| Check | Cause |
| --- | --- |
| Its `residual_capacity` in the operations year is 0 or less | The fleet holds none of it. |
| It does not take in electricity at one location and put it out at another, at the operations mode | A line needs two ends. |

| Sienna field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | The technology | `direct` |
| `arc` | | The location of the electricity fuel that it takes in → the location of the electricity fuel that it puts out | `derived` |
| `active_power_limits_from.max` | MW | `residual_capacity` in MW × `availability_factor` × the electricity `input_activity_ratio` at the operations mode | `derived` |
| `active_power_limits_to.max` | MW | `residual_capacity` in MW × `availability_factor` × the electricity `output_activity_ratio` at the operations mode | `derived` |
| `active_power_limits_from.min` | MW | − `residual_capacity` in MW × `availability_factor` × the electricity output ratio of the flow back, or 0 with no flow back | `derived` |
| `active_power_limits_to.min` | MW | − `residual_capacity` in MW × `availability_factor` × the electricity input ratio of the flow back, or 0 with no flow back | `derived` |
| `loss` | | A linear curve with the proportional term `1 − output ratio / input ratio` at the operations mode | `derived` |
| `reactive_power_limits_from` / `_to` | MVAR | `(0.0, 0.0)` | `default` |
| `active_power_flow` | MW | `0.0` | `default` |
| `available` | | `true` | `default` |

A `variable_operation_cost` above 0 goes to the `controllable_line` record of
`extensions.json`, as `marginal_cost` in $/MWh sent: the cost / the electricity input ratio. A
Sienna line prices no flow.

The step does not apply the `capacity_factor` of a transport technology. `decisions.md` records
it.

## Technologies with no component

The system holds electricity only. The step records each technology below as
`COMPONENT_SKIPPED`, with its kind, and one warning for each reason names three:

| Technology | Note |
| --- | --- |
| Kind `fuel_supply` | It supplies a fuel that is not electricity. The fuel producer rule still reads its cost. |
| Kind `export` | It takes in a fuel and puts out nothing. The system has no component that takes energy out of the model. |
| Kind `conversion`, and each fuel of its flows is electricity | It converts one electricity fuel into another at one location. The two fuels share one bus, so it joins nothing. Its loss is lost, and each demand stays at the value that the model states. |
| Kind `conversion`, and a fuel of its flows is not electricity | The electricity that it takes in is a demand that the system does not hold. |
| No kind, with a flow in the year | It fits no kind, for example a pipeline of a fuel that is not electricity. |

A technology with no kind and no flow in the year moves no energy, so the step does not report
it.

---

## Special business rules

### The calendar

The step builds the hours of the operations year from four parameters:

| Parameter | Use |
| --- | --- |
| `Conversionls` (`timeslice_in_season`) | The season of each timeslice |
| `Conversionld` (`timeslice_in_day_type`) | The day type of each timeslice |
| `Conversionlh` (`timeslice_in_daily_time_bracket`) | The daily time bracket of each timeslice |
| `DaySplit` (`day_split`) | The length of each bracket, as a share of the year |

1. The step makes one day for each season and day type that holds timeslices, in the order of
   the `season` set, then the `day_type` set. The day is named `<season>/<day_type>`.
2. A bracket lasts `day_split × 8760` hours. A length within 0.05 h of a whole number of hours
   is rounded to it. `decisions.md` records each rounding.
3. The brackets of a day follow each other, in the order of the `daily_time_bracket` set. They
   must make 24 h.
4. The days follow each other from 00:00 on 1 January of the operations year. So each time
   series is hourly and in time order.
5. The weight of a day is `year_split / day_split` of its timeslices. When the timeslices of a
   day give different weights, the day takes their mean, and `decisions.md` gives the values.

Each day becomes one `representative_period` record in `extensions.json`:

| Field | Value |
| --- | --- |
| `name` | `<season>/<day_type>` |
| `first_timestamp` | The first hour of the day |
| `hours` | `24` |
| `weight` | The number of days of the year that the day stands for |
| `season`, `day_type` | The members that the day is for |

The step uses **one hour for each timeslice** when the model does not state that structure, and
writes a warning. These conditions cause it:

- the model states no timeslices, or no membership for a season, a day type or a bracket;
- a membership names a member that its set does not hold;
- a timeslice is in two members of one set, or in no day;
- a bracket is more than 0.05 h from a whole number of hours;
- two timeslices of one day share a bracket, or the brackets of a day do not make 24 h.

Then each timeslice is one hour, in the order of the `timeslice` set. Each hour becomes one
record named for its timeslice, with `hours` 1 and the weight `year_split × 8760`.

In both cases, the sum of `hours × weight` over the records is about 8760.

### Units

The canonical stage keeps each value in the unit of the model. The `units:` part of your
mappings file states the units. The step converts each value to the Sienna unit:

| Field of `units:` | Units that the step accepts | Sienna unit |
| --- | --- | --- |
| `capacity` | `kW`, `MW`, `GW`, `TW` | MW |
| `energy` | `kWh`, `MWh`, `GWh`, `TWh`, `kJ`, `MJ`, `GJ`, `TJ`, `PJ`, `EJ` | MWh |
| `emissions` | `t`, `kt`, `Mt`, `Gt` | t |
| `currency` | A three-letter code, with a scale: `USD`, `million USD`, `thousand EUR`, `bn USD`, `MUSD` | $ |
| `currency_year` | A whole year | The cost year of the portfolio |

A value in currency per activity becomes $/MWh. A value in currency per capacity becomes $/MW.
A value in emissions per activity becomes t/MWh. A penalty in currency per emission becomes $/t.

The step converts a column only when it holds a value other than 0. So a model with no cost
needs no `currency`. A unit that a conversion needs and that `units:` does not state stops the
run, and the message names the field, for example `units: energy`. A unit that the step does
not know stops the run, even when no conversion needs it.

The currency scale is the only currency conversion. A code is a name, so a model in euros reads
as a model in dollars.

### The fuel producer rule

A plant pays for each fuel that it takes in at the price of the producer of that fuel. The
producer is the cheapest `fuel_supply` technology that puts out the fuel in the region of the
plant, at the operations mode:

- The price of a producer is its `variable_operation_cost` / its `output_activity_ratio` for the
  fuel.
- A tie goes to the first technology name.
- A technology of any other kind, for example a pipeline, is not a producer.
- A producer whose `total_technology_annual_activity_upper_limit` in the year is 0 makes
  nothing, so it is not a producer.
- A fuel with no producer gives no fuel cost. `decisions.md` records the fuel as `NOT_MAPPED`.

A fuel has one location, so the producer in the region makes the fuel at the place where the
plant takes it in. The note of each fuel term gives the number of producers that the rule chose
from.

The emission rate of the plant also adds the rate of the producer: `input_activity_ratio` × the
`emission_rate` of the producer for each unit of its fuel. A plant with carbon capture keeps a
negative rate.

### The emission penalty

OSeMOSYS charges `EmissionsPenalty` (`emission_penalty`) on each unit of a pollutant that
activity emits. So the penalty is a cost of dispatch. For each pollutant, the variable cost adds
the emission rate of the plant in t/MWh × the penalty of its region in $/t. A negative rate
gives a credit, as in OSeMOSYS.

### Availability as a derate

OSeMOSYS states `AvailabilityFactor` (`availability_factor`) as the share of the year in which
a technology can run. It limits the energy of the year, and the plant can run at full output in
any one timeslice. A Sienna system has no limit on the energy of a year. So the step applies the
factor in each hour, as a derate. A plant then cannot reach its full output in a peak hour.

### Two-way lines

A transport technology can state a second mode that carries electricity back: it takes in
electricity at the far end and puts it out at the near end. The line then flows both ways. The
limits of the flow back come from the ratios of that mode. When two modes flow back, the first
in number order applies.

`decisions.md` records each value of another mode that is not the flow back as `NOT_MAPPED`, and
one warning names three lines. A mode that puts out electricity with no input, which is an
import from outside the model, is one example. A line states one loss. When the loss of the flow
back differs from the forward loss, `decisions.md` records the loss of the flow back as lost.

### Storage

- The energy of a storage is its `residual_storage_capacity`. Sienna holds it in hours of
  `base_power`.
- The default of `residual_storage_capacity` in many models is 999. A storage with no row then
  takes 999 units of energy, as OSeMOSYS gives it. The step translates the value as it is.
- `storage_level_start` states the level at the start of the model period. The step uses it as
  the level at the start of the operations year.

### The defaults of a flow or an emission

The step reads `input_activity_ratio`, `output_activity_ratio` and `emission_rate` only where the
model states a row. A default other than 0 would give every technology that ratio for every fuel
or pollutant and every mode. When a model declares such a default, `decisions.md` records it as
`NOT_MAPPED`, and one warning names the parameter. The step reads each other parameter with its
default.

### The parameters that no step applies

The last step of each pipeline reads each canonical parameter that states a value for the
operations year. A parameter that no step applies gets one `NOT_MAPPED` event for each member
that it states values for, and one warning that names three. A row at the default of the
parameter states nothing, so it does not count. For example:

```
osemosys-to-sienna: total_technology_annual_activity_lower_limit states 24 row(s) for 2021 that the operations system does not apply, for 24 technology(ies): ...
```

---

## Solving the system

The system has no AC line. So solve it with the network model `copperplate`. The network model
`dcp` needs AC branches.

The fleet is the residual capacity of one year. It can be short of the peak load at one
location, and one short hour makes the whole dispatch infeasible. Answer `penalised` at the
`Unserved energy?` prompt to let a load go unserved at a penalty. Refer to
[the solve tutorial](../tutorials/solve.md#unserved-energy).

---

## Not translated

| OSeMOSYS | Effect |
| --- | --- |
| Fuels that are not electricity, and their technologies | No component. The fuel cost and the emission rate of a plant still read them. |
| A `conversion` between two electricity fuels at one location | Its loss is lost. The demand stays at the value that the model states. |
| The capacity that a plan builds, and the years other than the operations year | The system holds the residual capacity of one year. |
| `TotalTechnologyAnnualActivityLowerLimit`, `TotalTechnologyAnnualActivityUpperLimit` | They go to the generator record of `extensions.json`. No step applies them. |
| `TotalTechnologyModelPeriodActivityLowerLimit` / `UpperLimit`, `TechnologyActivityByModeLowerLimit` / `UpperLimit`, `TechnologyActivityDecreaseByModeLimit` | No step applies them. |
| `AnnualEmissionLimit`, `ModelPeriodEmissionLimit` and the region group limits | No step applies them to the system. The portfolio holds some of them. |
| `ReserveMargin`, `ReserveMarginTagFuel`, `ReserveMarginTagTechnology` | No step applies them. |
| `REMinProductionTarget`, `RETagFuel`, `RETagTechnology` | No step applies them. |
| `StorageBalanceDay`, `StorageBalanceSeason`, `StorageBalanceYear`, `StorageMaxHours` | No step applies them to the system. |
| `CapacityToActivityUnit` | No step reads it. Refer to [Assumptions](#assumptions-worth-checking-against-your-model). |
| The values of another operating mode | Refer to [Technology](#technology). |
| The `capacity_factor` of a storage or a transport technology | Not applied. |
| Unit commitment data | OSeMOSYS states none. |
| The trade parameters (`TradeRoute`, `ResidualTradeCapacity` and the other `*Trade*` parameters) | No step reads them. A connection between two locations must be an `AggregateTransportTechnology`. |
| The investment parameters (`CapitalCost`, `OperationalLife` and the others) | The portfolio reads them. Refer to [translation-from-osemosys-to-sienna-investments.md](translation-from-osemosys-to-sienna-investments.md). |
| Each extension table of the canonical stage | No step reads it. |

## Assumptions worth checking against your model

The translator reads these values in a particular way. If your model uses a different
convention, the translator gives wrong values.

| Value | Assumed as |
| --- | --- |
| `units:` | The units of your values. `CapacityToActivityUnit` must agree with them: for example 31.536 PJ for each GW-year. |
| The electricity fuels | Each fuel whose annotation states `carrier: electricity`. A fuel that you do not mark is not electricity. |
| Mode `1` | The mode that the system runs, when the model holds it |
| `AvailabilityFactor` | A derate in each hour, not a limit on the energy of the year |
| `StorageMaxChargeRate`, `StorageMaxDischargeRate` | Energy in a year, in the unit of `units: energy`. A value of 0 states no limit. |
| `StorageLevelStart` | The level at the start of the operations year |
| `TechnologyToStorage`, `TechnologyFromStorage` | One technology and one mode in each direction |
| The cheapest `fuel_supply` technology of a fuel | The price that a plant pays for that fuel, with no limit on what that producer makes |
| A category | One Sienna type, one prime mover and, for a thermal type, one fuel |
