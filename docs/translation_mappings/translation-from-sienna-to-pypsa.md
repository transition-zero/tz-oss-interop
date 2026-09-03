# Translation from Sienna to PyPSA

This document tells you what each part of your Sienna system becomes in the PyPSA network.
It gives the source of each field.

> **Scope:** the translator accepts a SiennaSchemas system, and only that. It accepts
> electricity-only systems. It reads the system JSON, its HDF5 time series companion and an
> optional `extensions.json` sidecar. Refer to
> [What the translator reads](#what-the-translator-reads). Many Sienna systems come from the
> opposite translation, so this document also tells you which values change when a PyPSA
> network goes out to Sienna and comes back. Refer to
> [Round-trip asymmetries](#round-trip-asymmetries).

The pipeline is `sienna-to-pypsa`. Refer to
[Translation from PyPSA to Sienna](./translation-from-pypsa-to-sienna.md) for the opposite
direction.

---

## What becomes what

| Sienna | PyPSA |
| --- | --- |
| [`ACBus`](#acbus--bus) | `Bus` |
| [`Area`](#acbus--bus) | No component. It gives the bus `location`. |
| [`Arc`](#line-and-monitoredline--line) | No component. It gives `bus0` and `bus1` on each branch. |
| [`PowerLoad`](#powerload--load) | `Load` |
| [`ThermalStandard`](#thermalstandard--generator) | `Generator` |
| [`RenewableDispatch`](#renewabledispatch-and-renewablenondispatch--generator) | `Generator` |
| [`RenewableNonDispatch`](#renewabledispatch-and-renewablenondispatch--generator) | `Generator` |
| [`HydroDispatch`](#hydrodispatch--storageunit) | `StorageUnit` with the carrier `hydro` |
| [`EnergyReservoirStorage`](#energyreservoirstorage--storageunit) | `StorageUnit` with the carrier `PHS` |
| [`Line`](#line-and-monitoredline--line) | `Line` |
| [`MonitoredLine`](#line-and-monitoredline--line) | `Line`, the same as a `Line` |
| [`TwoTerminalGenericHVDCLine`](#twoterminalgenerichvdcline--link) | `Link` |
| [`TimeSeriesAssociation`](#time-series) | No component. It gives a PyPSA time series. |
| [`extensions.json`](#the-extensions-sidecar) | No component. It restores the PyPSA fields that Sienna cannot hold. |
| Every other SiennaSchemas type | [Not translated](#not-translated) |

## Reading the tables

| Mapping | Meaning |
| --- | --- |
| `direct` | The translator uses your Sienna value without a change. |
| `derived` | The translator calculates the value from your values, with the formula that the table gives. |
| `default` | Sienna has no such data. The translator supplies this value. |
| `sidecar` | The translator reads the value from `extensions.json`, not from the Sienna component. |

A field that no table names does not go into the network. Refer to
[Not translated](#not-translated).

## What the translator reads

The translator reads three inputs.

| Input | Required | Holds |
| --- | --- | --- |
| The system JSON | Yes | Each component, in a top-level `components` object that maps a type name to a list. |
| The HDF5 companion | Yes | The values of each time series, at `time_series/<uuid>/data`. |
| `extensions.json` | No | The PyPSA fields that SiennaSchemas has no home for. |

The system JSON gives each component an integer `id`, and it points at another component by
that integer. The translator replaces each integer with the name of the component. Thus
every name in the PyPSA network is the name your Sienna system gives.

Only this translator writes an `extensions.json` sidecar. A SiennaSchemas system from a
partner is the system JSON and its HDF5 companion and nothing more. Leave the sidecar prompt
blank for such a system. The run then behaves as a system where no component had a record.

An `extensions.json` that a version before the kind-keyed format wrote is a list of records.
The translator refuses such a file and tells you to write it again. It does not read part of
it.

## Across all components

- **The name is the identifier.** The translator matches a sidecar record to a component by
  name. It does not use the integer `id` for this.
- **The system base is 100 MVA.** The translator uses this fixed value to convert each
  per-unit rating and impedance. It does not read a base from your system. If your system
  uses a different base, the ratings and the impedances will be wrong.
- **The snapshot duration comes from the first generator series.** The translator needs it
  to convert a ramp rate and a run-time limit. It reads the resolution of the first
  `RenewableDispatch`, `RenewableNonDispatch` or `ThermalStandard` series that your system
  holds. With no such series, it uses 60 minutes.
- **A missing table is not an error.** A system with no lines translates, and the network
  gets no lines.
- **Some source values stop the run.** An `ACBus` whose `bustype` is `ISOLATED` stops it,
  and so does a generator whose prime mover is not in [the carrier table](#carriers). A
  component that points at a bus your system does not hold stops it too. Every other value
  translates or gets a default. Refer to
  [What the report tells you](#what-the-report-tells-you).
- **Each derivation goes into the report.** `decisions.md` gives one row for each field, with
  the Sienna value, the PyPSA value and the formula between them.

---

## `ACBus` → `Bus`

| PyPSA field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | `ACBus.name` | `direct` |
| `v_nom` | kV | `base_voltage` | `direct` |
| `carrier` | | `extensions.carrier` of the `bus` record. If absent, `AC`. | `sidecar` or `default` |
| `control` | | `bustype`, through the table below | `derived` |
| `location` | | The name of the `Area` that `area` points at | `derived` |

The `bustype` becomes the PyPSA control mode:

| Sienna `bustype` | PyPSA `control` |
| --- | --- |
| `PQ` | `PQ` |
| `PV` | `PV` |
| `REF` | `Slack` |
| `SLACK` | `Slack` |

`ISOLATED` is the one `bustype` that has no PyPSA control mode. A bus with that type stops
the run, because a wrong control mode would change the power flow without telling you.

A bus that points at no `Area` gets an empty `location`. The translator writes the
`location` in a second step, `sienna_to_pypsa_relate_components`, so its report rows carry
that step name rather than the mapping step name.

The translator does not set the bus coordinates, `x` and `y`. It does not set the voltage
magnitude fields either. Refer to [Not translated](#not-translated).

## `PowerLoad` → `Load`

| PyPSA field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | `PowerLoad.name` | `direct` |
| `bus` | | The bus that `bus` points at | `derived` |
| `p_set` | MW | `max_active_power` | `direct` |
| `carrier` | | `extensions.carrier` of the `load` record | `sidecar` |
| `type` | | `extensions.type` of the `load` record | `sidecar` |

A `PowerLoad` can carry a `max_active_power` time series. Sienna holds that series as a
shape whose peak is 1.0. The translator multiplies each value by the static
`max_active_power`, so `p_set` becomes a demand in MW. Refer to
[Time series](#time-series).

## `ThermalStandard` → `Generator`

| PyPSA field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | `ThermalStandard.name` | `direct` |
| `bus` | | The bus that `bus` points at | `derived` |
| `carrier` | | `extensions.carrier` of the `generator` record. If absent, the `prime_mover_type` and `fuel_type` pair. Refer to [Carriers](#carriers). | `sidecar` or `derived` |
| `p_nom` | MW | `base_power` | `direct` |
| `p_max_pu` | per unit of `p_nom` | `rating` | `direct` |
| `p_min_pu` | per unit of `p_nom` | `active_power_limits.min` ÷ `base_power` | `derived` |
| `marginal_cost` | cost for each MWh | The proportional term of the value curve of `operation_cost.variable` | `derived` |
| `start_up_cost` | cost | `operation_cost.start_up` | `direct` |
| `shut_down_cost` | cost | `operation_cost.shut_down` | `direct` |
| `ramp_limit_up` | per unit of `p_nom` for each snapshot | `ramp_limits.up` × the snapshot duration in minutes ÷ `base_power` | `derived` |
| `ramp_limit_down` | per unit of `p_nom` for each snapshot | `ramp_limits.down` × the snapshot duration in minutes ÷ `base_power` | `derived` |
| `min_up_time` | snapshots | `time_limits.up` × 60 ÷ the snapshot duration in minutes | `derived` |
| `min_down_time` | snapshots | `time_limits.down` × 60 ÷ the snapshot duration in minutes | `derived` |
| `up_time_before` | snapshots | `time_at_status` × 60 ÷ the snapshot duration in minutes | `derived` |
| `committable` | | `extensions.committable` of the `generator` record. If absent, `False`. | `sidecar` or `default` |
| `p_nom_extendable` | | `extensions.p_nom_extendable` of the `generator` record. If absent, `False`. | `sidecar` or `default` |
| `efficiency` | | The translator sets nothing, so PyPSA applies its own default of 1.0 | `default` |

Sienna states a ramp rate in MW for each minute, and PyPSA states it as a share of `p_nom`
for each snapshot. Sienna states a run-time limit in hours, and PyPSA states it in
snapshots. Both conversions need the snapshot duration. Refer to
[Across all components](#across-all-components) for where that duration comes from.

Three fields have a default when your generator states nothing:

- A generator with no `ramp_limits` keeps PyPSA's unconstrained default. The translator
  leaves `ramp_limit_up` and `ramp_limit_down` unset.
- A generator with no `time_limits` gets `min_up_time = 0` and `min_down_time = 0`.
- A generator whose `time_at_status` is `10000.0` gets `up_time_before = 0`. That number is
  a sentinel. Refer to [Round-trip asymmetries](#round-trip-asymmetries).

A generator whose `base_power` is `0.0` gets `p_min_pu = 0.0`. A zero capacity is a valid
placeholder, so the translator does not divide by it.

## `RenewableDispatch` and `RenewableNonDispatch` → `Generator`

| PyPSA field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | `name` | `direct` |
| `bus` | | The bus that `bus` points at | `derived` |
| `carrier` | | `extensions.carrier` of the `generator` record. If absent, `prime_mover_type`. Refer to [Carriers](#carriers). | `sidecar` or `derived` |
| `p_nom` | MW | `base_power` | `direct` |
| `p_max_pu` | per unit of `p_nom` | `rating` | `direct` |
| `p_min_pu` | per unit of `p_nom` | `active_power` ÷ `base_power` | `derived` |
| `marginal_cost` | cost for each MWh | For a `RenewableDispatch`, the proportional term of the value curve of `operation_cost.variable`. For a `RenewableNonDispatch`, `0.0`. | `derived` or `default` |
| `p_nom_extendable` | | `extensions.p_nom_extendable` of the `generator` record. If absent, `False`. | `sidecar` or `default` |
| `committable` | | `False` | `default` |

These two types differ from a thermal generator in three ways:

- `p_min_pu` comes from `active_power`, the initial dispatch point. A thermal generator
  takes it from `active_power_limits.min` instead, because a renewable type has no such
  field.
- `RenewableNonDispatch` has no `operation_cost`, so its `marginal_cost` is `0.0`. The
  report gives a row for that default.
- Neither type carries a unit-commitment field. The translator sets no ramp limit, no
  run-time limit, no start cost and no stop cost, so PyPSA applies its own defaults.

A `max_active_power` time series on either type becomes `p_max_pu`. Refer to
[Time series](#time-series).

## `HydroDispatch` → `StorageUnit`

A `HydroDispatch` is a generator in Sienna and a storage unit in PyPSA. This is the one
mapping where several PyPSA fields have no Sienna source.

| PyPSA field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | `HydroDispatch.name` | `direct` |
| `bus` | | The bus that `bus` points at | `derived` |
| `carrier` | | `hydro`, for every `HydroDispatch` | `default` |
| `p_nom` | MW | `base_power` | `direct` |
| `p_max_pu` | per unit of `p_nom` | `rating` | `direct` |
| `p_min_pu` | per unit of `p_nom` | `active_power_limits.min` ÷ `base_power` | `derived` |
| `marginal_cost` | cost for each MWh | The proportional term of the value curve of `operation_cost.variable` | `derived` |
| `inflow` | MW | `hydro_budget` × `base_power` | `derived` |
| `max_hours` | h | `1.0` | `default` |
| `efficiency_store` | | `1.0` | `default` |
| `efficiency_dispatch` | | `1.0` | `default` |
| `state_of_charge_initial` | MWh | `0.0` | `default` |
| `cyclic_state_of_charge` | | `False` | `default` |
| `p_nom_extendable` | | `False` | `default` |

The translator does not read the `prime_mover_type` of a `HydroDispatch`. Every one of them
gets the carrier `hydro`.

The last six rows are the lossy ones. A `HydroDispatch` states no reservoir capacity, no
round-trip efficiency and no reservoir level, so the translator supplies a PyPSA default for
each. The report gives one row for each of the six, so `decisions.md` names every hydro unit
whose storage behaviour is a default rather than your data.

The translator reads no sidecar record for a `HydroDispatch`. `p_nom_extendable` is always
`False`, even where the sidecar holds a `generator` record of the same name.

## `EnergyReservoirStorage` → `StorageUnit`

| PyPSA field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | `EnergyReservoirStorage.name` | `direct` |
| `bus` | | The bus that `bus` points at | `derived` |
| `carrier` | | `PHS`, for every `EnergyReservoirStorage` | `default` |
| `p_nom` | MW | `base_power` | `direct` |
| `max_hours` | h | `storage_capacity` | `direct` |
| `p_max_pu` | per unit of `p_nom` | `output_active_power_limits.max` | `direct` |
| `p_min_pu` | per unit of `p_nom` | `input_active_power_limits.max`, with the sign changed | `derived` |
| `efficiency_store` | | `efficiency.in` | `direct` |
| `efficiency_dispatch` | | `efficiency.out` | `direct` |
| `marginal_cost` | cost for each MWh | The proportional term of the value curve of `operation_cost.discharge_variable_cost` | `derived` |
| `state_of_charge_initial` | MWh | `initial_storage_capacity_level` × `base_power` × `storage_capacity` | `derived` |
| `cyclic_state_of_charge` | | `True` where `operation_cost.energy_shortage_cost` is above zero. If not, `False`. | `derived` |
| `p_nom_extendable` | | `extensions.p_nom_extendable` of the `storage` record. If absent, `False`. | `sidecar` or `default` |

PyPSA states charge and discharge on one `p_nom`, with a negative `p_min_pu` for the charge
side. Sienna states them as two separate limits. The translator changes the sign of the
input limit to get `p_min_pu`.

The translator does not read the `prime_mover_type`. Every `EnergyReservoirStorage` gets the
carrier `PHS`, so a battery that reached Sienna through this type comes back as pumped
storage.

A PyPSA storage unit has one `marginal_cost`, and Sienna has a charge cost and a discharge
cost. The translator reads the discharge cost. Refer to [Not translated](#not-translated).

## Carriers

The translator derives a generator carrier from the prime mover, and from the fuel as well
for a thermal generator. A `carrier` in the sidecar always wins over these tables.

`ThermalStandard`:

| `prime_mover_type` | `fuel_type` | PyPSA `carrier` |
| --- | --- | --- |
| `ST` | `COAL` | `coal` |
| `ST` | `NUCLEAR` | `nuclear` |
| `ST` | `OTHER_BIOMASS_SOLIDS` | `biomass` |
| `CC` | `NATURAL_GAS` | `CCGT` |
| `GT` | `NATURAL_GAS` | `OCGT` |
| `GT` | `DISTILLATE_FUEL_OIL` | `oil` |
| `BT` | `GEOTHERMAL` | `geothermal` |

`RenewableDispatch`:

| `prime_mover_type` | PyPSA `carrier` |
| --- | --- |
| `PVe` | `solar` |
| `WT` | `onwind` |
| `WS` | `offwind-ac` |
| `HY` | `ror` |

`RenewableNonDispatch`:

| `prime_mover_type` | PyPSA `carrier` |
| --- | --- |
| `PVe` | `solar-rooftop` |

A pair that is not in the thermal table stops the run. A prime mover that is not in the
renewable table stops it too. The translator does not guess a carrier, because a wrong
carrier would put the generator in the wrong cost and emission group.

`HydroDispatch` and `EnergyReservoirStorage` do not use these tables. They always get
`hydro` and `PHS`.

## `Line` and `MonitoredLine` → `Line`

Both Sienna types become a PyPSA line. Sienna states the rating and the impedance as
per-unit values on the system base, and PyPSA states them in physical units. Each formula
below uses a base of 100 MVA and the `v_nom` of the `bus0` end.

| PyPSA field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | `name` | `direct` |
| `bus0` / `bus1` | | The two buses that the `Arc` points at | `derived` |
| `s_nom` | MVA | `rating` × 100 | `derived` |
| `r` | Ω | `r` × `v_nom²` ÷ 100 | `derived` |
| `x` | Ω | `x` × `v_nom²` ÷ 100 | `derived` |
| `b` | S | (`b.from` + `b.to`) × 100 ÷ `v_nom²` | `derived` |
| `g` | S | (`g.from` + `g.to`) × 100 ÷ `v_nom²` | `derived` |
| `v_ang_min` | degrees | `angle_limits.min`, in radians, converted to degrees | `derived` |
| `v_ang_max` | degrees | `angle_limits.max`, in radians, converted to degrees | `derived` |
| `active` | | `available` | `direct` |
| `carrier` | | `extensions.carrier` of the `line` record | `sidecar` |
| `length` | km | `extensions.length` of the `line` record. If absent, `0.0`. | `sidecar` or `default` |
| `num_parallel` | | `extensions.num_parallel` of the `line` record. If absent, `1.0`. | `sidecar` or `default` |
| `s_nom_extendable` | | `extensions.s_nom_extendable` of the `line` record | `sidecar` |

Sienna splits the shunt susceptance and the shunt conductance between the two ends of the
line. PyPSA holds one total for each. The translator adds the two ends together.

A line with no `angle_limits` keeps PyPSA's unbounded default.

The translator takes the `v_nom` of the `bus0` end only. A line whose two ends are at
different voltages therefore gets a wrong impedance. Such a branch is a transformer, and
this translator does not handle a transformer.

Four fields come from the sidecar. A line that reaches the translator without a sidecar
record gets `length = 0.0` and `num_parallel = 1.0`, and the report says nothing about
either. Check the length of each line if you plan to use it.

## `TwoTerminalGenericHVDCLine` → `Link`

| PyPSA field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | `name` | `direct` |
| `bus0` / `bus1` | | The two buses that the `Arc` points at | `derived` |
| `p_nom` | MW | `active_power_limits_from.max`, divided by `extensions.p_max_pu` where the sidecar states one | `derived` |
| `p_max_pu` | per unit of `p_nom` | `extensions.p_max_pu` of the `controllable_line` record | `sidecar` |
| `p_min_pu` | per unit of `p_nom` | `extensions.p_min_pu` of the `controllable_line` record. If absent, `active_power_limits_from.min` ÷ `p_nom`. | `sidecar` or `derived` |
| `efficiency` | | 1 − the proportional term of `loss.function_data` | `derived` |
| `active` | | `available` | `direct` |
| `carrier` | | `extensions.carrier` of the `controllable_line` record | `sidecar` |
| `p_nom_extendable` | | `extensions.p_nom_extendable` of the `controllable_line` record | `sidecar` |

Sienna folds the PyPSA capacity and the maximum dispatch share into one number. It writes
`active_power_limits_from.max` as `p_nom` × `p_max_pu`. The translator undoes this in three
cases:

- The sidecar states no `p_max_pu`. Then `p_nom` is `active_power_limits_from.max`, and
  PyPSA's default `p_max_pu` of 1.0 holds.
- The sidecar states a `p_max_pu`. Then `p_nom` is `active_power_limits_from.max` divided by
  that share. A link stored as 500 MW with a `p_max_pu` of 0.5 comes back as a 1000 MW link.
- The stored maximum is zero. Then `p_nom` is `0.0` and `p_min_pu` is `0.0`. The report gives
  a row for that default.

Sienna forces the minimum at the from-end to zero for a link whose PyPSA `p_min_pu` was
positive. A positive lower bound therefore survives only in the sidecar.

## Time series

Sienna holds a time series as a `TimeSeriesAssociation` record in the system JSON and its
values in the HDF5 companion. The translator reads five series and leaves every other one.

| Sienna owner and series | PyPSA target | Each value is multiplied by |
| --- | --- | --- |
| `PowerLoad` `max_active_power` | `loads.p_set` | The static `max_active_power` of the load, in MW |
| `RenewableDispatch` `max_active_power` | `generators.p_max_pu` | `rating` |
| `RenewableNonDispatch` `max_active_power` | `generators.p_max_pu` | `rating` |
| `ThermalStandard` `active_power_limits` | `generators.p_max_pu` | `active_power_limits.max` ÷ `base_power` |
| `HydroDispatch` `hydro_budget` | `storage_units.inflow` | `base_power` |

The snapshots of the network come from the first profile that reaches it: the start time,
the resolution and the length of that profile.

**Every profile must cover the same snapshots.** The translator counts the values of each
profile. A profile whose count differs from the snapshot window does not go into the
network, and the component keeps its static value instead. The report records each such
profile, and the log warning names at most three profiles for each length that it found.

This direction writes at most one profile for each field of each component, because a
component has one Sienna type and each type gives one series.

## The extensions sidecar

`extensions.json` carries the PyPSA fields that SiennaSchemas has no home for. The document
is keyed by kind, and each record names the component it belongs to.

| Kind | Field | It restores | If the record or the field is absent |
| --- | --- | --- | --- |
| `bus` | `carrier` | `Bus.carrier` | The carrier is `AC`. |
| `generator` | `carrier` | `Generator.carrier` | The translator derives the carrier. Refer to [Carriers](#carriers). |
| `generator` | `committable` | `Generator.committable` | `False` |
| `generator` | `p_nom_extendable` | `Generator.p_nom_extendable` | `False` |
| `load` | `carrier` | `Load.carrier` | PyPSA's own default holds. |
| `load` | `type` | `Load.type` | PyPSA's own default holds. |
| `line` | `carrier` | `Line.carrier` | PyPSA's own default holds. |
| `line` | `length` | `Line.length` | `0.0` |
| `line` | `num_parallel` | `Line.num_parallel` | `1.0` |
| `line` | `s_nom_extendable` | `Line.s_nom_extendable` | PyPSA's own default holds. |
| `controllable_line` | `carrier` | `Link.carrier` | PyPSA's own default holds. |
| `controllable_line` | `p_nom_extendable` | `Link.p_nom_extendable` | PyPSA's own default holds. |
| `controllable_line` | `p_max_pu` | `Link.p_max_pu`, and the split of `p_nom` | PyPSA's own default of 1.0 holds, and `p_nom` is the stored maximum. |
| `controllable_line` | `p_min_pu` | `Link.p_min_pu` | The translator derives it from the stored minimum. |
| `storage` | `p_nom_extendable` | `StorageUnit.p_nom_extendable` | `False` |

Two kinds have no reader in this direction:

- `reserve`, which a PLEXOS model puts there. PyPSA has no reserve component.
- `network`, which holds the PyPSA version and the solved objective.

One field also has no reader: the `sign` of a `load` record, which is the PyPSA sign
convention.

**A record that no mapping reads is dropped, and the report says so.** The translator lists
each unread record as `NOT_MAPPED` at the end of the mapping step. Thus a reserve that
travelled from PLEXOS through Sienna stops here, and `decisions.md` names it.

The `storage` kind belongs to an `EnergyReservoirStorage` only. A `HydroDispatch` reads no
record.

## Round-trip asymmetries

Many Sienna systems come from the opposite translation. Each item below is a value that does
not come back the same. Each one is a known limit of the two formats, not a fault in your
model.

**The line voltage angle limits.** SiennaSchemas has no infinite bound, so a PyPSA line
whose `v_ang_min` and `v_ang_max` were unset goes out as ±π/2 radians. It comes back as an
explicit ±90°. A line with a finite angle limit comes back exactly. The translator cannot
tell the ±90° stand-in for "unbounded" apart from a real ±90° limit, and treating one value
as a sentinel would corrupt a line that really is limited to 90°.

**The prior on-time of a thermal generator.** The opposite direction writes
`time_at_status = 10000.0` where `up_time_before` was unset. The translator reads that
number back as `up_time_before = 0`. A real prior on-time of exactly 10000 hours, which is
417 days, is not distinguishable from the sentinel. Any other value comes back exactly.

**The storage behaviour of a `HydroDispatch`.** `max_hours`, `efficiency_store`,
`efficiency_dispatch`, `state_of_charge_initial`, `cyclic_state_of_charge` and
`p_nom_extendable` have no `HydroDispatch` field. A PyPSA storage unit with six hours of
storage and 90% efficiency comes back as a one-hour unit with 100% efficiency. The report
gives a row for each of the six.

**The carriers that share a prime mover.** Several PyPSA carriers map to one Sienna pair.
`coal` and `lignite` are both `ST` and `COAL`. `offwind-ac` and `offwind-dc` are both `WS`.
Where the sidecar holds the original carrier, it comes back exactly. Without the sidecar,
each of them comes back as the one carrier that [the table](#carriers) gives.

**The rating share of a line.** The opposite direction folds `s_max_pu` into the Sienna
`rating`. A line with an `s_max_pu` of 0.7 comes back with an `s_nom` that is 30% lower, and
with `s_max_pu` at PyPSA's default of 1.0.

**The capacity of an extendable component.** The opposite direction writes the optimised
capacity of a solved network into `base_power`. That capacity comes back as `p_nom`. The
sidecar restores `p_nom_extendable`, but the expansion bounds are gone.

**The hydro inflow.** The opposite direction divides the inflow by the dispatch efficiency.
This translator multiplies by `base_power` and assumes an efficiency of 1.0. Thus the inflow
comes back multiplied by the original `efficiency_dispatch`. A hydro unit with an efficiency
of 0.9 comes back with 90% of its inflow.

**The `max_active_power` series of a `HydroDispatch`.** The opposite direction always writes
one. This translator reads `hydro_budget` instead, and it does not read this series. The
values stay in the HDF5 companion, and the report says nothing about them.

**The charge cost of a storage unit.** PyPSA has one `marginal_cost`, and Sienna has a
charge cost and a discharge cost. The translator reads the discharge cost, and the charge
cost does not reach the network. No report row records it.

**The cyclic state of charge.** Sienna has no cyclic flag, so the opposite direction states
the state as a large `energy_shortage_cost`. This translator reads any
`energy_shortage_cost` above zero as cyclic. A system that did not come from PyPSA can
therefore get a cyclic storage unit that its author did not intend.

## Not translated

The translator reads each field the tables above name, and it leaves every other field on
the component. It writes no report row for a field it leaves, so `decisions.md` does not
name one.

| Sienna | Effect |
| --- | --- |
| `ACBus.number`, `.angle`, `.magnitude`, `.voltage_limits` | The bus keeps PyPSA's own defaults for the voltage state. |
| `ACBus.available` | Every bus goes into the network. A bus stays there even where your system marks it unavailable. |
| `ACBus.load_zone` | The zonal group is lost. The `Area` group still goes to the bus `location`. |
| `PowerLoad.available`, `.active_power`, `.reactive_power`, `.base_power`, `.max_reactive_power`, `.conformity` | This pipeline holds no reactive demand on a load. |
| `operation_cost.vom_cost` and `operation_cost.fixed` on a generator | Only the proportional term of the variable cost reaches `marginal_cost`. |
| The `constant_term` and the `input_at_zero` of any cost curve | PyPSA holds one linear cost. The other terms of the curve are lost. |
| `EnergyReservoirStorage.rating` and `.storage_target` | Nothing applies the storage target. |
| `EnergyReservoirStorage` `operation_cost.charge_variable_cost` and `.energy_surplus_cost` | The charge cost is lost. Refer to [Round-trip asymmetries](#round-trip-asymmetries). |
| `Line.rating_b` and `.rating_c` | Nothing applies the emergency ratings. The dispatch can use the normal rating only. |
| Everything a `MonitoredLine` adds to a `Line` | A `MonitoredLine` translates as an ordinary line. |
| `TwoTerminalGenericHVDCLine.active_power_limits_to`, and both reactive power limits | PyPSA holds one capacity on a link. The to-end limit is lost. |
| A transformer of any type | The translator does not carry a transformer. A branch whose two ends are at different voltages needs one. |
| A reserve of any type | PyPSA has no reserve component. A reserve in the sidecar is reported as dropped. |
| Every result field, such as `active_power_flow` | These are outputs of a solve, not model data. |

## What the report tells you

`decisions.md` gives one row for each field the translator writes. Three kinds of row
appear.

| Kind | Meaning |
| --- | --- |
| `VALUE_DERIVED` | The translator wrote the value from your data. The row gives the formula. |
| `TRANSLATOR_DEFAULT_APPLIED` | Sienna held no such value. The row gives the default and says why. |
| `NOT_MAPPED` | The value did not reach the network. This covers a profile that does not fit the snapshot window, and a sidecar record that no mapping read. |

`COMPONENT_SKIPPED` never appears in this direction. The translator leaves out no component.
A value that it cannot use stops the run instead.
[Across all components](#across-all-components) names each such value.
