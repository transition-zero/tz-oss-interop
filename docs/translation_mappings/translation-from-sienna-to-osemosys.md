# Translation from Sienna to OSeMOSYS

This document tells you what each part of a Sienna system becomes in the OSeMOSYS model that
tz-oss-interop writes. It gives the source of each field. It is the authoritative mapping for
the Sienna to OSeMOSYS leg, so read it before you decide a field, a default or a scope
question.

> **Scope:** the leg writes a one year dispatch model as an otoole CSV model. It writes no
> capacity expansion model, and it reads no Sienna Investments `portfolio.json`. It writes no
> TZ-format `model.json`. The leg reads a SiennaSchemas 0.2 system, its time-series sidecar and
> an optional `extensions.json` sidecar.

## The pipelines

The command of tz-oss-interop is `interop`. Three pipelines write an otoole CSV model:

| Pipeline | Reads | Writes |
| --- | --- | --- |
| `osemosys-csv-to-osemosys-csv` | an otoole model: a configuration YAML file and a directory of CSV files | the same three files below |
| `tz-osemosys-to-osemosys-csv` | a TZ-format `model.json` file | the same three files below |
| `sienna-to-osemosys-csv` | `system.json`, its time-series sidecar and an optional `extensions.json` | the same three files below |

Each one writes three things:

- `config.yaml`, the otoole configuration that declares each set and each parameter of the
  model.
- a directory of CSV files, one for each set, one for each parameter and one for each extension
  table.
- a mappings file, which states the units of the written values, so a run back over the model
  reads the same numbers.

Every pipeline goes through the canonical OSeMOSYS stage. The canonical stage is one fixed form
of an OSeMOSYS model, which
[The canonical OSeMOSYS stage](../developer_documentation/osemosys-canonical-format.md)
describes. The two format conversion pipelines take a staged model straight across. The Sienna
pipeline builds the canonical tables from the components of the system.

The format conversion pipelines run these nodes, in this order:

| Node | What it does |
| --- | --- |
| `stage_osemosys_csv` or `stage_tz_osemosys_json` | Writes the canonical stage. |
| `osemosys_canonical_build_destination_stage` | Builds the canonical tables that the sink writes, and turns each `default_from` into a number. |
| `emit_osemosys_csv` | Writes the configuration, the CSV files and the mappings file. |

## What the written model states

### The file of each table

A set takes the `osemosys_name` of the canonical schema, so the canonical set `technology`
becomes `TECHNOLOGY.csv`. A parameter takes its own `osemosys_name` and its own column order, so
the canonical parameter `capital_cost` becomes `CapitalCost.csv` with the columns `REGION`,
`TECHNOLOGY`, `YEAR` and `VALUE`. An extension table keeps the raw name and the raw columns that
it came in under, because no canonical parameter claims it. The written model does not reproduce
a publisher's own `short_name` values, its column order or its per country tables.

One raw column name does not come back. The canonical stage renames each column of an extension
table to the canonical name of the set that it matched, and it keeps no record of the raw
spelling. So a raw column that is already spelled as a canonical name, such as a column named
`region` rather than `REGION`, comes back under the OSeMOSYS name of that set.

### The configuration

The configuration states `type`, `dtype` and, for a parameter, `indices` and `default`. `dtype`
is `float` for a parameter and `str` for a set. The default of a parameter is the number of the
`metadata/defaults` table of the canonical stage, which is the default that the model declared,
or the default of the canonical schema where the model declared none. A parameter whose schema
default comes from another parameter takes the number that the named parameter defaults to,
because a configuration states one number for a default.

### The parameter set

The canonical schema holds 82 parameters, and each one states its origin. The written model
declares the 54 whose origin is OSeMOSYS v1.0.1, so a stock OSeMOSYS v1.0.1 model file accepts
it. GNU MathProg refuses a datafile that sets a parameter that its model file does not declare.
Set the sink parameter `wants_every_parameter` to write the rest, which a tz-osemosys model file
or an OSeMOSYS MUIO model file declares. The run warns and names each parameter that it leaves
out, with its origin.

### The units

The written model states the units of the `metadata/units` table of the canonical stage, and the
mappings file beside the model states the same units. A format conversion run therefore writes
the units of the model that it read.

## From a Sienna system

This section holds the field-level mapping of the Sienna leg. The sub-issues of the Sienna to
OSeMOSYS epic fill it in, one component group at a time.

### The frame, the calendar and the buses

These three groups run in `sienna_to_osemosys_map_components`, and
`sienna_to_osemosys_relate_components` then derives the sets. The Sienna pipeline runs these
nodes, in this order:

| Node | What it does |
| --- | --- |
| `stage_sienna_system_json` | Stages the system, its time-series sidecar and its optional `extensions.json`. |
| `sienna_to_osemosys_map_components` | Builds the frame, the buses, the calendar, the demands, the generators, the storages and the reservoirs. |
| `sienna_to_osemosys_relate_components` | Derives each set that only a parameter key names, and the default of each parameter. |
| `osemosys_canonical_build_destination_stage` | Turns each `default_from` into a number. |
| `emit_osemosys_csv` | Writes the configuration, the CSV files and the mappings file. |

#### Who writes a set

A set whose members a Sienna component states directly is written by the step that reads that
component. A set whose members exist only as the key of a parameter is derived from the
parameter tables, so no such set holds a member that no parameter table names.

A parameter table can also name a member of a set that a component step wrote. A fuel that a
plant burns and that no bus balances is a member of `FUEL` that no bus states. So a set that a
component step wrote keeps its own members and gains each member that a parameter table names,
and `decisions.md` records the count that it gained.

| Set | Written by | From |
| --- | --- | --- |
| `REGION` (`region`) | the bus group | The part of the name of each bus before the fuel |
| `FUEL` (`fuel`) | the bus group | The part of the name of each bus after the region |
| `YEAR` (`year`) | `sienna_to_osemosys_relate_components` | The `year` column of each parameter table |
| `TIMESLICE` (`timeslice`) | `sienna_to_osemosys_relate_components` | The `timeslice` column of each parameter table |
| `SEASON` (`season`) | `sienna_to_osemosys_relate_components` | The `season` column of each parameter table |
| `DAYTYPE` (`day_type`) | `sienna_to_osemosys_relate_components` | The `day_type` column of each parameter table |
| `DAILYTIMEBRACKET` (`daily_time_bracket`) | `sienna_to_osemosys_relate_components` | The `daily_time_bracket` column of each parameter table |
| `TECHNOLOGY` (`technology`) | `sienna_to_osemosys_relate_components` | The `technology` column of each parameter table |
| `MODE_OF_OPERATION` (`operating_mode`) | `sienna_to_osemosys_relate_components` | The `operating_mode` column of each parameter table |
| `STORAGE` (`storage`) | `sienna_to_osemosys_relate_components` | The `storage` column of each parameter table |

#### A bus → one region and one fuel

A bus is named `<region>/<fuel>`, because each fuel balances in its region. So one bus states
one member of the `REGION` set and one member of the `FUEL` set.

| The bus | Region | Fuel |
| --- | --- | --- |
| A `bus` record that states a `location`, whose name starts with that location | The `location` of the record | The rest of the name |
| A name that holds a `/` | The part before the last `/` | The part after the last `/` |
| A name that holds no `/` | The whole name | `electricity` |

The third row is what lets a system from PLEXOS or from PyPSA reach OSeMOSYS. Such a system
names a bus for the node alone, so each bus becomes one region that balances electricity and no
two buses merge into one balance. The `Area` of the bus reaches no OSeMOSYS set.

`decisions.md` records the region and the fuel of each bus, with the rule that gave them.

#### The years of the model

The model holds the years that the `ByYear` fields of `extensions.json` name, which is every
year that a record keys a value by. A record that holds a list of further records, such as the
operating modes of a technology, keys years of its own, so the walk goes into it.

Where no field names a year, the model holds one year:

1. the year of the `first_timestamp` of the earliest `representative_period` record;
2. the year of the first snapshot of the series;
3. the year `1`, where the system states neither. `decisions.md` records it.

#### The calendar

One timeslice covers one hour of one representative period. The record states the first hour,
the length, the weight, the season, the day type and `DaysInDayType`, and the timeslice is
named `<record name>/<hour of the record>`, counting the hours from 1.

| Parameter | Value | Source |
| --- | --- | --- |
| `YearSplit` (`year_split`) | The `weight` of the record / the 8760 hours of a year, for each timeslice and each year | `representative_period.weight` |
| `DaySplit` (`day_split`) | 1 hour / the 8760 hours of a year, for each daily time bracket and each year | One timeslice covers one hour |
| `DaysInDayType` (`days_in_day_type`) | The `days_in_day_type` of the record, as it stands, for each season, day type and year | `representative_period.days_in_day_type` |
| `Conversionls` (`timeslice_in_season`) | 1 for each timeslice and the season of its record | `representative_period.season` |
| `Conversionld` (`timeslice_in_day_type`) | 1 for each timeslice and the day type of its record | `representative_period.day_type` |
| `Conversionlh` (`timeslice_in_daily_time_bracket`) | 1 for each timeslice and the hour of its record | The hour of the record |

A record that states fewer than one hour, or a weight of zero or less, is left out as
`NOT_MAPPED`, and one warning names three records. Two records of one season and one day type
that disagree on `days_in_day_type` keep the value of the first, and `decisions.md` records the
other as `NOT_MAPPED`.

A season, a day type or a daily time bracket that no record states gives no row, so the written
model declares no file and no set for it.

#### An invented calendar

`extensions.json` is an optional input. A system that states no `representative_period` record
gets one timeslice for each hour of the series, named for the hour and counting from 1. Each
one covers an equal share of the year, so `YearSplit` is 1 / the hours of the series and the
shares still sum to 1. Such a calendar states no season, no day type and no daily time bracket.
`decisions.md` records the whole calendar as a translator default, and one warning names the
hours.

A system that states no series at all gets one timeslice.

#### The units, and the two parameters that the units fix

Every value of a Sienna system is in MW, MWh, dollars or tonnes. So the `metadata/units` table
states `capacity: MW`, `energy: MWh`, `currency: USD` and `emissions: t`, and the mappings file
beside the written model states the same four. A second run over the written model therefore
reads the same numbers.

| Parameter | Value | Source |
| --- | --- | --- |
| `CapacityToActivityUnit` (`capacity_to_activity_unit`) | 8760, as the default of the parameter | The units above: one MW of capacity runs 8760 MWh in a whole year |
| `DiscountRate` (`discount_rate`) | 0.05, as the default of the parameter | The default of the canonical schema, because no Sienna field states a rate for one region |

Each of the two gets a CSV file with no rows, and the configuration states the number as the
default. Every region and every technology then takes that number, which is how an OSeMOSYS
model states a value that holds for the whole model.

### The demands

`sienna_to_osemosys_map_demands` runs in `sienna_to_osemosys_map_components`, after the bus
group and the calendar group, because a demand is keyed by a region, a fuel, a timeslice and a
year.

OSeMOSYS keys a demand by its region and its fuel, so the bus of a load states both. The
Sienna load gives the demand for an electricity fuel. A fuel that is not electricity has no
Sienna component, so its demand comes from a `load` record of the sidecar.

#### The megawatts of each hour

| The load | The megawatts of one hour | The megawatts where it states no series |
| --- | --- | --- |
| A `PowerLoad` or an `InterruptiblePowerLoad` | The `max_active_power` series of the load x its `max_active_power`, because the series is a share of that rating | Its `max_active_power` |
| A `load` record that states a `bus` | The `p_set` column of the companion parquet, which states megawatts as they stand | Its `p_set` |

A `load` record that states no `bus` describes a load that Sienna itself holds, so it is no
demand of its own and the demand group reads nothing from it.

#### A demand → the energy of the year and the share of each timeslice

A timeslice covers one hour, so the energy of one timeslice is the megawatts of its hour times
the hours of the year that the timeslice covers. Those hours are the `weight` of the
representative period of the timeslice, or 8760 / the hours of the series for an invented
calendar. Two loads on one bus state one demand between them, so their megawatts add up in
each timeslice.

| Parameter | Value | Source |
| --- | --- | --- |
| `SpecifiedAnnualDemand` (`specified_annual_demand`) | The sum over the timeslices of the megawatts of each hour x the hours of the year that its timeslice covers, in MWh, for each year of the model | The series of each load of the fuel |
| `SpecifiedDemandProfile` (`specified_demand_profile`) | The energy of one timeslice / the energy of the whole year, for each timeslice and each year | The same series |
| `AccumulatedAnnualDemand` (`accumulated_annual_demand`) | The same sum, for a load named `<fuel>/accumulated` | The series of that load |

The shares of one fuel sum to 1, because each one is that fuel's own energy divided by the sum
of the same numbers. A load named `<fuel>/accumulated` states the demand that the model can
meet at any time of the year, which is how the forward leg names it, so it gives the annual
total and no profile.

The hour of the series that a timeslice covers is the forward leg's reshape read the other
way. The hours of one representative period follow each other from the `first_timestamp` of
that period, so a timeslice of a period states the one hour that it covers. A timeslice of an
invented calendar states none, so it takes the hour at its own position in the series.

A demand holds in each year of the model, because a Sienna load states one series and no value
for one year.

#### What stops a load from reaching a demand

A model's data never stops a translation, so each load below is left out and every other load
still gives its demand. `decisions.md` carries a `COMPONENT_SKIPPED` event for each one, and
one warning names three of them.

| The load | Why it is left out |
| --- | --- |
| A load whose bus is no bus of the system | OSeMOSYS keys a demand by the region and the fuel of its bus, which the system does not state |
| A load that asks for no energy over the timeslices of the year | A demand of no energy spreads over no profile, so a share of it is a division by zero |
| A load whose `power_units` is not `NATURAL_UNITS` | Its megawatts are a share of a base power, so reading them as megawatts would write a number nobody meant |

### The generators and their operating modes

`sienna_to_osemosys_map_generators` runs in `sienna_to_osemosys_map_components`, after the bus
group and the calendar group, because a technology is keyed by a region and its hourly share by
a timeslice.

Each Sienna generator becomes one OSeMOSYS technology in the region of its bus. The
`ThermalStandard`, the `RenewableDispatch`, the `RenewableNonDispatch`, the `HydroDispatch` and
the `HydroTurbine` of the system all become technologies, because each one puts out
electricity.

#### The electricity output ratio is written as 1

The forward leg rated a generator on the electricity that it puts out. It took the
`ResidualCapacity` of the technology, multiplied it by `CapacityToActivityUnit` / 8760 h and by
the electricity `OutputActivityRatio` of the mode that the generator runs, and it divided every
cost, every emission rate, every fuel ratio and every activity limit of the technology by that
same ratio. No Sienna field states the ratio, so this leg cannot recover it.

So the leg writes the electricity `OutputActivityRatio` of the held mode as 1, and every other
value as the quotient that the forward leg left. One megawatt hour of the activity of the
written technology is then one megawatt hour of electricity, and the written model is the input
model with every value of that technology divided by one number. `decisions.md` carries a
`NOT_MAPPED` event for each value that the ratio scaled, and one warning names three
technologies. A technology that no Sienna component holds follows the same rule, with the
output ratio of the fuel that it puts out; "A technology that no Sienna component holds" below
states it.

`CapacityToActivityUnit` is 8760 for the same reason: the units of the written model are MW and
MWh, so one MW of capacity runs the 8760 MWh of a whole year. The frame group writes that
parameter with no rows and the configuration states 8760 as its default, so `ResidualCapacity`
is the base power of the generator in megawatts. The `capacity_to_activity_unit` of a
`generator` record therefore reaches no table.

#### A generator → a technology, a mode and a fleet

| Parameter | Value | Source |
| --- | --- | --- |
| `ResidualCapacity` (`residual_capacity`) | The base power of the generator, in MW, for each year of the model | `base_power` |
| `OutputActivityRatio` (`output_activity_ratio`) | 1, for the electricity fuel of its bus at the held mode | The rule above |
| `InputActivityRatio` (`input_activity_ratio`) | The ratio of each `fuel_buses` entry, at the held mode | `generator.fuel_buses` |
| `OutputActivityRatio` | The ratio of each `output_buses` entry, at the held mode | `generator.output_buses` |
| `InputActivityRatio`, `OutputActivityRatio` | The `input_ratios` and the `output_ratios` of each other mode, for that mode | `generator.operating_modes` |
| `CapacityFactor` (`capacity_factor`) | The share of its fleet that the generator can use in the hour of the timeslice | The series of the generator, or the capacity below |

A `fuel_buses` entry and an `output_buses` entry are each keyed by the bus of the fuel,
`<region>/<fuel>`, and the leg reads the fuel of that bus under the same rule as the bus group.
The row takes the region of the technology, because OSeMOSYS keys an activity ratio by the
region of the technology that states it. An `operating_modes` entry names the fuel itself.

#### The held mode and the other modes

A Sienna generator runs one operating mode and holds the cost, the flows and the emissions of
that mode itself, so the forward leg kept those out of the sidecar. Each other mode of the
technology travels as an `operating_modes` entry in full, and the bounds of every mode travel
there, the held mode included.

So the leg reads the held mode back this way:

1. An entry that states neither `input_ratios` nor `output_ratios` is the held mode, because
   the forward leg removed the flows of the held mode and of no other mode.
2. Where no entry is like that, the held mode takes the first mode name, counting from 1, that
   no entry claims.

The mode names of a model whose operations mode was not `1` therefore change. OSeMOSYS reads a
mode name as a label, so a renamed mode gives the same model.

#### The share of each hour

OSeMOSYS states the share of its capacity that a technology can use in one timeslice as
`CapacityFactor`, and the share of the energy of a year that it can make as
`AvailabilityFactor`. The forward leg multiplied the two into one hourly derate, so this leg
cannot tell them apart. It writes the whole derate as `CapacityFactor` and leaves
`AvailabilityFactor` at its default of 1, because a Sienna availability limits the power of
each hour and not the energy of the year.

A staged series of a generator is a share of one capacity of its own, and which capacity that
is differs by Sienna type:

| Sienna type | The capacity that one value of its series is a share of |
| --- | --- |
| `ThermalStandard` | `active_power_limits.max` |
| `RenewableDispatch`, `RenewableNonDispatch` | `rating` |
| `HydroDispatch`, `HydroTurbine` | `base_power` |

So the share of its fleet that the generator can use in one hour is the value of that hour times
that capacity, over its base power. A generator that states no series can use the same share in
every hour, which is that capacity over its base power.

A share of 1 is the default of `CapacityFactor`, so a generator that can use its whole fleet in
a timeslice gets no row for that timeslice.

#### What a technology costs, what it emits and what bounds its activity

A Sienna generator states what one megawatt hour of its electricity costs, and its record
states what one megawatt of its capacity costs to build and to keep. Every one of these values
already divides by the electricity output ratio, so the leg writes each one as it stands.

| Parameter | Value | Source |
| --- | --- | --- |
| `VariableCost` (`variable_operation_cost`) | The cost of one MWh at the held mode, in $/MWh, in each year of the model | `own_marginal_cost` of the record, else the proportional term of `operation_cost.variable_operation_cost` |
| `VariableCost` | The cost of one MWh at each other mode, in each year | `generator.operating_modes[].variable_cost` |
| `FixedCost` (`fixed_cost`) | The yearly charge on one MW of capacity, in each year | `generator.fom_charge_per_mw_year` |
| `CapitalCost` (`capital_cost`) | What one MW of new capacity costs, in each year | `generator.overnight_cost_per_mw` |
| `OperationalLife` (`lifetime`) | How many years the plant runs | `generator.lifetime_years` |
| `EmissionActivityRatio` (`emission_rate`) | The tonnes of each pollutant for one MWh at the held mode, in each year | `own_emission_rates_t_per_mwh` of the record, else `emission_rates_t_per_mwh` |
| `EmissionActivityRatio` | The same, at each other mode | `generator.operating_modes[].emission_rates` |
| `TotalTechnologyAnnualActivityLowerLimit`, `UpperLimit` | The MWh that the technology must and may make, in each year that the record names | `generator.e_sum_min`, `generator.e_sum_max` |
| `TotalTechnologyModelPeriodActivityLowerLimit`, `UpperLimit` | The same over the whole model period | `generator.e_sum_min_horizon`, `generator.e_sum_max_horizon` |
| `TechnologyActivityByModeUpperLimit`, `LowerLimit` | The MWh that one mode must and may make, in each year that the entry names | `generator.operating_modes[].activity_max`, `activity_min` |
| `TechnologyActivityDecreaseByModeLimit` | The most that the activity of one mode can fall from the year before | `generator.operating_modes[].activity_decrease_max` |

**A plant that draws its fuel from a bus prices neither the fuel nor its emissions.** A Sienna
cost curve holds the price of the fuel and a Sienna emission rate holds what the producer of
that fuel emits, because Sienna prices no fuel of its own. A written model prices the fuel at
the technology that supplies it, so the cost and the rates of such a plant are the `own_` fields
of its record, which hold neither. A generator that burns no fuel from a bus has no `own_` field,
and its cost curve and its rates are its own.

**A value that holds in every year.** A Sienna generator states one cost and no cost for one
year, so a value with no year of its own gives one row for each year of the model.
`decisions.md` carries one event for each value and not one for each year.

**A value that equals the default of its parameter gets no row.** OSeMOSYS reads the default
where a model states no row, so a generator that costs 0 to run writes no `VariableCost` row and
an emission rate of 0 writes no `EmissionActivityRatio` row. A limit of 0 is still written,
because `TotalTechnologyAnnualActivityUpperLimit` defaults to -1 and a limit of 0 states that the
technology may not run.

**Three of these parameters are not core OSeMOSYS v1.0.1.**
`TechnologyActivityByModeUpperLimit`, `TechnologyActivityByModeLowerLimit` and
`TechnologyActivityDecreaseByModeLimit` come from the OSeMOSYS MUIO model v5.7. The leg builds
their tables, and the default run leaves their files out and names each one in a warning, as
"The parameter set" above states. Set the sink parameter `wants_every_parameter` to write them.

**`AvailabilityFactor` takes its default for a Sienna generator.** No Sienna generator states a
limit on the energy of a year of its own, because the forward leg folded that limit into the
hourly derate. "The share of each hour" above states the whole rule. A technology that no
Sienna component holds does state one, and the section below gives it.

#### A technology that no Sienna component holds

Sienna holds electricity only, so a technology that supplies a fuel that is not electricity has
no Sienna component. The forward leg wrote such a technology as a `generator` record of the
sidecar, and this leg reads that record back as one OSeMOSYS technology. A demand for a fuel
that is not electricity then has a producer.

A `generator` record gives a technology of its own under two conditions. It must state a `bus`,
and no Sienna generator may carry its name. The record of a Sienna generator holds the fields
that no Sienna field holds, and it states no `bus`, so it gives no second technology.

| Parameter | Value | Source |
| --- | --- | --- |
| `ResidualCapacity` (`residual_capacity`) | The MW of the fuel that already run, in each year of the model | `generator.p_nom` |
| `OutputActivityRatio` (`output_activity_ratio`) | 1, for the fuel of the bus of the record, at the held mode | The rule below |
| `VariableCost` (`variable_operation_cost`) | What one MWh of the fuel costs, in $/MWh, in each year | `generator.marginal_cost` |
| `AvailabilityFactor` (`availability_factor`) | The share of the energy of a year that the technology can make, in each year | `generator.p_max_pu` |

The region and the fuel of such a technology come from the bus of its record, under the same
rule as the bus group. The record names the bus, so a bus that the bus group placed gives its
region and its fuel, and the name of the bus alone answers a bus that the bus group did not
place.

Every other parameter of the two sections above comes from the same field of the record for
both routes. So the emission rates, the capital cost, the fixed cost, the life, the other modes
and the activity limits of such a technology need no rule of their own.

**The output ratio of such a technology is 1 for the same reason.** The forward leg rated it on
the fuel that it puts out. It multiplied the `p_nom` and the activity limits of the record by
the `OutputActivityRatio` of that fuel, and it divided the cost and the emission rates of the
record by the same ratio. No Sienna field and no record field states the ratio, so this leg
writes the ratio as 1 and every other value as the quotient that the forward leg left.
`decisions.md` carries a `NOT_MAPPED` event against the `p_nom` of the record.

**`AvailabilityFactor` comes back for such a technology and not for a Sienna generator.** The
forward leg wrote the `AvailabilityFactor` of a technology that no Sienna component holds as the
`p_max_pu` of its record, and it folded the `AvailabilityFactor` of a Sienna generator into the
hourly derate of its series. So the two routes answer that parameter differently.

#### What stops a generator from reaching a technology

A model's data never stops a translation, so each generator below is left out and every other
generator still gives its technology. `decisions.md` carries a `COMPONENT_SKIPPED` event for
each one, and one warning names three of them under the Sienna type, or the record kind, that
states them.

| The generator | Why it is left out |
| --- | --- |
| A generator whose `power_units` is not `NATURAL_UNITS` | Its megawatts are a share of a base power, so reading them as megawatts would write a number nobody meant |
| A generator of no base power | OSeMOSYS states the share of a fleet that a technology can use, and a generator of no fleet has no share to state |
| A `generator` record of no `p_nom` | The same reason, because the megawatts of the fuel that already run are the fleet of such a technology |

### The storages

`sienna_to_osemosys_map_storages` runs in `sienna_to_osemosys_map_components`, after the
generator group, because a storage adds two technologies of its own to the same parameter
tables that a generator fills.

A Sienna `EnergyReservoirStorage` holds its energy, its power and its two efficiencies on one
component. OSeMOSYS holds the energy on a member of the `STORAGE` set, and it gives that member
its power through one technology that charges it and one technology that discharges it. So each
Sienna storage becomes one `STORAGE` member and two technologies, in the region of its bus.

#### The name and the mode of each technology

The forward leg kept neither the name nor the mode of the charging technology and of the
discharging technology, so the leg invents both. The charging technology takes the name of the
storage, a `/` and `charge`; the discharging technology takes `discharge` in the same place.
Each one runs one mode, which the leg names 1.

#### Each efficiency is the activity ratio of its own technology

The forward leg merged two OSeMOSYS values into each Sienna efficiency:

- `efficiency.in` is `TechnologyToStorage` / the electricity `InputActivityRatio` of the
  charging technology.
- `efficiency.out` is the electricity `OutputActivityRatio` of the discharging technology /
  `TechnologyFromStorage`.

Neither factor comes back alone, so the leg writes each storage link as 1 and the whole
efficiency as the activity ratio of its technology. One unit of the activity of each technology
is then one megawatt hour of the energy of the storage: the charging technology draws
1 / `efficiency.in` megawatt hours from its bus to store one, and the discharging technology
sends `efficiency.out` megawatt hours to its bus for each one that it draws. A second forward
run over the written model therefore gives the two efficiencies of the input system.

#### A storage → one STORAGE member and two technologies

| Parameter | Value | Source |
| --- | --- | --- |
| `ResidualStorageCapacity` (`residual_storage_capacity`) | The energy that the storage holds, in MWh, for each year of the model | `storage_capacity` in hours x `base_power` |
| `StorageLevelStart` (`storage_level_start`) | The energy in the storage at the start of the model period, in MWh | `initial_storage_capacity_level` x that energy |
| `MinStorageCharge` (`min_storage_charge`) | The lowest level of the storage, as a share of its energy, for each year | `storage_level_limits.min` |
| `TechnologyToStorage` (`technology_to_storage`) | 1, for the charging technology at mode 1 | The rule above |
| `TechnologyFromStorage` (`technology_from_storage`) | 1, for the discharging technology at mode 1 | The rule above |
| `InputActivityRatio` (`input_activity_ratio`) | 1 / `efficiency.in`, for the electricity fuel of its bus at mode 1 | `efficiency.in` |
| `OutputActivityRatio` (`output_activity_ratio`) | `efficiency.out`, for the electricity fuel of its bus at mode 1 | `efficiency.out` |
| `ResidualCapacity` (`residual_capacity`) | The fleet of the charging technology, in MW of the energy of the storage, for each year | `input_active_power_limits.max` x `base_power` x `efficiency.in` |
| `ResidualCapacity` | The fleet of the discharging technology, in the same unit, for each year | `output_active_power_limits.max` x `base_power` / `efficiency.out` |
| `CapitalCostStorage` (`energy_capital_cost`) | What one MWh of new energy costs to build, for each year | `storage.energy_overnight_cost` |
| `OperationalLifeStorage` (`storage_lifetime`) | How many years new energy operates | `storage.lifetime_years` |

Each power limit of a Sienna storage is a share of its base power, so the megawatts of a limit
are the share times the base power. The fleet of a technology is in the unit of its activity,
which is a megawatt hour of the energy of the storage, so the megawatts of the charge limit
multiply by `efficiency.in` and those of the discharge limit divide by `efficiency.out`.

`STORAGE` and `TECHNOLOGY` both take their members from the parameter tables, so the storage
and its two technologies reach their set files with no writer of their own. The `MinStorageCharge`
row of a storage that may empty states 0, which is the default of the parameter, so such a
storage gets no row; "A value that equals the default of its parameter gets no row" holds for
every parameter of this group.

#### A storage with no record

`CapitalCostStorage` and `OperationalLifeStorage` come from the `storage` record of
`extensions.json`, because no Sienna field states either: Sienna prices no build on an
operations model. A system with no record therefore keeps every rating of its storages, and
`decisions.md` carries one `NOT_MAPPED` event for each of the two fields that the record does
not state.

#### What stops a storage from reaching the written model

A model's data never stops a translation, so each storage below is left out and every other
storage still reaches the model. `decisions.md` carries a `COMPONENT_SKIPPED` event for each
one, and one warning names three of them.

| The storage | Why it is left out |
| --- | --- |
| A storage whose `power_units` is not `COMPONENT_BASE` | Its power limits are then already in megawatts, so reading them as shares of its base power would write a number nobody meant |
| A storage of no base power | Its energy and both of its power limits are a share of that base power, so there is nothing to take a share of |
| A storage of no `storage_capacity` | OSeMOSYS states the level of a storage as a share of its energy, so a storage of no energy gives a share that divides by zero |
| A storage whose `efficiency.in` or `efficiency.out` is 0 | Each efficiency becomes the activity ratio of one technology, and an efficiency of 0 gives a ratio that divides by zero |

### The reservoirs

`sienna_to_osemosys_map_reservoirs` runs in `sienna_to_osemosys_map_components`, after the
generator group and the storage group, because a reservoir reads the technology that the
generator group wrote for each of its turbines.

A Sienna `HydroReservoir` holds the energy behind a `HydroTurbine`, and the turbine spends that
energy. OSeMOSYS holds such energy on a member of the `STORAGE` set, and a technology that
draws on that member states a storage link. So each reservoir becomes one `STORAGE` member, and
each turbine that the reservoir feeds gains the link that spends its energy.

#### The turbine stays one technology

The generator group already wrote each `HydroTurbine` as a technology of its own bus, with the
fleet that its base power states and an electricity output ratio of 1. So this group writes no
second technology for a turbine: it joins the `downstream_turbines` of the reservoir to the
table of the generator group, by the integer id that the reservoir names each turbine under,
and writes one `TechnologyFromStorage` row for each pair. The row takes the operating mode that
the generator group read for that turbine.

`TechnologyFromStorage` and the electricity `OutputActivityRatio` of the turbine are both 1, so
one unit of the activity of the turbine draws one megawatt hour from the reservoir and sends
one megawatt hour to its bus. The level of an energy reservoir is already the energy that its
turbines can deliver, so the `efficiency` of the turbine has no part in the link.

#### The inflow gets a charging technology of its own

No Sienna component puts the inflow into a reservoir, so the group writes one technology for
it, named `<reservoir>/inflow`, running mode 1. Its storage link is 1 and its fleet is the
megawatts of the inflow, and it takes in no fuel. One unit of its activity therefore stores one
megawatt hour of the energy of the reservoir, and the inflow bounds the energy that it can
store in each timeslice. The solve can leave that technology idle, which is the spillage of the
reservoir. A reservoir of no inflow gets no such technology.

#### The region of the reservoir

A `HydroReservoir` names no bus, so the bus of a turbine that it feeds is what states the
region of the storage. Every turbine of one reservoir must name the same region, because
OSeMOSYS keys a storage by one region.

#### A reservoir → one STORAGE member and the links that move its energy

| Parameter | Value | Source |
| --- | --- | --- |
| `ResidualStorageCapacity` (`residual_storage_capacity`) | The energy that the reservoir holds, in MWh, for each year of the model | `storage_level_limits.max` |
| `StorageLevelStart` (`storage_level_start`) | The energy in the reservoir at the start of the model period, in MWh | `initial_level` |
| `MinStorageCharge` (`min_storage_charge`) | The lowest level of the reservoir, as a share of its energy, for each year | `storage_level_limits.min` / `storage_level_limits.max` |
| `TechnologyFromStorage` (`technology_from_storage`) | 1, for each turbine of the reservoir at the mode that the generator group read | `downstream_turbines` |
| `TechnologyToStorage` (`technology_to_storage`) | 1, for the inflow technology at mode 1 | `inflow` |
| `ResidualCapacity` (`residual_capacity`) | The fleet of the inflow technology, in MW, for each year | `inflow` |

A reservoir states its levels in megawatt hours and its inflow in megawatts only where its
`level_data_type` is `ENERGY`. `STORAGE` and `TECHNOLOGY` both take their members from the
parameter tables, so the reservoir and its inflow technology reach their set files with no
writer of their own. "A value that equals the default of its parameter gets no row" holds for
every parameter of this group, so a reservoir that may empty writes no `MinStorageCharge` row.

#### What stops a reservoir from reaching the written model

A model's data never stops a translation, so each reservoir below is left out and every other
reservoir still reaches the model. `decisions.md` carries a `COMPONENT_SKIPPED` event for each
one, and one warning names three of them.

| The reservoir | Why it is left out |
| --- | --- |
| A reservoir whose `level_data_type` is not `ENERGY` | A level in cubic metres or in metres of head becomes megawatt hours through the `head_to_volume_factor` of the reservoir and the `conversion_factor` of its turbine, and OSeMOSYS holds neither |
| A reservoir of no `storage_level_limits.max` | OSeMOSYS states the lowest level of a storage as a share of the energy that it holds, so a reservoir of no energy gives a share that divides by zero |
| A reservoir that feeds no `HydroTurbine` that reached a technology | The bus of such a turbine is what states the region of the storage, so the reservoir has no region and nothing that spends its energy |
| A reservoir whose turbines name more than one region | OSeMOSYS keys a storage by one region |

### The lines, the conversions and the trade

Not written yet.

### The emission policies

Not written yet.

## Not translated

The frame, the calendar, the buses and the demands leave these out. A later section adds the
ones that a later component group reads.

| What the Sienna system states | Why it reaches no OSeMOSYS table |
| --- | --- |
| The `Area` and the `LoadZone` of a bus | A bus is one OSeMOSYS region of its own, so neither group of buses has a home. `REGIONGROUP` is the nearest OSeMOSYS set, and no parameter of this group names it. |
| The `base_voltage` and the `bustype` of a bus | OSeMOSYS holds no electrical data. |
| The `value_of_lost_load` of a `bus` record | OSeMOSYS states no unserved energy variable. |
| The timestamps of the series | OSeMOSYS keys a value by its timeslice and not by its hour, so the calendar keeps the hour count and the weight and drops the clock. |
| The `available` of a load | OSeMOSYS states no availability of a demand, so the leg writes the demand of every load. |
| The `active_power`, the `reactive_power`, the `max_reactive_power` and the `base_power` of a load | OSeMOSYS holds no electrical data, and the energy of the year comes from the series and not from one hour of it. |
| The `conformity` of a load | OSeMOSYS has no load conformity concept. |
| The `operation_cost` of an `InterruptiblePowerLoad` | OSeMOSYS states no unserved energy variable, so it prices no demand that the model does not meet. |
| The `carrier`, the `type` and the `sign` of a `load` record | A fuel takes its name from the bus of the load, and OSeMOSYS states no sign of a demand. |
| The `prime_mover_type` and the `fuel` of a generator, and the `carrier` and the `category` of its record | OSeMOSYS states the kind of a technology as an annotation of the canonical stage, and the written otoole model holds no annotation table. |
| The `rating`, the `active_power`, the `reactive_power` and the `power_factor` of a generator | OSeMOSYS holds no electrical data. The rating of a renewable generator is read as the capacity that its series is a share of, and nothing else. |
| The `active_power_limits.min` of a generator | OSeMOSYS states no minimum stable level, which is why the forward leg writes that limit as 0. |
| The `status`, the `time_at_status`, the `ramp_limits` and the `time_limits` of a generator | OSeMOSYS states no unit commitment data. |
| The `available` of a generator | OSeMOSYS states no availability of a technology, so the leg writes the technology of every generator. |
| The `committable`, the `efficiency` and the `p_nom_extendable` of a `generator` record | Each one is a PyPSA field of the round trip. OSeMOSYS states the efficiency of a technology as its activity ratios, and this leg writes a dispatch model with no build. |
| The `fixed`, the `start_up`, the `shut_down` and the `vom_cost` of a generator's `operation_cost` | OSeMOSYS charges a fixed cost on capacity and not on a plant, which `FixedCost` holds, and it states no unit commitment cost. |
| The `unit_size_mw`, the `p_nom_min`, the `p_nom_max`, the `discount_rate`, the `technical_life_years`, the `build_year`, the `retirement_year`, the `max_growth`, the `min_growth`, the `max_growth_rate`, the `min_growth_rate`, the `max_growth_floor`, the `capacity_factor_min`, the `production_share_min` and the `production_share_max` of a `generator` record | Each one bounds or prices new capacity, and this epic writes a dispatch model over the years that the sidecar names. OSeMOSYS holds each of them, so a later epic that writes a capacity expansion model can add them: about 100 lines in this leg. |
| The `marginal_cost_series` of a `generator` record | OSeMOSYS prices a technology by the year and not by the hour. |
| The `operation_cost` of a storage | OSeMOSYS prices the activity of the charging technology and of the discharging technology as a `VariableCost` of each. A later rung can write both from the charge cost and the discharge cost of the `StorageCost`: about 40 lines in this leg. `decisions.md` records neither cost today. |
| The `prime_mover_type`, the `storage_technology_type`, the `rating`, the `active_power`, the `reactive_power`, the `conversion_factor` and the `cycle_limits` of a storage | OSeMOSYS holds no electrical data and no storage technology, and it states the energy of a storage in megawatt hours, so the conversion factor of 1 that the forward leg wrote has no home. |
| The `storage_level_limits.max` and the `storage_target` of a storage | OSeMOSYS holds the highest level of a storage at its capacity and states no end of horizon target, which the forward leg read from `StorageBalanceYear`, `StorageBalanceSeason` and `StorageBalanceDay`. |
| The `duration_max_hours`, the `cyclic_state_of_charge_per_period`, the `cyclic_state_of_charge_per_season`, the `cyclic_state_of_charge_per_day` and the `charge_fom_cost` of a `storage` record | `StorageMaxHours` and the three storage balance flags come from tz-osemosys v0.4.1 and not from core OSeMOSYS v1.0.1, and `FixedCost` charges the capacity of the charging technology. A later rung can write all five: about 60 lines in this leg. |
| The `max_hours`, the `state_of_charge_initial`, the `inflow_mw` and the `inflow_series` of the `storage` record of a hydro generator | The reservoir of a hydro generator reaches an OSeMOSYS storage only where the system holds it as a `HydroReservoir` component. A `storage` record of a hydro generator states the same three values, and this leg reads none of them: about 40 lines in this leg would read the record into the same rows that the reservoir group writes. |
| The `outflow` of a reservoir | OSeMOSYS states no outflow that a storage must release, so the written model holds the energy of the reservoir and not the water that leaves it. `decisions.md` carries one `NOT_MAPPED` event for each reservoir that states a non-zero outflow, and one warning names three of them. |
| The `spillage_limits` and the `evaporative_loss` of a reservoir | OSeMOSYS states neither. The solve can leave the inflow technology idle, which spills the whole inflow, and nothing bounds that spillage or takes a standing loss off the level. |
| The `level_targets` of a reservoir | OSeMOSYS states no end of horizon target for a storage, as it states none for an `EnergyReservoirStorage`. |
| The `available`, the `intake_elevation`, the `head_to_volume_factor` and the `upstream_reservoirs` of a reservoir | OSeMOSYS holds no cascade and no water, so a chain of reservoirs reaches one storage for each reservoir and no flow between them. |
| The `operation_cost` of a reservoir | OSeMOSYS prices the activity of a technology and the capacity of a storage, and it prices neither a level shortage, nor a level surplus, nor spillage. |
| The `efficiency`, the `conversion_factor`, the `outflow_limits`, the `travel_time` and the `powerhouse_elevation` of a `HydroTurbine` | The level of an energy reservoir is already the energy that its turbines can deliver, so the storage link of a turbine is 1 and its efficiency has no part in it. OSeMOSYS holds no water and no travel time. |

## Open questions

**A bus name that holds a `/` and states no fuel.** The leg reads the part of the name after
the last `/` as the fuel. A system whose bus names hold a `/` for another reason, such as a
node named for its area and its node, therefore gives a fuel that the publisher did not mean.
`decisions.md` names the region and the fuel of every bus, so the reading is visible, and a
`bus` record that states a `location` is read from that field instead. A later rung could take
the `Area` of the bus as the region prefix, which is exact for a system that this translator
wrote and no better for any other.

**A `YearSplit` that does not sum to 1.** The forward leg takes the mean weight where the
timeslices of one day disagree, and a day that takes a mean weight makes the sum of
`hours x weight` over the records differ from 8760. The reverse leg writes the weight of the
record as it stands, so the shares of such a model do not sum to 1 and OSeMOSYS reads a year
that is longer or shorter than a year. The leg records no event for this, because the record
alone does not say that a mean was taken.

**The hours of a series that is not hourly.** The leg counts the distinct snapshots of the
first staged series as the hours of the series. A series of another resolution therefore gives
one timeslice for each snapshot and not for each hour.

**An hour of a load's series that the calendar covers with no timeslice.** A timeslice of a
representative period covers the hour that the `first_timestamp` of that period names, so an
hour of the series that no period covers reaches no timeslice and its megawatts reach no
demand. A system that this translator wrote has one hour for each timeslice, so nothing is
lost there. A system whose periods cover part of its series loses the rest of it, and the leg
records no event for that hour, because it records one event for each demand and not one for
each hour. A later rung could report the hours that no period covers, as one event for each
load.

**The electricity output ratio of a technology.** The forward leg divided every value of a
generator by that ratio, and no Sienna field states it, so the leg writes the ratio as 1 and
every other value as the quotient. A second forward run over the written model therefore gives
the same Sienna system, and the numbers of the written model are the publisher's own only where
the ratio was 1. A later rung could relay the ratio through a field of the `generator` record,
which is about 20 lines in each leg and makes the whole technology exact.

**The split of `CapacityFactor` and `AvailabilityFactor`.** The forward leg multiplied the two
into one hourly derate. This leg writes the whole derate as `CapacityFactor`, so a model that
stated both no longer limits the energy of its year with a factor of its own. The hourly limit
of the written model is the hourly limit of the input model, so the dispatch is the same.

**A `HydroTurbine` whose reservoir the system does not hold as a component.** The reservoir
group gives a turbine its energy budget through the `HydroReservoir` that feeds it. A system
that holds the turbine and no reservoir, or that holds the reservoir as a `storage` record of
the sidecar, therefore reaches a technology with its own fleet and its own hourly share and no
energy budget.

**A load record whose companion parquet states hours that no Sienna series states.** An
invented calendar has one timeslice for each distinct snapshot of the first staged Sienna
series. A `load` record whose companion parquet states another set of snapshots therefore
reaches the timeslices of the hours that the two have in common, and no others.
