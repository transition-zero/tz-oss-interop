# OSeMOSYS Mappings Guide

tz-oss-interop is a tool that translates energy-system models from one format to another. This guide
is for a modeller who has an OSeMOSYS model and wants to use it with tz-oss-interop. It tells you what
to write, and why.

## What tz-oss-interop does with an OSeMOSYS model

Each OSeMOSYS model names and shapes its data in its own way. For example, one model calls its
set of technologies `TECHNOLOGY`, and another model calls it `TECH`. One model gives the
availability of a technology as a fraction, and another model gives it in percent.

So tz-oss-interop first puts each OSeMOSYS model into one standard form. tz-oss-interop calls this standard
form the canonical stage. The canonical stage is a directory of files. It is not a translation to
another tool. It is one fixed form of an OSeMOSYS model.

tz-oss-interop does not yet translate the canonical stage to another tool. Sienna is a power-system
modelling tool. A translation to Sienna is planned, and it will read the canonical stage. Because
each OSeMOSYS model has the same form in the canonical stage, that translation will work for
each OSeMOSYS model.

tz-oss-interop cannot find some facts in the files of your model. These are examples:

- The real units of your values, for example GW and PJ.
- That your set `TECH` holds the technologies.
- That your parameter `AvailabilityPercent` holds a percent, so tz-oss-interop must multiply each value
  by 0.01.
- What each technology or fuel is, and where it is. For example, the fuel `AAGAS` is natural gas
  in the country `AA`.

You write these facts in a mappings file. The mappings file is a text file that you write and
give to tz-oss-interop.

tz-oss-interop then gives you two things:

- A directory of tables, with one table for each set and each parameter of your model. This
  directory is the canonical stage.
- A report, `decisions.md`. It lists each decision that tz-oss-interop made, with the reason.

You must know your own model: its sets, its parameters and its files. You must be able to edit a
text file. You do not need to read Python or the code of tz-oss-interop. The mappings file uses
YAML, a text format for names and values. This guide explains each YAML form where an example
first uses it.

[The words](#the-words), at the end of this guide, lists each term that this guide uses.

## How tz-oss-interop reads your model

### The two model formats

tz-oss-interop reads an OSeMOSYS model in one of two formats:

- **An otoole model.** otoole is a tool that reads and writes OSeMOSYS models. An otoole model
  is a configuration file and a directory of CSV files. The configuration file declares each set
  and each parameter. For each parameter, it gives its `indices` and its default value. The
  `indices` are the sets that the values of the parameter depend on. Each CSV file holds one set
  or one parameter.
- **A TZ-format model.** This is the `model.json` file that tz-osemosys writes. tz-osemosys is
  the OSeMOSYS tool of TransitionZero.

### The model reader and the engine

tz-oss-interop puts your model into the canonical stage in two steps:

1. The model reader reads the files of your model. The model reader is the code in tz-oss-interop that
   reads one file format. tz-oss-interop has one model reader for each of the two formats.
2. The engine reads your mappings file, and writes the canonical stage. The engine is the code
   in tz-oss-interop that applies your mappings file to your model.

### Your model in its own names

The model reader gives your model to the engine with the names that your model uses. This guide
uses these words for it:

- A **raw set** is one set of your model, with the name that your model gives it. For example,
  `TECHNOLOGY` or `UNIT`.
- A **set member**, or **member**, is one value in a set. For example, the technology `GASCC` or
  the year `2030`.
- A **raw table** is one parameter of your model, with the name that your model gives it. For
  example, `CapitalCost` or `MaxRampRate`.
- The **index columns** of a raw table are its columns that name set members. For example,
  `REGION`, `TECHNOLOGY` and `YEAR`. In an otoole model, the `indices` of the parameter in the
  configuration file give them.
- The column `VALUE` of a raw table holds the number.
- A **table row** is one line of values in a table. For example, the table row
  `R1,GASCC,2030,950` gives the capital cost 950 of `GASCC` in the region `R1` in 2030.

### The canonical schema

tz-oss-interop knows a fixed list of sets and parameters. This list is the canonical schema. Each set
and each parameter in it has a canonical name, in lower case. For example, the canonical name of
the OSeMOSYS parameter `CapitalCost` is `capital_cost`.

The OSeMOSYS name of a set or a parameter is its name in the OSeMOSYS v1.0.1 model file. For
example, `CapitalCost` and `REGION` are OSeMOSYS names. A parameter that only tz-osemosys or
OSeMOSYS MUIO has uses the name that that tool gives it. A file that comes with tz-oss-interop, the
schema file, gives each OSeMOSYS name as `osemosys_name`.
[Find the canonical names and columns](#find-the-canonical-names-and-columns) shows the schema
file.

- A **canonical set** is a set of the canonical schema, for example `technology`.
- A **canonical parameter** is a parameter of the canonical schema, for example `capital_cost`.
- The **canonical columns** of a canonical parameter are its columns, in a fixed order. For
  example, the canonical columns of `capital_cost` are `region, technology, year`. A `value`
  column comes after them.

The engine writes each canonical set and each canonical parameter of your model to one file. This
file is a canonical table. Each canonical table is a parquet file. A parquet file is a file that
holds one table: the column names, a type for each column, and the table rows. A text editor
cannot show a parquet file. [Look at a parquet file](#look-at-a-parquet-file) gives a command that
shows it.

### What the engine does with each raw set and raw table

The engine looks at each raw set and each raw table of your model. For each one, it does one of
these things:

- It maps it. To map a raw set or a raw table to a canonical set or a canonical parameter is to
  give it that canonical name. The result is a canonical table.
- It keeps it with its own name. The result is an extension table. An extension table is a raw
  table or a raw set that gets no canonical name. The canonical stage keeps it, so you lose
  no data.
- It leaves the raw table out, if your mappings file tells it to do so.

The engine maps a raw table automatically when your model uses the published OSeMOSYS name and
the published index columns. This is the automatic match. So the mappings file holds only the
differences between your model and the canonical schema. [The automatic match](#the-automatic-match)
tells you the rules.

The engine also writes annotations. An annotation is a fact about a set member that the model
does not state as a parameter. For example, an annotation can tell that a technology is in the
country `AA`. You give an annotation in the mappings file, or the engine infers it. To infer a
value is to find it from other data in the model.

### How to read the examples

A worked example in this guide has three items:

1. A small raw table from an invented model.
2. The lines of the mappings file.
3. The canonical table that tz-oss-interop writes.

Each model in the examples is invented. tz-oss-interop wrote each result table from that model, in a
run. A run is one use of tz-oss-interop on a model, with the command of [Your first run](#your-first-run).

## The mappings file

### A YAML file

The mappings file is a text file in YAML format. You can write it in any text editor.

This is the smallest valid mappings file:

```yaml
osemosys: {}
```

Read it like this:

- `osemosys` is a key. In YAML, a key is a name. A colon follows the key, then a space, then the
  value of the key.
- `{}` is an empty value. It means that `osemosys` holds nothing.
- `osemosys` is a top-level key, because its line has no spaces at its start. This guide is about
  the top-level key `osemosys:`.

In a longer file, the lines below `osemosys:` start with spaces. These indented lines belong to
`osemosys:`. This example uses `units:`, which [`units:`](#units) explains:

```yaml
osemosys:
  units:
    capacity: GW
```

Notice these points:

- `units:` has two spaces at its start, so it belongs to `osemosys:`.
- `capacity: GW` has four spaces at its start, so it belongs to `units:`.
- A line belongs to the nearest line above it that has fewer spaces at its start.
- `capacity` is a key, and `GW` is its value.
- `osemosys:` has no `{}` now. When `osemosys:` holds a part, do not write `{}` after it.

Two mistakes stop the run. [Errors that stop the run](#errors-that-stop-the-run) gives the error
for each:

- A tab character at the start of a line. YAML does not accept it, so use spaces. This guide uses
  two spaces for each level.
- A key with no space after its colon. YAML reads `capacity:GW` as one text value, and not as a
  key and a value. Write `capacity: GW`.

### Other top-level keys in the same file

One file can hold more than one top-level key. For example, a translation of a PyPSA model reads
the top-level key `carriers:`. PyPSA is another energy-system modelling tool. The engine reads
only `osemosys:`, so `osemosys:` and `carriers:` can be in the same file.

### The four parts of `osemosys:`

The top-level key `osemosys:` holds four parts. Each part is optional:

| Part | What it states |
| --- | --- |
| `units:` | The real units of your model |
| `sets:` | The canonical set of a raw set whose name is not its OSeMOSYS name |
| `parameters:` | How the engine maps a raw table to a canonical parameter |
| `objects:` | What each technology, fuel, storage and region is |

With `osemosys: {}`, the engine maps what it can automatically. It keeps the rest as extension
tables.

`parameters:` and `objects:` each hold lists. One item of such a list is a row. For example, a
`parameters:` row tells the engine what to do with one raw table. In this guide, "row" alone
means a row of the mappings file, and "table row" means one line of values in a table.

A key inside a part or inside a row is a field. For example, `capacity` is a field of the part
`units:`, and `source` is a field of a `parameters:` row.

Inside `osemosys:`, a part or a field that the engine does not know stops the run.

## Your first run

Here you use tz-oss-interop on a very small model with the smallest mappings file. The text explains
each item of the command and each item of the result. The later examples use the same command.

### Before you start

The console is the window where you type a command. The commands in this guide are for the
console of Linux or macOS. On Windows, use WSL (the Windows Subsystem for Linux), or change each
command to the form that your console needs.

The command of tz-oss-interop is `interop`. This command must work in any directory of your
console. The tz-oss-interop directory is the directory `tz-oss-interop`, which the `git clone` step
of the installation makes on your computer.

1. Do all the steps of [Installation](user-tutorial.md#installation) in the user tutorial.
2. Do not skip the last step, `uv tool install .`. Without it, `interop` works only in the
   tz-oss-interop directory.

tz-oss-interop runs inside a project directory. A project directory is a directory that holds the files
of one piece of work: your model, your mappings file and the results. It also holds
`adapters.yaml`, a file of settings that tz-oss-interop reads at the start of each run.

A run in a directory with no `adapters.yaml` stops with this message:
``adapters.yaml not found at ... Run `interop init <dir>` to scaffold a project.``

So make a project directory first:

1. Go to the directory where you keep your work. Do not use the tz-oss-interop directory.
2. Type `interop` and press Enter. tz-oss-interop shows a menu.
3. Use the arrow keys to select `init`. Then press Enter.
4. At `Target directory?`, type a name for a new directory, for example `my-osemosys-project`.
5. At `Scaffold an example?`, select `none`. This gives a project with no example model.
6. tz-oss-interop shows the menu again. Press Ctrl-C to close it.
7. Type `cd my-osemosys-project` and press Enter.

[Setting up a project](user-tutorial.md#setting-up-a-project) in the user tutorial tells you more.

The new project directory already holds the file `inputs/user_mappings.yaml`. `init` writes it,
with the top-level key `carriers:` for a translation of a PyPSA model. This guide uses a new file,
`inputs/osemosys_mappings.yaml`. The run command tells tz-oss-interop which file to read.

### The model of the first run

The model of the first run is an otoole model. It has one region, two technologies, one year and
one parameter.

To do the first run, make the six files below in your project directory. First, make the
directories `inputs/model/` and `inputs/model/csv/`:

1. Go to the project directory.
2. Type `mkdir -p inputs/model/csv` and press Enter.

Put the otoole configuration file at `inputs/model/config.yaml`:

```yaml
REGION:
  type: set
  dtype: str
TECHNOLOGY:
  type: set
  dtype: str
YEAR:
  type: set
  dtype: int
CapitalCost:
  type: param
  indices: [REGION, TECHNOLOGY, YEAR]
  dtype: float
  default: 0
```

Put these four CSV files in `inputs/model/csv/`. `REGION.csv`:

```csv
VALUE
R1
```

`TECHNOLOGY.csv`:

```csv
VALUE
GASCC
WINDON
```

`YEAR.csv`:

```csv
VALUE
2030
```

`CapitalCost.csv`:

```csv
REGION,TECHNOLOGY,YEAR,VALUE
R1,GASCC,2030,950
R1,WINDON,2030,1300
```

Put the mappings file at `inputs/osemosys_mappings.yaml`. It is the smallest valid file:

```yaml
osemosys: {}
```

The project directory holds other files too. This list shows only the files that the run uses:

```
my-osemosys-project/
  adapters.yaml
  inputs/
    osemosys_mappings.yaml
    model/
      config.yaml
      csv/
        CapitalCost.csv
        REGION.csv
        TECHNOLOGY.csv
        YEAR.csv
```

You can put the mappings file anywhere in your project directory. This guide uses
`inputs/osemosys_mappings.yaml`.

### The two pipelines

A pipeline is a named set of steps that tz-oss-interop runs. A pipeline starts with a model reader, and
ends with a sink. A sink is the code in a pipeline that writes the result. Two pipelines write the canonical stage of a model to a
directory:

| Pipeline | Model that it reads |
| --- | --- |
| `osemosys-csv-to-canonical` | An otoole model: a configuration YAML file and a directory of CSV files |
| `tz-osemosys-to-canonical` | A TZ-format `model.json` file |

### Run the pipeline for an otoole model

1. Put the otoole configuration file at `inputs/model/config.yaml`.
2. Put the CSV files in `inputs/model/csv/`.
3. Write the mappings file at `inputs/osemosys_mappings.yaml`.
4. Go to the project directory.
5. Run this command. [The items of the command](#the-items-of-the-command) explains each item.

```bash
INTEROP_LOG_LEVEL=WARNING interop headless_cli --pipeline osemosys-csv-to-canonical \
  --override 'source.config_path=inputs/model/config.yaml' \
  --override 'source.csv_dir=inputs/model/csv' \
  --override 'sink[0].output_dir=outputs/canonical' \
  --user-mappings-path inputs/osemosys_mappings.yaml
```

Each path in the command starts from the project directory. If you put a file in another place,
change its path in the command.

### The items of the command

| Item | What it does |
| --- | --- |
| `INTEROP_LOG_LEVEL=WARNING` | It tells tz-oss-interop to show the warnings on the console, for this command only. A warning tells you about a problem that does not stop the run. |
| `interop headless_cli` | It runs tz-oss-interop with no menu and no questions. The command line gives all the settings. |
| `--pipeline osemosys-csv-to-canonical` | It chooses the pipeline. |
| `\` at the end of a line | It continues the command on the next line. |
| `--override 'NAME=VALUE'` | It gives a value to one setting of the pipeline. The single quotes keep the text as it is. |
| `source.config_path=inputs/model/config.yaml` | `source` is the model reader of the pipeline. `config_path` is the path of the otoole configuration file. |
| `source.csv_dir=inputs/model/csv` | `csv_dir` is the directory that holds the CSV files. |
| `sink[0].output_dir=outputs/canonical` | `sink[0]` is the first sink of the pipeline, and these pipelines have one sink only. `output_dir` is the directory where it writes the canonical stage. |
| `--user-mappings-path inputs/osemosys_mappings.yaml` | It gives the path of your mappings file. tz-oss-interop calls the mappings file "user mappings" in this option and in its messages. |

Without `INTEROP_LOG_LEVEL=WARNING`, the console shows only the errors. The line
`log_level: INFO` in `adapters.yaml` does not change what the console shows. Only
`INTEROP_LOG_LEVEL` changes it.

### What the first run shows

The console shows one warning:

```
WARNING ... no kind fits 2 technology(ies) in their region, so each keeps an empty kind: R1/GASCC, R1/WINDON
```

Each warning starts with `WARNING`. Then the console names the code in tz-oss-interop that writes the
warning. This guide writes `...` in place of that name.

This warning tells you that the engine cannot infer a `kind` for the two technologies:

- `kind` is an annotation that tells the role of a technology in the power system, for example a
  technology that makes electricity.
- The engine infers `kind` from the activity ratios, and from the fuels that `objects:` marks as
  electricity. This model has no activity ratios, so no kind fits.
- `R1/GASCC` is the technology `GASCC` in the region `R1`.

In the first run, you can ignore this warning. [`kind`](#kind) tells you more.

If the run stops, the console shows a line that starts with `ERROR`, and the run writes no
canonical stage. [Errors that stop the run](#errors-that-stop-the-run) lists the errors.

The run writes these files in `outputs/canonical/`:

```
annotations/fuel.parquet
annotations/region.parquet
annotations/storage.parquet
annotations/technology.parquet
metadata/defaults.parquet
metadata/schema.parquet
metadata/units.parquet
parameters/capital_cost.parquet
sets/region.parquet
sets/technology.parquet
sets/year.parquet
```

Notice that the engine maps the raw table `CapitalCost` to `parameters/capital_cost.parquet`. The
automatic match maps it, because it has the published name and index columns.

The run also writes two reports in the project directory, next to `adapters.yaml`:

- `decisions.md` lists each decision of the engine.
- `validation-report.md` is a second report. This guide does not use it.

The message that `init` shows says that `decisions.md` goes in `outputs/`. With the
`adapters.yaml` that `init` writes, the run writes it in the project directory.
[What the run writes](#what-the-run-writes) tells you more.

### Look at a parquet file

This command shows the canonical table `capital_cost` on the console. It uses uv, the tool that
installs tz-oss-interop, and polars, a library that reads parquet files. Run it in the project
directory:

```bash
uv run --with polars python -c "import polars as pl; print(pl.read_parquet('outputs/canonical/parameters/capital_cost.parquet'))"
```

`--with polars` gives Python the polars library for this one command. To see another table,
change the path between the single quotes.

The command shows:

```
shape: (2, 4)
┌────────┬────────────┬──────┬────────┐
│ region ┆ technology ┆ year ┆ value  │
│ ---    ┆ ---        ┆ ---  ┆ ---    │
│ str    ┆ str        ┆ str  ┆ f64    │
╞════════╪════════════╪══════╪════════╡
│ R1     ┆ GASCC      ┆ 2030 ┆ 950.0  │
│ R1     ┆ WINDON     ┆ 2030 ┆ 1300.0 │
└────────┴────────────┴──────┴────────┘
```

Notice these points:

- `shape: (2, 4)` tells you that the table has 2 table rows and 4 columns.
- The canonical columns `region`, `technology` and `year` come first, in their fixed order. The
  `value` column comes last.
- Under each column name, polars shows the type of the column. `str` is text, and `f64` is a
  number.
- polars writes 950 as `950.0`. It writes `null` for an empty cell.
- For a long table, polars shows only the first table rows and the last table rows.

This guide shows each table without the types. It writes 950 as `950`, and it shows an empty
cell as blank.

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

This command has the same items as the command for an otoole model, with two differences:

- `--pipeline tz-osemosys-to-canonical` chooses the pipeline for a TZ-format model.
- `source.model_json_path` is the path of the `model.json` file. It replaces `config_path` and
  `csv_dir`.

The TZ-format model reader gives each table its OSeMOSYS name, so the tables match
automatically. Usually a mappings file for a TZ-format model needs only `units:` and `objects:`.
[`objects:`](#objects) shows how to write them.

## What the run writes

### The canonical stage

The run writes the canonical stage in the `output_dir` that you give:

| Directory | What it holds |
| --- | --- |
| `sets/` | One file for each canonical set that the model has, with one column, `value` |
| `parameters/` | One file for each canonical parameter that a raw table maps to |
| `extensions/` | One file for each raw table and raw set that stays an extension table |
| `annotations/` | One file each for `technology`, `fuel`, `storage` and `region` |
| `metadata/` | `defaults.parquet`, `units.parquet` and `schema.parquet` |

In `metadata/`, `defaults.parquet` holds the default value of each parameter. `units.parquet`
holds the units that the `units:` part states. `schema.parquet` holds the version of the
canonical schema.

### `decisions.md`

`decisions.md` is a text file in Markdown format, so you can open it in any text editor.
`decisions.md` has five headings. Under each heading is a table, with one table row for each
decision of the engine:

| Heading | What it lists |
| --- | --- |
| Values derived | Each raw set and raw table that the engine mapped, and each annotation that the engine inferred |
| Translator defaults applied | These pipelines record nothing in it |
| User config defaults applied | Each annotation that an `objects:` row gave |
| Components skipped | Each raw table that the engine left out, each table that lost table rows, and each problem that the model reader found |
| Fields not mapped | Each extension table, each technology that got no `kind`, and each value of the model file that the model reader did not read |

The `Note` column of each table row gives the reason.

### The warnings on the console

The console shows one warning for each type of problem that does not stop the run. For example,
a warning names each extension table. A warning gives three names at most, and counts the others. [Problems in the model data that do not stop the run](#problems-in-the-model-data-that-do-not-stop-the-run)
lists each warning.

## Find the canonical names and columns

The canonical schema is in the file
[`interop/plugins/shared/osemosys_canonical_schema.yaml`](../../interop/plugins/shared/osemosys_canonical_schema.yaml).
This file comes with tz-oss-interop. On your computer, it is in the tz-oss-interop directory, at
`tz-oss-interop/interop/plugins/shared/osemosys_canonical_schema.yaml`. You can open it in any
text editor. It has one entry for each canonical set and each canonical parameter. An entry is the group of lines that describes one set or one parameter.

To find the entry for a parameter of your model, search the file for its OSeMOSYS name, for
example `osemosys_name: CapitalCost`. [Names](../developer_documentation/osemosys-canonical-format.md#names)
in the developer document tells why each canonical name has its form. You do not need it to
write a mappings file.

This is the entry for `transport_capital_cost`. In the file, this entry is under the top-level
key `parameters:`, with two more spaces at the start of each line:

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

- `transport_capital_cost` is the canonical name. You write it in the field `canonical` of a
  `parameters:` row. [`parameters:`](#parameters) tells you how.
- `columns` gives the canonical columns, in order. The word after each colon is the canonical
  set that the column holds. Here, `start_region` and `end_region` both hold members of
  the set `region`.
- `osemosys_name` is the OSeMOSYS name of the parameter. The automatic match uses it.
- `osemosys_columns` gives the OSeMOSYS name of each column, at the same position as
  `columns`. OSeMOSYS calls the second region `_REGION`.
- `default` is the value that applies where the model states no value. The default that your
  model declares wins over it.
- `unit` tells the kind of unit. The canonical stage keeps the unit of your model.
- `meaning` tells what the parameter holds.
- `origin` tells which model first had the parameter. Here it is tz-osemosys, so the OSeMOSYS
  v1.0.1 model file does not have `CapitalCostTrade`.

`[REGION, _REGION, FUEL, YEAR]` is a YAML list on one line. A list on one line has its items in
square brackets, with a comma between two items.

Most canonical columns have the name of their set, for example `technology` or `year`. Only
`start_region` and `end_region` have other names. They are in each parameter that holds a
pair of regions.

This table gives the canonical name of each OSeMOSYS set. Use these names in `sets:`, and in the
fields `rename_columns`, `columns_from_name` and `repeat_for_all` of a `parameters:` row:

| OSeMOSYS set | Canonical set |
| --- | --- |
| `REGION` | `region` |
| `TECHNOLOGY` | `technology` |
| `FUEL` | `fuel` |
| `EMISSION` | `pollutant` |
| `MODE_OF_OPERATION` | `operating_mode` |
| `YEAR` | `year` |
| `TIMESLICE` | `timeslice` |
| `SEASON` | `season` |
| `DAYTYPE` | `day_type` |
| `DAILYTIMEBRACKET` | `daily_time_bracket` |
| `STORAGE` | `storage` |
| `REGIONGROUP` | `region_group` |

## The automatic match

You need no `parameters:` row for a raw table when both of these are true:

- Its name is the OSeMOSYS name of a canonical parameter, for example `CapitalCost`.
- Its index columns are the OSeMOSYS columns of that canonical parameter. The order of the
  index columns does not matter.

You need nothing in `sets:` for a raw set when its name is the OSeMOSYS name of a canonical set,
for example `TECHNOLOGY`.

### Example: a raw table that matches automatically

This example shows that the order of the index columns does not stop the automatic match.

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

Notice that `region` is now the first column.

### Example: a raw table with the right name and other index columns

This example shows what happens when a raw table has an extra index column. A raw table has an
extra index column when your model adds a column to a published parameter.

The raw table `FixedCost.csv` has a `MODE_OF_OPERATION` column. The canonical parameter
`fixed_cost` has no such column, so the raw table does not match automatically:

```csv
REGION,TECHNOLOGY,MODE_OF_OPERATION,YEAR,VALUE
R1,GASCC,1,2030,22
```

With `osemosys: {}`, the run writes `extensions/FixedCost.parquet`. An extension table keeps
its own name, but its columns take the canonical set names. `MODE_OF_OPERATION` becomes
`operating_mode`, its canonical set name:

| region | technology | operating_mode | year | value |
| --- | --- | --- | --- | --- |
| R1 | GASCC | 1 | 2030 | 22 |

The run writes this warning:

```
WARNING ... 1 raw table(s) match no canonical parameter by name and key, so each stays an extension table: FixedCost
```

In a message from tz-oss-interop, "key" means the index columns of a raw table. So "by name and key"
means "by the name and the index columns".

To map such a table, write a `parameters:` row. This row keeps the table rows of operating mode
1, and removes the column:

```yaml
osemosys:
  parameters:
    - source: FixedCost
      canonical: fixed_cost
      remove_column: {column: operating_mode, rule: choose, member: "1"}
```

Read the row like this:

- A line that starts with `- ` (a hyphen and a space) starts one row of `parameters:`. The
  indented lines below it belong to the same row.
- The braces hold the fields of `remove_column` on one line. A comma separates two fields.
- A member that is a number must be in double quotes, so write `"1"` and not `1`.

The run then writes `parameters/fixed_cost.parquet`:

| region | technology | year | value |
| --- | --- | --- | --- |
| R1 | GASCC | 2030 | 22 |

Write `operating_mode`, not `MODE_OF_OPERATION`. With `MODE_OF_OPERATION`, the run stops.
[The column names that the operations see](#the-column-names-that-the-operations-see) tells why.
[`remove_column`](#remove_column) explains each field of `remove_column`.

### See what matched

- In `decisions.md`, the table under the heading "Values derived" holds the note
  `matched by name and key` for each automatic match.
- The directory `extensions/` holds each raw table and raw set that did not match.
- The warnings name each extension table.

### Find out why a table did not match

A run writes temporary files in a staging directory. A staging directory is a temporary
directory that tz-oss-interop deletes at the end of the run. The option `--keep-staging`
keeps it, so that you can read what the model reader read.

Know these facts before you do the steps:

- The temporary directory of the system is `/tmp` on Linux and in WSL. On macOS, it is the
  directory in `$TMPDIR`.
- For a TZ-format model, the name of the staging directory starts `interop-tz-osemosys-staging-`.
- `raw/declarations.parquet` has one table row for each raw table that the model reader saw.
- The `key` column holds the list of the index columns of the raw table, in their order.

Do these steps:

1. Put `--keep-staging` at the end of the last line of the run command. Then do the run.
2. Find the directory `interop-osemosys-staging-<random>` in the temporary directory of the
   system. `<random>` is a set of random characters.
3. Show `raw/declarations.parquet` with the command below. In the command, replace
   `abc123` with the random characters of your staging directory. On macOS, also replace `/tmp`
   with the directory in `$TMPDIR`.

   ```bash
   uv run --with polars python -c "import polars as pl; pl.Config.set_fmt_str_lengths(200); print(pl.read_parquet('/tmp/interop-osemosys-staging-abc123/raw/declarations.parquet'))"
   ```

   `pl.Config.set_fmt_str_lengths(200)` stops polars from cutting a long `key`. For the model of
   the first run, the command shows:

   ```
   shape: (1, 3)
   ┌─────────────┬──────────────────────────────────┬─────────┐
   │ name        ┆ key                              ┆ default │
   │ ---         ┆ ---                              ┆ ---     │
   │ str         ┆ list[str]                        ┆ f64     │
   ╞═════════════╪══════════════════════════════════╪═════════╡
   │ CapitalCost ┆ ["REGION", "TECHNOLOGY", "YEAR"] ┆ 0.0     │
   └─────────────┴──────────────────────────────────┴─────────┘
   ```

4. Read the columns `name`, `key` and `default` of the table row for the raw table that did not
   match.
5. Compare `name` and `key` with `osemosys_name` and `osemosys_columns` in the schema entry.

For example, a table row can have the `name` `MaxRampRate` and the `key`
`["REGION", "TECHNOLOGY", "YEAR"]`. It matches only a schema entry with the same `osemosys_name`
and the same `osemosys_columns`.

## `units:`

`units:` states the real units of your model. It has five optional fields: `capacity`,
`energy`, `currency`, `currency_year` and `emissions`. The engine does not convert a value.
It writes the units in `metadata/units.parquet`.

This example states all five units of a model:

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

`currency_year` must be a whole number. Each other unit is text. tz-oss-interop copies it and does not
check it. A field that the file does not state has no table row.

## `sets:`

`sets:` maps a raw set to its canonical set. Write the raw set name, a colon, and the canonical
set name. Write one line for each raw set.

### Example: a set of pollutants with another name

This example shows how to map a raw set whose name is not the OSeMOSYS name.

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

Notice that the canonical table has the canonical set name `pollutant`, and not `GHG`.

`sets:` changes the name of the set only. It does not change the `GHG` column of a raw table.
To change that column, use `rename_columns` on a `parameters:` row.
[`rename_columns`](#rename_columns) shows it.

When `sets:` maps two raw sets to one canonical set, the canonical set holds the members of both.
For example, a raw set `TECHNOLOGY` and a raw set `TECH` that `sets:` maps to `technology` give
one `technology` set.

A raw set with no canonical name stays an extension table. For example, a raw set `UNIT`
gives `extensions/UNIT.parquet`, and this warning:

```
WARNING ... 1 raw set(s) have no canonical set name, so each stays an extension table: UNIT
```

## `parameters:`

### Rows

`parameters:` holds a list of rows. A row tells the engine what to do with one raw table, or with
a group of raw tables.

In YAML, a line that starts with `- ` (a hyphen and a space) starts one item of a list. The
indented lines below it belong to the same item. Each example below shows rows in this form.

The engine counts the rows from 0, so the first row is "row 0". Its messages use these numbers.

### Patterns

A pattern is a short text that describes a group of names. A pattern is a regular expression, a
standard notation for a text search. You do not need to know regular expressions. The table
below gives each
symbol that this guide uses.

The field `source_pattern` of a `parameters:` row takes a pattern. The field `match` of an
`objects:` row also takes a pattern.

The engine searches for the pattern in the name, so a pattern with no `^` and `$` can match
inside a longer name. For example, the pattern `Cost` matches `CapitalCost`, `FixedCost` and
`CostScenario`.

A pattern uses these symbols. Each other character, for example a letter, matches itself. A
pattern is case-sensitive, so `Cost` does not match `COST`.

| Symbol | What it matches | Example pattern | Matches | Does not match |
| --- | --- | --- | --- | --- |
| `^` | The start of the name | `^AAGAS` | `AAGASCC`, `AAGASIMP` | `BBAAGAS` |
| `$` | The end of the name | `GASCC$` | `GASCC`, `AAGASCC` | `GASCC2` |
| `^` and `$` together | The whole name | `^AAGASCC$` | `AAGASCC` | `AAGASCC2`, `XAAGASCC` |
| `[A-Z]` | One capital letter, from A to Z | `^[A-Z]GAS$` | `AGAS`, `BGAS` | `AAGAS`, `aGAS` |
| `[a-z]` | One lowercase letter, from a to z | `^gas-[a-z][a-z]$` | `gas-cc` | `gas-CC`, `gas-ccc` |
| `[0-9]` | One digit, from 0 to 9 | `^Z[0-9]+$` | `Z1`, `Z12` | `Z`, `ZA` |
| `+` | One or more of the item before it | `^Z[0-9]+$` | `Z1`, `Z12` | `Z` |
| `{2}` | Exactly two of the item before it | `^[A-Z]{2}ELEC$` | `AAELEC`, `BBELEC` | `AELEC`, `AAAELEC` |
| `{4}` | Exactly four of the item before it | `^[A-Z]{4}LINK$` | `AABBLINK` | `AALINK` |
| `(?P<name>X)` | A named group, where `X` is a pattern. The characters that `X` matches get the name `name`. | `^CapacityFactor(?P<zone>[A-Z]+)$` | `CapacityFactorNORTH`, with `zone` = `NORTH` | `CapacityFactor`, `CapacityFactorNorth` |
| `?` after a group | The group is optional | `^(?P<country>[A-Z]{2})?GAS$` | `AAGAS`, with `country` = `AA`; `GAS`, with no `country` | `AGAS` |

A named group lets the engine use some characters of a name. For example, `columns_from_name`
writes them into a column. The annotation `location`, which tells where a member is, can also use
them. [`location`](#location) shows how.

In the mappings file, put each pattern in double quotes, for example `"^AAGASCC$"`. Some
symbols of a pattern, for example `[` and `{`, have another meaning in YAML. The quotes keep the
pattern as text.

### The fields of a `parameters:` row

Each row states exactly one of these two fields:

| Field | What it names |
| --- | --- |
| `source` | One raw table, by its exact name, for example `source: AvailabilityPercent` |
| `source_pattern` | Each raw table whose name the pattern finds, for example `source_pattern: "^CapacityFactor(?P<zone>[A-Z]+)$"` |

Each row also states exactly one of these two fields:

| Field | What it does |
| --- | --- |
| `canonical` | It names the canonical parameter that the engine maps the raw table to, for example `canonical: availability_factor`. |
| `ignore: true` | It leaves the raw table out of the canonical stage. |

`canonical` takes a canonical name only. An OSeMOSYS name such as `CapitalCost` stops the run.

### Example: `ignore: true`

This example shows how to leave out a raw table that you do not need in the canonical stage.

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

Notice that `- source: ReportingFlag` starts row 0, and `ignore: true` belongs to the same row.

The run writes no file for `ReportingFlag`. `decisions.md` lists it under the heading
"Components skipped", and the run writes this warning:

```
WARNING ... 1 raw table(s) match a `parameters:` row that says ignore: true, so each is left out: ReportingFlag
```

### The column names that the operations see

A row can give operations. An operation is a change that a row makes to the raw table, for
example a new name for a column. [The operations](#the-operations) lists them.

Before the operations, the engine changes the column names of the raw table:

- A column with the OSeMOSYS name of a set takes the canonical set name. For example,
  `TECHNOLOGY` becomes `technology`, and `MODE_OF_OPERATION` becomes `operating_mode`.
- `_REGION` becomes `end_region`.
- If the canonical parameter has a `start_region` column, `REGION` becomes `start_region`.
- `VALUE` becomes `value`.
- Each other column keeps its name, for example `TECH`, `GHG` or `UNIT`.

So in an operation, write `technology` for a `TECHNOLOGY` column. Write `TECH` for a `TECH`
column.

After the operations, the columns must be the canonical columns of the canonical parameter.
If they are not, the run stops.

### The operations

The engine always does the operations of a row in this order. The order in the file does not
change it.

| Order | Operation | What it does |
| --- | --- | --- |
| 1 | `rename_columns` | It gives a column a new name. |
| 2 | `columns_from_name` | It writes some characters of the raw table name into a new column. |
| 3 | `remove_column` | It removes one column, and combines the table rows that differ only in that column. |
| 4 | `repeat_for_all` | It repeats each value for each member of a canonical set. |
| 5 | `multiply_by` | It multiplies each value, and the default of the raw table, by a number. |

#### `rename_columns`

`rename_columns` gives a column a new name. Write the old name, a colon, and the new name.

This example shows how to rename a column whose name is not an OSeMOSYS set name.

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

`{GHG: pollutant}` writes a key, a colon and a value on one line, in braces. It is the same as
the line `GHG: pollutant`, indented below `rename_columns:`. Put a comma between two keys with
their values, for example `{column: UNIT, rule: sum}`.

The run writes `parameters/emission_rate.parquet`:

| region | technology | pollutant | operating_mode | year | value |
| --- | --- | --- | --- | --- | --- |
| NORTH | GASCC | CO2 | 1 | 2030 | 0.056 |
| SOUTH | GASCC | CO2 | 1 | 2030 | 0.056 |

Notice that the `GHG` column is now `pollutant`.

The line `GHG: pollutant` in `sets:` is necessary. Without it, the canonical set `pollutant` has
no members, and the engine leaves out each table row of `emission_rate`.

#### `columns_from_name`

`columns_from_name` writes some characters of the raw table name into a column. It needs a
`source_pattern` with a named group. A named group is a piece of the pattern in the form
`(?P<name>X)`, where `X` is a pattern. Write the group name, a colon, and the column name.

This example shows how to read a region from the name of a table. Your model needs this when it
has one table for each region.

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

The pattern finds a name that starts with `CapacityFactor` and ends with one or more capital
letters. The group `zone` holds those letters.

The row matches both tables. The engine writes `NORTH` or `SOUTH` into the `region` column, and
puts the two tables into one `parameters/capacity_factor.parquet`:

| region | technology | timeslice | year | value |
| --- | --- | --- | --- | --- |
| NORTH | WINDON | DAY | 2030 | 0.31 |
| NORTH | WINDON | NIGHT | 2030 | 0.42 |
| SOUTH | WINDON | DAY | 2030 | 0.27 |
| SOUTH | WINDON | NIGHT | 2030 | 0.38 |

Notice that one row gives one canonical table from two raw tables.

The value in the new column must be a member of its canonical set. Here, `NORTH` and `SOUTH`
must be in the `REGION` set. If a member is not in its set, the engine leaves out the table
row. [Problems in the model data that do not stop the run](#problems-in-the-model-data-that-do-not-stop-the-run)
tells you more.

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
| `choose` | The value of the table row that holds `member`. The engine leaves out the other table rows. |
| `sum` | The sum of the values |
| `mean` | The mean of the values. Each value has the same weight. |
| `min` | The lowest value |
| `max` | The highest value |

This example shows how to sum the values of the generating units of a technology.

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
| R1 | COALST | 2030 | 1 |

Notice that the two table rows become one, with the value 0.6 + 0.4 = 1.

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

This example shows how to use one value for each region and each year. Your model needs this
when it states a value once, and the canonical parameter needs it for each region and year.

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

Notice that each value appears once for each year.

You can also write `start_region` or `end_region` in `repeat_for_all`. Each one takes the members
of the `region` set.

#### `multiply_by`

`multiply_by` multiplies each value by a number. It also multiplies the default that the model
declares for the raw table.

This example shows how to change a percent into a fraction.

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

### Example: three operations in one row

This example shows that one row can give more than one operation. The engine does them in the
order of [The operations](#the-operations).

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

The line `TECH: technology` in `sets:` is necessary. Without it, the canonical set `technology`
has no members, and the engine leaves out each table row of `capital_cost`.

### The order of the rows

The engine applies these rules to the `parameters:` rows:

- **The first row that matches a raw table wins.** The engine does not try the rows after it.
- **A row stops the automatic match for its canonical parameter.** When a row maps a raw table
  to a canonical parameter, no automatic match writes to that parameter.
- **The engine maps a family to one canonical table only when the defaults agree.** The raw tables that `parameters:` rows map
  to one canonical parameter are a family. They must declare the same default, after
  `multiply_by`. If not, each one stays an extension table.
- **Two raw tables cannot write one canonical table row.** If they do, the run stops.

#### Example: the first row wins

This example shows how to leave out one table of a group that a pattern finds.

The model has `CapacityFactorNORTH` and `CapacityFactorSOUTH`, as in
[`columns_from_name`](#columns_from_name). The first row leaves out the `NORTH` table:

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

This example shows how to use another raw table in place of the table that matches
automatically.

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

If you also add a row that maps `CapitalCost` to `capital_cost`, the two tables write the same
table row. The run then stops:

```
Rows 0, 1 of `parameters:` map the raw tables CapitalCost, OvernightCost to the same capital_cost row (R1, GASCC, 2030). Change the rows so that one raw table gives each canonical row.
```

## `objects:`

`objects:` gives annotations to set members. An annotation tells what a member is, or where it
is. There are four annotations:

- `kind` tells the role of a technology in the power system, from a fixed list.
- `category` is free text that names the type of a technology.
- `carrier` is free text that names the type of a fuel.
- `location` tells where a member is.

[`kind`](#kind), [`category` and `carrier`](#category-and-carrier) and [`location`](#location)
explain each annotation.

Nothing in tz-oss-interop reads the annotations yet. The planned translation to Sienna will read them.
An empty annotation stops nothing today. But give each annotation that you know, because the
translation to Sienna will need it.

`objects:` has four lists. Each list annotates the members of one canonical set, and
accepts only some annotations:

| List | Canonical set | Annotations that it accepts |
| --- | --- | --- |
| `technologies:` | `technology` | `kind`, `category`, `location` |
| `fuels:` | `fuel` | `carrier`, `location` |
| `storages:` | `storage` | `location` |
| `regions:` | `region` | `location` |

Each item of a list is one `objects:` row. The engine counts these rows from 0 in each list.

The run writes one annotation table for each list, in `annotations/`. An annotation table has
one table row for each region and each member, because one member name can be in many regions.

| File | Columns |
| --- | --- |
| `annotations/technology.parquet` | `region`, `technology`, `kind`, `category`, `location` |
| `annotations/fuel.parquet` | `region`, `fuel`, `carrier`, `location` |
| `annotations/storage.parquet` | `region`, `storage`, `location` |
| `annotations/region.parquet` | `region`, `location` |

**Warning:** mark each electricity fuel with `carrier: electricity` in a `fuels:` row. If you do
not, the engine does not know that the fuel is electricity. Then no technology gets
`SupplyTechnology`, and no warning tells you. For example, in a small model with no
`carrier: electricity`, a wind technology that puts out only `ELEC` got the kind `fuel_supply`. A
gas technology that takes in `GAS` and puts out `ELEC` got the kind `conversion`.

### `match`

Each `objects:` row has a `match`, which is a pattern. [Patterns](#patterns) tells you how to
write one. The engine searches for the pattern in the member name. Then:

- The first row that matches a member wins.
- A row gives only the annotations that it states. When a row does not give `kind` or
  `location`, the engine infers it. `category` and `carrier` stay empty.
- A row gives the same annotations in each region.

A search can match inside a longer name. Use `^` for the start of the name and `$` for the
end.

This example shows the result of a pattern that matches more names than you want. The model has
the technologies `AAGASCC`, `AAGASIMP` and `BBWINDON`:

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

Because the first row wins, put a narrow row before a wide row. A narrow row matches few names,
and a wide row matches many names. This example gives one technology its own category:

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

Notice that `AAGASOC` gets the category of row 0, although row 1 also matches it.

### `location`

`location` is a text template. A template is a text with places that the engine fills in. Put a
name in braces, for example `{country}`, and the engine writes a value in its place. You can use two kinds of
names:

- A named group of `match`, for example `{country}` from `(?P<country>[A-Z]{2})`.
- `{region}`, which is the region of the table row.

Put a template in double quotes, for example `"{country}"`. Without the quotes, YAML does not read
the braces as text.

A template can also hold fixed text. This example writes a zone name from the number in a region
name. The regions are `Z1` and `Z2`:

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

Notice that the fixed text `zone-` comes before the number from the group.

#### Example: a country prefix

This example shows how to read a country from the start of each fuel name. Your model needs this
when one region of your model holds more than one country.

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

Each pattern finds a name that is two capital letters and then `ELEC`, `GAS` or `COAL`. The group
`country` holds the two letters.

The run writes `annotations/fuel.parquet`:

| region | fuel | carrier | location |
| --- | --- | --- | --- |
| R1 | AAELEC | electricity | AA |
| R1 | BBELEC | electricity | BB |
| R1 | CCELEC | electricity | CC |
| R1 | AAGAS | natural-gas | AA |
| R1 | CCCOAL | coal | CC |

### `kind`

`kind` tells the role of a technology in the power system. It takes one value from this list:

| `kind` | The technology |
| --- | --- |
| `StorageTechnology` | Charges or discharges a storage |
| `AggregateTransportTechnology` | Moves electricity from one location to another |
| `SupplyTechnology` | Makes electricity |
| `fuel_supply` | Supplies a fuel that is not electricity |
| `export` | Takes in a fuel and puts out nothing |
| `conversion` | Changes one fuel into another at one location |

The first three are type names in Sienna. The planned translation to Sienna will use `kind` to
choose the Sienna type of each technology. Another value, for example `generator`, stops the run.

The engine infers `kind` from the activity ratios, the storage tables and the fuels whose
`carrier` is `electricity`. A row needs `kind` only to change the inference.
[What the engine infers](#what-the-engine-infers) gives the rules.

### `category` and `carrier`

`category` is free text for a technology, for example `gas-combined-cycle` or `wind-onshore`.
The engine never infers a category.

`carrier` is free text for a fuel, for example `natural-gas` or `coal`. The engine never infers
a carrier. One value has a fixed meaning: `carrier: electricity` tells the engine that the fuel is
electricity. The `kind` rules use it.

#### Example: a TZ-format model

This example shows a typical mappings file for a TZ-format model. It holds only `units:` and
`objects:`, because the tables of a TZ-format model match automatically.

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

`units:` here writes its fields and their values on one line, in braces, as in
[`rename_columns`](#rename_columns).

The run writes `annotations/technology.parquet`:

| region | technology | kind | category | location |
| --- | --- | --- | --- | --- |
| NORTH | gas-cc | SupplyTechnology | gas-combined-cycle | NORTH |
| NORTH | gas-import | fuel_supply | | NORTH |
| SOUTH | gas-cc | SupplyTechnology | gas-combined-cycle | SOUTH |
| SOUTH | gas-import | fuel_supply | | SOUTH |

The activity ratios of this model are not shown. They make `gas-cc` take in `natural-gas` and put
out `electricity`. `gas-import` puts out `natural-gas` and takes in nothing.

Notice that the engine infers each `kind`, and that `gas-import` gets no category.

In this model, `location: "{region}"` changes no result. A fuel with no `location` also takes the
location of its region. But when the engine infers the location and the kind of a technology, it
counts only a location that a row gives. So the line matters when rows give other fuels another
location.

For example, the region `R1` holds the fuels `ELEC` and `AAELEC`. The technology `LINK` takes in
`ELEC` and puts out `AAELEC`. Both fuels have `carrier: electricity`, and a row gives `AAELEC` the
location `AA`. The row for `ELEC` changes the result:

| Row for `ELEC` | `kind` of `LINK` | `location` of `LINK` |
| --- | --- | --- |
| `carrier: electricity` | `conversion` | `AA` |
| `carrier: electricity` and `location: "{region}"` | `AggregateTransportTechnology` | `R1~AA` |

### What the engine infers

The engine infers each `location` and `kind` that no row gives. An `objects:` row overrides an
inference.

The engine infers a location like this:

- A region is its own location.
- A fuel and a storage take the location of their region.
- A technology takes the locations that `objects:` rows give to the fuels that it takes in and
  puts out. A fuel location that the engine inferred does not count.
- If the fuels of a technology have two or more locations, `~` joins them, for example `AA~BB`.
  The locations of the lowest operating mode come first. In each mode, the location of the input
  fuel comes first.
- If no fuel of a technology has a location from a row, the technology takes the location of
  its region.

The engine infers a kind from the canonical tables `input_activity_ratio`,
`output_activity_ratio`, `technology_to_storage` and `technology_from_storage`. Only a table row
with a `value` above zero counts. The engine tries the kinds in this order. The first kind that fits wins:

| Order | `kind` | The technology |
| --- | --- | --- |
| 1 | `StorageTechnology` | Has a table row in `technology_to_storage` or `technology_from_storage` |
| 2 | `AggregateTransportTechnology` | Takes in electricity and puts out electricity, and rows give these fuels two or more locations |
| 3 | `SupplyTechnology` | Puts out electricity, and takes in no electricity |
| 4 | `fuel_supply` | Puts out a fuel that is not electricity, and takes in nothing |
| 5 | `export` | Takes in a fuel, and puts out nothing |
| 6 | `conversion` | Takes in and puts out, and rows give its fuels one location or none |

If no kind fits, `kind` stays empty. `decisions.md` lists the technology under the heading
"Fields not mapped", and the run writes a warning:

```
WARNING ... no kind fits 1 technology(ies) in their region, so each keeps an empty kind: R1/COALST
```

A technology with no table rows in the activity ratio tables or the storage tables of a region
gets this warning for that region.

#### Example: the inferred kinds and locations

This example shows the kinds and the locations that the engine infers from the activity ratios.

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

With the `fuels:` rows of [Example: a country prefix](#example-a-country-prefix), and no
`technologies:` row, the engine infers:

| technology | kind | location | Why |
| --- | --- | --- | --- |
| AAGASCC | SupplyTechnology | AA | It puts out electricity, and takes in gas |
| BBWINDON | SupplyTechnology | BB | It puts out electricity, and takes in nothing |
| CCCOALST | SupplyTechnology | CC | It puts out electricity, and takes in coal |
| AABBLINK | AggregateTransportTechnology | AA~BB | It takes in electricity in `AA`, and puts out electricity in `BB` |
| AAGASIMP | fuel_supply | AA | It puts out gas, and takes in nothing |

`decisions.md` gives the rule of each inference under the heading "Values derived", for example:

```
location AA~BB: the locations of the fuels that it takes in and puts out; kind AggregateTransportTechnology: it takes in electricity at one location and puts it out at another
```

#### Example: a row overrides an inference

This example shows how to give a kind where the engine cannot infer one.

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

Notice that `WINDON` has a kind in `NORTH` too.

`decisions.md` lists the row under the heading "User config defaults applied":

```
row 0 of `objects: technologies` gives kind, category
```

## Errors that stop the run

An error in the mappings file stops the run. The run writes no canonical stage. The console
shows the error, also without `INTEROP_LOG_LEVEL`.

An error in the YAML itself contains `Invalid YAML in user mappings file`. The message gives the
line and the column of the error in the file.

The engine checks the mappings file before it reads your model. An error from this check contains
`Invalid user mappings at <file>`. `<file>` is the path of your mappings file. A later line names
the place in the file, for example `osemosys.parameters.0` for row 0 of `parameters:`.

| The error contains | Cause | Fix |
| --- | --- | --- |
| `` found character '\t' that cannot start any token `` | A tab character at the start of a line | Use spaces in place of the tab. |
| `Input should be a valid dictionary` | A field with no space after its colon, for example `capacity:GW` | Put a space after the colon: `capacity: GW`. |
| `Extra inputs are not permitted` | A part or a field that the engine does not know, for example `parameter:` in place of `parameters:` | Correct the name of the part or the field. |
| `` `sets:` names the canonical sets ['technologies'], which do not exist `` | A line in `sets:` names a canonical set that does not exist | Use a canonical set name, for example `technology`. |
| `` row 0 of `parameters:` names the canonical parameter CapitalCost, which the canonical schema does not hold `` | `canonical` holds an OSeMOSYS name or a wrong name | Use the canonical name from the schema file, for example `capital_cost`. |
| `` row 0 of `parameters:` repeats for ['regions'], which are not canonical sets `` | `repeat_for_all` names a column that no canonical parameter has | Use a canonical column name, for example `region`. |
| `remove_column states a member when its rule is choose, and only then` | `member` with a rule other than `choose`, or `choose` with no `member` | Give `member` with `choose` only. |
| `Input should be a valid string` | A `member` that is a number with no quotes | Put the member in quotes, for example `"2"`. |
| `a row states exactly one of source and source_pattern` | A row states both fields, or neither | Keep one of the two. |
| `a row states exactly one of canonical and ignore: true` | A row states both fields, or neither | Keep one of the two. |
| `is not a regular expression` | A `source_pattern` or a `match` that is not a correct pattern | Correct the pattern. |
| `columns_from_name names the groups ['zone'], which source_pattern does not hold` | `columns_from_name` names a group that the pattern does not have | Add the named group to the pattern, for example `(?P<zone>[A-Z]+)`. |
| `` row 0 of `objects: fuels` gives category, which a fuels row does not hold `` | An annotation that the list does not accept | Move the annotation to the correct list. |
| `` Input should be 'StorageTechnology', 'AggregateTransportTechnology', 'SupplyTechnology', 'fuel_supply', 'export' or 'conversion' `` | A `kind` that is not in the list | Use a value from the list. |
| `the location {country} names country, which match does not capture` | `location` names a group that `match` does not have | Add the group to `match`, or use `{region}`. |
| `the location '{}' holds an empty {}` | `location` holds empty braces | Put a group name or `region` in the braces. |

The engine finds the errors below when it applies the file to the model. So each one names the
raw table or the member:

| The error contains | Cause | Fix |
| --- | --- | --- |
| `` Row 0 of `parameters:` cannot map the raw table InvestmentCost to capital_cost. Its operations turn the key TECH into technology, but capital_cost is keyed region, technology, year. `` | After the operations, the columns are not the canonical columns | Add the missing columns with `repeat_for_all` or `columns_from_name`, or remove the extra column with `remove_column`. |
| `The row names the columns MODE_OF_OPERATION, which are not in the key.` | `rename_columns` or `remove_column` names a column that the raw table does not have at that step | Use the column name that the operation sees. [The column names that the operations see](#the-column-names-that-the-operations-see) gives the names. |
| `` Rows 0, 1 of `parameters:` map the raw tables CapitalCost, OvernightCost to the same capital_cost row (R1, GASCC, 2030). `` | Two raw tables write the same canonical table row | Change the rows, so that one raw table gives each table row. |
| `` row 0 of `objects: fuels` gives the location {country}, but its match captures no country for GAS `` | The group is optional in `match`, and it is empty for this member | Remove the `?` after the group, or add a row for this member above this row. |

## Problems in the model data that do not stop the run

A problem in the data of your model never stops the run. The engine leaves out what it cannot
use, and it reports it. To find these problems, read the warnings and `decisions.md`. Run with
`INTEROP_LOG_LEVEL=WARNING` to see the warnings.

| Problem | What the engine does | The warning contains | Heading in `decisions.md` |
| --- | --- | --- | --- |
| A raw table matches no canonical parameter | It keeps an extension table | `match no canonical parameter by name and key` | Fields not mapped |
| A raw set has no canonical name | It keeps an extension table | `have no canonical set name` | Fields not mapped |
| A raw table matches a canonical parameter that a row maps another table to | It keeps an extension table | `row maps instead` | Fields not mapped |
| The raw tables of a family declare different defaults | It keeps each one as an extension table | `map to one canonical parameter but declare different defaults` | Fields not mapped |
| A row says `ignore: true` | It leaves out the raw table | `row that says ignore: true` | Components skipped |
| A value names a set member that its canonical set does not hold, or it has an empty cell | It leaves out that table row, and keeps the others | `hold values whose set member is not in its canonical set` | Components skipped |
| A `parameters:` row matches no raw table | Nothing | `match no raw table` | None |
| A line in `sets:` names no raw set | Nothing | `name no raw set` | None |
| `choose` names a member that no table row holds | That raw table gives no table rows | `choose a member that no row of the raw table holds` | None |
| `repeat_for_all` names a set with no members | That raw table gives no table rows | `repeat each value for a set with no members` | None |
| No kind fits a technology | `kind` stays empty | `no kind fits` | Fields not mapped |

For example, a `CapitalCost` table row for the technology `OIL`, which is not in the
`TECHNOLOGY` set, gives this warning:

```
WARNING ... 1 canonical parameter table(s) hold values whose set member is not in its canonical set, so those values are left out: capital_cost (absent members: OIL)
```

The model readers also report problems in the files of your model. A problem in a file does not
stop the run, with one exception. If the CSV directory holds none of the declared files, the run
stops. The error names `csv_dir`.

For an otoole model, the model reader does this:

| Problem in the files | What the model reader does | Warning |
| --- | --- | --- |
| A set with no CSV file, or a set file that is not CSV | The set has no members | Yes |
| A set file that is empty | The set has no members | No |
| A set file with no `VALUE` column | It leaves out the set | Yes |
| A parameter with no CSV file, or an empty file | The table has no table rows, so the default applies | No |
| A parameter file that is not CSV | The table has no table rows | Yes |
| A header that is not the declared index columns and `VALUE` | The table has no table rows | Yes |
| A `VALUE` that is not a number | It leaves out that table row, and keeps the others | Yes |

For a TZ-format model, the model reader does this. Each problem gives a warning:

| Problem in the file | What the model reader does |
| --- | --- |
| An object that it cannot use, for example a technology with no `id` | It leaves out the object |
| A field that it does not know | It leaves out the field |
| A value that is not a number | It leaves out the value |
| Two values for the same table row, for example from two trades | It keeps the first value |

`decisions.md` lists each problem with a warning under the heading "Components skipped" or
"Fields not mapped". [The sources](../developer_documentation/osemosys-canonical-format.md#the-sources)
in the developer document gives more detail for developers. In that document, a source is a
model reader.

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
- **Keep characters of a name that have no canonical column.** `columns_from_name` must write into a
  canonical column. A country code in a model with one region has no canonical column, so
  write it into a `location` with an `objects:` row.
- **Add a concept that the canonical schema does not have.** `canonical` must name a parameter
  of the schema file.
- **Change a set member.** No operation changes a member name, for example `GAS` to `gas`.
- **Give a region its own annotation for one member.** An `objects:` row gives the same
  annotations in each region. Only `{region}` in a `location` changes from region to region.

A raw table that the mappings file cannot map stays an extension table, with its own name, in
`extensions/`. You lose no data. If the table has no use, a row with `ignore: true` leaves it out.

## Complete example: one region, three countries

This example puts the earlier examples together in one file. Use it as a start for a file that
annotates countries inside one region.

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

| Raw table | Index columns | What the mappings file does with it |
| --- | --- | --- |
| `InputActivityRatio`, `OutputActivityRatio`, `CapitalCost` | The published ones | Nothing. They match automatically. |
| `AvailabilityPercent` | `REGION`, `TECHNOLOGY`, `YEAR` | It maps the table to `availability_factor`, and changes the percent to a fraction. |
| `ResidualCapacity` | `REGION`, `TECHNOLOGY`, `UNIT`, `YEAR` | It sums the table rows of the units. The model has one table row for each unit. |
| `FixedCostFlat` | `TECHNOLOGY` | It repeats the one value for each region and year. |
| `ReportingFlag` | `TECHNOLOGY` | It leaves the table out. The model uses it for reports only. |
| `MaxRampRate` | `REGION`, `TECHNOLOGY`, `YEAR` | Nothing. It stays an extension table, because the canonical schema has no such parameter. |

In the file below, a line that starts with `#` is a comment. The engine does not read a comment.

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

The run writes three warnings. Each warning is correct for this model. You do not need to change
the file.

```
WARNING ... 1 raw set(s) have no canonical set name, so each stays an extension table: UNIT
WARNING ... 1 raw table(s) match a `parameters:` row that says ignore: true, so each is left out: ReportingFlag
WARNING ... 1 raw table(s) match no canonical parameter by name and key, so each stays an extension table: MaxRampRate
```

## Complete example: one region for each zone

This example puts the earlier examples together for a model with more than one region. Use it as
a start for a file where each zone of your model is a region.

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

| Raw table | Index columns | What the mappings file does with it |
| --- | --- | --- |
| `InputActivityRatio`, `OutputActivityRatio`, `TechnologyToStorage`, `TechnologyFromStorage`, `TradeRoute` | The published ones | Nothing. They match automatically. |
| `CapacityFactorNORTH`, `CapacityFactorSOUTH` | `TECHNOLOGY`, `TIMESLICE`, `YEAR` | It reads the region from the table name. |
| `EmissionActivityRatio` | `REGION`, `TECHNOLOGY`, `GHG`, `MODE_OF_OPERATION`, `YEAR` | It renames the pollutant column `GHG`. |
| `CapitalCost` | `REGION`, `TECHNOLOGY`, `SCENARIO`, `YEAR` | It keeps the table rows of one cost scenario. The model has one table row for each scenario. |
| `MinUpTime` | `REGION`, `TECHNOLOGY` | Nothing. It stays an extension table, because the canonical schema has no such parameter. |

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
- `parameters/capital_cost.parquet` holds only the values of the `CENTRAL` table rows. For
  example, it holds 900 for `NORTH`, `GASCC` and `2030`.

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

The run writes two warnings. Each warning is correct for this model. You do not need to change
the file.

```
WARNING ... 1 raw set(s) have no canonical set name, so each stays an extension table: SCENARIO
WARNING ... 1 raw table(s) match no canonical parameter by name and key, so each stays an extension table: MinUpTime
```

## The words

Each term in this list has one meaning in this guide. The guide explains each term where it first
uses it. This list is for reference.

| Word | Meaning |
| --- | --- |
| tz-oss-interop | A tool that translates energy-system models from one format to another. |
| Model | Your OSeMOSYS model: an otoole configuration file and a directory of CSV files, or a TZ-format model. |
| otoole model | A model in the format of otoole: a configuration file that declares each set and parameter, and one CSV file for each set and parameter. |
| TZ-format model | The `model.json` file that tz-osemosys writes. |
| Model reader | The code in tz-oss-interop that reads the files of your model. A pipeline calls it `source`. |
| Engine | The code in tz-oss-interop that reads your mappings file and writes the canonical stage. |
| Mappings file | The YAML file that tells the engine the facts that it cannot find in your model. tz-oss-interop calls it "user mappings" in its options and messages. |
| Key | In YAML, a name before a colon. This guide is about the top-level key `osemosys:`. In a message from tz-oss-interop, "key" means the index columns of a raw table. For example, the note `matched by name and key` means that the name and the index columns match. |
| Top-level key | A YAML key with no spaces at the start of its line, for example `osemosys:` or `carriers:`. |
| Part | One of the four keys inside `osemosys:`: `units:`, `sets:`, `parameters:` and `objects:`. |
| Field | A key inside a part or inside a row, for example `capacity` in `units:` or `source` in a `parameters:` row. |
| Entry | The group of lines that describes one set or one parameter in the schema file. |
| OSeMOSYS name | The name of a set or a parameter in the OSeMOSYS v1.0.1 model file, or in tz-osemosys or OSeMOSYS MUIO for a parameter that only that tool has. The schema file gives it as `osemosys_name`. |
| Raw set | One set of your model, with the name that your model gives it, for example `TECHNOLOGY` or `UNIT`. |
| Set member | One value in a set, for example the technology `GASCC` or the year `2030`. |
| Raw table | One parameter of your model, with its own name, for example `CapitalCost` or `MaxRampRate`. |
| Index columns | The columns of a raw table that name set members, for example `REGION`, `TECHNOLOGY` and `YEAR`. In an otoole model, the `indices` of the parameter give them. |
| `VALUE` | The column of a raw table that holds the number. |
| Canonical schema | The fixed list of sets and parameters that tz-oss-interop knows. Each one has a canonical name, for example `capital_cost`. |
| Canonical set, canonical parameter | A set or a parameter of the canonical schema. |
| Canonical columns | The columns of a canonical parameter, in a fixed order, for example `region, technology, year`. Each canonical table has a `value` column after them. |
| Map | To give a raw set or a raw table a canonical name. |
| Automatic match | The engine maps a raw table with no `parameters:` row, because its name and index columns are the published OSeMOSYS ones. |
| Canonical stage | Your model in the canonical schema: one parquet file for each canonical set and each canonical parameter, with the annotations and the metadata. |
| Canonical table | One parquet file of the canonical stage. |
| Parquet file | A file that holds one table, with the column names and a type for each column. |
| Extension table | A raw table or a raw set that gets no canonical name. The canonical stage keeps it with its own name, so you lose no data. |
| Annotation | A fact about a set member that the model does not state as a parameter, for example that a technology is in the country `AA`. |
| Infer | To find a value from other data in the model. |
| Project directory | The directory that holds the files of one piece of work, with `adapters.yaml`. You run tz-oss-interop in it. |
| Pipeline | A named set of steps that tz-oss-interop runs, from a model reader to a sink. |
| Sink | The code in a pipeline that writes the result. `sink[0]` is the first sink. |
| Console | The window where you type a command. |
| Warning | A line on the console about a problem that does not stop the run. |
| Staging directory | A temporary directory where a run writes temporary files. `--keep-staging` keeps it. |
| Table row | One line of values in a table. |
| `parameters:` row, `objects:` row | One item in the `parameters:` list or an `objects:` list of the mappings file. The engine counts these rows from 0, so the first row is "row 0". |
| Family | The raw tables that `parameters:` rows map to one canonical parameter. |
| Operation | A change that a `parameters:` row makes to a raw table, for example `rename_columns`. |
| Pattern | A regular expression, a standard notation for a text search. It describes a group of names. `source_pattern` and `match` take one. |
| Template | A text with places that the engine fills in, for example `"zone-{number}"` in `location`. |
| Named group | A piece of a pattern in the form `(?P<name>X)`, where `X` is a pattern. It gives a name to the characters that `X` matches. |
| `decisions.md` | The report that lists each decision of the engine, with the reason. |

## More about the canonical stage

The [developer document](../developer_documentation/osemosys-canonical-format.md) describes the
canonical stage in full. It gives each canonical name and its reason, the metadata tables, and
how each model reader reads its files.
