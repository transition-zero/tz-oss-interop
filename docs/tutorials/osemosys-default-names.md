# What tz-oss-interop knows about an OSeMOSYS model

OSeMOSYS sets no names. Each modeller chooses the name of each set and each parameter of a model.
tz-oss-interop knows one fixed list of names, the default names. It maps a model that uses the
default names with no mappings file.

This page lists the default names and the other facts that tz-oss-interop knows. It also lists
the facts that it does not know. Use it to find what your mappings file must state. The
[OSeMOSYS mappings tutorial](osemosys-mappings.md) teaches each part of the mappings file.

This page copies the canonical schema file,
`interop/plugins/shared/osemosys_canonical_schema.yaml`. If this page and the schema file
disagree, the schema file is correct.

## How to use this page

1. For each set of your model, find its default name in [The sets](#the-sets).
2. For each parameter of your model, find its default name in [The parameters](#the-parameters).
3. Compare the name, the index columns and the unit of each item with the table.
4. Write one entry in your mappings file for each difference.
5. Write each item of [What tz-oss-interop does not know](#what-tz-oss-interop-does-not-know).

A set or a parameter that agrees with this page needs no entry. A set or a parameter that has no
entry and does not agree with this page stays an extension table. tz-oss-interop keeps an
extension table in `extensions/` with its own name, so you lose no data. But a tool that reads the
canonical stage does not find it.

## The sets

| Default name | Canonical set | Meaning |
| --- | --- | --- |
| `YEAR` | `year` | Years of the model period. |
| `TECHNOLOGY` | `technology` | Technologies, each of which takes in fuels, puts out fuels, or both. |
| `TIMESLICE` | `timeslice` | Parts of a year, each with its own demand and availability values. |
| `FUEL` | `fuel` | Energy carriers and other commodities that technologies put out or take in. |
| `EMISSION` | `pollutant` | Emissions and other impacts that the activity of a technology causes. |
| `MODE_OF_OPERATION` | `operating_mode` | Modes in which a technology can operate, each with its own ratios. |
| `REGION` | `region` | Regions, each with its own balance of every fuel. |
| `SEASON` | `season` | Seasons that group the timeslices of a year for storage. |
| `DAYTYPE` | `day_type` | Day types that group the timeslices of a season for storage. |
| `DAILYTIMEBRACKET` | `daily_time_bracket` | Parts of a day that group the timeslices of a day type for storage. |
| `STORAGE` | `storage` | Storages that technologies charge and discharge. |
| `REGIONGROUP` | `region_group` | Groups of regions that share an emission limit or a renewable target. |

If your model gives a set a different name, give the set its canonical name in `sets:`. Also
change the name of the index column in each table that uses the set, with `rename_columns`. See
[Lesson 3](osemosys-mappings.md#lesson-3-a-set-with-another-name).

A table that holds two regions names the second region `_REGION`. `_REGION` is not a set. It is
a column that holds members of the set `REGION`.

The value column of each table is `VALUE`.

## The parameters

The columns of the table:

- **Default name** is the name that the automatic match looks for.
- **Default columns** are the index columns that the automatic match looks for. Their order does
  not matter.
- **Canonical name** is the name that you write in `canonical` in a `parameters:` row.
- **Unit** is the type of the value. The list after this one explains each unit.
- **Default** is the value where your model states no value. The default that your model declares
  wins over it. "none" means that the parameter applies no constraint where your model states no
  value.

The units:

- `fraction` is a value from 0 to 1. If your model gives a percent, use `multiply_by: 0.01`. See
  [Lesson 5](osemosys-mappings.md#lesson-5-a-percent-in-place-of-a-fraction).
- `flag` is a whole number that selects an option. The meaning gives each value.
- `rate` is a ratio of two quantities, for example a discount rate or an activity ratio.
- Each other unit is a quantity in the units of your model. tz-oss-interop does not convert it.
  State your units in `units:`. See [Lesson 2](osemosys-mappings.md#lesson-2-state-the-units).

Each difference between a table of your model and this table has one fix:

| Difference | Fix | Lesson |
| --- | --- | --- |
| A different name | A `parameters:` row with `source` and `canonical` | [4](osemosys-mappings.md#lesson-4-a-table-with-another-name) |
| A percent in place of a fraction | `multiply_by` | [5](osemosys-mappings.md#lesson-5-a-percent-in-place-of-a-fraction) |
| An extra index column | `remove_column` | [6](osemosys-mappings.md#lesson-6-a-table-with-an-extra-column) |
| A missing index column | `repeat_for_all` | [7](osemosys-mappings.md#lesson-7-a-table-with-a-missing-column) |
| One table for each region | `source_pattern` and `columns_from_name` | [8](osemosys-mappings.md#lesson-8-one-table-for-each-region) |
| A table that you do not need | `ignore: true` | [9](osemosys-mappings.md#lesson-9-a-table-that-you-do-not-need) |
| Two tables for one parameter | A `parameters:` row for the table that you want | [10](osemosys-mappings.md#lesson-10-two-tables-for-one-parameter) |

| Default name | Default columns | Canonical name | Unit | Default | Meaning |
| --- | --- | --- | --- | --- | --- |
| `AccumulatedAnnualDemand` | `REGION`, `FUEL`, `YEAR` | `accumulated_annual_demand` | activity | 0 | Annual demand for a fuel that the model can meet at any time of the year. |
| `AnnualEmissionLimit` | `REGION`, `EMISSION`, `YEAR` | `annual_emission_limit` | emission | -1 | Highest emission in a year, where -1 means no limit. |
| `AnnualEmissionLimitRegionGroup` | `REGIONGROUP`, `EMISSION`, `YEAR` | `annual_emission_limit_region_group` | emission | none | Highest emission of a region group in a year. |
| `AnnualExogenousEmission` | `REGION`, `EMISSION`, `YEAR` | `annual_exogenous_emission` | emission | 0 | Emission in a year from sources outside the technologies of the model. |
| `AnnualExogenousEmissionRegionGroup` | `REGIONGROUP`, `EMISSION`, `YEAR` | `annual_exogenous_emission_region_group` | emission | none | Emission of a region group in a year from sources outside the technologies of the model. |
| `AvailabilityFactor` | `REGION`, `TECHNOLOGY`, `YEAR` | `availability_factor` | fraction | 1 | Share of the year in which a technology can operate. |
| `AvailabilityFactorTrade` | `REGION`, `_REGION`, `FUEL`, `YEAR` | `transport_availability_factor` | fraction | none | Share of the year in which the route from start_region to end_region can operate. |
| `CapacityAdditionalMaxFloor` | `REGION`, `TECHNOLOGY`, `YEAR` | `capacity_additional_max_floor` | capacity | none | New capacity that a technology can add in a year above its highest growth rate. |
| `CapacityAdditionalMaxGrowthRate` | `REGION`, `TECHNOLOGY`, `YEAR` | `capacity_additional_max_growth_rate` | rate | none | Highest growth of the capacity of a technology from one year to the next. |
| `CapacityAdditionalMinGrowthRate` | `REGION`, `TECHNOLOGY`, `YEAR` | `capacity_additional_min_growth_rate` | rate | none | Lowest growth of the capacity of a technology from one year to the next. |
| `CapacityFactor` | `REGION`, `TECHNOLOGY`, `TIMESLICE`, `YEAR` | `capacity_factor` | fraction | 1 | Share of the capacity of a technology that it can use in one timeslice. |
| `CapacityOfOneTechnologyUnit` | `REGION`, `TECHNOLOGY`, `YEAR` | `unit_size` | capacity | 0 | Size of one unit of new capacity, where 0 lets new capacity take any size. |
| `CapacityToActivityUnit` | `REGION`, `TECHNOLOGY` | `capacity_to_activity_unit` | activity per capacity | 1 | Activity of one unit of capacity that operates for a whole year. |
| `CapitalCost` | `REGION`, `TECHNOLOGY`, `YEAR` | `capital_cost` | currency per capacity | 0 | Overnight investment cost of one unit of new capacity. |
| `CapitalCostStorage` | `REGION`, `STORAGE`, `YEAR` | `energy_capital_cost` | currency per activity | 0 | Investment cost of one unit of new storage capacity, which holds energy. |
| `CapitalCostTrade` | `REGION`, `_REGION`, `FUEL`, `YEAR` | `transport_capital_cost` | currency per capacity | 0.00001 | Overnight investment cost of one unit of new transport capacity on a route. |
| `Conversionld` | `TIMESLICE`, `DAYTYPE` | `timeslice_in_day_type` | flag | 0 | 1 when a timeslice falls in a day type, otherwise 0. |
| `Conversionlh` | `TIMESLICE`, `DAILYTIMEBRACKET` | `timeslice_in_daily_time_bracket` | flag | 0 | 1 when a timeslice falls in a daily time bracket, otherwise 0. |
| `Conversionls` | `TIMESLICE`, `SEASON` | `timeslice_in_season` | flag | 0 | 1 when a timeslice falls in a season, otherwise 0. |
| `DaysInDayType` | `SEASON`, `DAYTYPE`, `YEAR` | `days_in_day_type` | count | 7 | Number of days of one day type in one week of a season. |
| `DaySplit` | `DAILYTIMEBRACKET`, `YEAR` | `day_split` | fraction | 0.00137 | Length of one daily time bracket, as a share of the year. |
| `DepreciationMethod` | `REGION` | `depreciation_method` | flag | 1 | Method of the salvage value, 1 for a sinking fund and 2 for a straight line. |
| `DiscountRate` | `REGION` | `discount_rate` | rate | 0.05 | Discount rate that a region applies to future costs. |
| `DiscountRateIdv` | `REGION`, `TECHNOLOGY` | `technology_discount_rate` | rate | the value of `discount_rate` | Discount rate for the investments in one technology. |
| `DiscountRateStorage` | `REGION`, `STORAGE` | `storage_discount_rate` | rate | 0.05 | Discount rate for the investments in one storage. |
| `DiscountRateTrade` | `REGION`, `_REGION`, `FUEL` | `transport_discount_rate` | rate | 0.1 | Discount rate for the investments in the transport capacity of a route. |
| `EmissionActivityRatio` | `REGION`, `TECHNOLOGY`, `EMISSION`, `MODE_OF_OPERATION`, `YEAR` | `emission_rate` | emission per activity | 0 | Emission that each unit of the activity of a technology in a mode causes. |
| `EmissionsPenalty` | `REGION`, `EMISSION`, `YEAR` | `emission_penalty` | currency per emission | 0 | Cost of one unit of an emission. |
| `FixedCost` | `REGION`, `TECHNOLOGY`, `YEAR` | `fixed_cost` | currency per capacity per year | 0 | Annual cost of one unit of installed capacity. |
| `InputActivityRatio` | `REGION`, `TECHNOLOGY`, `FUEL`, `MODE_OF_OPERATION`, `YEAR` | `input_activity_ratio` | rate | 0 | Quantity of a fuel that a technology takes in for each unit of its activity in a mode. |
| `MinStorageCharge` | `REGION`, `STORAGE`, `YEAR` | `min_storage_charge` | fraction | 0 | Lowest level of a storage, as a share of its capacity. |
| `ModelPeriodEmissionLimit` | `REGION`, `EMISSION` | `model_period_emission_limit` | emission | -1 | Highest emission over the model period, where -1 means no limit. |
| `ModelPeriodExogenousEmission` | `REGION`, `EMISSION` | `model_period_exogenous_emission` | emission | 0 | Emission over the model period from sources outside the technologies of the model. |
| `OperationalLife` | `REGION`, `TECHNOLOGY` | `lifetime` | years | 1 | Number of years that new capacity of a technology operates. |
| `OperationalLifeStorage` | `REGION`, `STORAGE` | `storage_lifetime` | years | 0 | Number of years that new storage capacity operates. |
| `OperationalLifeTrade` | `REGION`, `_REGION`, `FUEL`, `YEAR` | `transport_lifetime` | years | 1 | Number of years that new transport capacity on a route operates. |
| `OutputActivityRatio` | `REGION`, `TECHNOLOGY`, `FUEL`, `MODE_OF_OPERATION`, `YEAR` | `output_activity_ratio` | rate | 0 | Quantity of a fuel that a technology puts out for each unit of its activity in a mode. |
| `RegionGroupREMinProductionTarget` | `REGIONGROUP`, `YEAR` | `region_group_generation_fraction_requirement` | fraction | none | Lowest share of the tagged fuel production that renewable technologies must give in a region group. |
| `RegionGroupTagRegion` | `REGIONGROUP`, `REGION`, `YEAR` | `region_group_tag_region` | flag | none | 1 when a region is a member of a region group in a year, otherwise 0. |
| `REMinProductionTarget` | `REGION`, `YEAR` | `generation_fraction_requirement` | fraction | 0 | Lowest share of the tagged fuel production that renewable technologies must give. |
| `ReserveMargin` | `REGION`, `YEAR` | `reserve_margin` | rate | 1 | Ratio of the tagged capacity to the tagged peak demand that a region must hold. |
| `ReserveMarginTagFuel` | `REGION`, `FUEL`, `YEAR` | `reserve_margin_tag_fuel` | flag | 0 | 1 when the demand for a fuel needs the reserve margin, otherwise 0. |
| `ReserveMarginTagTechnology` | `REGION`, `TECHNOLOGY`, `YEAR` | `reserve_margin_tag_technology` | fraction | 0 | Share of the capacity of a technology that counts toward the reserve margin. |
| `ResidualCapacity` | `REGION`, `TECHNOLOGY`, `YEAR` | `residual_capacity` | capacity | 0 | Capacity that exists before the model period and remains in a year. |
| `ResidualStorageCapacity` | `REGION`, `STORAGE`, `YEAR` | `residual_storage_capacity` | activity | 999 | Storage capacity that exists before the model period and remains in a year. |
| `ResidualTradeCapacity` | `REGION`, `_REGION`, `FUEL`, `YEAR` | `residual_transport_capacity` | capacity | 0 | Transport capacity from start_region to end_region that exists before the model period. |
| `RETagFuel` | `REGION`, `FUEL`, `YEAR` | `renewable_tag_fuel` | flag | 0 | 1 when the production of a fuel counts toward the renewable target, otherwise 0. |
| `RETagTechnology` | `REGION`, `TECHNOLOGY`, `YEAR` | `renewable_tag_technology` | flag | 0 | 1 when the production of a technology counts as renewable, otherwise 0. |
| `SpecifiedAnnualDemand` | `REGION`, `FUEL`, `YEAR` | `specified_annual_demand` | activity | 0 | Annual demand for a fuel that the demand profile spreads over the timeslices. |
| `SpecifiedDemandProfile` | `REGION`, `FUEL`, `TIMESLICE`, `YEAR` | `specified_demand_profile` | fraction | 0 | Share of the specified annual demand for a fuel that falls in one timeslice. |
| `StorageBalanceDay` | `REGION`, `STORAGE` | `storage_balance_day` | flag | 0 | 1 when the charge of a storage must equal its discharge over each day, otherwise 0. |
| `StorageBalanceSeason` | `REGION`, `STORAGE` | `storage_balance_season` | flag | 0 | 1 when the charge of a storage must equal its discharge over each season, otherwise 0. |
| `StorageBalanceYear` | `REGION`, `STORAGE` | `storage_balance_year` | flag | 0 | 1 when the charge of a storage must equal its discharge over each year, otherwise 0. |
| `StorageLevelStart` | `REGION`, `STORAGE` | `storage_level_start` | activity | 0 | Energy in a storage at the start of the model period. |
| `StorageMaxChargeRate` | `REGION`, `STORAGE` | `storage_max_charge_rate` | rate | 0 | Highest rate at which a storage can charge. |
| `StorageMaxDischargeRate` | `REGION`, `STORAGE` | `storage_max_discharge_rate` | rate | 0 | Highest rate at which a storage can discharge. |
| `StorageMaxHours` | `REGION`, `STORAGE` | `duration_limits_max` | hours | none | Highest number of hours for which a storage can charge or discharge in one timeslice. |
| `TechnologyActivityByModeLowerLimit` | `REGION`, `TECHNOLOGY`, `MODE_OF_OPERATION`, `YEAR` | `technology_activity_by_mode_lower_limit` | activity | 0 | Lowest activity of a technology in one mode in a year. |
| `TechnologyActivityByModeUpperLimit` | `REGION`, `TECHNOLOGY`, `MODE_OF_OPERATION`, `YEAR` | `technology_activity_by_mode_upper_limit` | activity | 0 | Highest activity of a technology in one mode in a year. |
| `TechnologyActivityDecreaseByModeLimit` | `REGION`, `TECHNOLOGY`, `MODE_OF_OPERATION`, `YEAR` | `technology_activity_decrease_by_mode_limit` | rate | 0 | Highest decrease of the activity of a technology in one mode from one year to the next. |
| `TechnologyFromStorage` | `REGION`, `TECHNOLOGY`, `STORAGE`, `MODE_OF_OPERATION` | `technology_from_storage` | flag | 0 | 1 when a technology discharges a storage in a mode, otherwise 0. |
| `TechnologyMaxProductionTarget` | `REGION`, `TECHNOLOGY`, `FUEL`, `YEAR` | `technology_max_production_target` | fraction | none | Highest share of the production of a fuel in a year that one technology can give. |
| `TechnologyMinProductionTarget` | `REGION`, `TECHNOLOGY`, `FUEL`, `YEAR` | `technology_min_production_target` | fraction | none | Lowest share of the production of a fuel in a year that one technology must give. |
| `TechnologyToStorage` | `REGION`, `TECHNOLOGY`, `STORAGE`, `MODE_OF_OPERATION` | `technology_to_storage` | flag | 0 | 1 when a technology charges a storage in a mode, otherwise 0. |
| `TotalAnnualMaxCapacity` | `REGION`, `TECHNOLOGY`, `YEAR` | `capacity_limits_max` | capacity | -1 | Highest total capacity of a technology in a year, where -1 means no limit. |
| `TotalAnnualMaxCapacityInvestment` | `REGION`, `TECHNOLOGY`, `YEAR` | `total_annual_max_capacity_investment` | capacity | -1 | Highest new capacity of a technology in a year, where -1 means no limit. |
| `TotalAnnualMaxTradeInvestment` | `REGION`, `_REGION`, `FUEL`, `YEAR` | `total_annual_max_transport_investment` | capacity | none | Highest new transport capacity on the route from start_region to end_region in a year. |
| `TotalAnnualMinCapacity` | `REGION`, `TECHNOLOGY`, `YEAR` | `capacity_limits_min` | capacity | 0 | Lowest total capacity of a technology in a year. |
| `TotalAnnualMinCapacityFactor` | `REGION`, `TECHNOLOGY`, `YEAR` | `total_annual_min_capacity_factor` | fraction | none | Lowest annual activity of a technology, as a share of its full use of its capacity. |
| `TotalAnnualMinCapacityFactorTrade` | `REGION`, `_REGION`, `FUEL`, `YEAR` | `transport_total_annual_min_capacity_factor` | fraction | none | Lowest share of the year in which the route from start_region to end_region must operate. |
| `TotalAnnualMinCapacityInvestment` | `REGION`, `TECHNOLOGY`, `YEAR` | `total_annual_min_capacity_investment` | capacity | 0 | Lowest new capacity of a technology in a year. |
| `TotalTechnologyAnnualActivityLowerLimit` | `REGION`, `TECHNOLOGY`, `YEAR` | `total_technology_annual_activity_lower_limit` | activity | 0 | Lowest activity of a technology in a year. |
| `TotalTechnologyAnnualActivityUpperLimit` | `REGION`, `TECHNOLOGY`, `YEAR` | `total_technology_annual_activity_upper_limit` | activity | -1 | Highest activity of a technology in a year, where -1 means no limit. |
| `TotalTechnologyModelPeriodActivityLowerLimit` | `REGION`, `TECHNOLOGY` | `total_technology_model_period_activity_lower_limit` | activity | 0 | Lowest activity of a technology over the model period. |
| `TotalTechnologyModelPeriodActivityUpperLimit` | `REGION`, `TECHNOLOGY` | `total_technology_model_period_activity_upper_limit` | activity | -1 | Highest activity of a technology over the model period, where -1 means no limit. |
| `TotalTradeAnnualActivityLowerLimit` | `REGION`, `_REGION`, `FUEL`, `YEAR` | `total_transport_annual_activity_lower_limit` | activity | none | Lowest quantity of a fuel that leaves start_region for end_region in a year. |
| `TotalTradeAnnualActivityUpperLimit` | `REGION`, `_REGION`, `FUEL`, `YEAR` | `total_transport_annual_activity_upper_limit` | activity | none | Highest quantity of a fuel that leaves start_region for end_region in a year. |
| `TradeCapacityToActivityUnit` | `REGION`, `_REGION`, `FUEL` | `transport_capacity_to_activity_unit` | activity per capacity | 1 | Quantity of a fuel that one unit of transport capacity moves in a whole year. |
| `TradeLossBetweenRegions` | `REGION`, `_REGION`, `FUEL`, `YEAR` | `line_loss` | fraction | 0 | Share of a fuel lost in transport on the route from start_region to end_region. |
| `TradeRoute` | `REGION`, `_REGION`, `FUEL`, `YEAR` | `transport_route` | flag | 0 | 1 when a fuel can move from start_region to end_region, otherwise 0. |
| `VariableCost` | `REGION`, `TECHNOLOGY`, `MODE_OF_OPERATION`, `YEAR` | `variable_operation_cost` | currency per activity | 0 | Cost of one unit of activity of a technology in a mode. |
| `YearSplit` | `TIMESLICE`, `YEAR` | `year_split` | fraction | 0 | Share of the year that one timeslice covers. |

You cannot add a parameter that this table does not have. A table of your model that has no
canonical parameter stays an extension table.

## What tz-oss-interop does not know

The files of an OSeMOSYS model do not state these facts. Only your mappings file can give them.

| Fact | Part of the mappings file | Lesson |
| --- | --- | --- |
| The units of your values | `units:`, with the fields `capacity`, `energy`, `currency`, `currency_year` and `emissions` | [2](osemosys-mappings.md#lesson-2-state-the-units) |
| Which fuel is electricity | A `fuels:` row in `objects:`, with `carrier: electricity` | [11](osemosys-mappings.md#lesson-11-mark-the-electricity-fuel) |
| The category of each technology | A `technologies:` row in `objects:`, with `category` | [12](osemosys-mappings.md#lesson-12-name-the-type-of-each-technology) |

**Warning:** mark each electricity fuel of your model with `carrier: electricity`. Without it,
the kind of each technology can be wrong, and no warning tells you.

## What tz-oss-interop infers

tz-oss-interop finds these facts from other data in your model. A row in `objects:` can give a
different value.

| Fact | Rules | When the rules do not fit |
| --- | --- | --- |
| The kind of each technology | [How tz-oss-interop infers a kind](osemosys-mappings.md#how-tz-oss-interop-infers-a-kind) | [Lesson 13](osemosys-mappings.md#lesson-13-give-a-kind-that-tz-oss-interop-cannot-infer) |
| The location of each technology, fuel, storage and region | [How tz-oss-interop infers a location](osemosys-mappings.md#how-tz-oss-interop-infers-a-location) | [Lesson 14](osemosys-mappings.md#lesson-14-read-a-country-from-a-fuel-name) |
