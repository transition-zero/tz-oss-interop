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

- **The schema level** is the parameters of a model: the name, the columns and the default
  value of each parameter. The columns of a parameter name the sets that its value depends on.
- **The object level** is the members of the sets, such as a technology called `ATGASCC1`,
  and the values with their units.
- **A default name** is the name that the automatic match looks for, for example `CapitalCost`
  or `REGION`. The `osemosys_name` field of each schema entry holds it. OSeMOSYS does not
  require these names, so a model can give a set or a parameter any name.
- **The default columns** of a parameter are the index columns that the automatic match looks
  for. The `osemosys_columns` field of each schema entry holds them.
- **A canonical name** is the name of a set, a parameter or a column in the canonical schema,
  for example `capital_cost` or `region`. The section "Names" gives the rules.
- **The raw stage** is the model after the source removes the file format. It keeps the
  names, the index columns and the set members of the model, as the model states them.
- **A raw table** is the table of one parameter in the raw stage. **A raw set** is the table
  of one set in the raw stage.
- **The canonical schema** is the schema that tz-oss-interop defines for an OSeMOSYS model, in
  `interop/plugins/shared/osemosys_canonical_schema.yaml`.
- **The canonical stage** is the model in the canonical schema, with its annotations and its
  metadata.
- **An extension table** is a raw table or a raw set that no canonical name receives. The
  canonical stage keeps it as it is, so no data is lost.
- **An annotation** tells what a set member is: for example, that a technology is a
  `SupplyTechnology` at the location `AT`.
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
  --user-mappings-path inputs/osemosys_mappings.yaml
```

The console shows only errors by default. Set `INTEROP_LOG_LEVEL=WARNING` to see the
warnings on the console. `decisions.md` holds each event of the run.

## Names

The canonical stage uses Sienna's nomenclature: the vocabulary of SiennaSchemas, the JSON
schemas of the Sienna data model. The names come from SiennaSchemas commit `9d58d29`, and
mostly from its `Investments` domain. A translation from the canonical stage to Sienna then
needs one vocabulary only.

The raw stage keeps the names of the model, because the source only removes the file format.

### The rules for a canonical name

1. Every canonical name is snake_case. This applies to each set, parameter, column and
   metadata field.
2. If SiennaSchemas has a field for the same quantity in the same sense, the canonical name is
   that field name. A nested Sienna field gives its leaf name, so `capital_costs.capital_cost`
   gives `capital_cost`.
3. If SiennaSchemas has no such field, the canonical name is the default name in snake_case.
   The canonical name gives each abbreviation in full: `RE` becomes `renewable`, and `Idv`
   becomes `technology`.
4. One concept takes one word. SiennaSchemas calls a link between two regions a transport
   technology, so each OSeMOSYS trade parameter takes the word `transport`.
5. A quantity with a different encoding does not take the Sienna name. For example, OSeMOSYS
   `ReserveMargin` is a ratio to the demand, such as 1.2. Sienna's `capacity_reserve_fraction`
   is a fraction above the peak, so the canonical name is `reserve_margin`.
6. A name that holds a unit does not take the Sienna name. For example, Sienna's `max_mtons`
   states its unit, but a model can state an emission limit in any unit. So the canonical name
   is `annual_emission_limit`.

### The sets

| Default name | Canonical name | Source of the name |
| --- | --- | --- |
| `REGION` | `region` | `region` on each Sienna investment technology |
| `TECHNOLOGY` | `technology` | The Sienna investment types end in `Technology` |
| `FUEL` | `fuel` | `SupplyTechnology.fuel` |
| `EMISSION` | `pollutant` | `EmissionsData.pollutant` |
| `MODE_OF_OPERATION` | `operating_mode` | `HydroPumpTurbine.operating_mode` |
| `STORAGE` | `storage` | `StorageTechnology` |
| `YEAR` | `year` | Rule 3 |
| `TIMESLICE` | `timeslice` | Rule 3 |
| `SEASON` | `season` | Rule 3 |
| `DAYTYPE` | `day_type` | Rule 3 |
| `DAILYTIMEBRACKET` | `daily_time_bracket` | Rule 3 |
| `REGIONGROUP` | `region_group` | Rule 3 |

A table that holds two regions names them `start_region` and `end_region`, as Sienna's
`AggregateTransportTechnology` does. They are not sets. Each one is a column that holds the
members of the `region` set. The default columns name the second region `_REGION`. The `columns` field of
the schema entry names each column and its set:

```yaml
transport_capital_cost:
  columns:
    start_region: region
    end_region: region
    fuel: fuel
    year: year
  osemosys_name: CapitalCostTrade
  osemosys_columns: [REGION, _REGION, FUEL, YEAR]
```

The value column of each canonical table and each extension table is `value`. The OSeMOSYS
name of that column is `VALUE`.

### The parameters

The schema file `interop/plugins/shared/osemosys_canonical_schema.yaml` holds the full table of
the parameters. Each entry gives the canonical name, the default name and the default columns of
one parameter.

These parameters take a SiennaSchemas name, by rule 2:

| Default name | Canonical name | SiennaSchemas field |
| --- | --- | --- |
| `CapitalCost` | `capital_cost` | `SupplyTechnology.capital_costs.capital_cost` |
| `CapitalCostStorage` | `energy_capital_cost` | `StorageTechnology.capital_costs.energy_capital_cost` |
| `VariableCost` | `variable_operation_cost` | `ThermalGenerationCost.variable_operation_cost` |
| `OperationalLife` | `lifetime` | `SupplyTechnology.lifetime` |
| `CapacityOfOneTechnologyUnit` | `unit_size` | `SupplyTechnology.unit_size` |
| `TotalAnnualMaxCapacity` | `capacity_limits_max` | `SupplyTechnology.capacity_limits.max` |
| `TotalAnnualMinCapacity` | `capacity_limits_min` | `SupplyTechnology.capacity_limits.min` |
| `StorageMaxHours` | `duration_limits_max` | `StorageTechnology.duration_limits.max` |
| `TradeLossBetweenRegions` | `line_loss` | `AggregateTransportTechnology.line_loss` |
| `DiscountRate` | `discount_rate` | `PortfolioFinancialData.discount_rate` |
| `EmissionActivityRatio` | `emission_rate` | `EmissionsData.emission_rate` |
| `REMinProductionTarget` | `generation_fraction_requirement` | `EnergyShareRequirements.generation_fraction_requirement` |

`capacity_limits_max`, `capacity_limits_min` and `duration_limits_max` keep their parent
field, because the leaf `max` or `min` alone is not clear. A canonical parameter keeps the
model's own unit. For example, `duration_limits_max` holds hours, but Sienna's `duration_limits`
holds minutes.

Four parameters keep a prefix, so that one name means one table: `storage_lifetime`,
`transport_lifetime`, `transport_capital_cost` and `storage_discount_rate`.

Each other parameter takes its default name in snake_case, by rules 3 and 4. For example:

| Default name | Canonical name |
| --- | --- |
| `DiscountRateIdv` | `technology_discount_rate` |
| `TradeRoute` | `transport_route` |
| `RETagTechnology` | `renewable_tag_technology` |
| `FixedCost` | `fixed_cost` |
| `AvailabilityFactor` | `availability_factor` |
| `InputActivityRatio` | `input_activity_ratio` |

The three `Conversionl*` parameters take the field names of tz-osemosys, because `ls`, `ld` and
`lh` are abbreviations: `timeslice_in_season`, `timeslice_in_day_type` and
`timeslice_in_daily_time_bracket`.

### Where each vocabulary applies

- The raw stage uses the names of the model: the raw sets, the raw tables, their index columns
  and `VALUE`.
- The automatic match compares the name and the index columns of a raw table with the
  `osemosys_name` and the `osemosys_columns` of each canonical parameter. It compares the name of a raw set with
  the `osemosys_name` of each canonical set.
- The canonical stage uses the canonical names: the sets, the parameters, the columns, the
  paths and the `State` keys.
- An extension table keeps its own name. Its columns take the canonical set names and
  `value`. If it holds a pair of regions, they are `start_region` and `end_region`.
- The user mappings file accepts canonical names only. A default name such as `CapitalCost`
  in a `canonical:` value stops the run.

## The stages

A source writes both stages in its `staging_dir`. The run deletes `staging_dir` at the end,
unless you give `--keep-staging`.

```
raw/sets/<SET>.parquet                    one column, VALUE
raw/parameters/<Name>.parquet             the index columns of the model, then VALUE
raw/declarations.parquet                  name, index columns and default of each parameter
planned/<name>.parquet                    each table that a parameters: row maps, before the absent-member rule
canonical/sets/<set>.parquet              one column, value
canonical/parameters/<name>.parquet       the canonical columns, then value
canonical/extensions/<Name>.parquet       each raw table and raw set with no canonical name
canonical/annotations/<set>.parquet       one table each for technology, fuel, storage, region
canonical/metadata/defaults.parquet       the default of each parameter for this model
canonical/metadata/units.parquet          the units from the user mappings file
canonical/metadata/schema.parquet         the version of the canonical schema
```

For example, the raw table `raw/parameters/CapitalCost.parquet` becomes
`canonical/parameters/capital_cost.parquet`.

The engine computes each canonical parameter table that a `parameters:` row maps one time,
into `planned/`. The overlap check, the absent-member rule and the canonical table then read
that file. The annotations read the canonical tables that the engine writes.

The sink `emit_osemosys_canonical_parquet` writes the `canonical/` part to its `output_dir`,
with the same five directories. It does not write the raw stage or `planned/`.

### The raw stage

The raw stage keeps every set member as a string, so a mode called `1` stays `1`. Each
`VALUE` of a raw table is a float. A raw table keeps the name and the index columns that the
model declares.

### The canonical stage

A canonical parameter table has exactly the columns of its schema entry, in the order of
the entry, then `value`. A table that holds two regions names them `start_region` and
`end_region`.

Each canonical table is sparse. It holds only the rows that the model holds. A canonical
parameter whose raw table has no rows gives a table with its columns and no rows. A
canonical parameter that no raw table maps to gives no table.

An extension table keeps the name and the values of its raw table. Its columns take canonical
names by these rules:

- A column with the default name of a set takes the canonical name of that set.
- `_REGION` becomes `end_region`. Then, if the table holds `end_region`, `region` becomes
  `start_region`.
- `VALUE` becomes `value`.
- A column with another name keeps its name.

For example, a raw table with the index columns `REGION` and `_REGION` gives an extension table with the
columns `start_region`, `end_region` and `value`. A raw set with no canonical name becomes an
extension table with one column, `value`.

### The metadata

`defaults.parquet` has the columns `kind`, `parameter`, `default` and `default_from`. It
holds one row for each parameter of the canonical schema, with the kind `parameter`. It also
holds one row for each parameter extension table, with the kind `extension`.

The default of a canonical parameter comes from the first of these that gives one:

1. The default that the model declares for the raw table that maps to it, after
   `multiply_by`. This fills `default`.
2. The `default` of the schema entry. This fills `default`.
3. The `default_from` of the schema entry. This fills `default_from`, and `default` stays
   empty.

`default_from` names another canonical parameter. The default of a row is the value of that
parameter at the same key columns. A consumer joins the two tables on the columns that both
hold. Where the named parameter has no row, its own `default` applies. The engine does not
put one number in `default`, because OSeMOSYS gives each row the value of the named
parameter, not its default.

For example, a model states 0.10 for `DiscountRate` in the region `R1`, and declares no
default for `DiscountRateIdv`. The row of `technology_discount_rate` has an empty `default`
and the `default_from` value `discount_rate`. A consumer gives each technology in `R1` the
default 0.10.

When the model declares no default, the engine records `TRANSLATOR_DEFAULT_APPLIED` for the
parameter. The note says whether the default comes from the schema or from `default_from`.
The default of an extension table is the default that the model declares, and its
`default_from` is empty.

The `parameter` column holds the canonical name of a parameter, or the name of an extension
table.

`units.parquet` has the columns `quantity` and `unit`. It holds one row for each unit that
the `units:` part of the user mappings file states. `schema.parquet` has one column,
`schema_version`, and one row.

### Where `State` keeps each table

The source gives back a `State` that holds only the canonical stage:

- Each parameter table and each extension table goes into `source_time_series`, under the key
  `(kind, name)`, for example `("parameter", "capital_cost")`. A reader must not collect
  such a table in full, because it can hold billions of rows.
- Each set table, annotation table and metadata table goes into `source_topology`, under the
  key `<kind>/<name>`, for example `set/technology`, `annotation/fuel` or
  `metadata/defaults`.

Every table stays lazy.

## The canonical schema

The canonical schema is a data file:
`interop/plugins/shared/osemosys_canonical_schema.yaml`. The class `CanonicalSchema` in
`interop/plugins/shared/osemosys_canonical/schema.py` loads it and checks it.

| Part | Count | Origin |
| --- | --- | --- |
| Sets | 12 | The 11 sets of OSeMOSYS v1.0.1, and `region_group` |
| Parameters from OSeMOSYS v1.0.1 | 54 | The input parameters of the OSeMOSYS v1.0.1 model file |
| Parameters from tz-osemosys v0.4.1 | 25 | Trade, technology, storage and region group parameters |
| Parameters from OSeMOSYS MUIO model v5.7 | 3 | Activity limits by mode |

A core parameter takes its columns from the OSeMOSYS v1.0.1 model file. It takes its default
from the otoole reference config, which has the MIT licence.

The name of a set entry is its canonical name. Each set entry has two fields, and both are
required. `meaning` states what the members are. `osemosys_name` states the default name of
the set.

The name of a parameter entry is its canonical name. Each parameter entry has these fields:

| Field | Required | What it states |
| --- | --- | --- |
| `columns` | Yes | An ordered mapping from each canonical column to the set whose members it holds. A column of a set has the name of the set. `start_region` and `end_region` hold `region`. |
| `osemosys_name` | Yes | The default name of the parameter. |
| `osemosys_columns` | Yes | The default columns: the default name of the set at each position of `columns`, or `_REGION`. |
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
- A set in `columns` is not a set of the schema.
- `osemosys_columns` and `columns` have different lengths.
- `osemosys_columns` holds the same column two times.
- A column of `osemosys_columns` does not name the set of the column at the same position in
  `columns`.
- `REGION` stands at `end_region`, or `_REGION` stands at any column other than `end_region`.
  `REGION` at the position of `start_region` is correct.
- An entry holds `end_region`, but `REGION` does not stand at `start_region`.
- Two set entries, or two parameter entries, have the same `osemosys_name`.
- `default_from` names a parameter that the schema does not hold.
- `default_from` names a parameter that itself states `default_from`. A consumer then needs
  one join only, and a cycle is not possible.
- An entry holds a field that the tables above do not name.

### Add an extension

An extension is a parameter that OSeMOSYS v1.0.1 does not declare. The schema accepts an
extension only when both of these are true:

- A published OSeMOSYS variant defines it.
- Its name does not already mean a different thing.

Describe the parameter by its meaning. Never name a model that uses it.

1. Open `interop/plugins/shared/osemosys_canonical_schema.yaml`.
2. Find the comment line of the variant that publishes the parameter.
3. If no comment line names the variant, add one at the end of `parameters:`.
4. Give the entry the canonical name that the rules in "Names" give.
5. Add `columns`, `osemosys_name`, `osemosys_columns`, `unit`, `meaning` and `origin` to the entry.
6. If the table holds two regions, name them `start_region: region` and `end_region: region` in `columns`.
7. Add `default` only if the variant documents a default.
8. Run `uv run pytest -q tests/step_defs/osemosys_staging`.

After the change, a raw table with the default name and the default columns of the entry maps to
the new parameter automatically. Before the change, it stayed an extension table.

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

The file accepts canonical names only: each `canonical:` value, each `sets:` target, each
column of an operation and each `kind`. A raw set or a raw table keeps its own name in `sets:`,
`source` and `source_pattern`.

### The automatic match

The engine maps a raw set automatically when its name is the `osemosys_name` of a canonical
set. It maps a raw table automatically when its name is the `osemosys_name` of a canonical
parameter, and its index columns are the `osemosys_columns`. The order of the index columns
does not matter.

The engine then gives each default column the canonical column at the same position in
`columns`. For example, the raw table `CapitalCostTrade`, with the index columns `REGION,
_REGION, FUEL, YEAR`, becomes `transport_capital_cost`, with the columns `start_region,
end_region, fuel, year`.

Each automatic match records a `VALUE_DERIVED` event with the note "matched by name and
key".

### `sets:`

`sets:` gives a raw set its canonical set name:

```yaml
osemosys:
  sets: {TECH: technology}
```

`sets:` changes the name of the set table only. It does not change a column of a raw table.
To change a column, give the `rename_columns` operation on a `parameters:` row.

When two raw sets map to one canonical set, the canonical set holds the members of both. For
example, a raw set `TECHNOLOGY` and a raw set `TECH` that `sets:` renames merge into one
`technology` set.

An entry of `sets:` that names no raw set writes a warning. The entry changes nothing.

### `parameters:`

A row names one raw table with `source`, or a family of raw tables with `source_pattern`. A
pattern is a Python regular expression. The engine uses `re.search`, so a pattern with no
`^` can match inside a name. A row then states one of these:

- `canonical`, the canonical parameter that receives the table.
- `ignore: true`, which leaves out the table.

Before the operations of a row, the engine gives canonical names to the columns of the raw
table:

- A column with the default name of a set takes the canonical name of that set.
- `_REGION` becomes `end_region`.
- Then, if the canonical columns hold `start_region`, `region` becomes `start_region`.
- `VALUE` becomes `value`.
- A column with another name keeps its name, for example `TECH`.

So the operations use the canonical names, and the raw names of the other columns.

A row can give operations. The engine applies them in this order:

| Order | Operation | What it does |
| --- | --- | --- |
| 1 | `rename_columns` | It gives a column a new name, for example `{TECH: technology}`. |
| 2 | `columns_from_name` | It writes a named group of `source_pattern` into a new column. |
| 3 | `remove_column` | It removes one index column with a `rule`. |
| 4 | `repeat_for_all` | It repeats each value for each member of the sets that it names. |
| 5 | `multiply_by` | It multiplies each value, and the declared default, by a number. |

`remove_column` has three fields: `column`, `rule` and `member`. The `rule` is one of these:

- `choose` keeps the rows of one `member`, and you must give `member`.
- `mean`, `sum`, `min` and `max` combine the values of the rows that differ only in the
  removed column. Do not give `member` with them.

`repeat_for_all` takes its members from the canonical set. `start_region` and `end_region`
take the members of `region`. If the canonical set has no members, the row gives no rows.

Two operations can give an empty table from a raw table that has rows. Each records
`NOT_MAPPED` against the raw table, with a note that names the row. Each also writes a
warning:

- `remove_column` with `choose` gives a `member` that no row of the raw table holds.
- `repeat_for_all` names a set that has no members.

After the operations, the index columns must be the canonical columns. An invented example:

```yaml
osemosys:
  sets: {TECH: technology}
  parameters:
    - source: InvestmentCost
      canonical: capital_cost
      rename_columns: {TECH: technology}
      repeat_for_all: [region, year]
      multiply_by: 0.001
    - source_pattern: "^(?P<country>[A-Z]{2})ReserveTag$"
      canonical: reserve_margin_tag_technology
      columns_from_name: {country: region}
    - source: ModelNotes
      ignore: true
```

The second row merges each table such as `ATReserveTag` and `BEReserveTag` into one
`reserve_margin_tag_technology` table. It writes `AT` or `BE` into the `region` column.

#### The order of the rows

- The first row that matches a raw table wins. The engine does not try the rows after it.
- When a row maps a raw table to a canonical parameter, no automatic match writes to that
  parameter. A raw table that would match it automatically stays an extension table.
- A family of raw tables merges into one canonical table only when all of its tables declare
  the same default, after `multiply_by`. If the defaults differ, each table of the family
  stays an extension table.
- If two raw tables write the same canonical row, each raw table that maps to that canonical
  parameter stays an extension table. The note names the rows and the first key in key
  order that two raw tables both give.
- A row that matches no raw table writes a warning.

### `objects:`

`objects:` gives annotations to set members. It has four lists. Each list annotates one set,
and each list accepts only its own annotations:

| List | Set | Annotations |
| --- | --- | --- |
| `technologies:` | `technology` | `kind`, `category`, `location` |
| `fuels:` | `fuel` | `carrier`, `location` |
| `storages:` | `storage` | `location` |
| `regions:` | `region` | `location` |

Each row has a `match`, which is a Python regular expression. The engine uses `re.search`
against the name of the member. The first row that matches a member wins. A row gives only
the annotations that it states, and the inferences give the rest.

- `kind` is one value from a closed list: `StorageTechnology`, `AggregateTransportTechnology`,
  `SupplyTechnology`, `fuel_supply`, `export` or `conversion`. The first three are Sienna type
  names. Sienna has no type for the other three.
- `category` is free text, for example `gas-combined-cycle`.
- `carrier` is free text. The value `electricity` has a fixed meaning for the kind inference.
- `location` is a template. It can name a named group of `match`, for example `"{country}"`,
  or the region, `"{region}"`. If the group captures nothing for a member, the location of
  that member stays empty, and no inference fills it. The engine records `NOT_MAPPED` and
  writes a warning.

An annotation table has one row for each region and each member of its set. Its key is
`region` and the member, because one member name can exist in many regions. The `region`
table has one row for each region. An annotation that nothing gives stays empty.

| Table | Columns |
| --- | --- |
| `annotations/technology.parquet` | `region`, `technology`, `kind`, `category`, `location` |
| `annotations/fuel.parquet` | `region`, `fuel`, `carrier`, `location` |
| `annotations/storage.parquet` | `region`, `storage`, `location` |
| `annotations/region.parquet` | `region`, `location` |

`category`, `carrier` and `location` have no Sienna field with the same meaning, so they keep
these names.

#### The inferences

The engine infers each annotation that the structure of the model can show. A row overrides
an inference. The engine infers no `category` and no `carrier`.

The location rules:

- A region is its own location.
- A fuel and a storage take the location of their region.
- A technology takes the locations that `objects:` rows give to the fuels that it takes in
  and puts out. A fuel location that the engine infers does not count.
- The technology takes each such location once. A `~` joins two or more locations.
- The order of the locations starts with the lowest operating mode. In one mode, an input
  fuel comes before an output fuel. Then the location text sorts in code-point order.
- If no fuel location counts, the technology takes the location of its region.

The kind rules use the rows of the canonical tables `input_activity_ratio`,
`output_activity_ratio`, `technology_to_storage` and `technology_from_storage`. Only a row with
a `value` above zero counts, in any year and any mode. A fuel is electricity when its `carrier`
is `electricity`. As in the location rules, only a fuel location that an `objects:` row gives
counts. The engine tries the kinds in this order, and the first that fits wins:

| `kind` | The technology |
| --- | --- |
| `StorageTechnology` | Has a row in `technology_to_storage` or `technology_from_storage` |
| `AggregateTransportTechnology` | Takes in electricity and puts out electricity, at two or more locations that rows give |
| `SupplyTechnology` | Puts out electricity, and takes in no electricity |
| `fuel_supply` | Puts out a fuel that is not electricity, and takes in nothing |
| `export` | Takes in a fuel, and puts out nothing |
| `conversion` | Takes in and puts out, and rows give its fuels one location or none |

If no kind fits, `kind` stays empty. The engine records `NOT_MAPPED` and writes a warning.

For example, a technology `ATDEINT` takes in `ATELEC` and puts out `DEELEC`. A `fuels:` row
gives these fuels the carrier `electricity` and the locations `AT` and `DE`. The technology
needs no row: its location is `AT~DE` and its kind is `AggregateTransportTechnology`.

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

Each source reads its input through `self._fs` into raw tables. The shared base class
`OsemosysCanonicalSource`, in
`interop/plugins/shared/osemosys_canonical/canonical_source.py`, then cleans the raw tables,
writes the raw stage, and calls the mappings engine. A new source implements only
`_build_raw_tables`.

The sets and the raw tables in this section are in the raw stage. `stage_osemosys_csv` keeps
the names of the model. `stage_tz_osemosys_json` gives each field its default name. Each
source records its events through its `recorder`, so `decisions.md` names the source in its
`Step` column.

### The rules that both sources apply

`normalise_raw_tables` in `interop/plugins/shared/osemosys_canonical/raw_values.py` cleans
the raw tables of both sources, so that one model gives the same raw stage from each format:

- It removes the spaces and tabs before and after each set member and each key cell. A
  MathProg data file splits on spaces, so a space is not part of a member.
- It keeps one copy of a set member that a set holds two times.
- It keeps the first row of a key that a raw table holds two times, and leaves out the later
  rows. It records `COMPONENT_SKIPPED` for each such raw table, with a note that gives the
  count and the first repeated key. It also writes one warning.

### `stage_osemosys_csv`

This source reads a model in the otoole CSV format, from local paths only. A URL cannot name
the directory `csv_dir`, so the source does not accept a URL for either parameter. It has two
parameters:

| Parameter | What it names |
| --- | --- |
| `config_path` | The otoole config YAML, which declares each set and parameter |
| `csv_dir` | The directory that holds one CSV file for each set and parameter |

The config YAML can be outside `csv_dir`. The source reads the entries of `type: set` and
`type: param`. It does not read an entry of `type: result`. The `indices` of a parameter
give its index columns, and its `default` gives its declared default. The name of an entry,
and its `short_name`, become file names. So a name that holds `/`, `\` or `..` stops the run.

The source finds each parameter file by its full name, then by its `short_name`. It finds
each set file by its full name only. A raw table takes the full name. If `csv_dir` holds none
of the declared files, the run stops. The error names `csv_dir`. A `csv_dir` that names a
file holds none of the declared files, so it stops the run in the same way.

The source removes the spaces and tabs before and after each header name and each `VALUE`.
The rules that both sources apply remove them from the other cells.

| Input | What the source does | Event and warning |
| --- | --- | --- |
| A set with no CSV file | It stages the set with no members | Yes |
| A set with an empty file | It stages the set with no members | No |
| A set file that is not CSV | It stages the set with no members | Yes |
| A set file with no `VALUE` column | It leaves out the set | Yes |
| A parameter with no CSV file, or an empty file | It stages the table with no rows, so the default applies | No |
| A parameter file that is not CSV | It stages the table with no rows | Yes |
| A header that is not the declared index columns and `VALUE` | It stages the table with no rows | Yes |
| A `VALUE` that is not a number | It leaves out that row and keeps the others | Yes |

The order of the columns in a header does not matter. Each event in the table above is
`COMPONENT_SKIPPED`.

### `stage_tz_osemosys_json`

This source reads a model in the TZ format: the `model.json` file that tz-osemosys writes. Its
one parameter, `model_json_path`, names that file. The document must be a JSON object with a
`time_definition`.

The field table in `interop/plugins/shared/osemosys_canonical/tz_fields.py` follows the field
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
`DAILYTIMEBRACKET`. A count `n` in place of a list stands for the members 1 to `n`. A member
of these lists must be a string or a number. The source leaves out any other member, records
`COMPONENT_SKIPPED` and writes a warning.

The source reads each value as follows:

- It removes the `{"is_composed": true, "data": ...}` wrapper from a value.
- A `"*"` key stands for each member of its set that the level does not name. A member that
  the level names wins.
- A value that stops above the last nested level applies to each member of each level below.
- `true` becomes 1 and `false` becomes 0. A null field adds no rows.
- `sinking-fund` becomes 1 and `straight-line` becomes 2, as `DepreciationMethod` uses them.
- A number written as `2030.0` in a member becomes `2030`. This applies also to a value that
  names a set member, such as the season in `timeslice_in_season`.
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
| A member of a `time_definition` list that is not a string or a number, such as `true` | It leaves out the member and keeps the rest |
| A field that the field table does not hold | It leaves out the field |
| A `construct_region_pairs` that is not `true` or `false` | It copies no pair and keeps the trade |
| A wildcard over a set with no members | The value adds no rows |
| A value that is not a number | It leaves out the value |
| Two rows of one raw table with the same index columns, for example from two trades | It keeps the row that it reads first, and leaves out the later rows |

For each problem in the table above, the source records an event and writes a warning. These
problems record `COMPONENT_SKIPPED`:

- An object that cannot be used.
- A member of a `time_definition` list that is not a string or a number.
- A value that is not a number.
- A row with the same index columns as an earlier row of the raw table.

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
| `sets:` or a `parameters:` row names a canonical set or parameter that the schema does not hold, for example the default name `CapitalCost` | The run stops |
| `repeat_for_all` names a column that is not a canonical set, `start_region` or `end_region` | The run stops |
| `remove_column` gives a `member` with a rule other than `choose`, or no `member` with `choose` | The run stops |
| A `parameters:` row states both or neither of `source` and `source_pattern` | The run stops |
| A `parameters:` row states both or neither of `canonical` and `ignore: true` | The run stops |
| A pattern or a `match` is not a regular expression | The run stops |
| `columns_from_name` names a group that `source_pattern` does not hold | The run stops |
| The operations of a row do not give the canonical columns | The run stops, and the error names the row |
| An `objects:` row gives an annotation that its list does not accept | The run stops |
| A `kind` is not in the closed list, for example `generator` | The run stops |
| A `location` names a group that `match` does not hold, or holds an empty `{}` | The run stops |
| `config_path` does not end in `.yaml` or `.yml` | The run stops |
| `csv_dir` names a file, or holds none of the declared set and parameter files | The run stops, and the error names `csv_dir` |
| The config YAML cannot be read, or it is not an otoole config | The run stops |
| The name or the `short_name` of a config entry holds `/`, `\` or `..` | The run stops |
| The `model.json` cannot be read, or it is not a JSON object with a `time_definition` | The run stops |

These problems in the data of the model do not stop the run:

- A raw stage problem that the sections on the two sources list. The source leaves out the
  part that it cannot use.
- A value that names a set member that its canonical set does not hold. The engine leaves
  out those rows.
- Two raw tables that write the same canonical row. Each raw table of that canonical
  parameter stays an extension table.
- A `location` group that captures nothing for a member. The location of that member stays
  empty.

The rule for an absent set member applies to each canonical parameter table. The engine
checks each column against the set that it holds, as `columns` states. An empty
cell counts as an absent member. The engine records `COMPONENT_SKIPPED` for each table
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
| A `parameters:` row makes a raw table give no rows | `NOT_MAPPED` |
| The model declares no default, so the default comes from the schema | `TRANSLATOR_DEFAULT_APPLIED` |
| A raw table repeats a key | `COMPONENT_SKIPPED` |
| A canonical table loses rows to absent set members | `COMPONENT_SKIPPED` |
| An `objects:` row gives annotations | `USER_CONFIG_DEFAULT_APPLIED`, with a note that names the row |
| The engine infers annotations | `VALUE_DERIVED`, with a note that names each rule |
| No kind fits a technology | `NOT_MAPPED` |
| A `location` group captures nothing for a member | `NOT_MAPPED` |

The source field of each event has the framework `osemosys`. Three groups of events also
have a destination field, with the framework `osemosys-canonical`:

- Each `VALUE_DERIVED` event.
- Each annotation event, including each `NOT_MAPPED` annotation event.
- Each `TRANSLATOR_DEFAULT_APPLIED` event. Its destination field names the column of
  `defaults.parquet` that the default fills.

Every other event has a source field only. This includes each `COMPONENT_SKIPPED` event, and
each `NOT_MAPPED` event for an extension table.

In a `VALUE_DERIVED` event for a raw table or a raw set, the source field holds the raw name.
The destination field holds the canonical name, for example `osemosys-canonical.set.pollutant`
for the raw set `EMISSION`. An annotation event names its member as the region, a `/` and the
member, for example `R1/ATGASCC1`.

The engine writes one warning for each reason, not one for each table. A warning gives the
count, and it names at most three tables or members. For example:

```
WARNING ... 5 raw table(s) match no canonical parameter by name and key, so each stays an extension table: ATTag, BETag, CHTag and 2 more
```
