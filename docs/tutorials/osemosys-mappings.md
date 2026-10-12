# OSeMOSYS Mappings Guide

This guide tells you how to write the `osemosys:` part of a mappings file. The mappings file
tells interop how to put your OSeMOSYS model into one fixed form, the canonical stage. You must
know your own model and YAML. You do not need to know the code of interop. The section "The
words" tells you what each term means.

A worked example has three parts:

1. A small raw table from an invented model.
2. The rows of the mappings file.
3. The canonical table that the run writes.

Each example is from a real run. The values are invented.

## The words

These words have one meaning in this guide.

| Word | Meaning |
| --- | --- |
| Model | Your OSeMOSYS model: an otoole configuration file and a directory of CSV files, or a TZ-format model. |
| TZ-format model | The `model.json` file that tz-osemosys writes. |
| Raw set | One set of your model, with the name that your model gives it, for example `TECHNOLOGY` or `UNIT`. |
| Set member | One value in a set, for example the technology `GASCC` or the year `2030`. |
| Raw table | One parameter of your model, with its own name, for example `CapitalCost` or `MaxRampRate`. |
| Index columns | The columns of a raw table that name set members, for example `REGION`, `TECHNOLOGY` and `YEAR`. In an otoole model, the `indices` of the parameter give them. |
| Key | In a message from interop, the index columns of a raw table. For example, the note `matched by name and key` means that the name and the index columns match. |
| `VALUE` | The column of a raw table that holds the number. |
| Canonical schema | The fixed list of sets and parameters that interop knows. Each one has a canonical name, for example `capital_cost`. |
| Canonical set, canonical parameter | A set or a parameter of the canonical schema. |
| Canonical columns | The columns of a canonical parameter, in a fixed order, for example `region, technology, year`. Each canonical table has a `value` column after them. |
| Canonical stage | Your model in the canonical schema: one parquet file for each canonical set and each canonical parameter. |
| Canonical table | One parquet file of the canonical stage. |
| Extension table | A raw table or a raw set that no canonical name receives. The canonical stage keeps it with its own name, so no data is lost. |
| Annotation | A fact about a set member that the model does not state as a parameter, for example that a technology is in the country `AA`. |
| Model reader | The part of interop that reads the files of your model. |
| Engine | The part of interop that reads your mappings file and writes the canonical stage. |
| Table row | One line of values in a table. |
| `parameters:` row, `objects:` row | One item in the `parameters:` list or an `objects:` list of the mappings file. The engine counts these rows from 0, so the first row is "row 0". |

The canonical stage is not a translation to another tool. It is one fixed form of an OSeMOSYS
model. A later translation reads that form.

## What the mappings file does

The engine reads each raw set and each raw table of your model. For each one, it does one of
these things:

- It gives the raw set or raw table a canonical name. The result is a canonical table.
- It keeps the raw set or raw table as an extension table.
- It leaves the raw table out, if a `parameters:` row says `ignore: true`.

The engine gives a canonical name automatically when your model uses the published OSeMOSYS
name and the published index columns. The section "The automatic match" tells you when.
The mappings file holds only the differences between your model and the canonical schema.

The mappings file is a YAML file. Its OSeMOSYS part is under one key, `osemosys:`. That key
holds four parts, and each part is optional:

| Part | What it states |
| --- | --- |
| `units:` | The real units of your model |
| `sets:` | The canonical set of a raw set that has a different name |
| `parameters:` | How a raw table becomes a canonical parameter |
| `objects:` | What each technology, fuel, storage and region is |

A file that holds `osemosys: {}`, or only `{}`, is a valid mappings file. With such a file, the
engine maps what it can automatically, and keeps the rest as extension tables.

The file can hold other keys next to `osemosys:`, for example the `carriers:` list of a PyPSA
translation. The engine reads only `osemosys:`. Inside `osemosys:`, an unknown key stops the run.

You can put the mappings file anywhere in your project directory. This guide uses
`inputs/osemosys_mappings.yaml`.

## Run a pipeline

Two pipelines write the canonical stage of a model to a directory:

| Pipeline | Model that it reads |
| --- | --- |
| `osemosys-csv-to-canonical` | An otoole model: a configuration YAML file and a directory of CSV files |
| `tz-osemosys-to-canonical` | A TZ-format `model.json` file |

### Run the pipeline for an otoole model

You must run interop inside a project directory. The section "Setting up a project" of the
[user tutorial](user-tutorial.md) tells you how to make one.
A run in a directory with no `adapters.yaml` stops with this message:
``adapters.yaml not found at ... Run `interop init <dir>` to scaffold a project.``
Make a project with `interop init` first.

1. Put the otoole configuration file at `inputs/model/config.yaml`.
2. Put the CSV files in `inputs/model/csv/`.
3. Write the mappings file at `inputs/osemosys_mappings.yaml`.
4. Go to the project directory.
5. Run this command:

```bash
INTEROP_LOG_LEVEL=WARNING interop headless_cli --pipeline osemosys-csv-to-canonical \
  --override 'source.config_path=inputs/model/config.yaml' \
  --override 'source.csv_dir=inputs/model/csv' \
  --override 'sink[0].output_dir=outputs/canonical' \
  --user-mappings-path inputs/osemosys_mappings.yaml
```

`INTEROP_LOG_LEVEL=WARNING` shows the warnings on the console. Without it, the console shows
only the errors.

### Run the pipeline for a TZ-format model

1. Put the model at `inputs/model.json`.
2. Write the mappings file at `inputs/osemosys_mappings.yaml`.
3. Go to the project directory.
4. Run this command:

```bash
INTEROP_LOG_LEVEL=WARNING interop headless_cli --pipeline tz-osemosys-to-canonical \
  --override 'source.model_json_path=inputs/model.json' \
  --override 'sink[0].output_dir=outputs/canonical' \
  --user-mappings-path inputs/osemosys_mappings.yaml
```

The TZ-format reader gives each table its OSeMOSYS name, so the tables match automatically.
Usually a mappings file for a TZ-format model needs only `units:` and `objects:`. The section
"`objects:`" shows how to write them.

### What the run writes

The run writes the canonical stage in the `output_dir` that you give:

| Directory | What it holds |
| --- | --- |
| `sets/` | One file for each canonical set that the model has, with one column, `value` |
| `parameters/` | One file for each canonical parameter that a raw table maps to |
| `extensions/` | One file for each raw table and raw set that stays an extension table |
| `annotations/` | One file each for `technology`, `fuel`, `storage` and `region` |
| `metadata/` | `defaults.parquet`, `units.parquet` and `schema.parquet` |

For example, the raw table `CapitalCost` becomes `outputs/canonical/parameters/capital_cost.parquet`.

The run also writes `decisions.md` in the project directory. `decisions.md` has one line for
each decision of the engine, in five sections:

| Section | What it lists |
| --- | --- |
| Values derived | Each raw set and raw table that got a canonical name, and each annotation that the engine inferred |
| Translator defaults applied | These pipelines record nothing in it |
| User config defaults applied | Each annotation that an `objects:` row gave |
| Components skipped | Each raw table that the engine left out, each table that lost table rows, and each problem that the model reader found |
| Fields not mapped | Each extension table, each technology that got no `kind`, and each field that the model reader did not read |

The `Note` column of each line tells you the reason.

## The automatic match

You need no `parameters:` row for a raw table when both of these are true:

- Its name is the OSeMOSYS name of a canonical parameter, for example `CapitalCost`.
- Its index columns are the OSeMOSYS columns of that canonical parameter. The order of the
  index columns does not matter.

You need no `sets:` entry for a raw set when its name is the OSeMOSYS name of a canonical set,
for example `TECHNOLOGY`.

### Example: a raw table that matches automatically

The raw table `CapitalCost.csv` has the index columns `TECHNOLOGY`, `REGION` and `YEAR`. The
order is not the order of the schema, and the table still matches:

```csv
TECHNOLOGY,REGION,YEAR,VALUE
GASCC,R1,2030,950
WINDON,R1,2030,1300
```

The mappings file holds nothing for it:

```yaml
osemosys: {}
```

The run writes `parameters/capital_cost.parquet`, with the canonical columns in their fixed order:

| region | technology | year | value |
| --- | --- | --- | --- |
| R1 | GASCC | 2030 | 950 |
| R1 | WINDON | 2030 | 1300 |

### Example: a raw table with the right name and other index columns

The raw table `FixedCost.csv` has a `MODE_OF_OPERATION` column. The canonical parameter
`fixed_cost` has no such column, so the raw table does not match automatically:

```csv
REGION,TECHNOLOGY,MODE_OF_OPERATION,YEAR,VALUE
R1,GASCC,1,2030,22
```

With `osemosys: {}`, the run writes `extensions/FixedCost.parquet`. An extension table keeps
its own name, but its columns take the canonical set names:

| region | technology | operating_mode | year | value |
| --- | --- | --- | --- | --- |
| R1 | GASCC | 1 | 2030 | 22 |

The run writes this warning:

```
WARNING ... 1 raw table(s) match no canonical parameter by name and key, so each stays an extension table: FixedCost
```

To map such a table, write a `parameters:` row. The section "`remove_column`" shows how to
remove an extra column.

### See what matched

- In `decisions.md`, the section "Values derived" holds the note `matched by name and key`
  for each automatic match.
- The directory `extensions/` holds each raw table and raw set that did not match.
- The warnings name each extension table. A warning names three tables at most, and counts
  the others.

### Find out why a table did not match

1. Add `--keep-staging` to the run command. The run then keeps its staging directory.
2. Find the directory `interop-osemosys-staging-<random>` in the temporary directory of the
   system. For a TZ-format model, the name starts `interop-tz-osemosys-staging-`.
3. Open `raw/declarations.parquet`. It has one row for each raw table that the reader saw.
4. Read the columns `name`, `key` and `default` of the row for the table that did not match.
5. Compare `name` and `key` with `osemosys_name` and `osemosys_columns` in the schema entry.

For example, a row with `name` `MaxRampRate` and `key` `["REGION", "TECHNOLOGY", "YEAR"]` matches
only a schema entry with the same `osemosys_name` and the same `osemosys_columns`.

## Find the canonical names and columns

The canonical schema is in the file
[`interop/plugins/shared/osemosys_canonical_schema.yaml`](../../interop/plugins/shared/osemosys_canonical_schema.yaml).
The section "Names" of the
[developer document](../developer_documentation/osemosys-canonical-format.md#names)
gives the rule for each name.

This is the entry for `transport_capital_cost`:

```yaml
transport_capital_cost:
  columns:
    start_region: region
    end_region: region
    fuel: fuel
    year: year
  osemosys_name: CapitalCostTrade
  osemosys_columns: [REGION, _REGION, FUEL, YEAR]
  default: 0.00001
  unit: currency per capacity
  meaning: Overnight investment cost of one unit of new transport capacity on a route.
  origin: tz-osemosys v0.4.1
```

Read it like this:

- `transport_capital_cost` is the canonical name. Write it in `canonical:`.
- `columns` gives the canonical columns, in order. The word after each colon is the canonical
  set that the column holds. Here, `start_region` and `end_region` both hold members of
  the set `region`.
- `osemosys_name` is the OSeMOSYS name of the parameter. The automatic match uses it.
- `osemosys_columns` gives the OSeMOSYS name of each column, at the same position as
  `columns`. OSeMOSYS calls the second region `_REGION`.
- `default` is the value that applies where the model states no value. The default that your
  model declares wins over it.
- `unit` tells the kind of unit. The canonical stage keeps the unit of your model.

Most canonical columns have the name of their set, for example `technology` or `year`. Only
`start_region` and `end_region` have other names. They are in each parameter that holds a
pair of regions.

## `units:`

`units:` states the real units of your model. It has five optional fields: `capacity`,
`energy`, `currency`, `currency_year` and `emissions`. The engine does not convert a value.
It writes the units in `metadata/units.parquet`.

```yaml
osemosys:
  units:
    capacity: GW
    energy: PJ
    currency: EUR
    currency_year: 2022
    emissions: Mt
```

The run writes `metadata/units.parquet`:

| quantity | unit |
| --- | --- |
| capacity | GW |
| energy | PJ |
| currency | EUR |
| currency_year | 2022 |
| emissions | Mt |

`currency_year` must be a whole number. A field that the file does not state has no table row.

## `sets:`

`sets:` gives a raw set its canonical set. Write the raw set name, a colon, and the canonical
set name.

### Example: a set of pollutants with another name

The model calls its set of pollutants `GHG`. The file `GHG.csv` holds:

```csv
VALUE
CO2
```

The mappings file:

```yaml
osemosys:
  sets:
    GHG: pollutant
```

The run writes `sets/pollutant.parquet`:

| value |
| --- |
| CO2 |

`sets:` changes the name of the set only. It does not change the `GHG` column of a raw table.
To change that column, use `rename_columns` on a `parameters:` row. The section
"`rename_columns`" shows it.

When two raw sets go to one canonical set, the canonical set holds the members of both. For
example, a raw set `TECHNOLOGY` and a raw set `TECH` that `sets:` sends to `technology` give
one `technology` set.

A raw set with no canonical name stays an extension table. For example, a raw set `UNIT`
gives `extensions/UNIT.parquet`, and this warning:

```
WARNING ... 1 raw set(s) have no canonical set name, so each stays an extension table: UNIT
```

## `parameters:`

A `parameters:` row tells the engine what to do with one raw table, or with a family of raw
tables (the raw tables that rows send to one canonical parameter).

### The fields of a `parameters:` row

Each row states exactly one of these two fields:

| Field | What it names |
| --- | --- |
| `source` | One raw table, by its exact name, for example `source: AvailabilityPercent` |
| `source_pattern` | Each raw table whose name the pattern finds, for example `source_pattern: "^CapacityFactor(?P<zone>[A-Z]+)$"` |

Each row also states exactly one of these two fields:

| Field | What it does |
| --- | --- |
| `canonical` | It names the canonical parameter that receives the raw table, for example `canonical: availability_factor`. |
| `ignore: true` | It leaves the raw table out of the canonical stage. |

`source_pattern` is a Python regular expression. The engine searches for the pattern in the
name, so a pattern with no `^` and `$` can match inside a longer name. For example, the
pattern `Cost` matches `CapitalCost`, `FixedCost` and `CostScenario`.

`canonical` takes a canonical name only. An OSeMOSYS name such as `CapitalCost` stops the run.

### Example: `ignore: true`

The model has a raw table `ReportingFlag` that only its reports use:

```csv
TECHNOLOGY,VALUE
AAGASCC,1
```

```yaml
osemosys:
  parameters:
    - source: ReportingFlag
      ignore: true
```

The run writes no file for `ReportingFlag`. `decisions.md` lists it in "Components skipped",
and the run writes this warning:

```
WARNING ... 1 raw table(s) match a `parameters:` row that says ignore: true, so each is left out: ReportingFlag
```

### The column names that the operations see

A row can give operations that change the raw table. Before the operations, the engine changes
the column names of the raw table:

- A column with the OSeMOSYS name of a set takes the canonical set name. For example,
  `TECHNOLOGY` becomes `technology`, and `MODE_OF_OPERATION` becomes `operating_mode`.
- `_REGION` becomes `end_region`.
- If the canonical parameter has a `start_region` column, `REGION` becomes `start_region`.
- `VALUE` becomes `value`.
- Each other column keeps its name, for example `TECH`, `GHG` or `UNIT`.

So write an operation with the canonical name of a set column, and with the raw name of each
other column.

After the operations, the columns must be the canonical columns of the canonical parameter.
If they are not, the run stops.

### The operations

The engine always does the operations of a row in this order. The order in the file does not
change it.

| Order | Operation | What it does |
| --- | --- | --- |
| 1 | `rename_columns` | It gives a column a new name. |
| 2 | `columns_from_name` | It writes a part of the raw table name into a new column. |
| 3 | `remove_column` | It removes one column, and combines the table rows that differ only in that column. |
| 4 | `repeat_for_all` | It repeats each value for each member of a canonical set. |
| 5 | `multiply_by` | It multiplies each value, and the default of the raw table, by a number. |

#### `rename_columns`

`rename_columns` gives a column a new name. Write the old name, a colon, and the new name.

The raw table `EmissionActivityRatio.csv` has a `GHG` column. `GHG` is not an OSeMOSYS set
name, so the column keeps its name:

```csv
REGION,TECHNOLOGY,GHG,MODE_OF_OPERATION,YEAR,VALUE
NORTH,GASCC,CO2,1,2030,0.056
SOUTH,GASCC,CO2,1,2030,0.056
```

```yaml
osemosys:
  sets:
    GHG: pollutant
  parameters:
    - source: EmissionActivityRatio
      canonical: emission_rate
      rename_columns: {GHG: pollutant}
```

The run writes `parameters/emission_rate.parquet`:

| region | technology | pollutant | operating_mode | year | value |
| --- | --- | --- | --- | --- | --- |
| NORTH | GASCC | CO2 | 1 | 2030 | 0.056 |
| SOUTH | GASCC | CO2 | 1 | 2030 | 0.056 |

The `sets:` entry is necessary. Without it, the canonical set `pollutant` has no members, and
the engine leaves out each table row of `emission_rate`.

#### `columns_from_name`

`columns_from_name` writes a part of the raw table name into a column. It needs a
`source_pattern` with a named group. A named group is a part of the pattern in the form
`(?P<name>...)`. Write the group name, a colon, and the column name.

The model has one capacity factor table for each zone, and the table name gives the zone.
`CapacityFactorNORTH.csv`:

```csv
TECHNOLOGY,TIMESLICE,YEAR,VALUE
WINDON,DAY,2030,0.31
WINDON,NIGHT,2030,0.42
```

`CapacityFactorSOUTH.csv`:

```csv
TECHNOLOGY,TIMESLICE,YEAR,VALUE
WINDON,DAY,2030,0.27
WINDON,NIGHT,2030,0.38
```

```yaml
osemosys:
  parameters:
    - source_pattern: "^CapacityFactor(?P<zone>[A-Z]+)$"
      canonical: capacity_factor
      columns_from_name: {zone: region}
```

The row matches both tables. The engine writes `NORTH` or `SOUTH` into the `region` column, and
puts the two tables into one `parameters/capacity_factor.parquet`:

| region | technology | timeslice | year | value |
| --- | --- | --- | --- | --- |
| NORTH | WINDON | DAY | 2030 | 0.31 |
| NORTH | WINDON | NIGHT | 2030 | 0.42 |
| SOUTH | WINDON | DAY | 2030 | 0.27 |
| SOUTH | WINDON | NIGHT | 2030 | 0.38 |

The value in the new column must be a member of its canonical set. Here, `NORTH` and `SOUTH`
must be in the `REGION` set. If a member is not in its set, the engine leaves out the table
row. The section "Problems in the model data that do not stop the run" tells you more.

#### `remove_column`

`remove_column` removes one column that the canonical parameter does not have. It has three
fields:

| Field | What it states |
| --- | --- |
| `column` | The column to remove |
| `rule` | How to get one value from the table rows that differ only in that column |
| `member` | The member to keep. Give it with the rule `choose` only. |

The rule is one of these:

| Rule | The value that it keeps |
| --- | --- |
| `choose` | The value of the table row that holds `member`. The engine drops the other table rows. |
| `sum` | The sum of the values |
| `mean` | The mean of the values. Each value has the same weight. |
| `min` | The lowest value |
| `max` | The highest value |

The raw table `ResidualCapacity.csv` has one table row for each generating unit, in a `UNIT`
column:

```csv
REGION,TECHNOLOGY,UNIT,YEAR,VALUE
R1,COALST,U1,2030,0.6
R1,COALST,U2,2030,0.4
```

```yaml
osemosys:
  parameters:
    - source: ResidualCapacity
      canonical: residual_capacity
      remove_column: {column: UNIT, rule: sum}
```

The run writes `parameters/residual_capacity.parquet`:

| region | technology | year | value |
| --- | --- | --- | --- |
| R1 | COALST | 2030 | 1.0 |

With each other rule, the same raw table gives this `value`:

| `remove_column` | value |
| --- | --- |
| `{column: UNIT, rule: mean}` | 0.5 |
| `{column: UNIT, rule: min}` | 0.4 |
| `{column: UNIT, rule: max}` | 0.6 |
| `{column: UNIT, rule: choose, member: U2}` | 0.4 |

Write a member that is a number in quotes, for example `member: "2"`. Without the quotes, the
run stops with `Input should be a valid string`.

#### `repeat_for_all`

`repeat_for_all` adds a column, and repeats each value for each member of its canonical set.
Give a list of canonical columns.

The raw table `FixedCostFlat.csv` gives one fixed cost for each technology:

```csv
TECHNOLOGY,VALUE
AAGASCC,22
BBWINDON,35
```

The `REGION` set holds `R1`. The `YEAR` set holds `2030` and `2035`.

```yaml
osemosys:
  parameters:
    - source: FixedCostFlat
      canonical: fixed_cost
      repeat_for_all: [region, year]
```

The run writes `parameters/fixed_cost.parquet`:

| region | technology | year | value |
| --- | --- | --- | --- |
| R1 | AAGASCC | 2030 | 22 |
| R1 | BBWINDON | 2030 | 35 |
| R1 | AAGASCC | 2035 | 22 |
| R1 | BBWINDON | 2035 | 35 |

`start_region` and `end_region` take the members of the `region` set.

#### `multiply_by`

`multiply_by` multiplies each value by a number. It also multiplies the default that the model
declares for the raw table.

The raw table `AvailabilityPercent.csv` holds the availability in percent:

```csv
REGION,TECHNOLOGY,YEAR,VALUE
R1,AAGASCC,2030,92
R1,CCCOALST,2030,85
```

The canonical parameter `availability_factor` holds a fraction, so multiply by 0.01:

```yaml
osemosys:
  parameters:
    - source: AvailabilityPercent
      canonical: availability_factor
      multiply_by: 0.01
```

The run writes `parameters/availability_factor.parquet`:

| region | technology | year | value |
| --- | --- | --- | --- |
| R1 | AAGASCC | 2030 | 0.92 |
| R1 | CCCOALST | 2030 | 0.85 |

`multiply_by` takes one number. It cannot add a number or use a formula.

### Example: three operations in one row

The model calls its technology set `TECH`. The raw table `InvestmentCost.csv` states one cost
in EUR per MW for each technology. The other costs of the model are in EUR per kW.

```csv
TECH,VALUE
GASCC,900000
WINDON,1250000
```

The otoole configuration file declares a default of 1000 for `InvestmentCost`. The `REGION` set
holds `R1`. The `YEAR` set holds `2030` and `2035`.

```yaml
osemosys:
  sets:
    TECH: technology
  parameters:
    - source: InvestmentCost
      canonical: capital_cost
      rename_columns: {TECH: technology}
      repeat_for_all: [region, year]
      multiply_by: 0.001
```

The engine renames `TECH` to `technology`. Then it repeats each value for `R1`, `2030` and
`2035`. Then it multiplies each value by 0.001. The run writes `parameters/capital_cost.parquet`:

| region | technology | year | value |
| --- | --- | --- | --- |
| R1 | GASCC | 2030 | 900 |
| R1 | WINDON | 2030 | 1250 |
| R1 | GASCC | 2035 | 900 |
| R1 | WINDON | 2035 | 1250 |

In `metadata/defaults.parquet`, the default of `capital_cost` is 1, which is 1000 multiplied
by 0.001.

The `sets:` entry is necessary. Without it, the canonical set `technology` has no members, and
the engine leaves out each table row of `capital_cost`.

### The order of the rows

The engine applies these rules to the `parameters:` rows:

- **The first row that matches a raw table wins.** The engine does not try the rows after it.
- **A row stops the automatic match for its canonical parameter.** When a row sends a raw table
  to a canonical parameter, no automatic match writes to that parameter.
- **A family merges only when the defaults agree.** The raw tables that `parameters:` rows send
  to one canonical parameter are a family. They must declare the same default, after
  `multiply_by`. If not, each one stays an extension table.
- **Two raw tables cannot write one canonical table row.** If they do, the run stops.

#### Example: the first row wins

The model has `CapacityFactorNORTH` and `CapacityFactorSOUTH`, as in the section
"`columns_from_name`". The first row leaves out the `NORTH` table:

```yaml
osemosys:
  parameters:
    - source: CapacityFactorNORTH
      ignore: true
    - source_pattern: "^CapacityFactor(?P<zone>[A-Z]+)$"
      canonical: capacity_factor
      columns_from_name: {zone: region}
```

Row 0 matches `CapacityFactorNORTH`, so row 1 does not get it. `parameters/capacity_factor.parquet`
holds the `SOUTH` values only:

| region | technology | timeslice | year | value |
| --- | --- | --- | --- | --- |
| SOUTH | WINDON | DAY | 2030 | 0.27 |
| SOUTH | WINDON | NIGHT | 2030 | 0.38 |

#### Example: a row stops the automatic match

The model has two cost tables with the same index columns. `CapitalCost.csv`:

```csv
REGION,TECHNOLOGY,YEAR,VALUE
R1,GASCC,2030,950
```

`OvernightCost.csv`:

```csv
REGION,TECHNOLOGY,YEAR,VALUE
R1,GASCC,2030,870
```

```yaml
osemosys:
  parameters:
    - source: OvernightCost
      canonical: capital_cost
```

`parameters/capital_cost.parquet` holds the value of `OvernightCost`:

| region | technology | year | value |
| --- | --- | --- | --- |
| R1 | GASCC | 2030 | 870 |

`CapitalCost` would match `capital_cost` automatically. The row takes `capital_cost`, so
`CapitalCost` stays an extension table, `extensions/CapitalCost.parquet`. The run writes this
warning:

```
WARNING ... 1 raw table(s) match a canonical parameter that a `parameters:` row maps instead, so each stays an extension table: CapitalCost
```

If you also add a row that sends `CapitalCost` to `capital_cost`, the two tables write the same
table row. The run then stops:

```
Rows 0, 1 of `parameters:` map the raw tables CapitalCost, OvernightCost to the same capital_cost row (R1, GASCC, 2030). Change the rows so that one raw table gives each canonical row.
```

## `objects:`

`objects:` gives annotations to set members. An annotation tells what a member is, or where it
is. `objects:` has four lists. Each list annotates the members of one canonical set, and
accepts only some annotations:

| List | Canonical set | Annotations that it accepts |
| --- | --- | --- |
| `technologies:` | `technology` | `kind`, `category`, `location` |
| `fuels:` | `fuel` | `carrier`, `location` |
| `storages:` | `storage` | `location` |
| `regions:` | `region` | `location` |

The run writes one annotation table for each list, in `annotations/`. An annotation table has
one table row for each region and each member, because one member name can be in many regions.

| File | Columns |
| --- | --- |
| `annotations/technology.parquet` | `region`, `technology`, `kind`, `category`, `location` |
| `annotations/fuel.parquet` | `region`, `fuel`, `carrier`, `location` |
| `annotations/storage.parquet` | `region`, `storage`, `location` |
| `annotations/region.parquet` | `region`, `location` |

### `match`

Each `objects:` row has a `match`, which is a Python regular expression. The engine searches
for it in the member name. Then:

- The first row that matches a member wins.
- A row gives only the annotations that it states. The engine infers the others.
- A row gives the same annotations in each region.

A search can match inside a longer name. Use `^` for the start of the name and `$` for the
end. For example, the model has the technologies `AAGASCC`, `AAGASIMP` and `BBWINDON`:

```yaml
osemosys:
  objects:
    technologies:
      - match: "GAS"
        category: gas-combined-cycle
```

The pattern `GAS` matches two technologies, and the gas import gets the wrong category:

| region | technology | kind | category | location |
| --- | --- | --- | --- | --- |
| R1 | AAGASCC | | gas-combined-cycle | R1 |
| R1 | AAGASIMP | | gas-combined-cycle | R1 |
| R1 | BBWINDON | | | R1 |

Write `match: "^AAGASCC$"` for one technology, or `match: "GASCC$"` for each name that ends in
`GASCC`.

Because the first row wins, put a narrow row before a wide row:

```yaml
osemosys:
  objects:
    technologies:
      - match: "^AAGASOC$"
        category: gas-open-cycle
      - match: "^AAGAS"
        category: gas-combined-cycle
```

| region | technology | kind | category | location |
| --- | --- | --- | --- | --- |
| R1 | AAGASCC | | gas-combined-cycle | R1 |
| R1 | AAGASOC | | gas-open-cycle | R1 |

### `location`

`location` is a text template. Put a name in braces, `{...}`, and the engine writes a value in
its place. You can use two kinds of names:

- A named group of `match`, for example `{country}` from `(?P<country>[A-Z]{2})`.
- `{region}`, which is the region of the table row.

A template can also hold fixed text. In this example, the regions are `Z1` and `Z2`:

```yaml
osemosys:
  objects:
    regions:
      - match: "^Z(?P<number>[0-9]+)$"
        location: "zone-{number}"
```

The run writes `annotations/region.parquet`:

| region | location |
| --- | --- |
| Z1 | zone-1 |
| Z2 | zone-2 |

#### Example: a country prefix

The model has one region, `R1`, and three countries, `AA`, `BB` and `CC`. Each fuel name starts
with the country:

```csv
VALUE
AAELEC
BBELEC
CCELEC
AAGAS
CCCOAL
```

```yaml
osemosys:
  objects:
    fuels:
      - match: "^(?P<country>[A-Z]{2})ELEC$"
        carrier: electricity
        location: "{country}"
      - match: "^(?P<country>[A-Z]{2})GAS$"
        carrier: natural-gas
        location: "{country}"
      - match: "^(?P<country>[A-Z]{2})COAL$"
        carrier: coal
        location: "{country}"
```

The run writes `annotations/fuel.parquet`:

| region | fuel | carrier | location |
| --- | --- | --- | --- |
| R1 | AAELEC | electricity | AA |
| R1 | BBELEC | electricity | BB |
| R1 | CCELEC | electricity | CC |
| R1 | AAGAS | natural-gas | AA |
| R1 | CCCOAL | coal | CC |

### `kind`

`kind` tells what a technology is. It takes one value from this list:

| `kind` | The technology |
| --- | --- |
| `StorageTechnology` | Charges or discharges a storage |
| `AggregateTransportTechnology` | Moves electricity from one location to another |
| `SupplyTechnology` | Makes electricity |
| `fuel_supply` | Supplies a fuel that is not electricity |
| `export` | Takes in a fuel and puts out nothing |
| `conversion` | Changes one fuel into another at one location |

The first three are type names in Sienna, the tool that a later translation writes to.
Another value, for example `generator`, stops the run.
The engine infers `kind` from the activity ratios and the storage tables.
A row needs `kind` only to change the inference.
The section "What the engine infers" gives the rules.

### `category` and `carrier`

`category` is free text for a technology, for example `gas-combined-cycle` or `wind-onshore`.
The engine never infers a category.

`carrier` is free text for a fuel, for example `natural-gas` or `coal`. The engine never infers
a carrier. One value has a fixed meaning: `carrier: electricity` tells the engine that the fuel is
electricity. The `kind` rules use it.

#### Example: a TZ-format model

A TZ-format model has the regions `NORTH` and `SOUTH`, the fuels `natural-gas` and
`electricity`, and the technologies `gas-cc` and `gas-import`. This file gives the units, a
carrier and a location for each fuel, and a category for `gas-cc`:

```yaml
osemosys:
  units: {capacity: MW, energy: MWh, currency: USD, currency_year: 2023}
  objects:
    fuels:
      - match: "^electricity$"
        carrier: electricity
        location: "{region}"
      - match: "^natural-gas$"
        carrier: natural-gas
        location: "{region}"
    technologies:
      - match: "^gas-cc$"
        category: gas-combined-cycle
```

The run writes `annotations/technology.parquet`:

| region | technology | kind | category | location |
| --- | --- | --- | --- | --- |
| NORTH | gas-cc | SupplyTechnology | gas-combined-cycle | NORTH |
| NORTH | gas-import | fuel_supply | | NORTH |
| SOUTH | gas-cc | SupplyTechnology | gas-combined-cycle | SOUTH |
| SOUTH | gas-import | fuel_supply | | SOUTH |

### What the engine infers

The engine infers each `location` and `kind` that no row gives. An `objects:` row overrides an
inference.

The engine infers a location like this:

- A region is its own location.
- A fuel and a storage take the location of their region.
- A technology takes the locations that `objects:` rows give to the fuels that it takes in and
  puts out. A fuel location that the engine inferred does not count.
- If a technology touches two or more locations, `~` joins them, for example `AA~BB`. The
  lowest operating mode comes first. In one mode, the location of an input fuel comes first.
- If no fuel of a technology has a location from a row, the technology takes the location of
  its region.

The engine infers a kind from the canonical tables `input_activity_ratio`,
`output_activity_ratio`, `technology_to_storage` and `technology_from_storage`. Only a table row
with a `value` above zero counts. A fuel is electricity when its `carrier` is `electricity`.
The engine tries the kinds in this order. The first kind that fits wins:

| Order | `kind` | The technology |
| --- | --- | --- |
| 1 | `StorageTechnology` | Has a table row in `technology_to_storage` or `technology_from_storage` |
| 2 | `AggregateTransportTechnology` | Takes in electricity and puts out electricity, and rows give these fuels two or more locations |
| 3 | `SupplyTechnology` | Puts out electricity, and takes in no electricity |
| 4 | `fuel_supply` | Puts out a fuel that is not electricity, and takes in nothing |
| 5 | `export` | Takes in a fuel, and puts out nothing |
| 6 | `conversion` | Takes in and puts out, and rows give its fuels one location or none |

If no kind fits, `kind` stays empty. `decisions.md` lists the technology in "Fields not
mapped", and the run writes a warning:

```
WARNING ... no kind fits 1 technology(ies) in their region, so each keeps an empty kind: R1/COALST
```

A technology with no table rows in a region gets this warning for that region.

#### Example: the inferred kinds and locations

The model with the countries `AA`, `BB` and `CC` has these table rows in
`InputActivityRatio.csv`:

```csv
REGION,TECHNOLOGY,FUEL,MODE_OF_OPERATION,YEAR,VALUE
R1,AAGASCC,AAGAS,1,2030,1.8
R1,CCCOALST,CCCOAL,1,2030,2.5
R1,AABBLINK,AAELEC,1,2030,1
```

And in `OutputActivityRatio.csv`:

```csv
REGION,TECHNOLOGY,FUEL,MODE_OF_OPERATION,YEAR,VALUE
R1,AAGASCC,AAELEC,1,2030,1
R1,BBWINDON,BBELEC,1,2030,1
R1,CCCOALST,CCELEC,1,2030,1
R1,AABBLINK,BBELEC,1,2030,0.97
R1,AAGASIMP,AAGAS,1,2030,1
```

With the `fuels:` rows of the section "Example: a country prefix", and no `technologies:` row,
the engine infers:

| technology | kind | location | Why |
| --- | --- | --- | --- |
| AAGASCC | SupplyTechnology | AA | It puts out electricity, and takes in gas |
| BBWINDON | SupplyTechnology | BB | It puts out electricity, and takes in nothing |
| CCCOALST | SupplyTechnology | CC | It puts out electricity, and takes in coal |
| AABBLINK | AggregateTransportTechnology | AA~BB | It takes in electricity in `AA`, and puts out electricity in `BB` |
| AAGASIMP | fuel_supply | AA | It puts out gas, and takes in nothing |

`decisions.md` gives the rule of each inference in "Values derived", for example:

```
location AA~BB: the locations of the fuels that it takes in and puts out; kind AggregateTransportTechnology: it takes in electricity at one location and puts it out at another
```

#### Example: a row overrides an inference

In a model with the regions `NORTH` and `SOUTH`, the technology `WINDON` has table rows in
`SOUTH` only. In `NORTH`, no kind fits. A row gives the kind in each region:

```yaml
osemosys:
  objects:
    technologies:
      - match: "^WINDON$"
        kind: SupplyTechnology
        category: wind-onshore
```

| region | technology | kind | category | location |
| --- | --- | --- | --- | --- |
| NORTH | WINDON | SupplyTechnology | wind-onshore | NORTH |
| SOUTH | WINDON | SupplyTechnology | wind-onshore | SOUTH |

`decisions.md` lists the row in "User config defaults applied":

```
row 0 of `objects: technologies` gives kind, category
```

## Errors that stop the run

An error in the mappings file stops the run. The run writes no canonical stage. The console
shows the error, also without `INTEROP_LOG_LEVEL`.

An error in the form of the file contains `Invalid user mappings at <file>`. A later line
names the place in the file, for example `osemosys.parameters.0` for row 0 of `parameters:`.

| The error contains | Cause | Fix |
| --- | --- | --- |
| `Extra inputs are not permitted` | A key that the engine does not know, for example `parameter:` in place of `parameters:` | Correct the name of the key. |
| `` `sets:` names the canonical sets ['technologies'], which do not exist `` | A `sets:` entry names a canonical set that does not exist | Use a canonical set name, for example `technology`. |
| `` row 0 of `parameters:` names the canonical parameter CapitalCost, which the canonical schema does not hold `` | `canonical` holds an OSeMOSYS name or a wrong name | Use the canonical name from the schema file, for example `capital_cost`. |
| `` row 0 of `parameters:` repeats for ['regions'], which are not canonical sets `` | `repeat_for_all` names a column that no canonical parameter has | Use a canonical column name, for example `region`. |
| `remove_column states a member when its rule is choose, and only then` | `member` with a rule other than `choose`, or `choose` with no `member` | Give `member` with `choose` only. |
| `Input should be a valid string` | A `member` that is a number with no quotes | Put the member in quotes, for example `"2"`. |
| `a row states exactly one of source and source_pattern` | A row states both fields, or neither | Keep one of the two. |
| `a row states exactly one of canonical and ignore: true` | A row states both fields, or neither | Keep one of the two. |
| `is not a regular expression` | A `source_pattern` or a `match` that is not a correct regular expression | Correct the pattern. |
| `columns_from_name names the groups ['zone'], which source_pattern does not hold` | `columns_from_name` names a group that the pattern does not have | Add the named group `(?P<zone>...)` to the pattern. |
| `` row 0 of `objects: fuels` gives category, which a fuels row does not hold `` | An annotation that the list does not accept | Move the annotation to the correct list. |
| `` Input should be 'StorageTechnology', 'AggregateTransportTechnology', 'SupplyTechnology', 'fuel_supply', 'export' or 'conversion' `` | A `kind` that is not in the list | Use a value from the list. |
| `the location {country} names country, which match does not capture` | `location` names a group that `match` does not have | Add the group to `match`, or use `{region}`. |
| `the location '{}' holds an empty {}` | `location` holds empty braces | Put a group name or `region` in the braces. |

The engine finds these errors when it applies the file to the model, so they name the raw table
or the member:

| The error contains | Cause | Fix |
| --- | --- | --- |
| `` Row 0 of `parameters:` cannot map the raw table InvestmentCost to capital_cost. Its operations turn the key TECH into technology, but capital_cost is keyed region, technology, year. `` | After the operations, the columns are not the canonical columns | Add the missing columns with `repeat_for_all` or `columns_from_name`, or remove the extra column with `remove_column`. |
| `The row names the columns ..., which are not in the key.` | `rename_columns` or `remove_column` names a column that the raw table does not have at that step | Use the column name that the operation sees. The section "The column names that the operations see" gives the names. |
| `` Rows 0, 1 of `parameters:` map the raw tables CapitalCost, OvernightCost to the same capital_cost row (R1, GASCC, 2030). `` | Two raw tables write the same canonical table row | Change the rows, so that one raw table gives each table row. |
| `` row 0 of `objects: fuels` gives the location {country}, but its match captures no country for GAS `` | The group is optional in `match`, and it is empty for this member | Make the group required, or add a row for this member before the row. |

## Problems in the model data that do not stop the run

A problem in the data of your model never stops the run. The engine leaves out what it cannot
use, and it reports it. To find these problems, read the warnings and `decisions.md`. Run with
`INTEROP_LOG_LEVEL=WARNING` to see the warnings.

| Problem | What the engine does | The warning contains | Section of `decisions.md` |
| --- | --- | --- | --- |
| A raw table matches no canonical parameter | It keeps an extension table | `match no canonical parameter by name and key` | Fields not mapped |
| A raw set has no canonical name | It keeps an extension table | `have no canonical set name` | Fields not mapped |
| A raw table matches a canonical parameter that a row sends another table to | It keeps an extension table | `row maps instead` | Fields not mapped |
| The raw tables of a family declare different defaults | It keeps each one as an extension table | `map to one canonical parameter but declare different defaults` | Fields not mapped |
| A row says `ignore: true` | It leaves out the raw table | `row that says ignore: true` | Components skipped |
| A value names a set member that its canonical set does not hold, or it has an empty cell | It leaves out that table row, and keeps the others | `hold values whose set member is not in its canonical set` | Components skipped |
| A `parameters:` row matches no raw table | Nothing | `match no raw table` | None |
| A `sets:` entry names no raw set | Nothing | `name no raw set` | None |
| `choose` names a member that no table row holds | That raw table gives no table rows | `choose a member that no row of the raw table holds` | None |
| `repeat_for_all` names a set with no members | That raw table gives no table rows | `repeat each value for a set with no members` | None |
| No kind fits a technology | `kind` stays empty | `no kind fits` | Fields not mapped |

For example, a `CapitalCost` table row for the technology `OIL`, which is not in the
`TECHNOLOGY` set, gives this warning:

```
WARNING ... 1 canonical parameter table(s) hold values whose set member is not in its canonical set, so those values are left out: capital_cost (absent members: OIL)
```

The model readers also report problems in the files, for example a `VALUE` that is not a
number. The section "The sources" of the
[developer document](../developer_documentation/osemosys-canonical-format.md#the-sources) lists
them.

## What a mappings file cannot do

A mappings file can rename, merge, remove a column, repeat and multiply. It cannot do these
things:

- **Change an equation of the model.** The engine copies parameter values. It does not read or
  change the equations of your OSeMOSYS variant.
- **Use a formula other than a factor.** `multiply_by` takes one number. The engine cannot add
  a number, or calculate a value from two values.
- **Join two tables.** Each row reads one raw table at a time. The engine cannot look up a value
  in a second table, for example to divide a cost by a capacity.
- **Calculate a weighted mean.** The `mean` rule gives each value the same weight.
- **Keep a part of a name that has no canonical column.** `columns_from_name` must write into a
  canonical column. A country code in a model with one region has no canonical column, so
  write it into a `location` with an `objects:` row.
- **Add a concept that the canonical schema does not have.** `canonical` must name a parameter
  of the schema file.
- **Change a set member.** No operation changes a member name, for example `GAS` to `gas`.
- **Give a region its own annotation for one member.** An `objects:` row gives the same
  annotations in each region. Only `{region}` in a `location` changes from region to region.

A raw table that the mappings file cannot map stays an extension table, with its own name, in
`extensions/`. No data is lost. If the table has no use, a row with `ignore: true` leaves it out.

## Complete example: one region, three countries

An invented model has one region, `R1`, and three countries, `AA`, `BB` and `CC`. The first two
letters of each technology and fuel name give the country.

| Set | Members |
| --- | --- |
| `REGION` | `R1` |
| `TECHNOLOGY` | `AAGASCC`, `BBWINDON`, `CCCOALST`, `AABBLINK`, `AAGASIMP` |
| `FUEL` | `AAELEC`, `BBELEC`, `CCELEC`, `AAGAS`, `CCCOAL` |
| `MODE_OF_OPERATION` | `1` |
| `YEAR` | `2030`, `2035` |
| `UNIT` | `U1`, `U2` |

| Raw table | Index columns | Why it needs a row |
| --- | --- | --- |
| `InputActivityRatio`, `OutputActivityRatio`, `CapitalCost` | The published ones | They match automatically |
| `AvailabilityPercent` | `REGION`, `TECHNOLOGY`, `YEAR` | Percent in place of a fraction, and another name |
| `ResidualCapacity` | `REGION`, `TECHNOLOGY`, `UNIT`, `YEAR` | One table row for each unit |
| `FixedCostFlat` | `TECHNOLOGY` | One value for all regions and years |
| `ReportingFlag` | `TECHNOLOGY` | The model uses it for reports only |
| `MaxRampRate` | `REGION`, `TECHNOLOGY`, `YEAR` | The canonical schema has no such parameter |

The mappings file:

```yaml
osemosys:
  units:
    capacity: GW
    energy: PJ
    currency: EUR
    currency_year: 2022
    emissions: Mt

  parameters:
    # Availability as a percentage, 0 to 100.
    - source: AvailabilityPercent
      canonical: availability_factor
      multiply_by: 0.01

    # One table row for each generating unit; the canonical table holds the total.
    - source: ResidualCapacity
      canonical: residual_capacity
      remove_column: {column: UNIT, rule: sum}

    # One fixed cost for each technology, for every region and every year.
    - source: FixedCostFlat
      canonical: fixed_cost
      repeat_for_all: [region, year]

    # A table for the reports of the model only.
    - source: ReportingFlag
      ignore: true

  objects:
    fuels:
      - match: "^(?P<country>[A-Z]{2})ELEC$"
        carrier: electricity
        location: "{country}"
      - match: "^(?P<country>[A-Z]{2})GAS$"
        carrier: natural-gas
        location: "{country}"
      - match: "^(?P<country>[A-Z]{2})COAL$"
        carrier: coal
        location: "{country}"
    technologies:
      - match: "GASCC$"
        category: gas-combined-cycle
      - match: "WINDON$"
        category: wind-onshore
      - match: "COALST$"
        category: coal-steam
      - match: "^[A-Z]{4}LINK$"
        category: interconnector
```

The run gives these results:

- `parameters/` holds `availability_factor`, `capital_cost`, `fixed_cost`,
  `input_activity_ratio`, `output_activity_ratio` and `residual_capacity`.
- `extensions/` holds `MaxRampRate` and `UNIT`.
- The run writes no file for `ReportingFlag`.

`annotations/technology.parquet`:

| region | technology | kind | category | location |
| --- | --- | --- | --- | --- |
| R1 | AAGASCC | SupplyTechnology | gas-combined-cycle | AA |
| R1 | BBWINDON | SupplyTechnology | wind-onshore | BB |
| R1 | CCCOALST | SupplyTechnology | coal-steam | CC |
| R1 | AABBLINK | AggregateTransportTechnology | interconnector | AA~BB |
| R1 | AAGASIMP | fuel_supply | | AA |

The run writes three warnings. You can expect each one:

```
WARNING ... 1 raw set(s) have no canonical set name, so each stays an extension table: UNIT
WARNING ... 1 raw table(s) match a `parameters:` row that says ignore: true, so each is left out: ReportingFlag
WARNING ... 1 raw table(s) match no canonical parameter by name and key, so each stays an extension table: MaxRampRate
```

## Complete example: one region for each zone

An invented model has two zones, and each zone is a region: `NORTH` and `SOUTH`. The names of
the technologies and fuels are the same in each region.

| Set | Members |
| --- | --- |
| `REGION` | `NORTH`, `SOUTH` |
| `TECHNOLOGY` | `GASCC`, `WINDON`, `BATTERY`, `GASIMP` |
| `FUEL` | `GAS`, `ELEC` |
| `STORAGE` | `BATTSTORE` |
| `GHG` | `CO2` |
| `MODE_OF_OPERATION` | `1`, `2` |
| `YEAR` | `2030`, `2035` |
| `TIMESLICE` | `DAY`, `NIGHT` |
| `SCENARIO` | `LOW`, `CENTRAL`, `HIGH` |

| Raw table | Index columns | Why it needs a row |
| --- | --- | --- |
| `InputActivityRatio`, `OutputActivityRatio`, `TechnologyToStorage`, `TechnologyFromStorage`, `TradeRoute` | The published ones | They match automatically |
| `CapacityFactorNORTH`, `CapacityFactorSOUTH` | `TECHNOLOGY`, `TIMESLICE`, `YEAR` | The table name gives the region |
| `EmissionActivityRatio` | `REGION`, `TECHNOLOGY`, `GHG`, `MODE_OF_OPERATION`, `YEAR` | The pollutant column is `GHG` |
| `CapitalCost` | `REGION`, `TECHNOLOGY`, `SCENARIO`, `YEAR` | One table row for each cost scenario |
| `MinUpTime` | `REGION`, `TECHNOLOGY` | The canonical schema has no such parameter |

The mappings file:

```yaml
osemosys:
  units:
    capacity: MW
    energy: MWh
    currency: USD
    currency_year: 2023
    emissions: t

  sets:
    GHG: pollutant

  parameters:
    # One capacity factor table for each zone; the name gives the zone.
    - source_pattern: "^CapacityFactor(?P<zone>[A-Z]+)$"
      canonical: capacity_factor
      columns_from_name: {zone: region}

    # The model names its pollutant column GHG.
    - source: EmissionActivityRatio
      canonical: emission_rate
      rename_columns: {GHG: pollutant}

    # The model holds three cost scenarios; the canonical stage takes CENTRAL.
    - source: CapitalCost
      canonical: capital_cost
      remove_column: {column: SCENARIO, rule: choose, member: CENTRAL}

  objects:
    fuels:
      - match: "^ELEC$"
        carrier: electricity
        location: "{region}"
      - match: "^GAS$"
        carrier: natural-gas
        location: "{region}"
    technologies:
      - match: "^GASCC$"
        category: gas-combined-cycle
      # A row gives the kind in every region, also where the technology has no table rows.
      - match: "^WINDON$"
        kind: SupplyTechnology
        category: wind-onshore
      - match: "^BATTERY$"
        kind: StorageTechnology
        category: battery
```

The run gives these results:

- `parameters/` holds `capacity_factor`, `capital_cost`, `emission_rate`,
  `input_activity_ratio`, `output_activity_ratio`, `technology_from_storage`,
  `technology_to_storage` and `transport_route`.
- `sets/pollutant.parquet` holds `CO2`.
- `extensions/` holds `MinUpTime` and `SCENARIO`.
- `parameters/capital_cost.parquet` holds the `CENTRAL` value, 900, for `NORTH`, `GASCC`
  and `2030`.

`parameters/transport_route.parquet` comes from the automatic match. `REGION` becomes
`start_region`, and `_REGION` becomes `end_region`:

| start_region | end_region | fuel | year | value |
| --- | --- | --- | --- | --- |
| NORTH | SOUTH | ELEC | 2030 | 1 |
| SOUTH | NORTH | ELEC | 2030 | 1 |

`annotations/technology.parquet`:

| region | technology | kind | category | location |
| --- | --- | --- | --- | --- |
| NORTH | GASCC | SupplyTechnology | gas-combined-cycle | NORTH |
| NORTH | WINDON | SupplyTechnology | wind-onshore | NORTH |
| NORTH | BATTERY | StorageTechnology | battery | NORTH |
| NORTH | GASIMP | fuel_supply | | NORTH |
| SOUTH | GASCC | SupplyTechnology | gas-combined-cycle | SOUTH |
| SOUTH | WINDON | SupplyTechnology | wind-onshore | SOUTH |
| SOUTH | BATTERY | StorageTechnology | battery | SOUTH |
| SOUTH | GASIMP | fuel_supply | | SOUTH |

`WINDON` has no table rows in `NORTH`, and `BATTERY` has no table rows in `SOUTH`. Without the
two `kind` values in the file, `kind` stays empty for them there.

The run writes two warnings. You can expect each one:

```
WARNING ... 1 raw set(s) have no canonical set name, so each stays an extension table: SCENARIO
WARNING ... 1 raw table(s) match no canonical parameter by name and key, so each stays an extension table: MinUpTime
```

## More about the canonical stage

The [developer document](../developer_documentation/osemosys-canonical-format.md) describes the
canonical stage in full. It gives each canonical name and its reason, the metadata tables, and
how each model reader reads its files.
