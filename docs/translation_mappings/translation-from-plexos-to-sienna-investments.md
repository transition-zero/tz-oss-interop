# Translation from PLEXOS to a Sienna investments portfolio

This document tells you what each part of your PLEXOS expansion plan becomes in the Sienna
portfolio. It gives the source of each field.

> **Scope:** the translator accepts electricity-only models. It translates what your plan may
> build, not when it builds it: it does not carry the investment periods, the representative
> days or their weights. It does not translate an expansion of a transmission line, and it
> writes no aggregation of candidates by category. Refer to
> [Not translated](#not-translated) and to
> [the gap analysis](plexos-to-sienna-gap-analysis.md), which states what each loss does to an
> expansion.

One run of `plexos-to-sienna-investments` writes **two documents**. `system.json` is the base
power system: the fleet that already runs. `portfolio.json` is the expansion problem: the
technologies a plan may build, the demand they have to meet, and the caps they run under. The
portfolio names the system in its `base_system_file`, so the two are read together.

The pipeline runs through a PyPSA network on the way. This document does not describe that
network. It states the mapping as one step, because that is what you give and what you get.
Where the intermediate form loses something, this document says so.

---

## What becomes what

| PLEXOS | Sienna investments |
| --- | --- |
| [`Generator` that may be built](#generator-that-may-be-built--supplytechnology) | `SupplyTechnology` |
| [`Battery` that may be built](#battery-or-pumped-storage-that-may-be-built--storagetechnology) | `StorageTechnology` |
| [Pumped-storage turbine that may be built](#battery-or-pumped-storage-that-may-be-built--storagetechnology) | `StorageTechnology` |
| [`Region`](#region--the-portfolios-regions) | The region each technology sits in, and a `TopologyMapping` naming its nodes |
| [Region `Load`](#region-load--demandrequirement) | `DemandRequirement` |
| [`Constraint`](#constraint--carboncaps) | `CarbonCaps`, but only where its members cover the whole model |
| [A plant that already runs](#a-plant-that-already-runs--existingdevices-and-retirementpotential) | `ExistingDevices` and `RetirementPotential` on the technology of its carrier |
| Everything else | A component of the base system. Refer to [translation-from-plexos-to-sienna.md](translation-from-plexos-to-sienna.md). |

## Reading the tables

| Mapping | Meaning |
| --- | --- |
| `direct` | The translator uses your PLEXOS value without a change. |
| `derived` | The translator calculates the value from your values, with the formula that the table gives. |
| `default` | PLEXOS has no such data. The translator supplies this value. |
| `dropped` | The Sienna investments schema has no equivalent. The value does not go into the portfolio. |
| `mapped by you` | Your carrier mappings file gives the value. |
| `parameter` | The run gives the value. Refer to [The base year](#the-base-year). |

## Across all components

- **`Max Units Built` is what makes an object a candidate.** An object stating a count above
  zero may be built and becomes a technology. An object stating none may not, and its capacity
  is fixed: it belongs to the base system alone.
- **One candidate becomes one technology, named after the object.** The translator does not
  join a category of objects into one technology, because no PLEXOS field states how to
  average unequal build costs, discount rates and lifetimes.
- **A build the plan has yet to decide is not a plant.** An object that runs no units yet is
  in the portfolio and not in the base system. An object that runs some units and may build
  more is in both: the base system rates it at the units it runs, and the portfolio's
  `capacity_limits.min` is that same capacity, which a build cannot take away.
- **A candidate whose carrier your mappings file does not name is left out.** The run
  completes and `decisions.md` names each one.
- **A generator candidate names one of four base system types.** Your mappings file must send
  its carrier to `ThermalStandard`, `RenewableDispatch`, `RenewableNonDispatch` or
  `HydroDispatch`, and a `ThermalStandard` row also states the `sienna_fuel_type`. A `Battery`
  candidate and a pumped-storage candidate need no row of their own, because the mappings
  pipeline supplies a `storage_kind` row for all three storage kinds.
- **A candidate whose carrier your mappings file sends to another kind's type is left out.**
  A generator becomes a `SupplyTechnology` and a battery or a pumped-storage turbine becomes a
  `StorageTechnology`, so a carrier sent to a base system type the other kind holds names a
  type the technology never becomes. The run completes and `decisions.md` names each one.
- **A candidate that prices no build is already gone.** The PLEXOS to PyPSA leg leaves out a
  candidate with no `Build Cost`, no `WACC` or no `Economic Life`, because PyPSA cannot
  annuitise a cost without all three. `decisions.md` names each one.

## `Generator` that may be built → `SupplyTechnology`

| Sienna field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | `Generator.name` | `direct` |
| `power_systems_type` | | The base system type your mappings file sends the generator's `Fuel` or category to | `mapped by you` |
| `prime_mover_type` | | Your mappings file | `mapped by you` |
| `fuel` | | Your mappings file, for a thermal type only. A renewable or hydro type names none. | `mapped by you` |
| `region` | | The `Region` that contains the generator's `Node` | `derived` |
| `capacity_limits.min` | MW | `Max Capacity × Units`: the capacity a build cannot take away | `derived` |
| `capacity_limits.max` | MW | `Max Capacity × (Units + Max Units Built)` | `derived` |
| `unit_size` | MW | `Max Capacity`: what one unit of the candidate is | `direct` |
| `capital_costs.capital_cost` | $/MW | `Build Cost`, as the slope of a linear cost curve | `derived` |
| `capital_costs.interconnection_cost` | $ | `0.0`. PLEXOS prices no last-mile connection separately. | `default` |
| `operation_costs.fixed` | $/MW/yr | `FO&M Charge` | `direct` |
| `operation_costs.cost_type` | | `THERMAL` where the base system type is `ThermalStandard`, `HYDRO_GEN` where it is `HydroDispatch`, `RENEWABLE` otherwise | `derived` |
| `operation_costs.start_up`, `shut_down` | $ | `0.0`, and only for a `THERMAL` cost. The other two cost representations state neither. | `default` |
| `operation_costs.variable_operation_cost` | | A zero curve. The `VO&M Charge` and the fuel price price the component in the base system, not the build. | `default` |
| `lifetime` | yr | `Technical Life`: how long a built unit runs | `direct` |
| `financial_data.capital_recovery_period` | yr | `Economic Life`: the period the build cost is recovered over | `direct` |
| `financial_data.return_on_equity` | | `WACC`. Refer to [WACC is written as all-equity financing](#wacc-is-written-as-all-equity-financing). | `derived` |
| `financial_data.debt_fraction`, `debt_rate`, `tax_rate` | | `0`, as the same rule requires | `default` |
| `financial_data.technology_base_year` | | The run's `base_year` | `parameter` |
| `available` | | `true` | `default` |
| `outage_factor` | | `Forced Outage Rate` and `Maintenance Rate` derate the component in the base system, not the technology. | `dropped` |
| `min_generation_fraction`, `ramp_limits`, `time_limits`, `start_fuel_mmbtu_per_mw` | | The base system carries the operating characteristics. | `dropped` |
| `cofire_start_limits`, `cofire_level_limits` | | PLEXOS multi-fuel blending is not translated. | `dropped` |
| `requirements` | | A `CarbonCaps` this translator writes holds the whole portfolio, so it names no members and no technology names it. | `dropped` |

## `Battery` or pumped storage that may be built → `StorageTechnology`

A Sienna storage technology adds charge power, discharge power and energy independently. A
PLEXOS `Battery` states one `Max Power` and one `Capacity`, and a pumped-storage plant one
`Max Capacity` and one reservoir volume, so the discharge side carries the rating and the
cost and the energy side is derived from the two.

| Sienna field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | `Battery.name`, or the turbine `Generator.name` | `direct` |
| `power_systems_type` | | The base system type your mappings file sends the storage kind to | `mapped by you` |
| `prime_mover_type` | | Your mappings file (`BA` for a `Battery`, `PS` for pumped storage, by the rows the mappings pipeline derives) | `mapped by you` |
| `storage_tech` | | `OTHER_MECH`. PLEXOS names no chemistry, and `StorageTech` has no value for an unstated one. | `default` |
| `region` | | The `Region` that contains the object's `Node` | `derived` |
| `capacity_limits_discharge.min` / `.max` | MW | `Max Power × Units` and `Max Power × (Units + Max Units Built)` | `derived` |
| `capacity_limits_energy.min` / `.max` | MWh | The discharge limits multiplied by the object's storage hours (`Capacity ÷ Max Power` for a `Battery`) | `derived` |
| | | A candidate whose storage hours come out at zero is left out, since a build could add power it can never charge. A candidate whose storage hours are not a finite number is left out too, since the energy a build may add has no upper bound. `decisions.md` names each one. | |
| `unit_size_discharge` | MW | `Max Power`: what one unit of the candidate is | `direct` |
| `capital_costs.discharge_capital_cost` | $/MW | `Build Cost`, as the slope of a linear cost curve | `derived` |
| `capital_costs.charge_capital_cost`, `energy_capital_cost` | | Zero curves. PLEXOS prices the object by its power, so it states no separate price for charging or for energy. | `default` |
| `operation_costs.fixed` | $/MW/yr | `FO&M Charge` | `direct` |
| `efficiency.in` / `.out` | | `Charge Efficiency` or `Pump Efficiency`, read as a round trip and split evenly | `derived` |
| `lifetime` | yr | `Technical Life` | `direct` |
| `financial_data` | | As for a [`SupplyTechnology`](#generator-that-may-be-built--supplytechnology) | |
| `unit_size_charge`, `unit_size_energy` | | PLEXOS sizes one unit by its power alone. | `dropped` |
| `capacity_limits_charge` | | PLEXOS builds charging and discharging together. | `dropped` |
| `duration_limits`, `losses`, `min_discharge_fraction` | | The base system carries the operating characteristics. | `dropped` |

## `Region` → the portfolio's regions

The portfolio does not hold its regions as components of its own: `aggregation` names the base
system type they are, which is `Area`, and each technology's `region` is a list of `Area` ids
in that system. Each `Region` of your model is one `Area` there.

Each region also gets a `TopologyMapping`, a supplemental attribute holding the names of the
nodes in it, so a consumer can place the region's technologies on the base system's buses.

## Region `Load` → `DemandRequirement`

The translator writes one `DemandRequirement` for each demand of the base system, naming the
region it is drawn in.

| Sienna field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | `<Region>_load`, the name the demand has in the base system | `direct` |
| `power_systems_type` | | The base system type the demand is held as: `InterruptiblePowerLoad` where the region prices a shortfall, `PowerLoad` otherwise | `derived` |
| `region` | | The `Region` that contains the demand's node | `derived` |
| `available` | | `true` | `default` |
| `new_demand_mw`, `new_construction_year`, `growth_rate`, `conformity` | | These describe a demand a plan adds. The demand your model states is one the base system already holds, with its own profile. | `dropped` |
| `value_of_lost_load`, `unserved_demand_curve` | | The region's `VoLL` prices the load in the base system on a reliability run. | `dropped` |

## `Constraint` → `CarbonCaps`

`CarbonCaps` carries a target year and a limit, and **names no members and no region**: a cap
in a portfolio holds the whole portfolio. So only a `Constraint` whose members cover the whole
model becomes one. The whole model is every generator and storage object the two documents
hold: the plants in the base system and the candidates in the portfolio. An object neither
document holds emits nothing a cap could bound, so a constraint need not name it.

| Sienna field | Unit | From | Mapping |
| --- | --- | --- | --- |
| `name` | | `Constraint.name` | `direct` |
| `max_mtons` | Mt | The `RHS Year`, or the `RHS` where the constraint states no yearly limit | `derived` |
| `available` | | `true` | `default` |
| `target_year` | | PLEXOS states the span a right-hand side applies over, not the year it applies in. | `dropped` |
| `max_tons_mwh` | | PLEXOS has no rate-based right-hand side. | `dropped` |

Five kinds of `Constraint` are left out, each named in `decisions.md`:

- one whose `Include in LT Plan` is false, because the expansion plan does not have to meet
  it, and a cap written from it would bound a problem the model leaves free;
- one whose members cover only part of the model, because a cap written from it would hold
  more than the model meant;
- one whose `Sense` is not `<=`, because a cap is a ceiling and nothing else;
- one stating neither an `RHS Year` nor an `RHS`, because no other span bounds the whole run;
- one whose right-hand side is not a finite number, because a cap states a number of
  million tonnes, and neither NaN nor Infinity is one.

Every `Constraint` still reaches `extensions.json` unchanged, whether or not it became a cap.

## A plant that already runs → `ExistingDevices` and `RetirementPotential`

A technology stands for more of what its own region already runs. So for each technology, the
translator writes two supplemental attributes naming the base system's components that share
both its carrier and its region:

| Sienna field | From | Mapping |
| --- | --- | --- |
| `ExistingDevices.existing_devices` | The base system components sharing the technology's carrier and region | `derived` |
| `RetirementPotential.eligible_generators` | The same list | `derived` |
| `RetirementPotential.build_year` | The first year the object's dated `Units` rise above zero, per object | `derived` |
| `RetirementPotential.planned_retirement_year` | The first year the object's dated `Units` fall back to zero, per object | `derived` |
| `RetirementPotential.retirement_cost` | A zero curve. PLEXOS prices no retirement. | `default` |

A technology that no such base system component matches gets neither attribute.

## Special business rules

### `WACC` is written as all-equity financing

`TechnologyFinancialData` requires all six of its fields and has none for a weighted average
cost of capital. So the portfolio states `debt_fraction: 0`, `debt_rate: 0`, `tax_rate: 0` and
a `return_on_equity` equal to your `WACC`. With no debt the weighted average cost of capital
equals the return on equity, so the number your model states is the number the solver uses.
It is a derivation, not a default, and `decisions.md` records it as one.

### A scoped `Constraint` is left out

Refer to [`Constraint` → `CarbonCaps`](#constraint--carboncaps). Writing a cap from a
constraint over part of the model would apply that limit to the whole portfolio, which is a
different problem from the one your model states. Leaving it out and naming it is the safer
answer.

### The base year

`PortfolioFinancialData.base_year` and each technology's `financial_data.technology_base_year`
are the economic year a cost is quoted in. No PLEXOS field and no PyPSA field states one, so
both come from the `base_year` parameter of the `pypsa_to_sienna_investments_map_technologies`
step. It defaults to **2020**, which is the year SiennaSchemas itself defaults a construction
year to. Set it to the dollar year your `Build Cost` and `FO&M Charge` are quoted in.

A chained pipeline prompts for the source of its first leg and the sinks of its last, and for
no step in between, so a `plexos-to-sienna-investments` run always takes the default. To state
another year, run the two legs yourself: `plexos-to-pypsa`, then `pypsa-to-sienna-investments`
over the network and the sidecar it wrote. The second leg prompts for its steps, so the base
year is the `base_year` of `step[2]`. That leg also asks for a mappings file in PyPSA words,
which the chain derives from your PLEXOS file and a lone run cannot, so write a `carriers`
file with one `pypsa_carrier` row for each carrier the first leg wrote, the storage carriers
included.

### What the PyPSA hub cannot carry

The route runs through a PyPSA network, and three values have no PyPSA column:

| PLEXOS | How it crosses the hub |
| --- | --- |
| `Max Capacity` or `Max Power` as the size of one unit | The extensions sidecar, as `unit_size_mw`. PyPSA sizes a candidate by `p_nom_max` alone. |
| `Technical Life` | The extensions sidecar, as `technical_life_years`. PyPSA has one lifetime field, and the capital recovery period claims it. |
| The year a dated `Units` falls to zero | The extensions sidecar, as `retirement_year`. PyPSA carries a build year and nothing for the other end of a life. |

The build year rides the hub as PyPSA's own `build_year`, so it survives the netCDF round trip
as a real field. A run that loses the sidecar loses the three values above, and the portfolio
then states no unit size, takes the schema's own default lifetime of 100 years, and names no
planned retirement.

### Units and rounding

The unit rules of the dispatch translation apply here too: refer to
[translation-from-plexos-to-sienna.md](translation-from-plexos-to-sienna.md#unit-conversions).
Two more apply to the expansion fields:

| Value | Read in |
| --- | --- |
| `Build Cost` | $/MW, from the unit your model declares for it |
| `FO&M Charge` | $/MW/yr, from the unit your model declares for it |
| `WACC` | A fraction, read from a percentage where your model declares one |

`max_mtons` is read in million tonnes. The translator applies **no conversion** to the
constraint's right-hand side: it writes the number your model states and records the unit your
model named it in.

## Not translated

| PLEXOS | Effect |
| --- | --- |
| Investment periods, and the years a plan steps through | The portfolio states one expansion problem, not a schedule. These belong on the solve request beside the model. |
| Representative days and their weights | As above. |
| An expandable `Line` or transformer | No transport technology is written, so the plan cannot build transmission. |
| `Max Units Built` on anything other than a `Generator`, a `Battery` or a pumped-storage turbine | The object's capacity is fixed. |
| A category of candidates as one technology | Each candidate is its own technology. |
| `Constraint` over part of the model | Refer to [`Constraint` → `CarbonCaps`](#constraint--carboncaps). |
| Emission objects and their prices | The carbon price reaches the base system's operating cost. No `Emission` becomes a cap. |
| Retirement costs | `RetirementPotential.retirement_cost` is zero. |

## Assumptions worth checking against your model

The translator reads these values in a particular way. If your model uses a different
convention, the translator gives wrong values.

| Value | Assumed as |
| --- | --- |
| `Max Units Built` | The count of units the plan may add on top of `Units`, not the total it may reach |
| `Max Capacity`, `Max Power` | The rating of one unit, so a candidate's ceiling is that rating times the units it may hold |
| `Build Cost` | An overnight cost per MW, which the solver annuitises. It is not an annuitised cost already. |
| `Economic Life` | The period the build cost is recovered over, which is not how long the plant runs |
| `Technical Life` | How long a built unit runs |
| `WACC` | A cost of capital with no debt in it |
| A `Constraint` right-hand side | Already in million tonnes, if you read the cap as a mass of CO2 |
| A `Fuel` name or a category | One technology. Two names are two technologies, even where they are one chemistry. |
