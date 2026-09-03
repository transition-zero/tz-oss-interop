# Results format

The results format is the shared shape every solved network or reference
dataset is normalised into before comparison. It is a long-format Parquet table
plus a small run manifest. Names, carriers, and categories use the hub (PyPSA)
vocabulary, so two tables produced from artifacts related by translation align
on plain name equality.

The schema and vocabulary are defined in code and this document mirrors them:

- `interop/plugins/shared/results_constants.py`: the columns, the variable
  vocabulary, the units, and the Polars schema.
- `interop/plugins/shared/results_manifest.py`: the run manifest.

## The table

Each row is one observation. Dense per-component data and sparse per-category
aggregates share the same five columns; a dimension that does not apply to a row
is left null rather than encoded in a second shape.

| Column | Type | Nullable | Meaning |
| --- | --- | --- | --- |
| `variable` | Enum (see vocabulary) | no | What the row measures. |
| `component` | string | yes | Hub component name (a generator, a line). Null on aggregate and scalar rows. |
| `category` | string | yes | Hub carrier the row belongs to (`coal`, `solar`). Null when it does not apply. |
| `timestamp` | datetime, microsecond, naive | yes | The snapshot the observation belongs to. Null on scalar rows. |
| `value` | float64 | no | The number, in the variable's fixed unit. |

Granularity is explicit in which dimensions are populated:

- **Dense** (per-component, per-snapshot dispatch): `component`, `category`, and
  `timestamp` are all set.
- **Sparse** (per-category, per-hour aggregates): `component` is null;
  `category` and `timestamp` are set.
- **Scalar** (the objective): `component`, `category`, and `timestamp` are all
  null.

A null is a null, not zero and not a sentinel. Sparseness is absent rows plus
null dimensions; there is no wide variant and no second table.

## Variable vocabulary

| Variable | Unit | Sign convention | Dimensions typically set |
| --- | --- | --- | --- |
| `dispatch` | MW | positive = generation into the bus | component, category, timestamp |
| `load` | MW | positive = consumption at the bus | component, timestamp |
| `flow` | MW | positive = from `bus0` towards `bus1` | component, timestamp |
| `available_capacity` | MW | positive = usable capacity | component or category, timestamp |
| `surplus` | MW | positive = capacity above load | timestamp |
| `price` | cost/MWh | positive = cost of one more MWh | component, timestamp |
| `snapshot_weight` | h | positive = hours represented | timestamp only |
| `objective` | cost | as reported by the solve | none (scalar) |

The "dimensions typically set" column is the finest granularity a variable
uses; an aggregate row drops the finer dimensions to null, which is how the two
sides of a comparison meet at a shared granularity. `load` never carries a
`category`: demand has no carrier, so its `category` is always null (a
per-component load sets `component`, a system-level load leaves it null).

`price` is the marginal cost of one more MWh at a bus, so its `component` is a
bus and its `category` is always null: a price belongs to a location, not to a
carrier. `available_capacity` is the only per-`category` variable. `surplus` is
system-level headroom: total available capacity, summed across categories,
minus `load` at the same timestamp. A reference dataset may state it directly
instead of deriving it.
`objective` is the solve's objective value, carried as a single scalar row.

## How a comparison meets at a shared granularity

Compare joins the two tables per variable at the finest granularity both sides share.

`dispatch`, which both sides carry per component, is joined on the component:

| side | component | category | timestamp | value |
| --- | --- | --- | --- | --- |
| pypsa | `gen_a` | coal | 2026-09-02 18:00 | 100 |
| sienna | `gen_a` | coal | 2026-09-02 18:00 | 98 |

→ joined on `(variable, component, timestamp)`; the diff is 2 for `gen_a`.

`load`, which one side reports only as a system total, is summed on each side to category grain first:

| side | component | category | timestamp | value |
| --- | --- | --- | --- | --- |
| caiso-plexos | — | — | 2026-09-02 18:00 | 46,844 |
| pypsa | `load_a` | — | 2026-09-02 18:00 | 40,844 |
| pypsa | `load_b` | — | 2026-09-02 18:00 | 6,000 |

→ each side summed to `(variable, category, timestamp)` (both 46,844); the diff is 0.

## Units and signs

Units and signs are fixed by this document. Each side's pipeline is responsible
for emitting values already in these units and signs; nothing downstream infers
them, and the run manifest never restates them. Two consequences follow:

- Power quantities (`dispatch`, `load`, `flow`, `available_capacity`,
  `surplus`) are in MW. Energy is not stored directly: it is a power quantity
  multiplied by the `snapshot_weight` at the same timestamp.
- A framework that solves with a different sign convention (for example, load as
  negative consumption) normalises to the convention above in its own pipeline,
  so no sign has to be guessed at comparison time.

## Run manifest

A small JSON object travels beside the Parquet. It records provenance and the
zone for the table's naive timestamps.

| Field | Meaning |
| --- | --- |
| `framework` | The source the table was normalised from (`pypsa`, `sienna`, `caiso-plexos`). |
| `label` | A human-readable name for the run. |
| `timezone` | IANA zone name for the table's naive timestamps. |
| `translator_version` | The translator version the table was built with. |
| `source_artifact` | The input file the table was normalised from. |

The manifest carries no units or signs; those belong to the format itself. The
translator version is recorded because comparison re-runs translation, so a
table reflects the translator it was built with rather than any earlier run's
decisions.
