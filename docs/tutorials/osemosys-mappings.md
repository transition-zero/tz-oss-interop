# OSeMOSYS Mappings Tutorial

tz-oss-interop is a tool that translates energy-system models from one format to another. This
tutorial is for a modeller who has an OSeMOSYS model and wants to use it with tz-oss-interop. It
teaches you how to write a mappings file for your model.

## Why your model needs a mappings file

Each OSeMOSYS model names and shapes its data in its own way. For example, one model calls its
set of technologies `TECHNOLOGY`, and another model calls it `TECH`. One model gives the
availability of a technology as a fraction, and another model gives it in percent.

So tz-oss-interop first puts each OSeMOSYS model into one standard form. tz-oss-interop calls this
standard form the canonical stage. The canonical stage is a directory of files. It is one fixed
form of an OSeMOSYS model.

tz-oss-interop cannot find some facts in the files of your model. These are examples:

- The real units of your values, for example GW and PJ.
- That your set `TECH` holds the technologies.
- That your parameter `AvailabilityPercent` holds a percent, so tz-oss-interop must multiply each
  value by 0.01.
- Which fuel is electricity.

You write these facts in a mappings file. The mappings file is a text file in YAML format that
you give to tz-oss-interop. YAML is a text format for names and values.

## How this tutorial works

You make one very small OSeMOSYS model, the base model. The base model uses the default names,
so it needs no mappings file. [Lesson 1](#the-canonical-names) explains the default names.

Each lesson then changes the base model in one way, the way a real model differs. Each lesson has
these parts:

1. **The change.** The lesson changes one or two files of the base model.
2. **The problem.** You do a run with an empty mappings file, and you see what goes wrong.
3. **The fix.** You write the smallest mappings file that fixes the problem, and you do the run
   again.
4. **Mistakes.** The lesson shows the errors that you can get, and how to fix each one.

Each lesson starts from the base model, so you can do the lessons in any order. Do
[Set up](#set-up) and [Lesson 1](#lesson-1-a-model-that-needs-no-mappings) first.

You must know your own model: its sets, its parameters and its files. You must be able to edit a
text file and type a command. You do not need to read Python.

## Set up

### Install tz-oss-interop

The console is the window where you type a command. The commands in this tutorial are for the
console of Linux or macOS. On Windows, use WSL (the Windows Subsystem for Linux).

The command of tz-oss-interop is `interop`. This command must work in any directory of your
console.

1. Do all the steps of [Installation](user-tutorial.md#installation) in the user tutorial.
2. Do not skip the last step, `uv tool install .`. Without it, `interop` works only in the
   directory where you cloned tz-oss-interop.

### Make a project directory

tz-oss-interop runs inside a project directory. A project directory holds your model, your
mappings file and the results. It also holds `adapters.yaml`, a file of settings that
tz-oss-interop reads at the start of each run.

1. Go to the directory where you keep your work. Do not use the directory where you cloned
   tz-oss-interop.
2. Type `interop` and press Enter. tz-oss-interop shows a menu.
3. Use the arrow keys to select `init`. Then press Enter.
4. At `Target directory?`, type `my-osemosys-project`.
5. At `Scaffold an example?`, select `osemosys`.
6. tz-oss-interop shows the menu again. Press Ctrl-C to close it.
7. Type `cd my-osemosys-project` and press Enter.

The `osemosys` example puts the base model in `inputs/model/`. It also puts the mappings file
`inputs/osemosys_mappings.yaml` in the project directory. The file `inputs/user_mappings.yaml` is
not for an OSeMOSYS model, and this tutorial does not use it.

### The base model

The base model is an otoole model. otoole is a tool that reads and writes OSeMOSYS models. An
otoole model is a configuration file and a directory of CSV files, with one CSV file for each set
and each parameter.

The base model has one region, two technologies, two fuels, one mode of operation and one year.
The gas plant `GASCC` takes in the fuel `GAS` and puts out the fuel `ELEC`. The wind farm
`WINDON` puts out `ELEC` and takes in nothing. Each value is invented.

The model is a configuration file, `inputs/model/config.yaml`, and eight CSV files in
`inputs/model/csv/`.

`inputs/model/config.yaml`:

```yaml
REGION:
  type: set
  dtype: str
TECHNOLOGY:
  type: set
  dtype: str
FUEL:
  type: set
  dtype: str
MODE_OF_OPERATION:
  type: set
  dtype: int
YEAR:
  type: set
  dtype: int
CapitalCost:
  type: param
  indices: [REGION, TECHNOLOGY, YEAR]
  dtype: float
  default: 0
InputActivityRatio:
  type: param
  indices: [REGION, TECHNOLOGY, FUEL, MODE_OF_OPERATION, YEAR]
  dtype: float
  default: 0
OutputActivityRatio:
  type: param
  indices: [REGION, TECHNOLOGY, FUEL, MODE_OF_OPERATION, YEAR]
  dtype: float
  default: 0
```

The configuration file declares each set and each parameter. For each parameter, `indices` gives
the sets that its values depend on.

Each of the five set files has the heading `VALUE`, then one member on each line:

| File | Its members |
| --- | --- |
| `REGION.csv` | `R1` |
| `TECHNOLOGY.csv` | `GASCC`, `WINDON` |
| `FUEL.csv` | `GAS`, `ELEC` |
| `MODE_OF_OPERATION.csv` | `1` |
| `YEAR.csv` | `2030` |

For example, `TECHNOLOGY.csv` is:

```csv
VALUE
GASCC
WINDON
```

`CapitalCost.csv`:

```csv
REGION,TECHNOLOGY,YEAR,VALUE
R1,GASCC,2030,950
R1,WINDON,2030,1300
```

`InputActivityRatio.csv`:

```csv
REGION,TECHNOLOGY,FUEL,MODE_OF_OPERATION,YEAR,VALUE
R1,GASCC,GAS,1,2030,1.8
```

`OutputActivityRatio.csv`:

```csv
REGION,TECHNOLOGY,FUEL,MODE_OF_OPERATION,YEAR,VALUE
R1,GASCC,ELEC,1,2030,1
R1,WINDON,ELEC,1,2030,1
```

### Keep a copy of the base model

Each lesson changes the base model. Keep a copy, so that you can start each lesson from the base
model:

1. In the project directory, type `cp -r inputs/model inputs/base-model` and press Enter.

To start a lesson from the base model, do these steps.

**Warning:** the first step deletes `inputs/model` and each change that you made in it.

1. Type `rm -rf inputs/model` and press Enter.
2. Type `cp -r inputs/base-model inputs/model` and press Enter.

### Do a run

A run reads your model and your mappings file, and writes the canonical stage. You start each run
from the menu of tz-oss-interop.

**Warning:** a run does not delete the files of an earlier run. An old file can stay and mislead
you. Delete the old result before each run.

#### The first run

1. In the project directory, type `rm -rf outputs/canonical` and press Enter.
2. Type `INTEROP_LOG_LEVEL=WARNING interop` and press Enter. tz-oss-interop shows the menu.
3. Select `translate`.
4. At `Source framework?`, select `osemosys`.
5. At `Destination framework?`, select `osemosys-canonical`.
6. At `Pipeline?`, select `osemosys-csv-to-canonical`.
7. At `source.config_path`, press Enter.
8. At `source.csv_dir`, press Enter.
9. At `sink[0].output_dir`, press Enter.
10. At `User mappings file?`, delete the path `inputs/user_mappings.yaml`.
11. Type `inputs/osemosys_mappings.yaml` and press Enter. The run starts.
12. When the menu shows again, the run is complete. Press Ctrl-C to close the menu.

| Item | What it does |
| --- | --- |
| `rm -rf outputs/canonical` | It deletes the result of the last run. |
| `INTEROP_LOG_LEVEL=WARNING` | It shows the warnings on the console. A warning tells you about a problem that does not stop the run. Without it, the console shows only the errors. |
| `osemosys-csv-to-canonical` | This pipeline reads an otoole model. |
| `User mappings file?` | It asks for the path of your mappings file. tz-oss-interop calls the mappings file "user mappings" in this question and in its messages. |

Each path question shows the path that the run uses. To use another path, type it at the
question:

| Question | What it gives | The path that the run uses |
| --- | --- | --- |
| `source.config_path` | The otoole configuration file | `inputs/model/config.yaml` |
| `source.csv_dir` | The directory that holds the CSV files | `inputs/model/csv` |
| `sink[0].output_dir` | The directory where the run writes the canonical stage | `outputs/canonical` |

If you change `sink[0].output_dir`, delete that directory in step 1.

#### The next runs

The menu keeps your last 30 runs in its history. A run from the history asks the same questions,
and each question shows your answer from that run.

1. In the project directory, type `rm -rf outputs/canonical` and press Enter.
2. Type `INTEROP_LOG_LEVEL=WARNING interop` and press Enter.
3. Select `history`.
4. At `Re-run which past invocation?`, select the top row that names `osemosys-csv-to-canonical`.
   The newest run is at the top.
5. At each question, press Enter.
6. When the menu shows again, press Ctrl-C to close the menu.

Each lesson tells you to do the run. Do the steps of [The next runs](#the-next-runs).

## Lesson 1: a model that needs no mappings

This lesson shows what tz-oss-interop does with a model that uses the default names.

### The run

The example holds the file `inputs/osemosys_mappings.yaml`, with this text:

```yaml
osemosys: {}
```

Do the steps of [The first run](#the-first-run).

`osemosys: {}` is the smallest valid mappings file. It tells tz-oss-interop nothing about your
model. [Lesson 2](#lesson-2-state-the-units) explains the YAML.

The console shows no warning. The run writes these files in `outputs/canonical/`:

```
annotations/fuel.parquet
annotations/region.parquet
annotations/storage.parquet
annotations/technology.parquet
metadata/defaults.parquet
metadata/schema.parquet
metadata/units.parquet
parameters/capital_cost.parquet
parameters/input_activity_ratio.parquet
parameters/output_activity_ratio.parquet
sets/fuel.parquet
sets/operating_mode.parquet
sets/region.parquet
sets/technology.parquet
sets/year.parquet
```

This directory is the canonical stage. Each file holds one table:

| Directory | What it holds |
| --- | --- |
| `sets/` | One table for each set of your model |
| `parameters/` | One table for each parameter of your model |
| `extensions/` | One table for each set and each parameter that tz-oss-interop cannot name. This run has none. |
| `annotations/` | Facts about each technology, fuel, storage and region. [Lesson 11](#lesson-11-mark-the-electricity-fuel) explains them. |
| `metadata/` | The default value of each parameter, the units, and the version of the canonical schema |

### The canonical names

tz-oss-interop gives each set and each parameter a canonical name, in lower case. For example, the
canonical name of the parameter `CapitalCost` is `capital_cost`, and the canonical name of the set
`MODE_OF_OPERATION` is `operating_mode`. The fixed list of canonical names is the canonical
schema.

This tutorial uses these words:

- A **raw table** is one parameter of your model, with the name that your model gives it, for
  example `CapitalCost`.
- A **raw set** is one set of your model, with the name that your model gives it, for example
  `TECHNOLOGY`.
- The **index columns** of a raw table are its columns that name set members, for example
  `REGION`, `TECHNOLOGY` and `YEAR`. A set member is one value in a set, for example `GASCC`.
- A **canonical table** is one file of the canonical stage, for example
  `parameters/capital_cost.parquet`.

A default name is a name that tz-oss-interop knows without a mappings file. For example,
`CapitalCost` is the default name of the canonical parameter `capital_cost`. `EMISSION` is the
default name of the canonical set `pollutant`. Many otoole models use these names, but OSeMOSYS
does not require them. [What tz-oss-interop knows about an OSeMOSYS model](osemosys-default-names.md)
lists each default name.

tz-oss-interop maps a raw table automatically when both of these are true:

- Its name is the default name of a canonical parameter, for example `CapitalCost`.
- Its index columns are the default columns of that parameter. Their order does not matter.

This is the automatic match. Each table of the base model matches automatically, so the mappings
file needs nothing. A mappings file holds only the differences between your model and the default
names.

### Look at a canonical table

A canonical table is a parquet file. A parquet file holds one table, with a type for each column.
A text editor cannot show it. This command shows `capital_cost` on the console:

```bash
uv run --with polars python -c "import polars as pl; print(pl.read_parquet('outputs/canonical/parameters/capital_cost.parquet'))"
```

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

- The columns have the canonical names `region`, `technology` and `year`, in a fixed order. The
  `value` column comes last.
- `shape: (2, 4)` tells you that the table has 2 rows and 4 columns.
- polars writes 950 as `950.0`. It writes `null` for an empty cell.

To see another table, change the path between the single quotes. This tutorial shows each table
without the types. It writes 950 as `950`, and it shows an empty cell as blank:

| region | technology | year | value |
| --- | --- | --- | --- |
| R1 | GASCC | 2030 | 950 |
| R1 | WINDON | 2030 | 1300 |

### Read `decisions.md`

The run also writes the report `decisions.md` in the project directory. It is a text file in
Markdown format. It lists each decision that tz-oss-interop made, with the reason in the `Note`
column. For example, under the heading "Values derived":

```
| `osemosys.parameter.CapitalCost` | `osemosys-canonical.parameter.capital_cost` |  | matched by name and key | osemosys-csv-to-canonical | stage_osemosys_csv |
```

In a message from tz-oss-interop, "key" means the index columns. So `matched by name and key`
tells you that `CapitalCost` matched automatically.

`decisions.md` has five headings:

| Heading | What it lists |
| --- | --- |
| Values derived | Each raw set and raw table that tz-oss-interop mapped, and each annotation that it inferred |
| Translator defaults applied | Nothing. This heading is always empty for an OSeMOSYS model. |
| User config defaults applied | Each annotation that your mappings file gave |
| Components skipped | Each raw table that tz-oss-interop left out, and each table that lost rows |
| Fields not mapped | Each extension table, and each technology that got no kind |

The run also writes `validation-report.md`. This tutorial does not use it.

## Lesson 2: state the units

This lesson shows how to write YAML, and how to tell tz-oss-interop the units of your model.

### The problem

The files of an otoole model do not state units. tz-oss-interop cannot know that your capacity is
in GW and your costs are in EUR of 2022. After the run of Lesson 1, `metadata/units.parquet` has
no rows.

### The fix

1. Write `inputs/osemosys_mappings.yaml` with this text:

   ```yaml
   osemosys:
     units:
       capacity: GW
       energy: PJ
       currency: EUR
       currency_year: 2022
       emissions: Mt
   ```

2. Do the run.

Read the file like this:

- `osemosys` is a key. In YAML, a key is a name. A colon follows the key.
- `osemosys` has no spaces at the start of its line, so it is a top-level key.
- `units:` has two spaces at its start, so it belongs to `osemosys:`.
- `capacity: GW` has four spaces at its start, so it belongs to `units:`. `capacity` is a key,
  and `GW` is its value.
- A line belongs to the nearest line above it that has fewer spaces at its start.

The run writes `metadata/units.parquet`:

| quantity | unit |
| --- | --- |
| capacity | GW |
| energy | PJ |
| currency | EUR |
| currency_year | 2022 |
| emissions | Mt |

Notice these points:

- Each of the five fields is optional. A field that you do not write has no row.
- `currency_year` must be a whole number. Each other unit is text, and tz-oss-interop does not
  check it.
- tz-oss-interop does not convert a value. It only records the units.

In Lesson 1, `osemosys:` held nothing, so it had `{}` after it. When `osemosys:` holds a part,
do not write `{}`.

### The parts of the mappings file

`osemosys:` holds four parts. Each part is optional:

| Part | What it states | Lessons |
| --- | --- | --- |
| `units:` | The units of your model | 2 |
| `sets:` | The canonical name of a raw set | 3 |
| `parameters:` | How tz-oss-interop maps a raw table | 3 to 10 |
| `objects:` | What each technology, fuel, storage and region is | 11 to 14 |

A key inside a part is a field. For example, `capacity` is a field of `units:`.

### Mistakes

A mistake in the mappings file stops the run. The run then writes no canonical stage. The console
shows the cause in red, and then the menu again.

A tab character at the start of a line:

```
Invalid YAML in user mappings file: inputs/osemosys_mappings.yaml:
while scanning for the next token
found character '\t' that cannot start any token
  in "<unicode string>", line 2, column 1:
```

YAML does not accept a tab. Use spaces. This tutorial uses two spaces for each level.

No space after a colon, for example `capacity:GW`:

```
Invalid user mappings at inputs/osemosys_mappings.yaml:
1 validation error for OsemosysCanonicalMappings
osemosys.units
  Input should be a valid dictionary or instance of Units [type=model_type, input_value='capacity:GW', input_type=str]
```

YAML reads `capacity:GW` as one text value, and not as a key and a value. Write `capacity: GW`.
The line `osemosys.units` tells you where the mistake is in the file.

A part that does not exist, for example `unit:` in place of `units:`:

```
osemosys.unit
  Extra inputs are not permitted [type=extra_forbidden, input_value={'capacity': 'GW'}, input_type=dict]
```

Correct the name of the part or the field.

## Lesson 3: a set with another name

This lesson shows how to map a raw set whose name is not the default name. It uses `sets:` and
`rename_columns`.

### The change

Your model adds emissions, and calls its set of pollutants `GHG`. tz-oss-interop does not know
the name `GHG`. Without a mappings file, tz-oss-interop finds the set of pollutants only when its
name is `EMISSION`.

1. Start from the base model.
2. Add these lines to the end of `inputs/model/config.yaml`:

   ```yaml
   GHG:
     type: set
     dtype: str
   EmissionActivityRatio:
     type: param
     indices: [REGION, TECHNOLOGY, GHG, MODE_OF_OPERATION, YEAR]
     dtype: float
     default: 0
   ```

3. Make `inputs/model/csv/GHG.csv`:

   ```csv
   VALUE
   CO2
   ```

4. Make `inputs/model/csv/EmissionActivityRatio.csv`:

   ```csv
   REGION,TECHNOLOGY,GHG,MODE_OF_OPERATION,YEAR,VALUE
   R1,GASCC,CO2,1,2030,0.056
   ```

### The problem

Write `osemosys: {}` in `inputs/osemosys_mappings.yaml`, and do the run. The console shows two
warnings:

```
WARNING ... 1 raw set(s) have no canonical set name, so each stays an extension table: GHG
WARNING ... 1 raw table(s) match no canonical parameter by name and key, so each stays an extension table: EmissionActivityRatio
```

This tutorial writes `...` in place of the text between `WARNING` and the message.

An extension table is a raw set or a raw table that gets no canonical name. tz-oss-interop keeps it
in `extensions/` with its own name, so you lose no data. But a tool that reads the canonical
stage does not find your emissions.

`EmissionActivityRatio` does not match automatically, because the automatic match looks for the
index column `EMISSION`, and your table has `GHG`.

### The fix

```yaml
osemosys:
  sets:
    GHG: pollutant
  parameters:
    - source: EmissionActivityRatio
      canonical: emission_rate
      rename_columns: {GHG: pollutant}
```

Read the file like this:

- `GHG: pollutant` in `sets:` gives the raw set `GHG` the canonical name `pollutant`.
- `parameters:` holds a list. A line that starts with `- ` (a hyphen and a space) starts one item
  of the list. In this tutorial, one item of `parameters:` is a row.
- `source` names the raw table. `canonical` names the canonical parameter.
- `rename_columns` gives the column `GHG` the new name `pollutant`.
- `{GHG: pollutant}` writes a key and its value on one line, in braces.

[Lesson 4](#find-the-canonical-name) tells you how to find a canonical name such as
`emission_rate`.

Do the run. The console shows no warning. The run writes `sets/pollutant.parquet`:

| value |
| --- |
| CO2 |

And `parameters/emission_rate.parquet`:

| region | technology | pollutant | operating_mode | year | value |
| --- | --- | --- | --- | --- | --- |
| R1 | GASCC | CO2 | 1 | 2030 | 0.056 |

### The column names that an operation sees

`rename_columns` is an operation. An operation is a change that a row makes to a raw table.

Before the operations, tz-oss-interop gives canonical names to some columns of the raw table:

- A column with the default name of a set takes the canonical name. For example,
  `MODE_OF_OPERATION` becomes `operating_mode`.
- `VALUE` becomes `value`.
- Each other column keeps its name, for example `GHG`.

So in an operation, write `GHG` for the `GHG` column. Write `operating_mode` for a
`MODE_OF_OPERATION` column.

This table gives the default name of each canonical set:

| Default name | Canonical set |
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

### Mistakes

You need both parts. `sets:` changes the name of the set only. It does not change the `GHG`
column of a raw table. And `rename_columns` without `sets:` gives a canonical set `pollutant`
with no members. With only the `parameters:` row, the run writes an empty `emission_rate`:

```
WARNING ... 1 raw set(s) have no canonical set name, so each stays an extension table: GHG
WARNING ... 1 canonical parameter table(s) hold values whose set member is not in its canonical set, so those values are left out: emission_rate (absent members: CO2)
```

A canonical name that does not exist, for example `GHG: pollutants`, stops the run:

```
Value error, `sets:` names the canonical sets ['pollutants'], which do not exist
```

A raw set name that your model does not have, for example `GHGS: pollutant`, does not stop the
run. With the `parameters:` row of the fix, the console shows:

```
WARNING ... 1 entry(ies) of `sets:` name no raw set: GHGS
WARNING ... 1 raw set(s) have no canonical set name, so each stays an extension table: GHG
WARNING ... 1 canonical parameter table(s) hold values whose set member is not in its canonical set, so those values are left out: emission_rate (absent members: CO2)
```

The first warning tells you the cause. The other two warnings come from it: the set `GHG` gets no
canonical name, so the canonical set `pollutant` has no members.

## Lesson 4: a table with another name

This lesson shows how to map a raw table whose name is not the default name. It also shows how to
find a canonical name.

### The change

The model calls its capital cost `InvestmentCost`.

1. Start from the base model.
2. Rename `inputs/model/csv/CapitalCost.csv` to `InvestmentCost.csv`.
3. In `inputs/model/config.yaml`, change the line `CapitalCost:` to `InvestmentCost:`.

### The problem

Write `osemosys: {}`, and do the run. The console shows:

```
WARNING ... 1 raw table(s) match no canonical parameter by name and key, so each stays an extension table: InvestmentCost
```

The run writes `extensions/InvestmentCost.parquet`, and no `parameters/capital_cost.parquet`.

### Find the canonical name

[What tz-oss-interop knows about an OSeMOSYS model](osemosys-default-names.md) gives the
canonical name of each default name. Find `CapitalCost` in its table of parameters.

The page copies the canonical schema file, `interop/plugins/shared/osemosys_canonical_schema.yaml`,
in the directory where you cloned tz-oss-interop. The schema file has one entry for each canonical
set and each canonical parameter.

Search the schema file for the default name, `osemosys_name: CapitalCost`. The search also finds
longer names that start with `CapitalCost`, for example `CapitalCostStorage`. Use the entry where
the line stops after `CapitalCost`:

```yaml
  capital_cost:
    columns:
      region: region
      technology: technology
      year: year
    osemosys_name: CapitalCost
    osemosys_columns: [REGION, TECHNOLOGY, YEAR]
    default: 0
    unit: currency per capacity
    meaning: Overnight investment cost of one unit of new capacity.
    origin: OSeMOSYS v1.0.1
```

Read it like this:

- `capital_cost` is the canonical name. You write it in `canonical`.
- `columns` gives the canonical columns, in order. The word after each colon is the canonical set
  that the column holds.
- `osemosys_name` and `osemosys_columns` are the default name and the default columns. The
  automatic match looks for them.
- `default` is the value where the model states no value. The default that your model declares
  wins over it.
- `meaning` tells what the parameter holds.

### The fix

```yaml
osemosys:
  parameters:
    - source: InvestmentCost
      canonical: capital_cost
```

Do the run. The console shows no warning, and the run writes `parameters/capital_cost.parquet`:

| region | technology | year | value |
| --- | --- | --- | --- |
| R1 | GASCC | 2030 | 950 |
| R1 | WINDON | 2030 | 1300 |

`decisions.md` gives the row under "Values derived":

```
row 0 of `parameters:` maps the raw table InvestmentCost to capital_cost: no operations
```

tz-oss-interop counts the rows from 0, so the first row is "row 0". Its messages use these
numbers.

### Find out why a table did not match

If a raw table does not match automatically, compare it with the schema entry:

1. Compare the name of the raw table with `osemosys_name`.
2. Compare the `indices` of the parameter in `config.yaml` with `osemosys_columns`.

A difference in either one stops the automatic match.

### Mistakes

The default name in `canonical`, for example `canonical: CapitalCost`, stops the run:

```
Value error, row 0 of `parameters:` names the canonical parameter CapitalCost, which the canonical schema does not hold
```

Use the canonical name, `capital_cost`.

A `source` that names no raw table, for example `InvestmentCosts`, does not stop the run. The
console shows:

```
WARNING ... 1 row(s) of `parameters:` match no raw table: row 0 (InvestmentCosts)
WARNING ... 1 raw table(s) match no canonical parameter by name and key, so each stays an extension table: InvestmentCost
```

## Lesson 5: a percent in place of a fraction

This lesson shows how to multiply each value of a raw table by a number. It uses `multiply_by`.

### The change

The model gives the availability of each technology in percent. The canonical parameter
`availability_factor` holds a fraction from 0 to 1.

1. Start from the base model.
2. Add these lines to the end of `inputs/model/config.yaml`:

   ```yaml
   AvailabilityPercent:
     type: param
     indices: [REGION, TECHNOLOGY, YEAR]
     dtype: float
     default: 100
   ```

3. Make `inputs/model/csv/AvailabilityPercent.csv`:

   ```csv
   REGION,TECHNOLOGY,YEAR,VALUE
   R1,GASCC,2030,92
   R1,WINDON,2030,35
   ```

### The problem

Write `osemosys: {}`, and do the run. The console shows:

```
WARNING ... 1 raw table(s) match no canonical parameter by name and key, so each stays an extension table: AvailabilityPercent
```

A row with only `source` and `canonical` maps the table, but the values are wrong:

| region | technology | year | value |
| --- | --- | --- | --- |
| R1 | GASCC | 2030 | 92 |
| R1 | WINDON | 2030 | 35 |

The value 92 is not a fraction from 0 to 1. The console shows no warning about it.

### The fix

```yaml
osemosys:
  parameters:
    - source: AvailabilityPercent
      canonical: availability_factor
      multiply_by: 0.01
```

Do the run. `parameters/availability_factor.parquet` holds:

| region | technology | year | value |
| --- | --- | --- | --- |
| R1 | GASCC | 2030 | 0.92 |
| R1 | WINDON | 2030 | 0.35 |

`multiply_by` also multiplies the default that your model declares. In
`metadata/defaults.parquet`, the default of `availability_factor` is 1, which is 100 multiplied by
0.01. Without `multiply_by`, it is 100.

`metadata/defaults.parquet` has one row for each canonical parameter. polars shows only the first
five rows and the last five rows of a long table. This command shows only the row of
`availability_factor`:

```bash
uv run --with polars python -c "import polars as pl; print(pl.read_parquet('outputs/canonical/metadata/defaults.parquet').filter(pl.col('parameter') == 'availability_factor'))"
```

The command shows:

```
shape: (1, 4)
┌───────────┬─────────────────────┬─────────┬──────────────┐
│ kind      ┆ parameter           ┆ default ┆ default_from │
│ ---       ┆ ---                 ┆ ---     ┆ ---          │
│ str       ┆ str                 ┆ f64     ┆ str          │
╞═══════════╪═════════════════════╪═════════╪══════════════╡
│ parameter ┆ availability_factor ┆ 1.0     ┆ null         │
└───────────┴─────────────────────┴─────────┴──────────────┘
```

## Lesson 6: a table with an extra column

This lesson shows how to remove a column that the canonical parameter does not have. It uses
`remove_column`.

### The change

The model gives the residual capacity of each generating unit, in a `UNIT` column. The canonical
parameter `residual_capacity` has no such column.

1. Start from the base model.
2. Add these lines to the end of `inputs/model/config.yaml`:

   ```yaml
   UNIT:
     type: set
     dtype: str
   ResidualCapacity:
     type: param
     indices: [REGION, TECHNOLOGY, UNIT, YEAR]
     dtype: float
     default: 0
   ```

3. Make `inputs/model/csv/UNIT.csv`:

   ```csv
   VALUE
   U1
   U2
   ```

4. Make `inputs/model/csv/ResidualCapacity.csv`:

   ```csv
   REGION,TECHNOLOGY,UNIT,YEAR,VALUE
   R1,GASCC,U1,2030,0.6
   R1,GASCC,U2,2030,0.4
   ```

### The problem

Write `osemosys: {}`, and do the run. The console shows:

```
WARNING ... 1 raw set(s) have no canonical set name, so each stays an extension table: UNIT
WARNING ... 1 raw table(s) match no canonical parameter by name and key, so each stays an extension table: ResidualCapacity
```

### The fix

```yaml
osemosys:
  parameters:
    - source: ResidualCapacity
      canonical: residual_capacity
      remove_column: {column: UNIT, rule: sum}
```

`remove_column` has two fields here. A comma separates them. `column` names the column to remove.
`rule` tells tz-oss-interop how to get one value from the rows that differ only in that column.

Do the run. `parameters/residual_capacity.parquet` holds:

| region | technology | year | value |
| --- | --- | --- | --- |
| R1 | GASCC | 2030 | 1 |

Notice that the two rows become one, with the value 0.6 + 0.4 = 1.

The console still shows the warning for `UNIT`. This is correct. No canonical set holds units, so
the set `UNIT` stays an extension table.

### The rules

Each rule gives a different value from the same two rows:

| `remove_column` | value |
| --- | --- |
| `{column: UNIT, rule: sum}` | 1 |
| `{column: UNIT, rule: mean}` | 0.5 |
| `{column: UNIT, rule: min}` | 0.4 |
| `{column: UNIT, rule: max}` | 0.6 |
| `{column: UNIT, rule: choose, member: U2}` | 0.4 |

`mean` gives each value the same weight. `choose` keeps only the rows of one member, and needs the
field `member`.

### Mistakes

A row with no `remove_column` stops the run:

```
Row 0 of `parameters:` cannot map the raw table ResidualCapacity to residual_capacity. Its operations turn the key region, technology, UNIT, year into region, technology, UNIT, year, but residual_capacity is keyed region, technology, year.
```

After the operations, the columns must be the canonical columns. Here the `UNIT` column is extra.

`choose` with no `member`, or `member` with another rule, stops the run:

```
Value error, remove_column states a member when its rule is choose, and only then
```

A member that is a number must be in double quotes. Write `member: "2"`, not `member: 2`. Without
the quotes, the run stops:

```
osemosys.parameters.0.remove_column.member
  Input should be a valid string [type=string_type, input_value=2, input_type=int]
```

## Lesson 7: a table with a missing column

This lesson shows how to repeat each value for each member of a set. It uses `repeat_for_all`.

### The change

The model states one fixed cost for each technology, with no region and no year. The canonical
parameter `fixed_cost` needs a value for each region and each year. The model also has a second
year.

1. Start from the base model.
2. Add these lines to the end of `inputs/model/config.yaml`:

   ```yaml
   FixedCost:
     type: param
     indices: [TECHNOLOGY]
     dtype: float
     default: 0
   ```

3. Make `inputs/model/csv/FixedCost.csv`:

   ```csv
   TECHNOLOGY,VALUE
   GASCC,22
   WINDON,35
   ```

4. Change `inputs/model/csv/YEAR.csv` to:

   ```csv
   VALUE
   2030
   2035
   ```

### The problem

Write `osemosys: {}`, and do the run. `FixedCost` has the default name, but not the default
columns. So the console shows:

```
WARNING ... 1 raw table(s) match no canonical parameter by name and key, so each stays an extension table: FixedCost
```

### The fix

```yaml
osemosys:
  parameters:
    - source: FixedCost
      canonical: fixed_cost
      repeat_for_all: [region, year]
```

`[region, year]` is a YAML list on one line. A comma separates two items. Write canonical column
names in `repeat_for_all`.

Do the run. `parameters/fixed_cost.parquet` holds:

| region | technology | year | value |
| --- | --- | --- | --- |
| R1 | GASCC | 2030 | 22 |
| R1 | WINDON | 2030 | 35 |
| R1 | GASCC | 2035 | 22 |
| R1 | WINDON | 2035 | 35 |

Notice that each value appears once for each year.

### Mistakes

A row with no `repeat_for_all` stops the run:

```
Row 0 of `parameters:` cannot map the raw table FixedCost to fixed_cost. Its operations turn the key technology into technology, but fixed_cost is keyed region, technology, year.
```

A name that is not a canonical set, for example `regions`, stops the run:

```
Value error, row 0 of `parameters:` repeats for ['regions'], which are not canonical sets
```

## Lesson 8: one table for each region

This lesson shows how to read a region from the name of a raw table. It uses a pattern,
`source_pattern` and `columns_from_name`.

### The change

The model has two regions. It gives the availability of each region in its own table, and the
name of the table ends with the region.

1. Start from the base model.
2. Change `inputs/model/csv/REGION.csv` to:

   ```csv
   VALUE
   R1
   R2
   ```

3. Add these lines to the end of `inputs/model/config.yaml`:

   ```yaml
   AvailabilityFactorR1:
     type: param
     indices: [TECHNOLOGY, YEAR]
     dtype: float
     default: 1
   AvailabilityFactorR2:
     type: param
     indices: [TECHNOLOGY, YEAR]
     dtype: float
     default: 1
   ```

4. Make `inputs/model/csv/AvailabilityFactorR1.csv`:

   ```csv
   TECHNOLOGY,YEAR,VALUE
   GASCC,2030,0.92
   WINDON,2030,0.35
   ```

5. Make `inputs/model/csv/AvailabilityFactorR2.csv`:

   ```csv
   TECHNOLOGY,YEAR,VALUE
   GASCC,2030,0.9
   WINDON,2030,0.41
   ```

### The problem

Write `osemosys: {}`, and do the run. The console shows:

```
WARNING ... 2 raw table(s) match no canonical parameter by name and key, so each stays an extension table: AvailabilityFactorR1, AvailabilityFactorR2
WARNING ... no kind fits 2 technology(ies) in their region, so each keeps an empty kind: R2/GASCC, R2/WINDON
```

The second warning tells you that `R2` has no activity ratios. Ignore it in this lesson.
[Lesson 13](#lesson-13-give-a-kind-that-tz-oss-interop-cannot-infer) explains it.

### Patterns

A pattern is a short text that describes a group of names. A pattern is a regular expression, a
standard notation for a text search. The field `source_pattern` takes a pattern in place of the
one name of `source`.

A letter or a digit in a pattern matches itself. These symbols have a special meaning:

| Symbol | What it matches | Example pattern | Matches | Does not match |
| --- | --- | --- | --- | --- |
| `^` | The start of the name | `^GAS` | `GASCC` | `AAGAS` |
| `$` | The end of the name | `ELEC$` | `ELEC`, `BBELEC` | `ELEC2` |
| `[A-Z]` | One capital letter, from A to Z | `^[A-Z]GAS$` | `AGAS` | `AAGAS`, `aGAS` |
| `[0-9]` | One digit, from 0 to 9 | `^R[0-9]$` | `R1`, `R2` | `R`, `R12` |
| `+` | One or more of the item before it | `^R[0-9]+$` | `R1`, `R12` | `R` |
| `{2}` | Exactly two of the item before it | `^[A-Z]{2}ELEC$` | `BBELEC` | `BELEC` |
| `(?P<name>X)` | A named group. The characters that the pattern `X` matches get the name `name`. | `^AvailabilityFactor(?P<zone>R[0-9]+)$` | `AvailabilityFactorR1`, with `zone` = `R1` | `AvailabilityFactor` |

Without `^` and `$`, a pattern can match inside a longer name. A pattern is case-sensitive.

### The fix

```yaml
osemosys:
  parameters:
    - source_pattern: "^AvailabilityFactor(?P<zone>R[0-9]+)$"
      canonical: availability_factor
      columns_from_name: {zone: region}
```

Read the row like this:

- The pattern finds each name that starts with `AvailabilityFactor` and ends with `R` and one or
  more digits.
- The group `zone` holds `R1` or `R2`.
- `columns_from_name` writes the group `zone` into the canonical column `region`.
- Put each pattern in double quotes. Some symbols, for example `[` and `{`, have another meaning
  in YAML.

Do the run. One row maps the two raw tables into one `parameters/availability_factor.parquet`:

| region | technology | year | value |
| --- | --- | --- | --- |
| R1 | GASCC | 2030 | 0.92 |
| R1 | WINDON | 2030 | 0.35 |
| R2 | GASCC | 2030 | 0.9 |
| R2 | WINDON | 2030 | 0.41 |

The value in the new column must be a member of its set. Here, `R1` and `R2` must be in
`REGION.csv`. If a value is not a member, tz-oss-interop leaves out that row and gives a warning.

### Mistakes

The raw tables that rows map to one canonical parameter must declare the same default. If
`AvailabilityFactorR2` declares the default 0.5, each table stays an extension table:

```
WARNING ... 2 raw table(s) map to one canonical parameter but declare different defaults, so each stays an extension table: AvailabilityFactorR1, AvailabilityFactorR2
```

`columns_from_name` must name a group of the pattern. `{area: region}` stops the run:

```
Value error, columns_from_name names the groups ['area'], which source_pattern does not hold
```

A pattern that is not correct stops the run. For example, a missing `)`:

```
Value error, the pattern '^AvailabilityFactor(?P<zone>R[0-9]+$' is not a regular expression: missing ), unterminated subpattern at position 19
```

## Lesson 9: a table that you do not need

This lesson shows how to leave out a raw table. It uses `ignore: true`.

### The change

The model has a table that only its reports use.

1. Start from the base model.
2. Add these lines to the end of `inputs/model/config.yaml`:

   ```yaml
   ReportingFlag:
     type: param
     indices: [TECHNOLOGY]
     dtype: float
     default: 0
   ```

3. Make `inputs/model/csv/ReportingFlag.csv`:

   ```csv
   TECHNOLOGY,VALUE
   GASCC,1
   ```

### The problem

Write `osemosys: {}`, and do the run. The table stays an extension table:

```
WARNING ... 1 raw table(s) match no canonical parameter by name and key, so each stays an extension table: ReportingFlag
```

### The fix

```yaml
osemosys:
  parameters:
    - source: ReportingFlag
      ignore: true
```

Do the run. The run writes no file for `ReportingFlag`. The console shows:

```
WARNING ... 1 raw table(s) match a `parameters:` row that says ignore: true, so each is left out: ReportingFlag
```

`decisions.md` lists the table under the heading "Components skipped".

### Mistakes

A row states `canonical` or `ignore: true`, and never both. A row with both stops the run:

```
Value error, a row states exactly one of canonical and ignore: true
```

## Lesson 10: two tables for one parameter

This lesson shows how a row changes the automatic match, and what happens when two rows give the
same value.

### The change

The model has two capital-cost tables. `CapitalCost` matches automatically, but you want the
values of `OvernightCost`.

1. Start from the base model.
2. Add these lines to the end of `inputs/model/config.yaml`:

   ```yaml
   OvernightCost:
     type: param
     indices: [REGION, TECHNOLOGY, YEAR]
     dtype: float
     default: 0
   ```

3. Make `inputs/model/csv/OvernightCost.csv`:

   ```csv
   REGION,TECHNOLOGY,YEAR,VALUE
   R1,GASCC,2030,870
   R1,WINDON,2030,1200
   ```

### The problem

Write `osemosys: {}`, and do the run. `capital_cost` holds the values of `CapitalCost`, 950 and
1300. `OvernightCost` stays an extension table.

### The fix

```yaml
osemosys:
  parameters:
    - source: OvernightCost
      canonical: capital_cost
```

Do the run. `parameters/capital_cost.parquet` holds the values of `OvernightCost`:

| region | technology | year | value |
| --- | --- | --- | --- |
| R1 | GASCC | 2030 | 870 |
| R1 | WINDON | 2030 | 1200 |

A row stops the automatic match for its canonical parameter. So `CapitalCost` stays an extension
table, and the console shows:

```
WARNING ... 1 raw table(s) match a canonical parameter that a `parameters:` row maps instead, so each stays an extension table: CapitalCost
```

### The rules for the rows

tz-oss-interop applies these rules to the `parameters:` rows:

- The first row that matches a raw table wins. tz-oss-interop does not try the rows after it.
- A row stops the automatic match for its canonical parameter.
- If two raw tables write the same canonical row, both stay extension tables.

To leave out one table of a group that a pattern finds, write an `ignore: true` row for that
table. Put it above the row with the pattern.

### Mistakes

A row for each table gives two values for the same canonical row:

```yaml
osemosys:
  parameters:
    - source: CapitalCost
      canonical: capital_cost
    - source: OvernightCost
      canonical: capital_cost
```

The run does not stop. Both raw tables stay extension tables, so the canonical stage has no
`capital_cost`. The console shows:

```
WARNING ... 2 raw table(s) map to one canonical parameter but give the same canonical row, so each stays an extension table: CapitalCost, OvernightCost
```

`decisions.md` names one canonical row only, the first one in the order of the columns:

```
rows 0, 1 of `parameters:` map the raw tables CapitalCost, OvernightCost to the same capital_cost row (R1, GASCC, 2030), so each stays an extension table
```

Here `WINDON` also has two values. Change the rows so that one raw table gives each canonical
row.

## Lesson 11: mark the electricity fuel

This lesson shows how to tell tz-oss-interop which fuel is electricity. It uses `objects:` and
`carrier`.

### The problem

The base model needs no change. Look at `annotations/technology.parquet` from the run of
[Lesson 1](#lesson-1-a-model-that-needs-no-mappings):

| region | technology | kind | category | location |
| --- | --- | --- | --- | --- |
| R1 | GASCC | conversion |  | R1 |
| R1 | WINDON | fuel_supply |  | R1 |

An annotation is a fact about a set member that the model does not state as a parameter. `kind`
is an annotation that tells the role of a technology in the power system. tz-oss-interop infers
`kind` from the activity ratios. To infer a value is to find it from other data in the model.

Both kinds are wrong:

- `WINDON` makes electricity, but it got `fuel_supply`. This is the kind of a technology that
  supplies a fuel that is not electricity.
- `GASCC` makes electricity, but it got `conversion`. This is the kind of a technology that
  changes one fuel into another fuel.

The console shows no warning. The cause is that the name `ELEC` does not tell tz-oss-interop that
the fuel is electricity.

### The fix

```yaml
osemosys:
  objects:
    fuels:
      - match: "^ELEC$"
        carrier: electricity
```

Read the file like this:

- `objects:` holds lists. `fuels:` is the list for the members of the set `FUEL`.
- One item of the list is a row. `match` is a pattern that finds member names.
  [Lesson 8](#patterns) explains patterns.
- `carrier` is an annotation for a fuel. The value `electricity` tells tz-oss-interop that the
  fuel is electricity.

Do the run. `annotations/technology.parquet` holds:

| region | technology | kind | category | location |
| --- | --- | --- | --- | --- |
| R1 | GASCC | SupplyTechnology |  | R1 |
| R1 | WINDON | SupplyTechnology |  | R1 |

And `annotations/fuel.parquet` holds:

| region | fuel | carrier | location |
| --- | --- | --- | --- |
| R1 | GAS |  | R1 |
| R1 | ELEC | electricity | R1 |

`decisions.md` gives the reason for each kind under "Values derived", for example:

```
kind SupplyTechnology: it puts out electricity, and takes in no electricity
```

**Warning:** mark each electricity fuel of your model with `carrier: electricity`. Without it,
each kind can be wrong, and no warning tells you.

### How tz-oss-interop infers a kind

tz-oss-interop reads the canonical tables `input_activity_ratio`, `output_activity_ratio`,
`technology_to_storage` and `technology_from_storage`. Only a row with a value above zero counts.
It tries the kinds in this order, and the first kind that fits wins:

| Order | `kind` | The technology |
| --- | --- | --- |
| 1 | `StorageTechnology` | Has a row in `technology_to_storage` or `technology_from_storage` |
| 2 | `AggregateTransportTechnology` | Takes in electricity and puts out electricity, and rows give these fuels two or more locations |
| 3 | `SupplyTechnology` | Puts out electricity, and takes in no electricity |
| 4 | `fuel_supply` | Puts out a fuel that is not electricity, and takes in nothing |
| 5 | `export` | Takes in a fuel, and puts out nothing |
| 6 | `conversion` | Takes in and puts out, and rows give its fuels one location or none |

[Lesson 14](#lesson-14-read-a-country-from-a-fuel-name) explains locations.

## Lesson 12: name the type of each technology

This lesson shows how to give each technology a category, and why the order of the rows matters.
It uses `technologies:` and `category`.

### The problem

The base model needs no change. In the run of Lesson 11, the `category` column is empty.
tz-oss-interop never infers a category. Only your mappings file can give one.

### The fix

```yaml
osemosys:
  objects:
    fuels:
      - match: "^ELEC$"
        carrier: electricity
    technologies:
      - match: "^GASCC$"
        category: gas-combined-cycle
      - match: "^[A-Z]+$"
        category: other
```

`category` is free text. You choose the words.

Do the run. `annotations/technology.parquet` holds:

| region | technology | kind | category | location |
| --- | --- | --- | --- | --- |
| R1 | GASCC | SupplyTechnology | gas-combined-cycle | R1 |
| R1 | WINDON | SupplyTechnology | other | R1 |

Notice that row 1 also matches `GASCC`, but `GASCC` gets the category of row 0. The first row that
matches a member wins. So put a row for one member above a row that matches many members.

A row gives the same annotations in each region.

### The lists and their annotations

`objects:` has four lists. Each list accepts only some annotations:

| List | Members of the canonical set | Annotations that it accepts |
| --- | --- | --- |
| `technologies:` | `technology` | `kind`, `category`, `location` |
| `fuels:` | `fuel` | `carrier`, `location` |
| `storages:` | `storage` | `location` |
| `regions:` | `region` | `location` |

### Mistakes

An annotation that the list does not accept stops the run. For example, `carrier` in a
`technologies:` row:

```
Value error, row 0 of `objects: technologies` gives carrier, which a technologies row does not hold
```

## Lesson 13: give a kind that tz-oss-interop cannot infer

This lesson shows how to give a kind in your mappings file. It uses `kind`.

### The change

The model has no activity ratio for `WINDON`.

1. Start from the base model.
2. Change `inputs/model/csv/OutputActivityRatio.csv` to:

   ```csv
   REGION,TECHNOLOGY,FUEL,MODE_OF_OPERATION,YEAR,VALUE
   R1,GASCC,ELEC,1,2030,1
   ```

### The problem

Write the mappings file of [Lesson 11](#lesson-11-mark-the-electricity-fuel), and do the run. The
console shows:

```
WARNING ... no kind fits 1 technology(ies) in their region, so each keeps an empty kind: R1/WINDON
```

`R1/WINDON` is the technology `WINDON` in the region `R1`. `WINDON` has no row in the activity
ratio tables, so no kind fits, and its `kind` stays empty. `decisions.md` lists it under "Fields
not mapped".

### The fix

```yaml
osemosys:
  objects:
    fuels:
      - match: "^ELEC$"
        carrier: electricity
    technologies:
      - match: "^WINDON$"
        kind: SupplyTechnology
```

Do the run. The console shows no warning. `annotations/technology.parquet` holds:

| region | technology | kind | category | location |
| --- | --- | --- | --- | --- |
| R1 | GASCC | SupplyTechnology |  | R1 |
| R1 | WINDON | SupplyTechnology |  | R1 |

A `kind` in a row wins over the inferred kind. `decisions.md` lists it under "User config defaults
applied":

```
row 0 of `objects: technologies` gives kind
```

### Mistakes

`kind` takes one value from the table in [Lesson 11](#how-tz-oss-interop-infers-a-kind). Another
value, for example `generator`, stops the run:

```
osemosys.objects.technologies.0.kind
  Input should be 'StorageTechnology', 'AggregateTransportTechnology', 'SupplyTechnology', 'fuel_supply', 'export' or 'conversion'
```

## Lesson 14: read a country from a fuel name

This lesson shows how to tell tz-oss-interop where each fuel is. It uses `location` and a named
group.

### The change

The model has one region, but its fuels are in two countries. The first two letters of each fuel
name give the country: `AAGAS` is gas in the country `AA`, and `BBELEC` is electricity in the
country `BB`.

1. Start from the base model.
2. Change `inputs/model/csv/FUEL.csv` to:

   ```csv
   VALUE
   AAGAS
   BBELEC
   ```

3. Change `inputs/model/csv/InputActivityRatio.csv` to:

   ```csv
   REGION,TECHNOLOGY,FUEL,MODE_OF_OPERATION,YEAR,VALUE
   R1,GASCC,AAGAS,1,2030,1.8
   ```

4. Change `inputs/model/csv/OutputActivityRatio.csv` to:

   ```csv
   REGION,TECHNOLOGY,FUEL,MODE_OF_OPERATION,YEAR,VALUE
   R1,GASCC,BBELEC,1,2030,1
   R1,WINDON,BBELEC,1,2030,1
   ```

### The problem

Write a mappings file that marks the electricity fuel:

```yaml
osemosys:
  objects:
    fuels:
      - match: "ELEC$"
        carrier: electricity
```

Do the run. Each fuel and each technology gets the location `R1`, the region:

| region | fuel | carrier | location |
| --- | --- | --- | --- |
| R1 | AAGAS |  | R1 |
| R1 | BBELEC | electricity | R1 |

tz-oss-interop cannot find the countries in the files of the model.

### The fix

```yaml
osemosys:
  objects:
    fuels:
      - match: "^(?P<country>[A-Z]{2})ELEC$"
        carrier: electricity
        location: "{country}"
      - match: "^(?P<country>[A-Z]{2})GAS$"
        location: "{country}"
```

Read the file like this:

- The pattern `^(?P<country>[A-Z]{2})ELEC$` finds a name that is two capital letters and then
  `ELEC`. The named group `country` holds the two letters.
- `location` is a template. A template is a text with places that tz-oss-interop fills in. Put a
  group name in braces, and tz-oss-interop writes the characters of that group in its place.
- Put a template in double quotes.

Do the run. `annotations/fuel.parquet` holds:

| region | fuel | carrier | location |
| --- | --- | --- | --- |
| R1 | AAGAS |  | AA |
| R1 | BBELEC | electricity | BB |

And `annotations/technology.parquet` holds:

| region | technology | kind | category | location |
| --- | --- | --- | --- | --- |
| R1 | GASCC | SupplyTechnology |  | AA~BB |
| R1 | WINDON | SupplyTechnology |  | BB |

Notice that each technology takes the locations of the fuels that it takes in and puts out.
`GASCC` takes in gas in `AA` and puts out electricity in `BB`, so `~` joins the two locations.

### How tz-oss-interop infers a location

tz-oss-interop infers each location that no row gives:

- A region is its own location.
- A fuel and a storage take the location of their region.
- A technology takes the locations that rows give to its fuels. A fuel location that
  tz-oss-interop inferred does not count.
- If no fuel of a technology has a location from a row, the technology takes the location of its
  region.

A template can also hold fixed text, for example `"zone-{country}"`. It can use `{region}`, which
is the region of the row.

### Mistakes

A template that names a group that `match` does not have stops the run. For example,
`location: "{zone}"`:

```
Value error, the location {zone} names zone, which match does not capture
```

A template with no double quotes stops the run. YAML reads `{country}` as a key with no value:

```
osemosys.objects.fuels.0.location
  Input should be a valid string [type=string_type, input_value={'country': None}, input_type=dict]
```

## Lesson 15: a TZ-format model

This lesson shows how to use a TZ-format model. A TZ-format model is the `model.json` file that
tz-osemosys writes. tz-osemosys is the OSeMOSYS tool of TransitionZero.

### The model

This `model.json` holds the capital costs of the base model:

```json
{
  "id": "tutorial",
  "time_definition": {"id": "time", "years": [2030], "timeslices": []},
  "regions": [{"id": "R1"}],
  "commodities": [],
  "impacts": [],
  "technologies": [
    {"id": "GASCC", "operating_modes": [], "capex": {"R1": {"2030": 950}}},
    {"id": "WINDON", "operating_modes": [], "capex": {"R1": {"2030": 1300}}}
  ],
  "storage": [],
  "trade": []
}
```

Put the model at `inputs/model.json`.

### The run

Write this mappings file:

```yaml
osemosys:
  units: {capacity: MW, currency: USD}
```

`units:` here writes its fields on one line, in braces.

The pipeline `tz-osemosys-to-canonical` reads a TZ-format model. It has no default path for the
model, so you must type that path. Do these steps:

1. In the project directory, type `rm -rf outputs/canonical` and press Enter.
2. Type `INTEROP_LOG_LEVEL=WARNING interop` and press Enter.
3. Select `translate`.
4. At `Source framework?`, select `tz-osemosys`.
5. At `Destination framework?`, select `osemosys-canonical`.
6. At `Pipeline?`, select `tz-osemosys-to-canonical`.
7. At `source.model_json_path`, type `inputs/model.json` and press Enter.
8. At `sink[0].output_dir`, press Enter.
9. At `User mappings file?`, delete the path `inputs/user_mappings.yaml`.
10. Type `inputs/osemosys_mappings.yaml` and press Enter.
11. When the menu shows again, press Ctrl-C to close the menu.

To do this run again, do the steps of [The next runs](#the-next-runs). At step 4, select the top
row that names `tz-osemosys-to-canonical`.

`parameters/capital_cost.parquet` holds:

| region | technology | year | value |
| --- | --- | --- | --- |
| R1 | GASCC | 2030 | 950 |
| R1 | WINDON | 2030 | 1300 |

tz-oss-interop gives each field of a TZ-format model its default name. For example, `capex`
becomes `CapitalCost`. So each table matches automatically, and you do not need `sets:` or
`parameters:`. A mappings file for a TZ-format model usually needs only `units:` and `objects:`.

The console shows one warning:

```
WARNING ... no kind fits 2 technology(ies) in their region, so each keeps an empty kind: R1/GASCC, R1/WINDON
```

This model has no activity ratios. [Lesson 13](#lesson-13-give-a-kind-that-tz-oss-interop-cannot-infer)
shows how to give a kind.

## What a mappings file cannot do

A mappings file can rename, remove a column, repeat and multiply. It cannot do these things:

- **Change an equation of the model.** tz-oss-interop copies parameter values. It does not read or
  change the equations of your model.
- **Use a formula other than a factor.** `multiply_by` takes one number. You cannot add a number,
  or calculate a value from two values.
- **Join two tables.** Each row reads one raw table at a time. A row cannot look up a value in a
  second table, for example to divide a cost by a capacity.
- **Calculate a weighted mean.** The rule `mean` gives each value the same weight.
- **Add a parameter that the canonical schema does not have.** `canonical` must name a parameter
  of the schema file.
- **Change a set member.** No operation changes a member name, for example `GAS` to `gas`.
- **Give a different annotation in each region.** An `objects:` row gives the same annotations in
  each region. Only `{region}` in a `location` changes from region to region.

A raw table that the mappings file cannot map stays an extension table, so you lose no data. If
you do not need the table, leave it out with `ignore: true`, as in
[Lesson 9](#lesson-9-a-table-that-you-do-not-need).
