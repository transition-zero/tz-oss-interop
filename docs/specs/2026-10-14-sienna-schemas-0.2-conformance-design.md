# Every Sienna output of tz-oss-interop is a valid SiennaSchemas 0.2 document

## Goal and scope

Every Sienna document that tz-oss-interop writes must validate against SiennaSchemas 0.2.
Every Sienna reader in tz-oss-interop must read that shape. The check is the Python package
`power-openapi-models` 0.2.0. The PyPSA output of every round trip must not change.

In scope:

- The writers: `pypsa-to-sienna` (with its ensemble and investments variants),
  `plexos-to-sienna`, and `osemosys-csv-to-sienna`.
- The readers: `stage_sienna_system_json`, its ensemble variant, `stage_sienna_results`,
  the `sienna_to_pypsa` steps, and the `sienna_to_powersimulations` steps.
- The test builders in `libs/interop-testing`, a contract test, the mapping documents, and
  the Sienna input contract in `CLAUDE.md`.

Out of scope:

- A SiennaGridDB sink. It waits on the GridDB insert SDK.
- A psy6 solve, and the removal of the psy5 envelope route.
- A GridDB source.
- A new HDF5 value layout.

After this work, the psy6 loader and the GridDB insert SDK can read the output with no
extra translation step.

## Why this is not a small change

- No output passes today. The check covered 178 `system.json` files from the
  `pypsa_to_sienna` scenarios. None of the 173 files with a `components` key has a valid
  envelope. Only `ACBus` rows are valid, which is 1 of 12 types.
- The SDK ignores a component key that no class names. Four more gaps pass a plain
  validity check: `fuel_type` (the SDK field is `fuel`), `must_run`, the HVDC
  `active_power_limits_*` fields, and the HVDC `loss` shape.
- Ids conflict. tz-oss-interop makes ids unique for each type. SiennaGridDB declares
  `entities.id` as the primary key, and the SiennaSchemas document says ids are unique
  across every type.
- One document feeds many routes. Three writers produce it. Five pipelines read it through
  one function, `stage_topology`. `plexos-to-pypsa` is `plexos-to-sienna` followed by
  `sienna-to-pypsa`.
- About half of the changes break a reader if only the writer changes. The Arc ends, the
  time-series key, and the cost key are examples. A writer-only cost-key rename gives a zero
  marginal cost on the PowerSimulations route, with no error.
- The sink makes two decisions today: the Area constants and the time-series association
  ids.

## Baseline

The per-type result of the check, before any change:

| Type | Valid rows | Failing fields |
|---|---|---|
| ACBus | 209 of 209 | none |
| Eleven other types | none valid | see the table below |

Six field gaps explain all 184 failing component rows:

| Field | Types | Rows |
|---|---|---|
| `power_units` | 10 | 154 |
| `operation_cost` | 4 | 70 |
| `base_power` | 3 | 48 |
| `status` (an enum, not a `bool`) | 1 | 41 |
| `from_id` and `to_id` | 1 (Arc) | 30 |
| `rating` | 1 (HVDC) | 20 |

`power_units` fails in 10 of the 11 failing types. It is the first gap to close.
The check has not yet covered the `plexos-to-sienna` and `osemosys-csv-to-sienna`
outputs. They share the sink and the constants, so the same gaps are likely.

## Decisions

The first four decisions follow the order of the work. Each is fixed for this work.

1. **Contract check.** Pin `power-openapi-models==0.2.0` in the runtime dependencies of
   tz-oss-interop. The pin is exact, because a pre-1.0 release can break. A `Then` step in
   `libs/interop-testing` validates each written document. It checks each row with its SDK
   class and compares the row keys with the class fields. The sink builds the document with
   the SDK, so the envelope comes from the package.
2. **Ids.** Ids are unique across the whole document. The steps allocate them with one
   counter.
3. **Sidecar pointer.** Remove the `extensions_filename` key from `system.json`, because the
   schema forbids it. Keep every path parameter. The readers already take
   `extensions_json_path` as a parameter.
4. **Time series.** Association rows follow 0.2, with `uri = "time_series/<uuid>/data"`.
   The HDF5 value layout does not change.
5. **Units basis.** Storage and Line use `COMPONENT_BASE`. A Line `base_power` is 100.0.
   Loads and HVDC use `NATURAL_UNITS`. Generators use `NATURAL_UNITS`, so `rating` becomes
   MVA.
6. **HVDC limits.** `rating_from = p_nom * p_max_pu`. `rating_to = -p_nom * p_min_pu` when
   `p_min_pu < 0`, else 0.0. `rating` is the larger of the two.
7. **Thermal fields.** `status` defaults to `"ONLINE"`. `fuel_type` becomes `fuel`.
   `must_run` moves to the `extensions.json` sidecar.
8. **Archived parity baseline.** Keep the archived manifests and delete nothing. They no
   longer match the output once the envelope changes. No live test enforces them. The
   `plexos_to_pypsa` suite guards the composed path.

Who writes the time-series values stays open. The HDF5 writer does not change in the first
rungs.

## Order of the work

| Task | Change | Types valid after |
|---|---|---|
| 01 | Contract step, baseline, this spec | ACBus |
| 02 | Envelope, sorted keys, no decisions in the sink | ACBus |
| 03 | Ids unique across the document | ACBus |
| 04 | Labels that keep today's values, enums, new series fields | Area, Line, PowerLoad, EnergyReservoirStorage |
| 05 | Arc ends | Arc |
| 06 | Cost key `variable_operation_cost` | InterruptiblePowerLoad |
| 07 | Thermal `status`, `fuel`, `must_run` | none yet |
| 08 | HVDC `rating` and `LossCurve` | TwoTerminalGenericHVDCLine |
| 09 | Generator units basis | the four generator types, 12 of 12 |
| 10 | Series rows by `uri` | none new |
| 11 | Documentation | none new |

Tasks 01 to 04 change the writers only. Tasks 05 to 10 each change the writer, the readers
and the test builders together.

## The archived parity baseline

The archived parity baseline (`interop/pipelines/archive/plexos-to-sienna-via-pypsa.yaml`
and the manifests that go with it) describes the output as it was before this work. After
task 02 it no longer matches the output of the writers. This work keeps it as history and
does not refresh it.
