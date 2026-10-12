# The OSeMOSYS mappings guide becomes a tutorial

## The problem

The OSeMOSYS mappings guide, `docs/tutorials/osemosys-mappings.md`, explains each part of
the `osemosys:` mappings file with a different invented model. A reader must read each new
model before the reader can see the point of an example. The guide also holds reference
material, for example error tables and a glossary, that a reader does not read in order.

## The design

The guide becomes a tutorial of short lessons over one base model.

### The base model

The base model is an otoole model with one region, two technologies, two fuels, one mode
of operation and one year. It has three parameters: `CapitalCost`, `InputActivityRatio` and
`OutputActivityRatio`. It uses the published OSeMOSYS names, so `osemosys: {}` maps each
table. The tutorial shows each file of the base model in full.

### The lessons

Each lesson starts from the base model and changes one or two files, the way a real model
differs. Each lesson has the same parts:

1. The changed file.
2. The run with `osemosys: {}`, and the problem that it shows.
3. The smallest mappings file that fixes the problem.
4. The run again, with the fixed table, and each error that the reader can meet.

No lesson needs an earlier lesson, except for the project and the run command of the first
lesson.

| Lesson | Change to the base model | What the lesson teaches |
| --- | --- | --- |
| 1 | None | The project, the run command, the automatic match, a parquet file, `decisions.md` |
| 2 | None | YAML and `units:` |
| 3 | A pollutant set `GHG` and an `EmissionActivityRatio` table | `sets:` and `rename_columns` |
| 4 | `CapitalCost` becomes `InvestmentCost` | A `parameters:` row, and a canonical name from the schema file |
| 5 | An `AvailabilityPercent` table | `multiply_by` |
| 6 | A `ResidualCapacity` table with a `UNIT` column | `remove_column` |
| 7 | A `FixedCost` table with only a `TECHNOLOGY` column | `repeat_for_all` |
| 8 | Two regions, with one availability table for each | Patterns, `source_pattern` and `columns_from_name` |
| 9 | A table for reports only | `ignore: true` |
| 10 | A second capital-cost table | The order of the rows, and a row that stops the automatic match |
| 11 | None | `carrier: electricity` and the inference of `kind` |
| 12 | None | `category` and `match` |
| 13 | `WINDON` has no activity ratio | A `kind` that tz-oss-interop cannot infer |
| 14 | Fuel names that start with a country | `location` and named groups |
| 15 | A TZ-format model | The pipeline for a TZ-format model |

A short section at the end lists what a mappings file cannot do.

### What the tutorial removes

- The two complete examples. The lessons replace them.
- The glossary. Each lesson defines a term where it first uses it.
- The error tables. Each error moves to the lesson of the feature that causes it.

### The output in the tutorial

Each table and each warning in the tutorial comes from a real run of the lesson. A script
outside git makes the lesson files and runs them, so an author can run the lessons again
after a change to tz-oss-interop.
