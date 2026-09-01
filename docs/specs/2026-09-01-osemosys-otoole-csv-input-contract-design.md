# An OSeMOSYS model reaches the translator as an otoole CSV folder and its config

## The problem

The repository holds no OSeMOSYS code. Before anything can map OSeMOSYS to PyPSA, the
project must say what an OSeMOSYS model looks like when it arrives.

OSeMOSYS data comes in three forms: an Excel workbook, a GNU MathProg datafile, and an
otoole CSV folder. otoole converts the first two into the third.

Only the CSV folder states its own schema. Beside the folder sits a config YAML that gives,
for each set and each parameter, the index columns in order, the data type and the default.
That matters more than it looks. The standard OSeMOSYS parameter list differs between
versions, and a real model adds to it. In AETOS, the Africa-Europe Energy Transition model,
156 of the 213 parameters are not in standard OSeMOSYS: the model runs a variant model file
that adds one `YearlyPeakXX` parameter and one `XXReserveMarginTagTechnology` parameter for
each of 78 countries. A source that holds its own parameter list reads none of them.

## The design

### The contract is the CSV folder plus the config

The source takes two parameters. `path` is the CSV folder. `config_path` is the config YAML.

The config is a separate parameter, not a file found inside the folder, for two reasons.
`FilesystemPort` has no directory-listing method, so the source cannot search for a file it
cannot name. And in AETOS the config is neither inside the folder nor named by a fixed name:
the data sits at `AETOS_Runner/CSVFiles/` and the config at
`AETOS_Runner/config_otoole_AETOS.yaml`.

The source reads the config first, then reads what the config declares. It holds no
parameter list of its own.

An Excel workbook, a GNU MathProg datafile and a run with no readable config each raise. A
missing input is not model data.

### Three entry types, and the translator reads two

A config entry carries `type: set`, `type: param` or `type: result`. AETOS declares 11 sets,
213 parameters and 34 result variables. The source reads sets and parameters. It reads no
result.

A set carries `dtype` and `type`. A parameter also carries `indices` and `default`. Either
may carry a `short_name` of at most 31 characters, because GLPK limits a symbol name. The
file on disk normally uses the full name, so the source looks for the full name first and
then for the short name.

A set CSV has one column, `VALUE`. A parameter CSV has the index columns in the order the
config gives, then `VALUE`.

### A declared file the folder does not hold is left out, with a warning

The run carries on. This is the rule in `CLAUDE.md`: a model's data never stops a
translation. The same applies to a file whose header does not match what the config
declares.

### A staged frame keeps the OSeMOSYS column names

The repository convention for a time-series frame is `snapshot` / `component` / `value`. An
OSeMOSYS `CapacityFactor` row is `REGION`, `TECHNOLOGY`, `TIMESLICE`, `YEAR`, `VALUE`, and a
snapshot only exists once somebody decides that a snapshot is a `(YEAR, TIMESLICE)` pair.
That decision belongs to the mapping work, so staging does not make it and keeps the source
names.

The same rule keeps a name whole. `REGION` in AETOS has one member, `REGION1`, and the
country sits in a two-letter prefix on each technology and fuel name: `ATE1` is an Austrian
fuel and `AOBATTN1` an Angolan technology. The rule that reads a country out of a name is
the mapping's, not staging's.

### What goes in which bucket

`State` has two buckets. A later step may read a `source_topology` frame in full. It may not
read a `source_time_series` frame in full; it may only take a summary of one.

A frame goes to `source_time_series` only if it has a `TIMESLICE` column **and** also names
a `TECHNOLOGY`, a `FUEL` or a `STORAGE`. Everything else goes to `source_topology`.

Six AETOS parameters carry a `TIMESLICE` column. The rule splits them as the sizes suggest:

| Parameter | Rows | Bucket |
| --- | --- | --- |
| `CapacityFactor` | 269,920 | `source_time_series` |
| `SpecifiedDemandProfile` | 43,680 | `source_time_series` |
| `YearSplit` | 560 | `source_topology` |
| `Conversionld` / `Conversionlh` / `Conversionls` | 64 each | `source_topology` |

The simpler rule, "anything with a `TIMESLICE` column goes to `source_time_series`", puts
`YearSplit` out of reach. A step needs all of `YearSplit` to work out how many hours of the
year each timeslice stands for.

### The frame stays sparse

An OSeMOSYS CSV holds only the values that differ from the default. The source carries the
default forward from the config and does not fill it in. Filling it would turn 3,158
technologies over 35 years into 110,530 rows for a parameter that may hold ten.

A parameter that sits wholly at its default is a CSV with a header and no rows. AETOS has 18
of them. The source stages an empty frame with the types the config declares, so a reader
sees the right types rather than text.

## What this does not do

This design adds a source and the document that states the contract. It adds no mapping step
and no sink, so it ships no committed `osemosys-to-pypsa` pipeline. The four structural
questions of the mapping (what a TECHNOLOGY becomes, what a FUEL becomes, what a TIMESLICE
becomes, and what a YEAR becomes) stay open.
