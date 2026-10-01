# A Sienna ensemble reads back, so the hub holds a Monte Carlo run

Follows `2026-09-24-direct-plexos-to-sienna-investments-design.md`, which took the last
live pipeline off `interop/pipelines/archive/`.

## The problem

`plexos-to-pypsa` is a chain through Sienna. `plexos-to-pypsa-monte-carlo` is not: it maps
PLEXOS straight into PyPSA, because nothing can read a Sienna ensemble back.

Two things are missing, and one of them is in a sink:

- **`emit_sienna_files_ensemble` writes no manifest.** It writes one subdirectory per
  replication and stops. `FilesystemPort` cannot list a directory, and one of its adapters
  serves files over HTTP where no listing exists, so a reader has no way to learn which
  replications an ensemble holds. `emit_pypsa_network_ensemble` writes `ensemble.json` for
  exactly this reason.
- **No source reads a directory of Sienna systems.** `stage_sienna_system_json` reads one
  system.

So Sienna is the hub for a single system and a dead end for an ensemble.

## The design

### The ensemble manifest belongs to neither framework

`interop/plugins/shared/pypsa_ensemble_manifest.py` states what an ensemble directory says
about itself. Nothing in it is PyPSA. It becomes
`interop/plugins/shared/ensemble_manifest.py`, and both ensemble sinks write one.

`EnsembleReplication.filename` stays relative to the directory holding the manifest. A
PyPSA replication names one file, `0.nc`. A Sienna replication names the system file inside
its own directory, `0/system.json`, and its two companions sit beside that file under the
names a single-system translation gives them.

### `emit_sienna_files_ensemble` writes the manifest

One more file, written after the replications, naming each one and the system file it
holds.

### `stage_sienna_system_json_ensemble` reads it back

A new source, shaped like `stage_pypsa_network_ensemble`:

- Read the manifest, and raise where it is absent or names no replication.
- Stage each replication's system JSON and HDF5 companion into a directory of its own.
- Take the topology from the first replication, because every replication of an ensemble
  holds the same components.
- Tag each replication's time series with its label in a `sample` column, and concatenate,
  so every mapping step downstream stays sample-agnostic.
- Read the sidecar of the first replication, which every replication repeats.

A Sienna ensemble needs none of the narrowing `stage_pypsa_network_ensemble` does. PyPSA
leaves a component out of a series where its values never move, so a profile can reach some
replications and not others. Every replication of a Sienna ensemble carries the same
`TimeSeriesAssociation` rows, because the sink builds the document once and writes it many
times.

### `sienna-to-pypsa-ensemble` is the pipeline that uses it

```yaml
source_framework: sienna
destination_framework: pypsa
source:
  name: stage_sienna_system_json_ensemble
steps:
  - name: sienna_to_pypsa_map_components
sinks:
  - name: emit_pypsa_network_ensemble
    params:
      output_dir: outputs/ensemble
  - name: emit_extensions_json
    params:
      output_path: outputs/extensions.json
```

The step is the one `sienna-to-pypsa` already runs. It reads the staged tables and writes
reverse time-series metadata; the sink reads a sample at a time, as it already does for a
PyPSA ensemble.

## What this does not do

`plexos-to-pypsa-monte-carlo` stays as it is. Making it a chain needs
`plexos-to-sienna-monte-carlo` to go direct first, and the reliability pair needs a
`sienna_add_load_shedding` step that no one has written. Both follow this change and
neither belongs in it.

## The tests come first, and then they freeze

A source with no pipeline behind it has no user surface, so the reader and its pipeline land
together, and one scenario drives both.

`tests/features/pypsa_to_sienna_to_pypsa.feature` already takes a PyPSA network out to
Sienna and back through a project-local pipeline the test writes. An ensemble round trip
states the same thing for many replications:

- A new feature file writes a project-local pipeline chaining `pypsa-to-sienna-ensemble`
  and `sienna-to-pypsa-ensemble`.
- It asserts the ensemble that comes back holds the same replications, and that a profile
  differing between two replications still differs after the round trip.

No existing scenario changes. The manifest the Sienna ensemble sink now writes is one more
file in a directory no scenario counts.
