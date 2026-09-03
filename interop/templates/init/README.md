# Interop project

Pipelines live in `pipelines/`, project-local plugins in `plugins/<category>/`,
framework adapter overrides in `adapters.yaml`.

## Run

Launch `interop` in this directory and pick `translate`; choose the
source / destination frameworks and the pipeline when prompted.

## Extend

Drop a new step / source / sink / adapter class under the matching
`plugins/<category>/` directory and reference it by `name` from a
pipeline YAML. See `docs/developer_documentation/extending.md` in the interop repository.
