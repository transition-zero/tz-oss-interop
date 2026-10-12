# An OSeMOSYS to Sienna pipeline, and a scaffolded OSeMOSYS example

## The problem

A user can stage an OSeMOSYS model into the canonical stage, but no pipeline goes from an
OSeMOSYS model to Sienna. Later pull requests add the translation steps one at a time. Each
of them needs a pipeline that already runs from end to end.

The OSeMOSYS mappings tutorial also tells the reader to type each file of its toy model.
`interop init` can scaffold a PyPSA example, but it has no OSeMOSYS example.

## The design

### The pipeline

A new built-in pipeline, `interop/pipelines/osemosys-csv-to-sienna.yaml`, reads an otoole
model with the real source `stage_osemosys_csv`. It has no steps. Its sink,
`emit_sienna_files`, writes a Sienna system with no components, with its two companion files.
Later pull requests add steps to this file.

```yaml
source_framework: osemosys
destination_framework: sienna
source:
  name: stage_osemosys_csv
  params:
    config_path: inputs/model/config.yaml
    csv_dir: inputs/model/csv
sinks:
  - name: emit_sienna_files
    params:
      output_system_json_file_path: outputs/system.json
```

### The default paths

The pipeline `osemosys-csv-to-canonical` gets the same source paths, and the output directory
`outputs/canonical`. A run of the scaffolded example then needs no `--override`. An
`--override` still replaces each default. `pypsa-to-sienna` already gives a default path in the
same way.

### The scaffolded example

`Example` gets the member `OSEMOSYS = "osemosys"`, so the `init` menu offers it. The template
`interop/templates/examples/osemosys/` holds:

- the toy otoole model of the tutorial, in `inputs/model/`. Each value is invented.
- `inputs/osemosys_mappings.yaml`, with `osemosys: {}`.

The template holds no pipeline. A package pipeline wins over a project pipeline with the same
name, so a copy in the project never loads. `init` removes the placeholder
`pipelines/example.yaml`, as it does for the PyPSA example.

### The tests

- `interop_init.feature` checks that `init` writes the files of the example.
- A new feature scaffolds the example and runs both pipelines on it. It checks that the Sienna
  system has no components, that `decisions.md` records the automatic match, and that the
  canonical table `capital_cost` has its two rows.

### The tutorial

The tutorial scaffolds the example in place of the steps that make each file. It still shows
each file of the model. Its run command uses the default paths. It does not name
`osemosys-csv-to-sienna`.
