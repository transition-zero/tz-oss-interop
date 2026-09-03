# Translation from PyPSA to Sienna

## What changed in this revision (retargeted to SiennaSchemas)

**This revision retargets the document from the PowerSystems.jl `to_json` serialisation to SiennaSchemas as the output format.** The previous version's worked examples and "struct (from schema)" references actually built a PowerSystems.jl `System` — UUID identities, `__metadata__`/`internal` envelopes, `{"value": "<uuid>"}` references, deeply nested cost objects re-tagged with `__metadata__`, and an HDF5 sidecar whose associations live in an embedded SQLite store. Serialising that produces the PowerSystems.jl shape, **not** SiennaSchemas. Every example, reference, and mapping is now SiennaSchemas JSON.

Concretely, versus `main` (≈280 insertions / 294 deletions):

- **Target format (new section).** Each component is a flat SiennaSchemas JSON object: integer `id`, integer references, **no** `__metadata__`/`internal`/`ext` envelope, nested values as plain typed objects. Stated explicitly that this is *not* PowerSystems.jl `to_json` and that you must not build a `System` and serialise it. All Julia was converted to SiennaSchemas JSON or removed — the document now contains no Julia.
- **System container (newly defined).** The previously-undefined whole-system packaging is now a JSON object mapping each Sienna type to a list of its objects (`{ "ACBus": [...], "ThermalStandard": [...] }`); identity is `(type, id)`, which is how every reference resolves.
- **Time series.** Replaced the `SingleTimeSeries`/`add_time_series!` framing with SiennaSchemas `TimeSeriesAssociation` records (integer `owner_id`); value arrays are **retained in HDF5** keyed by `time_series_uuid` (the schema's named external store). Standardised on the **per-unit shape + `scaling_factor_multiplier`** convention.
- **Component extensions.** PyPSA fields with no SiennaSchemas home now go in a separate `extensions.json` sidecar, a document keyed by kind whose records are identified by `name`, replacing the PowerSystems.jl `ext` dict.
- **References & ordering.** `get_component(...)` / "added to the `System`" became integer-`id` references with an id-assignment ordering (the lists themselves are unordered).
- **Investments boundary.** Added that SiennaSchemas' `Investments/` namespace is a separate, parallel model (the home for capacity expansion); v1 targets **Operations** (PowerSimulations.jl), with the rationale and the open question of whether expansion interoperability is intended.

---

> **Scope (v1):** This page covers electricity-only networks. All buses are assumed to have `carrier = "AC"` or `"DC"` (HVDC). Multi-carrier and non-electricity content is preserved in the Deferred section at the bottom of this page.
>

---

## Target format

**The translation target is SiennaSchemas-conformant JSON, not PowerSystems.jl's expected input format.** Each translated component is emitted as a flat JSON object matching its schema under `SiennaSchemas/` (see the table in Schema Ground Truth), and nothing more:

- **Integer identity.** Every component carries an integer `id`. There is no UUID identity.
- **References are integers.** A cross-reference (`bus`, `area`, `arc`, a time series' `owner_id`) is the integer `id` of the referenced component, never a `{"value": "<uuid>"}` object.
- **No serialisation envelope.** There is no `__metadata__`, `internal`, `ext`, `units_info`, or `services`. A component's type is given by which schema (or collection) it belongs to, not a `__metadata__.type` tag.
- **Nested values are plain typed objects.** Limits (`{"min", "max"}`), costs (`ThermalGenerationCost` and its curves), and efficiencies follow their SiennaSchemas definitions directly, with no per-level `__metadata__`.
- **Time series** are `Core/TimeSeries/TimeSeriesAssociation.json` records — integer `owner_id`, `time_series_uuid`, `name`, `resolution`, `initial_timestamp`, `scaling_factor_multiplier`. The value arrays live in an external store keyed by `time_series_uuid`.

This is deliberately **not** the PowerSystems.jl `to_json` serialisation. Do **not** build a PowerSystems.jl `System` and serialise it: that produces UUID identities, `__metadata__`/`internal` envelopes, `{"value": "<uuid>"}` references, deeply nested cost objects each re-tagged with `__metadata__`, and an HDF5 sidecar with a SQLite association store — none of which is SiennaSchemas. The worked examples below show the SiennaSchemas JSON object to emit, not Julia construction.

### Time series

A time series has two parts, and SiennaSchemas pins down only the first:

- **Association (JSON, SiennaSchemas-defined).** One `TimeSeriesAssociation` record per (component, series): `owner_id` (the owning component's integer `id`) and `owner_type`, `time_series_uuid`, `name`, `resolution` (ISO 8601, e.g. `PT1H`), `initial_timestamp`, `length`, `time_series_type` (e.g. `SingleTimeSeries`), and optional `scaling_factor_multiplier` / `units`.
- **Value array (not defined by SiennaSchemas).** Referenced by `time_series_uuid`. The schema's own field description says it "may reference inline data or an external store (e.g., HDF5)." **We use HDF5**, keyed by `time_series_uuid`.

**Store per-unit shapes, not absolute values.** The array is a per-unit profile (typically `[0, 1]`); `scaling_factor_multiplier` is a getter on the component (e.g. `"PowerSystems.get_max_active_power"`) that Sienna multiplies the profile by at read time. Keep the magnitude in the static field (`max_active_power`, `rating`, …) and the shape in the series. PyPSA renewable `p_max_pu` is already per-unit (store as-is); for loads, normalise `p_set` by its peak. A `null` multiplier (absolute values) is valid PowerSystems.jl but non-canonical and not used here.

So HDF5 is retained — it is the external store SiennaSchemas explicitly anticipates. Relative to a PowerSystems.jl `System`, **only the association layer changes**: out of the SQLite table embedded inside the `.h5` (keyed by the component's UUID) and into JSON `TimeSeriesAssociation` records keyed by the integer `owner_id`. The HDF5 value arrays (`/time_series/<uuid>/data`) are unchanged.

### Component extensions

SiennaSchemas components have **no free-form `ext` field**, so PyPSA attributes with no SiennaSchemas home are carried in a **separate companion file** (`extensions.json`), in our own format. The SiennaSchemas system is complete without it; a SiennaSchemas-only consumer ignores it.

The document is keyed by **kind**, and the key fixes every attribute's type. A kind names a concept rather than a framework's class, so a `ThermalStandard`, a `RenewableDispatch` and a `HydroDispatch` all land under `generator`. Every record is identified by `name`, one type across every framework, so the hop that reads a record matches it to a component without knowing which framework wrote it. Pydantic models in `interop/core/extensions.py` are the schema; a field only one framework carries is absent from the others' records.

```json
{
  "bus": [ { "name": "bus_1", "carrier": "AC" } ],
  "load": [ { "name": "load_1", "carrier": "", "type": "", "sign": -1 } ],
  "generator": [ { "name": "coal_1", "carrier": "coal", "committable": true } ],
  "line": [ { "name": "line_1", "length": 120.0, "num_parallel": 2.0 } ],
  "reserve": [
    { "name": "Spin", "requirement_mw": 480.0, "contributing_generators": ["coal_1"],
      "direction": "up", "kind": "unknown", "is_mutually_exclusive": true }
  ]
}
```

- **Optional and additive.** A component with no extras has no record; an absent key means "not carried."
- **Free-form values** (`object`) — the point is to hold whatever has no SiennaSchemas field.
- **Ownership rule:** the kind and the record's `name` identify the component the field *belongs to*. A load's `carrier` goes on the load record; a bus's `carrier` goes on the bus record. Cross-component fields are never stored on another component's record.
- **What goes here:** PyPSA fields with no SiennaSchemas equivalent. Two buckets:
  - *Physical / topology:* `length_km`, `num_parallel`, `terrain_factor`, line `type`, `sub_network`.
  - *Round-trip / provenance:* `carrier` (per-component), `sign`, `type` for loads; `committable` for thermals; `p_nom_extendable` for generators and storage (the boolean flag only, as a round-trip crumb); `pypsa_name`, the `has_time_varying_*` flags for other types.
- **What does NOT go here:** capacity-expansion *economics* (`p_nom_min`/`p_nom_max`/`p_nom_opt`, `capital_cost`, `marginal_cost`, `build_year`, `lifetime`). Those have real homes in the SiennaSchemas `Investments/` schemas and are handled there (or deferred) — not in this generic bag. The `p_nom_extendable` boolean is the one exception: it carries no economics, has no Operations-component home, and is kept here purely so a PyPSA → Sienna → PyPSA round-trip preserves the flag.

### Relationship to SiennaSchemas Investments

This document targets the SiennaSchemas **Operations** namespace (the dispatchable system PowerSimulations.jl runs). SiennaSchemas also has a top-level **`Investments/`** namespace, backing PowerSystemsInvestments.jl — and it is a **separate, parallel data model, not an extension of Operations**:

- Its spatial unit is a `Node`/`Zone` (region), not an `ACBus`.
- Its components are buildable *technologies* (`SupplyTechnology`, `StorageTechnology`, `NodalACTransportTechnology`, `NodalHVDCTransportTechnology`, `DemandRequirement`) carrying `capital_costs`, `operation_costs`, `capacity_limits`, `lifetime`, and `financial_data` — not operational instances like `ThermalStandard`.
- It adds policy `Requirements` (`CarbonCaps`, `CarbonTax`, `CapacityReserveMargin`, `EnergyShareRequirements`, …) and `Financials`.
- It bridges to Operations through each technology's `power_systems_type` (the Operations type it realises into) and `TopologyMapping` (region → buses).

**Implication for this translation.** PyPSA's capacity-expansion fields (`p_nom_extendable`, `capital_cost`, `p_nom_min`/`p_nom_max`, `build_year`, `lifetime`) belong to **Investments**, which is a separate translation target (PyPSA expansion → SiennaSchemas Investments), not extra fields on an Operations component. It is **out of scope for v1**. For v1 we translate the **solved** fleet: take `p_nom_opt` (post-solve capacities) as fixed Operations capacity and drop the expansion parameters (or keep round-trip crumbs in the `ext` sidecar). A genuine expansion problem is the future Investments path.

Throughout this document, **`effective_p_nom`** denotes `p_nom_opt` when `p_nom_extendable` is `True`, and `p_nom` otherwise. All capacity-derived fields — `base_power`, `active_power`, `active_power_limits`, `ramp_limits`, and the hydro energy budget scaling factor — use `effective_p_nom`. For a non-extendable component `effective_p_nom = p_nom`; for an extendable component in a solved network `effective_p_nom = p_nom_opt > 0`. An extendable component in an *unsolved* network has `p_nom = p_nom_opt = 0`, so `effective_p_nom = 0` — such a component has no meaningful capacity to translate and lies outside the v1 scope.

**Why Operations and not Investments.** This is a deliberate scope choice tied to the deliverable, not a claim that Operations is the more natural fit:

- **The deliverable targets PowerSimulations.jl** — the *operations* solver (dispatch, UC, PCM). The Investments schemas are consumed by PowerSystemsInvestments.jl, a separate and newer solver that is not the funded target. The acceptance test ("it runs in PowerSimulations.jl") pins us to Operations.
- **Maturity.** Operations + PowerSimulations.jl is the mature, well-exercised path; the `Investments/` schemas and PowerSystemsInvestments.jl are newer.
- **Investments is a larger, separate translation** with its own open mappings: aggregating PyPSA buses into `Node`/`Zone` regions, reconciling PyPSA's (often pre-annuitised) `capital_cost` with `discount_rate`/`capital_recovery_period`/`interest_rate`, and mapping PyPSA `GlobalConstraints` (e.g. CO₂ limits) to `Requirements` (`CarbonCaps`/`CarbonTax`).
- **Counterpoint (kept honest):** a PyPSA-Eur network *is* natively a capacity-expansion model, so Investments is the faithful target if the goal is **expansion interoperability** rather than **dispatching a solved system**. If that is the intent, the target flips to Investments. Confirm the deliverable's intent (dispatch-in-PowerSimulations vs expansion-in-Sienna) before assuming Operations is sufficient.

### System container

SiennaSchemas defines per-component schemas but not how a whole system is packaged, so we define the container: a **JSON object mapping each Sienna type name to a list of that type's component objects**.

```json
{
  "ACBus": [ { "id": 1, "name": "bus_1", ... } ],
  "PowerLoad": [ { "id": 1, "name": "load_1", ... } ],
  "ThermalStandard": [ { "id": 1, "name": "ccgt_1", ... } ],
  "Line": [ { "id": 1, ... } ]
}
```

The type is implied by the key, so the objects stay **pure SiennaSchemas** — no `type`/`__metadata__` discriminator on the objects themselves. Identity is `(type, id)`: `id` is unique within its type's list, and a reference resolves by looking up the type's array and matching `id`. This is how every cross-reference within the system document resolves — a bus's integer `bus`/`area`, and a `TimeSeriesAssociation`'s `owner_type`/`owner_id`. The extensions sidecar is the exception: it keys by `name`, because the frameworks either side of a hop share names and not integer ids.

`TimeSeriesAssociation` records sit alongside the components (a sibling key, e.g. `"TimeSeriesAssociation": [ ... ]`); the extensions document and the HDF5 value arrays are separate companion files.

**A value that varies over the horizon travels in a companion parquet** beside the sidecar, named for what it holds (`reserves.parquet`) and restated in the terms of the field that references it, so a consumer never has to know what the source framework called it.

**The sidecar is an optional input to every source.** Only this translator writes one, so a SiennaSchemas system from a partner is `system.json` plus its HDF5 companion and nothing more, and it stages with no sidecar at all. A staged record that no mapping in the hop consumes is dropped and reported, not relayed into the next sidecar: a concept survives a chain exactly as far as the frameworks along it understand it.

> **Open question: companion file references.** The reader takes each companion as an explicit path: `system_json_path` (the system document), `time_series_h5_path` (the HDF5 value store), and the optional `extensions_json_path`. The writer embeds pointer keys in the document (`time_series_storage_filename` and `extensions_filename`), but the reader does not consult them. Whether embedded pointer keys, a naming convention, or something NLR specifies is the agreed mechanism is still to be confirmed with NLR.

> **Open question — HDF5 layout.** SiennaSchemas does not define the internal HDF5 layout for the value arrays (only that `time_series_uuid` points at an external store). The layout is still to be agreed with NLR; we reuse `/time_series/<uuid>/data` for now.

---

## Schema Ground Truth

**SiennaSchemas is the authoritative reference for all Sienna-side field names, types, required/optional status, and enum values.** Any drift between this document and the schema should be resolved in favour of the schema. This document is regenerated against the schema periodically.

- **Repository:** `SiennaSchemas/` (cloned alongside this repo)
- **Commit targeted:** `906001306e9d3063a8820e84fd2ca7f955bf455e`

| Sienna type | Schema file |
| --- | --- |
| `ThermalStandard` | `Operations/StaticInjection/ThermalStandard.json` |
| `RenewableDispatch` | `Operations/StaticInjection/RenewableDispatch.json` |
| `RenewableNonDispatch` | `Operations/StaticInjection/RenewableNonDispatch.json` |
| `HydroDispatch` | `Operations/StaticInjection/HydroDispatch.json` |
| `HydroTurbine` | `Operations/StaticInjection/HydroTurbine.json` |
| `HydroPumpTurbine` | `Operations/StaticInjection/HydroPumpTurbine.json` |
| `EnergyReservoirStorage` | `Operations/StaticInjection/EnergyReservoirStorage.json` |
| `PowerLoad` | `Operations/StaticInjection/PowerLoad.json` |
| `ACBus` | `Operations/Topology/ACBus.json` |
| `DCBus` | `Operations/Topology/DCBus.json` |
| `Area` | `Operations/Topology/Area.json` |
| `LoadZone` | `Operations/Topology/LoadZone.json` |
| `Line` | `Operations/Branch/Line.json` |
| `MonitoredLine` | `Operations/Branch/MonitoredLine.json` |
| `TwoTerminalGenericHVDCLine` | `Operations/Branch/TwoTerminalGenericHVDCLine.json` |
| `Arc` | `Operations/Topology/Arc.json` |

Enum types (all in `Core/common.json`): `ThermalFuels`, `PrimeMovers`, `ACBusType`, `LoadConformity`, `HydroTurbineType`, `PumpHydroStatus`.

---

## Generator (PyPSA) → Generator (Sienna)

Glossary

| Code | Description |
| --- | --- |
| `BA` | Energy Storage, Battery |
| `BT` | Binary Cycle Turbine (incl. geothermal) |
| `CA` | Combined-Cycle – Steam Part |
| `CC` | Combined-Cycle – Aggregated Plant |
| `CE` | Energy Storage, Compressed Air |
| `CP` | Energy Storage, Concentrated Solar Power |
| `CS` | Combined-Cycle Single-Shaft |
| `CT` | Combined-Cycle Combustion Turbine Part |
| `ES` | Energy Storage, Other |
| `FC` | Fuel Cell |
| `FW` | Energy Storage, Flywheel |
| `GT` | Combustion (Gas) Turbine |
| `HA` | Hydrokinetic, Axial Flow Turbine |
| `HB` | Hydrokinetic, Wave Buoy |
| `HK` | Hydrokinetic, Other |
| `HY` | Hydraulic Turbine |
| `IC` | Internal Combustion Engine |
| `PS` | Reversible Hydraulic Turbine (Pumped Storage) |
| `OT` | Other |
| `ST` | Steam Turbine |
| `PVe` | Photovoltaic (renamed from EIA `PV` to avoid conflict with `BusType.PV`) |
| `WT` | Wind Turbine, Onshore |
| `WS` | Wind Turbine, Offshore |

---

### Carrier Mapping Table

The PyPSA carrier names in the left-hand column were gathered from three places. Every
Sienna type, fuel and prime-mover assignment against them is this project's own work.

- `PyPSA2PowerSystems.jl/src/PyPSA2PowerSystems.jl` (`PYPSA_CATS` dict), read for the
  carrier names it recognises
- A separate PyPSA carrier-mapping table that spells some carriers with a hyphen
- Binary `.nc` network files (carriers inferred from sidecar metadata)

**Mapping type key:** `direct` = correct and unambiguous; `default assumption` = one of several plausible choices; `unsupported` = no clean Sienna mapping exists.

The `Sienna ThermalFuels` column is populated only for `ThermalStandard` targets. Renewable and hydro types do not have a fuel classification.

| PyPSA carrier | Sienna concrete type | Sienna `ThermalFuels` | Sienna `PrimeMovers` | Mapping type | Notes |
| --- | --- | --- | --- | --- | --- |
| **Solar** |  |  |  |  |  |
| `solar` | `RenewableDispatch` | — | `PVe` | direct | Generic utility-scale PV |
| `solar-utility` | `RenewableDispatch` | — | `PVe` | direct | Equivalent to `solar`; deduplicate at ingestion |
| `solar-rooftop` | `RenewableNonDispatch` | — | `PVe` | default assumption | Behind-the-meter; assumed non-dispatchable. Use `RenewableDispatch` if curtailment is modelled |
| **Wind** |  |  |  |  |  |
| `onwind` | `RenewableDispatch` | — | `WT` | direct | Onshore wind |
| `on-wind` | `RenewableDispatch` | — | `WT` | direct | Hyphenated spelling of `onwind` — treat identically |
| `offwind-ac` | `RenewableDispatch` | — | `WS` | direct | Offshore wind, AC grid connection |
| `offwind-dc` | `RenewableDispatch` | — | `WS` | direct | Offshore wind, DC link; AC/DC topology distinction lost |
| `off-wind` | `RenewableDispatch` | — | `WS` | direct | Hyphenated spelling of `offwind` |
| **Hydro** |  |  |  |  |  |
| `hydro` | `HydroDispatch` | — | `HY` | direct | Reservoir or dispatchable run-of-river |
| `ror` | `HydroDispatch` | — | `HY` | default assumption | Run-of-river typically has `p_max_pu` time series in PyPSA but no reservoir. `HydroDispatch` is the closest fit; see open questions |
| `PHS` | `EnergyReservoirStorage` | — | `PS` | direct | Pumped-storage hydro (PyPSA `StorageUnit`). The translator emits PHS as `EnergyReservoirStorage` (Sienna's self-contained battery-style storage device with input / output power limits and SoC dynamics), not `HydroPumpTurbine` + `HydroReservoir`. See section 6 |
| **Nuclear** |  |  |  |  |  |
| `nuclear` | `ThermalStandard` | `NUCLEAR` | `ST` | direct |  |
| **Coal** |  |  |  |  |  |
| `coal` | `ThermalStandard` | `COAL` | `ST` | direct | Generic coal; subcategory (bituminous, lignite, subcritical/supercritical) lost. More specific values: `BITUMINOUS_COAL`, `LIGNITE_COAL`, `SUBBITUMINOUS_COAL` |
| **Gas** |  |  |  |  |  |
| `CCGT` | `ThermalStandard` | `NATURAL_GAS` | `CC` | direct | `CC` = Combined-Cycle Aggregated Plant |
| `OCGT` | `ThermalStandard` | `NATURAL_GAS` | `GT` | direct | `GT` = Combustion (Gas) Turbine |
| `gas` | `ThermalStandard` | `NATURAL_GAS` | `CC` | default assumption | Generic gas; defaults to CCGT. Should be configurable — see open questions |
| **Oil** |  |  |  |  |  |
| `oil` | `ThermalStandard` | `DISTILLATE_FUEL_OIL` | `GT` | default assumption | Distillate assumed (No. 1/2/4 diesel); could be `RESIDUAL_FUEL_OIL` (heavy fuel oil). `GT` for peakers; could be `IC` (diesel reciprocating) or `ST` |
| **Geothermal** |  |  |  |  |  |
| `geothermal` | `ThermalStandard` | `GEOTHERMAL` | `BT` | default assumption | `BT` = Binary Cycle Turbine (most common for new geothermal). Flash-steam plants use `ST`. Ambiguous without plant-level metadata |
| **Biomass / Bioenergy** |  |  |  |  |  |
| `biomass` | `ThermalStandard` | `OTHER_BIOMASS_SOLIDS` | `ST` | default assumption | Broad category. `AG_BYPRODUCT` (crop residue), `WOOD_WASTE_SOLIDS` (forestry), `OTHEHR_BIOMASS_GAS` (biogas) are more specific alternatives |
| `bioenergy` | `ThermalStandard` | `OTHER_BIOMASS_SOLIDS` | `ST` | default assumption | Even broader than `biomass`; could span solids, liquids, or gas fractions. Very coarse mapping |
| **Waste** |  |  |  |  |  |
| `waste` | `ThermalStandard` | `MUNICIPAL_WASTE` | `ST` | direct | Municipal solid waste incineration. `TIREDERIVED_FUEL` or `SLUDGE_WASTE` for more specific waste streams |
| **Hydrogen** |  |  |  |  |  |
| `hydrogen` | `ThermalStandard` | `OTHER_GAS` | `FC` | default assumption | **Lossy.** No `HYDROGEN` in `ThermalFuels`. `FC` = Fuel Cell; use `GT` for hydrogen combustion turbine. See flags |

---

### Storage-related carriers (not Generator types)

The following carrier appears in PyPSA networks alongside Generator carriers but maps to a different PyPSA component type and is out of scope for v1 Generator translation.

| PyPSA carrier | PyPSA component type | Sienna target (v1) | Sienna `PrimeMovers` | Mapping type | Notes |
| --- | --- | --- | --- | --- | --- |
| `battery` | `StorageUnit` | (`EnergyReservoirStorage`) | `BA` | unsupported | Not a `Generator`. Maps to `EnergyReservoirStorage` in Sienna — needs a separate translation path. Storage translation is out of scope for v1. |

---

### Generator Attribute Mappings

#### 1. `ThermalStandard`

**Applies to carriers:** `coal`, `CCGT`, `OCGT`, `gas`, `oil`, `nuclear`, `geothermal`, `biomass`, `bioenergy`, `waste`, `hydrogen`

`ThermalStandard` is the workhorse thermal type — single startup category, linear or piecewise cost curve, optional unit commitment constraints. `ThermalMultiStart` (not mapped here) requires multi-temperature startup cost data that PyPSA networks rarely carry.

| Sienna field | Type / unit | PyPSA source | Transform | Mapping type | Notes |
| --- | --- | --- | --- | --- | --- |
| `id` | `Int` | — | auto-assigned | defaulted | Auto-assigned by Sienna on ingestion; do not set |
| `name` | `String` | `n.generators.index` | — | direct | Generator name from index |
| `available` | `Bool` | `n.generators.active` | — | direct | Default `True` |
| `status` | `Bool` | `n.generators.active` | — | defaulted | `True` — PyPSA has no separate initial on/off state; use `active` |
| `bus` | `ACBus` | `n.generators.bus` | name → ACBus lookup | derived | Must resolve string bus name to instantiated `ACBus` object |
| `active_power` | `Float64` (MW) | `n.generators.p_nom`, `p_min_pu` | `effective_p_nom × p_min_pu` | derived | Initial dispatch point; use min operating point. If `committable=False` and `p_min_pu=0`, use `0.0` |
| `reactive_power` | `Float64` (MVAR) | — | `0.0` | defaulted | PyPSA networks rarely model Q for generators |
| `rating` | `Float64` (pu) | `n.generators.p_max_pu` | `p_max_pu` | derived | Nameplate in pu of `base_power`; typically `1.0` |
| `active_power_limits` | `MinMax` (MW) | `n.generators`: `p_nom`, `p_min_pu`, `p_max_pu` | `(min=effective_p_nom×p_min_pu, max=effective_p_nom×p_max_pu)` | derived | Use static values. If `p_max_pu` / `p_min_pu` are time-varying, use the representative max (e.g. mean or peak) for the static field, and attach a time series — see time series section |
| `reactive_power_limits` | `Union{Nothing,MinMax}` (MVAR) | — | `nothing` | defaulted | PyPSA does not carry Q limits for most generators |
| `ramp_limits` | `Union{Nothing,UpDown}` (MW/min) | `n.generators.ramp_limit_up`, `ramp_limit_down` | `effective_p_nom × ramp_limit_up ÷ (dt_h × 60)` | derived | PyPSA ramp is pu/snapshot → MW/min: divide by snapshot duration (hours) and by 60. If `NaN` → `nothing`. See snapshot note in cross-cutting section |
| `operation_cost` | `ThermalGenerationCost` | `n.generators.marginal_cost`, `start_up_cost`, `shut_down_cost` | See cost pattern above | derived | `marginal_cost` ($/MWh) → `CostCurve(LinearCurve(marginal_cost))`. See cost notes below |
| `base_power` | `Float64` (MVA) | `n.generators.p_nom` | `effective_p_nom` (`p_nom_opt` when `p_nom_extendable` else `p_nom`) | derived | See convention discussion above |
| `time_limits` | `Union{Nothing,UpDown}` (hours) | `n.generators.min_up_time`, `min_down_time` | `min_up_time × dt_h` | derived | PyPSA counts snapshots; multiply by snapshot duration in hours. If both `0` → `nothing` |
| `must_run` | `Bool` | — | `false` | defaulted | No PyPSA equivalent; could be inferred from `p_min_pu ≈ p_max_pu` for must-run units |
| `prime_mover_type` | `PrimeMovers` | (carrier classification) | from carrier mapping table | derived | Set per carrier: e.g. `CC` for CCGT, `ST` for coal/nuclear |
| `fuel_type` | `ThermalFuels` | (carrier classification) | from carrier mapping table | derived | Set per carrier: e.g. `NATURAL_GAS`, `COAL`, `NUCLEAR` |
| `time_at_status` | `Float64` (hours) | `n.generators.up_time_before`, `down_time_before` | `up_time_before × dt_h` | derived | Optional; tracks how long unit has been at current status before optimisation starts |
| `dynamic_injector` | `Union{Nothing,DynamicInjection}` | — | `nothing` | defaulted | Dynamic stability models not in PyPSA |

**Minimal valid JSON example (`ThermalStandard`):**

```json
{
  "id": 1,
  "name": "coal_gen_1",
  "available": true,
  "status": true,
  "bus": 1,
  "active_power": 100.0,
  "reactive_power": 0.0,
  "rating": 1.0,
  "active_power_limits": { "min": 50.0, "max": 200.0 },
  "base_power": 200.0,
  "operation_cost": {
    "cost_type": "THERMAL",
    "fixed": 5000.0,
    "start_up": 1000.0,
    "shut_down": 500.0,
    "variable": {
      "variable_cost_type": "COST",
      "power_units": "NATURAL_UNITS",
      "value_curve": {
        "curve_type": "INPUT_OUTPUT",
        "function_data": { "function_type": "LINEAR", "proportional_term": 10.0, "constant_term": 0.0 }
      },
      "vom_cost": {
        "curve_type": "INPUT_OUTPUT",
        "function_data": { "function_type": "LINEAR", "proportional_term": 0.0, "constant_term": 0.0 }
      }
    }
  }
}
```

##### Time series for `ThermalStandard`

| PyPSA time-varying attribute | Target | Sienna mechanism |
| --- | --- | --- |
| `n.generators_t.p_max_pu` | `max_active_power` | `TimeSeriesAssociation` on `max_active_power`: store the per-unit `p_max_pu` shape (no pre-multiplication), `scaling_factor_multiplier: "PowerSystems.get_max_active_power"` |
| `n.generators_t.marginal_cost` | `operation_cost` | Cannot attach a series to `ThermalGenerationCost.variable` directly; requires `MarketBidCost`. Flag as unsupported in simple translation; document as known gap |

##### Unit commitment (`committable`)

SiennaSchemas `ThermalStandard` has no `committable` field, and whether a thermal is unit-committed is a PowerSimulations.jl *formulation* choice made per component type at simulation time — not per-component data. It therefore cannot be encoded in the emitted JSON.

So the translation makes no unit-commitment decision in the output. It records each thermal's PyPSA `committable` value in the `extensions.json` sidecar (see Target format → Component extensions), under the `generator` kind, and does nothing else with it:

```json
{ "generator": [ { "name": "coal_1", "committable": true } ] }
```

The related `ThermalStandard` fields that *do* have schema homes (`operation_cost.start_up`/`shut_down`, `time_limits`, `time_at_status`, start/shut ramp limits) are mapped from their PyPSA sources as ordinary data when present, per the table above — unconditionally, not gated on `committable`.

The reverse direction is documented in [Translation from Sienna to PyPSA](./translation-from-sienna-to-pypsa.md).

---

#### 2. `RenewableDispatch`

**Applies to carriers:** `solar`, `solar-utility`, `onwind`, `on-wind`, `offwind-ac`, `offwind-dc`, `off-wind`

`RenewableDispatch` represents curtailable renewable generators — those whose output can be reduced below their available profile. It has no `active_power_limits` field; the maximum is defined entirely by the `max_active_power` time series (or `rating × base_power` if no time series exists). It has no `must_run` or `ramp_limits`.

| Sienna field | Type / unit | PyPSA source | Transform | Mapping type | Notes |
| --- | --- | --- | --- | --- | --- |
| `id` | `Int` | — | auto-assigned | defaulted | Auto-assigned by Sienna on ingestion |
| `name` | `String` | `n.generators.index` | — | direct |  |
| `available` | `Bool` | `n.generators.active` | — | direct |  |
| `bus` | `ACBus` | `n.generators.bus` | name → ACBus lookup | derived |  |
| `active_power` | `Float64` (MW) | `n.generators.p_nom`, `p_min_pu` | `effective_p_nom × p_min_pu` | derived | Typically `0.0` for renewables (p_min_pu default = 0) |
| `reactive_power` | `Float64` (MVAR) | — | `0.0` | defaulted |  |
| `rating` | `Float64` (pu) | `n.generators.p_max_pu` (static) | `p_max_pu` | derived | Typically `1.0`; derating possible |
| `prime_mover_type` | `PrimeMovers` | (carrier classification) | `PVe` / `WT` / `WS` | derived | From carrier mapping table |
| `reactive_power_limits` | `Union{Nothing,MinMax}` (MVAR) | — | `nothing` | defaulted |  |
| `power_factor` | `Float64` ([0,1]) | — | `1.0` | defaulted | No scalar power factor in PyPSA generator schema |
| `operation_cost` | `RenewableGenerationCost` | `n.generators.marginal_cost` | `CostCurve(LinearCurve(marginal_cost))` | derived | Usually `0.0` for wind/solar; non-zero for curtailment-penalised networks |
| `base_power` | `Float64` (MVA) | `n.generators.p_nom` | `effective_p_nom` (`p_nom_opt` when `p_nom_extendable` else `p_nom`) | derived |  |
| `dynamic_injector` | `Union{Nothing,DynamicInjection}` | — | `nothing` | defaulted |  |

**Minimal valid JSON example (`RenewableDispatch`):**

```json
{
  "id": 2,
  "name": "solar_gen_1",
  "available": true,
  "bus": 1,
  "active_power": 0.0,
  "reactive_power": 0.0,
  "rating": 1.0,
  "prime_mover_type": "PVe",
  "power_factor": 1.0,
  "base_power": 100.0,
  "operation_cost": {
    "cost_type": "RENEWABLE",
    "variable": {
      "variable_cost_type": "COST",
      "power_units": "NATURAL_UNITS",
      "value_curve": {
        "curve_type": "INPUT_OUTPUT",
        "function_data": { "function_type": "LINEAR", "proportional_term": 0.0, "constant_term": 0.0 }
      },
      "vom_cost": {
        "curve_type": "INPUT_OUTPUT",
        "function_data": { "function_type": "LINEAR", "proportional_term": 0.0, "constant_term": 0.0 }
      }
    }
  }
}
```

#### Time series for `RenewableDispatch`

`RenewableDispatch` has **no static `max_active_power` parameter** — the docstring explicitly states it is “instead calculated when calling `get_max_active_power()`”, which reads an attached time series.

| PyPSA attribute | Where | Target | Transform | Notes |
| --- | --- | --- | --- | --- |
| `p_max_pu` | `n.generators_t.p_max_pu` (or static scalar) | `TimeSeriesAssociation` on `max_active_power`, `scaling_factor_multiplier: "PowerSystems.get_max_active_power"` | values = `p_max_pu_series` (pu of `base_power`, stored unchanged) | **Required** if p_max_pu is time-varying. If static scalar, encode in `rating` only |
| `p_min_pu` | `n.generators_t.p_min_pu` | Not directly supported | — | `RenewableDispatch` has no time-varying lower limit. Use `0.0` for `active_power` |
| `marginal_cost` | `n.generators_t.marginal_cost` | Not directly supported | — | Switch to `MarketBidCost` if time-varying marginal cost is needed |

**Storage convention.** `PowerSimulations.jl/src/devices_models/devices/renewable_generation.jl`'s `get_default_time_series_names` registers `ActivePowerTimeSeriesParameter => "max_active_power"` for `RenewableGen` under `FixedOutput` and any `AbstractRenewableFormulation`. The formulation multiplies the stored series by `get_max_active_power(d)` (i.e. `rating × base_power`) at solve time. Storing the series in pu of `base_power`, with values in `[0, 1]`, matches this convention and mirrors the `PowerLoad` pattern used for demand. The translator must not pre-multiply by `p_nom`, since the multiplier is applied by the formulation.

**v1 implementation behaviour.** The translator skips the time series when the generator does not appear as a column in `n.generators_t.p_max_pu`, or when its per-unit profile is flat (`np.ptp(values) < 1e-9`). A flat profile carries the same information as the static `rating × base_power` ceiling already encoded on the component, so emitting it would only inflate the H5 sidecar. A column whose index does not match `n.snapshots` is treated as a hard error rather than silently coerced.

---

#### 3. `RenewableNonDispatch`

**Applies to carriers:** `solar-rooftop`

`RenewableNonDispatch` is the must-take type — the system always accepts whatever is available. It has **no `operation_cost` field**, **no `active_power_limits`**, and **no `reactive_power_limits`**. The maximum power is defined by `rating × base_power` and/or an attached `max_active_power` time series.

| Sienna field | Type / unit | PyPSA source | Transform | Mapping type | Notes |
| --- | --- | --- | --- | --- | --- |
| `id` | `Int` | — | auto-assigned | defaulted | Auto-assigned by Sienna on ingestion |
| `name` | `String` | `n.generators.index` | — | direct |  |
| `available` | `Bool` | `n.generators.active` | — | direct |  |
| `bus` | `ACBus` | `n.generators.bus` | name → ACBus lookup | derived |  |
| `active_power` | `Float64` (MW) | `n.generators.p_nom`, `p_max_pu` | `effective_p_nom × p_max_pu` | derived | Initial active power — use peak available for initialisation |
| `reactive_power` | `Float64` (MVAR) | — | `0.0` | defaulted |  |
| `rating` | `Float64` (pu) | `n.generators.p_max_pu` | `p_max_pu` | derived | Typically `1.0` |
| `prime_mover_type` | `PrimeMovers` | (carrier classification) | `PVe` | derived |  |
| `power_factor` | `Float64` ([0,1]) | — | `1.0` | defaulted |  |
| `base_power` | `Float64` (MVA) | `n.generators.p_nom` | `effective_p_nom` (`p_nom_opt` when `p_nom_extendable` else `p_nom`) | derived |  |
| `dynamic_injector` | `Union{Nothing,DynamicInjection}` | — | `nothing` | defaulted |  |

**Minimal valid JSON example (`RenewableNonDispatch`):**

```json
{
  "id": 3,
  "name": "rooftop_solar_1",
  "available": true,
  "bus": 1,
  "active_power": 0.0,
  "reactive_power": 0.0,
  "rating": 1.0,
  "prime_mover_type": "PVe",
  "power_factor": 1.0,
  "base_power": 50.0
}
```

##### Time series for `RenewableNonDispatch`

Same mechanism as `RenewableDispatch`: emit a `TimeSeriesAssociation` on `max_active_power` (`scaling_factor_multiplier: "PowerSystems.get_max_active_power"`) whose values are `p_max_pu_series` in pu of `base_power` (no pre-multiplication by `p_nom`). The same skip-when-absent and skip-when-flat rules apply. The difference is that the Sienna solver treats this as an inviolable maximum (must-take), not as a curtailable upper bound.

##### Note on `operation_cost`

`RenewableNonDispatch` has **no cost field**. If the PyPSA generator has a non-zero `marginal_cost`, that information is **lost** in translation. Flag in the output log.

---

#### 4. `HydroDispatch`

**Applies to carriers:** `hydro` (PyPSA `StorageUnit`).

**Source component.** Reservoir hydro is a PyPSA `StorageUnit`, not a `Generator`: it carries the `inflow` series and round-trip efficiency the energy budget needs. The v1 translator therefore emits `HydroDispatch` from `StorageUnit` rows with carrier `hydro`. (`ror` run-of-river is a PyPSA `Generator` with no reservoir/inflow; it is deferred — `ror` generators are reported as skipped until a generator-sourced path is added.)

**Emitted fields.** v1 emits only HydroDispatch's *required* fields (matching the minimal JSON example below). `ramp_limits`, `time_limits`, `status`, `time_at_status`, and `reactive_power_limits` have no `StorageUnit` source and are omitted (they are optional in the schema, with `status`/`time_at_status` carrying struct defaults).

| Sienna field | Type / unit | PyPSA source | Transform | Mapping type | Notes |
| --- | --- | --- | --- | --- | --- |
| `id` | `Int` | — | auto-assigned | defaulted | Auto-assigned by Sienna on ingestion |
| `name` | `String` | `n.storage_units.index` | — | direct |  |
| `available` | `Bool` | — | `true` | defaulted | StorageUnit has no `active` field |
| `bus` | `ACBus` | `n.storage_units.bus` | name → ACBus lookup | derived |  |
| `active_power` | `Float64` (MW) | `n.storage_units.p_nom`, `p_min_pu` | `effective_p_nom × p_min_pu` | derived |  |
| `reactive_power` | `Float64` (MVAR) | — | `0.0` | defaulted |  |
| `rating` | `Float64` (pu) | `n.storage_units.p_max_pu` | `p_max_pu` | derived |  |
| `prime_mover_type` | `PrimeMovers` | (carrier classification) | `HY` | derived |  |
| `active_power_limits` | `MinMax` (MW) | `p_nom`, `p_min_pu`, `p_max_pu` | `(effective_p_nom×p_min_pu, effective_p_nom×p_max_pu)` | derived |  |
| `base_power` | `Float64` (MVA) | `n.storage_units.p_nom` | `effective_p_nom` (`p_nom_opt` when `p_nom_extendable` else `p_nom`) | derived |  |
| `operation_cost` | `HydroGenerationCost` | `n.storage_units.marginal_cost` | `CostCurve(LinearCurve(marginal_cost))` | derived | Water value if any; default `0.0` |

**Minimal valid JSON example (`HydroDispatch`):**

```json
{
  "id": 4,
  "name": "hydro_dispatch_1",
  "available": true,
  "bus": 1,
  "active_power": 50.0,
  "reactive_power": 0.0,
  "rating": 1.0,
  "prime_mover_type": "HY",
  "active_power_limits": { "min": 10.0, "max": 100.0 },
  "base_power": 100.0,
  "operation_cost": {
    "cost_type": "HYDRO_GEN",
    "variable": {
      "variable_cost_type": "COST",
      "power_units": "NATURAL_UNITS",
      "value_curve": {
        "curve_type": "INPUT_OUTPUT",
        "function_data": { "function_type": "LINEAR", "proportional_term": 5.0, "constant_term": 0.0 }
      },
      "vom_cost": {
        "curve_type": "INPUT_OUTPUT",
        "function_data": { "function_type": "LINEAR", "proportional_term": 0.0, "constant_term": 0.0 }
      }
    }
  }
}
```

##### Time series for `HydroDispatch`

The translator emits `HydroDispatch` from PyPSA `StorageUnit` rows with carrier `hydro` (see the storage section below for the source-component mapping) and dispatches them under `HydroDispatchRunOfRiverBudget`. Two time series are attached per unit:

| PyPSA attribute | Where | Target | Transform | Notes |
| --- | --- | --- | --- | --- |
| `p_max_pu` (static) | `n.storage_units.p_max_pu` | `TimeSeriesAssociation` on `max_active_power`, `scaling_factor_multiplier: "PowerSystems.get_max_active_power"` | flat values = `p_max_pu` (pu of `base_power`) | Per-step active-power cap. Multiplier in PSI is `get_max_active_power(d) = p_max_pu × base_power`, so a flat `1.0` series allows the turbine to dispatch at rated power any hour. The formulation requires this TS to be present even when constant; PSI's `add_parameters!` errors on missing TS. |
| `inflow` × `efficiency_dispatch` | `n.storage_units_t.inflow` × `n.storage_units.efficiency_dispatch` (`StorageUnit` carrier `hydro`) | `TimeSeriesAssociation` on `hydro_budget` | values = `inflow_mw × efficiency_dispatch / p_nom` (pu of `base_power`) | Energy budget over the horizon. PSI's `EnergyBudgetConstraint` enforces `sum(P[t]) <= sum(get_max_active_power(d) × budget[t])`, so summed in MW the right-hand side becomes `efficiency_dispatch × total_inflow_mwh`. This is the deliverable inflow energy. |

**Why `max_active_power`, not `inflow`.** `HydroDispatch` (and its parent `HydroGen`) has no `inflow` struct field in either `SiennaSchemas/Operations/StaticInjection/HydroDispatch.json` or `PowerSystems.jl/src/models/generated/HydroDispatch.jl`. Only `HydroReservoir` carries an `inflow` field. Correspondingly, `HydroPowerSimulations.jl/src/hydro_generation.jl`'s `get_default_time_series_names(::HydroGen, HydroDispatchRunOfRiverBudget)` registers `ActivePowerTimeSeriesParameter => "max_active_power"` and `EnergyBudgetTimeSeriesParameter => "hydro_budget"`. A series named `"inflow"` attached to a `HydroDispatch` would be silently ignored.

**Why fold `efficiency_dispatch` into the budget.** PyPSA's `StorageUnit` deducts `dispatch / efficiency_dispatch` from the state of charge, so under `cyclic_state_of_charge=True` the natural upper bound on weekly dispatch is `efficiency_dispatch × total_inflow_mwh` (with any spillage subtracting further; PyPSA-Eur typically prices spillage at zero and rarely uses it). `HydroDispatch` has no turbine-efficiency field of its own; `efficiency` is only on `HydroTurbine`. Encoding the efficiency in the budget delivers the same deliverable-energy cap without forcing a `HydroTurbine` schema migration.

**Why `HydroDispatchRunOfRiverBudget`, not `HydroEnergyModelReservoir`.** `HydroEnergyModelReservoir` (and its sibling `HydroWaterFactorModel`) operate on `HydroReservoir`, a separate PSY type whose schema requires `intake_elevation`, `head_to_volume_factor` (a `ValueCurve`), and topological pairing with `HydroTurbine` instances via `upstream_turbines`/`downstream_turbines`. PyPSA carries none of these. The budget formulation gives us the same horizon-wide energy cap (the dominant constraint when storage capacity is large relative to inflow) without inventing schema fields. Within-horizon storage capacity bounds (`max_hours × p_nom`) are not enforced; on the PyPSA-Eur sample network this is uncontroversial because aggregate storage capacity (204 TWh) is two orders of magnitude larger than weekly inflow (5.3 TWh). Networks with smaller reservoirs or longer horizons may need the `HydroReservoir` + `HydroTurbine` pairing.

**Empirical verification.** On the one-week PyPSA-Eur test network the budget formulation reproduces PyPSA's reservoir hydro dispatch exactly (4.7417 TWh on both sides; per-unit totals match to the megawatt-hour). The previous run-of-river mapping (`max_active_power` TS = `inflow_pu`, no budget) over-dispatched by 11% because per-step inflow ceilings did not allow time-shifting.

---

#### 5. `HydroTurbine`

**Applies to carriers:** `hydro` (where detailed plant-level modelling is needed)

`HydroTurbine` is a unit-level hydro type (`<: HydroUnit <: HydroGen`) representing a single turbine within a plant. It has richer physical fields than `HydroDispatch`: `efficiency`, `powerhouse_elevation`, `outflow_limits`, `conversion_factor`, `travel_time`. Most of these have **no PyPSA equivalent** — only the basic power and ramp parameters can be populated from PyPSA data.

> **Note on usage context:** The docstring for `HydroUnit` says these types represent “generators represented as units”. Whether `HydroTurbine` can be added directly to a `System` as a standalone component (like `HydroDispatch`) or only as part of a compound hydro asset is unconfirmed. **Verify before using this type in production.** If standalone use is not supported, fall back to `HydroDispatch`.
>

| Sienna field | Type / unit | PyPSA source | Transform | Mapping type | Notes |
| --- | --- | --- | --- | --- | --- |
| `id` | `Int` | — | auto-assigned | defaulted | Auto-assigned by Sienna on ingestion |
| `name` | `String` | `n.generators.index` | — | direct |  |
| `available` | `Bool` | `n.generators.active` | — | direct |  |
| `bus` | `ACBus` | `n.generators.bus` | name → ACBus lookup | derived |  |
| `active_power` | `Float64` (MW) | `p_nom`, `p_min_pu` | `effective_p_nom × p_min_pu` | derived |  |
| `reactive_power` | `Float64` (MVAR) | — | `0.0` | defaulted |  |
| `rating` | `Float64` (pu) | `p_max_pu` | `p_max_pu` | derived |  |
| `active_power_limits` | `MinMax` (MW) | `p_nom`, `p_min_pu`, `p_max_pu` | `(effective_p_nom×p_min_pu, effective_p_nom×p_max_pu)` | derived |  |
| `reactive_power_limits` | `Union{Nothing,MinMax}` | — | `nothing` | defaulted |  |
| `base_power` | `Float64` (MVA) | `p_nom` | `effective_p_nom` (`p_nom_opt` when `p_nom_extendable` else `p_nom`) | derived |  |
| `operation_cost` | `HydroGenerationCost` | `marginal_cost` | `CostCurve(LinearCurve(marginal_cost))` | derived |  |
| `powerhouse_elevation` | `Float64` (m) | — | `0.0` | defaulted | Not in PyPSA; default to sea level |
| `ramp_limits` | `Union{Nothing,UpDown}` (MW/min) | `ramp_limit_up`, `ramp_limit_down` | `effective_p_nom × ramp_limit_up ÷ (dt_h × 60)` | derived |  |
| `time_limits` | `Union{Nothing,UpDown}` (hours) | `min_up_time`, `min_down_time` | `× dt_h` | derived |  |
| `outflow_limits` | `Union{Nothing,MinMax}` (m³/s) | — | `nothing` | unsupported | Water flow physics not in PyPSA |
| `efficiency` | `Float64` ([0,1]) | `n.generators.efficiency` | direct | direct | PyPSA `efficiency` (gen output/input ratio); same semantics |
| `turbine_type` | `HydroTurbineType` | — | `HydroTurbineType.UNKNOWN` | defaulted | No PyPSA equivalent |
| `conversion_factor` | `Float64` (m³→pu·hr) | — | `1.0` | defaulted | Volumetric-to-power conversion; not in PyPSA |
| `prime_mover_type` | `PrimeMovers` | (classification) | `PrimeMovers.HY` | derived |  |
| `travel_time` | `Float64` (hours) | — | — | unsupported | Optional in schema; hydraulic travel time not in PyPSA |

**Minimal valid JSON example (`HydroTurbine`):**

```json
{
  "id": 5,
  "name": "hydro_turbine_1",
  "available": true,
  "bus": 1,
  "active_power": 50.0,
  "reactive_power": 0.0,
  "rating": 1.0,
  "active_power_limits": { "min": 10.0, "max": 100.0 },
  "base_power": 100.0,
  "operation_cost": {
    "cost_type": "HYDRO_GEN",
    "variable": {
      "variable_cost_type": "COST",
      "power_units": "NATURAL_UNITS",
      "value_curve": {
        "curve_type": "INPUT_OUTPUT",
        "function_data": { "function_type": "LINEAR", "proportional_term": 5.0, "constant_term": 0.0 }
      },
      "vom_cost": {
        "curve_type": "INPUT_OUTPUT",
        "function_data": { "function_type": "LINEAR", "proportional_term": 0.0, "constant_term": 0.0 }
      }
    }
  }
}
```

---

#### 6. `EnergyReservoirStorage` (PHS)

**Applies to carriers:** `PHS` (pumped-storage hydro)

In PyPSA, pumped storage is represented as a `StorageUnit` (not a `Generator`), so the source component is different from all other types in this document. `p_min_pu` is typically `-1.0` (charging / pumping) and `p_max_pu = 1.0` (discharging / generating).

The translator emits each PHS unit as a single `EnergyReservoirStorage` component. `EnergyReservoirStorage` is Sienna's self-contained battery-style storage device (`<: Storage`), with its own `input_active_power_limits` (charging), `output_active_power_limits` (discharging), `storage_capacity` (MWh), and `efficiency::NamedTuple{(:in, :out)}`. PSI's `StorageDispatchWithReserves` formulation (from `StorageSystemsSimulations.jl`) enforces the energy balance and, with the `energy_target` attribute on, a hard end-of-horizon target for cyclic SoC.

> **Why not `HydroPumpTurbine` + `HydroReservoir`?** That pair (path A in the design discussion) is the PSY-canonical PHS topology, but it requires a second component per PHS, an `InflowTimeSeriesParameter` for every reservoir, and a custom JuMP constraint for cyclic SoC (the formulation does not enforce final == initial natively). `EnergyReservoirStorage` (path B) collapses the same physics into one component with a tighter PyPSA-StorageUnit-shaped interface. Trade-off: pump and turbine variables surface as `ActivePowerInVariable` / `ActivePowerOutVariable` rather than as the explicit `HydroPumpTurbine` pair.

| Sienna field | Type / unit | PyPSA source | Transform | Mapping type | Notes |
| --- | --- | --- | --- | --- | --- |
| `id` | `Int` | — | auto-assigned | defaulted | Auto-assigned by Sienna on ingestion |
| `name` | `String` | `n.storage_units.index` | — | direct | From `StorageUnit`, not `Generator` |
| `available` | `Bool` | `n.storage_units.active` | — | direct |  |
| `bus` | `ACBus` | `n.storage_units.bus` | name -> ACBus lookup | derived |  |
| `prime_mover_type` | `PrimeMovers` | (classification) | `PrimeMovers.PS` | derived | Pumped Storage |
| `storage_technology_type` | `StorageTech` | — | `StorageTech.OTHER_MECH` | defaulted | The `StorageTech` enum has no PHS-specific value; `OTHER_MECH` is the closest fit |
| `storage_capacity` | `Float64` (pu-hours of base_power) | `max_hours` | `max_hours` | direct | PSI stores `storage_capacity` and the energy variable in pu of base_power and multiplies by `base_power` on result export (`convert_result_to_natural_units`), so this field carries `max_hours`. Translator raises if `max_hours <= 0` for a PHS row |
| `storage_level_limits` | `MinMax` (ratio) | — | `(min=0.0, max=1.0)` | defaulted | Allowable SoC band as a ratio of `storage_capacity` |
| `initial_storage_capacity_level` | `Float64` (ratio) | `state_of_charge_initial` | `state_of_charge_initial / (effective_p_nom * max_hours)` clamped to [0, 1] | derived | PyPSA-EUR commonly defaults this to 0; translator passes through verbatim and notes the choice in the decisions log |
| `rating` | `Float64` (pu of base_power) | `p_max_pu` | `p_max_pu` | direct | Discharge-side rating |
| `active_power` | `Float64` (MW) | — | `0.0` | defaulted | PHS at rest at start of horizon |
| `input_active_power_limits` | `MinMax` (pu of base_power) | `p_min_pu` | `(0.0, abs(p_min_pu))` | direct | Pump (charging) capacity. PyPSA sign: charging is `p < 0`, so pump capacity = `abs(p_min_pu)` pu. Multiplied by `base_power` (= `effective_p_nom`) on export to give MW |
| `output_active_power_limits` | `MinMax` (pu of base_power) | `p_max_pu` | `(0.0, p_max_pu)` | direct | Turbine (discharging) capacity in pu. Multiplied by `base_power` on export to give MW |
| `efficiency` | `NamedTuple{(:in, :out)}` ([0, 1] each) | `efficiency_store`, `efficiency_dispatch` | `(in=efficiency_store, out=efficiency_dispatch)` | direct | Direct mapping from StorageUnit |
| `reactive_power` | `Float64` (MVAR) | — | `0.0` | defaulted |  |
| `reactive_power_limits` | `Union{Nothing, MinMax}` | — | `nothing` | defaulted |  |
| `base_power` | `Float64` (MVA) | `p_nom` | `effective_p_nom` (`p_nom_opt` when `p_nom_extendable` else `p_nom`) | derived |  |
| `operation_cost` | `Union{StorageCost, MarketBidCost}` | `marginal_cost`, cyclic flag | `StorageCost(charge_variable_cost=0, discharge_variable_cost=marginal_cost, energy_shortage_cost=energy_surplus_cost=1e6 if cyclic else 0)` | derived | Discharge cost takes the PyPSA `marginal_cost`. Symmetric shortage / surplus penalty makes `storage_target` a hard constraint when cyclic |
| `conversion_factor` | `Float64` | — | `1.0` | defaulted | No unit conversion between `storage_capacity` and energy variable |
| `storage_target` | `Float64` (pu-hours of base_power) | `state_of_charge_initial`, `cyclic_state_of_charge` | `initial_storage_capacity_level * max_hours` if cyclic else `0.0` | derived | End-of-horizon energy target on the same internal scale as the energy variable (despite the schema docstring's "ratio" wording, `StorageDispatchWithReserves` reads it literally in `StateofChargeTargetConstraint`). Translator raises if `cyclic_state_of_charge` is mixed across PHS units, since the formulation attribute is per device-model |
| `cycle_limits` | `Int` | — | `10000` | defaulted | Unused: pipeline disables the `cycling_limits` formulation attribute (`storage_target` covers the cyclic boundary) |

**Minimal valid JSON example (`EnergyReservoirStorage`):**

```json
{
  "name": "AT0 0 PHS",
  "available": true,
  "bus": 1,
  "prime_mover_type": "PS",
  "storage_technology_type": "OTHER_MECH",
  "storage_capacity": 125.9,
  "storage_level_limits": { "min": 0.0, "max": 1.0 },
  "initial_storage_capacity_level": 0.0,
  "rating": 1.0,
  "active_power": 0.0,
  "input_active_power_limits": { "min": 0.0, "max": 1.0 },
  "output_active_power_limits": { "min": 0.0, "max": 1.0 },
  "efficiency": { "in": 0.866, "out": 0.866 },
  "reactive_power": 0.0,
  "base_power": 4241.3,
  "operation_cost": {
    "cost_type": "STORAGE",
    "charge_variable_cost": { "value_curve": { "function_data": { "function_type": "LINEAR", "proportional_term": 0.0, "constant_term": 0.0 } } },
    "discharge_variable_cost": { "value_curve": { "function_data": { "function_type": "LINEAR", "proportional_term": 0.0, "constant_term": 0.0 } } },
    "fixed": 0.0,
    "start_up": 0.0,
    "shut_down": 0.0,
    "energy_shortage_cost": 1000000.0,
    "energy_surplus_cost": 1000000.0
  },
  "conversion_factor": 1.0,
  "storage_target": 0.0,
  "cycle_limits": 10000
}
```

In this example, `storage_capacity = 125.9` (pu-hours = `max_hours`); on result export PSI multiplies by `base_power = 4241.3` MVA to give the natural unit `533991 MWh`. Likewise the power limit `max = 1.0` (pu) becomes `4241.3 MW` on export.

#### StorageUnit fields with no `EnergyReservoirStorage` mapping

| PyPSA StorageUnit field | Notes |
| --- | --- |
| `spill_cost` | Spillage costs not representable; closed reservoir model |
| `inflow` (time-varying) | Natural inflow into the reservoir. `EnergyReservoirStorage` has no inflow field; the formulation models a closed loop with no external water source. PyPSA-EUR typically reports zero PHS inflow in any case. If non-zero PHS inflow becomes meaningful, migrate to the `HydroPumpTurbine` + `HydroReservoir` pair (path A) which has an `InflowTimeSeriesParameter` |
| `marginal_cost_storage` | Charging marginal cost; `StorageCost.charge_variable_cost` is set to zero. PyPSA's `marginal_cost` populates `discharge_variable_cost` only |
| `ramp_limit_up`, `ramp_limit_down` | Storage ramp limits; no `EnergyReservoirStorage` field |
| `min_up_time`, `min_down_time` | No equivalent on this type |

## Bus Mappings

### `ACBus` — Attribute Mapping Table

PyPSA electricity buses (`carrier = "AC"`) map to Sienna `ACBus`. This covers the vast majority of buses in BTE PyPSA networks. A PyPSA network translated to Sienna will have one `ACBus` per electricity bus.

| Sienna field | Type / unit | PyPSA source | Transform | Mapping type | Notes |
| --- | --- | --- | --- | --- | --- |
| `id` | `Int` | — | auto-assigned | defaulted | Auto-assigned by Sienna on ingestion |
| `number` | `Int` | `n.buses.index` | 1-based row position in `n.buses` DataFrame | derived | PyPSA bus names are strings; Sienna requires a unique positive integer. Use the DataFrame row index (1-based in Julia). |
| `name` | `String` | `n.buses.index` | direct | direct | Use the PyPSA bus name string directly as the Sienna component name. |
| `available` | `Bool` | — | `true` | defaulted | PyPSA `Bus` has no `active` input field. Always `true`. |
| `bustype` | `Union{Nothing, ACBusType}` | `n.buses.control` (output) | `"PQ"→PQ`, `"PV"→PV`, `"Slack"→REF` | derived | **Critical — see bus type assignment section below.** `control` is an output derived from generators; may not be present. |
| `angle` | `Union{Nothing, Float64}` (radians) | — | `0.0` | defaulted | PyPSA has no input bus angle. Post-PF `v_ang` (in `n.buses_t`) is an output and not appropriate here. |
| `magnitude` | `Union{Nothing, Float64}` (pu) | `n.buses.v_mag_pu_set` | direct | direct | Both PyPSA and Sienna use pu of `base_voltage`. PyPSA default `1.0`. If `v_mag_pu_set` is time-varying (in `n.buses_t`), use the first value or the static default. |
| `voltage_limits` | `Union{Nothing, MinMax}` (pu) | `n.buses.v_mag_pu_min`, `v_mag_pu_max` | `(min=v_mag_pu_min, max=v_mag_pu_max)` | derived | **PyPSA defaults (0.0 / ∞) are invalid for Sienna.** When limits are at default, apply the standard fallback `(min=0.9, max=1.1)`. When explicitly set by the user, map directly. See voltage limits note below. |
| `base_voltage` | `Union{Nothing, Float64}` (kV) | `n.buses.v_nom` | direct | direct | Both in kV. PyPSA default is `1.0 kV` — this is the fallback for buses where voltage level was never specified; flag these for user review since 1 kV is atypical for transmission networks. |
| `area` | `Union{Nothing, Area}` | `n.buses.location` | create `Area(name=location)` if non-empty | derived | No native area concept in PyPSA. Use `location` string as a proxy Area name if populated. If `location` is empty, `area = nothing`. See area/zone notes. |
| `load_zone` | `Union{Nothing, LoadZone}` | `n.buses.location` | create `LoadZone(name=location, ...)` if non-empty | derived | Same proxy as `area`. Use the same `location` string for both `Area` and `LoadZone` name. If empty, `load_zone = nothing`. |

**Minimal valid JSON example (`ACBus`):**

```json
{
  "id": 1,
  "name": "BUS_1",
  "available": true,
  "number": 1
}
```

**Extensions sidecar.** Bus attributes with no SiennaSchemas field go in the `extensions.json` companion (see Component extensions), as a `bus` record identified by `name`:

```json
{ "bus": [ { "name": "bus_1", "carrier": "AC" } ] }
```

`carrier` is the only unmapped PyPSA `Bus` field. It is always `"AC"` for translated buses (DC buses are filtered out), but preserved for round-trip completeness.

---

### `DCBus` — Attribute Mapping Table

PyPSA `DC` carrier buses (`carrier = "DC"`) map to Sienna `DCBus`. These arise in networks with HVDC connections or DC grid nodes. `DCBus` is a subset of `ACBus` — it has no `bustype` or `angle` fields.

| Sienna field | Type / unit | PyPSA source | Transform | Mapping type | Notes |
| --- | --- | --- | --- | --- | --- |
| `id` | `Int` | — | auto-assigned | defaulted | Auto-assigned by Sienna on ingestion |
| `number` | `Int` | `n.buses.index` | 1-based row position | derived | Same strategy as `ACBus.number`. Integer IDs must be unique **across** both `ACBus` and `DCBus` instances in the same `System`. Use a global counter. |
| `name` | `String` | `n.buses.index` | direct | direct |  |
| `available` | `Bool` | — | `true` | defaulted |  |
| `magnitude` | `Union{Nothing, Float64}` (pu) | `n.buses.v_mag_pu_set` | direct | direct | Same as `ACBus`. |
| `voltage_limits` | `Union{Nothing, MinMax}` (pu) | `n.buses.v_mag_pu_min`, `v_mag_pu_max` | `(min, max)` | derived | Apply same fallback `(0.9, 1.1)` when defaults are 0.0/∞. |
| `base_voltage` | `Union{Nothing, Float64}` (kV) | `n.buses.v_nom` | direct | direct |  |
| `area` | `Union{Nothing, Area}` | `n.buses.location` | proxy | derived | Same as `ACBus`. |
| `load_zone` | `Union{Nothing, LoadZone}` | `n.buses.location` | proxy | derived | Same as `ACBus`. |

**Minimal valid JSON example (`DCBus`):**

```json
{
  "id": 2,
  "name": "DC_BUS_1",
  "available": true,
  "number": 101
}
```

---

### `Area` and `LoadZone` — Construction

These are aggregation containers for buses. A bus references its `Area`/`LoadZone` by integer `id`, so those objects must exist and have `id`s assigned; in the serialised type→list container, order within a list does not matter (references resolve by `id`).

#### `Area`

```json
{ "id": 1, "name": "Western Region" }
```

`name` is the bus location string. `peak_active_power`, `peak_reactive_power`, and `load_response` (MW/Hz load damping) are not in PyPSA and default to `0.0`.

#### `LoadZone`

```json
{ "id": 1, "name": "Zone_1", "peak_active_power": 1500.0, "peak_reactive_power": 300.0 }
```

`name` matches the `Area` name; `peak_active_power`/`peak_reactive_power` are schema-required and default to `0.0` (backfill with zonal totals after loads are translated if needed).

**Id-assignment order:** assign integer `id`s so referenced types come first — `Area`/`LoadZone`, then `ACBus`/`DCBus` (which reference them), then generators, loads, and branches (which reference buses). The serialised lists are unordered; only the `id` references matter.

---

## PyPSA `Line` → Sienna `Line` Attribute Mapping

---

### Summary

A PyPSA `Line` represents an AC transmission branch with physical impedance parameters (r, x, b, g). It maps cleanly to Sienna’s `Line` (`ACTransmission <: ACBranch`) since both use the same π-model representation of AC transmission physics. The principal translation challenge is unit conversion: PyPSA stores series impedances in absolute ohms and shunt admittances in siemens, while Sienna stores all quantities in per-unit on the system MVA base. Bus endpoint resolution follows the same name-lookup pattern as the generator mapping: PyPSA `bus0`/`bus1` string names are resolved to instantiated Sienna `ACBus` objects and wrapped in an `Arc`.

---

### Reference: Sienna ACBranch Type Hierarchy

For context (schema files are in `SiennaSchemas/Operations/Branch/`):

```
Branch (abstract)
└── ACBranch (abstract)
    └── ACTransmission (abstract)
        ├── Line                   ← primary translation target for PyPSA Line
        ├── MonitoredLine          ← Line + operator flow limits (see below)
        ├── TwoWindingTransformer  ← abstract supertype for transformer types
        │   ├── Transformer2W
        │   ├── TapTransformer
        │   ├── PhaseShiftingTransformer
        │   └── PhaseShiftingTransformer3W
    └── TwoTerminalHVDC (abstract)
        ├── TwoTerminalGenericHVDCLine
        ├── TwoTerminalLCCLine
        └── TwoTerminalVSCLine
    └── DiscreteControlledACBranch (switch/breaker)
```

**Translation target for PyPSA `Line`:** always `Line` (default) or `MonitoredLine` if the operator has applied more restrictive flow limits. There is no other plausible ACBranch target — transformer types require tap ratio data and HVDC types require converter-specific fields that PyPSA `Line` does not carry.

---

### Reference: Sienna `Line` Struct (from schema)

Source: `SiennaSchemas/Operations/Branch/Line.json` (commit `906001306e9d3063a8820e84fd2ca7f955bf455e`)

```json
{
  "id": 1,
  "name": "line_1_2",
  "available": true,
  "active_power_flow": 0.0,
  "reactive_power_flow": 0.0,
  "arc": 1,
  "r": 0.0098,
  "x": 0.0803,
  "b": { "from": 1.475, "to": 1.475 },
  "rating": 10.0,
  "angle_limits": { "min": -1.5708, "max": 1.5708 },
  "rating_b": null,
  "rating_c": null,
  "g": { "from": 0.0, "to": 0.0 }
}
```

Field notes: `arc` is the integer `id` of the `Arc` joining the from/to buses. `r`, `x`, `b`, `g` are per-unit on `SYSTEM_BASE` (`r`/`x` validated in `(0, 4)`); `b` and `g` are `{from, to}` pairs and default to `{from: 0.0, to: 0.0}`. `rating` is **per-unit on `SYSTEM_BASE`** — PowerSystems.jl `Line.jl` requires `rating` in pu of the system base power when a line is defined before attachment to a `System` (it multiplies by `base_power` on attachment to recover MVA), so the value emitted to JSON is `(s_nom * s_max_pu) / S_base`, not raw MVA. `rating_b`/`rating_c` are MVA and nullable (always `null` here). `angle_limits` is `{min, max}` in radians. `active_power_flow`/`reactive_power_flow` are MW/MVAR initial conditions.

---

### Reference: Sienna `MonitoredLine` Struct (from schema)

Source: `SiennaSchemas/Operations/Branch/MonitoredLine.json` (commit `906001306e9d3063a8820e84fd2ca7f955bf455e`)

`MonitoredLine` extends `Line` with one additional required field: `flow_limits`. Unlike `Line`, `b` is **required** in `MonitoredLine`.

`flow_limits` is a `{from_to, to_from}` pair in MVA (more restrictive than the thermal `rating`).

**When to use:** Only when the network data carries explicit operator-imposed flow limits that are more restrictive than `s_nom`. PyPSA `Line` has no native `flow_limits` concept, so `MonitoredLine` is **not the default translation target**. If the user supplies per-line flow constraints via override, translate to `MonitoredLine`; otherwise always use `Line`.

**Minimal valid JSON example (`MonitoredLine`):**

```json
{
  "id": 2,
  "name": "mon_line_1_2",
  "available": true,
  "active_power_flow": 0.0,
  "reactive_power_flow": 0.0,
  "arc": 1,
  "r": 0.0098,
  "x": 0.0803,
  "b": { "from": 1.475, "to": 1.475 },
  "flow_limits": { "from_to": 1000.0, "to_from": 1000.0 },
  "rating": 12.0,
  "angle_limits": { "min": -1.5708, "max": 1.5708 }
}
```

---

### Reference: PyPSA `Line` Input Attributes

Source: `pypsa/data/component_attrs/lines.csv`

**Input attributes (static on `n.lines`):**

| Attribute | Type | Unit | Default | Required | Description |
| --- | --- | --- | --- | --- | --- |
| `name` | string | — | — | yes | Unique line name (index) |
| `bus0` | string | — | — | yes | Origin bus name |
| `bus1` | string | — | — | yes | Destination bus name |
| `type` | string | — | `""` | no | Standard line type name. If non-empty, overrides `r`/`x`/`b` using type library × `length` / `num_parallel` |
| `x` | float | Ohm | 0 | yes | Series reactance |
| `r` | float | Ohm | 0 | yes | Series resistance |
| `b` | float | Siemens | 0 | no | Total shunt susceptance |
| `g` | float | Siemens | 0 | no | Total shunt conductance |
| `s_nom` | float | MVA | 0 | no | Apparent power rating (ignored if `s_nom_extendable`) |
| `s_max_pu` | float or series | pu | 1.0 | no | Max apparent flow as fraction of `s_nom` (dynamic line rating if time-varying) |
| `active` | bool | — | True | no | Whether component is included in optimisation |
| `length` | float | km | 0 | no | Physical length; used with `type` to compute impedance |
| `num_parallel` | float | — | 1 | no | Number of parallel circuits; used with `type` |
| `carrier` | string | — | `""` | no | Always `"AC"` for lines |
| `v_ang_min` | float | degrees | −∞ | no | Min voltage angle difference (placeholder; not enforced by PyPSA) |
| `v_ang_max` | float | degrees | +∞ | no | Max voltage angle difference (placeholder; not enforced by PyPSA) |
| `s_nom_extendable` | bool | — | False | no | Allow capacity expansion in optimisation |
| `s_nom_min` | float | MVA | 0 | no | Min `s_nom_opt` if extendable |
| `s_nom_max` | float | MVA | ∞ | no | Max `s_nom_opt` if extendable |
| `capital_cost` | float | currency/MVA | 0 | no | Annuitised investment cost per MVA |
| `build_year` | int | year | 0 | no | Asset build year |
| `lifetime` | float | years | ∞ | no | Asset lifetime |
| `terrain_factor` | float | pu | 1 | no | Multiplier on `length` for cost calculation |

**Output attributes (computed; do not set by hand):**

| Attribute | Description |
| --- | --- |
| `x_pu`, `r_pu`, `b_pu`, `g_pu` | Per-unit values on **1 MVA base**, computed by `n.calculate_dependent_values()` |
| `x_pu_eff`, `r_pu_eff` | Effective pu for linearised power flow |
| `sub_network` | Connected sub-network ID (from `n.determine_network_topology()`) |
| `s_nom_opt` | Optimised capacity (post-LOPF) |
| `p0`, `q0`, `p1`, `q1` | Power flows at each end (output only) |
| `mu_lower`, `mu_upper` | Shadow prices of capacity limits |

**Time-varying on `n.lines_t`:**

| Attribute | Description |
| --- | --- |
| `s_max_pu` | Dynamic line rating as fraction of `s_nom` (e.g. weather-dependent overhead line capacity) |
| `p0`, `q0`, `p1`, `q1` | Power flow time series (outputs only) |

---

### Per-Unit Conversion — Critical Detail

PyPSA and Sienna use different system bases for per-unit quantities on branches.

**PyPSA:** stores `r`, `x` in **Ohms** and `b`, `g` in **Siemens** (absolute physical units). When `n.calculate_dependent_values()` is called, it computes `r_pu` etc. using **1 MVA as the power base**:

```
z_base_pypsa = v_nom_kV² / 1.0   [Ohm]
r_pu_pypsa   = r_ohm / z_base_pypsa
b_pu_pypsa   = b_siemens × z_base_pypsa
```

**Sienna:** stores `r`, `x`, `b`, `g` in per-unit on the **system MVA base** (`SYSTEM_BASE`, typically 100 MVA):

```
z_base_sienna = v_nom_kV² / S_base_MVA   [Ohm]
r_sienna = r_ohm / z_base_sienna = r_ohm × S_base_MVA / v_nom_kV²
b_sienna = b_siemens × z_base_sienna     = b_siemens × v_nom_kV² / S_base_MVA
```

**Conversion formulas** (from PyPSA ohm/siemens to Sienna system-base pu):

```
r_sienna = r_ohm × S_base / v_nom_kV²
x_sienna = x_ohm × S_base / v_nom_kV²
b_sienna = b_siemens × v_nom_kV² / S_base          (total, before from/to split)
g_sienna = g_siemens × v_nom_kV² / S_base          (total, before from/to split)
```

If PyPSA pu values (`r_pu`, `x_pu` on 1-MVA base) are available post-`calculate_dependent_values()`:

```
r_sienna = r_pu_pypsa × S_base_MVA
x_sienna = x_pu_pypsa × S_base_MVA
b_sienna = b_pu_pypsa / S_base_MVA
g_sienna = g_pu_pypsa / S_base_MVA
```

**Verified:** `elec_s_70_ec_lv1.05_Co2L0.0-24H.nc` at 380 kV gives `r_ohm=14.15`, `x_ohm=116.0`, `b_S=0.00204`. With S_base=100 MVA: `r_sienna=0.0098 pu`, `x_sienna=0.0803 pu`, `b_sienna=2.95 pu` (total, then split 1.475 / 1.475 per end).

**Use `v_nom` of `bus0`.** Lines must connect two buses at the same voltage; validate before translation and warn on mismatch.

---

### Attribute Mapping Table: PyPSA `Line` → Sienna `Line`

| Sienna field | Type / unit | PyPSA source | Transform | Mapping type | Notes |
| --- | --- | --- | --- | --- | --- |
| `id` | `Int` | — | auto-assigned | **defaulted** | Auto-assigned by Sienna on ingestion |
| `name` | `String` | `n.lines.index` | direct | **direct** | Use the PyPSA line name string directly |
| `available` | `Bool` | `n.lines.active` | direct | **direct** | PyPSA `active` (bool, default `True`) → `available`. All lines active in sample files |
| `active_power_flow` | `Float64` (MW) | — | `0.0` | **defaulted** | PyPSA does not store initial branch flow as an input; `p0`/`p1` in `n.lines_t` are outputs |
| `reactive_power_flow` | `Float64` (MVAR) | — | `0.0` | **defaulted** | Same — Q flow outputs only |
| `arc` | `Arc` | `n.lines.bus0`, `n.lines.bus1` | look up ACBus by name → `Arc(from_bus, to_bus)` | **derived** | `bus0` → `from`, `bus1` → `to`. In the JSON schema, `Arc.from` and `Arc.to` are integer bus IDs; in the Julia API, pass ACBus objects. Requires the bus registry built in the bus translation step. |
| `r` | `Float64` (pu, SYSTEM_BASE) | `n.lines.r` (Ohm) | `r_ohm × S_base / v_nom_kV²` | **derived** | PyPSA stores in Ohms. Use bus `v_nom` (kV). Sienna validates `r ∈ (0, 4)` — flag if outside range |
| `x` | `Float64` (pu, SYSTEM_BASE) | `n.lines.x` (Ohm) | `x_ohm × S_base / v_nom_kV²` | **derived** | Same as `r`. Must be > 0 for linearised power flow; PyPSA requires this too |
| `b` | `FromTo` (pu, SYSTEM_BASE) | `n.lines.b` (Siemens) | `b_total_sienna = b_S × v_nom_kV² / S_base`; split equally: `(from=b_total/2, to=b_total/2)` | **derived** | Optional in schema; PyPSA `b` is the total shunt susceptance (π-model). Sienna splits per end. Default `(from=0.0, to=0.0)` when `b=0` |
| `rating` | `Float64` (pu, SYSTEM_BASE) | `n.lines.s_nom` (MVA), `n.lines.s_max_pu` (pu) | `(s_nom * s_max_pu) / S_base` | **derived** | PyPSA's effective AC line capacity is `s_nom * s_max_pu`. `s_max_pu` is a derating factor in `[0, 1]`; PyPSA-Eur applies a uniform `s_max_pu = 0.7` across all lines as an N-1 contingency margin. Ignoring `s_max_pu` causes Sienna to see every AC corridor as `1/s_max_pu` wider than PyPSA does, which lets cheaper imports replace expensive local generation. Stored in pu of `SYSTEM_BASE` (PowerSystems.jl multiplies by `base_power` on attachment to recover MVA). If `s_nom_extendable=True`, use `s_nom_opt` if available (post-LOPF); otherwise fall back to `s_nom`. See capacity expansion note. A line whose `s_max_pu` is a series in `n.lines_t` carries no static rating this field can hold, so that line is left out. |
| `angle_limits` | `MinMax` (radians) | `n.lines.v_ang_min`, `v_ang_max` (degrees) | convert degrees → radians; use `(min=-π/2, max=π/2)` when ±∞ | **defaulted** | PyPSA `v_ang_min`/`v_ang_max` are documented placeholders not enforced by PyPSA. In all sample files they are ±∞. Apply default `(min=-1.5708, max=1.5708)` (±90°). If a finite value is explicitly set by the user, map it: `radians = degrees × π/180` |
| `rating_b` | `Union{Nothing, Float64}` (MVA) | — | `nothing` | **defaulted** | No PyPSA equivalent for a second thermal rating |
| `rating_c` | `Union{Nothing, Float64}` (MVA) | — | `nothing` | **defaulted** | No PyPSA equivalent |
| `g` | `FromTo` (pu, SYSTEM_BASE) | `n.lines.g` (Siemens) | `g_total_sienna = g_S × v_nom_kV² / S_base`; split: `(from=g_total/2, to=g_total/2)` | **derived** | Same π-split as `b`. Default is `0.0` in PyPSA — most lines carry no shunt conductance |

**Extensions sidecar.** Line attributes with no SiennaSchemas field go in the `extensions.json` companion (see Component extensions), as a `line` record identified by `name`:

```json
{ "line": [ { "name": "line_1_2", "length": 120.0, "num_parallel": 1.0,
               "carrier": "AC", "s_nom_extendable": false } ] }
```

(`build_year` / `lifetime` are capacity-expansion vintage context — those belong with the `Investments/` mapping, not this generic bag.)

**Minimal valid JSON example (`Line`):**

```json
{
  "id": 1,
  "name": "line_1_2",
  "available": true,
  "active_power_flow": 0.0,
  "reactive_power_flow": 0.0,
  "arc": 1,
  "r": 0.0098,
  "x": 0.0803,
  "rating": 12.0,
  "angle_limits": { "min": -1.5708, "max": 1.5708 }
}
```

---

### Capacity Expansion Fields

PyPSA supports line capacity expansion via `s_nom_extendable`. Sienna `Line` does **not** have a native expansion mechanism — it models a fixed-rating branch.

| PyPSA field | Default | Notes |
| --- | --- | --- |
| `s_nom_extendable` | False | Expansion flag. **Both sample files have this set `True` for all lines.** |
| `s_nom_min` | 0 MVA | Lower bound on optimised capacity |
| `s_nom_max` | ∞ MVA | Upper bound on optimised capacity |
| `s_nom_opt` | 0 MVA | Optimised result (output; available in solved networks) |
| `capital_cost` | 0 | Annuitised investment cost per MVA |

**Recommended translator behaviour:**
1. If `s_nom_extendable=False`: use `s_nom` directly as `rating`.
2. If `s_nom_extendable=True` and `s_nom_opt > 0` (solved network): use `s_nom_opt` as `rating`.
3. If `s_nom_extendable=True` and `s_nom_opt = 0` (unsolved network): use `s_nom` as a fallback and log a warning — the nominal rating may be a lower bound, not the intended operating rating.
4. Store `s_nom_extendable`, `s_nom_min`, `s_nom_max`, `capital_cost` in `ext` for completeness.

---

### Time-Varying: `s_max_pu` (Dynamic Line Rating)

PyPSA allows `s_max_pu` to be time-varying in `n.lines_t`, representing dynamic line rating (DLR) — e.g. overhead line capacity varying with ambient temperature or wind. When present, the effective rating at time `t` is `s_nom × s_max_pu[t]`.

Sienna `Line` has a scalar `rating` field. There is no built-in time-varying rating mechanism on `Line` in the current PowerSystems.jl.

**v1 behaviour:** the static case (`n.lines_t["s_max_pu"]` empty) is fully supported; `rating = s_nom × s_max_pu / S_base` reproduces PyPSA's effective MVA limit and is what the translator emits. A line with a populated column in `n.lines_t["s_max_pu"]` is **left out**, with a `COMPONENT_SKIPPED` event and a warning: a static rating would misrepresent the dynamic envelope, and every other line still translates.

**Deferred follow-up:** for networks with DLR, the translator will need to emit a per-line `rate` time series and the pipeline will need to set a Line formulation that consumes it. PSI does not currently have a stock formulation for time-varying line ratings, so this likely involves a custom JuMP constraint after `build!`. Tracked as a separate ticket; not on the v1 critical path.

In both sample files `n.lines_t["s_max_pu"]` exists but has zero columns (not populated for any line), so no line is left out on current data.

---

### `Line.type` — Standard Library

When PyPSA `n.lines.type` is non-empty, PyPSA computes `r`, `x`, `b` as:

```
r = type.r_per_length × length / num_parallel   (Ohm)
x = type.x_per_length × length / num_parallel   (Ohm)
b = type.c_per_length × length × num_parallel × 2πf × 1e-9  (Siemens)
```

**After `n.calculate_dependent_values()`, the resulting ohm/siemens values are populated in `n.lines.r`, `n.lines.x`, `n.lines.b`** — so the translator can always read from those columns regardless of whether `type` is set. No special handling of the type library is needed.

Confirm: `elec_s_70` has non-empty `type` values; `solved_network` has empty `type`. Both have `r`, `x`, `b` populated in physical units after calling `calculate_dependent_values()`.

---

### Open Questions

1. **System MVA base agreement.** The impedance conversion formula uses `S_base_MVA` (Sienna’s system base). This must match the value passed as `base_power` when constructing the `System`. The existing `PyPSA2PowerSystems.jl` uses `100.0 MVA` as system base — confirm this is the expected convention for the BTE translator before implementing.
2. **`angle_limits` default.** The proposed default of `±π/2` (±90°) is a common planning convention for AC lines but can be overly tight on meshed networks. Some tools use `±π` (±180°, i.e. unconstrained) or `±60°`. Confirm the default with the BTE PowerSimulations.jl workflow — incorrect angle limits can make OPF infeasible. The reverse direction is documented in [Translation from Sienna to PyPSA](./translation-from-sienna-to-pypsa.md).
3. **`b` split asymmetry.** The translator splits total shunt susceptance equally between from and to ends. This is the standard π-model assumption. If the line `type` library provides asymmetric split (unusual), this approximation loses accuracy. Acceptable for v1.
4. **`s_nom = 0` lines.** PyPSA default `s_nom = 0` means no rating was specified. Sienna `Line.rating = 0` is technically valid but would constrain all flow to zero. Translator should warn when `s_nom = 0` and either substitute a very large default (representing unconstrained) or raise a hard error requiring user input.
5. **`v_nom` mismatch detection.** PyPSA Lines are AC branches connecting two buses at the same voltage level. If `bus0.v_nom ≠ bus1.v_nom`, it may indicate a transformer that was modelled as a Line (incorrect) or a data error. The translator should check this and warn or refuse to translate mismatched-voltage Lines.
6. **`rating` validation.** Sienna validates `r ∈ (0, 4)` and `x ∈ (0, 4)` on system base. After conversion, if a line has very small or very large impedance relative to the system base (e.g. short, low-voltage line in a high-base system), it may fail validation. Add a pre-check and log any out-of-range values before calling the constructor.
7. **`MonitoredLine` trigger.** There is currently no PyPSA field that maps to `flow_limits`. If the BTE workflow uses `MonitoredLine` for N-1 contingency constraints, these limits must be supplied as user overrides. Define an override mechanism (e.g. a CSV sidecar or a config dict) that the translator checks before choosing between `Line` and `MonitoredLine`.
8. **`Arc` collection.** An `Arc` is its own typed object (`{id, from, to}`) in the `Arc` list, referenced by a branch's integer `arc`. Decide whether a single `Arc` is shared between branches on the same bus pair or emitted one-per-branch, and assign `Arc` `id`s before the branches that reference them.

---

### Observation: Lines in Breakthrough Sample Files

Five sample `.nc` networks were checked:

| File | Lines | Links | Notes |
| --- | --- | --- | --- |
| `elec_s_70_ec_lv1.05_Co2L0.0-24H.nc` | **116** | 46 | PyPSA-EUR Breakthrough-style network; all at 380 kV |
| `solved_network.nc` | **105** | 0 | Pure AC network; buses at 138 kV |
| `network.nc` | 0 | 128 | Links only — no Lines |
| `APG_2023_2050_6Aug.nc` | 0 | 520 | Links only |
| `ac-dc-meshed.nc` (PyPSA example) | **7** | 4 | Mixed AC/DC test case |

**Key observations:**
- The two Breakthrough-format files both contain Lines and require this mapping.
- A network may contain no Lines at all, representing every transmission branch as a `Link` with `efficiency=1`.
- The `elec_s_70` file has `s_nom_extendable=True` for all 116 lines — the network is from a capacity expansion run. The translator must handle the `s_nom_opt` fallback described above.
- `v_ang_min`/`v_ang_max` are ±∞ in all files tested — the angle limit default will always apply in practice.
- `s_max_pu` time series exists in `n.lines_t` but has zero columns in all tested files (not actively used).

---

### Cross-Cutting Issues

#### Bus lookup and Arc construction

A line connects buses through an `Arc`, whose `from`/`to` are integer bus `id`s. Build a name→`id` map during bus translation, resolve `line.bus0`/`line.bus1` to those `id`s, emit one `Arc` per bus pair, and set the line's `arc` to that `Arc`'s `id`.

```json
{ "id": 1, "from": 1, "to": 2 }
```

If `bus0` or `bus1` refers to a non-electricity bus excluded during bus filtering, exclude the line too, with a warning.

#### Id-assignment order

References resolve by `id`, so the lists are unordered; assign `id`s so referenced components exist first: `Area`/`LoadZone` → `ACBus` → `Arc` → `Line`/`MonitoredLine` → generators and loads.

#### Relationship between `Line` and `Link` in the translator

PyPSA uses two fundamentally different components for transmission:

- **`Line`**: AC branch with physical impedance (r, x, b, g). Participation in power flow is determined by Kirchhoff’s laws. Cannot set an explicit flow direction or efficiency.
- **`Link`**: Controllable branch with explicit power flow direction (`bus0` → `bus1`) and configurable `efficiency`. No impedance parameters. Used in PyPSA for HVDC connections, and in some networks for all AC transmission as well (Links with `efficiency=1` approximate a lossless DC power flow).

**Both represent transmission but through different physics.** The translator must handle them independently:
- `Line` → `Line` (or `MonitoredLine`), using the impedance-based mapping in this document.
- `Link` → see the PyPSA `Link` → Sienna `TwoTerminalGenericHVDCLine` section below (typically `TwoTerminalGenericHVDCLine` for HVDC, or a special approximation where a network carries its AC transmission as Links).

A source PyPSA network may contain both (as in `elec_s_70`, which has 116 Lines and 46 Links). The translator must process both components and not conflate them.

#### Time-series handling

PyPSA `n.lines_t` currently carries only `s_max_pu` as a potentially time-varying input (the rest are outputs). For v1, a line whose `s_max_pu` is a series is left out and every other line takes its scalar `s_max_pu`. No `SingleTimeSeries` attachment to Sienna `Line` is needed unless DLR support is explicitly required.

---

### PyPSA Line Attributes with No Sienna Home

| PyPSA attribute | Disposition |
| --- | --- |
| `length` | Store in `ext["length_km"]`. No Sienna `Line` field. |
| `type` | Standard line type name. Store in `ext["type"]`. After `calculate_dependent_values()`, all impedance info is in `r`/`x`/`b`. |
| `num_parallel` | Number of parallel circuits. Store in `ext["num_parallel"]`. |
| `terrain_factor` | Cost calculation multiplier. Store in `ext["terrain_factor"]`. |
| `carrier` | Always `"AC"` for Lines. Store in `ext["carrier"]` for traceability. |
| `build_year`, `lifetime` | Asset management — not operational. Store in `ext`. |
| `capital_cost`, `overnight_cost`, `discount_rate`, `fom_cost` | Investment costs — not operational Sienna fields. Store in `ext` if present. |
| `s_nom_extendable`, `s_nom_min`, `s_nom_max`, `s_nom_set` | Expansion planning — no Sienna `Line` equivalent. Store in `ext`. |
| `sub_network` | Computed topology output. Store in `ext["sub_network"]`. |
| `v_ang_min`, `v_ang_max` | Mapped to `angle_limits` (with default when ±∞). Originals stored in `ext` for auditability. |
| `rating_b`, `rating_c` | Defaulted to `nothing` — no PyPSA source. N/A. |
| `p0`, `q0`, `p1`, `q1` | Power flow outputs — not Sienna inputs. Discard. |
| `mu_lower`, `mu_upper` | Optimisation shadow prices — not Sienna inputs. Discard. |
| `s_nom_opt` | Used as `rating` fallback for extendable lines in solved networks. Not stored separately. |

## PyPSA `Link` → Sienna `TwoTerminalGenericHVDCLine` Attribute Mapping

Source verification:
- `SiennaSchemas/Operations/Branch/TwoTerminalGenericHVDCLine.json` (commit `906001306e9d3063a8820e84fd2ca7f955bf455e`)
- `pypsa/.venv/lib/python3.14/site-packages/pypsa/data/component_attrs/links.csv` (PyPSA schema)
- Sample networks: `PyPSA2PowerSystems.jl/data/elec_s_70.nc`, `network.nc`, `PyPSA-EUR/networks/`, `ac-dc-meshed`

### Summary

A PyPSA `Link` represents a controllable directed power flow branch with no physical impedance: power flows from `bus0` to `bus1` at a specified efficiency, under explicit min/max dispatch bounds. It carries no AC physics. Sienna’s `TwoTerminalGenericHVDCLine` is the correct translation target: it models a two-terminal DC link with active power limits and an optional loss model, connecting two `ACBus` nodes.

**Key translation decisions:**
1. **Scope filter (v1):** Only Links where both `bus0` and `bus1` connect to AC or DC electricity buses are translated. Links involving non-electricity carriers (H₂, gas, heat) are deferred. In all tested sample files, cross-carrier Links do not appear.
2. **Efficiency → loss:** PyPSA `efficiency ∈ (0, 1]` maps to Sienna `loss = InputOutputCurve(LinearFunctionData(proportional_term=1-efficiency, constant_term=0.0))`. Efficiency=1.0 (lossless) → proportional_term=0.0. Efficiency=0.97 → proportional_term=0.03.
3. **Directionality:** PyPSA `p_min_pu` determines bidirectionality. `p_min_pu = 0` (the PyPSA default) → unidirectional; `p_min_pu = -1` (Breakthrough/elec_s_70) → bidirectional. The `active_power_limits_from.min` reflects this.
4. **No impedance conversion needed:** Links have no `r`/`x`/`b`/`g`; all power limits are in MW.
5. **Multi-port Links (bus2, bus3, …)** are out of scope for v1. No tested sample file uses them.

---

### Reference: Sienna TwoTerminalHVDC Type Hierarchy

For context (schema files are in `SiennaSchemas/Operations/Branch/`):

```
Branch (abstract)
└── ACBranch (abstract)
    └── TwoTerminalHVDC (abstract)
        ├── TwoTerminalGenericHVDCLine   ← primary translation target
        ├── TwoTerminalLCCLine           ← LCC thyristor HVDC — not used
        └── TwoTerminalVSCLine           ← VSC converter HVDC — not used
```

**Why `TwoTerminalGenericHVDCLine` and not VSC/LCC:**
- `TwoTerminalVSCLine` has 30+ fields for VSC converter controls (DC voltage setpoints, AC control modes, reactive power droop, filter parameters). PyPSA `Link` carries none of this; forcing the mapping would require fabricating dozens of parameters.
- `TwoTerminalLCCLine` is specific to thyristor-based LCC converters with commutation reactance and firing angle fields. Not appropriate for a generic controllable Link.
- `TwoTerminalGenericHVDCLine` has exactly the fields a PyPSA Link provides: power limits, loss model, and bus connectivity. It is the intended “catch-all” HVDC type for simplified operational modeling.

---

### Reference: Sienna `TwoTerminalGenericHVDCLine` Struct (from schema)

Source: `SiennaSchemas/Operations/Branch/TwoTerminalGenericHVDCLine.json` (commit `906001306e9d3063a8820e84fd2ca7f955bf455e`)

```json
{
  "id": 1,
  "name": "hvdc_1_2",
  "available": true,
  "active_power_flow": 0.0,
  "arc": 1,
  "active_power_limits_from": { "min": -2500.0, "max": 2500.0 },
  "active_power_limits_to": { "min": -2500.0, "max": 2500.0 },
  "reactive_power_limits_from": { "min": 0.0, "max": 0.0 },
  "reactive_power_limits_to": { "min": 0.0, "max": 0.0 },
  "loss": {
    "curve_type": "INPUT_OUTPUT",
    "function_data": { "function_type": "LINEAR", "proportional_term": 0.03, "constant_term": 0.0 },
    "input_at_zero": null
  }
}
```

Field notes: `arc` is the integer `id` of the `Arc` joining the from/to buses. `active_power_limits_*` / `reactive_power_limits_*` are `{min, max}` pairs in MW / MVAR. `loss` is a `TwoTerminalLoss` (here an `InputOutputCurve`): a linear loss of `proportional_term` MW per MW of flow, i.e. `1 - efficiency` (so `efficiency = 0.97` → `0.03`). `loss` is optional — a lossless link omits it or sets `proportional_term: 0.0`.

---

### Reference: PyPSA `Link` Input Attributes

Source: `pypsa/data/component_attrs/links.csv`

**Static input attributes (on `n.links`):**

| Attribute | Type | Unit | Default | Required | Description |
| --- | --- | --- | --- | --- | --- |
| `name` | string | — | — | yes | Unique link name (index) |
| `bus0` | string | — | — | yes | Origin bus name |
| `bus1` | string | — | — | yes | Destination bus name |
| `bus2`..`bus4` | string | — | `""` | no | Additional port buses (multi-port; v1 out of scope) |
| `carrier` | string | — | `""` | no | Energy carrier (e.g. `"DC"`, `"interconnector-GBR-FRA"`) |
| `active` | bool | — | True | no | Whether included in optimisation |
| `p_nom` | float | MW | 0 | no | Nominal power capacity (from-end) |
| `p_nom_extendable` | bool | — | False | no | Allow capacity expansion in optimisation |
| `p_nom_min` | float | MW | 0 | no | Min `p_nom_opt` if extendable |
| `p_nom_max` | float | MW | +∞ | no | Max `p_nom_opt` if extendable |
| `p_nom_opt` | float | MW | 0 | no | Optimised capacity (written after solve) |
| `p_min_pu` | float or series | pu | 0 | no | Min dispatch as fraction of `p_nom`. Negative → bidirectional |
| `p_max_pu` | float or series | pu | 1 | no | Max dispatch as fraction of `p_nom` |
| `p_set` | float | MW | 0 | no | Active power setpoint (fixed-dispatch non-optimised links) |
| `efficiency` | float or series | pu | 1 | no | Fraction of power at bus0 that arrives at bus1 |
| `efficiency2`..`4` | float or series | pu | 1 | no | Efficiency for additional ports (multi-port; v1 out of scope) |
| `marginal_cost` | float or series | currency/MWh | 0 | no | Dispatch cost per MWh at bus0 |
| `capital_cost` | float | currency/MW | 0 | no | Investment cost per MW added (if extendable) |
| `build_year` | int | year | 0 | no | Year of commissioning |
| `lifetime` | float | years | +∞ | no | Component lifetime |
| `length` | float | km | 0 | no | Physical length (informational) |
| `terrain_factor` | float | — | 1 | no | Terrain multiplier for cost scaling |
| `ramp_limit_up` | float | pu/h | NaN | no | Upward ramp rate limit |
| `ramp_limit_down` | float | pu/h | NaN | no | Downward ramp rate limit |
| `ramp_limit_start_up` | float | pu | 1 | no | Ramp limit at startup |
| `ramp_limit_shut_down` | float | pu | 1 | no | Ramp limit at shutdown |

**Time-varying attributes (on `n.links_t`):**

| Attribute | Description |
| --- | --- |
| `p_min_pu` | Time-varying min dispatch fraction |
| `p_max_pu` | Time-varying max dispatch fraction |
| `efficiency` | Time-varying efficiency (e.g. seasonal variation) |
| `marginal_cost` | Time-varying dispatch cost |
| `ramp_limit_up` | Time-varying ramp limit |
| `ramp_limit_down` | Time-varying ramp limit |

---

### Scope Filtering

**v1 filter: electricity-only Links.**

A Link is in scope if and only if both endpoint buses are electricity buses. Check:

```python
def is_electricity_bus(n, bus_name):
    if bus_name not in n.buses.index:
        return False
    carrier = n.buses.loc[bus_name, "carrier"]
    return carrier in {"AC", "DC", ""}  # empty string = AC by convention


def link_in_scope(n, link_name):
    link = n.links.loc[link_name]
    return (
        is_electricity_bus(n, link.bus0)
        and is_electricity_bus(n, link.bus1)
        and link.get("bus2", "") == ""  # no multi-port
        and link.get("bus3", "") == ""
    )
```

**Multi-port Links** (bus2/bus3/bus4 non-empty) are unconditionally deferred regardless of carrier, because PowerSystems.jl has no equivalent multi-port branch type.

In all tested sample files, every Link passes the electricity filter. Cross-carrier Links (H₂, gas, heat endpoints) are hypothetically possible in a Links-only network but do not appear in current test data.

---

### Attribute Mapping Table: PyPSA `Link` → `TwoTerminalGenericHVDCLine`

| PyPSA attribute | Sienna field | Rule | Notes |
| --- | --- | --- | --- |
| — | `id` | Auto-assigned | Do not set; Sienna assigns on ingestion |
| `name` | `name` | Direct copy | No transformation needed |
| `active` | `available` | Direct copy (bool) | PyPSA `active=True` → `available=true` |
| — | `active_power_flow` | Set to `0.0` | PyPSA has `p0`/`p1` result fields, not an initial condition; initialise to 0 |
| `bus0` | `arc` (from) | resolve name → bus `id` | `arc` is the integer `id` of an `Arc` whose `from`/`to` are the bus `id`s of `bus0`/`bus1` |
| `bus1` | `arc` (to) | Name lookup → `ACBus` | Same Arc; both buses must already exist in the system |
| `p_nom × p_min_pu` | `active_power_limits_from.min` | Multiply; see directionality | If `p_min_pu ≥ 0`: min = 0.0. If `p_min_pu < 0`: min = `p_nom × p_min_pu` (negative MW) |
| `p_nom × p_max_pu` | `active_power_limits_from.max` | Multiply | `p_nom × p_max_pu` (MW); use `p_nom_opt` if available after solve |
| `p_nom × p_min_pu × efficiency` | `active_power_limits_to.min` | Multiply + efficiency | For bidirectional: min = `p_nom × p_min_pu × efficiency` |
| `p_nom × p_max_pu × efficiency` | `active_power_limits_to.max` | Multiply + efficiency | `p_nom × p_max_pu × efficiency` (MW arriving at bus1) |
| — | `reactive_power_limits_from` | Set to `(min=0.0, max=0.0)` | PyPSA Links carry no reactive power; DC assumption |
| — | `reactive_power_limits_to` | Set to `(min=0.0, max=0.0)` | Same |
| `efficiency` | `loss` | `InputOutputCurve(LinearFunctionData(proportional_term=1-efficiency, constant_term=0.0))` | efficiency=1.0 → proportional_term=0.0; efficiency=0.97 → proportional_term=0.03 |
| `marginal_cost` | `ext["marginal_cost"]` | Store in ext | No native Sienna field; preserve for downstream use |
| `capital_cost` | `ext["capital_cost"]` | Store in ext | For capacity expansion context |
| `p_nom_extendable` | `ext["p_nom_extendable"]` | Store in ext | Sienna has no native expansion mechanism (see below) |
| `p_nom_min` | `ext["p_nom_min"]` | Store in ext | Only meaningful if `p_nom_extendable=true` |
| `p_nom_max` | `ext["p_nom_max"]` | Store in ext | Only meaningful if `p_nom_extendable=true` |
| `p_nom_opt` | `ext["p_nom_opt"]` | Store in ext | Write-back field from solver; preserve if present |
| `carrier` | `ext["carrier"]` | Store in ext | Useful for debugging and round-trip reconstruction |
| `build_year` | `ext["build_year"]` | Store in ext | Relevant for multi-period or vintage-based analysis |
| `lifetime` | `ext["lifetime"]` | Store in ext | As above |
| `length` | `ext["length"]` | Store in ext | Informational; no Sienna equivalent |
| `bus2`..`bus4` | DEFER | Skip if non-empty | Multi-port Links are not translatable in v1 |
| `ramp_limit_up` | — | No mapping | `TwoTerminalGenericHVDCLine` has no ramp rate field |
| `ramp_limit_down` | — | No mapping | Same |
| `p_set` | — | No mapping | Setpoint-based dispatch is not a Sienna concept for this type |

**Minimal valid JSON example (`TwoTerminalGenericHVDCLine`):**

```json
{
  "id": 1,
  "name": "hvdc_GB_FR",
  "available": true,
  "active_power_flow": 0.0,
  "arc": 2,
  "active_power_limits_from": { "min": 0.0, "max": 2000.0 },
  "active_power_limits_to": { "min": 0.0, "max": 1940.0 },
  "reactive_power_limits_from": { "min": 0.0, "max": 0.0 },
  "reactive_power_limits_to": { "min": 0.0, "max": 0.0 }
}
```

---

### Directionality and Bidirectionality

PyPSA Links are inherently directed: power flows from `bus0` toward `bus1`. Whether the flow can reverse depends on `p_min_pu`:

| `p_min_pu` value | Interpretation | `active_power_limits_from` | Example source |
| --- | --- | --- | --- |
| `0.0` (default) | Unidirectional — no reverse flow | `(min=0.0, max=p_nom)` | `network.nc`, APG |
| `-1.0` | Fully bidirectional — can flow either way | `(min=-p_nom, max=p_nom)` | Breakthrough elec_s_70, ac-dc-meshed |
| `-0.9` | Bidirectional but asymmetric | `(min=-0.9×p_nom, max=p_nom)` | ac-dc-meshed |

Sienna `TwoTerminalGenericHVDCLine.active_power_limits_from` accepts negative min values to represent reverse flow capability. The convention is:
- Positive flow = from bus0 to bus1 (consistent with PyPSA convention)
- Negative flow = from bus1 to bus0 (reverse)

**For `active_power_limits_to`:** The to-end limits reflect what arrives at `bus1` after losses:
- `max = p_nom × p_max_pu × efficiency`
- `min = p_nom × p_min_pu × efficiency` (negative if bidirectional)

This preserves the physics that arriving power is less than (or equal to, if lossless) sent power.

---

### Efficiency and Loss Model

PyPSA `efficiency` is a per-unit fraction: `p1 = efficiency × |p0|`. The inverse is `1 - efficiency` = fractional loss.

Sienna `TwoTerminalGenericHVDCLine.loss` is typed `TwoTerminalLoss` (`InputOutputCurve | IncrementalCurve`). Use `InputOutputCurve(LinearFunctionData(proportional_term, constant_term=0.0))` where `proportional_term` is MW of loss per MW of flow.

**Mapping:**

```
loss = InputOutputCurve(LinearFunctionData(proportional_term = 1.0 - efficiency, constant_term = 0.0))
```

| PyPSA `efficiency` | Sienna `loss` | Meaning |
| --- | --- | --- |
| `1.0` (lossless) | `InputOutputCurve(LinearFunctionData(proportional_term=0.0, constant_term=0.0))` | No losses |
| `0.97` | `InputOutputCurve(LinearFunctionData(proportional_term=0.03, constant_term=0.0))` | 3% proportional loss |
| `0.95` | `InputOutputCurve(LinearFunctionData(proportional_term=0.05, constant_term=0.0))` | 5% proportional loss |

**Time-varying efficiency:** If `efficiency` appears in `n.links_t`, it varies per timestep. The `TwoTerminalLoss` (`InputOutputCurve`) is static — time-varying efficiency cannot be represented natively. For v1, use the static `efficiency` column value. If the time-varying series is present, store a flag in `ext["has_time_varying_efficiency"] = true` so downstream systems are aware.

**Constant loss component:** PyPSA `efficiency` implies only proportional loss. If a constant loss term (e.g. no-load station consumption) is needed, it must be added outside of PyPSA’s standard Link model.

---

### Capacity Expansion Handling

PyPSA supports capacity expansion via `p_nom_extendable=True` with bounds `[p_nom_min, p_nom_max]` and `capital_cost`. Sienna `TwoTerminalGenericHVDCLine` has no native expansion mechanism.

**v1 approach:**

1. If `p_nom_extendable=False`: use `p_nom` directly for power limits.
2. If `p_nom_extendable=True` and `p_nom_opt > 0` (post-solve): use `p_nom_opt` as the effective capacity — the optimiser has already determined the installed size.
3. If `p_nom_extendable=True` and `p_nom_opt = 0` or absent (pre-solve): use `p_nom` as a fallback lower bound. Store all expansion metadata in `ext`.

```python
def get_effective_p_nom(link):
    if link.p_nom_extendable and link.p_nom_opt > 0:
        return link.p_nom_opt
    return link.p_nom
```

In all tested sample files, `p_nom_extendable=True` is common (every link in `network.nc` and in the Breakthrough-format files). Post-solve `p_nom_opt` is typically available in solved networks; use it when present.

---

### Time-Varying Dispatch Limits

PyPSA allows `p_min_pu` and `p_max_pu` to be time series (in `n.links_t`). When present, they override the static values per timestep.

Sienna `TwoTerminalGenericHVDCLine` stores fixed `active_power_limits_from/to` — no native time-varying limits. For v1:
- Use the static `p_min_pu`/`p_max_pu` columns for power limit construction.
- If time-varying versions exist in `n.links_t`, store a flag in `ext["has_time_varying_p_min_pu"]` / `ext["has_time_varying_p_max_pu"]`.
- Do not attempt to attach `TimeSeriesData` to the power limits field; Sienna does not support this.

---

### Sample File Observations

#### `PyPSA2PowerSystems.jl/data/elec_s_70.nc`

- **46 links** total; all pass electricity filter
- `carrier = "DC"` on all Links; all endpoint buses are AC carriers
- `p_min_pu = -1.0` → fully bidirectional
- `efficiency = 1.0` → `InputOutputCurve(LinearFunctionData(proportional_term=0.0, ...))` (no losses)
- `p_nom_extendable = True` on all; `p_nom_opt` values present (post-solve network)
- No `bus2`/`bus3` in any row
- Typical `p_nom` range: 100–1000 MW

#### `network.nc`

- **128 links** total; all pass electricity filter
- `carrier` values: `"interconnector-GBR-FRA"`, `"interconnector-GBR-IRL"`, etc.
- `p_min_pu = 0.0` → unidirectional
- `efficiency = 0.97` → `InputOutputCurve(LinearFunctionData(proportional_term=0.03, ...))`
- `p_nom_extendable = True` on all
- No `bus2`/`bus3`

#### APG network

- **520 links**; same structure as `network.nc`
- `p_min_pu = 0.0`, `efficiency = 0.97`, unidirectional
- All electricity-to-electricity

#### `PyPSA-EUR/networks/ac-dc-meshed.nc`

- **4 links**; all electricity filter pass
- `p_min_pu = -0.9` → asymmetrically bidirectional
- `efficiency = 1.0` → lossless
- `carrier = "DC"`
- Demonstrates that `p_min_pu` is not always exactly -1 or 0

#### `solved_network.nc`

- **0 links** in tested file

---

### Complete Translation Examples

#### Unidirectional Link (efficiency=0.97)

PyPSA input:

```python
link.name = "interconnector-GBR-FRA"
link.bus0 = "GB"
link.bus1 = "FR"
link.p_nom = 2000.0  # MW
link.p_min_pu = 0.0
link.p_max_pu = 1.0
link.efficiency = 0.97
link.p_nom_extendable = True
link.p_nom_opt = 2500.0  # MW (post-solve)
```

Sienna (SiennaSchemas JSON):

```json
{
  "id": 1,
  "name": "interconnector-GBR-FRA",
  "available": true,
  "active_power_flow": 0.0,
  "arc": 1,
  "active_power_limits_from": { "min": 0.0, "max": 2500.0 },
  "active_power_limits_to": { "min": 0.0, "max": 2425.0 },
  "reactive_power_limits_from": { "min": 0.0, "max": 0.0 },
  "reactive_power_limits_to": { "min": 0.0, "max": 0.0 },
  "loss": {
    "curve_type": "INPUT_OUTPUT",
    "function_data": { "function_type": "LINEAR", "proportional_term": 0.03, "constant_term": 0.0 },
    "input_at_zero": null
  }
}
```

Capacity uses `p_nom_opt` (2500 MW). `arc` is the integer `id` of the `Arc` (GB→FR). `active_power_limits_to.max = 2500 × 0.97 = 2425`. `loss.proportional_term = 1 − efficiency = 0.03`.

#### Bidirectional elec_s_70 HVDC Link (efficiency=1.0)

PyPSA input:

```python
link.name = "DC line 1"
link.bus0 = "1"
link.bus1 = "2"
link.p_nom = 600.0
link.p_min_pu = -1.0
link.p_max_pu = 1.0
link.efficiency = 1.0
link.p_nom_extendable = True
link.p_nom_opt = 720.0
```

Sienna (SiennaSchemas JSON):

```json
{
  "id": 2,
  "name": "DC line 1",
  "available": true,
  "active_power_flow": 0.0,
  "arc": 2,
  "active_power_limits_from": { "min": -720.0, "max": 720.0 },
  "active_power_limits_to": { "min": -720.0, "max": 720.0 },
  "reactive_power_limits_from": { "min": 0.0, "max": 0.0 },
  "reactive_power_limits_to": { "min": 0.0, "max": 0.0 },
  "loss": {
    "curve_type": "INPUT_OUTPUT",
    "function_data": { "function_type": "LINEAR", "proportional_term": 0.0, "constant_term": 0.0 },
    "input_at_zero": null
  }
}
```

Capacity uses `p_nom_opt` (720 MW). Bidirectional, so `active_power_limits_*.min = -720`. `efficiency = 1.0` → `loss.proportional_term = 0.0` (lossless).

---

### Deferred Items

These PyPSA `Link` features are explicitly out of scope for v1 translation:

| Item | Reason | Suggested future approach |
| --- | --- | --- |
| **Cross-carrier Links** (bus0/bus1 on non-electricity carriers) | No Sienna equivalent for multi-energy network branches | Define custom extension types or store as `ext`-only objects |
| **Multi-port Links** (bus2, bus3, bus4) | `TwoTerminalGenericHVDCLine` is two-port only | Split into N pairwise Links as an approximation, or introduce a new Sienna component |
| **Time-varying efficiency** (`n.links_t.efficiency`) | `TwoTerminalLoss` (`InputOutputCurve`) is static | v1 uses the static `loss`; record a `has_time_varying_efficiency` flag in the `ext` sidecar |
| **Time-varying p_min_pu / p_max_pu** | Power limits are static in `TwoTerminalGenericHVDCLine` | v1 uses static limits; record a `has_time_varying_p_min_pu`/`_max_pu` flag in the `ext` sidecar |
| **Ramp limits** (`ramp_limit_up/down`) | No field in `TwoTerminalGenericHVDCLine` | Store in `ext`; ignored by Sienna operations |
| **`TwoTerminalVSCLine`** | 30+ VSC-specific fields; PyPSA `Link` provides none | Only use if source data explicitly encodes VSC converter parameters |
| **`TwoTerminalLCCLine`** | LCC thyristor-specific; not appropriate for generic Links | Only use if source data explicitly encodes LCC converter parameters |

---

### Open Questions

1. **`active_power_limits_to` with bidirectional + losses:** For a bidirectional Link with `efficiency < 1.0`, the loss applies asymmetrically depending on flow direction. Current mapping applies `efficiency` uniformly to both ends. Is this the correct Sienna interpretation of `TwoTerminalLoss` (`InputOutputCurve`) for reverse flow?
2. **`p_set` Links:** Some PyPSA networks use non-extendable, non-optimised Links with `p_set` (fixed dispatch). These represent must-run injections. Should they translate to a `TwoTerminalGenericHVDCLine` with `active_power_limits_from = active_power_limits_to = (min=p_set, max=p_set)`, or should they be represented differently?
3. **Bus carrier `"DC"`:** In Breakthrough-style networks, Links connect AC buses but carry carrier `"DC"`. The endpoint buses themselves have carrier `"AC"`. The `is_electricity_bus` filter accepts AC, DC, and empty — but what if there are pure DC bus nodes (`DCBus` in Sienna) that should connect to DC branches instead? Needs clarification on when `ACBus` vs `DCBus` is appropriate.
4. **`p_nom = 0` and `p_nom_opt = 0`:** A Link with both values at zero produces a `TwoTerminalGenericHVDCLine` with `active_power_limits_from = (min=0.0, max=0.0)` — effectively non-functional. Should such Links be skipped or included as available=false?
5. **Round-trip reconstruction:** When reconstructing PyPSA from Sienna, `efficiency` must be recovered from `1 - loss.proportional_term` (where `loss` is an `InputOutputCurve`). Is the `ext["carrier"]` field sufficient to reconstruct a PyPSA Link correctly, or do we need to also preserve `p_min_pu`/`p_max_pu` explicitly in `ext`?
6. **`marginal_cost` in `ext`:** PowerSimulations.jl uses `OperationalCost` subtypes for dispatch cost. Should `marginal_cost` be written into a `ThermalGenerationCost`like wrapper attached to the component, or is `ext` the right home for v1?

---

### PyPSA Link Attributes with No Sienna Home

These attributes are not mapped and not stored in `ext` (low value for operational simulation):

| Attribute | Reason dropped |
| --- | --- |
| `terrain_factor` | Cost scaling factor — only relevant for investment planning |
| `ramp_limit_start_up` / `ramp_limit_shut_down` | Startup/shutdown ramp — not applicable to DC link model |
| `p0`/`p1` (result fields) | Solver outputs, not inputs; use for `active_power_flow` initialization if available |
| `mu_lower` / `mu_upper` (dual variables) | Optimisation duals — not translatable |

## Deferred — Multi-carrier and non-electricity content

The scope-cleanup pass that produced this document removed multi-carrier content from the main mapping flow. Most of that content did not need to be preserved here because the removed fields / types weren't in the SiennaSchemas schema either — they simply don't exist as Sienna concepts. Only items that had a Sienna type or enum value but were excluded by scope (e.g. `ammonia`) are preserved below.

*This content was removed from the main translation flow as part of a v1 scope decision to target electricity-only networks. Nothing has been deleted — it is preserved here for a future iteration that extends support to multi-carrier and sector-coupled PyPSA networks.*

### Carrier: `ammonia`

**Why deferred:** `AMMONIA` is not a value in Sienna's `ThermalFuels` enum, and ammonia generators in PyPSA networks arise primarily in sector-coupling contexts (e.g. ammonia co-firing, green ammonia from electrolysis). No clean mapping exists in the electricity-only scope. Requires a team decision when multi-carrier support is added.

| PyPSA carrier | Sienna concrete type | Sienna `ThermalFuels` | Sienna `PrimeMovers` | Mapping type | Notes |
| --- | --- | --- | --- | --- | --- |
| **Ammonia** |  |  |  |  |  |
| `ammonia` | — | — | — | unsupported | **No mapping possible.** `AMMONIA` is not in `ThermalFuels`. Requires team decision |

---

## PyPSA `Load` → Sienna `PowerLoad` Attribute Mapping

Source verification:

- `SiennaSchemas/Operations/StaticInjection/PowerLoad.json` (commit `906001306e9d3063a8820e84fd2ca7f955bf455e`)
- `pypsa/.venv/lib/python3.14/site-packages/pypsa/data/component_attrs/loads.csv` (PyPSA schema)
- Sample networks: `PyPSA2PowerSystems.jl/data/` and `pypsa/data/`

### Summary

A PyPSA `Load` is a simple demand component: it draws active power (`p_set`) and optionally reactive power (`q_set`) from an attached bus. It carries no voltage-dependency model, no impedance, and no operational cost for curtailment. Sienna's `PowerLoad` is the direct counterpart: a static load with `active_power`/`reactive_power` as initial-condition scalars and `max_active_power`/`max_reactive_power` as capacity ceilings used in operational simulations.

**Key translation decisions:**

1. **Default target:** `PowerLoad`. It matches PyPSA Load's information content exactly: fixed demand with no ZIP model, no demand-response cost. `StandardLoad` (ZIP) and `ExponentialLoad` require voltage-dependency exponents that PyPSA `Load` does not carry. `InterruptiblePowerLoad` requires an `operation_cost` with no natural default.
2. **`p_set` handling:** PyPSA `p_set` serves dual duty — as a static initial condition (in `n.loads.p_set`) and as a time-varying dispatch profile (in `n.loads_t.p_set`). When a time series is present for a load, it overrides the static value. Map static `p_set` → `active_power` (initial condition). Map the peak of the time series (or static `p_set` when no series is present) → `max_active_power`. Emit a `TimeSeriesAssociation` on `max_active_power` (per-unit shape, `scaling_factor_multiplier: "PowerSystems.get_max_active_power"`).
3. **Sign convention:** PyPSA `p_set` positive = power consumed (load convention). Sienna `active_power` positive = demand. No sign flip required.
4. **Reactive power:** PyPSA `q_set` → Sienna `reactive_power` (initial condition) and `max_reactive_power`. In planning networks `q_set = 0`; in solved power-flow networks it may be non-zero. Map directly.
5. **`base_power`:** Sienna requires this for per-unitization. Set to the load's `max_active_power` when > 0, otherwise fall back to the system base (100.0 MVA). See the `base_power` sub-section for rationale.
6. **Scope filter:** Only loads whose attached bus has carrier `"AC"`, `"DC"`, or `""` are translated. Non-electricity loads (hydrogen, heat, gas demand) are deferred.

---

### Reference: Sienna ElectricLoad Type Hierarchy

For context (schema files in `SiennaSchemas/Operations/StaticInjection/`):

```
StaticInjection (abstract)
└── ElectricLoad (abstract)
    └── StaticLoad (abstract)
        ├── PowerLoad                 ← primary translation target for PyPSA Load
        ├── StandardLoad              ← ZIP load (Z/I/P components); dynamics/power flow
        ├── ExponentialLoad           ← P0·V^α, Q0·V^β voltage model; dynamics
        ├── MotorLoad                 ← motor load model
        ├── ActiveConstantPowerLoad   ← constant-power active load
        └── ControllableLoad (abstract)
            ├── InterruptiblePowerLoad    ← demand response with curtailment cost
            ├── InterruptibleStandardLoad ← ZIP + demand response
            └── ShiftablePowerLoad        ← time-shiftable demand
    └── FixedAdmittance               ← shunt admittance; NOT a demand load
```

**Translation target for PyPSA `Load`:** always `PowerLoad` by default. The other types require information that PyPSA `Load` does not carry:

- `StandardLoad` and `ExponentialLoad` need ZIP/exponential voltage-dependency parameters — absent in PyPSA.
- `InterruptiblePowerLoad` requires `operation_cost::Union{LoadCost, MarketBidCost}` with no sensible automatic default.
- `FixedAdmittance` is a shunt Y element, not a demand model — it carries `Y::Complex{Float64}` admittance, not power setpoints.

---

### Reference: Sienna `PowerLoad` Struct (from schema)

Source: `SiennaSchemas/Operations/StaticInjection/PowerLoad.json` (commit `906001306e9d3063a8820e84fd2ca7f955bf455e`)

```json
{
  "id": 1,
  "name": "load_1",
  "available": true,
  "bus": 1,
  "active_power": 150.0,
  "reactive_power": 0.0,
  "base_power": 250.0,
  "max_active_power": 250.0,
  "max_reactive_power": 0.0,
  "conformity": "UNDEFINED"
}
```

Field notes: `bus` is the integer `id` of the load's `ACBus`. `active_power`/`reactive_power` are MW/MVAR initial demand; `max_active_power`/`max_reactive_power` are the maxima (the time-series target). `base_power` is MVA for per-unitisation (validation `> 0.0001`). `conformity` is a `LoadConformity` — `UNDEFINED` for a PyPSA `Load`.

`LoadConformity` enum (from `definitions.jl`):

| Value | Integer | Meaning |
| --- | --- | --- |
| `LoadConformity.NON_CONFORMING` | 0 | Does not respond predictably to voltage/frequency |
| `LoadConformity.CONFORMING` | 1 | Responds predictably to voltage/frequency |
| `LoadConformity.UNDEFINED` | 2 | Not specified (default) |

PyPSA `Load` has no conformity concept — use `LoadConformity.UNDEFINED` throughout.

---

### Reference: Other Sienna Load Types

#### `StandardLoad <: StaticLoad`

Source: `SiennaSchemas/Operations/StaticInjection/StandardLoad.json`

A voltage-dependent ZIP load: `P = P_P·V⁰ + P_I·V¹ + P_Z·V²`, `Q = Q_P·V⁰ + Q_I·V¹ + Q_Z·V²`.

Required fields: `name`, `available`, `bus`, `base_power`. All power components are optional (default `0.0`):

```
constant_active_power / _reactive_power    # P_P, Q_P (constant power, MW/MVAR)
impedance_active_power / _reactive_power   # P_Z, Q_Z (constant impedance, MW/MVAR)
current_active_power / _reactive_power     # P_I, Q_I (constant current, MW/MVAR)
max_constant_active_power / _reactive_power
max_impedance_active_power / _reactive_power
max_current_active_power / _reactive_power
```

**When to use instead of `PowerLoad`:** Only if the source data carries explicit ZIP decomposition (e.g. from a power flow case with voltage-dependency modelling). PyPSA `Load` does not provide ZIP parameters — do not use `StandardLoad` for a direct PyPSA translation. A user could post-process the translation to assign ZIP fractions, but the translator should not guess them.

#### `InterruptiblePowerLoad <: ControllableLoad`

Source: `SiennaSchemas/Operations/StaticInjection/InterruptiblePowerLoad.json`

Identical fields to `PowerLoad` plus one **required** field with no default: `operation_cost` (a `LoadCost` or `MarketBidCost`) — the cost of interrupting load.

**When to use instead of `PowerLoad`:** Only when the load is enrolled in a demand response program with a known curtailment cost. PyPSA `Load` has no curtailment cost field. If a user explicitly provides `operation_cost` overrides per load, translate to `InterruptiblePowerLoad`; otherwise default to `PowerLoad`.

#### `ExponentialLoad <: StaticLoad`

Source: `SiennaSchemas/Operations/StaticInjection/ExponentialLoad.json`

Models `P = P0·Vᵅ` and `Q = Q0·Vᵝ`. Required fields beyond `name`/`available`/`bus`/`base_power`: `active_power` (P0, MW), `reactive_power` (Q0, MVAR), `α`/`β` (active/reactive voltage exponents, `> 0`), `max_active_power`, `max_reactive_power`.

**When to use:** Only for dynamics or power flow studies with known voltage-dependency exponents. Not a standard PyPSA `Load` translation target.

#### `FixedAdmittance <: ElectricLoad`

Source: `SiennaSchemas/Operations/StaticInjection/FixedAdmittance.json`

Its one distinctive field is `Y` — a fixed admittance (complex, pu on `SYSTEM_BASE`).

**Not a translation target.** Represents a shunt impedance element attached to a bus (e.g. capacitor bank, reactor) — not a demand load. PyPSA does not have an exact equivalent component type (shunts in PyPSA are represented on the bus via `b` and `g` fields, not as separate load objects).

---

### Reference: PyPSA `Load` Input Attributes

Source: `pypsa/data/component_attrs/loads.csv`

**Static input attributes (on `n.loads`):**

| Attribute | Type | Unit | Default | Required | Description |
| --- | --- | --- | --- | --- | --- |
| `name` | string | — | — | yes | Unique load name (index) |
| `bus` | string | — | — | yes | Name of bus to which load is attached |
| `carrier` | string | — | `""` | no | Energy carrier of the load |
| `type` | string | — | `""` | no | Placeholder — not implemented |
| `p_set` | float or series | MW | 0 | no | Active power consumption (positive = consuming) |
| `q_set` | float or series | MVar | 0 | no | Reactive power consumption (positive = inductive) |
| `sign` | float | — | −1 | no | Sign convention (−1 for loads: subtracts from bus injection) |
| `active` | bool | — | True | no | Whether included in optimisation |

**Time-varying attributes (on `n.loads_t`):**

| Attribute | Description |
| --- | --- |
| `p_set` | Active power demand profile (MW) — overrides static value when present for a given load |
| `q_set` | Reactive power profile (MVar) — overrides static value when present |

**Output-only attributes (computed; do not map as inputs):**

| Attribute | Description |
| --- | --- |
| `p` | Net active power drawn from bus (output of power flow) |
| `q` | Net reactive power drawn from bus (output) |

**`sign` field note:** The `sign` attribute is a PyPSA internal convention. For loads, `sign = -1` means the component subtracts `p_set` from the bus net injection (`p_net_bus += sign × p_set`). This is NOT a sign flip for the translator — `p_set` itself is always defined as positive for consuming loads in PyPSA's API. Sienna's `active_power` is also positive for consuming loads. No sign flip is applied.

---

### Scope Filtering

**v1 filter: electricity-only Loads.**

A `Load` is in scope if its attached bus is an electricity bus:

```python
def is_electricity_bus(n, bus_name):
    if bus_name not in n.buses.index:
        return False
    carrier = n.buses.loc[bus_name, "carrier"]
    return carrier in {"AC", "DC", ""}  # empty string = AC by convention


def load_in_scope(n, load_name):
    load = n.loads.loc[load_name]
    return is_electricity_bus(n, load.bus)
```

In all tested sample files, every load connects to an AC bus. Non-electricity loads (hydrogen demand, heat demand, etc.) are hypothetically possible in multi-energy networks but do not appear in the tested data. A load whose bus is not in the electricity carrier set is skipped with a warning and added to the deferred list.

---

### Sign Convention and Units

| Quantity | PyPSA convention | Sienna convention | Transform |
| --- | --- | --- | --- |
| Active power demand | `p_set` > 0 → consuming (MW) | `active_power` > 0 → consuming (MW) | None |
| Reactive power demand | `q_set` > 0 → inductive/consuming (MVar) | `reactive_power` > 0 → consuming (MVAR) | None |
| Power units | MW / MVar (absolute) | MW / MVAR (absolute) | None — both use natural units |

No sign flip, no unit conversion needed for P and Q. Both frameworks treat positive load demand as positive.

---

### Attribute Mapping Table: PyPSA `Load` → Sienna `PowerLoad`

| Sienna field | Type / unit | PyPSA source | Transform | Mapping type | Notes |
| --- | --- | --- | --- | --- | --- |
| `id` | `Int` | — | auto-assigned | **defaulted** | Auto-assigned by Sienna on ingestion |
| `name` | `String` | `n.loads.index` | direct | **direct** | Use PyPSA load name string |
| `available` | `Bool` | `n.loads.active` | direct | **direct** | `active=True` → `available=true`. Default `True` in both |
| `bus` | integer `id` | `n.loads.bus` | name → bus `id` | **derived** | the integer `id` of the load's `ACBus` (resolve the PyPSA bus name via the name→id map) |
| `active_power` | `Float64` (MW) | `n.loads.p_set` | direct | **direct** | Static `p_set` value. Used as initial condition for power flow. If `n.loads_t.p_set` is present, use its first timestep (or the static value if the load has no time-varying entry) |
| `reactive_power` | `Float64` (MVAR) | `n.loads.q_set` | direct | **direct** | Static `q_set` → `reactive_power`. Zero in most planning networks; may be non-zero in solved power flow cases |
| `base_power` | `Float64` (MVA) | — | see below | **derived** | No direct PyPSA source. See `base_power` section |
| `max_active_power` | `Float64` (MW) | `n.loads.p_set` or `n.loads_t.p_set` | see below | **derived** | Peak demand ceiling. See time-series section |
| `max_reactive_power` | `Float64` (MVAR) | `n.loads.q_set` or `n.loads_t.q_set` | direct or peak of ts | **derived** | Same logic as `max_active_power`. If `q_set` is always static and zero, set to `0.0` |
| `conformity` | `LoadConformity` | — | `LoadConformity.UNDEFINED` | **defaulted** | PyPSA `Load` has no conformity concept |
| `dynamic_injector` | `Union{Nothing, DynamicInjection}` | — | `nothing` | **defaulted** | Dynamics not relevant for PyPSA Load translation |

**Extensions sidecar.** Load attributes with no SiennaSchemas field go in the `extensions.json` companion (see Component extensions), as a `load` record identified by `name`:

```json
{ "load": [ { "name": "load_AT0", "carrier": "", "type": "", "sign": -1 } ] }
```

**Minimal valid JSON example (`PowerLoad`):**

```json
{
  "id": 7,
  "name": "load_AT0",
  "available": true,
  "bus": 1,
  "active_power": 8200.0,
  "reactive_power": 0.0,
  "base_power": 13450.0,
  "max_active_power": 13450.0,
  "max_reactive_power": 0.0
}
```

---

### `base_power` Handling

Sienna's `base_power` field is the MVA base used to convert this component's power quantities to per-unit when Sienna operates in `DEVICE_BASE` mode. Its validation constraint is `> 0.0001`.

PyPSA `Load` has no equivalent field. Two defensible conventions:

| Convention | Value | Rationale | Drawback |
| --- | --- | --- | --- |
| **System base** | `100.0 MVA` | Consistent with system-base convention used throughout the translator | Loads with small peak demand have large per-unit values |
| **Peak demand** | `max(p_set)` or `max(p_set_ts)` | Load's own natural base; per-unit values stay near 1.0 | Requires knowing the time series peak before constructing the object |

**Recommended for v1:** Use `max_active_power` as `base_power` when `max_active_power > 0.0001`, otherwise fall back to `100.0`. This keeps device-base per-unit quantities near 1.0 and is the convention used in PowerSystemCaseBuilder.jl load construction.

```python
base_power = max(max_active_power, 0.1)  # at least 0.1 MVA to satisfy validation
```

---

### Time Series for `PowerLoad`

#### `p_set` — the critical case

PyPSA convention: `n.loads.p_set` is a static scalar (MW) that acts as the demand value when no time series is present. `n.loads_t.p_set` is a DataFrame (timesteps × load names) where each column overrides the static value for that load at each timestep. A load not appearing in `n.loads_t.p_set` uses its static `n.loads.p_set`.

Sienna `PowerLoad` convention: `active_power` is a scalar initial condition; `max_active_power` is the magnitude (peak), and the per-timestep shape is a `TimeSeriesAssociation` on `max_active_power` (per-unit, scaled back up by `max_active_power` at read time).

**Mapping logic:**

```python
if load_name in n.loads_t["p_set"].columns:
    # Time-varying load
    ts = n.loads_t["p_set"][load_name]  # pandas Series, MW
    active_power = float(ts.iloc[0])  # first timestep as initial condition
    max_active_power = float(ts.max())  # peak for capacity field
    # emit a TimeSeriesAssociation on max_active_power; store ts / max_active_power (per-unit shape)
else:
    # Static load
    static_p = float(n.loads.loc[load_name, "p_set"])  # MW
    active_power = static_p
    max_active_power = static_p
    # no time series to attach
```

**Emitting the `TimeSeriesAssociation`:**

See Target format → Time series for the canonical form. The key points:

- `name` is `"max_active_power"` (the field the series scales); `owner_type`/`owner_id` point at the load.
- `resolution` is the ISO 8601 snapshot interval (e.g. `PT1H`).
- The stored array is the **per-unit shape** (`p_set / peak`), with `scaling_factor_multiplier: "PowerSystems.get_max_active_power"`; the magnitude lives in `max_active_power`.

#### `q_set` — reactive power time series

Same logic as `p_set`. Check `n.loads_t["q_set"]`. In all tested sample files, no load has a time-varying `q_set` (`n.loads_t["q_set"]` is an empty DataFrame or has 0 columns). If present:

- Static `q_set` → `reactive_power` (initial condition) and `max_reactive_power`.
- Time-varying `q_set` → `max_reactive_power` (peak), plus a `TimeSeriesAssociation` on `max_reactive_power`.

---

### Capacity Expansion

PyPSA `Load` has no capacity expansion fields (`p_nom_extendable`, `p_nom_opt`, etc.). Load demand is treated as exogenous (given, not optimised). There is no mapping needed for load-side capacity expansion.

In all tested sample files, load `p_set` time series are fully specified inputs — they represent demand profiles, not decision variables.

---

### Sample File Observations

| File | Loads | Bus carriers | q_set non-zero | p_set time-varying | Notes |
| --- | --- | --- | --- | --- | --- |
| `elec_s_70_ec_lv1.05_Co2L0.0-24H.nc` | 70 | AC=69, DC=1 | 0 / 70 | YES (365 × 70), range 309–21,028 MW | PyPSA-EUR Breakthrough network; one load on a DC-carrier bus |
| `solved_network.nc` | 51 | AC=51 | 51 / 51 | NO (static p_set, 142–666 MW) | q_set non-zero for all loads; solved power flow case |
| `unsolved_network.nc` | 51 | AC=51 | 51 / 51 | NO (static p_set, 71–333 MW) | Same structure as solved; pre-solve half-values |
| `network.nc` | 24 | AC=24 | 0 / 24 | YES (8760 × 24), range 138–59,299 MW | Annual hourly; all loads time-varying |
| `APG_2023_2050.nc` | 25 | AC=25 | 0 / 25 | YES (61,344 × 25), range 0–139,399 MW | Multi-year hourly planning horizon |

**Key observations:**

- In all files, loads connect exclusively to AC buses. The DC-bus load in `elec_s_70` has `n.buses.loc[bus, "carrier"] = "AC"` despite the load `carrier` field being empty — the DC in that file refers to the HVDC link convention, not a DC bus in the electrical sense. The scope filter correctly handles this (carrier check is on the bus, not the load).
- `q_set` is non-zero only in `solved_network` and `unsolved_network` — these are power flow cases with reactive power dispatch specified. Planning networks (elec_s_70, `network.nc`, APG) all have `q_set = 0`.
- `p_set` time series covers all loads in every planning file (load shapes are always provided for all buses in these models).
- No load `active=False` in any file tested.
- Load `carrier` field is empty string (`""`) in all tested files — the carrier is inherited from the bus, not set on the load itself.

---

### Complete Translation Example

#### Time-varying load (elec_s_70 / `network.nc` style)

PyPSA input:

```python
# n.loads.loc["AT0 0"]
load.name = "AT0 0"
load.bus = "AT0 0"  # AC bus, v_nom = 380 kV
load.p_set = 0.0  # static (overridden by time series)
load.q_set = 0.0
load.active = True

# n.loads_t["p_set"]["AT0 0"] is a Series of 365 daily MW values
# range: ~5,000–15,000 MW across Austria's hourly profiles
peak_p = n.loads_t["p_set"]["AT0 0"].max()  # e.g. 13,450 MW
first_p = n.loads_t["p_set"]["AT0 0"].iloc[0]  # e.g. 8,200 MW
```

Sienna (SiennaSchemas JSON):

```json
{
  "id": 1,
  "name": "AT0 0",
  "available": true,
  "bus": 1,
  "active_power": 8200.0,
  "reactive_power": 0.0,
  "base_power": 13450.0,
  "max_active_power": 13450.0,
  "max_reactive_power": 0.0,
  "conformity": "UNDEFINED"
}
```

`active_power` is the first timestep (initial condition); `base_power` and `max_active_power` are the peak demand. `bus` is the integer `id` of the ACBus the load sits on (resolved from the PyPSA bus name during translation), not a name or UUID.

The demand profile is a separate `TimeSeriesAssociation` record pointing at the load by `owner_id`; the value array lives in the external HDF5 store under `time_series_uuid`:

```json
{
  "owner_type": "PowerLoad",
  "owner_id": 1,
  "name": "max_active_power",
  "time_series_uuid": "<uuid>",
  "time_series_type": "SingleTimeSeries",
  "initial_timestamp": "2020-01-01T00:00:00",
  "resolution": "P1D",
  "length": 365,
  "scaling_factor_multiplier": "PowerSystems.get_max_active_power"
}
```

The stored array is the **per-unit shape** (`p_set(t) / peak`, in `[0, 1]`); `scaling_factor_multiplier` makes Sienna multiply it by the load's `max_active_power` (the peak) at read time, recovering MW. Store the shape, keep the magnitude in `max_active_power`, multiply on read.

#### Static load with q_set (solved_network style)

PyPSA input:

```python
load.name = "42"
load.bus = "107"  # AC bus, v_nom = 138 kV
load.p_set = 420.0  # MW (static, no time series)
load.q_set = 85.0  # MVar (reactive load)
load.active = True
```

Sienna (SiennaSchemas JSON):

```json
{
  "id": 1,
  "name": "42",
  "available": true,
  "bus": 1,
  "active_power": 420.0,
  "reactive_power": 85.0,
  "base_power": 420.0,
  "max_active_power": 420.0,
  "max_reactive_power": 85.0,
  "conformity": "UNDEFINED"
}
```

`bus` is the integer `id` of the ACBus named `"107"`. `base_power = max_active_power` because there is no time series; no `TimeSeriesAssociation` is emitted.

---

### Cross-Cutting Issues

#### Bus reference

The load's `bus` is the integer `id` of its `ACBus`. Resolve the PyPSA bus name to that `id` via the name→id map built during bus translation. If the bus was excluded during bus filtering (non-electricity carrier), exclude the load too, with a warning.

#### Id-assignment order

References resolve by `id`, so the serialised lists are unordered; assign `id`s so a referenced component exists before anything references it: `Area`/`LoadZone` → `ACBus` → branches → generators → loads, then the `TimeSeriesAssociation` records (which reference loads by `owner_id`).

#### Time series (cross-reference)

A load's demand profile is a `TimeSeriesAssociation` on `max_active_power` — a per-unit shape with `scaling_factor_multiplier: "PowerSystems.get_max_active_power"` and the array in the HDF5 store. This is identical to the `max_active_power` association on a `RenewableDispatch` (see the Generator time-series section and Target format → Time series).

---

### PyPSA Load Attributes with No Sienna Home

| PyPSA attribute | Disposition |
| --- | --- |
| `carrier` | Store in `ext["carrier"]`. PyPSA load-level carrier (usually empty string — carrier is on the bus). |
| `type` | Placeholder, not implemented in PyPSA. Store in `ext["type"]` if non-empty; discard if empty. |
| `sign` | PyPSA internal sign convention (always −1 for loads). Store in `ext["sign"]` for round-trip auditability. |
| `p` | Output-only (active power result). Discard. |
| `q` | Output-only (reactive power result). Discard. |

---

### Open Questions

1. **`base_power` convention.** Using `max_active_power` as `base_power` keeps device-base per-unit values near 1.0, but it means `base_power` varies per load and is not the system base. Some Sienna workflows expect all loads to share the system MVA base (100.0 MVA). Confirm which convention the BTE PowerSimulations.jl workflow expects before finalising.
2. **`max_active_power` for static loads.** When `p_set` is static and no time series is present, `max_active_power = p_set`. But in operational simulations, `max_active_power` is the *ceiling* — if the actual dispatch can be less than `p_set` (e.g. load curtailment), should `max_active_power` be set higher? For `PowerLoad` (non-interruptible), curtailment is not modelled — the load always draws `max_active_power`. This is consistent with setting `max_active_power = p_set`.
3. **DC-bus loads.** `elec_s_70` has one load on a bus where the load's `carrier` field is `""` and the bus is an AC bus at 380 kV. This passes the electricity filter correctly. But if a future network uses a true `DCBus` (a Sienna concept for DC grid nodes), `PowerLoad` is typed to `ACBus`. Would a DC-bus load need a different Sienna type?
4. **Reactive power time series.** No tested file has time-varying `q_set`, but the mapping must handle it. The proposed approach is a `TimeSeriesAssociation` on `max_reactive_power`. Confirm that PowerSimulations.jl reads `max_reactive_power` time series for loads in reactive power-aware OPF formulations.
5. **`active=False` loads.** No inactive loads appear in tested files. If a load has `active=False`, should the translator set `available=false` and include it in the System, or skip it entirely? Sienna's `available=false` excludes components from simulations — including them as unavailable preserves round-trip fidelity.
6. **Round-trip reconstruction.** To recover a PyPSA `Load` from a Sienna `PowerLoad`, the translator needs the `p_set` time series (from `max_active_power` time series), bus name (from `bus.name`), and `q_set` (from `reactive_power` or `max_reactive_power` time series). Is `ext["carrier"]` sufficient for full reconstruction, or should the full PyPSA attribute set be serialised to `ext`?

---

### Deferred Items

| Item | Reason | Suggested future approach |
| --- | --- | --- |
| **Non-electricity loads** (hydrogen demand, heat demand, gas demand) | Bus carrier is not in `{"AC", "DC", ""}` | No PowerSystems.jl equivalent for multi-energy demand. Model as custom `ext`-only objects or extend the type hierarchy. |
| **`StandardLoad`** (ZIP model) | Requires Z/I/P fractions — not in PyPSA `Load` | Add a user-supplied ZIP fraction override mechanism. Or derive from bus-level load composition studies. |
| **`InterruptiblePowerLoad`** | Requires `operation_cost::Union{LoadCost, MarketBidCost}` | Add a per-load override file that specifies curtailment cost; use it to choose `InterruptiblePowerLoad` vs `PowerLoad`. |
| **`ExponentialLoad`** | Requires `α`, `β` voltage exponents — not in PyPSA | Only relevant for dynamics studies with known exponents. |
| **Shunt admittances as `FixedAdmittance`** | PyPSA bus-level `b` and `g` are on the bus, not as a `Load` component | Map bus shunts separately during bus translation if needed for dynamics models. |
| **Time-varying `q_set`** | No tested file uses this | Apply the same `TimeSeriesAssociation` pattern as `p_set`; cross-check with reactive OPF formulation requirements. |
