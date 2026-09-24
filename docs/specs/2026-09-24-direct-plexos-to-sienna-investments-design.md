# plexos-to-sienna-investments becomes a direct pipeline

Follows `2026-09-23-sienna-hub-for-plexos-design.md`, which made `plexos-to-sienna` direct
and moved the two manifests it replaced into `interop/pipelines/archive/`.

## The problem

`plexos-to-sienna-investments` is a composed pipeline. It runs `plexos-to-pypsa-direct`,
writes a PyPSA netCDF file into scratch, then runs `pypsa-to-sienna-investments` over that
file.

Two costs follow from that shape:

- `plexos-to-pypsa-direct` lives in `interop/pipelines/archive/`. A manifest in that
  directory is superseded work, and a pipeline on the translate menu depends on it.
- A PLEXOS expansion value crosses PyPSA on the way, so the portfolio holds what a PyPSA
  column can carry and nothing more.

## The design

`plexos-to-sienna-investments` becomes a simple pipeline.

```yaml
source_framework: plexos
destination_framework: sienna
source:
  name: stage_plexos_xml
steps:
  - name: plexos_to_sienna_map_components
  - name: sienna_relate_components
  - name: sienna_investments_map_technologies
validators:
  - name: plexos_node_reference_integrity
  - name: plexos_generators
  - name: plexos_storage_units
  - name: plexos_loads
  - name: plexos_lines
  - name: plexos_unique_names
sinks:
  - name: emit_sienna_files
    params:
      output_system_json_file_path: outputs/system.json
  - name: emit_sienna_portfolio
    params:
      output_path: outputs/portfolio.json
```

The first two steps and the six validators are the ones `plexos-to-sienna.yaml` already
names. The `mappings:` block goes: `derive-plexos-sienna-mappings` writes a PyPSA carrier
mappings file for a second leg, and there is no second leg. The user mappings file reaches
the step through the Dishka container, as it does in `plexos-to-sienna`.

### The new step reads Sienna, not PLEXOS

`plexos_to_sienna_map_components` already writes every value a technology needs. Nothing in
the portfolio comes from a PLEXOS table that the operations step did not already read.

| What a `SupplyTechnology` states | Where the operations step already put it |
| --- | --- |
| `power_systems_type` | the Sienna type of the component row |
| `prime_mover_type` | `prime_mover_type` on the component row |
| `region` | the `Area` the component's bus belongs to |
| `capacity_limits.max` | `p_nom_max` on the sidecar record |
| `capital_costs.capital_cost` | `overnight_cost_per_mw` on the sidecar record |
| `operation_costs.fixed` | `fom_charge_per_mw_year` on the sidecar record |
| `unit_size` | `unit_size_mw` on the sidecar record |
| `lifetime` | `technical_life_years` on the sidecar record |
| `financial_data.capital_recovery_period` | `lifetime_years` on the sidecar record |
| `financial_data.return_on_equity` | `discount_rate` on the sidecar record |

So the step reads `State.destination_tables` and `State.destination_extensions`, and it
reads no source table at all. It takes the name `sienna_investments_map_technologies`,
which names what it reads rather than the pipeline that runs it. `sienna_relate_components`
takes its name the same way.

`pypsa_to_sienna_investments_map_technologies` stays as it is. It reads the staged PyPSA
tables, and `pypsa-to-sienna-investments` keeps running it.

### A candidate is a technology, not a plant

A generator stating `Units` of 0 and `Max Units Built` above zero is capacity a plan may
build. The base system holds the fleet that already runs, so the base system must not hold
it.

The two hops disagree today, and each is right for the journey it makes:

- `pypsa_to_sienna_map_components` leaves an unbuilt candidate out, through
  `unbuilt_candidate_skip`. It never reaches a Sienna table.
- `plexos_to_sienna_map_components` writes one as a component, because
  `plexos-to-pypsa` rebuilds the extendable PyPSA generator from it on the second leg.
  A frozen scenario in `tests/features/plexos_to_pypsa/generators.feature` states this.

So `sienna_investments_map_technologies` takes the row out. It reads each unbuilt candidate
off the Sienna table, writes the technology, then drops the row from
`State.destination_tables` and records one event against it. The sink then writes a base
system holding the fleet alone.

An unbuilt candidate is one whose sidecar record states `p_nom_extendable` and whose
component holds no capacity it already runs.

### Carbon caps need no new reader

`interop/plugins/shared/pypsa_sienna_investments_translations/_carbon_caps.py` reads
`ConstraintExtension` records, which are framework-neutral. Two values bind it to PyPSA:

- `investments_skip_report` states `framework=Framework.PYPSA`.
- `_source` states `pypsa_source_field`.

Both become arguments, so one module serves both pipelines. `_demand.py`, `_supply.py`,
`_storage.py` and `_existing.py` read PyPSA tables, so the new step states its own
derivations for those four.

### What this does not buy

One step still cannot serve both pipelines. `sienna_investments_map_technologies` finds a
candidate on a Sienna table, and `pypsa_to_sienna_map_components` drops the candidate
before a Sienna table exists. Making the two converge means the PyPSA operations step stops
dropping it, which changes what `pypsa-to-sienna` writes. That is its own change.

### What the archive stops holding

After this change no manifest outside `interop/pipelines/archive/` names
`plexos-to-pypsa-direct`. Only `archive/plexos-to-sienna-via-pypsa.yaml` does, and both sit
in the archive together.

## The tests come first, and then they freeze

This is a refactor. Every assertion on a file the translation writes stays as it is:
`outputs/portfolio.json` and `outputs/system.json` keep every value.

Three things change in `tests/features/plexos_to_sienna_investments.feature`:

1. **The narrative.** It states the pipeline is a chain over `plexos-to-pypsa-direct` and
   `pypsa-to-sienna-investments`, and that a value crosses the hub in the sidecar. Neither
   holds after the change.
2. **One `decisions.md` row.** The source of a carbon cap reads `pypsa.constraint.GasCap`.
   The record comes from this run's own Sienna hop, so it becomes
   `sienna.constraint.GasCap`.
3. **The `When` step says "chain".** It becomes `I run plexos-to-sienna-investments
   against "..." writing "..."`.

One assertion is added. Scenario 1 already states the base system holds no
`RenewableDispatch`. It gains a `decisions.md` row saying why, because a component that
leaves the base system without a recorded reason is a silent drop.

The log assertion in scenario 5 needs no edit. It matches a substring that states no
framework.
