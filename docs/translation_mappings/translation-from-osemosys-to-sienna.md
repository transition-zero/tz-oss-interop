# Translation from OSeMOSYS to Sienna

This document tells you what each part of your OSeMOSYS model becomes in the Sienna system.
It gives the source of each field.

> **Scope:** the translator accepts the electricity part of a model. The `osemosys-csv-to-sienna`
> pipeline writes the fleet of one model year for dispatch. It writes no capacity expansion.
> What your plan may build becomes a Sienna Investments Portfolio, which
> [the `osemosys-csv-to-sienna-investments` pipeline](translation-from-osemosys-to-sienna-investments.md)
> writes. A fuel that is not electricity has no Sienna component. `extensions.json` holds it,
> and each technology on it, as PyPSA components for the Sienna to PyPSA hop. Refer to
> [The fuels that are not electricity](#the-fuels-that-are-not-electricity), to
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
| `osemosys_to_sienna_map_components` | Writes the buses, the loads, the generators, the storages and the lines of one model year, and the records of the fuels that are not electricity. |
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
| `fuel_supply`, `export`, `conversion`, or no kind | No component. A record of `extensions.json` for each mode, when a fuel of its flows is not electricity | No technology |

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

The values of each other mode go to the `operating_modes` field of the record of the component in
`extensions.json`. Refer to [The values that Sienna has no field for](#the-values-that-sienna-has-no-field-for).

### Fuel and location

- A `FUEL` whose annotation states the carrier `electricity` gives a bus at its location. Two
  electricity fuels at one location share one bus.
- Each location of an electricity fuel becomes one `ACBus` and one `Area`.
- A technology between two locations has the location `A~B`. That location is not a bus.
- A fuel that is not electricity has no Sienna component. Its bus is `<region>/<fuel>`, because
  the fuel balances in its region, and a `bus` record of `extensions.json` holds it. It also
  sets the fuel cost and the emission rate of a plant that burns it. Refer to
  [The fuels that are not electricity](#the-fuels-that-are-not-electricity) and to
  [The fuel producer rule](#the-fuel-producer-rule).
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
| [An import mode of an `AggregateTransportTechnology`](#an-import-mode--thermalstandard) | `ThermalStandard`, with the fuel `OTHER` and the prime mover `OT` |
| [`TIMESLICE`, `SEASON`, `DAYTYPE`, `DAILYTIMEBRACKET`](#the-calendar) | The hours of each time series, and one `representative_period` record for each day in `extensions.json` |
| [A `fuel_supply` technology](#the-fuels-that-are-not-electricity) | A `generator` record on the bus of its fuel in `extensions.json`. It also sets the fuel cost and part of the emission rate of each plant that burns its fuel. |
| [`EMISSION`](#the-emission-penalty) | No component. Its rate goes to `extensions.json`, and its penalty adds to the variable cost. |
| [A `conversion` or an `export` of electricity](#technologies-with-no-component) | No component. `decisions.md` names each one, and a `conversion` record of `extensions.json` holds it. |
| [A technology that moves or converts a fuel that is not electricity](#the-fuels-that-are-not-electricity) | A `conversion` record of `extensions.json` for each mode |
| [A demand for a fuel that is not electricity](#the-fuels-that-are-not-electricity) | A `load` record of `extensions.json` on the bus of the fuel |
| [An emission limit, a renewable target, a reserve margin](#the-policies-of-the-model) | A `constraint` record in `extensions.json` |
| Each other parameter | Refer to [Not translated](#not-translated). `decisions.md` names each one that states a value that no record holds. |

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
  them. A value that the system cannot hold goes to `extensions.json`, or `decisions.md` records
  it as `NOT_MAPPED`.
- **A missing parameter stops the run.** A `year` that is not a model year, and a unit that a
  conversion needs and that `units:` does not state, each stop the run with a message.
- **A name comes from the member.** A component takes the name of its technology, fuel or
  storage. When two regions hold a member of the same name, the name starts with
  `<region>/`.
- **The time series go into the HDF5 companion.** Each series is a `TimeSeriesAssociation`
  record whose values are in `system_time_series_storage.h5`.
- **A value with no Sienna field goes to `extensions.json`.** For example, the fixed cost and
  the emission rates of a generator. A field takes the name of the PyPSA attribute with the same
  meaning, in the PyPSA unit. Sienna does not read the sidecar. A later tz-oss-interop step can
  read it. Refer to [The values that Sienna has no field for](#the-values-that-sienna-has-no-field-for).
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

A demand for a fuel that is not electricity becomes a `load` record of `extensions.json`, as
[The fuels that are not electricity](#the-fuels-that-are-not-electricity) states. A demand for
an electricity fuel with no location has no bus, and the bus step reports the fuel. The step
leaves out these demands, and `decisions.md` names each one:

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
| `e_sum_min` | MWh | For each year, `TotalTechnologyAnnualActivityLowerLimit` (`total_technology_annual_activity_lower_limit`) in MWh × the electricity output ratio of that year. A limit of 0 is left out. |
| `e_sum_max` | MWh | For each year, `TotalTechnologyAnnualActivityUpperLimit` (`total_technology_annual_activity_upper_limit`) in MWh × the electricity output ratio of that year. A negative limit is left out. |
| `fuel_buses` | MWh/MWh | For each fuel that the plant takes in at the operations mode and that is not electricity, `input_activity_ratio` / the electricity output ratio, keyed by the bus of the fuel, `<region>/<fuel>`. No PyPSA field: PyPSA states it as the `bus0` and the `efficiency` of a `Link`. |
| `own_marginal_cost` | $/MWh | The own cost, plus the penalty of the own emissions of the plant, without a fuel term. Only where `fuel_buses` is stated. |
| `own_emission_rates_t_per_mwh` | t/MWh | For each pollutant, `EmissionActivityRatio` at the operations mode / the electricity output ratio, without the rate of a fuel. Only where `fuel_buses` is stated. |
| Each other field | | Refer to [The values that Sienna has no field for](#the-values-that-sienna-has-no-field-for). |

The Sienna to PyPSA hop reads `fuel_buses`, `own_marginal_cost` and
`own_emission_rates_t_per_mwh`. Where the network holds the bus of each fuel, a `ThermalStandard`
becomes a PyPSA `Link` that draws the fuel from its bus, so the network prices the fuel once.

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
`extensions.json`, as `fom_charge_per_mw_year` in $/MW/yr. The category of the discharging
technology goes to the same record, as `carrier`. A prime mover cannot keep it, because
several categories share one prime mover.

The step does not apply the `capacity_factor` of the discharging technology to the system. The
companion `storage.parquet` beside `extensions.json` holds it for each hour, in the column
`rating_pu`, and the `rating_series` field of the record names the file.

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
Sienna line prices no flow. An `availability_factor` below 1 goes to `p_max_pu`, because the
limits of the line hold it inside one number.

The step does not apply the `capacity_factor` of a transport technology to the system. The
companion `controllable_lines.parquet` holds it for each hour, in the column `p_max_pu`, and the
`p_max_pu_series` field of the record names the file.

### An import mode → `ThermalStandard`

An import mode is a mode of a transport technology, other than the operations mode, that obeys
all of these conditions:

- It puts out electricity at one location only.
- That location is one end of the line.
- It takes in no electricity.

So it brings electricity into the model from outside. Each import mode becomes one
`ThermalStandard` on the bus of that end. The line keeps its forward direction and its flow
back. The generator exists only when the line exists, so the checks of the line apply to it
too.

OSeMOSYS states no plant and no fuel for an import, so the generator takes a fixed type, a
fixed prime mover and a fixed fuel. A carriers row does not apply, because the category of a
transport technology names the line and not the import. `decisions.md` records each fixed
value as `TRANSLATOR_DEFAULT_APPLIED`.

| Sienna field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | `<line>/import/<mode>`. `<line>` is the name of the line. | `derived` |
| `bus` | | The location of the electricity fuel that the mode puts out | `derived` |
| `prime_mover_type` | | `OT` | `default` |
| `fuel_type` | | `OTHER` | `default` |
| `base_power` | MVA | `residual_capacity` of the line in MW × the electricity `output_activity_ratio` of the mode | `derived` |
| `active_power_limits` | MW | `(0, base_power × availability_factor of the line)` | `derived` |
| `operation_cost.variable` | $/MWh | A linear curve: `variable_operation_cost` of the mode in $/MWh / the electricity output ratio of the mode + the emission penalty of each pollutant | `derived` |
| `operation_cost.fixed` | $ | `0.0`. OSeMOSYS states the fixed cost for the technology, and the line record holds it. | `default` |
| `rating` | pu | `1.0` | `default` |

The other fields take the values of [`ThermalStandard`](#thermalstandard). The emission
penalty of a pollutant is the rate of the mode in t/MWh × `emission_penalty` of the region.
Refer to [The emission penalty](#the-emission-penalty).

The generator gets a generator record in `extensions.json`:

| Field | Unit | From |
| --- | --- | --- |
| `carrier`, `category` | | `import` |
| `emission_rates_t_per_mwh` | t/MWh | For each pollutant, `emission_rate` of the mode / the electricity output ratio of the mode. A rate of 0 is left out. |
| `source_technology` | | `<region>/<technology>` of the transport technology |
| `source_mode` | | The import mode |

The line record still holds the values of the import mode in its `operating_modes`.

## Technologies with no component

The system has no component for the two technologies of electricity below. The step records
each one as `COMPONENT_SKIPPED`, with its kind, and one warning for each reason names three:

| Technology | Note |
| --- | --- |
| Kind `export`, and it takes in electricity | It takes in electricity and puts out nothing. The system has no component that takes energy out of the model. A `conversion` record holds it. |
| Kind `conversion`, and each fuel of its flows is electricity | It converts one electricity fuel into another at one location. The two fuels share one bus, so it joins nothing. The dispatch loses its loss, and each demand stays at the value that the model states. A `conversion` record holds it. |

A technology of kind `fuel_supply`, `export` or `conversion`, or of no kind, whose fuels are not
all electricity, has records of its own. Refer to
[The fuels that are not electricity](#the-fuels-that-are-not-electricity). A technology with
no kind and no flow in the year moves no energy, so the step does not report it.

A technology of kind `conversion` whose fuels are all electricity, and a technology of kind
`export` that takes in electricity, each get a `conversion` record in `extensions.json`. The
record states the technology as a PyPSA `Link`:

| Field | Unit | From |
| --- | --- | --- |
| `name` | | The technology |
| `carrier` | | The category of the technology |
| `bus0` | | The location of the electricity fuel that it takes in at the operations mode |
| `bus1` | | The location of the electricity fuel that it puts out. An export has none. |
| `p_nom` | MW | `residual_capacity` in MW × the electricity input ratio |
| `efficiency` | | The electricity output ratio / the electricity input ratio |
| `marginal_cost` | $/MWh | `variable_operation_cost` in $/MWh / the electricity input ratio |
| `p_max_pu` | | `availability_factor`, when it is below 1 |
| `input_fuel`, `output_fuel` | | The electricity fuel that it takes in and the one that it puts out. No PyPSA field. |
| Each other field | | Refer to [The values that Sienna has no field for](#the-values-that-sienna-has-no-field-for). Each capacity rates on the electricity that goes in. |

The dispatch does not apply a conversion record. So the loss of a conversion is not in the
dispatch, and each demand stays at the value that the model states.

### A trade route

A trade route moves a fuel from one region to another: OSeMOSYS states it with `TradeRoute`
(`transport_route`) and the other trade parameters. A trade route of an electricity fuel gets
a `conversion` record too. A route joins regions and not locations, so `bus0` and `bus1` name
the region and the fuel as `<region>/<fuel>`, and not a Sienna bus. No location has to be
chosen. A route gets a record when a trade parameter states a value other than its default for
it, unless `TradeRoute` is 0 in each year that it states, which closes the route.

| Field | Unit | From |
| --- | --- | --- |
| `name` | | `<start region>/<end region>/<fuel>` |
| `bus0`, `bus1` | | `<start region>/<fuel>` and `<end region>/<fuel>` |
| `input_fuel`, `output_fuel` | | The fuel |
| `active` | | `TradeRoute` (`transport_route`) is 1, for each year |
| `p_nom` | MW | `ResidualTradeCapacity` (`residual_transport_capacity`) |
| `efficiency` | | 1 − `TradeLossBetweenRegions` (`line_loss`) |
| `p_max_pu` | | `AvailabilityFactorTrade` (`transport_availability_factor`), when it is not 1 |
| `overnight_cost_per_mw` | $/MW | `CapitalCostTrade` (`transport_capital_cost`) |
| `lifetime_years` | yr | `OperationalLifeTrade` (`transport_lifetime`) |
| `discount_rate` | | `DiscountRateTrade` (`transport_discount_rate`) |
| `max_growth` | MW | `TotalAnnualMaxTradeInvestment` (`total_annual_max_transport_investment`) |
| `e_sum_min`, `e_sum_max` | MWh | `TotalTradeAnnualActivityLowerLimit` and `TotalTradeAnnualActivityUpperLimit`, for each year |
| `capacity_factor_min` | | `TotalAnnualMinCapacityFactorTrade` (`transport_total_annual_min_capacity_factor`) |
| `capacity_to_activity_unit` | MWh/MW | `TradeCapacityToActivityUnit` (`transport_capacity_to_activity_unit`) |

Each value is that of the operations year, except `active`, `e_sum_min` and `e_sum_max`, which
hold for each year. A route of a fuel that is not electricity has no record.

## The fuels that are not electricity

Sienna holds electricity only. Each other fuel, and each technology that supplies, moves or
converts it, gets records of `extensions.json` in PyPSA terms. The Sienna to PyPSA hop builds
a PyPSA component from each record. The group `osemosys_to_sienna_map_fuels` of the step writes
them. Refer to [translation-from-sienna-to-pypsa.md](translation-from-sienna-to-pypsa.md#the-fuels-that-are-not-electricity).

### The bus of a fuel

A fuel that is not electricity balances in its region, so its bus is `<region>/<fuel>`, for
example `R1/DENG`. This is the name of a trade route end too. A fuel of electricity has the bus
of its location. A fuel gets a `bus` record when a technology of this section or a demand uses
it:

| Field | From |
| --- | --- |
| `name` | `<region>/<fuel>` |
| `carrier` | The `carrier` annotation of the fuel, or the name of the fuel where it states none |
| `location` | The `location` annotation of the fuel |

A fuel that only a plant burns gets no bus. The plant then stays a PyPSA `Generator` at its
Sienna price.

### The technologies

The step reads each technology of kind `fuel_supply`, `export` or `conversion`, or of no kind,
whose fuels are not all electricity and that has a flow in the operations year. Each operating
mode with a flow becomes one record. The operations mode, and the one mode of a technology of
one mode, take the name of the technology. Each other mode takes `<name>/mode<mode>`, for
example `DENGFRPI0/mode2`.

| The flows of the mode | Record | PyPSA component |
| --- | --- | --- |
| It takes in nothing and puts out one fuel | `generator` | A `Generator` on the bus of the fuel |
| It takes in and puts out | `conversion` | A `Link` from the bus of its largest input (`bus0`) to the bus of its largest output (`bus1`). A third and a fourth fuel go to `bus2` and `bus3`. |
| It takes in and puts out nothing | `conversion` with no `bus1` | None. The record travels on. |

A pipeline of two modes, one for each direction, thus becomes two one-way links. An import
from outside the model, which takes in nothing in its operations mode, is a generator in that
mode.

The step leaves out a mode, records it as `COMPONENT_SKIPPED` and warns once for each reason:

| Reason | Note |
| --- | --- |
| It uses an electricity fuel with no location | The fuel has no bus. |
| It takes in nothing and puts out more than one fuel | A PyPSA `Generator` has one bus. |
| It takes in and puts out more than four fuels | A link of this translation has four buses at most. |
| It has no residual capacity, and the model builds none at no cost | The fleet of the year holds none of it. |
| Its annual activity upper limit is 0 | It may not run in the year. |

### The values of a mode

Each value is for one MWh of the fuel that rates the component: the fuel that a generator puts
out, or the fuel that goes in at `bus0` of a link. The rating ratio is the
`output_activity_ratio` or the `input_activity_ratio` of that fuel at the mode.

| Field | Unit | From |
| --- | --- | --- |
| `bus`, `bus0`, `bus1`, `bus2`, `bus3` | | The bus of each fuel |
| `carrier` | | The category of the technology, else the carrier of its output fuel |
| `efficiency` | | The ratio of the output at `bus1` / the rating ratio |
| `efficiency2`, `efficiency3` | | The ratio of the fuel / the rating ratio, negative for a fuel that goes in |
| `p_nom` | MW | `ResidualCapacity` × `CapacityToActivityUnit`, in MWh, / 8760 h × the rating ratio |
| `p_nom_extendable` | | True where `CapitalCost` is 0, `TotalAnnualMaxCapacityInvestment` is not 0, and `TotalAnnualMaxCapacity` leaves room |
| `p_nom_max` | MW | `TotalAnnualMaxCapacity`, converted as `p_nom` is, for an extendable mode |
| `marginal_cost` | $/MWh | (`VariableCost` + Σ `EmissionActivityRatio` × `EmissionsPenalty`), in $/MWh of activity, / the rating ratio |
| `p_max_pu` | | `AvailabilityFactor`, when it is not 1 |
| `emission_rates_t_per_mwh` | t/MWh | `EmissionActivityRatio` of the mode, for each pollutant, / the rating ratio |
| `e_sum_min`, `e_sum_max` | MWh | The annual activity limit of the mode, and of a technology of one mode, in MWh × the rating ratio, keyed by the operations year |
| `input_fuel`, `output_fuel` | | The largest fuel that a link takes in and puts out |

`CapacityToActivityUnit` converts the capacity, because the capacity of a fuel technology is
often in units of energy a year rather than in the capacity unit of the mappings file. A model
that declares no `CapacityToActivityUnit` converts with its capacity unit. Each mode can run at
the whole capacity of the technology, where OSeMOSYS shares the capacity among the modes. The
annual limit of a technology of two modes holds their sum, so no mode states it, and the report
of the parameters that no step applies names it. `decisions.md` records an event for each value.

### A demand for a fuel that is not electricity

`SpecifiedAnnualDemand` and `AccumulatedAnnualDemand` of a fuel that is not electricity become
a `load` record, with the name and the MW of each hour that a `PowerLoad` would take:

| Field | Unit | From |
| --- | --- | --- |
| `name` | | The fuel, or `<fuel>/accumulated` |
| `bus` | | `<region>/<fuel>` |
| `carrier` | | The carrier of the fuel, or the name of the fuel |
| `p_set` | MW | The MW of each hour, where each hour is the same |
| `p_set_series` | | `loads.parquet`, where the hours differ. The companion holds the MW of each hour in the column `p_set`. |

## The values that Sienna has no field for

The generator, `storage`, `controllable_line` and `conversion` records hold the values below.
Each field takes the name of the PyPSA attribute with the same meaning, in the PyPSA unit. A
field with no PyPSA attribute takes a plain name. A value is the value of the operations year,
except the annual bounds and the bounds of a mode, which hold for each year. A capacity rates
on the electricity of the component: the output of a generator and of a storage, and the input
of a line and of a conversion. So a capacity multiplies by that electricity ratio, and a cost
for each unit of capacity divides by it. A row that binds nothing, for example a limit of -1,
gives no field.

| Field | Unit | From | PyPSA attribute |
| --- | --- | --- | --- |
| `overnight_cost_per_mw` | $/MW | `CapitalCost` (`capital_cost`) | `overnight_cost` |
| `lifetime_years` | yr | `OperationalLife` (`lifetime`) | `lifetime` |
| `discount_rate` | | `DiscountRateIdv` (`technology_discount_rate`). If the model states no row, the default that the model declares for it. If it has no default, `DiscountRate` (`discount_rate`) of the region. | `discount_rate` |
| `unit_size_mw` | MW | `CapacityOfOneTechnologyUnit` (`unit_size`), above 0 | `p_nom_mod` |
| `p_nom_max` | MW | `TotalAnnualMaxCapacity` (`capacity_limits_max`), not -1 | `p_nom_max` |
| `p_nom_min` | MW | `TotalAnnualMinCapacity` (`capacity_limits_min`), above 0 | `p_nom_min` |
| `max_growth` | MW | `TotalAnnualMaxCapacityInvestment` (`total_annual_max_capacity_investment`), not -1 | `Carrier.max_growth` |
| `min_growth` | MW | `TotalAnnualMinCapacityInvestment` (`total_annual_min_capacity_investment`), above 0 | none |
| `max_growth_rate` | | `CapacityAdditionalMaxGrowthRate` (`capacity_additional_max_growth_rate`): new capacity per unit of the total capacity of the year before | none: `Carrier.max_relative_growth` weighs the new capacity of the period before |
| `min_growth_rate` | | `CapacityAdditionalMinGrowthRate` (`capacity_additional_min_growth_rate`) | none |
| `max_growth_floor` | MW | `CapacityAdditionalMaxFloor` (`capacity_additional_max_floor`) | none |
| `e_sum_min_horizon` | MWh | `TotalTechnologyModelPeriodActivityLowerLimit` (`total_technology_model_period_activity_lower_limit`), above 0, × the electricity ratio of the operations year | `e_sum_min` |
| `e_sum_max_horizon` | MWh | `TotalTechnologyModelPeriodActivityUpperLimit` (`total_technology_model_period_activity_upper_limit`), 0 or above, × that ratio | `e_sum_max` |
| `capacity_factor_min` | | `TotalAnnualMinCapacityFactor` (`total_annual_min_capacity_factor`) | none |
| `production_share_min`, `production_share_max` | | `TechnologyMinProductionTarget` and `TechnologyMaxProductionTarget`, for each fuel | none |
| `capacity_to_activity_unit` | MWh/MW | `CapacityToActivityUnit` (`capacity_to_activity_unit`) in MWh for each MW. It is 8760 when the model agrees with `units:`. | none |
| `e_sum_min`, `e_sum_max` | MWh | `TotalTechnologyAnnualActivityLowerLimit` and `TotalTechnologyAnnualActivityUpperLimit` of each year × the electricity ratio of that year | `e_sum_min`, `e_sum_max`, keyed by the investment period |
| `fom_charge_per_mw_year` | $/MW/yr | `FixedCost` (`fixed_cost`), for a line and a conversion. A generator and a storage state it too, as their sections say. | `fom_cost` |
| `operating_modes` | | One entry for each mode that the component does not run, and for each mode with a bound. Refer to the table below. | none |

A storage takes these values from the technology that discharges it, except `lifetime_years`
and `discount_rate`. It also states:

| Field | Unit | From | PyPSA attribute |
| --- | --- | --- | --- |
| `energy_overnight_cost` | $/MWh | `CapitalCostStorage` (`energy_capital_cost`) | `Store.overnight_cost` |
| `lifetime_years` | yr | `OperationalLifeStorage` (`storage_lifetime`) | `lifetime` |
| `discount_rate` | | `DiscountRateStorage` (`storage_discount_rate`). If the model states no row, the default of `storage_discount_rate` (0.05 when the model declares none). | `discount_rate` |
| `duration_max_hours` | h | `StorageMaxHours` (`duration_limits_max`) | none |
| `cyclic_state_of_charge_per_period` | | `StorageBalanceYear` (`storage_balance_year`) is 1 | `cyclic_state_of_charge_per_period` |
| `cyclic_state_of_charge_per_season` | | `StorageBalanceSeason` (`storage_balance_season`) is 1 | none |
| `cyclic_state_of_charge_per_day` | | `StorageBalanceDay` (`storage_balance_day`) is 1 | none |
| `charge_fom_cost` | $/MW/yr | `FixedCost` of the technology that charges the storage, where it does not also discharge it, / its electricity input ratio | none |

The record keeps no other value of a separate charging technology. `decisions.md` names its
`capacity_factor` and each other value that no step applies.

A generator and a line run the operations mode. A storage runs its charge mode and its
discharge mode. Each entry of `operating_modes` states one mode, for each MWh of its activity:

| Field | Unit | From |
| --- | --- | --- |
| `mode` | | The member of `MODE_OF_OPERATION` |
| `variable_cost` | $/MWh | `variable_operation_cost` of the mode, in the operations year |
| `input_ratios`, `output_ratios` | | `input_activity_ratio` and `output_activity_ratio` of the mode, for each fuel |
| `emission_rates` | t/MWh | `emission_rate` of the mode, for each pollutant |
| `activity_max`, `activity_min` | MWh | `TechnologyActivityByModeUpperLimit` and `TechnologyActivityByModeLowerLimit`, for each year, above 0 |
| `activity_decrease_max` | | `TechnologyActivityDecreaseByModeLimit`, for each year, above 0 |

The cost and the ratios are for a mode that the component does not run. `emission_rates` are
for a mode that a generator does not run, and for each mode of a storage, a line and a
conversion, which have no other field for them. The bounds are for each mode.
`decisions.md` records each value that goes to a record.

## The policies of the model

An operations system has no emission limit, no renewable target and no reserve margin. So
each one goes to a `constraint` record of `extensions.json`, as a PyPSA `GlobalConstraint`
states it. The step reads every year in scope, so the record holds one limit for each year
that states one. The investments pipelines write the same records.

| Policy | `name` | `type` | `sense` | `limits` | `members` |
| --- | --- | --- | --- | --- | --- |
| `AnnualEmissionLimit` (`annual_emission_limit`) and `ModelPeriodEmissionLimit` (`model_period_emission_limit`) of a pollutant | The pollutant | `primary_energy`, with `carrier_attribute` the pollutant | `<=` | For each year: the limit − `AnnualExogenousEmission`, in t. Over the model period (`period: horizon`): the limit − `ModelPeriodExogenousEmission`, in t. | Each technology that emits the pollutant |
| `AnnualEmissionLimitRegionGroup` of a pollutant | `<region group>/<pollutant>` | `primary_energy` | `<=` | For each year: the limit − `AnnualExogenousEmissionRegionGroup`, in t | The regions of the group in `RegionGroupTagRegion` |
| `REMinProductionTarget` (`generation_fraction_requirement`) above 0 | `<region>/renewable_share` | `renewable_share` | `>=` | For each year, the share | The technologies of `RETagTechnology` and the fuels of `RETagFuel`, each with its tag as `coefficient` |
| `RegionGroupREMinProductionTarget` above 0 | `<region group>/renewable_share` | `renewable_share` | `>=` | For each year, the share | The regions of the group |
| `ReserveMargin` (`reserve_margin`), for a region with a tag | `<region>/reserve_margin` | `reserve_margin` | `>=` | For each year, the margin, or its default | The technologies of `ReserveMarginTagTechnology` and the fuels of `ReserveMarginTagFuel`, each with its tag as `coefficient` |

A limit of a year is a `limits` entry with `period: year` and `investment_period`, the year. A
tag that changes from year to year keeps the value of the earliest year that states one.

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
| `days_in_day_type` | `DaysInDayType` (`days_in_day_type`) of the day, or its default |

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

The line runs the operations mode and the flow back. An import mode becomes a generator. Refer
to [An import mode → `ThermalStandard`](#an-import-mode--thermalstandard). The
`operating_modes` of the line record hold each other mode, and the ratios of the flow back. One
warning names three lines that state values at a mode that is neither the flow back nor an
import. A line states one loss, so the loss of the flow back is in the ratios of its
`operating_modes` entry only.

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
operations year. A row that no step applies and that no record of `extensions.json` holds gets
one `NOT_MAPPED` event for each member that it states values for, and one warning that names
three. A row at the default of the parameter states nothing, so it does not count. For example:

```
osemosys-to-sienna: total_technology_annual_activity_upper_limit states 39 row(s) for 2021 that no step of the pipeline applies or keeps, for 39 technology(ies): ...
```

A component notes each row of its technology that it applies or that its record keeps: the
residual capacity, the availability, the costs and the emission rates among them. The report
counts only those rows as applied. So a row of a technology that has no component and no record,
for example the residual capacity of a supply technology with no carriers row, is reported. So
are the capacity factor of a technology that charges a storage that another technology
discharges, and the capital cost, the fixed cost and the life of a technology of a fuel that is
not electricity, which its record does not hold.

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
| Fuels that are not electricity, and their technologies | No Sienna component. The `bus`, `generator`, `conversion` and `load` records hold them as PyPSA components, and the Sienna to PyPSA hop builds them. The Sienna dispatch still prices a fuel at its cheapest producer. |
| A storage of a fuel that is not electricity | Not translated. The storage step reports it, as its technologies put out no electricity. |
| A trade route of a fuel that is not electricity | Not translated. The report of the parameters that no step applies names it. |
| The capital cost, the fixed cost and the life of a technology of a fuel that is not electricity | No record holds them. The report of the parameters that no step applies names them. |
| A `conversion` between two electricity fuels at one location | Its `conversion` record holds it. The dispatch does not apply its loss, and the demand stays at the value that the model states. |
| The capacity that a plan builds, and the years other than the operations year | The system holds the residual capacity of one year. A record holds the values of that year, except a bound of each year and a policy. |
| `TotalTechnologyAnnualActivityLowerLimit`, `TotalTechnologyAnnualActivityUpperLimit` | The generator, `storage`, `controllable_line` and `conversion` records hold them, as `e_sum_min` and `e_sum_max`. No step applies them. An upper limit of 0 in the year keeps a `fuel_supply` technology from being a fuel producer. |
| `TotalTechnologyModelPeriodActivityLowerLimit` / `UpperLimit`, `TechnologyActivityByModeLowerLimit` / `UpperLimit`, `TechnologyActivityDecreaseByModeLimit` | The records hold them. No step applies them. |
| `AnnualEmissionLimit`, `ModelPeriodEmissionLimit` and the region group limits | The `constraint` records hold them. No step applies them to the system. |
| `ReserveMargin`, `ReserveMarginTagFuel`, `ReserveMarginTagTechnology` | The `constraint` records hold them. No step applies them. |
| `REMinProductionTarget`, `RETagFuel`, `RETagTechnology` | The `constraint` records hold them. No step applies them. |
| `StorageBalanceDay`, `StorageBalanceSeason`, `StorageBalanceYear`, `StorageMaxHours` | The `storage` records hold them. No step applies them to the system. |
| `CapacityToActivityUnit` | The records hold it. The records of the fuels that are not electricity convert their capacity with it. No other step reads it. Refer to [Assumptions](#assumptions-worth-checking-against-your-model). |
| The values of another operating mode | The `operating_modes` of the records hold them. Refer to [Technology](#technology). |
| The `capacity_factor` of a storage or a transport technology | The companion parquet holds it. The system does not apply it. |
| `DepreciationMethod` | Not translated. No record holds a region. |
| Unit commitment data | OSeMOSYS states none. |
| The trade parameters (`TradeRoute`, `ResidualTradeCapacity` and the other `*Trade*` parameters) | A `conversion` record holds a route of an electricity fuel. Refer to [A trade route](#a-trade-route). No step applies them, and the system has no line for a route. A connection between two locations must be an `AggregateTransportTechnology`. |
| The investment parameters (`CapitalCost`, `OperationalLife` and the others) | The records hold the values of the operations year. The portfolio reads every year. Refer to [translation-from-osemosys-to-sienna-investments.md](translation-from-osemosys-to-sienna-investments.md). |
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
| The cheapest `fuel_supply` technology of a fuel | The price that a plant pays for that fuel in the Sienna system, with no limit on what that producer makes |
| A fuel technology with no residual capacity and no capital cost | Capacity that the model builds at no cost, so its PyPSA component is extendable |
| A category | One Sienna type, one prime mover and, for a thermal type, one fuel |
