# Each canonical schema entry names its columns and their sets in one field

This spec changes the format of a schema entry in
`2026-10-12-sienna-nomenclature-for-canonical-osemosys-design.md`. The names and the
behaviour stay as they are.

## The problem

A canonical schema entry used two fields to state its columns:

```yaml
transport_capital_cost:
  key: [start_region, end_region, fuel, year]
  roles: {start_region: region, end_region: region}
  osemosys_name: CapitalCostTrade
  osemosys_key: [REGION, _REGION, FUEL, YEAR]
```

The user found it hard to read, for two reasons:

- The word "key" names two different things: the canonical columns in `key`, and the
  OSeMOSYS columns in `osemosys_key`. A reader cannot tell which one a sentence means.
- `key` and `roles` state one fact in two places: which columns the table has, and which
  set holds the members of each column.

The user chose option 2 of three: one field that names each column and its set.

## The design

### The entry

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

- `columns` is an ordered mapping. Each item reads "this column holds members of this
  set". The order of the items is the order of the columns in the canonical table. A
  `value` column follows them, as before.
- `osemosys_columns` replaces `osemosys_key`. It lists the columns of the same parameter
  in OSeMOSYS, in the same order as `columns`.
- `key` and `roles` are gone. The word "key" does not appear in the schema file.

### What the loader checks

The loader stops the schema load, as before, when:

- `columns` and `osemosys_columns` have different lengths;
- a set in `columns` is not a canonical set;
- a position in `osemosys_columns` does not name the OSeMOSYS name of the set that the
  same position in `columns` names. `REGION` and `_REGION` both name the set `region`, but
  `REGION` must stand at `start_region` and `_REGION` at `end_region` when the entry holds a
  pair;
- two entries share an `osemosys_name`.

### Words in the code and the documents

The code and the documents call the canonical columns "the columns" and the OSeMOSYS
columns "the OSeMOSYS columns". The word "key" stays only where a document describes a
raw table's own index columns, and there it is written as "index columns".

### A guide for users

A new guide, `docs/tutorials/osemosys-mappings.md`, tells a user how to write the
`osemosys:` part of the mappings file. It uses plain English and many worked examples, each
with a raw table, the mappings rows, and the canonical table that results. The README and
the user tutorial link to it.

## Size

| Part | Time for a coding agent |
| --- | --- |
| The schema file, the loader, the engine reads, the scenarios that name the fields, the developer document | about 45 minutes |
| The user guide | about 45 minutes |
