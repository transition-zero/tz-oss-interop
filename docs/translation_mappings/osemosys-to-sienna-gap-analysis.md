# What an OSeMOSYS model loses on the way to Sienna

## What this document is for

tz-oss-interop translates an OSeMOSYS model into Sienna. Two pipelines do it, and this document
covers both:

- `osemosys-csv-to-sienna` writes a **Sienna system**: the fleet of one model year, which
  PowerSimulations.jl dispatches.
- `osemosys-csv-to-sienna-investments` writes the same system, and a **Sienna Investments
  Portfolio** beside it: the technologies that a plan may build over every year in scope, which
  PowerSystemsInvestments.jl expands.

The TZ-format pipelines, `tz-osemosys-to-sienna` and `tz-osemosys-to-sienna-investments`, run
the same steps, so each entry applies to them too.

An OSeMOSYS model states more than either document holds, and the two solvers state different
mathematics from OSeMOSYS. This document gives one entry for each loss. Each entry gives four
things:

| Column | What it holds |
| --- | --- |
| OSeMOSYS data | The set, the parameter or the rule of your model. The default name comes first, then the canonical name in brackets. |
| What happens to it | What the translation or the solve does with it |
| Cause | One of the causes below, and the reason |
| Effect | What the loss changes in the dispatch or in the expansion |

Read it before you trust a number from a solve of a translated OSeMOSYS model.

## The words this document uses

| Word | What it means |
| --- | --- |
| **The operations year** | The model year whose fleet the Sienna system holds |
| **The operations mode** | The operating mode whose values the system uses: mode `1` when the model holds it |
| **A representative day** | One day of 24 hours that stands for a number of days of the year, its weight |
| **The dispatch** | A PowerSimulations.jl solve of the Sienna system |
| **The expansion** | A PowerSystemsInvestments.jl solve of the portfolio |
| **The PyPSA dispatch** | A PyPSA solve of the network that the `sienna-to-pypsa` pipeline writes from the Sienna system and its `extensions.json` |
| `extensions.json` | A file that tz-oss-interop writes beside `system.json`. It holds values that Sienna has no field for, under the names of the PyPSA attributes with the same meaning. Sienna does not read it. |
| `decisions.md` | A file that tz-oss-interop writes beside the output of each run. It names each component and each value that the run leaves out, with the reason. |

## The causes

Each entry names one cause:

| Cause | Meaning |
| --- | --- |
| **translation** | The translation loses something. The reason is one of three: SiennaSchemas has no field for it, the rule of this translator leaves it out, or the scope of the translation is electricity only. A value that SiennaSchemas has no field for is in `extensions.json` when its component is electricity, so only the solve loses it. |
| **mathematics** | The two models state different mathematics. The data reaches Sienna, and the solve uses it in another way. |
| **optimum** | The solver found a different optimum among equal ones. |

An effect "on a large published model" comes from the benchmark run of a published OSeMOSYS
model of 78 countries over 35 years. The case studies under [`docs/case_studies/`](../case_studies/)
give the measured numbers.

## The short version

| Group | Entries | What to know |
| --- | --- | --- |
| [The four structural losses](#the-four-structural-losses) | 4 | No network, no unit commitment data, no time order inside a timeslice, one year of fleet. No version of this translator can carry them. |
| [What the system has no component for](#what-the-system-has-no-component-for) | 9 | The system holds electricity only. The largest effect is the loss of the conversion losses between two electricity fuels. `extensions.json` holds each conversion, and the fuels that are not electricity as PyPSA components. |
| [Operating modes](#operating-modes) | 4 | The system uses one mode for each technology. `extensions.json` holds the other modes, and the dispatch does not run them. |
| [Costs and prices](#costs-and-prices) | 6 | The fuel price comes from one producer. A line has no cost. |
| [Limits on activity and energy](#limits-on-activity-and-energy) | 5 | No annual limit on energy reaches a Sienna dispatch. This is the largest single effect on the dispatch. The `sienna-to-pypsa` leg gives the limits of the year to a PyPSA dispatch. |
| [Storage](#storage) | 7 | A storage is rated on its electricity output, and it cycles in time order. |
| [Time](#time) | 5 | The weights round, and a model with no day structure loses its time order. |
| [Policy](#policy) | 3 | No emission limit, no renewable target and no reserve margin reaches a dispatch. `extensions.json` holds each one. |
| [Units and defaults](#units-and-defaults) | 4 | `CapacityToActivityUnit` does not convert a unit. A non-zero default of a ratio is not applied. |
| [The portfolio](#the-portfolio) | 10 | One value for each candidate where OSeMOSYS states one for each year. A cap only for a pollutant of the whole model. |
| [The expansion solve](#the-expansion-solve) | 11 | Some entries are open. |
| [Differences that are not a loss](#differences-that-are-not-a-loss) | 5 | A comparison against published results also differs where nothing is lost. |
| [What a PyPSA dispatch holds](#what-a-pypsa-dispatch-holds) | 21 | A PyPSA network holds the annual bounds, the cost of a line, the loss of a line and the fuels that are not electricity. The other limits of Sienna stay. |
| [Losses that the report does not name](#losses-that-the-report-does-not-name) | 6 | These losses leave no event in `decisions.md`. |

---

## The four structural losses

| OSeMOSYS data | What happens to it | Cause | Effect |
| --- | --- | --- | --- |
| The connections between locations. OSeMOSYS states no electrical network, only a technology that moves a fuel from one location to another. | Each connection becomes a `TwoTerminalGenericHVDCLine`. The system has no `Line`, no impedance and no reference bus. | translation: OSeMOSYS has no data for an AC network. | The system is a transport model. It solves with the network model `copperplate`, because `dcp` needs AC branches. No flow follows the physics of a network. |
| Unit commitment data. OSeMOSYS states no start cost, no minimum stable level, no minimum up or down time and no ramp rate. | `ramp_limits` and `time_limits` are empty. `active_power_limits.min` is 0. `decisions.md` records each field as `NOT_MAPPED`. | translation: OSeMOSYS has no source for it. | A solve with exact unit commitment has nothing to apply. A thermal plant can run at any output from 0 to its limit, and change it in one hour. |
| The time order inside a year. OSeMOSYS states energy over a `TIMESLICE`, which is a share of the year and not an hour. | The step builds one representative day for each season and day type, and joins the days from 1 January. | mathematics: OSeMOSYS balances energy over each timeslice. PowerSimulations.jl dispatches over hours in time order. | A chronological constraint has no source in the model. The dispatch applies its own time order: a storage carries its level from one day to the next, and the next day stands for other days of the year. |
| The investment decisions of the model years. The Sienna system holds the `ResidualCapacity` (`residual_capacity`) of the operations year. | The capacity that the plan builds, in that year and in each other year, does not reach the system. | translation: the canonical stage reads no OSeMOSYS results, so an optimised capacity has no source. | The fleet can be short of the peak at one location. On a large published model, the published solve builds about 3 GW in the first year, mostly wind. The dispatch has no such plant, and 2 locations serve their peak only with unserved energy at a penalty. |

## What the system has no component for

| OSeMOSYS data | What happens to it | Cause | Effect |
| --- | --- | --- | --- |
| A technology of kind `conversion` between two electricity fuels at one location, for example a transmission or distribution step from one voltage fuel to another | It has no component. A `conversion` record of `extensions.json` holds it, with its `efficiency`. `decisions.md` records each one. The demand stays at the fuel where the model states it. | translation: the two fuels of one location share one bus, so the conversion joins nothing. | The dispatch does not make the electricity that the conversion loses. On a large published model this is about 400 TWh of a 4,100 TWh year, the largest part of the difference in production. |
| A fuel that is not electricity, and its `fuel_supply`, `conversion` and pipeline technologies | No Sienna component. The `bus`, `generator` and `conversion` records of `extensions.json` hold them as PyPSA buses, generators and links, one for each mode. The fuel cost rule still prices the fuel of a Sienna plant. | translation: Sienna holds electricity only. | In the Sienna dispatch, a limit on a fuel, for example the gas that a region can import, does not limit the plants that burn it. A PyPSA network of the same translation holds the limit. |
| Two modes of one fuel technology, for example the two directions of a pipeline | Each mode is a component of its own, and each can run at the whole capacity of the technology. | translation: a PyPSA component runs one set of ratios. | The two modes together can move twice the capacity. A flow in both directions at one time only loses energy, so a solve does not choose it. |
| The capital cost, the fixed cost and the life of a technology of a fuel that is not electricity | No record holds them. The report of the parameters that no step applies names them. | translation: a dispatch builds no capacity of a fuel at a cost. | A fuel technology with residual capacity and a capital cost keeps its residual capacity. One with no capital cost is extendable at no cost. |
| A technology of kind `export` | No component. An export of electricity has a `conversion` record with no `bus1`. | translation: the system has no component that takes energy out of the model. | An export of electricity is a demand that the system does not hold. |
| A trade route of an electricity fuel: `TradeRoute` (`transport_route`) and the other trade parameters | No component. A `conversion` record of `extensions.json` holds it, with the ends `<region>/<fuel>`. | translation: a route joins regions, and the system holds locations. | The dispatch moves no energy on the route. |
| `AccumulatedAnnualDemand` (`accumulated_annual_demand`) and `SpecifiedAnnualDemand` of a fuel that is not electricity | A `load` record of `extensions.json` on the bus of the fuel. An accumulated demand is flat over the year. | translation: Sienna holds electricity only. | None on the Sienna dispatch. A PyPSA network meets the demand in each hour, where OSeMOSYS meets an accumulated demand over the year. |
| A technology with no kind | Its records of `extensions.json`, where a fuel of its flows is not electricity. | translation: no kind fits it, often because it moves a fuel between two locations. | Its energy is not in the Sienna system. |
| A storage of a fuel that is not electricity, and a trade route of a fuel that is not electricity | Not translated. The storage step and the report of the parameters that no step applies name them. | translation: no record kind of this translation holds them. | The fuel cannot shift in time or move between regions. |

## Operating modes

| OSeMOSYS data | What happens to it | Cause | Effect |
| --- | --- | --- | --- |
| The values of a generator at a mode other than the operations mode | The `operating_modes` of the generator record in `extensions.json` hold the cost, the ratios and the emission rates of each other mode, for each MWh of its activity. | translation: a Sienna generator runs one cost curve and one set of ratios. | A plant that can switch to a cheaper or a cleaner mode cannot switch. |
| A mode of a transport technology that is not the flow back, for example a mode that puts out electricity at one end with no input, which is an import from outside the model | The `operating_modes` of the line record hold it, and one warning names three lines. | translation: a line holds one direction and its flow back. | The import does not happen. On a large published model, 21 lines to neighbours outside the model import about 70 TWh in the published solve and 0 in the dispatch. |
| The loss of the flow back of a line, when it differs from the forward loss | The ratios of the flow back are in the `operating_modes` of the line record. | translation: a Sienna line states one loss. | None in the dispatch today, because the solve applies no loss (refer to [Costs and prices](#costs-and-prices)). |
| Two or more modes that flow back on one line | The first mode in number order applies. The `operating_modes` of the line record hold the others. | translation: a line holds one flow back. | The line uses the ratios of the first mode only. |

## Costs and prices

| OSeMOSYS data | What happens to it | Cause | Effect |
| --- | --- | --- | --- |
| The price of a fuel. OSeMOSYS prices a fuel by the technologies that make it, with their limits. | A plant pays the `VariableCost` (`variable_operation_cost`) of the cheapest `fuel_supply` technology of the fuel in its region, for each unit of the fuel. A pipeline is not a producer. | translation: a Sienna cost curve states one price. The rule of this translator chooses one producer. | When the cheapest producer has a limit, the true price is higher, so the plant runs too cheaply. When the only producer is a backstop, the plant pays the backstop price and does not run. On a large published model, 13 gas plants of about 3 GW take a backstop price and do not run. The published solve gives them about 0.7 TWh. |
| The other costs of a producer: its capital cost, its fixed cost and the fuels that it takes in | Not in the fuel price | translation: the rule reads the variable cost of the producer only. | The fuel price is lower than the full cost of the fuel. |
| `VariableCost` of an `AggregateTransportTechnology` | It goes to `marginal_cost` of the `controllable_line` record of `extensions.json`. The `sienna-to-pypsa` leg writes it as `Link.marginal_cost`, so a PyPSA dispatch applies it. | translation: `TwoTerminalGenericHVDCLine` has no cost field. | Trade is free. With the loss below, this is most of the difference in trade: on a large published model, about 815 TWh in the dispatch against about 390 TWh published. |
| The loss of a line, `1 − output ratio / input ratio` | The system states it in `loss`. The solve uses `HVDCTwoTerminalLossless`, which ignores it. The `sienna-to-pypsa` leg writes it as `Link.efficiency`. It writes a two-way line as two one-way links, so a PyPSA dispatch applies the loss in each direction. | mathematics: the solve formulation is lossless. | Trade loses nothing, so a line carries more than in OSeMOSYS. |
| `FixedCost` (`fixed_cost`) of a generator or a storage | It goes to `fom_charge_per_mw_year` in `extensions.json`. `operation_cost.fixed` is 0. | translation: OSeMOSYS charges a fixed cost on capacity. A dispatch cannot change capacity. | None on the dispatch. The objective holds no fixed cost. |
| `VariableCost` of a `RenewableNonDispatch` | `NOT_MAPPED` | translation: the type has no `operation_cost`. | None on the dispatch, because the output is fixed. |

## Limits on activity and energy

| OSeMOSYS data | What happens to it | Cause | Effect |
| --- | --- | --- | --- |
| `TotalTechnologyAnnualActivityLowerLimit` (`total_technology_annual_activity_lower_limit`) and `TotalTechnologyAnnualActivityUpperLimit` (`total_technology_annual_activity_upper_limit`) | They go to `e_sum_min` and `e_sum_max` of the generator record of `extensions.json`, in MWh of output for each year. `decisions.md` records each limit of a technology with no record, and one warning names three. The `sienna-to-pypsa` leg writes the value of the operations year as `Generator.e_sum_min` and `e_sum_max`, weighted by the representative days, so a PyPSA dispatch applies it. | translation: a Sienna system has no field for a limit on the energy of a year. | The largest single effect on the dispatch. On a large published model, 24 gas plants must make about 450 TWh. The dispatch gives them about 78 TWh. Gas combined cycle makes about 220 TWh against about 550 TWh published, and coal makes more. |
| `TotalTechnologyModelPeriodActivityLowerLimit` / `UpperLimit`, `TechnologyActivityByModeLowerLimit` / `UpperLimit`, `TechnologyActivityDecreaseByModeLimit` | The record of the component holds them: `e_sum_min_horizon`, `e_sum_max_horizon` and the bounds of `operating_modes`. `decisions.md` records each one of a technology with no record, and one warning names three. | translation: SiennaSchemas has no field for them. | The dispatch is free of these limits. |
| `AvailabilityFactor` (`availability_factor`) | The step applies it in each hour, as a derate. | mathematics: OSeMOSYS states it as a limit on the energy of the year. A dispatch has no such limit. | A plant cannot reach its full output in a peak hour. On a large published model, the effect is small: about 1 TWh less nuclear. |
| `CapacityFactor` (`capacity_factor`) of a storage technology or a transport technology | A companion parquet beside `extensions.json` holds the factor of each hour: `storage.parquet` or `controllable_lines.parquet`. | translation: a storage and a line take their `availability_factor` as one derate for every hour, and no factor for each timeslice. | The storage or the line can use its capacity × its `availability_factor` in each hour. |
| The minimum stable level of a thermal plant | `active_power_limits.min` is 0. | translation: OSeMOSYS states none. | A thermal plant can run at any output. |

## Storage

| OSeMOSYS data | What happens to it | Cause | Effect |
| --- | --- | --- | --- |
| The capacity of a storage technology. OSeMOSYS states it on its activity. | `base_power` is the residual capacity × the electricity output ratio of the discharging technology. | mathematics: Sienna rates a storage on its electricity output. | The installed capacity of a storage is lower than the published value by the output ratio. On a large published model, pumped storage is about 9 GW lower. |
| The storage balance. OSeMOSYS balances a storage over its timeslices, and `StorageBalanceDay`, `StorageBalanceSeason` and `StorageBalanceYear` can add a balance over a day, a season or a year. | The dispatch carries the level from one representative day to the next. The storage record holds the three flags, and no step applies them. The `sienna-to-pypsa` leg writes `StorageBalanceYear` as `StorageUnit.cyclic_state_of_charge_per_period`, which PyPSA applies only to a cyclic unit. | mathematics: the dispatch runs the days in time order. | A storage cycles more. On a large published model, pumped storage puts out about 9 TWh in the dispatch against 0.05 TWh published. |
| A storage that two or more technologies or modes charge, or discharge | Left out | translation: a Sienna storage takes its power from one technology in each direction. | Its capacity is lost. |
| A storage with no `ResidualStorageCapacity` (`residual_storage_capacity`) in the operations year | Left out | translation: it holds no energy. | Its power is lost. On a large published model, one battery of about 0.4 GW states 0 energy. |
| The default 999 of `residual_storage_capacity` | A storage with no row takes 999 units of energy, as OSeMOSYS gives it. | translation: the translator uses the value as it is. | A storage with power and no stated energy has a very large energy capacity. On a large published model, no such storage has power in the first year. |
| An `input_activity_ratio` below 1 at the charge mode | `efficiency.in` is `technology_to_storage` / the ratio, which is above 1. | translation: the rule of this translator divides by the ratio. | The storage takes in more energy than it draws. |
| `StorageLevelStart` (`storage_level_start`) | The step uses it as the level at the start of the operations year. | translation: OSeMOSYS states it for the start of the model period. | The first hours of a later year start from that level. |

## Time

| OSeMOSYS data | What happens to it | Cause | Effect |
| --- | --- | --- | --- |
| A daily time bracket that is not a whole number of hours | It is rounded to a whole hour when it is within 0.05 h. `decisions.md` records each rounding. | translation: the dispatch runs in whole hours. | The weights of the days add up to a little more or less than 365 days. On a large published model, 365.02 days, so the demand of the year is 0.006 % high. |
| A model that states no day structure, or a structure that does not make days of 24 hours | Each timeslice becomes one hour, in set order. One warning names the reason. | translation: no day of 24 hours can stand for the timeslices. | The series lose their time order. A storage then cycles between unrelated hours. |
| Demand in a timeslice whose `YearSplit` (`year_split`) is 0 | Left out, and `decisions.md` names it | translation: the timeslice holds no hour. | That demand is lost. |
| The timeslices of a day that give different weights | The day takes the mean of the weights. `decisions.md` gives the values. | translation: a representative day has one weight. | The energy of each timeslice moves a little. |
| The representative days of the years after the first year, in the portfolio | Each series of a year uses the days of that year. `extensions.json` holds the days of the first year only. | translation: a `representative_period` record has no year. | The expansion leg splits each year by the days of the first year. A model whose days change by year is split wrongly. |

## Policy

| OSeMOSYS data | What happens to it | Cause | Effect |
| --- | --- | --- | --- |
| `AnnualEmissionLimit` (`annual_emission_limit`) and `ModelPeriodEmissionLimit` (`model_period_emission_limit`) in the dispatch | A `constraint` record of `extensions.json` holds them. No step applies them to the system. | translation: an operations system has no emission cap. | None on a model whose limits do not bind in the operations year. On a large published model, no limit binds in the first year. |
| `REMinProductionTarget` (`generation_fraction_requirement`), `RETagFuel`, `RETagTechnology` | A `constraint` record holds them. | translation: this translator writes no `EnergyShareRequirements`. | No renewable target binds. |
| `ReserveMargin` (`reserve_margin`), `ReserveMarginTagFuel`, `ReserveMarginTagTechnology` | A `constraint` record holds them, when a tag states a value. | translation: this translator writes no reserve requirement. | No reserve margin binds. |

## Units and defaults

| OSeMOSYS data | What happens to it | Cause | Effect |
| --- | --- | --- | --- |
| `CapacityToActivityUnit` (`capacity_to_activity_unit`) | The record of each component holds it, in MWh for each MW. The step uses `units:` for each conversion. | translation: the rule of this translator reads the units from the mappings file. | A model whose `CapacityToActivityUnit` does not agree with `units:` gets wrong costs and limits for each MWh. No check finds it today. |
| A default other than 0 of `InputActivityRatio`, `OutputActivityRatio` or `EmissionActivityRatio` | Not applied. `decisions.md` records it, and one warning names it. | translation: such a default gives every technology the ratio for every fuel and every mode. | A ratio that the model states only by its default is lost. |
| A currency code | The step applies the scale of the currency, for example `million`, and no other conversion. | translation: the translator converts no currency. | A model in euros reads as a model in dollars. |
| A default of `TotalTechnologyAnnualActivityLowerLimit` above 0, or of the upper limit at 0 or above | The bounds in `extensions.json` read the stated rows only. | translation: the rule of this translator. | A bound that the model states by its default is not in the record. |

## The portfolio

| OSeMOSYS data | What happens to it | Cause | Effect |
| --- | --- | --- | --- |
| `CapitalCost` (`capital_cost`) of each year | `capital_costs` holds the cost of the earliest year in which a plan can build the candidate at a cost above 0. `extensions.json` holds each year. | translation: a capital cost curve has no year. | A cost that falls over the years is the cost of one year in the expansion. |
| `FixedCost` (`fixed_cost`) and the variable cost of each year | The portfolio holds the first year. `extensions.json` holds each year. | translation: `operation_costs` has no year. | A fuel price or a penalty that changes by year is the price of the first year. |
| The capacity limits of an `AggregateTransportTechnology` | The portfolio holds the first year. `extensions.json` holds each year. | translation: the type holds one bound. | A limit that changes by year does not change. |
| The electricity ratios of each year | The portfolio reads the ratios of the first year. | translation: the rule of this translator. | A technology whose efficiency improves by year keeps the efficiency of the first year. |
| `AnnualEmissionLimit` of a pollutant that only some technologies emit, for example a pollutant of one region | It goes to a `constraint` record of `extensions.json`. `decisions.md` records each one. | translation: `CarbonCaps` names no region and no pollutant, so it limits the whole portfolio. | No limit binds. On a large published model, each pollutant belongs to one country, so no limit reaches the portfolio. |
| `ModelPeriodEmissionLimit` of a pollutant that covers the whole model | `NOT_MAPPED` in the portfolio, and one warning. The `constraint` record holds it. | translation: `CarbonCaps` holds one year. | That limit does not bind. |
| A limit on the energy capacity of a storage | None | translation: the canonical stage states none. | `capacity_limits_energy` is absent. |
| The variable cost of a storage candidate, and of a transport candidate | Not in the portfolio. The `technology` record of a transport candidate holds it for each year. | translation: `AggregateTransportTechnology` has no operation cost, and the storage candidate states its fixed cost only. | The expansion runs them at no cost. |
| `TotalAnnualMinCapacityInvestment`, `CapacityAdditionalMaxGrowthRate`, `CapacityAdditionalMinGrowthRate`, `CapacityAdditionalMaxFloor` | The `technology` record holds them for each year. `decisions.md` records each one of a technology that is not a candidate. | translation: SiennaSchemas has no field for a limit on the build of one year. | The expansion can build any amount in one period. |
| A plant of the base system that is not a candidate | In no technology. | translation: the rule of this translator gives a plant to the candidate of the same name only. | The expansion leg adds such a plant as a technology of its own. Refer to [The expansion solve](#the-expansion-solve). |

## The expansion solve

These entries come from the leg `sienna-to-power-systems-investments` and from
PowerSystemsInvestments.jl at the pinned commit `8bfed9f`.
[Running a capacity expansion](../developer_documentation/capacity-expansion.md) gives the
detail.
[The existing fleet of an OSeMOSYS plan](../developer_documentation/capacity-expansion.md#the-existing-fleet-of-an-osemosys-plan)
gives the rules for an existing plant.

| OSeMOSYS data | What happens to it | Cause | Effect |
| --- | --- | --- | --- |
| The capacity limits of each year | The leg writes one limit: the largest maximum of the years, and no minimum. `decisions.md` records each minimum. | mathematics: the package holds one limit, and reads `min` as a floor on the build of each period. | A limit that falls by year does not fall. A minimum does not bind. |
| `CarbonCaps` | It reaches the package with its `target_year`. The package builds no constraint from it. | mathematics: the package builds a constraint from `EnergyShareRequirements` only. | No cap binds. |
| `line_loss` | The leg writes 0. `decisions.md` records the stated loss. | mathematics: the package takes the loss at the end region of a flow that can be negative, so a flow back makes energy. | Trade loses nothing. |
| The direction of a transport technology | The flow goes both ways. | mathematics: the package lets a transport technology flow both ways. | A one-way connection carries energy back. |
| The retirement of the fleet. OSeMOSYS reduces the residual capacity of each year. | The package holds the existing capacity of the first year in every period. | mathematics: the package reads no retirement. | A plant that the model retires stays in the expansion. |
| An existing storage, an existing `RenewableNonDispatch` and an existing line | Left out of the plan. One warning names each one. | mathematics: the package attaches no such device. | The expansion builds again what exists. |
| The availability of a thermal candidate | Not read. One warning names each one. | mathematics: the package reads a profile for `RenewableDispatch` and `HydroDispatch` only. | A thermal plant runs at its whole capacity in every hour. |
| A `SupplyTechnology` of a type that has no model in the adapter, for example `RenewableNonDispatch` | Left out of the plan. The adapter warns. | mathematics: the adapter sets no formulation for the type. | That candidate cannot be built. |
| The years between two investment periods | They carry no operations. The weights do not change. | mathematics: the package counts the operations of the year of each period only. | The operating cost of the plan is lower than in OSeMOSYS, which counts each year. |
| A capacity limit or a unit size that the portfolio does not state | The leg writes the default of the package, for example a maximum of 1e8 MW. | mathematics: the reader refuses a null. | None. The default binds nothing. |
| The emissions of the expansion | The results pipeline `power-systems-investments-to-results` writes no `emissions` rows. | translation: the solve results state no emissions. | A comparison of emissions has one side only. |

## Differences that are not a loss

A comparison of a solve against published results differs for these reasons too:

| Difference | Cause | Effect |
| --- | --- | --- |
| The published emissions count the pollutant of each fuel that enters a region: extraction, imports, and pipelines that move a pollutant between two regions. | translation: Sienna holds electricity only, so the Sienna emissions are those of the power plants, with the fuel that each burns. A PyPSA network of the same translation holds the fuels, and counts the emissions of each component. | On a large published model, about 560 Mt of the published emissions are not from electricity, and two transit countries state negative emissions. The PyPSA dispatch gives 1,441 Mt against 1,459 Mt published. |
| The published emissions of a pollutant in two or more regions | translation: the Sienna system keys an emission rate by the pollutant alone, so `aetos-to-results` sums `AnnualEmissions` over the regions. | A comparison of emissions gives one row for each pollutant, and no row for each region. |
| The installed capacity of a plant or a line | translation: the published side states the capacity of the activity. The Sienna side states the electricity rating: for a plant the residual capacity × the electricity output ratio, and for a line the residual capacity × `availability_factor` × the electricity input ratio. | When a ratio or an `availability_factor` is not 1, the two `installed_capacity` rows differ by that factor. A storage differs by its output ratio, as [Storage](#storage) says. |
| The objective | mathematics: the published objective is the discounted cost of the whole model period. The dispatch objective is the cost of its hours, with no weight. | The two objectives do not compare. |
| Plants with the same cost | optimum: the solver can give the whole output to one plant of a set of plants with one cost. | On a large published model, the output of 19 gas plants at one cost goes to one of them. The total is the same. |
| The flow on lines with no cost and no loss | optimum: many flows give the same objective. | The trade of one line can differ from one solve to the next. The total of the system is the same. |
| The variable cost of a `RenewableDispatch` | mathematics: PowerSimulations.jl puts it in the objective with a negative sign, as a reward for output. | The objective is lower. On a large published model, by about 150 million USD in a year. |

## What a PyPSA dispatch holds

The `sienna-to-pypsa` pipeline turns the Sienna system into a PyPSA network. It reads the
values of `extensions.json`, and gives each value that PyPSA has an attribute for to that
attribute. Each other value goes on, unchanged, to the `extensions.json` of the network.
[The Sienna to PyPSA mapping](translation-from-sienna-to-pypsa.md) gives each field.

This table gives each entry above whose cause is a limit of Sienna: a field that SiennaSchemas
does not have, or a formulation of PowerSimulations.jl. "Holds it" tells you if the PyPSA
network of the same translation holds the OSeMOSYS data. The measured effects come from the
same large published model, in the first year. The pipeline reads a Sienna system and not a
portfolio, so the entries of [The portfolio](#the-portfolio) and
[The expansion solve](#the-expansion-solve) are not in the table.

| Entry | Holds it | Measured effect |
| --- | --- | --- |
| [The time order inside a year](#the-four-structural-losses) | No. PyPSA also dispatches the hours in time order. | Not measured |
| [A technology of kind `export`](#what-the-system-has-no-component-for) | No. The `conversion` record has no `bus1`, so it goes on to `extensions.json`. | Not measured |
| [The values of a generator at another mode](#operating-modes) | No. The `operating_modes` go on to `extensions.json`. A PyPSA generator has one `marginal_cost`. | Not measured |
| [An import mode of a transport technology](#operating-modes) | No. The `operating_modes` go on to `extensions.json`. | 21 lines import about 69 TWh in the published solve, and 0 in each dispatch. |
| [The loss of the flow back of a line](#operating-modes) | Partly. The reverse link of a line that flows both ways takes the `efficiency` of the forward direction. The ratios of the flow back go on to `extensions.json`. | Not measured |
| [Two or more modes that flow back on one line](#operating-modes) | No. The reverse link uses the values of the line. | Not measured |
| [The price of a fuel](#costs-and-prices) | Yes, for a plant whose fuel has a bus and that states no annual bound. The plant becomes a `Link` that draws its fuel from the bus, and the network prices the fuel. A plant with an annual bound stays a `Generator` at the Sienna price, because a `Link` has no `e_sum_min`. | On the large published model, 539 plants draw their fuel from a bus, and the 24 gas plants with a bound stay generators. |
| [A fuel that is not electricity, and its technologies](#what-the-system-has-no-component-for) | Yes. The network holds a bus for each fuel, a generator for each supply, a link for each mode that moves or converts a fuel, and a load for each demand. | The emissions are 1,441 Mt, against about 760 Mt before and 1,459 Mt published. The objective of the 96 hours rises from 1.85 × 10⁹ to 5.11 × 10⁹ USD, because it pays for the gas demand. |
| [The demand for a fuel that is not electricity](#what-the-system-has-no-component-for) | Yes. Each demand becomes a `Load` on the bus of its fuel. | The gas demand is 3,709 TWh in the year. |
| [`VariableCost` of an `AggregateTransportTechnology`](#costs-and-prices) | Yes. It becomes `Link.marginal_cost`. | With the loss of the line: the trade is about 400 TWh, against about 815 TWh in the dispatch and about 390 TWh published. A PyPSA dispatch with no line cost and no line loss gives about 875 TWh. |
| [The loss of a line](#costs-and-prices) | Yes. It becomes `Link.efficiency`, in each direction. | The lines lose about 21 TWh in the year. The row above gives the effect on trade. |
| [`VariableCost` of a `RenewableNonDispatch`](#costs-and-prices) | No. `marginal_cost` is 0. | None, because the output is fixed. |
| [`TotalTechnologyAnnualActivityLowerLimit` and `UpperLimit`](#limits-on-activity-and-energy) | Yes. They become `Generator.e_sum_min` and `e_sum_max` when the snapshots stand for one whole year. Solve them in one window. | The 24 gas plants make about 452 TWh, against about 78 TWh in the dispatch and about 453 TWh published. Without the bounds, a PyPSA dispatch gives gas combined cycle about 296 TWh less, coal about 214 TWh more, and about 98 Mt more emissions. |
| [The limits over the model period and by mode](#limits-on-activity-and-energy) | No. They go on to `extensions.json`. | Not measured |
| [`AvailabilityFactor`](#limits-on-activity-and-energy) | No. The network takes the same derate in each hour. | Not measured |
| [`CapacityFactor` of a storage or a transport technology](#limits-on-activity-and-energy) | Yes. The factor of each hour becomes the `p_max_pu` series of the storage unit or the link. | Not measured. The model states none. |
| [The capacity of a storage technology](#storage) | No. `p_nom` is `base_power`, the electricity output. | Pumped storage is about 42.9 GW in each dispatch, against about 51.7 GW published. |
| [The storage balance](#storage) | Partly. `StorageBalanceYear` becomes `cyclic_state_of_charge_per_period`, which PyPSA applies only to a cyclic unit. PyPSA also runs the days in time order. | Pumped storage puts out about 1.5 TWh, against about 8.9 TWh in the dispatch and 0.05 TWh published. |
| [A storage that two or more technologies charge or discharge](#storage) | No. The system has no such storage, so the network has none. | Not measured |
| [`AnnualEmissionLimit` and `ModelPeriodEmissionLimit` in the dispatch](#policy) | No. The `constraint` record goes on to `extensions.json`. | None. No limit binds in the first year. |
| [The variable cost of a `RenewableDispatch`](#differences-that-are-not-a-loss) | Yes. PyPSA puts the cost in the objective with a positive sign. | Not measured |

The other entries have the same effect on the PyPSA dispatch, because their cause comes before
the Sienna system. The comparison measured three of them:

- The production is about 358 TWh lower than published in the PyPSA dispatch, and about
  370 TWh lower in the dispatch. The conversions between two electricity fuels have no
  component in either network.
- The unserved energy is 1,141 MWh in the 96 hours in each dispatch.
- The emissions are about 1,441 Mt in the PyPSA dispatch, about 847 Mt in the dispatch and
  about 1,459 Mt published. The rest of the difference comes from the electricity production:
  less coal, oil and derived gas burn where the conversions lose nothing.

## Losses that the report does not name

These losses happen and leave no event in `decisions.md`. Each one is a defect of tz-oss-interop.

| OSeMOSYS data | What happens to it |
| --- | --- |
| A flow row of the reverse mode of a line on a fuel that is not electricity | Left out, with no event. |
| A `fuel_supply` technology that the activity limit of the year excludes from the fuel price | The note of the fuel term counts only the producers that remain. |
| A parameter that states values only in the years after the first year, in the investments pipeline | The report of the parameters that no step applies reads the first year only. |
| A demand of a year after the first year on a fuel that is not an electricity load | Left out of the portfolio, with no event. |
| An annual demand whose value is null | Left out, with no event. |
| A member of a set in a model with two or more regions | The scope step keeps a member that is in scope in one region, in every region. The storage step can report a storage as having no link in a region that does not hold it. |
