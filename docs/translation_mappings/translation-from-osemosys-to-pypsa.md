# Translation from OSeMOSYS to PyPSA

This document tells you what the translator reads from your OSeMOSYS model. It gives the
shape of each input and the rules the translator applies to it.

> **Scope:** the translator accepts an otoole CSV folder and the otoole config YAML that
> declares it, and only that. Refer to
> [What the translator reads](#what-the-translator-reads). This version stages the model.
> It does not yet map any part of it into a PyPSA network, so this document carries no field
> mapping tables. Refer to [What this version does](#what-this-version-does).

---

## What the translator reads

The translator reads two inputs.

| Input | Required | Holds |
| --- | --- | --- |
| The CSV folder | Yes | One CSV per set and one per parameter. |
| The config YAML | Yes | What each set and each parameter is: its index columns in order, its data type and its default. |

Give each one to the translator by name. The config is a separate answer, not a file the
translator looks for inside the folder, because a model puts the config beside the folder and
gives it a name of its own.

The translator reads the config first, then reads what the config declares. It holds no list
of OSeMOSYS parameters of its own.

## What this version does

This version stages your model. It reads each declared set and each declared parameter into a
table, and it says which table holds which. It writes no PyPSA network yet.

The four questions that a mapping must answer are open: what a `TECHNOLOGY` becomes, what a
`FUEL` becomes, what a `TIMESLICE` becomes, and what a `YEAR` becomes.

## What the translator refuses

| Input | What to do |
| --- | --- |
| An Excel workbook | Run `otoole convert` first. It writes the CSV folder. |
| A GNU MathProg datafile | Run `otoole convert` first. It writes the CSV folder. |
| A folder with no readable config | Give the translator the config YAML your model ships with. |

Each one stops the run. A missing input is not model data, so the translator does not carry
on without it.

## The config file

The config maps each name to what it declares. A set states its data type. A parameter also
states its index columns, in order, and its default.

```yaml
TECHNOLOGY:
    dtype: str
    type: set
CapacityFactor:
    indices: [REGION, TECHNOLOGY, TIMESLICE, YEAR]
    type: param
    dtype: float
    default: 1
```

| Key | What it names |
| --- | --- |
| `type` | `set`, `param` or `result`. |
| `dtype` | `str`, `int` or `float`. It gives the type of the `VALUE` column. |
| `indices` | The index columns of a parameter, in the order the CSV writes them. A set has none. |
| `default` | The value of a parameter where the CSV states no row. A set has none. |
| `short_name` | An optional second name of at most 31 characters. Refer to [Short names](#short-names). |

### The translator reads two of the three entry types

| Type | What the translator does |
| --- | --- |
| `set` | Reads it. |
| `param` | Reads it. |
| `result` | Does not read it. A result names a solve output, not an input. |

An index column of a parameter must name a set the config declares, because the set gives
that column its type. A config that indexes a parameter by a name it declares no set for
stops the run. A parameter must also name each of its index columns once: a config that
indexes a parameter by the same set twice stops the run, because the translator cannot give
one column name to two columns.

## Which OSeMOSYS parameter list the translator targets

Your config decides. The standard OSeMOSYS parameter list differs between OSeMOSYS versions,
and a model can add to it: a model that runs a variant model file states the parameters that
variant needs. The translator reads whatever the config declares, so it reads those too.

A parameter the config declares and the folder does not hold is left out. The run carries on
and stages the rest of the model. The translator gives a warning that names the first few and
the reason for each, and it marks each one in the [declarations table](#the-declarations-table).

## The column layout

| CSV | Columns |
| --- | --- |
| A set | One column, `VALUE`. |
| A parameter | The index columns in the order the config gives, then `VALUE`. |

The translator reads the header of each CSV against the columns the config declares. A CSV
whose header is different is left out, in the same way as a CSV the folder does not hold. So
is a CSV that holds a value that does not fit the type the config declares, and a CSV the
reader cannot parse at all.

The translator keeps each column name as your CSV writes it, and it keeps each value whole.
A model can put more in a name than its sets do: `REGION` can have one member while a
two-letter prefix on each technology name gives the country. Reading a country out of a name
is the job of a mapping, not of staging.

## Defaults

An OSeMOSYS CSV holds only the values that differ from the default. The translator keeps it
that way. It does not fill the default in.

The reason is size. Filling the default for one parameter of a model with 3,158 technologies
over 35 years writes 110,530 rows for a parameter that may state ten of them.

The translator carries each default forward instead, in the
[declarations table](#the-declarations-table), so a later step applies the default to the rows
your CSV leaves out.

A parameter that sits wholly at its default is a CSV with a header and no rows. The translator
stages it as an empty table with the types the config declares, and not as text.

## Short names

The config can give an entry a `short_name` of at most 31 characters, because GLPK limits the
length of a symbol name. A model that feeds GLPK can file the CSV under either name.

The translator looks for `<name>.csv` first. If the folder does not hold it, the translator
looks for `<short_name>.csv`.

## Where the translator puts each table

| The parameter is indexed by | Where it goes | What a later step may do |
| --- | --- | --- |
| `TIMESLICE`, and also `TECHNOLOGY`, `FUEL` or `STORAGE` | The time series tables | Take a summary of it. It can be millions of rows. |
| Anything else | The topology tables | Read all of it. |

A parameter indexed by `TIMESLICE` and by a component set holds a profile of those
components, so it is large: one number per component, per timeslice, per year. A parameter
indexed by `TIMESLICE` alone states how the timeslices divide up a year. That is model
structure, it is small, and a step must read all of it, so it goes with the topology.

Each declared set goes with the topology as well, as a table of its members.

## The declarations table

The translator writes one more topology table, `declarations`, with one row per set and per
parameter the config declares.

| Column | Holds |
| --- | --- |
| `name` | The name the config declares. |
| `entry_type` | `set` or `param`. |
| `dtype` | `str`, `int` or `float`. |
| `indices` | The index columns, in order. Empty for a set. |
| `default` | The default the config gives. Empty for a set. |
| `short_name` | The short name, where the config gives one. |
| `is_staged` | False where the config declared the entry and the source could not read it. |

This table is how a later step learns a default it must apply, and which parameters the model
did not deliver.
