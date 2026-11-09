# What SiennaSchemas needs to hold AETOS

Each item names one thing that AETOS does, and the reason that SiennaSchemas has no place for it.
[The AETOS case study](aetos.md) gives the measured effects.

## The system

1. **A minimum energy for each year.** AETOS makes 24 gas plants produce a minimum energy in each
   year, for example 450.59 TWh in total in 2021. A `ThermalStandard` states only its power limits
   for each hour, and has no field for the energy of a period.
2. **The cost of a line.** AETOS charges 10.00 USD for each MWh that a line between two countries
   carries. A `TwoTerminalGenericHVDCLine` states a loss and its ratings, but no cost.
3. **Timeslices with a weight.** AETOS divides each year into 16 timeslices: 4 seasons, each with
   4 parts of a day. Each timeslice has a share of the year. `SystemDocument` holds each time
   series as a sequence of hours, and has no field for the weight of an hour or a day.
4. **An emission limit for each country.** From 2030, AETOS limits the CO2 of each of its 78
   countries: 1,546 Mt in total in 2030, and 0 in 2050. The operations schemas have no emission
   limit, so a system of a year from 2030 cannot hold it.

## The portfolio

5. **Costs that change by year.** AETOS changes the capital cost of 1,478 technologies from year
   to year. For example, the capital cost of `DESOUTPH1`, utility solar in Germany, falls from
   830 to 643 USD/kW. A `CapitalCost` has one cost curve, and `operation_costs` has one value,
   with no year.
6. **A limit on the build of each year.** AETOS limits the new capacity of 2,240 technologies in
   each year. For example, `DESOUTPH1` can build 5.95 GW in 2022, and none in 2021 or 2023. It
   also makes 430 technologies build a minimum, for example 2.495 GW of `ZAWINDPN1` in 2021.
   `SupplyTechnology` and `StorageTechnology` limit the installed capacity only, and have no field
   for the build of one year.
7. **The cost of a transport candidate.** AETOS charges 10.00 USD for each MWh that a new line
   carries. An `AggregateTransportTechnology` states a capital cost and a loss, but no cost for
   each MWh.
8. **A weight for each technology in the reserve margin.** AETOS states a reserve margin of 1.0
   to 2030, and 1.1 from 2031. Each country has a table of its yearly peak, and a table that
   gives each technology a weight of 0, 0.05 or 1. A `RequirementAssociation` links a
   `CapacityReserveMargin` to a member, but has no field for the weight of that member.

## Out of scope

- **Fuels that are not electricity.** AETOS models gas production, gas pipelines and gas demand.
  It also limits the gas that each country extracts, over each year and over the whole model
  period, and the gas that each pipeline carries. SiennaSchemas has a bus for electricity only.
  The Sienna system holds electricity only, and `extensions.json` holds each other fuel.
