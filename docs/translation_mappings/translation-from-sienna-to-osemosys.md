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
| `sienna_to_osemosys_map_components` | Builds the frame, the buses, the calendar and the demands. |
| `sienna_to_osemosys_relate_components` | Derives each set that only a parameter key names, and the default of each parameter. |
| `osemosys_canonical_build_destination_stage` | Turns each `default_from` into a number. |
| `emit_osemosys_csv` | Writes the configuration, the CSV files and the mappings file. |

#### Who writes a set

A set whose members a Sienna component states directly is written by the step that reads that
component. A set whose members exist only as the key of a parameter is derived from the
parameter tables, so no such set holds a member that no parameter table names.

| Set | Written by | From |
| --- | --- | --- |
| `REGION` (`region`) | the bus group | The part of the name of each bus before the fuel |
| `FUEL` (`fuel`) | the bus group | The part of the name of each bus after the region |
| `YEAR` (`year`) | `sienna_to_osemosys_relate_components` | The `year` column of each parameter table |
| `TIMESLICE` (`timeslice`) | `sienna_to_osemosys_relate_components` | The `timeslice` column of each parameter table |
| `SEASON` (`season`) | `sienna_to_osemosys_relate_components` | The `season` column of each parameter table |
| `DAYTYPE` (`day_type`) | `sienna_to_osemosys_relate_components` | The `day_type` column of each parameter table |
| `DAILYTIMEBRACKET` (`daily_time_bracket`) | `sienna_to_osemosys_relate_components` | The `daily_time_bracket` column of each parameter table |

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

Not written yet.

### The storages

Not written yet.

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

**A load record whose companion parquet states hours that no Sienna series states.** An
invented calendar has one timeslice for each distinct snapshot of the first staged Sienna
series. A `load` record whose companion parquet states another set of snapshots therefore
reaches the timeslices of the hours that the two have in common, and no others.
