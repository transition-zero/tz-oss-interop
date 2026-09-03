# Pipeline composer with mapping pipeline support

Design for issue #181, on chaining a PLEXOS → PyPSA translation into a PyPSA → Sienna one.

## Problem

Translating PLEXOS to Sienna needs no new translator. Both legs exist: PLEXOS → PyPSA and
PyPSA → Sienna. What is missing is composition, running the legs back to back as one named
pipeline with one audit trail. Nothing outside a pipeline YAML can reach into it today, so
one pipeline's output cannot be wired to the next pipeline's input.

A second problem rides along. The PyPSA → Sienna leg needs a user mappings file keyed by
PyPSA carrier, but a PLEXOS user's vocabulary is PLEXOS objects, categories and fuels.
Carriers are an intermediate they never chose. So a composed run needs a setup phase that
derives the per-leg mappings files from one file written in the user's own vocabulary.

## Outcome

`plexos-to-sienna` appears in the same translate menu as every other pipeline, is picked
and run the same way, and produces one decisions report covering both legs. A user cannot
tell the difference unless they open the YAML, where they find an ordered list of existing
pipelines rather than a new translator.

## Composed document shape

A composed pipeline lives in `pipelines/` alongside every other pipeline and is found by
the same catalog scan. Ordinary pipeline YAMLs are unchanged.

```yaml
# interop/pipelines/plexos-to-sienna.yaml
source_framework: plexos
destination_framework: sienna
mappings:
  - pipeline: derive-plexos-sienna-mappings
compose:
  - pipeline: plexos-to-pypsa
  - pipeline: pypsa-to-sienna
    params:
      stage_pypsa_network_file.path: $plexos-to-pypsa.emit_pypsa_network.output_path
```

Every leg runs in full, including its sinks. The final leg's sinks are the composed
pipeline's outputs and the composed file has no sinks of its own.

### Addressing

A node is addressed by its plugin name: `<node>.<param>` to set a value and
`$<pipeline>.<node>.<param>` to read one. Reading and writing use one scheme, so a line
says what it does.

Plugin name rather than `sink[0]`, so reordering a pipeline's sinks cannot silently rewire
a chain. Duplicate plugin names within one pipeline are a load-time error rather than an
arbitrary pick. The index-based form the REPL prompts and the `--override` flag use is
untouched; nobody overrides an interior leg from the command line.

A value is a reference when it starts with `$`. There is no interpolation inside longer
strings.

### No variables block

The refinement had each pipeline declare a flat `variables` block, with a compose entry
setting only those variables so that a leg's inputs were an interface. Dropped: the
interface buys nothing here and costs a second naming layer over the one the prompts and
`--override` already use.

The trade is deliberate. If a leg later swaps its source plugin, a composed file naming
`stage_pypsa_network_file.path` stops matching and the run fails at load, where a variable
named `input_network_path` would have absorbed the change. Failing loudly is preferred:
whoever swaps a leg's source owns the chain too, and a silent rewire is worse than an
error naming the key. No shipped pipeline feeds one value to two params, and if one ever
does, YAML anchors handle it with no code.

## Rules the composer enforces

- The first leg's source framework and the last leg's destination framework match the
  composed file's own.
- Each adjacent pair agrees on the boundary framework. With PyPSA as the hub, every
  boundary in practice is PyPSA.
- Every compose entry after the first holds at least one reference to the immediately
  preceding leg. Without one the chain is not wired and the leg would read whatever its
  own default happened to be.
- No param may be set to a literal equal to a value an earlier leg produces, so a
  relocated output cannot silently break the chain. The error names the reference the
  author should have written.
- A leg may not itself be a composed pipeline.

## User mappings

User mappings are routed by schema type and are never named in a pipeline YAML.
`UserMappingsLoader` reads each node's `__init__` type hints and keeps the parameters
annotated with a `UserMappings` subclass; the DI layer matches the parameter name to the
schema type when it builds the node.

A composed run needs no new key, because each file in play is a different schema: the
user's file is PLEXOS per-object intent, one derived file is per-object carrier
assignments read by a PLEXOS → PyPSA step, the other is `CarrierMappings` read by the
PyPSA → Sienna step. The composer holds a schema-to-path map for the run and asks each leg
the same question the loader already asks a standalone pipeline. Two producers for one
schema is an error rather than a silent pick.

Two consequences for the plumbing:

- A source can now receive mappings, so a mapping pipeline's source declares the schema it
  wants and needs no path param at all.
- A sink that writes a derived mappings file declares the schema it writes.

The run's single "User mappings file?" answer covers whatever schema no mapping pipeline
produces, so a pipeline, composed or not, takes at most one user mappings file from the
user.

This assumes the two derived files are two distinct `UserMappings` subclasses. If the
PLEXOS → PyPSA leg's mapping step reused `CarrierMappings` for per-object assignments,
both files would claim one schema and the routing would need a tiebreak.

## Mapping pipelines

A mapping pipeline is an ordinary pipeline. It lives in `pipelines/mappings/`, excluded
from the translate menu the same way `pipelines/results/` already is, so it never appears
as a translation the user can pick.

For PLEXOS it takes the user's per-object file, mints one carrier name per distinct Sienna
triple, and writes two files: which carrier each object gets, and what each carrier
becomes. The user never types a PyPSA carrier name.

## Interior boundaries

Only the first leg's source and the last leg's sinks use the configured `FilesystemPort`.
Every interior hand-off, and every mapping pipeline sink, goes through `local_filesystem`
and lands in a run-scoped scratch directory removed unless `keep_staging` is set.

This is an invariant of composition, not a deployment binding, and deliberately not
configurable: an interior boundary pointed at signed URLs would break the chain, because
nobody mints a URL for plumbing the user never named. A scratch directory also means
nothing clobbers the project directory and a read-only project directory still works.

Within a composed run the filesystem port is therefore no longer a single global
singleton.

## Prompts

The user is asked only for the first leg's source fields and the last leg's sink fields,
worded exactly as they are for a standalone pipeline. Everything else takes its own
default or a reference. History replay and the `--override` / `INTEROP_OVERRIDE_*`
machinery are unchanged.

## Audit trail

One event log for the whole run, with each event stamped with the pipeline that produced
it as well as the step, so the decisions report reads PLEXOS → PyPSA → Sienna with no
collapsed hops. Validation errors accumulate across legs and the report is re-rendered
after each leg's validators complete, so a later failure still leaves a report on disk.

## Validate

`validate` runs a pipeline's validators without translating anything, and a chained
pipeline's second leg has no input until the first leg has run. So validate runs the first
leg's checks only and says which leg it checked.
