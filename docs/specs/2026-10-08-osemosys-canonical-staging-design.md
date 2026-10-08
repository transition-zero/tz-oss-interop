# Any OSeMOSYS model stages into one canonical form through a user mappings file

## The problem

OSeMOSYS has no fixed schema. Each variant of the model declares its own parameters in
its own model file. Two real models show how far two variants can differ:

- A model in the otoole CSV format declares 213 parameters. 156 of them exist only in
  that model, one family for each of 78 countries. Its single region holds every country,
  and a two-letter prefix on each name gives the country.
- TransitionZero's own format (the TZ format) is the `model.json` that the tz-osemosys
  library writes. It defines 25 parameters that OSeMOSYS v1.0.1 does not have. In the TZ
  example model, the regions are grid zones, and trade routes join them.

The two models also store their data in two file formats. A translation to Sienna, or
to PyPSA, cannot handle every variant in every rule. It needs one form of an OSeMOSYS
model to read.

This design gives that form: the canonical stage. Each source removes its file format.
A user mappings file then states how the model's own schema and objects map into the
canonical stage. Only that file knows the variant.

## The words

- **The schema level** is the parameters of a model: each name, its key and its default
  value. The key of a parameter is the list of sets that its value depends on.
- **The object level** is the members of the sets, such as a technology called
  `ATNGCCPH1`, and the values with their units.
- **The source model** is the model as its file holds it.
- **The raw stage** is the source model after the source removes the file format. It
  keeps the model's own names, keys and set members.
- **The canonical schema** is the schema that this repository defines for an OSeMOSYS
  model.
- **The canonical stage** is a model in the canonical schema, with its annotations and
  its metadata. Every later translation reads only the canonical stage.
- **The mappings engine** is the shared code that turns the raw stage into the canonical
  stage.

## The design

```
source model ──source──▶ raw stage ──mappings engine + user mappings file──▶ canonical stage
 (file format)           (model's own schema)                                 (canonical schema)
```

### Rules that TransitionZero's platform follows

TransitionZero's modelling platform turns one neutral data set into an OSeMOSYS model or a
PyPSA network. A PyPSA import pipeline turns a network back into that data set. No part of
the platform reads an OSeMOSYS model. These of its rules shape this design:

1. Every record has the same fixed key columns, and the literal `NA` fills an axis that a
   record does not use. So a fixed set of dimensions can hold any parameter.
2. The platform keeps what a technology is in a catalogue, not in its parameters. A
   technology there has a storage flag and a chain of parent categories.
3. The mappings file of the PyPSA import works at the object level only. It maps buses to
   nodes, lines to edges, and carriers to a technology and an input fuel.
4. The platform converts its units to GW, TWh, M$ and Mt for OSeMOSYS only. So the units
   of an OSeMOSYS model are the choice of its modeller.
5. The role of a technology decides which concept a value becomes, not the shape of the
   value. The same PyPSA availability series becomes a capacity factor for some
   technologies and an availability factor for others.
6. The platform finds some roles from names: the slugs `transmission` and
   `interconnection`, the word `export`, and a mode called `charging`. An arbitrary model
   has free-text names, so this design finds roles from the structure of the model.

### The canonical schema

The canonical schema is a data file in this repository,
`interop/plugins/shared/osemosys_canonical_schema.yaml`. A pydantic class loads it and
checks it. The vocabulary can then grow without a change to the code.

| Part | Count | Origin |
| --- | --- | --- |
| Sets | 12 | The 11 sets of OSeMOSYS v1.0.1, and `REGIONGROUP` from tz-osemosys v0.4.1 |
| Core parameters | 54 | The input parameters of OSeMOSYS v1.0.1 |
| Extension parameters | 28 | 25 from tz-osemosys v0.4.1, and 3 from OSeMOSYS MUIO model v5.7 |

OSeMOSYS v1.0.1 (`OSeMOSYS/OSeMOSYS_GNU_MathProg`, `src/osemosys.txt`) declares 61
parameters. The current `master` of that repository declares the same 61. Seven of them
are not inputs, so the canonical schema leaves them out:

- `ResultsPath` is the path of the output files.
- `DiscountFactor`, `DiscountFactorMid`, `DiscountFactorStorage`,
  `DiscountFactorMidStorage`, `CapitalRecoveryFactor` and `PvAnnuity` are values that the
  model calculates for itself.

The 25 extensions from tz-osemosys v0.4.1 are these:

- Trade: `TradeLossBetweenRegions`, `TotalAnnualMaxTradeInvestment`,
  `ResidualTradeCapacity`, `OperationalLifeTrade`, `CapitalCostTrade`,
  `DiscountRateTrade`, `TradeCapacityToActivityUnit`, `TotalTradeAnnualActivityUpperLimit`,
  `TotalTradeAnnualActivityLowerLimit`, `AvailabilityFactorTrade`,
  `TotalAnnualMinCapacityFactorTrade`.
- Technology: `CapacityAdditionalMaxGrowthRate`, `CapacityAdditionalMinGrowthRate`,
  `CapacityAdditionalMaxFloor`, `TotalAnnualMinCapacityFactor`,
  `TechnologyMinProductionTarget`, `TechnologyMaxProductionTarget`.
- Storage: `StorageMaxHours`, `StorageBalanceDay`, `StorageBalanceSeason`,
  `StorageBalanceYear`.
- Region groups: `RegionGroupTagRegion`, `RegionGroupREMinProductionTarget`,
  `AnnualEmissionLimitRegionGroup`, `AnnualExogenousEmissionRegionGroup`.

The 3 extensions from OSeMOSYS MUIO model v5.7 (`OSeMOSYS/MUIO`,
`WebAPP/SOLVERs/model.v.5.7.txt`) are `TechnologyActivityByModeUpperLimit`,
`TechnologyActivityByModeLowerLimit` and `TechnologyActivityDecreaseByModeLimit`.

**The rule for an extension.** A published OSeMOSYS variant must define it, and its name
must not already mean a different thing. The schema describes each entry by its meaning,
and names the variant that publishes it. The schema never names a model that uses it.

`StorageTag` and `StorageChargeDuration` are not in version 1. A GitHub code search found
no published file that defines them. A model that has them stages them as extension
tables.

The 34 result variables are not in the canonical schema, because staging reads inputs
only.

Each entry gives the name, the key, the default value, the kind of unit, the meaning and
the origin:

```yaml
schema_version: 1
parameters:
  CapitalCost:
    key: [REGION, TECHNOLOGY, YEAR]
    default: 0
    unit: currency per capacity
    meaning: Overnight investment cost of one unit of new capacity.
    origin: OSeMOSYS v1.0.1
  TradeLossBetweenRegions:
    key: [REGION, _REGION, FUEL, YEAR]
    default: 0
    unit: fraction
    meaning: Share of a traded fuel lost on the route from REGION to _REGION.
    origin: tz-osemosys v0.4.1
```

**The key is fixed.** Every canonical table of a parameter has exactly the key columns of
its entry, then `VALUE`. A key with a second region names that column `_REGION`, as otoole
and the TZ format both do. A source table can have a different name and a different key.
The user mappings file changes it into the canonical name and key.

**Default values.** Each canonical table stays sparse: it holds only the rows that the
source model holds. The default value of each parameter for this model goes into the
metadata. The mappings engine takes it from the raw declarations. The schema's own default
applies only when the model declares none. A model can declare a different default: the
otoole case-study model declares 0.075 for `DiscountRate`.

**Units.** The schema records the kind of unit, for example "currency per capacity".
Staging does not convert values. The user mappings file states the real units, and the
metadata keeps them. A later translation converts them.

### The two sources

Both sources are `StagedSource` plugins. Each one reads its input through `self._fs`,
writes the raw stage, calls the mappings engine, and gives back a `State` that holds the
canonical stage. Each source declares the mappings schema in its constructor, so the
loader asks the user for the file. A file that holds only `osemosys: {}` is valid.

#### `stage_osemosys_csv` reads the otoole CSV format

It has two parameters: `config_path`, the otoole config YAML, and `csv_dir`, the
directory of CSV files. Two parameters are necessary for two reasons:

- A model can keep its config YAML outside the CSV directory. The otoole case-study model
  does.
- The `FilesystemPort` cannot list a directory, so the source cannot search for the
  config YAML.

The source reads the config YAML first. It reads the entries of `type: set` and
`type: param`, and it does not read `type: result`. It finds each CSV file by its full
name, then by its `short_name`.

| Input | What the source does |
| --- | --- |
| `config_path` does not end in `.yaml` or `.yml` | It stops with an error |
| `csv_dir` names a file, for example an `.xlsx` workbook or a MathProg datafile | It stops with an error |
| A declared parameter with no CSV file | It keeps the declaration with no rows, so the default value applies |
| A CSV header that is not the declared key and `VALUE` | It leaves out that table, records `COMPONENT_SKIPPED`, and writes a warning |

#### `stage_tz_osemosys_json` reads the TZ format

Its parameter is one `model.json` file. A fixed table in the source maps each field path
of the TZ format to a raw table, for example `technologies[].capex` to `CapitalCost`. The
object that holds a field decides the table. `capex` on a storage maps to
`CapitalCostStorage`, and `capex` on a trade maps to `CapitalCostTrade`.

The source keeps its own copy of the field table, and the table names the tz-osemosys
version that it follows. The source cannot import the table from tz-osemosys, because
`pip download tz-osemosys==0.4.1` finds no version on PyPI.

The source does these things:

- It removes the `{"is_composed": true, "data": ...}` wrapper from each value.
- It expands each `"*"` wildcard into one row for each member of its set.
- It writes the field defaults of tz-osemosys as the raw declarations.
- For a field that the table does not hold, it records `NOT_MAPPED` and writes a warning.

### The layout in `staging_dir`

```
raw/sets/<SET>.parquet                   one column, VALUE
raw/parameters/<name>.parquet            the model's own key columns, then VALUE
raw/declarations.parquet                 name, key and default value of each parameter
canonical/sets/<SET>.parquet             one column, VALUE
canonical/parameters/<Name>.parquet      the canonical key, then VALUE, sparse
canonical/extensions/<name>.parquet      each raw table that nothing maps
canonical/annotations/<SET>.parquet      one table each for TECHNOLOGY, FUEL, STORAGE, REGION
canonical/metadata/defaults.parquet      the default value of each parameter for this model
canonical/metadata/units.parquet         the units from the user mappings file
canonical/metadata/schema.parquet        the canonical schema version
```

In `State`, each canonical or extension table whose key holds `TIMESLICE` goes into
`source_time_series`, so it stays lazy. Every other table goes into `source_topology`.

### The user mappings file

The file has four parts under one key, `osemosys:`. So the project's `user_mappings.yaml`
can hold other mappings schemas too. The loader checks the whole file against each schema,
and pydantic ignores the keys that a schema does not declare. A pydantic class,
`OsemosysCanonicalMappings`, checks the `osemosys:` part.

| Part | Level | What it states |
| --- | --- | --- |
| `sets:` | Schema | The canonical set of a raw set that has a different name |
| `parameters:` | Schema | How a raw table becomes a canonical parameter |
| `objects:` | Object | What each technology, fuel, storage and region is |
| `units:` | Object | The real units of the model |

#### The automatic match

The mappings engine maps a raw table automatically when its name and its key equal an
entry of the canonical schema. It maps a raw set automatically when its name equals a
canonical set. It records one `VALUE_DERIVED` event for each automatic match, with the note
"matched by name and key".

The file therefore holds only the real differences of a model. A row overrides an
automatic match: it can give a table a different canonical parameter, or it can say
`ignore: true`.

#### `parameters:` rows

A row names one raw table with `source`, or a family of raw tables with `source_pattern`.
A pattern is a Python regular expression with named groups. The row then names a
`canonical` parameter, or it says `ignore: true`.

The row can list operations. The engine applies them in this order:

| Order | Operation | What it does |
| --- | --- | --- |
| 1 | `rename_columns` | It gives a column its canonical set name |
| 2 | `columns_from_name` | It writes a named group of the pattern into a column |
| 3 | `remove_column` | It removes an extra set with a rule: `choose` one member, `mean`, `sum`, `min` or `max` |
| 4 | `repeat_for_all` | It repeats each value for each member of a missing set |
| 5 | `multiply_by` | It multiplies each value, and the default value, by a number |

After the operations, the columns must equal the canonical key. An invented example:

```yaml
osemosys:
  parameters:
    - source: InvestmentCost
      canonical: CapitalCost
      rename_columns: {TECH: TECHNOLOGY}
      repeat_for_all: [REGION, YEAR]
      multiply_by: 0.001
```

Rules for the rows:

- The first row that matches a raw table wins.
- When a row maps any raw table to a canonical parameter, no automatic match writes to
  that parameter.
- A family of tables merges into one canonical table only when all its tables declare the
  same default value. If the defaults differ, the engine stages the family as extension
  tables, records `NOT_MAPPED`, and writes a warning.

#### `objects:` rows

The annotation tables describe the set members. Their key is `REGION` and the member,
because one technology name can exist in many regions. Each row matches names exactly or
with a pattern, and gives annotations:

| Part | Annotations |
| --- | --- |
| `technologies:` | `kind`, from a closed list, and `category`, free text such as `gas-combined-cycle` |
| `fuels:` | `carrier`, free text, where the value `electricity` has a fixed meaning; and `location` |
| `storages:` | `location` |
| `regions:` | `location` |

A `location` can use a named group of the pattern, for example `"{country}"`, or the
region, `"{REGION}"`.

The closed list of `kind` has six values:

| `kind` | The technology |
| --- | --- |
| `storage` | Connects to a storage through `TechnologyToStorage` or `TechnologyFromStorage` |
| `link` | Takes in electricity at one location and puts it out at a different location |
| `generator` | Puts out electricity, and takes in a fuel that is not electricity, or nothing |
| `supply` | Puts out a fuel that is not electricity, and takes in nothing |
| `export` | Takes in a fuel, and puts out nothing |
| `conversion` | Takes in and puts out at one location, and is none of the above |

#### The inferences

The engine infers each annotation that the structure of the model can show. A row
overrides an inference. Each inference records a `VALUE_DERIVED` event with a note that
names its rule, so `decisions.md` shows it.

- A region is its own location.
- A fuel, a storage and a technology take the location of their region, when no row gives
  one.
- A technology whose fuels have a row-given location takes the location of those fuels.
  If the fuels have two locations, the technology takes both, written `A~B`. In its
  lowest mode of operation, A is the location of the input fuel and B is the location of
  the output fuel.
- The `kind` of a technology comes from its rows in `InputActivityRatio`,
  `OutputActivityRatio`, `TechnologyToStorage` and `TechnologyFromStorage`. The engine
  tries the kinds in the order of the table above, and the first that fits wins.

An interconnector in the otoole case-study model needs no row. It takes in Austrian
electricity and puts out German electricity, so its location is `AT~DE` and its `kind` is
`link`.

#### `units:`

`units:` states `capacity`, `energy`, `currency`, `currency_year` and `emissions`. Each
one is optional. The metadata keeps what the file states.

#### Two examples

The otoole case-study model:

```yaml
osemosys:
  units: {capacity: GW, energy: PJ, currency: USD, currency_year: 2021, emissions: Mt}
  objects:
    fuels:
      - match: "^(?P<country>[A-Z]{2})E[123]$"
        carrier: electricity
        location: "{country}"
      - match: "^(?P<country>[A-Z]{2})NG$"
        carrier: natural-gas
        location: "{country}"
    technologies:
      - match: "^[A-Z]{2}NGCC"
        category: gas-combined-cycle
```

The TZ format:

```yaml
osemosys:
  units: {capacity: GW, energy: TWh, currency: USD, emissions: Mt}
  objects:
    fuels:
      - match: "^electricity$"
        carrier: electricity
    technologies:
      - match: "^gas-combined-cycle$"
        category: gas-combined-cycle
```

### Reporting

The engine records one event for each raw table and one for each annotated set member. It
does not record one for each value row, because a table can hold 1.7 million rows.

| Decision | Event kind |
| --- | --- |
| A table maps automatically | `VALUE_DERIVED`, note "matched by name and key" |
| A table maps through a `parameters:` row | `VALUE_DERIVED`, with a note that names the row and its operations |
| A row says `ignore: true` | `COMPONENT_SKIPPED` |
| Nothing maps a table, so it becomes an extension table | `NOT_MAPPED` |
| An annotation comes from an `objects:` row | `USER_CONFIG_DEFAULT_APPLIED` |
| An annotation comes from an inference | `VALUE_DERIVED`, with a note that names the rule |

Each warning names at most three tables or members and counts the rest.

A source cannot record an event now. `make_source_factory` in `interop/di/factories.py`
gives a source only `fs` and its user mappings. It changes to give a source a
`ScopedRecorder` too, as `make_step_factory` gives one to a step.

### What stops a run

| Problem | Result |
| --- | --- |
| The mappings file does not parse | It stops with an error |
| A row names a canonical parameter that the schema does not hold | It stops with an error |
| The operations of a row do not give the canonical key | It stops with an error that names the row |
| Two rows write the same canonical row | It stops with an error that names both rows |
| A value names a set member that its set does not hold | The engine leaves out those rows, records `COMPONENT_SKIPPED`, and writes a warning |
| A CSV header that is not its declared key | The source leaves out the table, records `COMPONENT_SKIPPED`, and writes a warning |

The first four are errors in the user's file, so the run stops. The last two are model
data, so the run continues.

### A pipeline to check the canonical stage

No translation reads the canonical stage yet. A sink, `emit_osemosys_canonical_parquet`,
writes the canonical stage to a directory. Two pipelines use it:

- `osemosys-csv-to-canonical`: `stage_osemosys_csv`, then the sink.
- `tz-osemosys-to-canonical`: `stage_tz_osemosys_json`, then the sink.

A user can then check a mappings file before a translation exists. The BDD tests read the
files that the sink writes.

### The tests

The `interop-testing` package gets two builders, each with its `Given` steps:

- one builder for an otoole CSV directory with its config YAML,
- one builder for a TZ-format `model.json`.

`steps/__init__.py` lists both steps modules.

The feature files go in `tests/features/osemosys_staging/`, tagged `@slow` and
`@fork_unsafe`. One scenario covers each of these cases:

- an automatic match;
- a row with `rename_columns` and `repeat_for_all`;
- a family of tables with `columns_from_name`;
- a row with `ignore: true`;
- an extension table, with its warning;
- a file found by its `short_name`;
- a declared parameter with no CSV file;
- a table keyed on `TIMESLICE`, which goes into `source_time_series`;
- a TZ-format wildcard;
- each inference rule;
- a row that overrides an inference;
- each stop condition in the table above.

### The documents

- `docs/developer_documentation/osemosys-canonical-format.md` describes the current
  behaviour: the schema level, the object level, the user mappings file, and the input
  contract of each source.
- Issue #108 asks for `docs/translation_mappings/translation-from-osemosys-to-pypsa.md`
  and for tests in `tests/features/osemosys_to_pypsa/`. Sienna is now the hub, so this
  design uses the paths above in their place.

## What this does not do

- It does not translate to Sienna or to PyPSA. A later design does, and reads the
  canonical stage.
- It does not read result variables.
- It does not read a custom equation. A parameter whose meaning exists only in one
  model's equations stays an extension table.
- It does not convert units.

## Size

| Part | Code | Time for a coding agent |
| --- | --- | --- |
| The canonical schema, with a meaning for each of 82 parameters, and its loader | 1 YAML file, 1 module | about 1 hour |
| The mappings schema, the mappings engine, the operations and the inferences | 3 to 5 modules | about 2 hours |
| `stage_osemosys_csv` | 1 module | about 45 minutes |
| `stage_tz_osemosys_json` and its field table | 1 or 2 modules | about 1 hour |
| A recorder for sources | the source factory and the container | about 20 minutes |
| The sink and the two pipelines | 1 module, 2 YAML files | about 30 minutes |
| The builders, the steps and the BDD features | 4 modules, 3 or 4 feature files | about 2 hours |
| The developer documentation | 1 file | about 30 minutes |
