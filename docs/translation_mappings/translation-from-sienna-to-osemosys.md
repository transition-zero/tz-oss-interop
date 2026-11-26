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

Not written yet.

### The demands

Not written yet.

### The generators and their operating modes

Not written yet.

### The storages

Not written yet.

### The lines, the conversions and the trade

Not written yet.

### The emission policies

Not written yet.

## Not translated

Not written yet.

## Open questions

Not written yet.
