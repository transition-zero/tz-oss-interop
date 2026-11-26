# Sienna to OSeMOSYS: write an otoole CSV model

Owner: @thomaschristopherking

This epic holds the design. It is the source of the design until the first sub-issue's PR
commits it to `docs/specs/2026-11-25-sienna-to-osemosys-design.md`; after that the spec is, and
this body links to it.

## Goal and scope

Today tz-oss-interop reads OSeMOSYS and writes Sienna. This epic adds the leg back: it reads a
SiennaSchemas 0.2 system and writes an OSeMOSYS model as an otoole CSV directory with its otoole
configuration YAML file. That is the shape of the case study input, which is AETOS and not AEMO:
the run reads `config_otoole_AETOS.yaml` and `CSVFiles/` (`docs/case_studies/aetos.md:44-50`).

The epic also writes two side products, because the files come out of the canonical OSeMOSYS
stage and not out of a Sienna-specific writer:

- `tz-osemosys-to-osemosys-csv` converts a TZ format OSeMOSYS JSON model into an otoole model.
- `osemosys-csv-to-osemosys-csv` reads an otoole model and writes it again. It is the test
  harness of the writer, and it also normalises a model.

**In scope.** A one year dispatch model, with the years that the sidecar names. Every set, the
calendar, the demands, the generators and their operating modes, the storage, the transport, the
trade and the emission policies. One authoritative mapping document,
`docs/translation_mappings/translation-from-sienna-to-osemosys.md`.

**Out of scope.** An output that matches the publisher's own otoole configuration, with its short
file names, its column order and its per country extension tables. Decision 4 records why, and
states the size of the forward leg relay that the per country tables would need.

**Out of scope.** A capacity expansion model built from a Sienna Investments `portfolio.json`
(Decision 8 states its size). A TZ format JSON writer, which is a second sink over the same
steps. A results leg, because the canonical stage reads no OSeMOSYS results
(`docs/translation_mappings/translation-from-osemosys-to-sienna.md:72-75`). An OSeMOSYS solve,
because the repository holds no OSeMOSYS solver.

## Why this is not trivial

**Nothing in the repository writes OSeMOSYS.** Every OSeMOSYS reader runs one way only.
`otoole_config.py` parses a configuration and never writes one
(`interop/plugins/shared/osemosys_canonical/otoole_config.py:50`). `csv_tables.py` reads CSV
files and never writes one (`interop/plugins/shared/osemosys_canonical/csv_tables.py:65-72`).
`schema.py` maps an OSeMOSYS name to a canonical name and has no reverse lookup
(`interop/plugins/shared/osemosys_canonical/schema.py:106-117`). The only OSeMOSYS sink is
`emit_osemosys_canonical_parquet` (41 lines), which writes the canonical parquet files and not
OSeMOSYS files.

**The forward leg divides three values into one, in several places.** A generator's
`base_power` is `residual_capacity × capacity_to_activity_unit / 8760 × the electricity output
ratio` (`docs/translation_mappings/translation-from-osemosys-to-sienna.md:381`), and every cost
and rate of that generator divides by the same ratio (`:387-389`). So the reverse leg recovers
each factor only up to one unknown number for each technology. A storage holds
`efficiency.in` as `technology_to_storage / the input ratio` and `efficiency.out` as
`the output ratio / technology_from_storage` (`:543-544`), so neither factor comes back alone. A
line states its loss as `1 − output ratio / input ratio` (`:604`). An emission limit is the
limit less the exogenous emission, as one number (`:930`).

**The activity ratios of the mode that a component runs are in no record.** The sidecar holds
the other modes in full (`interop/core/osemosys_extensions.py:23-46`), but
`_read_mode_rows` removes the held mode for each parameter in `GENERATOR_RUN_PARAMETERS`, and
that list holds both activity ratio parameters
(`interop/plugins/shared/osemosys_sienna_translations/_operating_modes.py:151-157,264-266`).
A storage, a line and a conversion use `LINK_RUN_PARAMETERS`, which holds the cost only (`:159`),
so their flows do survive.

**The timeslice structure is gone.** A `representative_period` record states the first hour, 24
hours, a weight, the season, the day type and `DaysInDayType`
(`interop/core/osemosys_extensions.py:103-119`). It states no `TIMESLICE` member, no `YearSplit`,
no `DaySplit` and no `Conversionls`, `Conversionld` or `Conversionlh` membership. Where the
timeslices of one day hold different weights, the forward leg takes their mean
(`docs/translation_mappings/translation-from-osemosys-to-sienna.md:968-972`).

**The units are gone.** Every value in a Sienna system is in MW, MWh, dollars or tonnes
(`interop/plugins/shared/osemosys_sienna_translations/_units.py:33-60`). The `units:` block of
the mappings file reaches the canonical metadata table only
(`interop/plugins/shared/osemosys_canonical/metadata.py:61,128-133`), which neither `system.json`
nor `extensions.json` holds.

**The canonical layer reads one side of `State` only.** `list_canonical_tables` and
`set_canonical_table` read and write `source_topology` and `source_time_series`
(`interop/plugins/shared/osemosys_canonical/canonical_stage.py:122-143`). Every other
destination leg writes `destination_tables` and `destination_time_series`
(`interop/core/pipeline.py:98-99`). Decision 3 settles which side the outgoing tables use.

**`compare` cannot check the round trip.** It refuses two sides of one framework
(`interop/core/use_cases/compare.py:89-92`), and `tests/features/compare.feature:6` states the
rule. The round trip test follows `tests/features/pypsa_to_sienna_to_pypsa.feature` instead,
which writes a `compose:` chain in the test and asserts on the output of the second leg
(`tests/step_defs/test_pypsa_to_sienna_to_pypsa.py:14-32`).

**The two sides of the test already exist.** `SiennaSystemBuilder` writes a system JSON file, an
InfraStore sidecar and an `extensions.json` sidecar together
(`libs/interop-testing/src/interop_testing/builders/sienna_systems.py:845-894`), so a test needs
no forward run to make its input. `OtooleModelBuilder` writes an otoole directory
(`libs/interop-testing/src/interop_testing/builders/otoole_models.py:85-128`), and
`steps/osemosys_model.py` holds its Gherkin `Given` steps. The epic adds the `Then` steps that
assert an otoole directory, in the same module.

## Decisions

### 1. The name of the OSeMOSYS destination framework: **Decided**

A pipeline states `source_framework` and `destination_framework`, and both are plain strings with
no enum behind them (`interop/core/composition/document.py:26-27`). The REPL lists the values
themselves as the choices at `Source framework?` and `Destination framework?`
(`interop/adapters/inbound/interactive_cli/app.py:103-118`). Today the otoole CSV pipelines say
`osemosys` (`interop/pipelines/osemosys-csv-to-sienna.yaml:1`) and the TZ JSON pipelines say
`tz-osemosys` (`interop/pipelines/tz-osemosys-to-sienna.yaml:1`). A new pipeline that said
`destination_framework: osemosys` would not say which of the two shapes it writes.

otoole itself reads and writes three shapes: a directory of CSV files, an Excel workbook and a
GNU MathProg datafile (https://otoole.readthedocs.io/en/stable/functionality.html). So the name
of the tool alone does not say which shape a pipeline writes, and a name that states the shape
also leaves room for an Excel writer or a datafile writer later.

- **Option A: keep `osemosys`.** No file changes. The REPL then offers `osemosys` as a
  destination, and the user cannot see from the name which shape the run writes.
- **Option B: rename the value to `osemosys-csv`.** Every pipeline file stem already says
  `osemosys-csv`, so the value and the stem agree. The change touches three pipeline files, one
  test module (`tests/step_defs/osemosys_to_sienna/test_osemosys_to_sienna.py:92`) and five
  documentation lines (`docs/tutorials/osemosys-mappings.md:200`,
  `docs/tutorials/user-tutorial.md:416`, `docs/case_studies/aetos.md:254,355`).
- **Option C: rename the value to `otoole-csv`.** It names the tool that defines the shape, and
  the developer documentation already writes "the otoole CSV format"
  (`docs/developer_documentation/osemosys-canonical-format.md:669`). The name drops the word
  OSeMOSYS, so the REPL then offers `otoole-csv` and `tz-osemosys` with no shared word, and a
  user who looks for OSeMOSYS sees one of the two. It also disagrees with the pipeline file
  stems, with the `osemosys:` key of the mappings file
  (`interop/plugins/shared/osemosys_canonical/mappings.py:226`) and with the plugin name
  `stage_osemosys_csv`. None of those three can change, because each is a published key.
- **Option D: rename the value to `osemosys-otoole-csv`.** It states the format family, the tool
  and the shape, and both OSeMOSYS values then start with the same word. It renames six pipeline
  files, because no stem holds that word today. `otoole-osemosys` is the same idea without the
  shape, and it does not say which of otoole's three shapes the run writes.

In every option the translation event label stays `osemosys`
(`interop/plugins/shared/osemosys_canonical/constants.py:5`). Both OSeMOSYS legs share that
label, because both sources derive from `OsemosysCanonicalSource`
(`interop/plugins/shared/osemosys_canonical/canonical_source.py:33-36`). A rename of the label
would mislabel every event of the TZ JSON leg, and would change about 105 assertions in twelve
feature files.

**Recommendation:** B. The file stems already use that word, so the rename makes the value agree
with a name the repository states 40 times, and it leaves the shared event label alone. It also
keeps `osemosys` as the first word, so the REPL shows both OSeMOSYS destinations together, and
`osemosys-excel` and `osemosys-datafile` stay available for a later writer.

**Decided:** B, the framework value becomes `osemosys-csv`. @thomaschristopherking, 2026-11-26 (direct, no issue comment).

### 2. The route from a Sienna system to the CSV files: **Decided**

- **Option A: through the canonical stage.** The steps write canonical OSeMOSYS tables, and one
  sink writes the otoole files. The canonical schema states the OSeMOSYS name, the column order
  and the default of each parameter (`interop/plugins/shared/osemosys_canonical/schema.py:27-37`,
  `interop/plugins/shared/osemosys_canonical_schema.yaml:43-50`), so the sink needs no new
  mapping data. The same sink serves the two format conversion pipelines, and a later TZ JSON
  writer is a second sink with no new steps.
- **Option B: direct.** One group of steps writes the CSV rows. There is no format conversion
  product and no reuse, and each step states the OSeMOSYS name of each parameter itself.

**Recommendation:** A. It gives three pipelines for the work of one, and it keeps the OSeMOSYS
names in the one file that already holds them.

**Decided:** A, through the canonical stage. @thomaschristopherking, 2026-11-26 (direct, no issue comment).

### 3. Which side of `State` the outgoing canonical tables use: **Decided**

- **Option A: add a destination side pair of functions.** The reverse steps then write
  `destination_tables` and `destination_time_series`, as every other leg does. The table key
  becomes one string, for example `parameter/capital_cost`, because `destination_time_series`
  takes a string key and not a tuple (`interop/core/pipeline.py:94,99`). About 30 lines in
  `interop/plugins/shared/osemosys_canonical/canonical_stage.py`.
- **Option B: the reverse steps write the source keys.** No new code. A step then fills the field
  that the `State` docstring reserves for a source (`interop/core/pipeline.py:39-50`), and a
  reader of the state cannot tell a staged table from a built one.

**Recommendation:** A. The cost is 30 lines once, and it keeps one rule about which side of
`State` a step writes.

**Decided:** A, add the destination side pair of functions. @thomaschristopherking, 2026-11-26 (direct, no issue comment).

### 4. What the written otoole model states: **Decided**

The canonical stage holds no otoole configuration. Three parts of a configuration have no
canonical home. `dtype` is absent, although every real configuration states it
(`interop/templates/examples/osemosys/inputs/model/config.yaml:3,12,19`) and the reader ignores
it (`interop/plugins/shared/osemosys_canonical/otoole_config.py:34-38`). `short_name` is read for
the file name only. `default_from` names another parameter instead of a number
(`interop/plugins/shared/osemosys_canonical/metadata.py:101-125`).

- **Option A: write the canonical shape.** One CSV file for each canonical parameter under its
  `osemosys_name`, one for each set, one for each extension table under its raw name, and a
  configuration built from the schema and the `metadata/defaults` table. `dtype` is `float` for a
  parameter and `str` for a set. A step resolves `default_from` into a number before the sink
  runs, so the sink makes no decision and the format conversion pipelines carry that step.
- **Option B: take the input model's configuration as a sink parameter.** The output then matches
  the publisher's layout, with its `short_name` values and its column order. A Sienna system
  carries no configuration, so the run needs the original file as a separate input.

**Recommendation:** A. It is what every test of rungs 2 to 7 asserts against. B can follow later
as a sink parameter of about 40 to 60 lines, with no change to a step.

**Decided:** A, write the canonical shape. @thomaschristopherking, 2026-11-26 (direct, no issue
comment).

**Not planned: reproduce a publisher's file names.** AETOS loses 159 of its 224 tables, and the
warning says why: "159 raw table(s) match no canonical parameter by name and key"
(`docs/case_studies/aetos.md:201-204`). 78 of them are `ReserveMarginTagTechnology` and 78 are
`YearlyPeak`, each split into one file for each country, with the country code inside the file
name: `ATReserveMarginTagTechnology` and `YearlyPeakAT` (`docs/case_studies/aetos.md:225-232`).
Both parameters are canonical under their own names, and the forward leg turns
`ReserveMarginTagTechnology` into a `constraint` record of the sidecar
(`docs/translation_mappings/translation-from-osemosys-to-sienna.md:934`). So this loss is one
publisher's file naming habit, and not a class of data. A model that names its files as core
OSeMOSYS names them loses neither parameter.

To return AETOS's own file names, the forward leg must relay each unclaimed extension table
through the sidecar, because it reads none of them today
(`docs/translation_mappings/translation-from-osemosys-to-sienna.md:1166`). The sidecar already
writes a companion parquet file for each kind
(`interop/plugins/shared/extensions_sidecar.py:109-124`), so a new kind that holds one relayed
raw table fits the shape that exists. Size: about 200 to 300 lines of non-test code across the
forward leg and the reverse leg, and one more rung. This epic does not do it. The two format
conversion pipelines need none of it, because the canonical stage already keeps every extension
table under its raw name with its own columns
(`interop/plugins/shared/osemosys_canonical/parameter_mapping.py:352-355`).

### 5. Is `extensions.json` a required input: **Decided**

`stage_sienna_system_json` takes the sidecar path as an optional parameter
(`interop/plugins/sources/stage_sienna_system_json.py:110-116`). The sidecar holds the parts of
OSeMOSYS that a Sienna system has no field for: the operating modes, the representative days and
every fuel that is not electricity (`interop/core/osemosys_extensions.py:23-46,103-119,148-183`).

- **Option A: required.** The leg translates only a Sienna system that a tz-oss-interop OSeMOSYS
  run wrote. A system from PLEXOS or from PyPSA is refused.
- **Option B: optional.** With no sidecar the leg writes one operating mode for each technology,
  one timeslice for each hour of the series, and an electricity only model. It records each value
  that it invents. A PLEXOS or a PyPSA model then reaches OSeMOSYS through Sienna.

**Recommendation:** B. It agrees with the rule that a model's data never stops a translation, and
it gives PLEXOS to OSeMOSYS and PyPSA to OSeMOSYS at little extra cost.

**Decided:** B, `extensions.json` is an optional input. @thomaschristopherking, 2026-11-26 (direct, no issue comment).

### 6. The units of the written model: **Decided**

- **Option A: always write MW, MWh, USD and tonnes, and write a mappings file beside the model.**
  The mappings file states those units, so a second run over the output gives the same Sienna
  system. `emit_carrier_mappings` is the pattern for writing a YAML file through the port
  (`interop/plugins/sinks/emit_carrier_mappings.py:46-49`).
- **Option B: take a `units:` block and write the model in the units that it names,** for example
  GW and PJ as AETOS uses (`docs/case_studies/aetos.md:148-150`). The numbers then match the
  publisher's model. Each value needs one more conversion, and a wrong block gives a wrong model
  with no error.

**Recommendation:** A. It makes the round trip exact, and B can follow without changing a step.

**Decided:** A, always write MW, MWh, USD and tonnes, with a mappings file beside the model. @thomaschristopherking, 2026-11-26 (direct, no issue comment).

### 7. How a Sienna calendar becomes the OSeMOSYS timeslices: **Decided**

- **Option A: one timeslice for each hour of each representative period.** `YearSplit` is the
  weight of the period divided by the hours of a year. The season, the day type and the daily
  time bracket come from the record, and `DaysInDayType` comes back as it is. This is the only
  option that rebuilds the day structure of the input model.
- **Option B: aggregate the hours into a small timeslice set,** for example one timeslice for
  each season. The model is then much smaller and faster to solve. The hourly shape is lost, and a
  second forward run gives a different Sienna system.

**Recommendation:** A. Only A round trips, and a user who wants B can aggregate the output.

**Decided:** A, one timeslice for each hour of each representative period. @thomaschristopherking, 2026-11-26 (direct, no issue comment).

### 8. The years that this epic writes: **Decided**

- **Option A: one `system.json` and its sidecar.** The `YEAR` set holds the years that the
  `ByYear` fields of the sidecar name (`interop/core/osemosys_extensions.py:49-84`), and one year
  where they name none. The model solves as a dispatch.
- **Option B: also read a `portfolio.json`, and write a capacity expansion model.** The
  `technology` records hold the per year investment and growth values
  (`interop/plugins/shared/osemosys_sienna_investments_translations/_extensions.py:71-84`), and
  `stage_sienna_portfolio_json` already reads a portfolio. The leg then needs a second source and
  a second group of steps: about 400 to 600 lines of non-test code, and two more rungs.

**Recommendation:** A for this epic, and B as its own epic once A works.

**Decided:** A, one `system.json` and its sidecar. @thomaschristopherking, 2026-11-26 (direct, no issue comment).

### 9. How a test proves the output: **Decided**

The repository holds no OSeMOSYS solver and no otoole dependency (`pyproject.toml:27-40`). So a
test can prove the shape of the files, and not that OSeMOSYS solves them.

- **Option A: prove it by reading the output again.** A test stages the written model with
  `stage_osemosys_csv` and compares the canonical tables with the ones that went in. No new
  dependency, and the test runs in CI.
- **Option B: add otoole as a development dependency.** A test then converts the written model
  with otoole, which proves that otoole accepts the configuration and the CSV files. otoole brings
  its own dependency tree, and the test needs the network or a pinned wheel.

**Recommendation:** A, with a command in the case study page that a person runs with otoole by
hand.

**Decided:** A, prove the output by reading it back with `stage_osemosys_csv`. @thomaschristopherking, 2026-11-26 (direct, no issue comment).

### 10. A fuel with no producer in the year: **Decided**

OSeMOSYS states no unserved energy variable, so a region that cannot meet its
`SpecifiedAnnualDemand` makes the whole model infeasible. The forward leg can leave that gap. It
prices a fuel by the cheapest producer of that fuel that can run in the year, and it leaves out
a plant whose fuel has producers and none of them can run
(`docs/translation_mappings/osemosys-to-sienna-gap-analysis.md:116`). In AETOS the only producer
of the gas of `MR` and `GW` is a backstop with no capacity in the year, so the forward leg drops
it, and the gas bus of each of those countries then has no supply
(`docs/case_studies/aetos-comparison.md:167-176,279`). The Sienna dispatch leaves 1,141.1 MWh
unserved over its 96 hours and pays for it. A written OSeMOSYS model with the same gap does not
solve at all.

- **Option A: a step adds a backstop technology for each fuel with demand and no producer.** The
  step writes one technology on that fuel, with no capacity limit and a cost above every other
  producer of the model, and records one event for each one. The model then solves, and the
  activity of the backstop shows the size of the gap in the results. The step must be a step and
  not the sink, because a sink makes no decisions and records no event (root `CLAUDE.md`). The
  written model then holds a technology that no source model stated, which no other sink or step
  in the repository does.
- **Option B: leave the gap and report it.** The sink writes what the Sienna system holds, and a
  validator reports each fuel with demand and no producer. The user adds a backstop by hand.
  Nothing invented reaches the file, and the model does not solve as written.
- **Option C: a sink parameter, with B as the default.** Both behaviours, chosen for each run.
  One more parameter on the manifest, and two code paths to test.
- **Option D: the forward leg relays the producer that cannot run.** A `fuel_supply` technology
  of a fuel that is not electricity already becomes a `generator` record of the sidecar
  (`interop/plugins/shared/osemosys_sienna_translations/_fuel_records.py:197-204`). The forward
  leg leaves the record out when the producer has no capacity that can run in the year
  (`interop/plugins/shared/osemosys_sienna_translations/_fuel_supply.py:124-146`). Instead it
  keeps the record, with `p_nom` 0 and `p_nom_extendable` true, and the reverse leg writes the
  technology that the source model stated, with its real `CapitalCost`, `OperationalLife` and
  `FixedCost`. OSeMOSYS holds `NewCapacity` as a decision variable in every model, one year
  included, so the solve builds that producer and the model solves on the publisher's own
  numbers. Nothing is invented, and every value traces to the input.

  The sidecar needs no new field. `GeneratorExtension` inherits `ExpansionExtension`, which
  states `overnight_cost_per_mw`, `technical_life_years` and `fom_charge_per_mw_year`
  (`interop/core/extension_records.py:37-57`). `_generators.py:432` already sets the fixed cost
  on a generator record, and the `sienna-to-pypsa` leg already reads `overnight_cost_per_mw`
  (`interop/plugins/shared/sienna_pypsa_translations/overnight_cost.py:32`). So there is no new
  record kind and no new rung. What is missing is that `_build_rated_fields` reads neither the
  capital cost, nor the life, nor the fixed cost
  (`interop/plugins/shared/osemosys_sienna_translations/_fuel_records.py:176-191`). Size: about
  40 to 80 lines of non-test code in the forward leg, and about 20 in the reverse leg.

  Two limits. The price of the fuel still differs from the publisher's, because a one-year model
  period annualises a long-lived asset differently from a 35-year one. And the Sienna system
  itself gains a producer record that no Sienna component holds, so the Sienna dispatch and a
  PyPSA network of the same run are unchanged: this closes the gap for the OSeMOSYS output only.

  Not verified: how OSeMOSYS v1.0.1 computes `SalvageValue` over a one-year model period, which
  sets how much of the capital the solve pays.

**Recommendation:** D, for a Sienna system that a tz-oss-interop OSeMOSYS run wrote. It returns
the source model's own technology instead of inventing one, it needs no new sidecar field, and it
is the only option that both solves and keeps every number traceable to the input. Decision 5
admits a system with no sidecar, for example one from PLEXOS, and D cannot reach that case, so
B's report covers it: a validator names each fuel with demand and no producer, and the user
supplies one. A stays available if the owner later wants an output that always solves.

**Decided:** D, the forward leg relays the producer that cannot run, with B's validator report
for a system that carries no sidecar. @thomaschristopherking, 2026-11-26 (direct, no issue
comment).

D changes the forward leg, which no other decision of this epic does, so it adds sub-issue 8
below and the AETOS round trip becomes sub-issue 9.

### 11. Which parameter set the output declares: **Decided**

The canonical schema holds 82 parameters, and each one states its `origin`
(`interop/plugins/shared/osemosys_canonical/schema.py:37`): 54 from OSeMOSYS v1.0.1
(`interop/plugins/shared/osemosys_canonical_schema.yaml:51`), 25 from tz-osemosys v0.4.1 and 3
from the OSeMOSYS MUIO model v5.7
(`interop/plugins/shared/osemosys_canonical_schema.yaml:909,921,933`). GNU MathProg refuses a
datafile that sets a parameter that its model file does not declare. So a model written with all
82 does not run on a stock OSeMOSYS v1.0.1 model file.

- **Option A: write the core 54 by default, and the other 28 behind a sink parameter.** The
  default output runs on a stock OSeMOSYS model file. A user of tz-osemosys, or of a MUIO model
  file, asks for the rest. The sink reports each parameter that it leaves out, with its origin,
  so nothing goes quietly.
- **Option B: always write all 82.** Nothing is lost, and the user deletes the files that their
  model file does not declare. A round trip through the canonical stage is exact in one run. The
  default output does not run on a stock model file.
- **Option C: write every table that `State` holds.** The set of files then follows from the run
  and not from a rule: a format conversion run writes what its input stated, and a Sienna run
  writes what its steps built. No sink parameter, and no report of what is absent.

**Recommendation:** A. It is the only option whose default output a stock OSeMOSYS run accepts,
and the report names each parameter that it drops. Note that A and the round trip test of
decision 9 disagree, so the test asks the sink for all 82.

**Decided:** A, write the core 54 by default, and the other 28 behind a sink parameter. @thomaschristopherking, 2026-11-26 (direct, no issue comment).

The round trip test of decision 9 therefore asks the sink for all 82.

## Changes by package

- `interop/plugins/sinks/emit_osemosys_csv.py`: new sink. It writes the set CSV files, the
  parameter CSV files, the extension CSV files and the configuration YAML file, each through
  `self._fs`.
- `interop/plugins/shared/osemosys_canonical/otoole_tables.py`: new. It reverses each column name
  and builds the CSV bytes of one canonical table.
- `interop/plugins/shared/osemosys_canonical/otoole_config.py`: add `build_otoole_config`.
- `interop/plugins/shared/osemosys_canonical/canonical_stage.py`: add the destination side pair of
  functions (Decision 3).
- `interop/plugins/steps/osemosys_canonical_resolve_defaults.py`: new step. It turns each
  `default_from` into a number, so the sink makes no decision.
- `interop/plugins/steps/sienna_to_osemosys/`: new package. One module for each component group,
  and `relate_components.py`, which derives each set table from the parameter tables that the
  other steps wrote. `interop/plugins/steps/sienna_relate_components.py:85-113` is the pattern.
- `interop/plugins/shared/sienna_osemosys_translations/`: new package. The column expressions and
  the event factories.
- `interop/pipelines/sienna-to-osemosys-csv.yaml`, `osemosys-csv-to-osemosys-csv.yaml`,
  `tz-osemosys-to-osemosys-csv.yaml`: new.
- `docs/translation_mappings/translation-from-sienna-to-osemosys.md`: new, and the authoritative
  mapping. Rung 1 writes the skeleton and each later rung extends it.
- `docs/specs/2026-11-25-sienna-to-osemosys-design.md`: new, committed by rung 1 before its code.
- `interop/plugins/shared/osemosys_sienna_translations/_fuel_records.py` and `_fuel_supply.py`:
  the forward leg relay of Decision 10. It keeps the record of a producer that cannot run, and
  sets the three `ExpansionExtension` fields on every producer record.
- `docs/case_studies/aetos.md`: a round trip section (rung 9).
- `CLAUDE.md`: a "Sienna to OSeMOSYS" scope section that records Decisions 1 to 11.
- `libs/interop-testing/src/interop_testing/steps/osemosys_model.py`: add the `Then` steps that
  assert an otoole directory.

## Test plan

Every feature file sits under `tests/features/sienna_to_osemosys/` and carries `@slow
@fork_unsafe`, because each one runs a Polars compute. A step file binds its scenarios with
`scenarios(...)` and imports no `interop.*` name, which
`uv run python scripts/lint_test_decoupling.py` enforces.

| Acceptance criterion | Test (public boundary) |
| --- | --- |
| The writer inverts the reader over every canonical table | `osemosys-csv-to-osemosys-csv` over the shipped example, then stage the output and compare each canonical table with the input's |
| A TZ JSON model becomes an otoole model | `tz-osemosys-to-osemosys-csv` over a `TzOsemosysModelBuilder` model; the output has one CSV file for each stated parameter |
| The written configuration reads back | `stage_osemosys_csv` over the written directory raises no error and drops no table |
| A `default_from` parameter gets a number | the written configuration states a number for every parameter that has a default |
| The sets come back from the parameter tables | a system with two technologies gives a `TECHNOLOGY.csv` with two members, and no member that no parameter names |
| Each representative day gives its timeslices | a system with two `representative_period` records gives 48 `TIMESLICE` members, and `YearSplit` sums to 1 |
| A demand becomes a demand | a `PowerLoad` gives one `SpecifiedAnnualDemand` row and one `SpecifiedDemandProfile` row for each timeslice |
| A generator's held mode and its other modes both come back | a generator with two `operating_modes` records gives three `MODE_OF_OPERATION` members and three `VariableCost` rows |
| A system with no sidecar still gives a model | the output holds one mode for each technology, and `decisions.md` records each invented value (Decision 5) |
| A storage comes back | an `EnergyReservoirStorage` gives one `STORAGE` member, a `TechnologyToStorage` row and a `TechnologyFromStorage` row |
| A line comes back | a `TwoTerminalGenericHVDCLine` gives a technology with two modes and a `TradeRoute` row |
| An emission limit comes back | a `constraint` record gives an `AnnualEmissionLimit` row and an `EMISSION` member |
| What cannot come back is reported | each value the leg cannot rebuild gives a `NOT_MAPPED` event, and the log names at most three components |
| The Sienna round trip holds its values | a `compose:` chain of `osemosys-csv-to-sienna` and `sienna-to-osemosys-csv`, as `tests/features/pypsa_to_sienna_to_pypsa.feature` does |

## Sub-issues

1. #188 Write an otoole CSV model from the canonical OSeMOSYS stage (size M)
2. #189 Rebuild the OSeMOSYS frame, the calendar and the buses from a Sienna system (size L)
3. #190 Translate each Sienna load into an OSeMOSYS demand (size M)
4. #191 Translate each Sienna generator into an OSeMOSYS technology (size L)
5. #192 Translate each Sienna storage into an OSeMOSYS storage (size M)
6. #193 Translate each Sienna line and conversion into an OSeMOSYS technology (size L)
7. #194 Translate each Sienna policy into an OSeMOSYS limit (size M)
8. #195 Relay the producer that cannot run through the sidecar (size M)
9. #196 Run the AETOS round trip, and write down what it loses (size M)

Rung 8 is independent of rungs 5 to 7, and rung 9 waits on both 7 and 8.
