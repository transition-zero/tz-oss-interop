# A PLEXOS user writes the carrier mappings in PLEXOS words

## The problem

`plexos-to-sienna` runs two legs: `plexos-to-pypsa`, then `pypsa-to-sienna`. The second leg
needs a user mappings file, because it must give each generator a Sienna fuel type and a
Sienna prime mover type, and both are closed lists in SiennaSchemas. The translator cannot
guess either one.

That file names PyPSA carriers today. It looks like this:

```yaml
carriers:
  - pypsa_carrier: CCGT
    sienna_component_type: ThermalStandard
    sienna_fuel_type: NATURAL_GAS
    sienna_prime_mover_type: CC
```

A PLEXOS user has no PyPSA words. Their model holds `Fuel` objects and generator categories.
They know their own model, and they know Sienna, but the intermediate vocabulary is an
accident of how this chain is built. Asking for it leaks the hub into the user's work.

There is a second problem. Leg two raises `UnmappedCarriersError` when it meets one carrier
that the file does not name, and the whole run stops before it writes anything. A carrier is
the name of a `Fuel` in the source model, so this is a translation that a model's data stops.
The rule in `CLAUDE.md` says that never happens.

## The design

### One mappings file, in PLEXOS words

The user writes a `PlexosSiennaCarrierMappings` file. It has one `carriers:` list. Each row
says which PLEXOS concept its string comes from, because a `Fuel` named `Solar` and a
category named `Solar` are two different things:

```yaml
carriers:
  - plexos_concept: fuel
    plexos_name: Natural Gas
    sienna_component_type: ThermalStandard
    sienna_fuel_type: NATURAL_GAS
    sienna_prime_mover_type: CC
  - plexos_concept: category
    plexos_name: Solar
    sienna_component_type: RenewableDispatch
    sienna_prime_mover_type: PVe
```

The right side of a row is the same as the right side of a `CarrierMappings` row. Only the
left side changes. A `ThermalStandard` row carries a fuel type and a prime mover type, and
every other row carries a prime mover type only, so the row is a discriminated union on
`sienna_component_type` exactly as `CarrierMappings` already is.

### A mapping pipeline derives the file leg two reads

`docs/developer_documentation/pipeline-composition.md` already describes how a composed
pipeline derives a mappings file that one of its legs consumes. Nothing in this design
extends the composer. It writes the first mapping pipeline that uses the mechanism.

```yaml
# pipelines/plexos-to-sienna.yaml
mappings:
  - pipeline: derive-plexos-sienna-mappings
compose:
  - pipeline: plexos-to-pypsa
    params:
      emit_pypsa_network.output_path: network.nc
  - pipeline: pypsa-to-sienna
    params:
      stage_pypsa_network_file.path: $plexos-to-pypsa.emit_pypsa_network.output_path
```

The mapping pipeline is an ordinary pipeline in `pipelines/mappings/`, so the translate menu
never lists it:

| Node | What it does |
| --- | --- |
| `stage_plexos_sienna_mappings` | Declares a constructor parameter typed `PlexosSiennaCarrierMappings`, which is how the loader knows to ask the user for that file. Stages the rows as one table. |
| `plexos_sienna_mappings_to_carriers` | Derives one `CarrierMappings` row from each staged row, and emits one translation event for each. |
| `emit_carrier_mappings` | Writes the YAML. Declares `writes_user_mappings = UserMappingsOutput(schema=CarrierMappings, path_param="output_path")`, which is what routes the file to leg two. |

The derivation is a rename of the left side. `plexos-to-pypsa` gives a generator the name of
its `Fuel` when it burns one, and its PLEXOS category when it does not
(`interop/plugins/shared/plexos_pypsa_translations/_generator_derivation.py`). So a `fuel`
row and a `category` row both give `pypsa_carrier = plexos_name`.

The user is asked for one file, once. Nothing in a manifest names either file, because a
mappings file is routed by its schema.

### The four carriers that no PLEXOS string names

`plexos-to-pypsa` writes a fixed carrier for four kinds of unit. The words are the
translator's, and they appear nowhere in the source model:

| PLEXOS unit | Carrier | Sienna component type | Prime mover |
| --- | --- | --- | --- |
| Reservoir hydro | `hydro` | `HydroDispatch` | `HY` |
| Run-of-river | `ror` | `RenewableDispatch` | `HY` |
| Pumped storage | `PHS` | `EnergyReservoirStorage` | `PS` |
| A `Battery` object | `battery` | `EnergyReservoirStorage` | `BA` |

The derive pipeline supplies all four rows itself, so the user's file holds fuels and
categories only. A user who wants a different Sienna type for one of them writes a row with
`plexos_concept: storage_kind` and one of the four names as `plexos_name`. That row replaces
the default.

### An unmapped carrier skips its component

`_validate_and_skip` in `interop/plugins/steps/pypsa_to_sienna_map_components.py` stops
raising. A carrier that the mappings file does not name joins the carriers that map to a
component type the table does not translate: each component with that carrier is left out
with a `COMPONENT_SKIPPED` event, and the log warns once per carrier, naming three components
and counting the rest. `UnmappedCarriersError` is deleted.

The run then always completes, and `decisions.md` names every component that it left out.

The cost is that a user who forgets one row gets a system with a fleet missing, and only the
report says so. The report is the answer to that, and it is the answer this project already
gives everywhere else.

## What this does not do

- It does not change the composer. `LegKind.MAPPING`, the `mappings:` key, the
  `mappings` subdirectory and `Sink.writes_user_mappings` all exist.
- It does not give the PyPSA to Sienna leg a second mappings vocabulary. That leg still reads
  `CarrierMappings`, and a PyPSA user still writes that file by hand.
- It does not derive a mappings file for any other chain. `derive-plexos-sienna-mappings` is
  one pipeline, and a second chain that needs one writes its own.
- It does not guess a Sienna fuel type from a PLEXOS fuel name. Nothing reads the string.
