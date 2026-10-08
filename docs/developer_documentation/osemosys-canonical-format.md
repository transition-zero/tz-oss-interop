# The canonical OSeMOSYS stage

OSeMOSYS has no fixed schema. Each variant of the model declares its own parameters, and
each file format stores them in a different way. A translation from OSeMOSYS reads one form
of a model: the canonical stage. This document describes how a model gets into that form.

A source removes the file format of the model. The mappings engine then uses a user mappings
file to put the model into the canonical schema. Only the user mappings file knows the
variant of the model.

```
source model ──source──▶ raw stage ──mappings engine + user mappings file──▶ canonical stage
 (file format)           (the model's own schema)                             (canonical schema)
```

## The words

- **The schema level** is the parameters of a model: the name, the key and the default value
  of each parameter. The key of a parameter is the list of sets that its value depends on.
- **The object level** is the members of the sets, such as a technology called `ATGASCC1`,
  and the values with their units.
- **The raw stage** is the model after the source removes the file format. It keeps the
  names, the keys and the set members of the model.
- **A raw table** is the table of one parameter in the raw stage. **A raw set** is the table
  of one set in the raw stage.
- **The canonical schema** is the schema that interop defines for an OSeMOSYS model, in
  `interop/plugins/shared/osemosys_canonical_schema.yaml`.
- **The canonical stage** is the model in the canonical schema, with its annotations and its
  metadata.
- **An extension table** is a raw table or a raw set that no canonical name receives. The
  canonical stage keeps it as it is, so no data is lost.
- **An annotation** tells what a set member is: for example, that a technology is a
  generator at the location `AT`.
- **The mappings engine** is the shared code in `interop/plugins/shared/osemosys_canonical/`
  that turns the raw stage into the canonical stage.

## The two pipelines

No translation reads the canonical stage yet. Two pipelines write the canonical stage to a
directory, so that you can examine a user mappings file before a translation exists:

| Pipeline | Source | Sink |
| --- | --- | --- |
| `osemosys-csv-to-canonical` | `stage_osemosys_csv` | `emit_osemosys_canonical_parquet` |
| `tz-osemosys-to-canonical` | `stage_tz_osemosys_json` | `emit_osemosys_canonical_parquet` |

Both sources declare the `OsemosysCanonicalMappings` schema, so each run needs a user
mappings file. In `headless_cli`, give the file with `--user-mappings-path` or with the
`INTEROP_USER_MAPPINGS_PATH` environment variable:

```bash
interop headless_cli --pipeline osemosys-csv-to-canonical \
  --override 'source.config_path=inputs/model/config.yaml' \
  --override 'source.csv_dir=inputs/model/csv' \
  --override 'sink[0].output_dir=outputs/canonical' \
  --user-mappings-path inputs/user_mappings.yaml
```

The console shows only errors by default. Set `INTEROP_LOG_LEVEL=WARNING` to see the
warnings on the console. `decisions.md` holds each event of the run.

## The stages

A source writes both stages in its `staging_dir`. The run deletes `staging_dir` at the end,
unless you give `--keep-staging`.

```
raw/sets/<SET>.parquet                    one column, VALUE
raw/parameters/<name>.parquet             the key columns of the model, then VALUE
raw/declarations.parquet                  name, key and default of each parameter
canonical/sets/<SET>.parquet              one column, VALUE
canonical/parameters/<Name>.parquet       the canonical key, then VALUE
canonical/extensions/<name>.parquet       each raw table and raw set with no canonical name
canonical/annotations/<SET>.parquet       one table each for TECHNOLOGY, FUEL, STORAGE, REGION
canonical/metadata/defaults.parquet       the default of each parameter for this model
canonical/metadata/units.parquet          the units from the user mappings file
canonical/metadata/schema.parquet         the version of the canonical schema
```

The sink `emit_osemosys_canonical_parquet` writes the `canonical/` part to its `output_dir`,
with the same five directories. It does not write the raw stage.

### The raw stage

The raw stage keeps every set member as a string, so a mode called `1` stays `1`. Each
`VALUE` of a raw table is a float. A raw table keeps the name and the key that the model
declares.

### The canonical stage

A canonical parameter table has exactly the key columns of its schema entry, in the order of
the entry, then `VALUE`. A key that holds a second region names that column `_REGION`.

Each canonical table is sparse. It holds only the rows that the model holds. A canonical
parameter whose raw table has no rows gives a table with its key columns and no rows. A
canonical parameter that no raw table maps to gives no table.

An extension table keeps the name, the key columns and the values of its raw table. A raw set
with no canonical name becomes an extension table with one column, `VALUE`.

### The metadata

`defaults.parquet` has the columns `kind`, `parameter` and `default`. It holds one row for
each parameter of the canonical schema, with the kind `parameter`. It also holds one row for
each parameter extension table, with the kind `extension`.

The default of a canonical parameter comes from the first of these that gives one:

1. The default that the model declares for the raw table that maps to it, after
   `multiply_by`.
2. The `default` of the schema entry.
3. The default of the parameter that the entry names in `default_from`, by the same rules.

For example, a model that declares 0.075 for `DiscountRate` gets 0.075 for `DiscountRate`.
It also gets 0.075 for `DiscountRateIdv`, because that entry states `default_from:
DiscountRate`. The default of an extension table is the default that the model declares.

`units.parquet` has the columns `quantity` and `unit`. It holds one row for each unit that
the `units:` part of the user mappings file states. `schema.parquet` has one column,
`schema_version`, and one row.

### Where `State` keeps each table

The source gives back a `State` that holds only the canonical stage:

- A parameter table or an extension table with a `TIMESLICE` column goes into
  `source_time_series`, under the key `(kind, name)`, for example `("parameter",
  "CapacityFactor")`. The table stays lazy.
- Every other table goes into `source_topology`, under the key `<kind>/<name>`, for example
  `set/TECHNOLOGY` or `annotation/FUEL`.

## The canonical schema

The canonical schema is a data file:
`interop/plugins/shared/osemosys_canonical_schema.yaml`. The class `CanonicalSchema` in
`interop/plugins/shared/osemosys_canonical/schema.py` loads it and checks it.

| Part | Count | Origin |
| --- | --- | --- |
| Sets | 12 | The 11 sets of OSeMOSYS v1.0.1, and `REGIONGROUP` |
| Parameters from OSeMOSYS v1.0.1 | 54 | The input parameters of the OSeMOSYS v1.0.1 model file |
| Parameters from tz-osemosys v0.4.1 | 25 | Trade, technology, storage and region group parameters |
| Parameters from OSeMOSYS MUIO model v5.7 | 3 | Activity limits by mode |

A core parameter takes its key from the OSeMOSYS v1.0.1 model file. It takes its default
from the otoole reference config, which has the MIT licence. Each parameter entry has these
fields:

| Field | Required | What it states |
| --- | --- | --- |
| `key` | Yes | The sets of the key. Each one is a set of the schema, or `_REGION`. |
| `default` | No | The default value. |
| `default_from` | No | The parameter whose default this parameter takes. |
| `unit` | Yes | The kind of unit, for example `currency per capacity`. |
| `meaning` | Yes | What the value means. |
| `origin` | Yes | The OSeMOSYS variant that publishes the parameter, with its version. |

The schema does not convert units. `unit` records the kind of unit only. The real units come
from the `units:` part of the user mappings file.

An entry with no `default` and no `default_from` has no default. Such a parameter applies no
constraint where the model states no value.

The loader stops with an error for each of these faults in the schema file:

- An entry states both `default` and `default_from`.
- A key names a set that the schema does not hold.
- `default_from` names a parameter that the schema does not hold.
- An entry holds a field that the table above does not name.

### Add an extension

An extension is a parameter that OSeMOSYS v1.0.1 does not declare. The schema accepts an
extension only when both of these are true:

- A published OSeMOSYS variant defines it.
- Its name does not already mean a different thing.

Describe the parameter by its meaning. Never name a model that uses it.

1. Open `interop/plugins/shared/osemosys_canonical_schema.yaml`.
2. Find the comment line of the variant that publishes the parameter.
3. If no comment line names the variant, add one at the end of `parameters:`.
4. Add the entry under that comment line, with `key`, `unit`, `meaning` and `origin`.
5. Add `default` only if the variant documents a default.
6. Run `uv run pytest -q tests/step_defs/osemosys_staging`.

After the change, a raw table with the same name and key maps to the new parameter
automatically. Before the change, it stayed an extension table.

## The user mappings file

The file holds four parts under one key, `osemosys:`. The rest of the file can hold other
mappings schemas, because only the `osemosys:` part rejects an unknown key.

| Part | Level | What it states |
| --- | --- | --- |
| `sets:` | Schema | The canonical set of a raw set that has a different name |
| `parameters:` | Schema | How a raw table becomes a canonical parameter |
| `objects:` | Object | What each technology, fuel, storage and region is |
| `units:` | Object | The real units of the model |

Each part is optional. A file that holds `osemosys: {}`, or `{}`, is valid. The file holds
only the differences between the model and the canonical schema, because the engine maps the
rest automatically.

### The automatic match

The engine maps a raw set automatically when its name is a canonical set. It maps a raw table
automatically when its name is a canonical parameter and its key holds the same sets. The
order of the key columns does not matter.

Each automatic match records a `VALUE_DERIVED` event with the note "matched by name and
key".

### `sets:`

`sets:` gives a raw set its canonical set name:

```yaml
osemosys:
  sets: {TECH: TECHNOLOGY}
```

`sets:` changes the name of the set table only. It does not change a column of a raw table.
To change a column, give the `rename_columns` operation on a `parameters:` row.

When two raw sets map to one canonical set, the canonical set holds the members of both. For
example, a raw set `TECHNOLOGY` and a raw set `TECH` that `sets:` renames merge into one
`TECHNOLOGY` set.

An entry of `sets:` that names no raw set writes a warning. The entry changes nothing.

### `parameters:`

A row names one raw table with `source`, or a family of raw tables with `source_pattern`. A
pattern is a Python regular expression. The engine uses `re.search`, so a pattern with no
`^` can match inside a name. A row then states one of these:

- `canonical`, the canonical parameter that receives the table.
- `ignore: true`, which leaves out the table.

A row can give operations. The engine applies them in this order:

| Order | Operation | What it does |
| --- | --- | --- |
| 1 | `rename_columns` | It gives a column a new name, for example `{TECH: TECHNOLOGY}`. |
| 2 | `columns_from_name` | It writes a named group of `source_pattern` into a new column. |
| 3 | `remove_column` | It removes one key column with a `rule`. |
| 4 | `repeat_for_all` | It repeats each value for each member of the sets that it names. |
| 5 | `multiply_by` | It multiplies each value, and the declared default, by a number. |

`remove_column` has three fields: `column`, `rule` and `member`. The `rule` is one of these:

- `choose` keeps the rows of one `member`, and you must give `member`.
- `mean`, `sum`, `min` and `max` combine the values of the rows that differ only in the
  removed column. Do not give `member` with them.

`repeat_for_all` takes its members from the canonical set. `_REGION` takes the members of
`REGION`. If the canonical set has no members, the row gives no rows.

Two operations can give an empty table from a raw table that has rows. Each writes a warning
that names the row and the raw table:

- `remove_column` with `choose` gives a `member` that no row of the raw table holds.
- `repeat_for_all` names a set that has no members.

After the operations, the columns of the key must be the canonical key. An invented example:

```yaml
osemosys:
  sets: {TECH: TECHNOLOGY}
  parameters:
    - source: InvestmentCost
      canonical: CapitalCost
      rename_columns: {TECH: TECHNOLOGY}
      repeat_for_all: [REGION, YEAR]
      multiply_by: 0.001
    - source_pattern: "^(?P<country>[A-Z]{2})ReserveTag$"
      canonical: ReserveMarginTagTechnology
      columns_from_name: {country: REGION}
    - source: ModelNotes
      ignore: true
```

The second row merges each table such as `ATReserveTag` and `BEReserveTag` into one
`ReserveMarginTagTechnology` table. It writes `AT` or `BE` into the `REGION` column.

#### The order of the rows

- The first row that matches a raw table wins. The engine does not try the rows after it.
- When a row maps a raw table to a canonical parameter, no automatic match writes to that
  parameter. A raw table that would match it automatically stays an extension table.
- A family of raw tables merges into one canonical table only when all of its tables declare
  the same default, after `multiply_by`. If the defaults differ, each table of the family
  stays an extension table.
- If two raw tables write the same canonical row, the run stops.
- A row that matches no raw table writes a warning.

### `objects:`

`objects:` gives annotations to set members. It has four lists. Each list annotates one set,
and each list accepts only its own annotations:

| List | Set | Annotations |
| --- | --- | --- |
| `technologies:` | `TECHNOLOGY` | `kind`, `category`, `location` |
| `fuels:` | `FUEL` | `carrier`, `location` |
| `storages:` | `STORAGE` | `location` |
| `regions:` | `REGION` | `location` |

Each row has a `match`, which is a Python regular expression. The engine uses `re.search`
against the name of the member. The first row that matches a member wins. A row gives only
the annotations that it states, and the inferences give the rest.

- `kind` is one value from a closed list: `storage`, `link`, `generator`, `supply`, `export`
  or `conversion`.
- `category` is free text, for example `gas-combined-cycle`.
- `carrier` is free text. The value `electricity` has a fixed meaning for the kind inference.
- `location` is a template. It can name a named group of `match`, for example `"{country}"`,
  or the region, `"{REGION}"`.

An annotation table has one row for each region and each member of its set. Its key is
`REGION` and the member, because one member name can exist in many regions. The `REGION`
table has one row for each region. An annotation that nothing gives stays empty.

| Table | Columns |
| --- | --- |
| `annotations/TECHNOLOGY.parquet` | `REGION`, `TECHNOLOGY`, `kind`, `category`, `location` |
| `annotations/FUEL.parquet` | `REGION`, `FUEL`, `carrier`, `location` |
| `annotations/STORAGE.parquet` | `REGION`, `STORAGE`, `location` |
| `annotations/REGION.parquet` | `REGION`, `location` |

#### The inferences

The engine infers each annotation that the structure of the model can show. A row overrides
an inference. The engine infers no `category` and no `carrier`.

The location rules:

- A region is its own location.
- A fuel and a storage take the location of their region.
- A technology takes the locations that `objects:` rows give to the fuels that it takes in
  and puts out. A fuel location that the engine infers does not count.
- The technology takes each such location once. A `~` joins two or more locations.
- The order of the locations starts with the lowest mode of operation. In one mode, an input
  fuel comes before an output fuel. Then the location text sorts in code-point order.
- If no fuel location counts, the technology takes the location of its region.

The kind rules use the rows of the canonical tables `InputActivityRatio`,
`OutputActivityRatio`, `TechnologyToStorage` and `TechnologyFromStorage`. Only a row with a
`VALUE` above zero counts, in any year and any mode. A fuel is electricity when its `carrier`
is `electricity`. As in the location rules, only a fuel location that an `objects:` row gives
counts. The engine tries the kinds in this order, and the first that fits wins:

| `kind` | The technology |
| --- | --- |
| `storage` | Has a row in `TechnologyToStorage` or `TechnologyFromStorage` |
| `link` | Takes in electricity and puts out electricity, at two or more locations that rows give |
| `generator` | Puts out electricity, and takes in no electricity |
| `supply` | Puts out a fuel that is not electricity, and takes in nothing |
| `export` | Takes in a fuel, and puts out nothing |
| `conversion` | Takes in and puts out, and rows give its fuels one location or none |

If no kind fits, `kind` stays empty. The engine records `NOT_MAPPED` and writes a warning.

For example, a technology `ATDEINT` takes in `ATELEC` and puts out `DEELEC`. A `fuels:` row
gives these fuels the carrier `electricity` and the locations `AT` and `DE`. The technology
needs no row: its location is `AT~DE` and its kind is `link`.

### `units:`

`units:` has five optional fields: `capacity`, `energy`, `currency`, `currency_year` and
`emissions`. The metadata keeps what the file states. The engine does not convert a value.

### An example

An invented model has one region. A two-letter prefix on each name gives the country:

```yaml
osemosys:
  units: {capacity: GW, energy: PJ, currency: USD, currency_year: 2021, emissions: Mt}
  objects:
    fuels:
      - match: "^(?P<country>[A-Z]{2})ELEC$"
        carrier: electricity
        location: "{country}"
      - match: "^(?P<country>[A-Z]{2})GAS$"
        carrier: natural-gas
        location: "{country}"
    technologies:
      - match: "^[A-Z]{2}GASCC"
        category: gas-combined-cycle
```

## The sources

Each source reads its input through `self._fs`, writes the raw stage, and calls the mappings
engine. Each source records its events through its `recorder`, so `decisions.md` names the
source in its `Step` column.

### `stage_osemosys_csv`

This source reads a model in the otoole CSV format. It has two parameters:

| Parameter | What it names |
| --- | --- |
| `config_path` | The otoole config YAML, which declares each set and parameter |
| `csv_dir` | The directory that holds one CSV file for each set and parameter |

The config YAML can be outside `csv_dir`. The source reads the entries of `type: set` and
`type: param`. It does not read an entry of `type: result`. The `indices` of a parameter
give its key, and its `default` gives its declared default.

The source finds each parameter file by its full name, then by its `short_name`. It finds
each set file by its full name only. A raw table takes the full name. If `csv_dir` holds none
of the declared files, the run stops. The error names `csv_dir`.

The source removes the spaces and tabs before and after each header name and each cell. A
MathProg data file splits on spaces, so a space is not part of a member or a value.

| Input | What the source does | Event and warning |
| --- | --- | --- |
| A set with no CSV file | It stages the set with no members | Yes |
| A set with an empty file | It stages the set with no members | No |
| A set file that is not CSV | It stages the set with no members | Yes |
| A set file with no `VALUE` column | It leaves out the set | Yes |
| A parameter with no CSV file, or an empty file | It stages the table with no rows, so the default applies | No |
| A parameter file that is not CSV | It stages the table with no rows | Yes |
| A header that is not the declared key and `VALUE` | It stages the table with no rows | Yes |
| A `VALUE` that is not a number | It leaves out that row and keeps the others | Yes |

The order of the columns in a header does not matter. Each event in the table above is
`COMPONENT_SKIPPED`.

### `stage_tz_osemosys_json`

This source reads a model in the TZ format: the `model.json` file that tz-osemosys writes. Its
one parameter, `model_json_path`, names that file. The document must be a JSON object with a
`time_definition`.

The field table in `interop/plugins/shared/tz_osemosys_fields.py` follows the field
documentation of tz-osemosys v0.4.1. It gives the raw table, the nested sets and the default
of each field. The object that holds a field decides the raw table. For example, `capex` on a
technology goes to `CapitalCost`, and `capex` on a storage goes to `CapitalCostStorage`.

The source makes the sets from the objects:

| Object list | Set | Key columns that an object adds to its rows |
| --- | --- | --- |
| `regions` | `REGION` | `REGION` |
| `regionsgroup` | `REGIONGROUP` | `REGIONGROUP` |
| `commodities` | `FUEL` | `FUEL` |
| `impacts` | `EMISSION` | `EMISSION` |
| `technologies` | `TECHNOLOGY` | `TECHNOLOGY` |
| `operating_modes` of a technology | `MODE_OF_OPERATION` | `TECHNOLOGY`, `MODE_OF_OPERATION` |
| `storage` | `STORAGE` | `STORAGE` |
| `trade` | none | `FUEL`, from its `commodity` |

The `id` of an object is its set member. The `id` of a trade names the trade, not a member.
The `time_definition` gives `YEAR`, `TIMESLICE`, `SEASON`, `DAYTYPE` and
`DAILYTIMEBRACKET`. A count `n` in place of a list stands for the members 1 to `n`.

The source reads each value as follows:

- It removes the `{"is_composed": true, "data": ...}` wrapper from a value.
- A `"*"` key stands for each member of its set that the level does not name. A member that
  the level names wins.
- A value that stops above the last nested level applies to each member of each level below.
- `true` becomes 1 and `false` becomes 0. A null field adds no rows.
- `sinking-fund` becomes 1 and `straight-line` becomes 2, as `DepreciationMethod` uses them.
- A number written as `2030.0` in a member becomes `2030`.
- A field such as `timeslice_in_season` names a set member as its value. Each such value
  becomes a row with that member and the value 1.
- An annual demand with a profile for its region, fuel and year goes to
  `SpecifiedAnnualDemand`. An annual demand with no profile goes to `AccumulatedAnnualDemand`.
- When a trade states `construct_region_pairs: true`, a pair of regions in one direction also
  holds in the other direction. A direction that the trade states itself wins. This applies
  only to the eight region-pair fields: `trade_routes`, `trade_loss`, `residual_capacity`,
  `capex`, `capacity_additional_max`, `operating_life`, `cost_of_capital` and
  `capacity_activity_unit_ratio`.

The source stages a raw table for each table that the field table names. A table that no
field states has no rows. The declared defaults are the defaults of the field table.

| Input | What the source does |
| --- | --- |
| An object that cannot be used, such as a technology with no `id` | It leaves out the object and keeps the rest |
| A field that the field table does not hold | It leaves out the field |
| A `construct_region_pairs` that is not `true` or `false` | It copies no pair and keeps the trade |
| A wildcard over a set with no members | The value adds no rows |
| A value that is not a number | It leaves out the value |
| Two rows of one raw table with the same key, for example from two trades | It keeps the row that it reads first, and leaves out the later rows |

For each problem in the table above, the source records an event and writes a warning. These
problems record `COMPONENT_SKIPPED`:

- An object that cannot be used.
- A value that is not a number.
- A row with the same key as an earlier row of the raw table.

The others record `NOT_MAPPED`.

The source does not read the fields `long_name`, `description`, `otoole_cfg` and
`defaults_otoole`.

## What stops a run

An error in an input of the wrong kind, or in the user mappings file, stops the run. A
problem in the data of the model never stops the run.

| Problem | Result |
| --- | --- |
| The user mappings file is not given, or it does not parse | The run stops |
| `osemosys:`, or a part in it, holds a key that the schema does not declare | The run stops |
| `sets:` or a `parameters:` row names a canonical set or parameter that the schema does not hold | The run stops |
| `repeat_for_all` names a column that is not a canonical set or `_REGION` | The run stops |
| `remove_column` gives a `member` with a rule other than `choose`, or no `member` with `choose` | The run stops |
| A `parameters:` row states both or neither of `source` and `source_pattern` | The run stops |
| A `parameters:` row states both or neither of `canonical` and `ignore: true` | The run stops |
| A pattern or a `match` is not a regular expression | The run stops |
| `columns_from_name` names a group that `source_pattern` does not hold | The run stops |
| The operations of a row do not give the canonical key | The run stops, and the error names the row |
| Two raw tables write the same canonical row | The run stops, and the error names the rows |
| An `objects:` row gives an annotation that its list does not accept | The run stops |
| A `kind` is not in the closed list | The run stops |
| A `location` names a group that `match` does not hold, or holds an empty `{}` | The run stops |
| A `location` group captures nothing for a member | The run stops, and the error names the row |
| `config_path` does not end in `.yaml` or `.yml` | The run stops |
| `csv_dir` names a file | The run stops |
| `csv_dir` holds none of the declared set and parameter files | The run stops, and the error names `csv_dir` |
| The config YAML cannot be read, or it is not an otoole config | The run stops |
| The `model.json` cannot be read, or it is not a JSON object with a `time_definition` | The run stops |

These problems in the data of the model do not stop the run:

- A raw stage problem that the sections on the two sources list. The source leaves out the
  part that it cannot use.
- A value that names a set member that its canonical set does not hold. The engine leaves
  out those rows.

The rule for an absent set member applies to each canonical parameter table. The engine
checks each key column against its canonical set, and `_REGION` against `REGION`. An empty
key cell counts as an absent member. The engine records `COMPONENT_SKIPPED` for each table
and writes one warning. It does not apply this rule to an extension table.

## The reporting

The engine records one event for each raw table and raw set. For each member in each region,
it records one event for the row that annotates it, and one for its inferences. It records no
event for a single value row, because a table can hold millions of rows.

| Decision | Event kind |
| --- | --- |
| A raw set or a raw table maps automatically | `VALUE_DERIVED`, with the note "matched by name and key" |
| `sets:` renames a raw set | `VALUE_DERIVED` |
| A `parameters:` row maps a raw table | `VALUE_DERIVED`, with a note that names the row and its operations |
| A `parameters:` row says `ignore: true` | `COMPONENT_SKIPPED` |
| A raw table or a raw set becomes an extension table | `NOT_MAPPED` |
| A canonical table loses rows to absent set members | `COMPONENT_SKIPPED` |
| An `objects:` row gives annotations | `USER_CONFIG_DEFAULT_APPLIED`, with a note that names the row |
| The engine infers annotations | `VALUE_DERIVED`, with a note that names each rule |
| No kind fits a technology | `NOT_MAPPED` |

The source field of each event has the framework `osemosys`. Two groups of events also have
a destination field, with the framework `osemosys-canonical`:

- Each `VALUE_DERIVED` event.
- Each annotation event, including the `NOT_MAPPED` event when no kind fits a technology.

Every other event has a source field only. This includes each `COMPONENT_SKIPPED` event, and
each `NOT_MAPPED` event for an extension table. An annotation event names its member as
`REGION/member`, for example `R1/ATGASCC1`.

The engine writes one warning for each reason, not one for each table. A warning gives the
count, and it names at most three tables or members. For example:

```
WARNING ... 5 raw table(s) match no canonical parameter by name and key, so each stays an extension table: ATTag, BETag, CHTag and 2 more
```
