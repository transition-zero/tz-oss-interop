# Translation from OSeMOSYS to a Sienna Investments Portfolio

This document tells you what each part of your OSeMOSYS expansion plan becomes in the Sienna
Investments Portfolio. It gives the source of each field.

> **Scope:** the translator accepts the electricity part of a model. It keeps every year in
> scope: each value that changes by year goes to a field that has a year, or to
> `extensions.json`. It writes a cap on a pollutant only when the pollutant covers the whole
> model. Refer to [Not translated](#not-translated) and to
> [the gap analysis](osemosys-to-sienna-gap-analysis.md), which names each thing that the
> translation and the expansion solve lose.

One run of `osemosys-csv-to-sienna-investments`, or of `tz-osemosys-to-sienna-investments`,
writes **two documents**:

- `system.json` is the Sienna system: the fleet at the start of the plan.
  [translation-from-osemosys-to-sienna.md](translation-from-osemosys-to-sienna.md) describes it.
- `portfolio.json` is the Sienna Investments Portfolio (the portfolio in this document): the
  technologies that a plan may build, the demand that they must meet, and the caps that they
  run under. Its HDF5 companion, `portfolio_time_series_storage.h5`, holds its time series.

The portfolio names the system in its `base_system_file`, so the two are read together. This
document calls that system **the base system**, as the field does.

The pipeline runs the steps of the operations pipeline, then
`osemosys_to_sienna_investments_map_technologies`. That step reads the canonical stage again,
over every year in scope, and reads the base system that the operations step wrote. The
operations step takes `year: earliest` in both investments manifests. So the base system holds
the fleet of the earliest year in scope.

This document uses these words:

- **A candidate** is a technology that a plan may build. The rule is in
  [Which technology is a candidate](#which-technology-is-a-candidate).
- **The first year** is the earliest year in scope. The base system holds its fleet.
- **The cost year** is `units: currency_year` of your mappings file, or the first year when the
  file states none.
- **The priced year** of a candidate is the earliest year in scope in which a plan can build it
  and the model states a capital cost above 0.

---

## The structural decisions

[translation-from-osemosys-to-sienna.md](translation-from-osemosys-to-sienna.md#the-structural-decisions)
answers all six. This section adds what each one means for the portfolio.

### Operations year

The base system holds the fleet of the first year. The portfolio holds every year in scope.

### Technology

| Technology | In the base system | In the portfolio |
| --- | --- | --- |
| Residual capacity in the first year, and not a candidate | A component | None. It is in no technology. |
| A candidate with no residual capacity in the first year | None | A technology |
| A candidate with residual capacity in the first year | A component | A technology, whose `ExistingDevices` names the component |

A candidate uses the operations mode, as the base system does. A storage uses the charge mode
and the discharge mode of its links.

### Fuel and location

A technology sits in the region of its location: the `Area` of that location in the base
system. A transport candidate runs between two areas.

### Timeslice

The portfolio gives each year its own representative days. A series of a year covers the days
of that year from 1 January. The `representative_period` records of `extensions.json` hold the
days of the first year only. Refer to [Time series](#time-series).

### The years of the plan

SiennaSchemas has no field for an investment period. PowerSystemsInvestments.jl takes the
periods as arguments of the solve. So the portfolio states each value that changes by year in
a field that has a year:

- `SupplyTechnology.capacity_limits` uses the form keyed by year, for example
  `{"2030.0": {"min": 0.0, "max": 1000.0}}`.
- A pollutant cap is one `CarbonCaps` for each year that states a limit, with `target_year`.
- The demand of each year is a time series of the portfolio with the feature `year`.

A value with no year field goes to a `technology` record of `extensions.json`, keyed by year.
The capital cost and the fixed cost by year are examples.

### Size

The scope step takes a subset by location and by year. The years in scope are the years of the
plan. Refer to [Size](translation-from-osemosys-to-sienna.md#size).

---

## What becomes what

| OSeMOSYS | Sienna |
| --- | --- |
| [A `SupplyTechnology` that a plan may build](#supplytechnology-candidate--supplytechnology) | `SupplyTechnology` |
| [A `STORAGE` whose discharging technology a plan may build](#storage-candidate--storagetechnology) | `StorageTechnology` |
| [An `AggregateTransportTechnology` that a plan may build](#transport-candidate--aggregatetransporttechnology) | `AggregateTransportTechnology` |
| [Each load of the base system](#demand--demandrequirement) | `DemandRequirement`, with a time series for each year |
| [`AnnualEmissionLimit` of a pollutant that covers the whole model](#emission-limits--carboncaps-or-a-constraint-record) | One `CarbonCaps` for each year that states a limit |
| [`AnnualEmissionLimit` of any other pollutant](#emission-limits--carboncaps-or-a-constraint-record) | A `constraint` record in `extensions.json` |
| [A plant of the base system with the name of a candidate](#a-plant-that-already-runs--existingdevices-and-retirementpotential) | `ExistingDevices` and `RetirementPotential` on the candidate |
| Each location of the base system | A `TopologyMapping` that names the bus of the area |
| [`DiscountRate` and `units: currency_year`](#the-financial-data-of-the-portfolio) | `PortfolioFinancialData` |
| Everything else | A component of the base system, or not translated |

## Reading the tables

The **From** column gives the OSeMOSYS default name and then the canonical name in brackets.

| Mapping | Meaning |
| --- | --- |
| `direct` | The translator uses your OSeMOSYS value without a change. |
| `derived` | The translator calculates the value from your values, with the formula that the table gives. |
| `default` | OSeMOSYS has no such data. The translator supplies this value. |
| `dropped` | The Sienna investments schema has no equivalent. The value does not go into the portfolio. |
| `mapped by you` | A carriers row of your mappings file gives the value. |
| `by year` | One value for each year in scope. |

## Across all components

- **A candidate becomes one technology, named after the component of the base system.** The
  name is the technology, with `<region>/` in front when two regions hold it. A storage
  candidate takes the name of its storage.
- **A candidate whose category has no carriers row is left out.** The run completes, and
  `decisions.md` names each one.
- **Capacity is in MW of electricity.** A supply candidate multiplies the capacity of the model
  by its electricity output ratio at the operations mode, as the base system rates a generator.
  A transport candidate multiplies it by its electricity input ratio, which is the electricity
  that it sends.
- **Each cost is for one MW or one MWh of electricity.** A cost per capacity of the model is
  divided by the same ratio.
- **The electricity ratios come from the first year.** A ratio that changes in a later year does
  not change the portfolio.

### Which technology is a candidate

A technology is a candidate when one year in scope meets both conditions:

- A plan can build it in that year. `TotalAnnualMaxCapacityInvestment`
  (`total_annual_max_capacity_investment`) is not 0. `TotalAnnualMaxCapacity`
  (`capacity_limits_max`) is -1 or above `ResidualCapacity` (`residual_capacity`).
- The model states a price above 0 in that year. For a supply or a transport technology, that
  is `CapitalCost` (`capital_cost`). For a storage, it is the `capital_cost` of its discharging
  technology, or `CapitalCostStorage` (`energy_capital_cost`).

A technology that fails the rule is not a candidate, and the report says nothing of it. Each
year reads the stated value or the default of the parameter.

These checks then leave a candidate out, and `decisions.md` names each one:

| Candidate | Check |
| --- | --- |
| Supply | Its category has no carriers row, or the row names a type that is not a generator. |
| Supply | Its location is not a bus, or it puts out no electricity at the operations mode. |
| Storage | It does not link one charging technology and one discharging technology. |
| Storage | The category of the discharging technology has no carriers row, or the row is not `EnergyReservoirStorage`. |
| Storage | The location of the discharging technology is not a bus, or the links take in or put out no electricity. |
| Transport | It does not take in electricity at one location and put it out at another, at the operations mode. |
| Transport | An end is not an `Area` of the base system. |

---

## `SupplyTechnology` candidate → `SupplyTechnology`

| Sienna field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | The name of the generator in the base system | `derived` |
| `power_systems_type` | | The type that the carriers row of the category names | `mapped by you` |
| `prime_mover_type` | | The carriers row of the category | `mapped by you` |
| `fuel` | | The one `ThermalFuels` value of the carriers row, or none | `mapped by you` |
| `region` | | The `Area` of the location of the technology | `derived` |
| `capacity_limits` | MW | For each year, `TotalAnnualMinCapacity` (`capacity_limits_min`) and `TotalAnnualMaxCapacity` (`capacity_limits_max`) in MW × the electricity output ratio. A year with no upper limit states its lower limit only. A year with neither is left out. | `by year` |
| `capital_costs.capital_cost` | $/MW | `CapitalCost` (`capital_cost`) of the priced year in $/MW / the electricity output ratio, as the slope of a linear curve | `derived` |
| `operation_costs.fixed` | $/MW/yr | `FixedCost` (`fixed_cost`) of the first year / the electricity output ratio | `derived` |
| `operation_costs.variable_operation_cost` | $/MWh | The variable cost of the first year, with the fuel cost and the emission penalty, as the base system derives it | `derived` |
| `operation_costs.cost_type` | | `THERMAL`, `HYDRO_GEN` or `RENEWABLE`, from `power_systems_type` | `derived` |
| `unit_size` | MW | `CapacityOfOneTechnologyUnit` (`unit_size`) of the first year in MW × the electricity output ratio, when it is above 0 | `derived` |
| `lifetime` | yr | `OperationalLife` (`lifetime`) | `direct` |
| `financial_data.capital_recovery_period` | yr | `OperationalLife` (`lifetime`) | `direct` |
| `financial_data.return_on_equity` | | `DiscountRateIdv` (`technology_discount_rate`), else the `DiscountRate` (`discount_rate`) of the region | `derived` |
| `financial_data.debt_fraction`, `debt_rate`, `tax_rate` | | `0` | `default` |
| `financial_data.technology_base_year` | | The cost year | `default` |
| `available` | | `true` | `default` |
| `outage_factor`, `min_generation_fraction`, `ramp_limits`, `time_limits`, `start_fuel_mmbtu_per_mw` | | OSeMOSYS states none of them. | `dropped` |
| `cofire_start_limits`, `cofire_level_limits` | | Not translated. | `dropped` |
| `requirements` | | A `CarbonCaps` holds the whole portfolio, so no technology names it. | `dropped` |

The operations cost of the first year is the variable cost of the plant in the base system:
its own `variable_operation_cost`, the fuel term of each fuel, and the emission penalty of each
pollutant. Refer to
[The variable cost](translation-from-osemosys-to-sienna.md#the-variable-cost).

## `STORAGE` candidate → `StorageTechnology`

A storage is a candidate when its discharging technology is one. The discharging technology
gives the discharge power and prices it. A charging technology of its own gives the charge power
and its price. A technology that charges and discharges the storage has one capacity, so the
charge side then states no bound and no price of its own.

| Sienna field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | The storage | `direct` |
| `power_systems_type` | | The carriers row of the category of the discharging technology | `mapped by you` |
| `prime_mover_type` | | The same row | `mapped by you` |
| `storage_tech` | | `OTHER_MECH`, because OSeMOSYS states no storage technology | `default` |
| `region` | | The `Area` of the location of the discharging technology | `derived` |
| `capacity_limits_discharge` | MW | The capacity limits of the discharging technology, in each year | `by year` |
| `capacity_limits_charge` | MW | The capacity limits of a charging technology of its own, in each year | `by year` |
| `capital_costs.discharge_capital_cost` | $/MW | `capital_cost` of the discharging technology in the priced year / its electricity output ratio | `derived` |
| `capital_costs.energy_capital_cost` | $/MWh | `CapitalCostStorage` (`energy_capital_cost`) of the priced year | `derived` |
| `capital_costs.charge_capital_cost` | $/MW | `capital_cost` of a charging technology of its own, else a zero curve | `derived` |
| `operation_costs.fixed` | $/MW/yr | `fixed_cost` of the discharging technology in the first year | `derived` |
| `operation_costs.cost_type` | | `STORAGE` | `default` |
| `unit_size_discharge` | MW | `unit_size` of the discharging technology in MW of electricity output | `derived` |
| `duration_limits.max` | min | `StorageMaxHours` (`duration_limits_max`) × 60, when the model states it | `derived` |
| `efficiency.in` | | `technology_to_storage` / the electricity input ratio of the charging technology | `derived` |
| `efficiency.out` | | The electricity output ratio of the discharging technology / `technology_from_storage` | `derived` |
| `lifetime` | yr | `OperationalLifeStorage` (`storage_lifetime`) when it is above 0, else the `lifetime` of the discharging technology | `derived` |
| `financial_data.return_on_equity` | | `DiscountRateStorage` (`storage_discount_rate`) when the model states it, else the rate of the discharging technology | `derived` |
| `financial_data` (the other fields) | | As for a [`SupplyTechnology`](#supplytechnology-candidate--supplytechnology) | |
| `capacity_limits_energy` | | The canonical stage has no limit on the energy capacity of a storage. | `dropped` |
| `unit_size_charge`, `unit_size_energy` | | OSeMOSYS sizes one unit by its capacity only. | `dropped` |
| `losses`, `min_discharge_fraction` | | OSeMOSYS states neither. | `dropped` |

## Transport candidate → `AggregateTransportTechnology`

| Sienna field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | The technology | `direct` |
| `power_systems_type` | | `TwoTerminalGenericHVDCLine`, the type that the base system writes | `default` |
| `start_region` | | The `Area` of the location where it takes in electricity at the operations mode | `derived` |
| `end_region` | | The `Area` of the location where it puts electricity out | `derived` |
| `capacity_limits` | MW | `capacity_limits_min` and `capacity_limits_max` of the first year in MW × the electricity input ratio. The type holds one bound for every year. | `derived` |
| `capital_costs.capital_cost` | $/MW | `capital_cost` of the priced year in $/MW / the electricity input ratio | `derived` |
| `line_loss` | | `1 − the electricity output ratio / the electricity input ratio`, at the operations mode | `derived` |
| `unit_size` | MW | `unit_size` of the first year in MW of electricity sent | `derived` |
| `financial_data` | | As for a [`SupplyTechnology`](#supplytechnology-candidate--supplytechnology) | `derived` |
| `variable_operation_cost` | | The type has no operation cost. | `dropped` |

`extensions.json` holds the capacity limits of each year.

## Demand → `DemandRequirement`

The step writes one `DemandRequirement` for each load of the base system.

| Sienna field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | The name of the load in the base system | `direct` |
| `power_systems_type` | | `PowerLoad`, the type of the load in the base system | `derived` |
| `region` | | The `Area` of the bus of the load | `derived` |
| `available` | | `true` | `default` |
| The demand of each year | MW | A time series for each year. Refer to [Time series](#time-series). | `by year` |
| `new_demand_mw`, `new_construction_year`, `growth_rate`, `conformity` | | The demand of each year is a time series, so no growth field applies. | `dropped` |
| `value_of_lost_load`, `unserved_demand_curve` | | OSeMOSYS states no value of lost load. | `dropped` |

The first year reads the series that the operations step wrote. Each later year computes its
demand with the same formula, over its own days. The step reports a load of the base system
that has no demand in a year, and a demand of a later year that the base system holds no load
for.

## Emission limits → `CarbonCaps`, or a constraint record

`CarbonCaps` names no region and no pollutant. So one cap limits the emissions of the whole
portfolio. A pollutant **covers the whole model** when each technology that emits any pollutant
emits it. The step reads every year in scope and every mode. The step counts the technologies
of every region, so in a model of two regions a limit of one region covers the whole model only
if each emitting technology of the model is in that region.

A pollutant that covers the whole model gets one `CarbonCaps` for each year whose
`AnnualEmissionLimit` (`annual_emission_limit`) is not -1:

| Sienna field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | `<pollutant>/<year>` | `derived` |
| `target_year` | | The year | `direct` |
| `max_mtons` | Mt | (`annual_emission_limit` − `AnnualExogenousEmission` (`annual_exogenous_emission`)) in t / 1,000,000 | `derived` |
| `available` | | `true` | `default` |
| `max_tons_mwh` | | OSeMOSYS has no limit on a rate. | `dropped` |

OSeMOSYS adds `annual_exogenous_emission` to the emissions that a limit holds. So the cap is the
limit less that emission.

The limits of each other pollutant go to a `constraint` record of `extensions.json`:

| Field | Value |
| --- | --- |
| `name` | The pollutant |
| `sense` | `<=` |
| `limits` | One entry for each year with a limit: `period` `year`, `value` in t (the limit less the exogenous emission), `unit` `t`, `year`. One entry with `period` `horizon` from `ModelPeriodEmissionLimit` (`model_period_emission_limit`) − `ModelPeriodExogenousEmission` (`model_period_exogenous_emission`). |
| `members` | Each technology that emits the pollutant |

`decisions.md` records each such pollutant as `COMPONENT_SKIPPED`, and one warning names three.
A pollutant that covers the whole model and states a `model_period_emission_limit` records that
limit as `NOT_MAPPED`, because `CarbonCaps` holds one year.

## A plant that already runs → `ExistingDevices` and `RetirementPotential`

OSeMOSYS gives each technology its own residual capacity. So the one device of a candidate is
the component of the base system with the same name: a generator, an `EnergyReservoirStorage`
or a `TwoTerminalGenericHVDCLine`.

| Sienna field | From | Mapping |
| --- | --- | --- |
| `ExistingDevices.existing_devices` | The component of the base system with the name of the candidate | `derived` |
| `RetirementPotential.eligible_generators` | The same component | `derived` |
| `RetirementPotential.planned_retirement_year` | The earliest later year in which the `residual_capacity` of the technology is 0 or less | `derived` |
| `RetirementPotential.build_year` | OSeMOSYS states no build year. | `dropped` |
| `RetirementPotential.retirement_cost` | A zero curve. OSeMOSYS prices no retirement. | `default` |

A candidate with no such component gets neither attribute. A plant of the base system that is
not a candidate is in no technology of the portfolio.

## Time series

The portfolio holds its own time series. Each one is a `SingleTimeSeries` row of
`time_series_associations`, with its values in `portfolio_time_series_storage.h5`:

| Field | Value |
| --- | --- |
| `name` | `max_active_power` |
| `features` | `{"year": "<year>"}` |
| `resolution` | `PT1H` |
| `initial_timestamp` | 00:00 on 1 January of the year |
| Values | MW for a `DemandRequirement`. The per-unit availability for a `SupplyTechnology`. |

A `DemandRequirement` gets one series for each year. A `SupplyTechnology` gets one series for
each year when its availability is not 1 in some hour of some year. The availability is
`capacity_factor` × `availability_factor`, as the base system has it.

Each year builds its own representative days from the calendar of that year.

## The financial data of the portfolio

| Sienna field | From | Mapping |
| --- | --- | --- |
| `PortfolioFinancialData.base_year` | The cost year | `default` |
| `PortfolioFinancialData.discount_rate` | `DiscountRate` (`discount_rate`) of the first region of the `region` set | `derived` |
| `PortfolioFinancialData.inflation_rate`, `interest_rate` | `0.0`. OSeMOSYS states neither. | `default` |

## The `technology` records of `extensions.json`

Each candidate gets one `technology` record. Each field is keyed by the year, as text:

| Field | Unit | From |
| --- | --- | --- |
| `capital_cost_per_mw_by_year` | $/MW | `capital_cost` |
| `fixed_cost_per_mw_year_by_year` | $/MW/yr | `fixed_cost` |
| `residual_capacity_mw_by_year` | MW | `residual_capacity` |
| `total_annual_max_capacity_investment_mw_by_year` | MW | `total_annual_max_capacity_investment`, for each year with a limit |
| `variable_cost_per_mwh_by_year` | $/MWh | The variable cost with the fuel cost and the emission penalty (supply only) |
| `energy_capital_cost_per_mwh_by_year` | $/MWh | `energy_capital_cost` (storage only) |
| `capacity_limits_min_mw_by_year`, `capacity_limits_max_mw_by_year` | MW | The capacity limits (transport only) |

A year with no limit is not in a `_by_year` field of a limit. So a year that is not in
`capacity_limits_max_mw_by_year` or `total_annual_max_capacity_investment_mw_by_year` has no
limit.

---

## Special business rules

### A candidate is priced in its priced year

The earliest year in scope can state a capital cost of 0 for a technology that the model opens
later. A cost of 0 would make the technology free. So `capital_costs` holds the cost of the
priced year. The source field in `decisions.md` names that year. `extensions.json` holds the
cost of each year.

The fixed cost and the variable cost come from the first year.

### The rate is all-equity financing

`TechnologyFinancialData` requires six fields and has no field for one discount rate. So the
portfolio states `debt_fraction: 0`, `debt_rate: 0`, `tax_rate: 0`, and a `return_on_equity`
equal to the discount rate. With no debt, the cost of capital equals the return on equity. The
rate is `technology_discount_rate` when the model states it, else the `discount_rate` of the
region, as OSeMOSYS applies them.

### The capital recovery period is the operational life

OSeMOSYS recovers a capital cost over the operational life of the technology. So
`capital_recovery_period` and `lifetime` both take `OperationalLife` (`lifetime`).

### Units

The unit rules of the base system apply here too. Refer to
[Units](translation-from-osemosys-to-sienna.md#units). Two more apply:

| Value | Becomes |
| --- | --- |
| A limit on emissions, in `units: emissions` | t, and Mt in `max_mtons` |
| `StorageMaxHours` | Minutes in `duration_limits` |

---

## Solving the portfolio

The leg `sienna-to-power-systems-investments` turns the portfolio into the shape that
PowerSystemsInvestments.jl reads. The `solve` command with the model type
`sienna-investments` runs it.
[Running a capacity expansion](../developer_documentation/capacity-expansion.md) tells you what
the leg reads and what the solve loses.

## Not translated

| OSeMOSYS | Effect |
| --- | --- |
| A pollutant that does not cover the whole model | Its limits go to a `constraint` record of `extensions.json`. Nothing applies them. |
| `ModelPeriodEmissionLimit` of a pollutant that covers the whole model | `NOT_MAPPED`. A `CarbonCaps` holds one year. |
| `AnnualEmissionLimitRegionGroup` and the other region group parameters | No step applies them. |
| `REMinProductionTarget`, `RETagFuel`, `RETagTechnology` | No step applies them. No `EnergyShareRequirements` is written. |
| `ReserveMargin`, `ReserveMarginTagFuel`, `ReserveMarginTagTechnology` | No step applies them. |
| `TotalAnnualMinCapacityInvestment`, `CapacityAdditionalMaxGrowthRate`, `CapacityAdditionalMinGrowthRate`, `CapacityAdditionalMaxFloor` | No step applies them. |
| `TotalAnnualMaxCapacityInvestment` | It decides which technology is a candidate. `extensions.json` holds it. No field bounds the build of one year. |
| `DepreciationMethod`, the salvage value | Not translated. |
| The fixed and the variable cost of the years after the first year | `extensions.json` holds them. |
| The capacity limits of a transport candidate after the first year | `extensions.json` holds them. |
| The variable cost of a storage or a transport candidate | Not translated. |
| A limit on the energy capacity of a storage | The canonical stage states none. |
| The representative days of the years after the first year | Each series uses them, and `extensions.json` holds no record for them. |
| A plant of the base system that is not a candidate | It is in no technology. |
| The trade parameters (`TradeRoute`, `CapitalCostTrade` and the other `*Trade*` parameters) | No step reads them. |

## Assumptions worth checking against your model

| Value | Assumed as |
| --- | --- |
| `CapitalCost` | An overnight cost for each unit of capacity, which the solver annuitises |
| `OperationalLife` | The period over which the capital cost is recovered, and how long a built unit runs |
| `DiscountRateIdv`, `DiscountRate` | A cost of capital with no debt in it |
| `units: currency_year` | The year that each cost is quoted in |
| The electricity ratios of the first year | The ratios of every year |
| `AnnualEmissionLimit` | A limit on a pollutant of the region. It becomes a cap only when the pollutant covers the whole model. |
| A residual capacity | The capacity of one plant, which belongs to the candidate of the same name only |
