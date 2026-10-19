# Results format

The results format is the shared shape every solved network or reference
dataset is normalised into before comparison. It is a long-format Parquet table
plus a small run manifest. Names, carriers, and categories use the PyPSA
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
| `component` | string | yes | PyPSA component name (a generator, a line). Null on aggregate and scalar rows. |
| `category` | string | yes | PyPSA carrier the row belongs to (`coal`, `solar`). Null when it does not apply. |
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

Each generator and each storage unit of a solved PyPSA network has a `dispatch` row in each
snapshot. PyPSA's netCDF export leaves out a series that is 0 in every snapshot, so
`pypsa-to-results` writes 0 for a component that the file states no `p` for, if the network
states an objective. A PowerSimulations.jl solve writes a column for each device that it
models, also when the output is 0, so `sienna-to-results` already has a row for each of them.
A device with no column was not in the solve, and `sienna-to-results` writes no row for it.

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
| `installed_capacity` | MW | positive = capacity in service in the year | component, category, timestamp |
| `new_capacity` | MW | positive = capacity built in the year | component, category, timestamp |
| `production` | MWh in the year | positive = electricity put out | component, category, timestamp |
| `emissions` | t in the year | negative = removed from the air | component, timestamp |

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

### Annual variables

`installed_capacity`, `new_capacity`, `production` and `emissions` are annual. An annual row
takes the timestamp of 1 January of its year, at midnight. A capacity expansion model
reports these variables, and an hourly dispatch does not.

- The `component` of a capacity or a `production` row is a technology. The `component` of an
  `emissions` row is a pollutant, and its `category` is null.
- `production` is the electricity that a technology puts out in the year. The trade between
  two locations is the `production` of the transport technology between them. That is the
  energy that it delivers at its far end. The format has no `trade` variable.
- A conversion between two electricity fuels of one location, for example from transmission
  to distribution, is neither production nor trade. It has no `production`, `installed_capacity`
  or `new_capacity` row. The `controllable_line` record of such a line states
  `is_conversion: true` in `extensions.json`, and the Sienna to PyPSA hop carries the record
  to the PyPSA sidecar. `decisions.md` names each line that this leaves out, and one warning
  names three. Its hourly `flow` row stays.

A Sienna solve over representative periods also gives annual rows. The `extensions.json`
sidecar of the system must hold `representative_period` records. Each record gives the first
hour of a period, its number of hours and its weight. The weight is the number of times that
the period occurs in the year. The `sienna-to-results` pipeline then writes these rows:

- `production` of a generator or a storage is the sum over the hours of the positive part of
  `dispatch`, multiplied by 1 h and by the weight of the period of the hour. The `dispatch` of
  a `RenewableNonDispatch` is its fixed output, the `ActivePowerTimeSeriesParameter` of the
  solve.
- `production` of a `TwoTerminalGenericHVDCLine` is the same sum of the absolute `flow`. The
  solve models the line as lossless, so the energy that it delivers equals the energy that it
  sends.
- `installed_capacity` is `base_power` × `rating` of a generator, `base_power` ×
  `output_active_power_limits.max` of a storage, and `active_power_limits_from.max` of a
  `TwoTerminalGenericHVDCLine` that is not a conversion.
- `installed_capacity` is the nameplate, as the published `TotalCapacityAnnual` of an OSeMOSYS
  model is. `base_power` × `rating` is the nameplate of a plant from OSeMOSYS: `base_power` is
  the residual capacity in MW of electricity, and `rating` is always 1.0. The availability
  factor goes to `active_power_limits.max` and not to `rating`. A plant from PLEXOS or PyPSA
  can state a `rating` below 1.0, a derate, and then this number is less than its nameplate.
- `emissions` of a pollutant is the sum over the generators of `production` multiplied by the
  rate in `emission_rates_t_per_mwh` of the generator record.

The pipeline leaves out a period that cannot give a weight to its hours. These periods are left
out:

- a period with no `first_timestamp`, `hours` or `weight`;
- a period whose `first_timestamp` does not parse, or states a time zone;
- a period whose `hours` is not between 1 and 8784;
- a period whose `weight` is not a finite number of 0 or more;
- a period that holds an hour that an earlier period holds.

An hour of the solve that is in no period has no weight. The pipeline leaves it out of the sum.
It records each run of consecutive hours in `decisions.md` and writes one warning. A component
with a rating and no output in the solve gets `installed_capacity` and no `production`, and the
pipeline reports it. A solve with no `representative_period` records gives no annual rows.

A PyPSA solve over representative periods gives the same annual rows. The `pypsa-to-results`
pipeline writes them when one of these conditions holds:

- a `generators` snapshot weighting of the network is not 1;
- the `extensions.json` beside the network holds `representative_period` records.

The definitions are those of `sienna-to-results`, with the PyPSA fields:

- `production` of a generator or a storage unit is the sum over the snapshots of the positive
  part of `p`, multiplied by the `generators` snapshot weighting.
- PyPSA's netCDF export leaves out a series that is 0 in every snapshot. So if the network
  states an objective, a component with a rating and no `p` gets a `production` of 0. If the
  network states no objective, the component gets no `production` row, and the log warns.
- `production` of a link is the same sum of the power that the link delivers at the end that
  receives it, `max(-p0, 0) + max(-p1, 0)`. A link that loses energy delivers less than it
  sends. Its `category` is null, as for a Sienna HVDC line. The `<name> reverse` link of a
  two-way line adds to the `production` of `<name>`, so the row meets the one Sienna line.
- `installed_capacity` is the nameplate. For a generator it is `p_nom`, because `p_max_pu` is
  what the generator can make, not what it has. For a storage unit or a link it is `p_nom` ×
  `p_max_pu`. A two-way line and its reverse link give one row. The Sienna to PyPSA
  translation writes `base_power` as `p_nom`, and `output_active_power_limits.max` as the
  `p_max_pu` of a storage, so the two pipelines give the same number for a storage. They give
  the same number for a generator where `rating` is 1.0, as for every plant from OSeMOSYS.
- `emissions` of a pollutant is the sum over the generators and the storage units of
  `production` multiplied by the rate in `emission_rates_t_per_mwh` of the `generator` record of
  the sidecar. A Sienna `HydroDispatch` is a generator, and a PyPSA storage unit, so both
  pipelines count its emissions.
- A bus whose carrier is not `AC` or `DC` holds a fuel that is not electricity. A generator, a
  load and a link on such a bus make or take no electricity, so they have no `production`,
  `installed_capacity`, `dispatch`, `available_capacity`, `flow` or `load` row, and the bus has
  no `price` row. A plant link, which draws a fuel at `bus0` and puts out electricity at
  `bus1`, is a plant: its `dispatch` is `-p1`, its `production` is the electricity that it
  delivers, its `installed_capacity` is `p_nom` × `efficiency`, and its `category` is its
  carrier.
- The `emissions` also count a generator of a fuel, with its `production` of the fuel; a plant
  link, with its electricity × `own_emission_rates_t_per_mwh` of its `generator` record, as the
  generator of its fuel counts the fuel; and a link of a fuel, with the positive part of `p0` ×
  the `emission_rates_t_per_mwh` of its `conversion` record.

Two more results pipelines write annual rows:

- `aetos-to-results` reads a published results CSV of an OSeMOSYS model, which holds one value
  for each model year in a row. It also stages the model with its user mappings file, to convert
  the units and to find the electricity fuels. `installed_capacity` comes from
  `TotalCapacityAnnual`, `new_capacity` from `NewCapacity`, and `emissions` from
  `AnnualEmissions`. `production` is the sum over the modes of
  `TotalAnnualTechnologyActivityByMode` × the `OutputActivityRatio` of the electricity fuels.
  The pipeline leaves out a technology that puts out no electricity, and a conversion between
  two electricity fuels at one location, because the Sienna translation has no component for
  either. A technology that discharges a storage takes the name of the storage, as the Sienna
  system names it. The `emissions` of a pollutant are the sum over the regions, under the plain
  name of the pollutant, because the Sienna system keys an emission rate by the pollutant alone.
- `power-systems-investments-to-results` reads an expansion solve. Its rows are in
  [Running a capacity expansion](developer_documentation/capacity-expansion.md#reading-the-results).
  It writes no `emissions` rows, and its rows state no category.

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

An annual variable has its own name, so it never joins with an hourly variable. When both
sides state `production` for a technology, compare joins the rows on
`(variable, component, timestamp)`, and the timestamp is 1 January of the year. When only
one side states an annual variable, the coverage table shows the gap and no diff is made.

## Units and signs

Units and signs are fixed by this document. Each side's pipeline is responsible
for emitting values already in these units and signs; nothing downstream infers
them, and the run manifest never restates them. Two consequences follow:

- Power quantities (`dispatch`, `load`, `flow`, `available_capacity`,
  `surplus`) are in MW. An hourly energy is not stored directly: it is a power
  quantity multiplied by the `snapshot_weight` at the same timestamp. The annual
  `production` is the one energy in the format, in MWh in the year.
- A framework that solves with a different sign convention (for example, load as
  negative consumption) normalises to the convention above in its own pipeline,
  so no sign has to be guessed at comparison time.

## Run manifest

A small JSON object travels beside the Parquet. It records provenance and the
zone for the table's naive timestamps.

| Field | Meaning |
| --- | --- |
| `framework` | The source the table was normalised from (`pypsa`, `sienna`, `caiso-plexos`, `aetos`, `power-systems-investments`). |
| `label` | A human-readable name for the run. |
| `timezone` | IANA zone name for the table's naive timestamps. |
| `translator_version` | The translator version the table was built with. |
| `source_artifact` | The input file the table was normalised from. |

The manifest carries no units or signs; those belong to the format itself. The
translator version is recorded because comparison re-runs translation, so a
table reflects the translator it was built with rather than any earlier run's
decisions.
