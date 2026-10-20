# AETOS: how close the translation comes to the published results

This page measures how close a real OSeMOSYS model comes to its published results after the
translation into Sienna, and then into PyPSA. The model is AETOS `v2.0.0`, an OSeMOSYS model of 78 countries in Africa and
Europe. [The AETOS case study](aetos.md) gives each command, each prompt and each answer of the
runs. This page gives the numbers and their causes only.

## What we compared

For the year 2021, we compared three results:

- **The published results.** The AETOS authors publish the results of their scenario `UNNZ` in
  `AETOS_Runner/results/20260123_UNNZv2.csv`. This page calls the run of the authors the
  published run. tz-oss-interop did not solve the OSeMOSYS model itself. The commands file of
  the model, `commands_AETOS.txt`, states a solve with CPLEX.
- **The Sienna dispatch.** `osemosys-csv-to-sienna` writes a Sienna system of the 2021 fleet.
  PowerSimulations.jl dispatches it with HiGHS.
- **The PyPSA dispatch.** `sienna-to-pypsa` turns the same Sienna system and its
  `extensions.json` into a PyPSA network. PyPSA dispatches it with HiGHS.

Each results pipeline (`aetos-to-results`, `sienna-to-results` and `pypsa-to-results`) writes
the same results format. Then `compare` joins the rows by component name.

We also expanded a subset of the portfolio: five countries (`DE`, `FR`, `ES`, `IT` and `PT`) and
three years (2025, 2030 and 2035). PowerSystemsInvestments.jl solved it. We compared the build
with the published build of the same components.

## The words this page uses

| Word | What it means |
| --- | --- |
| **Trade** | The production of the lines between two countries: the energy that a line delivers at its far end |
| **A conversion line** | A line between two electricity fuels of one country, for example from `E1` to `E2`. AETOS has 156. It is neither production nor trade. |
| **An import generator** | A generator that stands for a line mode that imports electricity from outside the model. AETOS has 21. |
| **The 24 bounded gas plants** | The 24 gas plants that state a lower limit on their energy in 2021, 450.59 TWh in total |
| **The year-to-year limit** | The OSeMOSYS parameter `TechnologyActivityDecreaseByModeLimit`. The activity of a technology in one year must be at least 0.85 of its activity in the year before. |
| **A test copy** | A copy of the PyPSA network that a script outside tz-oss-interop changed, to measure one cause |

## The dispatch of 2021

The dispatch covers 96 hours: four representative days of 24 hours, one for each season. Each
results pipeline multiplies each hour by the weight of its day. Thus each value below is a value
for the whole year. The unserved energy is the total of the 96 hours, with no weight.

| Item | Published | Sienna dispatch | PyPSA dispatch |
| --- | --- | --- | --- |
| Installed capacity of the generators and the storages | 1,397.2 GW | 1,422.5 GW | 1,422.5 GW |
| Installed capacity of the lines | 171.0 GW | 171.0 GW | 171.0 GW |
| Production of the generators and the storages | 4,102.8 TWh | 3,732.6 TWh | 4,140.2 TWh |
| Trade | 389.5 TWh | 814.7 TWh | 376.9 TWh |
| Emissions | 1,459.1 Mt | 845.5 Mt | 1,702.1 Mt |
| Unserved energy in the 96 hours | none | 1,141.06 MWh | 2,367.51 MWh |
| Objective | 1.00476 × 10¹³ USD | 1.53338 × 10⁹ USD | 5.54311 × 10⁹ USD |
| Solve time | not measured | 3 min 5 s | 26.7 s |
| Solve peak memory | not measured | 2.27 GB | 1.78 GB |

The three objectives do not compare:

- The published objective is the discounted cost of the whole model over 35 years, with
  investment.
- Each dispatch objective is the operating cost of the 96 hours, with no weight for the days,
  plus 10,000 USD for each MWh of unserved energy.
- The PyPSA objective also pays for the fuels and the gas demand, which the Sienna system does
  not hold.

The installed capacity of the two dispatches includes the 21 import generators, 37.8 GW. The
published results have no such component.

In summary:

- **The PyPSA dispatch is close in production and trade.** Production is 37.3 TWh (0.9 %) above
  the published value. Trade is 12.7 TWh below it.
- **The PyPSA emissions are 243.0 Mt too high.** Two causes explain almost all of it. Refer to
  [The PyPSA dispatch](#the-pypsa-dispatch).
- **The Sienna dispatch is far from the published results.** Production is 370.3 TWh low, trade
  is 425.2 TWh high and emissions are 613.7 Mt low. Each cause is a value that a Sienna system or
  its solve cannot hold. Refer to [The Sienna dispatch](#the-sienna-dispatch).

## How the numbers moved as the translation gained features

Each row adds one feature to the row above it. The run column names the run that gave the row.
The PyPSA row from `compare3` is a test copy. The other rows come from the networks that the
pipelines wrote.

| Step | Run | Objective | Production | Trade | Emissions | `gas-combined-cycle` | `coal` | Unserved energy |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Sienna dispatch | `compare3` | 1.53357 × 10⁹ USD | 3,732.6 TWh | 815.2 TWh | 847.3 Mt | 217.9 TWh | 735.1 TWh | 1,141.06 MWh |
| PyPSA, with the same features as Sienna: no annual bounds, and lines with no cost and no loss | `compare3`, test copy | 1.52715 × 10⁹ USD | 3,728.5 TWh | 872.8 TWh | 838.4 Mt | 216.6 TWh | 730.6 TWh | 1,141.06 MWh |
| PyPSA, with the annual bounds, the line cost and the line loss | `compare4` | 1.84617 × 10⁹ USD | 3,744.5 TWh | 400.1 TWh | 759.9 Mt | 510.3 TWh | 526.5 TWh | 1,141.06 MWh |
| PyPSA, with the fuels that are not electricity | `carriers` | 5.11255 × 10⁹ USD | 3,744.5 TWh | 399.8 TWh | 1,441.5 Mt | 490.7 TWh | 527.7 TWh | 1,141.06 MWh |
| PyPSA, with one bus for each electricity fuel and the import generators | `busfuel` | 5.54311 × 10⁹ USD | 4,140.2 TWh | 376.9 TWh | 1,702.1 Mt | 546.0 TWh | 756.3 TWh | 2,367.51 MWh |
| Published | | none | 4,102.8 TWh | 389.5 TWh | 1,459.1 Mt | 547.9 TWh | 568.2 TWh | none |

The Sienna dispatch of the `busfuel` run holds the import generators too. It gives
1.53338 × 10⁹ USD, 3,732.6 TWh, 814.7 TWh of trade and 845.5 Mt.

What each step shows:

1. **The PyPSA network carries the Sienna system correctly.** With the same features, the two
   solvers agree to 0.4 % in the objective, 0.1 % in production and 1 % in emissions. Trade
   differs by 58 TWh, because many flows have the same cost on a line with no cost and no loss.
2. **The annual bounds, the line cost and the line loss move PyPSA towards the published
   results.** Trade falls by 472.8 TWh. `gas-combined-cycle` makes 293.7 TWh more, and `coal`
   makes 204.2 TWh less.
3. **The fuels that are not electricity add the emissions of each fuel supply.** Each fuel
   supply now emits, as in OSeMOSYS. The emissions rise by 681.5 Mt, to 17.7 Mt below the published value.
   Production and trade change by less than 0.1 %.
4. **The conversion lines add the conversion loss.** The 156 conversion lines lose 398.1 TWh in
   the year, so the plants make that much more. Production goes from 358.3 TWh below the
   published value to 37.3 TWh above it. Most of the extra production comes from coal, so the
   emissions rise by 260.7 Mt.

After step 3, the PyPSA coal was 527.7 TWh, near the published 568.2 TWh. That agreement was by
chance. Step 4 adds 395.7 TWh of production, and coal takes 228.6 TWh of it.

## The causes of the remaining differences

### The PyPSA dispatch

These causes are in order of size.

**1. The year-to-year limit: 188.8 TWh of coal and 135.8 Mt.** The translation does not apply
`TechnologyActivityDecreaseByModeLimit`. In AETOS, this limit is 0.15 for every year, on 187 fuel
supply technologies: coal, lignite, gas extraction, LNG and gas pipelines. The evidence:

- In the published results, the 2022 activity of each European coal and lignite supply with
  activity in 2021 is 0.850 of its 2021 activity. Thus the limit binds.
- Each PJ of coal in 2021 forces 0.85 PJ in 2022. The CO2 penalty of 2022 is 88 USD/t, against
  66 USD/t in 2021. Thus coal of 2021 has a future cost in OSeMOSYS, which a one-year dispatch
  does not have.
- The published run runs dearer plants and leaves cheaper coal idle. For example, `DELIELH1`
  (lignite, 104.6 USD/MWh) runs at a capacity factor of 0.06 in the published results and 0.54
  in PyPSA.
- `decisions.md` of the translation records `technology_activity_decrease_by_mode_limit` with
  "no step of the pipeline applies this parameter".

In a test copy, each coal and lignite supply generator took an `e_sum_max` equal to its
published 2021 activity. Coal fell from 756.3 TWh to 567.5 TWh, and the emissions fell by
135.8 Mt.

**2. The 24 bounded gas plants: 108.5 Mt, and no coal.** A PyPSA link has no `e_sum_min`. Thus
each of the 24 bounded gas plants stays a generator on its electricity bus, and does not draw gas
from its gas bus. The plants burn 2,846 PJ of gas that the gas network does not supply. The
network then imports less gas through the pipelines from `UA` and `AL`. In AETOS, each such
pipeline states a positive emission in the country that receives the gas, and the same negative
emission in `UA` or `AL`. PyPSA counts the full emission of the gas that the 24 plants burn, with
no negative emission against it. In a test copy, each of the 24 plants also took its gas from its
gas bus. The emissions fell from 1,702.3 Mt to 1,593.8 Mt, and coal did not change.

With both corrections in one test copy, PyPSA gave 567.5 TWh of coal and 1,449.4 Mt. The
published values are 568.2 TWh and 1,459.1 Mt.

**3. The imports from outside the model.** The 21 import generators make 5.5 TWh. The 21 lines
that import from outside the model carry 69.4 TWh in the published results. `HUELUAPH1` alone
carries 15.97 TWh.

**4. The categories that still differ after both corrections.** In the test copy with both
corrections:

- `gas-steam` is 37.6 TWh above the published value.
- `oil-steam` is 33.8 TWh below it.
- `biomass` is 18.4 TWh below it.
- `nuclear` is 15.0 TWh below it.

The year-to-year limit also holds gas extraction, LNG and the gas pipelines. This can explain
part of the `gas-steam` difference. We did not test it.

**5. The residual fleet.** The system holds the residual capacity of 2021 only. The published
run builds 3.06 GW of power plants in 2021, of which 2.5 GW is `ZAWINDPN1`. `MR` and `GW` are
short of their peak load, so the dispatch leaves 2,367.51 MWh unserved in the 96 hours. Of this,
2,307.86 MWh is at `REGION1/MRE3`. These countries must also cover their conversion loss.

**6. The storage.** Pumped storage has 42.9 GW, against 51.65 GW published, because a Sienna
storage is rated on its electricity output. It makes 0.60 TWh, against 0.05 TWh published. The
storage units are not cyclic, so the dispatch can empty the level that they hold at the start.
The results then multiply each hour of that output by the weight of its day.

### The Sienna dispatch

These causes are in order of size. Each is a value that the Sienna system has no field for, or
that the solve formulation ignores.

**1. The emission scope: 613.7 Mt.** The Sienna system holds electricity only. Thus the Sienna
emissions are those of the power plants only. The published emissions also count the CO2 of each
fuel that enters a country. Two transit countries state negative emissions: `UACO2` is
−128.72 Mt and `ALCO2` is −43.49 Mt.

**2. The line cost and the line loss: 425.2 TWh of trade.** A `TwoTerminalGenericHVDCLine` has no
cost field. The solve uses `HVDCTwoTerminalLossless`, which ignores the loss of a line. Thus trade
is free. In the `compare3` test copies of the PyPSA network with the annual bounds, the line
cost and the line loss lower the trade by 475.4 TWh.

**3. The conversion loss: 370.3 TWh of production.** Each conversion is a line with its loss.
The Sienna solve ignores the loss, so the plants do not make the 398.1 TWh that the conversions
lose in PyPSA.

**4. The annual energy limits: 330.6 TWh of `gas-combined-cycle`.** A Sienna system has no field
for a limit on the energy of a year. The 24 bounded gas plants make 73.8 TWh, against their lower
limit of 450.59 TWh. In the `compare3` test copies of the PyPSA network with the line cost and
the line loss, the annual bounds add 295.7 TWh of `gas-combined-cycle`, remove 213.9 TWh of
`coal`, and lower the emissions by 97.9 Mt.

**5. The storage: 8.8 TWh of pumped storage.** Pumped storage makes 8.87 TWh, against 0.05 TWh
published. The dispatch runs the days in time order and carries the level from one day to the
next.

**6. The residual fleet.** As in PyPSA, `MR` and `GW` are short of their peak load. The dispatch
leaves 1,141.06 MWh unserved in the 96 hours: 1,121.94 MWh in `MR` and 19.12 MWh in `GW`.

[The gap analysis](../translation_mappings/osemosys-to-sienna-gap-analysis.md) gives one entry for
each loss, with its cause and its effect.

## What Sienna cannot hold, and PyPSA can

The `sienna-to-pypsa` pipeline reads `extensions.json` beside the Sienna system. It gives each
value that PyPSA has an attribute for to that attribute.

| OSeMOSYS data | In the Sienna dispatch | In the PyPSA dispatch |
| --- | --- | --- |
| `TotalTechnologyAnnualActivityLowerLimit` and `UpperLimit` | No field. The 24 bounded gas plants make 73.8 TWh. | `Generator.e_sum_min` and `e_sum_max`. The 24 plants make 453.0 TWh, against 452.6 TWh published. |
| `VariableCost` of a line | No field. Trade is free. | `Link.marginal_cost` |
| The loss of a line | The solve ignores it. | `Link.efficiency`, in each direction. The transport lines lose 21.1 TWh in the `compare4` run. The conversion lines lose 398.1 TWh. |
| The fuels that are not electricity, and their technologies | No component | Buses, generators, links and loads. The emissions of each fuel supply count. |
| The price of a fuel | The cost of the cheapest producer in the region | 539 plants draw their fuel from a bus, and the network prices the fuel. |
| The demand for gas | No component | A `Load` on the bus of the gas of each country, 3,709 TWh in the year |

The gap analysis section
[What a PyPSA dispatch holds](../translation_mappings/osemosys-to-sienna-gap-analysis.md#what-a-pypsa-dispatch-holds)
gives every entry.

## The expansion subset

The subset holds 92 supply technologies and 2 transport technologies. The expansion solve gave
the run status `SUCCESSFULLY_FINALIZED` and the objective 3.17745 × 10¹⁰ USD. It took 2 min 49 s
and 2.18 GB of memory.

The totals are those of the 211 components that the expansion results name. The published values
are those of the same components:

| Item | Year | Published | Expansion |
| --- | --- | --- | --- |
| Installed capacity | 2025 | 684.7 GW | 532.1 GW |
| Installed capacity | 2030 | 809.9 GW | 542.5 GW |
| Installed capacity | 2035 | 948.8 GW | 542.5 GW |
| New capacity | 2025 | 43.3 GW | 23.7 GW |
| New capacity | 2030 | 56.1 GW | 10.4 GW |
| New capacity | 2035 | 48.6 GW | 0.0 GW |
| Production | 2025 | 1,740.8 TWh | 1,649.7 TWh |
| Production | 2030 | 2,042.3 TWh | 1,942.4 TWh |
| Production | 2035 | 2,158.4 TWh | 2,068.6 TWh |

Over the three years, the published run builds 64.8 GW of onshore wind and 64.8 GW of solar in
the five countries. The expansion builds 25.3 GW and 8.9 GW of two biomass technologies, and
almost nothing else. These causes apply:

- PowerSystemsInvestments.jl reads no availability profile for a thermal candidate. Thus a
  biomass plant can run at its full capacity in every hour.
- No emission limit binds. The package builds no constraint from `CarbonCaps`.
- The existing fleet does not retire. The package holds the existing capacity of the first year
  in every period.
- The years between two periods carry no operations.
- Trade has no loss, and a line flows both ways.

We did not measure the effect of each cause by itself. The published run optimises all 78
countries over 35 years. Thus these totals are an observation, and not a test of the
translation. The full model did not solve in 16 GB of memory.
[Running a capacity expansion](../developer_documentation/capacity-expansion.md#what-does-not-work)
gives each limit of the package.

## Open decisions

Two decisions remain open. Each one removes one difference of the PyPSA dispatch.

- **An annual limit on a PyPSA link, applied in the solve.** A PyPSA link has no `e_sum_min` or
  `e_sum_max`. The `solve` command could add the limit as a constraint of its own. Then each of
  the 24 bounded gas plants can be a link that draws gas from its gas bus. This removes the
  108.5 Mt of cause 2. It also applies the 85 annual bounds of the pipelines and the LNG
  terminals, which the PyPSA network now leaves out.
- **The year-to-year limit.** A network of one year cannot hold a limit between two years. The
  options are to record the difference only, to set an `e_sum_max` from the activity of a
  results file, or to translate a range of years and add the limit in the solve. This removes
  the 188.8 TWh of coal and the 135.8 Mt of cause 1.

## The limits of this comparison

- **One year.** The dispatch covers 2021 only. The published results come from a solve of 35
  years.
- **Representative days.** The dispatch covers four days of 24 hours, one for each season. The
  model states 16 timeslices.
- **The residual fleet.** The system holds the residual capacity of 2021. It holds no capacity
  that the published run builds.
- **No OSeMOSYS solve of our own.** tz-oss-interop did not solve the OSeMOSYS model. Each
  published value comes from the published run.
- **Test copies.** The measured effect of each cause comes from a test copy of the network. A
  script outside tz-oss-interop made each copy.
