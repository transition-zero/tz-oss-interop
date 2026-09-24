# Sienna becomes the hub for the PLEXOS translations

## The problem

`plexos-to-sienna` does not translate PLEXOS into Sienna. It is a composed pipeline. It runs
`plexos-to-pypsa`, writes a PyPSA netCDF file into scratch, then runs `pypsa-to-sienna` over
that file. PyPSA is the hub, and Sienna is the end of a chain.

Two costs follow from that shape:

- A PLEXOS value that PyPSA has no field for must travel in the `extensions.json` sidecar to
  cross the middle of the journey, even when Sienna has a field for it.
- A PLEXOS user reads `plexos-to-pypsa` and `pypsa_to_sienna_relate_components` in their own
  `decisions.md`. The report describes a journey that the product does not claim to make.

## The design

Two translations change.

1. `plexos-to-sienna` becomes one simple pipeline. A new step,
   `plexos_to_sienna_map_components`, reads the PLEXOS tables that the source stages and
   writes the Sienna tables that the sink needs. It calls no PyPSA code and it builds no
   PyPSA table.
2. `plexos-to-pypsa` becomes a composed pipeline over `plexos-to-sienna` and
   `sienna-to-pypsa`.

Both published pipeline names stay. Only what runs behind each name changes.

`docs/translation_mappings/translation-from-plexos-to-sienna.md` is the specification of the
mapping. The two existing translations are the reference for how a value is derived, and not
code to call.

### The direct manifest

```yaml
source_framework: plexos
destination_framework: sienna
source:
  name: stage_plexos_xml
steps:
  - name: plexos_to_sienna_map_components
  - name: sienna_relate_components
validators:
  - name: plexos_node_reference_integrity
  - name: plexos_generators
  - name: plexos_storage_units
  - name: plexos_loads
  - name: plexos_lines
  - name: plexos_unique_names
sinks:
  - name: emit_sienna_files
```

### The composed manifest

```yaml
source_framework: plexos
destination_framework: pypsa
compose:
  - pipeline: plexos-to-sienna
    params:
      emit_sienna_files.output_system_json_file_path: system.json
      emit_sienna_files.output_h5_file_path: time_series.h5
      emit_sienna_files.output_extensions_file_path: extensions.json
  - pipeline: sienna-to-pypsa
    params:
      stage_sienna_system_json.system_json_path: $plexos-to-sienna.emit_sienna_files.output_system_json_file_path
      stage_sienna_system_json.time_series_h5_path: $plexos-to-sienna.emit_sienna_files.output_h5_file_path
      stage_sienna_system_json.extensions_json_path: $plexos-to-sienna.emit_sienna_files.output_extensions_file_path
```

`sienna-to-pypsa` declares no `UserMappings` parameter, so the chain asks the user for one
file only, and asks in PLEXOS words.

### The parity contract

The direct pipeline writes what the archived chain writes, for the same input. `system.json`,
the HDF5 companion, `extensions.json` and `reserves.parquet` all match, record for record and
field for field. `metadata_uuid` is a `uuid4`, so a comparison normalises that field out.

Row order is part of the contract. `_build_time_series_associations` assigns `id` with
`with_row_index(offset=1)`, so the order in which the step builds the rows fixes every id.

`decisions.md` is not compared. The step names change by design.

### The sub-step names

`plexos_to_sienna_map_components` is one pipeline node that runs seven sub-steps, each in its
own `ScopedRecorder`. The names mirror the PLEXOS to PyPSA set, so a reader who knows one
knows the other:

- `plexos_to_sienna_map_buses`
- `plexos_to_sienna_map_loads`
- `plexos_to_sienna_map_generators`
- `plexos_to_sienna_map_transmission`
- `plexos_to_sienna_map_reserves`
- `plexos_to_sienna_map_storage_units`
- `plexos_to_sienna_map_constraints`

Two whole-network concerns run after them, each under its own name:
`choose_ensemble_samples` and `drop_profiles_off_the_window`.

### The relate step loses its PyPSA name

`pypsa_to_sienna_relate_components` becomes `sienna_relate_components`. The step reads only
Sienna tables off `State.destination_tables` and derives `Area` and `Arc` from them, so it is
already source agnostic. Both `pypsa-to-sienna` and `plexos-to-sienna` name the one step.

**A plugin name is a published key, so this breaks a downstream pipeline that names the old
one.** We take the break rather than carry a deprecated alias. Two registered names for one
class outlive the release that they were meant to smooth.

### The user mappings file reaches the step by schema

`plexos_to_sienna_map_components` declares `plexos_sienna_mappings: PlexosSiennaCarrierMappings`
on `__init__`. `interop/core/user_mappings_loader.py` routes a file by the schema that a node
declares, so the loader asks the user for the file in PLEXOS words. The step reads that file
directly. `derive-plexos-sienna-mappings` plays no part in this pipeline.

The user writes the same file as before, and the schema does not change.

**The step keeps the rule that one name gives one target.** A `fuel` row and a `category` row
of one name must state the same Sienna target, and the run stops when they disagree. The rule
comes from PyPSA, which holds one carrier per name, and the direct step could drop it. It
keeps the rule for two reasons. The archived chain still runs, so one file must mean one thing
under both pipelines. And the parity contract holds this work to matching the chain.

### The archive

`archive/` joins `_UNLISTED_SUBDIRS` in `interop/core/runner.py`. A manifest in such a
directory does not reach the translate menu, and still loads by name.

The two superseded manifests move into `interop/pipelines/archive/` and take new file stems,
because a pipeline resolves by stem across the whole tree:

- the composed `plexos-to-sienna` becomes `plexos-to-sienna-via-pypsa`
- the simple `plexos-to-pypsa` becomes `plexos-to-pypsa-direct`

`plexos-to-sienna-via-pypsa` names `plexos-to-pypsa-direct` as its first leg, and reads
`$plexos-to-pypsa-direct.emit_pypsa_network.output_path` on its second.
`plexos-to-sienna-investments.yaml` names `plexos-to-pypsa-direct` as well, because
`load_leg_spec` rejects a chain that names a chain.

`derive-plexos-sienna-mappings` and its three plugins stay. The archived composed manifest
names the mapping pipeline, and so does `plexos-to-sienna-investments`.

### The sidecar carries what Sienna cannot hold

`sienna-to-pypsa` gains an `emit_extensions_json` sink, so the sidecar reaches the user.
`sienna_to_pypsa_map_components` relays each kind that it does not consume, through
`ExtensionReader.relay(kind)`.

Each PLEXOS value that PyPSA holds today and Sienna has no field for gets three things: a
field on its record in `interop/core/extensions.py`, a write on the PLEXOS to Sienna side and
a read on the Sienna to PyPSA side. A value that changes at each snapshot also gets an entry
in `_COMPANIONS`, which names the parquet file that holds it.

### What this does not buy

A reserve still travels in `extensions.json` after this work.
`interop/plugins/shared/sienna_constants.py` names no Sienna reserve component, so nothing in
the repository builds one, and the direct step must not either. A `Zone` still reaches
nothing. Both belong to transition-zero/tz-infra-interop#228, which stays open.

## The tests come first, and then they freeze

The scenarios that we already have are what prove that the new step matches the old chain. The
branch opens with one commit that touches test files and nothing else. That commit holds every
test change that this work makes. After it, no test file changes again.

One rule separates a change we allow from one we do not.

- **An assertion on a file that the translation writes does not change.** The PyPSA network,
  `system.json`, the HDF5 companion and `extensions.json` are the output.
- **An assertion on `decisions.md` does change.** The report names the pipeline, the step and
  the intermediate field behind each decision, and all three change by design.

### The provenance columns become tokens

A `decisions.md` row ends with the pipeline and the step that recorded it. 29 assertions in
`tests/features/plexos_to_pypsa/` spell both out as literals. A fixture holds the expected
names, and the Gherkin holds a token, so a later rename touches one place.

`$` delimits a token, because `parsers.parse` captures with `{}` and a Gherkin
`Scenario Outline` substitutes with `<>`. A composed run records two legs in one report, so
the fixture holds a name per role:

| Token | Resolves to |
| --- | --- |
| `$source_leg$` | `plexos-to-sienna` |
| `$destination_leg$` | `sienna-to-pypsa` |
| `$source_generator_step$` | `plexos_to_sienna_map_generators` |
| `$source_storage_step$` | `plexos_to_sienna_map_storage_units` |
| `$source_window_step$` | `drop_profiles_off_the_window` |
| `$destination_generator_step$` | `sienna_to_pypsa_map_generators` |
| `$destination_storage_step$` | `sienna_to_pypsa_map_storage_units` |

A new step, `the decisions report contains "..."`, reads the fixture and substitutes each
token before it matches. The token resolves to the expected name, and never to what the run
wrote.

### Every PLEXOS to PyPSA scenario needs a mappings file

`plexos-to-pypsa` needs no user mappings today. Through Sienna its first leg needs a
`PlexosSiennaCarrierMappings` file, and `UserMappingsLoader._load` raises before the pipeline
runs when none is supplied.

The vocabulary of the suite is small and closed: five PLEXOS fuels and eight categories. One
table of thirteen rows covers all 178 scenarios. An autouse fixture in
`tests/step_defs/plexos_to_pypsa/conftest.py` writes that table, so no `.feature` file changes
for it. That keeps the 2750 lines of the suite unchanged, which is what makes a passing suite
parity evidence that nobody can call adjusted.

Each row states the Sienna type that preserves the scenario's intent. A generator that states
a minimum, a ramp limit, a start cost or a commitment needs `ThermalStandard`, because
`RenewableDispatch` has no `active_power_limits` and would lose the minimum. Solar and wind
take `RenewableDispatch`.

## Risks

- The new step is the largest part of this work.
  `interop/plugins/shared/pypsa_sienna_translations/` is about 4900 lines for one hop, and a
  PLEXOS to Sienna mapping is comparable.
- The PLEXOS validators are new code with no counterpart to check against. The PyPSA set is
  the shape to follow, and not a translation source.
- A `decisions.md` assertion that nobody can rewrite is evidence. It names a derivation that
  the new journey lost. It goes on the carried list, or into
  transition-zero/tz-infra-interop#228. Nobody deletes it to make the suite green.
