# The Sienna sink drops a null field, and a voltage-stepping PLEXOS Line becomes a transformer

Date: 2026-11-19. Issue: [#181](https://github.com/transition-zero/tz-oss-interop/issues/181).

A PLEXOS to Sienna translation wrote a `system.json` that the Sienna stack refuses in two
ways. This design states what changes.

1. The document states `null` on an optional field. The SiennaSchemas strict schema takes a
   value or no key at all, so the read fails.
2. A PLEXOS Line that steps voltage becomes a Sienna `Line`. PowerSystems.jl refuses a
   `Line` whose two endpoint buses hold different base voltages.

## What the strict bundle reports today

The SDK `power-openapi-models` 0.2.0 holds the strict JSON Schema bundle and the function
`validate_source` that applies it. The test suite does not apply it today, so this design
measures the gap first.

A probe ran the strict bundle over every Sienna document that the BDD suite writes. The
probe ran outside the repository and changed no file.

- Every error on a system document is a null on an optional field. The sink change below
  clears all of them. No required field is exposed.
- Every portfolio document holds exactly one more error: a `TopologyMapping` supplemental
  attribute states a `buses` key, and SiennaSchemas 0.2 defines no such attribute.

## 1. The sink drops each null-valued key

`drop_absent_fields` in `interop/plugins/sinks/_sienna_files.py` already drops a
null-valued key at each depth of a nested dict. The portfolio sink and the
PowerSystemsInvestments sink already call it. The system sink does not.

Two changes:

- `drop_absent_fields` also recurses into a dict inside a list. A null that the probe found
  sits nested, such as `operation_cost.variable_operation_cost.value_curve.input_at_zero`,
  and a cost curve holds a list of points. A list element that is itself null stays, because
  a drop would move each element after it.
- `serialise_system_document` and `serialise_portfolio_document` apply it to `components`
  and to `supplemental_attributes`.

The document envelope and the association rows stay as they are. The SDK owns them, and
`time_series_storage_file` is required and nullable, so its null must stay. No component
field and no association field in the 0.2.0 bundle is both required and nullable, so a null
inside a row is always safe to drop.

One place covers the PyPSA, PLEXOS and OSeMOSYS legs.

## 2. The strict bundle check joins the existing step

`libs/interop-testing/src/interop_testing/steps/sienna_schema.py` checks each row with its
pydantic class. Pydantic takes a null on an optional field, so no test caught this.

`list_document_problems` calls `validate_source(document, SCHEMA_VERSION, bundle,
BUNDLE_DIR)` from the SDK. `SCHEMA_VERSION` is the `"0.2.0"` constant that the module
already states, so the check names the pinned schema version. The check does not follow the
installed package, and it does not read PyPI, so a new release of the SDK does not change
what it tests.

`interop-testing` declares `power-openapi-models[source-version]`, which pulls `jsonschema`.
The main package `interop` takes no new dependency.

Each scenario that already states "the written Sienna system is a valid SiennaSchemas 0.2
document" gains the check. The same holds for the portfolio step.

## 3. The TopologyMapping attribute goes

SiennaSchemas 0.2 defines no `TopologyMapping`. The six supplemental attribute types that it
does define hold no field for a list of bus names. The SiennaSchemas change log records that
`TopologyMapping.json` was removed.

The attribute states the buses of one area. The same run writes the base system, and each
`ACBus` of the base system states its `area`, so the system document already holds the map.
Nothing in this repository reads the attribute back.

So the attribute goes. These parts are deleted:

- `interop/plugins/shared/pypsa_sienna_investments_translations/_topology.py`;
- `SiennaSupplementalAttribute.TOPOLOGY_MAPPING`, `TOPOLOGY_MAPPING_DESTINATION_SCHEMA` and
  `SiennaTopologyMappingCol` in `sienna_investments_constants.py`;
- the `SUPPLEMENTAL_ATTRIBUTE_ORDER` entry;
- the two call sites in `pypsa_sienna_investments_translations/_portfolio.py`;
- the two scenarios that assert the attribute, and the mapping document rows that state it.

One `NOT_MAPPED` event records that the area of each bus carries the map.

One shared module serves the PyPSA and the OSeMOSYS investments legs, so the deletion covers
both.

## 4. A voltage-stepping PLEXOS Line becomes a transformer

### When the transformer path applies

A PLEXOS Line takes the transformer path when all three conditions hold:

- the Line states a `Resistance` or a `Reactance`;
- both endpoint Nodes state a `Voltage`;
- the two stated voltages differ at all.

A Node that states no `Voltage` takes `DEFAULT_BUS_BASE_VOLTAGE`, which is 1.0 kV. The
second condition keeps a 230 kV Node joined to such a Node from reading as a 230:1
transformer. A `Voltage` in a data file that did not stage counts as not stated.

The threshold is any difference at all, and not the 1% of the mean that
`BRANCH_BUS_VOLTAGE_DIFFERENCE_TOL` in PowerSystems.jl applies. A rule with no tolerance is
simpler to state and to test.

A Line that states no impedance stays a `TwoTerminalGenericHVDCLine`, whatever its two
voltages are, because an HVDC line joins two voltages by design.

The stated voltages come from `build_buses_source_table`, which holds the stated value
before `DEFAULT_BUS_BASE_VOLTAGE` fills it. The bus step builds the same table.

### What one Line becomes

SiennaSchemas 0.2 splits a transformer in two, so one PLEXOS Line becomes three records.

| Record | What it holds |
| --- | --- |
| `Arc` | The Arc of the two endpoint buses, which `sienna_relate_components` derives |
| `TransformerCircuit` | `arc`, `r`, `x`, `tap`, `rating`, `available`, `power_units`, `base_power`, `base_voltage_primary`, `base_voltage_secondary` |
| `TwoWindingTransformer` | `id`, `name`, and `circuit`, the id of its circuit |

| Sienna field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | `Line.name`, on the `TwoWindingTransformer` | direct |
| `arc` | | The `Arc` of `Node From` and `Node To` | derived |
| `r` | pu | `Resistance` x the system base / the from-Node voltage squared | derived |
| `x` | pu | `Reactance` x the system base / the from-Node voltage squared | derived |
| `rating` | pu | `Max Rating`, else `Max Flow`, over the system base | derived |
| `base_voltage_primary` | kV | The stated `Voltage` of `Node From` | derived |
| `base_voltage_secondary` | kV | The stated `Voltage` of `Node To` | derived |
| `tap` | | `1.0`, because PLEXOS states no tap | default |
| `available` | | `True` | default |
| `power_units` | | `COMPONENT_BASE` | default |
| `base_power` | MVA | `100.0`, the system base | default |

The impedance base is the from-Node voltage, which is the base that the Line path already
applies. So one PLEXOS Line gives the same `r` and the same `x` whether it reads as a `Line`
or as a transformer. `base_voltage_primary` states that base, so a consumer can refer the
values to the other winding.

`magnetizing_shunt`, `shunt_location` and `admittance_units` stay absent, so each takes its
schema default.

### The wiring

- Two column classes and two destination schemas in `sienna_constants.py`. The circuit
  schema carries `bus0` and `bus1`, as the Line schema does, and the sink turns them into
  the Arc and drops them.
- `sienna_relate_components._BRANCH_COMPONENTS` gains `TransformerCircuit`, so the endpoints
  of a circuit get an Arc.
- `emit_sienna_system_json` sends a circuit through `_build_branch_components` and a
  transformer through `_build_plain_components`.
- The id counter in `map_transmission` covers four lists rather than two.
- `ExtensionKind.TRANSFORMER` and a `TransformerExtension` carry the PyPSA fields that no
  Sienna field holds: `carrier`, `length`, `num_parallel` and `s_nom_extendable`. Without
  the record, the `Length` and the `Circuits` of a stepping Line are lost, where the Line
  path keeps them.

### What stays out

- The Sienna to PyPSA leg does not read the two records back as a PyPSA `Transformer`.
- Neither leg reads the PLEXOS `Transformer` class.

Both are separate work.

## 5. Scenarios

- A PLEXOS Line between two Nodes of different stated voltage gives a
  `TwoWindingTransformer` and a `TransformerCircuit`.
- A PLEXOS Line between two Nodes of equal stated voltage gives a `Line`.
- A PLEXOS Line whose endpoint Node states no voltage gives a `Line`.
- A PyPSA `Line` row states no `rating_b` key and no `rating_c` key.
- Each scenario that already asserts a valid SiennaSchemas 0.2 document gains the strict
  bundle check.

## What this design does not change

The project stays on SiennaSchemas 0.2, which the pin `power-openapi-models==0.2.0` states.
The latest release of the SDK is 0.5.0. A move to 0.5.0 rewrites the input contract, both
mapping documents and every component schema. That is separate work.
