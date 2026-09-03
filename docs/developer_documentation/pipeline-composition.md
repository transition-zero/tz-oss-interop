# Composing pipelines

A composed pipeline runs existing pipelines back to back as one named pipeline with one
audit trail. `plexos-to-sienna` is `plexos-to-pypsa` and `pypsa-to-sienna` chained through
the PyPSA hub rather than a translator of its own.

A composed manifest lives in `pipelines/` beside every other manifest, is found by the same
catalog scan, and is picked and run from the same translate menu.

```yaml
# pipelines/plexos-to-sienna.yaml
source_framework: plexos
destination_framework: sienna
compose:
  - pipeline: plexos-to-pypsa
    params:
      emit_pypsa_network.output_path: network.nc
  - pipeline: pypsa-to-sienna
    params:
      stage_pypsa_network_file.path: $plexos-to-pypsa.emit_pypsa_network.output_path
```

A chain names the file it hands over, on the leg that produces it, and the leg after it
reads that name back by reference. The name is the chain's business rather than the leg's:
a pipeline run on its own never writes it, so its own manifest says nothing about it.

A node is addressed by its plugin name: `<node>.<param>` to set a value, and
`$<pipeline>.<node>.<param>` to read one. Plugin name rather than `sink[0]`, so reordering
a pipeline's sinks cannot silently rewire a chain. Every leg runs in full, including its
sinks, so the final leg's sinks are the composed pipeline's outputs and a composed manifest
has none of its own.

The composer rejects a manifest that is wired implicitly: adjacent legs must agree on the
boundary framework, and each leg after the first must reference the one before it. The
errors say which rule was broken and what to write instead, so they are the reference
rather than a list here.

Two things are worth knowing before reading the code.

## Interior boundaries are always local

Only the first leg's source and the last leg's sinks use the configured `FilesystemPort`,
which a deployment may bind to signed URLs. Every other end of every leg reads or writes
through a `local_filesystem` rooted at a directory inside the run's scratch space, removed
at the end of the run unless `keep_staging` is set.

Each hand-off gets its own directory, named for the leg that produces it, and both ends of
that hand-off are rooted there: the consuming leg reads back the exact relative path the
producing leg wrote. Nothing rewrites a param, so an interior leg's *other* outputs land in
scratch too, not just the one the next leg reads. That is what stops two legs writing the
same relative path from clobbering each other, or the project directory.

This is not configurable, and deliberately so: nobody mints a URL for a hand-off the user
never named, so an interior boundary that reached the configured port would break the
chain. A read-only project directory still works. Within a composed run the filesystem port
is therefore no longer one process-wide singleton.

The run's summary names every file it wrote. The hand-off files are listed apart from the
files written into the project, so `--keep-staging` plus that summary is how you inspect a
hand-off.

## Mapping pipelines route by schema

A leg may need a user mappings file whose vocabulary the user never chose: the
PyPSA → Sienna leg wants carriers, but a PLEXOS user thinks in objects, categories and
fuels. A composed manifest can name mapping pipelines, which run before the legs and derive
the files the legs consume from the one file the user wrote.

```yaml
mappings:
  - pipeline: derive-plexos-sienna-mappings
compose:
  - pipeline: plexos-to-pypsa
  - pipeline: pypsa-to-sienna
    params:
      stage_pypsa_network_file.path: $plexos-to-pypsa.emit_pypsa_network.output_path
```

A mapping pipeline is an ordinary pipeline, living in `pipelines/mappings/` so that it never
appears as a translation a user can pick, the same way `pipelines/results/` already works.

Nothing in the manifest wires the derived files, because user mappings are routed by schema
type and are never named in a pipeline YAML. A sink declares the schema it writes, each leg
already declares the schemas its nodes need, and the run matches the two:

```python
class EmitCarrierMappings(Sink):
    writes_user_mappings: ClassVar[UserMappingsOutput | None] = UserMappingsOutput(
        schema=CarrierMappings, path_param="output_path"
    )
```

A source can consume a mappings file the same way a step or validator does, by declaring a
parameter typed as a `UserMappings` subclass, which is how a mapping pipeline reads the
user's own file without a path param for it.

So the user is asked for one mappings file, once, and only for a schema no mapping pipeline
produces; a derived file wins over the user's own; and two producers of one schema is an
error.
