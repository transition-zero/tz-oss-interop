# Close the translator gaps that the CEN 12-month programme found

## The problem

The gap analysis in `docs/case_studies/cen-po12meses-2026-09.md` found that a
`plexos-to-sienna` run over the CEN model keeps almost nothing. Each gap below has a Sienna
home, so tz-oss-interop can close it. This spec records how.

## The decisions

### 1. A CSV header is read without letter case

PLEXOS reads a data file header without letter case. The CEN files write `NAME`, `YEAR`,
`MONTH`, `DAY`, `PERIOD` and `VALUE`. The source renames each header that names a known
column (`Name`, `Year`, `Month`, `Day`, `Period`, `Value`, `Pattern`, `DateTime`) to
the canonical spelling before it chooses a layout. A header that names an object or a sample
keeps its spelling.

### 2. A dated value by name is a dated property value

A file with the columns `Name`, `Year`, `Month`, `Day` and `Value`, and no `Period`, gives
one value for each object from a date onward. That is what a dated `t_data` row states. So
the source turns each CSV row into a dated property row, with the CSV value in place of the
XML placeholder and with `data_file` cleared. Then `apply_window` gives the value in force
when the window opens, and the steps inside the window, as it does for a dated `t_data` row.

A property that reads a share of the file through a `Variable` keeps its scaling. An object
that the file does not name keeps its XML row, and the file stays on it, so the mapping
reports it as it does now.

### 3. A chrono step type of 3 is a week

The horizon attribute defaults are `Step Type` 1 and `Chrono Step Type` 2, each with a step
count of 1. The CEN horizon `RP-56w` states `Step Type` 2 with 56 steps and `Chrono Step
Type` 3 with 56 steps. So the chrono step types are 2 for a day and 3 for a week. The source
reads a week as seven days. Other step types keep the warning that sets no snapshots.

### 4. A value by pattern expands onto the snapshots

A file with the columns `Name`, `Pattern` and `Value` (and an optional `Year`, or sample
columns in place of `Value`) gives a value for each pattern. A pattern is a list of terms,
separated by commas, and a snapshot matches when it matches every term. A `;` separates two
such lists, and a snapshot matches the pattern when it matches one of them:

- `M<n>` is the month `n`, from 1 to 12, and `Q<n>` is the quarter.
- `D<n>` is the day of the month, `W<n>` the day of the week from Sunday, and `K<n>` the ISO
  week.
- `H<n>` is the hour `n` of the day, from 1 to 24, and `P<n>` the trading period of the day.
- A term can state a range, such as `H1-3`. A comma before a digit adds a range to the term
  before it, so `H1-3,24` is the hours 1, 2, 3 and 24.
- `!` before a term negates it.
- Any other term names a `Timeslice` object. Its `Include` property reads a file with the
  columns `Year`, `Month`, `Day` and one column for each `Timeslice`, or states a pattern of
  its own. A day is in the `Timeslice` when its value in that column is not 0.

The source needs the snapshots to expand a pattern, so a pattern file stages only when the
horizon sets snapshots. A pattern that the source cannot read covers no snapshot. One
warning names it, and the rows of the other patterns in the file remain.

### 5. A `Load` object becomes a `PowerLoad`

A `Load` object joins one `Node` through the `Load.Node` collection. It becomes one Sienna
`PowerLoad` on the bus of that node. Its `Load` property gives the `max_active_power` and
the profile, in the same way as a region load.

### 6. A value the source could not read is dropped, not guessed

A line whose `Reactance`, `Resistance` or `Max Rating` comes from a data file that did not
stage takes no placeholder. The line keeps the translator default for that field, and the
run records `NOT_MAPPED` with the reason.

### 7. A drop warning names three components

The drop warnings for generators, batteries and storage give one warning for each reason.
Each warning names three components and counts the rest.

### 8. The Sienna homes that the translator writes

| PLEXOS | Sienna |
| --- | --- |
| `Zone` | `LoadZone`, and `ACBus.load_zone` on each node in the zone |
| `Reserve`, with its generators and batteries | `OnlineReserve` for a spinning reserve, `OfflineReserve` for a reserve that an offline unit can give, and one `ServiceAssociation` for each contributor |
| `Forced Outage Rate` and `Mean Time to Repair` | `GeometricDistributionForcedOutage`, and a supplemental attribute association to the unit |
| The hydro cascade: `Storage`, `Waterway` and the generators that name a head or tail storage | `HydroReservoir` and `HydroTurbine`, joined by `upstream_reservoirs`, `upstream_turbines` and `downstream_turbines` |

### 9. The rules the CEN run found

The first translation with decisions 1 to 8 found these rules. Each one is a rule of PLEXOS,
and not of the CEN model.

- **An object name reads without letter case,** and a data file row of a value that reads
  through a `Variable` carries the `Variable`'s name.
- **A membership property's row is named after both of its objects,** in either order.
- **A `Variable` that a property row names escalates the row's data file values.** The
  source multiplies the series by the `Variable`'s series at each snapshot.
- **A staged series with no rows is no series.** The source drops it, with a warning.
- **A generator that states `Units Out` takes its outage from `Units Out` alone.** The
  outage properties then belong to the units out.
- **A unit whose carrier the mappings file names as `ThermalStandard` stays thermal,** even
  where it names a head `Storage`. A `Storage` that only such units draw on is a fuel store,
  which Sienna has no home for.
- **A unit with a head and a tail `Storage`, no pump, and a `Waterway` out of the tail is a
  cascade turbine.** A closed pair stays pumped storage.
- **Every `Storage` of a cascade is a `HydroReservoir`:** each head and tail of a turbine,
  and each `Storage` that a `Waterway` joins to one.
- **`Efficiency Incr` gives a `HydroTurbine` its `conversion_factor`,** as
  `Efficiency Incr / 3600 / base_power`.

## What this spec does not change

- `VoRS` as a reserve demand curve, a `Flow Control` as a phase-shifting transformer, and a
  region `VoLL` as a sheddable load. Each one changes what PowerSimulations solves.
- A data file whose name differs only in letter case from the file on disk. The source
  cannot find it without a way to list a folder, and `FilesystemPort` has none. A new port
  method is a change to a published contract, so it needs a decision of its own.
- A combined-cycle plant. The model states each operating mode as a `Generator` of 0.01 MW,
  and states the plant only through `Constraint` objects that weight `Units Generating`.
  PLEXOS has no class for the plant itself, so a reading of those constraints as a
  `CombinedCycleBlock` would guess from the names. The plant stays with the `Constraint`
  row, which Sienna has no home for.
- `Units Out`. The availability series already applies it as a derate of
  `1 - Units Out / Units`. Decision 2 lets the source read it, so no `PlannedOutage` is
  needed.
- The gaps that Sienna has no home for. The case study lists them.
