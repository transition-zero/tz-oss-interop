# interop

interop translates energy-system models from one modelling framework to another. It also solves a translated model and compares the results of two solves.

## Models and frameworks

**Framework**:
A family of modelling tools whose model format interop reads or writes: PyPSA, Sienna, PLEXOS or OSeMOSYS.
_Avoid_: tool, platform

**Model**:
One energy-system description in the format of one framework. Each framework has its own word for a model, given below.
_Avoid_: case, dataset

**Source model**:
The model that a translation reads.
_Avoid_: input model

**Destination model**:
The model that a translation writes.
_Avoid_: output model, target model

**PyPSA network**:
A model in the PyPSA format.
_Avoid_: PyPSA model

**Sienna system**:
A model in the SiennaSchemas format, for an operational problem.
_Avoid_: dispatch system, base system, operations system

**Sienna Investments Portfolio**:
A SiennaSchemas document for a capacity expansion problem. interop writes a Sienna Investments Portfolio but does not read one.
_Avoid_: portfolio (alone), investments portfolio, expansion plan, long-term plan

**PLEXOS model**:
A model in the PLEXOS XML format.

**Hub**:
The framework that each built-in translation goes into or comes out of. Sienna is the hub.
_Avoid_: "PyPSA hub", "hub vocabulary" for the names in a results table

**Component**:
One element of a model, for example a bus, a generator or a line.
_Avoid_: object, element, asset

**Attribute**:
One named value on a component. PLEXOS calls it a property, and SiennaSchemas calls it a field.

**Carrier**:
The name of a component's technology or fuel, for example `coal` or `solar`.
_Avoid_: category (a PLEXOS category is a different thing)

**Candidate component**:
A component that an expansion problem can choose to build.
_Avoid_: candidate (alone), build, build candidate, extendable component, technology

## Time

**Snapshot**:
One modelled time step.
_Avoid_: timestep, timestamp, period

**Snapshot window**:
The span of snapshots that a model covers.
_Avoid_: horizon (PLEXOS uses Horizon for a settings object), window

**Snapshot weight**:
The number of hours that one snapshot stands for.

**Time series**:
The values of one attribute of one component, one value for each snapshot.
_Avoid_: profile, series, trace, shape

## Uncertainty

**Scenario**:
A PLEXOS set of tagged values that replace the base values of a model. A translation reads one scenario.
_Avoid_: overlay, override

**Replication**:
One Monte Carlo draw of a model's uncertain values.
_Avoid_: sample, draw, iteration

**Ensemble**:
A set of models, one for each replication of one source model.
_Avoid_: batch, family

## Pipelines

**Pipeline**:
A named, ordered set of plugins that does one translation, one validation or one results conversion.
_Avoid_: job, workflow, flow

**Pipeline manifest**:
The YAML file that names a pipeline's plugins and their parameters.
_Avoid_: manifest (alone), pipeline config

**Plugin**:
A unit that interop finds and registers by its name. Each plugin is a source, a step, a validator, a sink or an adapter for a port.
_Avoid_: node (except for a plugin's place in a pipeline manifest), module

**Source**:
The plugin that reads a source model into a pipeline.
_Avoid_: reader, loader, input

**Step**:
A plugin that changes the data in a pipeline from the source framework's shape toward the destination framework's shape.
_Avoid_: transform, stage, mapping

**Validator**:
A plugin that inspects a source model and reports problems. A validator changes nothing.
_Avoid_: checker, linter

**Sink**:
A plugin that writes the destination model, or a report, from a pipeline.
_Avoid_: writer, emitter, output

**Port**:
A service that interop needs from outside, for example file access, a solver or a report. A project binds each port to one or more adapters.
_Avoid_: interface, backend, service (alone)

**Adapter**:
A plugin that gives one port its service in one specified way, for example from the local disk or as a Markdown file.
_Avoid_: backend, driver, provider, implementation

**Run**:
One execution of one pipeline.
_Avoid_: invocation, job

**Composed pipeline**:
A pipeline made of other pipelines that run one after the other.
_Avoid_: chain, meta-pipeline

**Leg**:
One pipeline inside a composed pipeline.
_Avoid_: hop, stage, part

**Hand-off**:
The file that one leg writes and the next leg reads.
_Avoid_: handover, intermediate file

**Hop**:
One translation from one framework to the next, in a sequence of translations. A sequence of hops can be one composed pipeline or several separate runs.
_Avoid_: leg (a leg is a hop inside one composed pipeline)

**Mapping pipeline**:
A pipeline that makes a user mappings file for a leg from the file that the user wrote.
_Avoid_: derivation pipeline

**Results pipeline**:
A pipeline that converts a solve or a reference dataset into the results format.

## Translation records

**Translation mapping document**:
The document that states, for one pair of frameworks, how each source attribute becomes a destination attribute. It is the authority for translation design.
_Avoid_: mapping (alone), spec

**User mappings file**:
A YAML file in which a user states the choices that a translation cannot make alone, for example the carrier of a PLEXOS category.
_Avoid_: mapping (alone), carrier mappings file, user config

**Translation event**:
One record of how a translation got one destination value, or why it left a component or an attribute out.
_Avoid_: decision, mapping event, log entry

**Decisions report**:
The report that lists every translation event of a run, component by component.
_Avoid_: decision report, audit log

**Skipped component**:
A source component that a translation leaves out completely.
_Avoid_: dropped component, left-out component

**Translator default**:
A value that the translator writes when the source model states none.
_Avoid_: fallback, assumption

**Sidecar**:
The `extensions.json` file beside a destination model. It holds the attributes that the destination framework has no field for, so that a later hop can use them.
_Avoid_: extensions, companion file, ext, bag; sidecar for the HDF5 companion

**Extension record**:
One entry in a sidecar, for one component.

**Extension kind**:
The concept that an extension record describes, for example a bus or a reserve. A kind names a concept, not one framework's class.

**Extension series**:
A time series that an extension record points to, stored beside the sidecar.
_Avoid_: companion parquet

**HDF5 companion**:
The file that holds the values of a Sienna system's time series.
_Avoid_: HDF5 sidecar, H5 sidecar, external store

**Round trip**:
A translation from one framework to a second and back again.
_Avoid_: opposite translation

**Gap**:
Something that a source model states and that the destination framework has no place for.
_Avoid_: unsupported, known gap (for a place the translator does not fill yet)

**Deferred**:
Something that the destination framework has a place for but that the translator does not write yet.
_Avoid_: out of scope, known gap, DEFER

## Actions

**Translate**:
To convert a source model into a destination model.

**Solve**:
To run an optimisation over a translated Sienna system.

**Compare**:
To put the results of two solves, or of a solve and a reference dataset, side by side.

**Validate**:
To inspect a source model with validators, without translation.

## Results

**Results format**:
The shared table shape that every solve and every reference dataset becomes before a comparison.

**Run manifest**:
The record of where one results table came from.
_Avoid_: manifest (alone)

**Ensemble manifest**:
The record of the replications in an ensemble.
_Avoid_: manifest (alone)

**Reference dataset**:
Published figures that a comparison uses as one side, in place of a solve.
_Avoid_: ground truth, benchmark

**Comparison report**:
The report that a comparison writes.
_Avoid_: summary report, side-by-side report

## Projects

**Project**:
A directory that `interop init` makes. It holds a user's pipeline manifests, plugins, inputs and outputs.
_Avoid_: workspace
