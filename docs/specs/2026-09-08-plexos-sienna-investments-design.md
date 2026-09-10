# A PLEXOS expansion plan becomes a Sienna investments portfolio

## The problem

Every translation this repository makes gives an operations model. An operations model holds
a fixed fleet, so it has no place for a build cost, a build limit or a build year. Sienna
keeps investments in a separate schema with separate types, so this is a new destination, not
a flag on the dispatch path.

Four things stop the expansion data today:

- `PlexosProperty` names `Units` and `Units Out` and nothing else about building.
- The PLEXOS leg fixes every capacity on purpose, in five places. The note beside each one
  says so: "v1 translates a dispatch model, so capacity is fixed".
- A run reads the plan at one moment. `stage_plexos_xml` takes a `horizon_year` and
  `plexos_dated_properties.apply_window` narrows every dated property to the value in force,
  so a generator that is not yet built reads `Units = 0` and is dropped as retired.
- A PLEXOS `Constraint` reaches nothing. `map_constraints` reads every one and reports it as
  not carried.

The route is PLEXOS to PyPSA to Sienna. A PyPSA network that states its own expansion reaches
the same destination through the second leg alone.

## What the destination is, as it stands

`Sienna-Platform/SiennaSchemas` is the authority. Its `Investments/` namespace holds 21 types.
Four things about it decide the design, and three of them differ from what the work was
scoped against:

- There is **no `Node` and no `Zone`** under `Investments/`. `PortfolioDocument.aggregation`
  names a region type the consumer resolves, so a PLEXOS `Region` becomes a region of the base
  system, not an investments component.
- There is no `ExistingCapacity`. There is `ExistingDevices`, and it is a **supplemental
  attribute** holding names of devices in the base system, as are `RetirementPotential` and
  `TopologyMapping`. `PortfolioDocument` carries them in a flat `supplemental_attributes`
  array beside a `supplemental_attribute_associations` table.
- `TechnologyFinancialData` has **no `interest_rate`**. It requires `capital_recovery_period`,
  `technology_base_year`, `debt_fraction`, `debt_rate`, `return_on_equity` and `tax_rate`.
- `CarbonCaps` carries `target_year`, `max_mtons` and `max_tons_mwh`, and **no member list and
  no region**.

## The design

### `Max Units Built` is what makes an object a candidate

An object stating a count above zero may be built; an object stating none may not, and its
capacity stays fixed. The rule is the same for a `Generator`, a `Battery` and a
pumped-storage turbine, so one derivation serves all three.

A candidate becomes an extendable PyPSA component. `p_nom_min` is the capacity the object
already has, which a build cannot take away; `p_nom_max` is that capacity plus `Max Units
Built` units of it.

The dispatch pipelines keep writing what they write now. Every new column is null for an
object with no `Max Units Built`, and the sink omits a null column so PyPSA applies its own
default.

### PyPSA works out the annuity, so the translator does not

PyPSA 1.2 states that `overnight_cost` "takes precedence over `capital_cost`" and that PyPSA
"calculates annuity using `discount_rate` and `lifetime`". So the translator writes
`overnight_cost` from `Build Cost`, `discount_rate` from `WACC` and `lifetime` from
`Economic Life`, and never assembles a capital cost of its own. PyPSA reads `fom_cost` as a
charge for the whole modelled horizon rather than a yearly one, so the yearly `FO&M Charge`
travels in the extensions sidecar as `fom_charge_per_mw_year`.

`Economic Life` is the capital recovery period, which is the period PyPSA annuitises across.
`Technical Life` is how long the plant runs, and PyPSA has one lifetime field which the
recovery period already claims. So the technical life travels in the extensions sidecar, and
the capacity of one unit travels beside it because PyPSA sizes a candidate by `p_nom_max`
alone.

### One candidate becomes one technology

Each PLEXOS candidate object becomes its own `SupplyTechnology` or `StorageTechnology`, named
after the object. Aggregating a category into one technology would need a rule for joining
unequal build costs, discount rates and lifetimes, and no PLEXOS field states that rule. The
mappings file keeps the shape it has now; an expansion run adds rows for the candidate
categories a dispatch run leaves out.

### One run writes the portfolio and the base system it expands

`ExistingDevices.existing_devices`, `RetirementPotential.eligible_generators` and
`TopologyMapping.buses` are all lists of names in the base system. Without a base system they
point at nothing, so `pypsa-to-sienna-investments` runs the operations steps and the new
investments steps over one network and writes both documents. An extendable component that
states neither a `p_nom_opt` nor a capacity a build cannot take away is a build and nothing
else, and the operations steps report each one as skipped on that leg. An extendable
component that states one of the two keeps that capacity and stays in the base system.

### `WACC` is written as all-equity financing

`TechnologyFinancialData` requires all six of its fields and has none for a weighted average
cost of capital. The portfolio states `debt_fraction: 0`, `debt_rate: 0`, `tax_rate: 0` and
`return_on_equity` equal to the model's `WACC`. With no debt the weighted average cost of
capital equals the return on equity, so the number the model states is the number the solver
uses. It is a derivation, not a default.

### A scoped `Constraint` is left out

`CarbonCaps` names no members and no region, so a PLEXOS `Constraint` over a named subset of
generators cannot be written as one. Only a constraint whose members cover the whole model
becomes a `CarbonCaps`. Any other is left out and named in `decisions.md`, rather than written
as a cap that silently applies to more than the model meant.

### The build year rides the hub; the retirement year rides the sidecar

PyPSA carries `build_year` on Generator, StorageUnit, Line and Link, so a build year survives
the netCDF round trip as a real field. PyPSA has no retirement year, so a planned retirement
travels in the extensions sidecar, as `ExtensionKind.RESERVE` already travels for a concept
PyPSA does not hold.

Reading either one needs the whole dated `Units` series, which the `horizon_year` narrowing
throws away today, so the source stages every date band beside the value in force.

## What this does not do

- It does not translate the investment periods, the representative days or their weights.
  Those live on the model template rather than in the portfolio file, so they belong on a
  solve request beside the network model and the solver options.
- It does not write the PowerSystemsInvestments.jl JSON envelope. The product of a
  translation stays the SiennaSchemas document.
- It does not aggregate candidates by category.
- It does not translate an extendable Line or Link into a transport technology.
