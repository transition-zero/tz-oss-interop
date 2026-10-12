# The canonical OSeMOSYS stage takes Sienna's nomenclature

This spec changes the names in `2026-10-08-osemosys-canonical-staging-design.md`. The
structure, the rules and the behaviour of that design stay as they are.

## The problem

The canonical stage uses the OSeMOSYS names: `CapitalCost`, `REGION`, `MODE_OF_OPERATION`,
`VALUE`. The next translation reads the canonical stage and writes Sienna. Sienna uses
different words for some of the same things, and a different naming convention. So each
later translation rule must carry two vocabularies.

The user asked for the canonical stage to use Sienna's nomenclature. The user asked for
the change to run unattended, so this spec records each decision that the user did not
see.

## The words

- **Sienna's nomenclature** is the vocabulary of SiennaSchemas, the JSON schemas of the
  Sienna data model. This spec uses SiennaSchemas commit `9d58d29`. The `Investments`
  domain is the main source, because OSeMOSYS is a model of capacity investment.
- **Sienna's naming convention** is snake_case for a field name, and PascalCase for a
  type name.
- **An OSeMOSYS name** is the name that OSeMOSYS v1.0.1, tz-osemosys or MUIO gives a set
  or a parameter.

## The design

### The rules for a canonical name

1. Every canonical name follows Sienna's naming convention: snake_case for a set, a
   parameter, a column and a metadata field.
2. If SiennaSchemas has a field for the same quantity in the same sense, the canonical
   name is that field name. A nested Sienna field gives its leaf name, for example
   `capital_costs.capital_cost` gives `capital_cost`.
3. If SiennaSchemas has no such field, the canonical name is the OSeMOSYS name in
   snake_case. An abbreviation is written out: `RE` becomes `renewable`, and `Idv`
   becomes `technology`.
4. One concept takes one word. SiennaSchemas calls a link between two regions a
   transport technology, so every OSeMOSYS trade parameter takes the word `transport`.
5. A name that is the same quantity but a different encoding does not take the Sienna
   name. One example: Sienna's `capacity_reserve_fraction` is a fraction above the peak,
   but OSeMOSYS `ReserveMargin` is a ratio to the demand, such as 1.2.
6. A name that holds a unit does not take the Sienna name. One example: Sienna's
   `max_mtons` states its unit, but a model can state an emission limit in any unit.

The raw stage does not change. It keeps the model's own names, because the source only
removes the file format.

### The sets

| OSeMOSYS name | Canonical name | Source of the name |
| --- | --- | --- |
| `REGION` | `region` | `region` on each Sienna investment technology |
| `_REGION` (the second region of a pair) | `end_region` | `AggregateTransportTechnology.end_region` |
| `TECHNOLOGY` | `technology` | Sienna's investment types end in `Technology` |
| `FUEL` | `fuel` | `SupplyTechnology.fuel` |
| `EMISSION` | `pollutant` | `EmissionsData.pollutant` |
| `MODE_OF_OPERATION` | `operating_mode` | `HydroPumpTurbine.operating_mode` |
| `STORAGE` | `storage` | `StorageTechnology` |
| `YEAR` | `year` | snake_case (Sienna has `target_year`, `base_year`) |
| `TIMESLICE` | `timeslice` | snake_case |
| `SEASON` | `season` | snake_case |
| `DAYTYPE` | `day_type` | snake_case |
| `DAILYTIMEBRACKET` | `daily_time_bracket` | snake_case |
| `REGIONGROUP` | `region_group` | snake_case |

**A pair of regions.** A key that holds two regions names them `start_region` and
`end_region`, as `AggregateTransportTechnology` does. Both columns refer to the `region`
set. The schema states this as a role for each column:

```yaml
transport_capital_cost:
  key: [start_region, end_region, fuel, year]
  roles: {start_region: region, end_region: region}
  osemosys_name: CapitalCostTrade
  osemosys_key: [REGION, _REGION, FUEL, YEAR]
```

### The value column

`VALUE` becomes `value` in every canonical table and every extension table.

### The parameters

Twelve parameters take a SiennaSchemas name:

| OSeMOSYS name | Canonical name | SiennaSchemas field |
| --- | --- | --- |
| `CapitalCost` | `capital_cost` | `SupplyTechnology.capital_costs.capital_cost` |
| `CapitalCostStorage` | `energy_capital_cost` | `StorageTechnology.capital_costs.energy_capital_cost` |
| `VariableCost` | `variable_operation_cost` | `ThermalGenerationCost.variable_operation_cost` |
| `OperationalLife` | `lifetime` | `SupplyTechnology.lifetime` |
| `CapacityOfOneTechnologyUnit` | `unit_size` | `SupplyTechnology.unit_size` |
| `TotalAnnualMaxCapacity` | `capacity_limits_max` | `SupplyTechnology.capacity_limits.max` |
| `TotalAnnualMinCapacity` | `capacity_limits_min` | `SupplyTechnology.capacity_limits.min` |
| `StorageMaxHours` | `duration_limits_max` | `StorageTechnology.duration_limits.max` |
| `TradeLossBetweenRegions` | `line_loss` | `AggregateTransportTechnology.line_loss` |
| `DiscountRate` | `discount_rate` | `PortfolioFinancialData.discount_rate` |
| `EmissionActivityRatio` | `emission_rate` | `EmissionsData.emission_rate` |
| `REMinProductionTarget` | `generation_fraction_requirement` | `EnergyShareRequirements.generation_fraction_requirement` |

Every canonical parameter keeps the model's own unit, not the Sienna unit. For example,
`duration_limits_max` holds hours, and Sienna's `duration_limits` holds minutes. The
`units:` part of the mappings file and the metadata state the unit, as before.

`CapitalCost` (a nested Sienna name) gives `capital_cost`, by rule 2. Two nested Sienna
names keep their parent field, because the leaf alone is not clear: `capacity_limits_max`
and `duration_limits_max`.

Four parameters keep a prefix, so that one name means one table. Each prefix follows
rule 4:

| OSeMOSYS name | Canonical name |
| --- | --- |
| `OperationalLifeStorage` | `storage_lifetime` |
| `OperationalLifeTrade` | `transport_lifetime` |
| `CapitalCostTrade` | `transport_capital_cost` |
| `DiscountRateStorage` | `storage_discount_rate` |

These parameters look like a Sienna field but do not take its name, for the reason given:

| OSeMOSYS name | Canonical name | Reason |
| --- | --- | --- |
| `FixedCost` | `fixed_cost` | Sienna's `fixed` is a cost per hour online, not per capacity per year |
| `ReserveMargin` | `reserve_margin` | Rule 5 |
| `AnnualEmissionLimit` | `annual_emission_limit` | Rule 6 |
| `EmissionsPenalty` | `emission_penalty` | Rule 6: Sienna's `tax_dollars_per_ton` states a unit |
| `AvailabilityFactor` | `availability_factor` | Sienna's `outage_factor` is the complement, in two parts |
| `ResidualCapacity` | `residual_capacity` | Sienna has no number for existing capacity, only a list of devices |

Every other parameter takes its OSeMOSYS name in snake_case. The trade family takes
`transport` in place of `trade`. Examples:

| OSeMOSYS name | Canonical name |
| --- | --- |
| `DiscountRateIdv` | `technology_discount_rate` |
| `TradeRoute` | `transport_route` |
| `ResidualTradeCapacity` | `residual_transport_capacity` |
| `TotalAnnualMaxTradeInvestment` | `total_annual_max_transport_investment` |
| `TradeCapacityToActivityUnit` | `transport_capacity_to_activity_unit` |
| `DiscountRateTrade` | `transport_discount_rate` |
| `AvailabilityFactorTrade` | `transport_availability_factor` |
| `TotalAnnualMinCapacityFactorTrade` | `transport_total_annual_min_capacity_factor` |
| `TotalTradeAnnualActivityUpperLimit` | `total_transport_annual_activity_upper_limit` |
| `TotalTradeAnnualActivityLowerLimit` | `total_transport_annual_activity_lower_limit` |
| `RETagTechnology` | `renewable_tag_technology` |
| `RETagFuel` | `renewable_tag_fuel` |
| `RegionGroupREMinProductionTarget` | `region_group_generation_fraction_requirement` |
| `Conversionls` | `timeslice_in_season` |
| `Conversionld` | `timeslice_in_day_type` |
| `Conversionlh` | `timeslice_in_daily_time_bracket` |
| `YearSplit` | `year_split` |
| `InputActivityRatio` | `input_activity_ratio` |
| `TotalTechnologyAnnualActivityUpperLimit` | `total_technology_annual_activity_upper_limit` |

A region-group twin of a parameter takes the Sienna name of that parameter with the prefix `region_group_`.

The three `Conversionl*` names follow the field names of tz-osemosys, because `ls`, `ld`
and `lh` are abbreviations.

The schema file holds the full table: each entry has its canonical name, its OSeMOSYS
name and its OSeMOSYS key.

### The automatic match

The automatic match compares the raw name and the raw key with `osemosys_name` and
`osemosys_key`. It then renames the columns by their position in the two keys. The
automatic match of a set compares the raw set name with the set's `osemosys_name`.

### The columns of a raw table that a row maps

Before the operations of a `parameters:` row, the engine renames each column that names a
raw set to the canonical name of that set. `_REGION` becomes `end_region`. Then, if the
canonical key holds `start_region`, the column `region` becomes `start_region`. A row's
`rename_columns`, `repeat_for_all`, `columns_from_name` and `remove_column` use canonical
names.

### Extension tables

An extension table keeps its own name. Its columns take the canonical set names, and
`VALUE` becomes `value`, so the whole canonical stage uses one vocabulary.

### The absent-member rule

The rule reads a column's role. `start_region` and `end_region` are checked against the
`region` set.

### The annotations

| Before | After | Reason |
| --- | --- | --- |
| `kind: generator` | `kind: SupplyTechnology` | the Sienna type for a generating technology |
| `kind: storage` | `kind: StorageTechnology` | the Sienna type |
| `kind: link` | `kind: AggregateTransportTechnology` | the Sienna type for a link between regions |
| `kind: supply` | `kind: fuel_supply` | no Sienna type, and "supply" would read as `SupplyTechnology` |
| `kind: export` | `kind: export` | no Sienna type |
| `kind: conversion` | `kind: conversion` | no Sienna type |

A `kind` value is a Sienna type name exactly when Sienna has that type. The annotation
tables take the canonical set names: `annotations/technology.parquet`, with the columns
`region`, `technology`, `kind`, `category` and `location`. `location`, `category` and
`carrier` keep their names, because no Sienna field has the same meaning.

### The user mappings file

The structure does not change. Every canonical name in the file changes: a `canonical:`
value, a `sets:` target, the columns in the operations, and the `kind` values. The file
does not accept the old names.

### Paths and keys

The canonical paths and the `State` keys use the canonical names, for example
`canonical/parameters/capital_cost.parquet` and `"parameter/capital_cost"`.

## What this does not do

- It does not change the raw stage, the sources' input contracts or the TZ field table.
- It does not convert any unit.
- It does not accept the old canonical names. Nothing outside this branch reads them.

## Size

| Part | Time for a coding agent |
| --- | --- |
| The schema file, the schema model, the constants, the automatic match, the renames, the roles, the paths, and every scenario | about 2 hours |
| The annotation `kind` values and their scenarios | about 30 minutes |
| The developer document | about 30 minutes |
