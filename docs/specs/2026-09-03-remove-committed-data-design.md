# Remove the committed data files

Design for taking every third-party data file out of the repository before it goes public.

## Problem

Two data files in the tree are somebody else's.

`interop/data/caiso_plexos/` holds two CSVs of figures from CAISO's published 2026 Summer
Assessment. Hatchling packages the whole `interop/` tree, so they ship in the wheel, the
source distribution and the container image, under an Apache 2.0 banner and with no
statement of where they came from or on what terms.

`tests/inputs/pypsa_1_week.nc` is a 1.1 MB solved European network with PyPSA-Eur's
clustering names and carriers. Two scenarios in `stage_pypsa_network_file.feature` read it.
Whatever its provenance, network data of that shape carries the terms of the sources
underneath it — OpenStreetMap-derived topology and reanalysis weather among them.

Neither is required. The remaining data, the tutorial network under
`interop/templates/examples/pypsa/inputs/`, was written for the purpose: one bus, one
generator, a sinusoidal load profile. It stays.

## Outcome

interop redistributes no model data. The CAISO comparison still runs, against numbers the
user supplies. The staging scenarios still cover every component class. A lint stops the
next data file arriving.

## The CAISO stack model becomes a user-supplied input

`stage_caiso_plexos_stack_model` stops reading package data through
`importlib.resources` and takes two `InputFile` params instead, read through the
`FilesystemPort` like every other source:

```yaml
source:
  name: stage_caiso_plexos_stack_model
  params:
    stack_model_path: case_study_inputs/caiso-sa26/stack_model.csv
    appendix_path: case_study_inputs/caiso-sa26/appendix_capacity_by_fuel_month.csv
```

The params in the YAML are prompt defaults, not fixed paths: the REPL offers them and
validates whatever the user submits, so a missing file is re-asked rather than crashing
mid-pipeline. This puts the reference data under the same `case_study_inputs/` convention
the models already use.

`docs/case_studies/caiso-sa26.md` gains two sections. One says which published document
each CSV comes from, and gives every column the source reads, what it holds, and how the
pipeline reads it: the hour-ending-minus-one alignment, the `Charging Load (Y/N)` filter,
the fixed 2026 year, the May-to-September appendix scope, and the fuel roll-ups. The other
says exactly what to answer at each `compare` prompt.

Nothing about the mapping code changes. The column headers stay as the assessment spells
them, because a format's field names are its interface.

## The scenarios build their own fixtures

`CaisoStackModelBuilder` in `interop-testing` writes the pair of CSVs in the source's
column shape, defaulting every category column to zero so a scenario states only the
values it asserts on. Its Given steps live in `interop_testing.steps.caiso_stack_model`,
following the pattern every other framework already uses.

The seven CAISO scenarios keep the behaviour they covered and swap CAISO's published
figures for their own. That is the point of the exercise as much as the CSVs are: a
transcribed 46,844 in a feature file is the same material as a transcribed 46,844 in a
committed CSV, and neither is needed to prove that hour ending 18 maps to a 17:00 snapshot.

Both files are required to carry rows. An empty CSV reads back with no column types, and
the appendix roll-up cannot sum a string column, so the builder raises rather than writing
one.

## The staging scenarios build a network instead

The two scenarios that read `pypsa_1_week.nc` build what they need with
`PyPSANetworkBuilder`: a two-bus network holding one of each component class the manifest
asserts on, with a `p_max_pu` series and a `p_set` series.

Two builder additions make that possible.

`add_carrier` adds a `Carrier` component. Naming a carrier on a bus or a generator does
not create one, and a `Carrier` with no attribute set exports only its index coordinate,
so the scenario states `co2_emissions` to make the class stage at all.

`set_pypsa_version` states the version the file records as its writer. PyPSA stamps the
running version on export, so a freshly built file would otherwise agree with the version
reading it, and the scenario would no longer distinguish the two. The value is written
over the exported attribute, on the path that already post-processes the dataset for
forced duplicates.

The feature loses the paragraph explaining why loading a large fixture made it `@slow`,
and gains `@fork_unsafe` — it runs a Polars compute, so the general rule now covers it.

## The lint

`scripts/lint_committed_data.py` fails any tracked file in a data format outside
`interop/templates/`. The allowed directory carries its reason in the source, and a new
one needs the same. It runs in pre-commit with the other lints.

## What this does not do

The container image published to GHCR still bundles the whole runtime dependency closure
with no third-party licence file, and one of those dependencies is under the GPL. That is
a separate piece of work and is deliberately out of scope here.
