1: # Every Sienna output of tz-oss-interop is a valid SiennaSchemas 0.2 document
2:
3: ## Goal and scope
4:
5: Every Sienna document that tz-oss-interop writes must validate against SiennaSchemas 0.2.
6: Every Sienna reader in tz-oss-interop must read that shape. The check is the Python package
7: `power-openapi-models` 0.2.0. The PyPSA output of every round trip must not change.
8:
9: In scope:
10:
11: - The writers: `pypsa-to-sienna` (with its ensemble and investments variants),
12:   `plexos-to-sienna`, and `osemosys-csv-to-sienna`.
13: - The readers: `stage_sienna_system_json`, its ensemble variant, `stage_sienna_results`,
14:   the `sienna_to_pypsa` steps, and the `sienna_to_powersimulations` steps.
15: - The test builders in `libs/interop-testing`, a contract test, the mapping documents, and
16:   the Sienna input contract in `CLAUDE.md`.
17:
18: Out of scope:
19:
20: - A SiennaGridDB sink. It waits on the GridDB insert SDK.
21: - A psy6 solve, and the removal of the psy5 envelope route.
22: - A GridDB source.
23: - A new HDF5 value layout.
24:
25: After this work, the psy6 loader and the GridDB insert SDK can read the output with no
26: extra translation step.
27:
28: ## Why this is not a small change
29:
30: - No output passes today. The check covered 178 `system.json` files from the
31:   `pypsa_to_sienna` scenarios. None of the 173 files with a `components` key has a valid
32:   envelope. Only `ACBus` rows are valid, which is 1 of 12 types.
33: - The SDK ignores a component key that no class names. Four more gaps pass a plain
34:   validity check: `fuel_type` (the SDK field is `fuel`), `must_run`, the HVDC
35:   `active_power_limits_*` fields, and the HVDC `loss` shape.
36: - Ids conflict. tz-oss-interop makes ids unique for each type. SiennaGridDB declares
37:   `entities.id` as the primary key, and the SiennaSchemas document says ids are unique
38:   across every type.
39: - One document feeds many routes. Three writers produce it. Five pipelines read it through
40:   one function, `stage_topology`. `plexos-to-pypsa` is `plexos-to-sienna` followed by
41:   `sienna-to-pypsa`.
42: - About half of the changes break a reader if only the writer changes. The Arc ends, the
43:   time-series key, and the cost key are examples. A writer-only cost-key rename gives a zero
44:   marginal cost on the PowerSimulations route, with no error.
45: - The sink makes two decisions today: the Area constants and the time-series association
46:   ids.
47:
48: ## Baseline
49:
50: The per-type result of the check, before any change:
51:
52: | Type | Valid rows | Failing fields |
53: |---|---|---|
54: | ACBus | 209 of 209 | none |
55: | Eleven other types | none valid | see the table below |
56:
57: Six field gaps explain all 184 failing component rows:
58:
59: | Field | Types | Rows |
60: |---|---|---|
61: | `power_units` | 10 | 154 |
62: | `operation_cost` | 4 | 70 |
63: | `base_power` | 3 | 48 |
64: | `status` (an enum, not a `bool`) | 1 | 41 |
65: | `from_id` and `to_id` | 1 (Arc) | 30 |
66: | `rating` | 1 (HVDC) | 20 |
67:
68: `power_units` fails in 10 of the 11 failing types. It is the first gap to close.
69: The check has not yet covered the `plexos-to-sienna` and `osemosys-csv-to-sienna`
70: outputs. They share the sink and the constants, so the same gaps are likely.
71:
72: ## Decisions
73:
74: The first four decisions follow the order of the work. Each is fixed for this work.
75:
76: 1. **Contract check.** Pin `power-openapi-models==0.2.0` in the runtime dependencies of
77:    tz-oss-interop. The pin is exact, because a pre-1.0 release can break. A `Then` step in
78:    `libs/interop-testing` validates each written document. It checks each row with its SDK
79:    class and compares the row keys with the class fields. The sink builds the document with
80:    the SDK, so the envelope comes from the package.
81: 2. **Ids.** Ids are unique across the whole document. The steps allocate them with one
82:    counter.
83: 3. **Sidecar pointer.** Remove the `extensions_filename` key from `system.json`, because the
84:    schema forbids it. Keep every path parameter. The readers already take
85:    `extensions_json_path` as a parameter.
86: 4. **Time series.** Association rows follow 0.2, with `uri = "time_series/<uuid>/data"`.
87:    The HDF5 value layout does not change.
88: 5. **Units basis.** Storage and Line use `COMPONENT_BASE`. A Line `base_power` is 100.0.
89:    Loads and HVDC use `NATURAL_UNITS`. Generators use `NATURAL_UNITS`, so `rating` becomes
90:    MVA.
91: 6. **HVDC limits.** `rating_from = p_nom * p_max_pu`. `rating_to = -p_nom * p_min_pu` when
92:    `p_min_pu < 0`, else 0.0. `rating` is the larger of the two.
93: 7. **Thermal fields.** `status` defaults to `"ONLINE"`. `fuel_type` becomes `fuel`.
94:    `must_run` moves to the `extensions.json` sidecar.
95: 8. **Archived parity baseline.** Keep the archived manifests and delete nothing. They no
96:    longer match the output once the envelope changes. No live test enforces them. The
97:    `plexos_to_pypsa` suite guards the composed path.
98:
99: Who writes the time-series values stays open. The HDF5 writer does not change in the first
100: rungs.
101:
102: ## Order of the work
103:
104: | Task | Change | Types valid after |
105: |---|---|---|
106: | 01 | Contract step, baseline, this spec | ACBus |
107: | 02 | Envelope, sorted keys, no decisions in the sink | ACBus |
108: | 03 | Ids unique across the document | ACBus |
109: | 04 | Labels that keep today's values, enums, new series fields | Area, Line, PowerLoad, EnergyReservoirStorage |
110: | 05 | Arc ends | Arc |
111: | 06 | Cost key `variable_operation_cost` | InterruptiblePowerLoad |
112: | 07 | Thermal `status`, `fuel`, `must_run` | none yet |
113: | 08 | HVDC `rating` and `LossCurve` | TwoTerminalGenericHVDCLine |
114: | 09 | Generator units basis | the four generator types, 12 of 12 |
115: | 10 | Series rows by `uri` | none new |
116: | 11 | Documentation | none new |
117:
118: Tasks 01 to 04 change the writers only. Tasks 05 to 10 each change the writer, the readers
119: and the test builders together.
120:
121: ## The archived parity baseline
122:
123: The archived parity baseline (`interop/pipelines/archive/plexos-to-sienna-via-pypsa.yaml`
124: and the manifests that go with it) describes the output as it was before this work. After
125: task 02 it no longer matches the output of the writers. This work keeps it as history and
126: does not refresh it.
