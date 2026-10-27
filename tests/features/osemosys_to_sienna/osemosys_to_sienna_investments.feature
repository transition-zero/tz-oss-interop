@slow @fork_unsafe
Feature: osemosys-csv-to-sienna-investments writes a Sienna investments portfolio beside the base system
  The operations step writes the base system: the fleet of the earliest year in scope. The
  portfolio step reads the model again over every year in scope. A technology that a plan may
  build becomes a candidate technology. The demand of each load gets one series for each year.
  A limit on a pollutant that every emitting technology emits becomes a CarbonCaps for each
  year.

  The invented model below has the years 2030 and 2035, and the locations AT and DE. The gas
  plant ATGASCC exists in 2030, retires in 2035, and a plan may build more of it. The new gas
  plant ATGASNEW and the solar plant ATSOLAR have a capital cost and room to build, so each is a
  candidate. The solar plant ATLATESOLAR states its output and a capital cost in 2035 only. The biomass plant
  ATBIO has a capital cost but no carriers: row. The gas plant ATLOCKGASCC has a capital cost but
  no investment is allowed in any year. The gas plant ATFULLGASCC has a capital cost but its
  maximum capacity is its residual capacity in each year. The interconnector ATDELINK has a
  capital cost and no residual capacity. ATGASCC and ATGASNEW emit CO2. Only ATGASCC emits
  ATNOX.

  Background:
    Given an otoole model
    And the otoole set "REGION" holds "R1"
    And the otoole set "FUEL" holds "ATELEC DEELEC ATGAS"
    And the otoole set "YEAR" holds "2030 2035"
    And the otoole set "TIMESLICE" holds "S1B1 S1B2 S2B1 S2B2"
    And the otoole set "SEASON" holds "S1 S2"
    And the otoole set "DAYTYPE" holds "1"
    And the otoole set "DAILYTIMEBRACKET" holds "B1 B2"
    And the otoole set "TECHNOLOGY" holds "ATGASCC ATGASNEW ATSOLAR ATLATESOLAR ATBIO ATLOCKGASCC ATFULLGASCC ATDELINK ATGASWELL"
    And the otoole set "EMISSION" holds "CO2 ATNOX"
    And the otoole set "MODE_OF_OPERATION" holds "1"
    And the otoole parameter "YearSplit" keyed by "TIMESLICE YEAR" with default 0 has the rows:
      | TIMESLICE | YEAR | VALUE |
      | S1B1      | 2030 | 0.125 |
      | S1B2      | 2030 | 0.375 |
      | S2B1      | 2030 | 0.125 |
      | S2B2      | 2030 | 0.375 |
      | S1B1      | 2035 | 0.125 |
      | S1B2      | 2035 | 0.375 |
      | S2B1      | 2035 | 0.125 |
      | S2B2      | 2035 | 0.375 |
    And the otoole parameter "DaySplit" keyed by "DAILYTIMEBRACKET YEAR" with default 0.00137 has the rows:
      | DAILYTIMEBRACKET | YEAR | VALUE    |
      | B1               | 2030 | 0.000685 |
      | B2               | 2030 | 0.002055 |
      | B1               | 2035 | 0.000685 |
      | B2               | 2035 | 0.002055 |
    And the otoole parameter "Conversionls" keyed by "TIMESLICE SEASON" with default 0 has the rows:
      | TIMESLICE | SEASON | VALUE |
      | S1B1      | S1     | 1     |
      | S1B2      | S1     | 1     |
      | S2B1      | S2     | 1     |
      | S2B2      | S2     | 1     |
    And the otoole parameter "Conversionld" keyed by "TIMESLICE DAYTYPE" with default 0 has the rows:
      | TIMESLICE | DAYTYPE | VALUE |
      | S1B1      | 1       | 1     |
      | S1B2      | 1       | 1     |
      | S2B1      | 1       | 1     |
      | S2B2      | 1       | 1     |
    And the otoole parameter "Conversionlh" keyed by "TIMESLICE DAILYTIMEBRACKET" with default 0 has the rows:
      | TIMESLICE | DAILYTIMEBRACKET | VALUE |
      | S1B1      | B1               | 1     |
      | S1B2      | B2               | 1     |
      | S2B1      | B1               | 1     |
      | S2B2      | B2               | 1     |
    And the otoole parameter "SpecifiedAnnualDemand" keyed by "REGION FUEL YEAR" with default 0 has the rows:
      | REGION | FUEL   | YEAR | VALUE |
      | R1     | ATELEC | 2030 | 876   |
      | R1     | ATELEC | 2035 | 1752  |
    And the otoole parameter "SpecifiedDemandProfile" keyed by "REGION FUEL TIMESLICE YEAR" with default 0 has the rows:
      | REGION | FUEL   | TIMESLICE | YEAR | VALUE |
      | R1     | ATELEC | S1B1      | 2030 | 0.125 |
      | R1     | ATELEC | S1B2      | 2030 | 0.375 |
      | R1     | ATELEC | S2B1      | 2030 | 0.25  |
      | R1     | ATELEC | S2B2      | 2030 | 0.25  |
      | R1     | ATELEC | S1B1      | 2035 | 0.125 |
      | R1     | ATELEC | S1B2      | 2035 | 0.375 |
      | R1     | ATELEC | S2B1      | 2035 | 0.25  |
      | R1     | ATELEC | S2B2      | 2035 | 0.25  |
    And the otoole parameter "ResidualCapacity" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | ATGASCC    | 2030 | 0.5   |
      | R1     | ATFULLGASCC  | 2030 | 0.3   |
      | R1     | ATFULLGASCC  | 2035 | 0.3   |
    And the otoole parameter "InputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | FUEL   | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | ATGASCC    | ATGAS  | 1                 | 2030 | 2     |
      | R1     | ATGASNEW   | ATGAS  | 1                 | 2030 | 2     |
      | R1     | ATGASNEW   | ATGAS  | 1                 | 2035 | 1.5   |
      | R1     | ATLOCKGASCC  | ATGAS  | 1                 | 2030 | 2     |
      | R1     | ATFULLGASCC  | ATGAS  | 1                 | 2030 | 2     |
      | R1     | ATDELINK   | ATELEC | 1                 | 2030 | 1     |
      | R1     | ATDELINK   | ATELEC | 1                 | 2035 | 1     |
    And the otoole parameter "OutputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | FUEL   | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | ATGASCC    | ATELEC | 1                 | 2030 | 1     |
      | R1     | ATGASNEW   | ATELEC | 1                 | 2030 | 1     |
      | R1     | ATGASNEW   | ATELEC | 1                 | 2035 | 1     |
      | R1     | ATSOLAR    | ATELEC | 1                 | 2030 | 1     |
      | R1     | ATLATESOLAR | ATELEC | 1                | 2035 | 1     |
      | R1     | ATBIO      | ATELEC | 1                 | 2030 | 1     |
      | R1     | ATLOCKGASCC  | ATELEC | 1                 | 2030 | 1     |
      | R1     | ATFULLGASCC  | ATELEC | 1                 | 2030 | 1     |
      | R1     | ATDELINK   | DEELEC | 1                 | 2030 | 0.75  |
      | R1     | ATDELINK   | DEELEC | 1                 | 2035 | 0.75  |
      | R1     | ATGASWELL  | ATGAS  | 1                 | 2030 | 1     |
      | R1     | ATGASWELL  | ATGAS  | 1                 | 2035 | 1     |
    And the otoole parameter "VariableCost" keyed by "REGION TECHNOLOGY MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | ATGASNEW   | 1                 | 2030 | 1000  |
      | R1     | ATGASNEW   | 1                 | 2035 | 1000  |
      | R1     | ATGASWELL  | 1                 | 2030 | 3000  |
      | R1     | ATGASWELL  | 1                 | 2035 | 4000  |
    And the otoole parameter "FixedCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE    |
      | R1     | ATGASNEW   | 2030 | 20000000 |
    And the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE      |
      | R1     | ATGASCC    | 2030 | 800000000  |
      | R1     | ATGASNEW   | 2030 | 1000000000 |
      | R1     | ATGASNEW   | 2035 | 900000000  |
      | R1     | ATSOLAR    | 2030 | 600000000  |
      | R1     | ATLATESOLAR | 2035 | 500000000 |
      | R1     | ATBIO      | 2030 | 2000000000 |
      | R1     | ATLOCKGASCC  | 2030 | 700000000  |
      | R1     | ATLOCKGASCC  | 2035 | 700000000  |
      | R1     | ATFULLGASCC  | 2030 | 700000000  |
      | R1     | ATFULLGASCC  | 2035 | 700000000  |
      | R1     | ATDELINK   | 2030 | 200000000  |
    And the otoole parameter "TotalAnnualMaxCapacity" keyed by "REGION TECHNOLOGY YEAR" with default -1 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | ATGASNEW   | 2030 | 1     |
      | R1     | ATDELINK   | 2030 | 2     |
      | R1     | ATFULLGASCC  | 2030 | 0.3   |
      | R1     | ATFULLGASCC  | 2035 | 0.3   |
    And the otoole parameter "TotalAnnualMaxCapacityInvestment" keyed by "REGION TECHNOLOGY YEAR" with default -1 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | ATLOCKGASCC  | 2030 | 0     |
      | R1     | ATLOCKGASCC  | 2035 | 0     |
    And the otoole parameter "TotalAnnualMinCapacity" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | ATGASNEW   | 2035 | 0.2   |
    And the otoole parameter "OperationalLife" keyed by "REGION TECHNOLOGY" with default 1 has the rows:
      | REGION | TECHNOLOGY | VALUE |
      | R1     | ATGASNEW   | 30    |
    And the otoole parameter "DiscountRate" keyed by "REGION" with default 0.05 has the rows:
      | REGION | VALUE |
      | R1     | 0.07  |
    And the otoole parameter "CapacityFactor" keyed by "REGION TECHNOLOGY TIMESLICE YEAR" with default 1 has the rows:
      | REGION | TECHNOLOGY | TIMESLICE | YEAR | VALUE |
      | R1     | ATSOLAR    | S1B1      | 2030 | 0     |
      | R1     | ATSOLAR    | S1B2      | 2030 | 0.5   |
      | R1     | ATSOLAR    | S2B1      | 2030 | 0.25  |
      | R1     | ATSOLAR    | S2B2      | 2030 | 0.8   |
      | R1     | ATSOLAR    | S1B1      | 2035 | 0     |
      | R1     | ATSOLAR    | S1B2      | 2035 | 0.6   |
      | R1     | ATSOLAR    | S2B1      | 2035 | 0.25  |
      | R1     | ATSOLAR    | S2B2      | 2035 | 0.9   |
    And the otoole parameter "EmissionActivityRatio" keyed by "REGION TECHNOLOGY EMISSION MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | EMISSION | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | ATGASCC    | CO2      | 1                 | 2030 | 400   |
      | R1     | ATGASNEW   | CO2      | 1                 | 2030 | 350   |
      | R1     | ATGASCC    | ATNOX    | 1                 | 2030 | 1     |
    And the otoole parameter "AnnualEmissionLimit" keyed by "REGION EMISSION YEAR" with default -1 has the rows:
      | REGION | EMISSION | YEAR | VALUE   |
      | R1     | CO2      | 2030 | 600000  |
      | R1     | CO2      | 2035 | 250000  |
      | R1     | ATNOX    | 2030 | 100     |
    And the otoole parameter "AnnualExogenousEmission" keyed by "REGION EMISSION YEAR" with default 0 has the rows:
      | REGION | EMISSION | YEAR | VALUE  |
      | R1     | CO2      | 2030 | 100000 |
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                                                         |
      | osemosys: {                                                                                                                  |
      | units: {capacity: GW, energy: GWh, currency: USD, emissions: t},                                                             |
      | objects: {                                                                                                                   |
      | fuels: [                                                                                                                     |
      | {match: "^(?P<country>[A-Z]{2})ELEC$", carrier: electricity, location: "{country}"},                                         |
      | {match: "^(?P<country>[A-Z]{2})GAS$", carrier: gas, location: "{country}"}],                                                 |
      | technologies: [                                                                                                              |
      | {match: "GAS(CC\|NEW)$", category: gas-cc}, {match: "SOLAR$", category: solar}, {match: "BIO$", category: biomass}]}}       |
      | carriers: [                                                                                                                  |
      | {osemosys_category: gas-cc, sienna_component_type: ThermalStandard, sienna_fuel_type: NATURAL_GAS, sienna_prime_mover_type: CC}, |
      | {osemosys_category: solar, sienna_component_type: RenewableDispatch, sienna_prime_mover_type: PVe}]                          |

  Scenario: The TopologyMapping of an area names each bus of its location
    The fuel ATELECLV is a second electricity fuel at AT, so the area AT holds two buses.
    Given the otoole set "FUEL" holds "ATELEC ATELECLV DEELEC ATGAS"
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                                                         |
      | osemosys: {                                                                                                                  |
      | units: {capacity: GW, energy: GWh, currency: USD, emissions: t},                                                             |
      | objects: {                                                                                                                   |
      | fuels: [                                                                                                                     |
      | {match: "^(?P<country>[A-Z]{2})ELEC(LV)?$", carrier: electricity, location: "{country}"},                                    |
      | {match: "^(?P<country>[A-Z]{2})GAS$", carrier: gas, location: "{country}"}],                                                 |
      | technologies: [                                                                                                              |
      | {match: "GAS(CC\|NEW)$", category: gas-cc}, {match: "SOLAR$", category: solar}, {match: "BIO$", category: biomass}]}}       |
      | carriers: [                                                                                                                  |
      | {osemosys_category: gas-cc, sienna_component_type: ThermalStandard, sienna_fuel_type: NATURAL_GAS, sienna_prime_mover_type: CC}, |
      | {osemosys_category: solar, sienna_component_type: RenewableDispatch, sienna_prime_mover_type: PVe}]                          |
    When I translate the otoole model to a Sienna investments portfolio
    Then the pipeline exit code is 0
    And the file "outputs/portfolio.json" parses as a portfolio where the "TopologyMapping" of base system "Area" 1 has "buses" set to ["R1/ATELEC", "R1/ATELECLV"]
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "ATGASNEW" having "region" set to [1]

  Scenario: A candidate becomes a SupplyTechnology with its capacity limits of each year and the capital cost of the earliest year
    When I translate the otoole model to a Sienna investments portfolio
    Then the pipeline exit code is 0
    And the file "outputs/portfolio.json" parses as JSON with 4 components of type "SupplyTechnology"
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "ATGASNEW" having "power_systems_type" set to "ThermalStandard"
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "ATGASNEW" having "prime_mover_type" set to "CC"
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "ATGASNEW" having "fuel" set to ["NATURAL_GAS"]
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "ATGASNEW" having "region" set to [1]
    And the file "outputs/portfolio.json" parses as a portfolio where the "TopologyMapping" of base system "Area" 1 has "buses" set to ["R1/ATELEC"]
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "ATGASNEW" having "capacity_limits" set to {"2030.0": {"min": 0.0, "max": 1000.0}, "2035.0": {"min": 200.0}}
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "ATGASNEW" having "capital_costs.capital_cost.function_data.proportional_term" set to 1000000.0
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "ATGASNEW" having "operation_costs.fixed" set to 20000.0
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "ATGASNEW" having "operation_costs.variable_operation_cost.value_curve.function_data.proportional_term" set to 7.0
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "ATGASNEW" having "lifetime" set to 30
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "ATGASNEW" having "financial_data.capital_recovery_period" set to 30
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "ATGASNEW" having "financial_data.return_on_equity" set to 0.07
    And the file "outputs/extensions.json" parses as JSON technology extension record for "ATGASNEW" having "overnight_cost" set to {"2030": 1000000.0, "2035": 900000.0}
    And the file "outputs/extensions.json" parses as JSON technology extension record for "ATGASNEW" having "marginal_cost" set to {"2030": 7.0, "2035": 7.0}
    And the file "outputs/extensions.json" parses as JSON technology extension record for "ATGASNEW" having "fom_cost" set to {"2030": 20000.0, "2035": 0.0}
    And the file "outputs/portfolio.json" parses as JSON with "financial_data.discount_rate" set to 0.07
    And the file "outputs/portfolio.json" parses as JSON with "financial_data.base_year" set to 2030

  Scenario: The portfolio and each candidate quote their costs in the currency year of the user mappings file
    Given a file "user_mappings.yaml" containing the lines:
      | line                                                                                                                         |
      | osemosys: {                                                                                                                  |
      | units: {capacity: GW, energy: GWh, currency: USD, emissions: t, currency_year: 2020},                                        |
      | objects: {                                                                                                                   |
      | fuels: [                                                                                                                     |
      | {match: "^(?P<country>[A-Z]{2})ELEC$", carrier: electricity, location: "{country}"},                                         |
      | {match: "^(?P<country>[A-Z]{2})GAS$", carrier: gas, location: "{country}"}],                                                 |
      | technologies: [                                                                                                              |
      | {match: "GAS(CC\|NEW)$", category: gas-cc}, {match: "SOLAR$", category: solar}, {match: "BIO$", category: biomass}]}}       |
      | carriers: [                                                                                                                  |
      | {osemosys_category: gas-cc, sienna_component_type: ThermalStandard, sienna_fuel_type: NATURAL_GAS, sienna_prime_mover_type: CC}, |
      | {osemosys_category: solar, sienna_component_type: RenewableDispatch, sienna_prime_mover_type: PVe}]                          |
    When I translate the otoole model to a Sienna investments portfolio
    Then the pipeline exit code is 0
    And the file "outputs/portfolio.json" parses as JSON with "financial_data.base_year" set to 2020
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "ATGASNEW" having "financial_data.technology_base_year" set to 2020

  Scenario: The discount rate of a second region that states another rate is recorded as not mapped
    The portfolio holds one discount rate, the rate of the first region R1. OSeMOSYS discounts
    the costs of R2 at 0.10, so the report names that rate.
    Given the otoole set "REGION" holds "R1 R2"
    And the otoole parameter "DiscountRate" keyed by "REGION" with default 0.05 has the rows:
      | REGION | VALUE |
      | R1     | 0.07  |
      | R2     | 0.10  |
    When I translate the otoole model to a Sienna investments portfolio
    Then the pipeline exit code is 0
    And the file "outputs/portfolio.json" parses as JSON with "financial_data.discount_rate" set to 0.07
    And the file "decisions.md" contains "`osemosys.discount_rate.R2.region` = 0.1"
    And the log contains "1 region(s) state a discount_rate other than that of the first region, which the portfolio takes as its own"

  Scenario: The report of the parameters that no step applies leaves out the parameters of the portfolio
    The portfolio step applies the capital cost, the lifetime and the emission limits, so the
    report names none of them. It still names a parameter that no step applies.
    Given the otoole parameter "ReserveMargin" keyed by "REGION YEAR" with default 1 has the rows:
      | REGION | YEAR | VALUE |
      | R1     | 2030 | 1.15  |
    When I translate the otoole model to a Sienna investments portfolio
    Then the pipeline exit code is 0
    And the log does not contain "capital_cost states"
    And the log does not contain "annual_emission_limit states"
    And the file "decisions.md" does not contain "`osemosys.capital_cost.R1/ATGASNEW` = 1000000000.0 |  |  |"
    And the log contains "osemosys-to-sienna: reserve_margin states 1 row(s) for 2030 that no step of the pipeline applies or keeps, for 1 region(s): R1"

  Scenario: The cost of a fuel producer that only a candidate burns, and the cost of a transport candidate, count as kept
    Only the candidate ATGASNEW burns gas, so the cost of the gas well reaches its variable
    cost, and the report does not name it. The interconnector ATDELINK costs 1 $/MWh sent in
    2030, and its technology record keeps the cost of each year.
    Given the otoole parameter "InputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | FUEL   | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | ATGASNEW   | ATGAS  | 1                 | 2030 | 2     |
      | R1     | ATGASNEW   | ATGAS  | 1                 | 2035 | 1.5   |
      | R1     | ATDELINK   | ATELEC | 1                 | 2030 | 1     |
    And the otoole parameter "VariableCost" keyed by "REGION TECHNOLOGY MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | ATGASNEW   | 1                 | 2030 | 1000  |
      | R1     | ATGASNEW   | 1                 | 2035 | 1000  |
      | R1     | ATGASWELL  | 1                 | 2030 | 3000  |
      | R1     | ATGASWELL  | 1                 | 2035 | 4000  |
      | R1     | ATDELINK   | 1                 | 2030 | 1000  |
    When I translate the otoole model to a Sienna investments portfolio
    Then the pipeline exit code is 0
    And the file "outputs/extensions.json" parses as JSON technology extension record for "ATGASNEW" having "marginal_cost" set to {"2030": 7.0, "2035": 7.0}
    And the file "outputs/extensions.json" parses as JSON technology extension record for "ATDELINK" having "marginal_cost" set to {"2030": 1.0, "2035": 0.0}
    And the log does not contain "variable_operation_cost states"

  Scenario: The bounds on the growth and the energy of a candidate reach its technology record
    Given the otoole parameter "TotalAnnualMinCapacityInvestment" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | ATGASNEW   | 2035 | 0.1   |
    And the otoole parameter "CapacityAdditionalMaxGrowthRate" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | ATGASNEW   | 2030 | 0.2   |
      | R1     | ATGASNEW   | 2035 | 0.3   |
    And the otoole parameter "TotalTechnologyAnnualActivityUpperLimit" keyed by "REGION TECHNOLOGY YEAR" with default -1 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | ATGASNEW   | 2035 | 2     |
    And the otoole parameter "CapacityToActivityUnit" keyed by "REGION TECHNOLOGY" with default 1 has the rows:
      | REGION | TECHNOLOGY | VALUE |
      | R1     | ATGASNEW   | 8760  |
    When I translate the otoole model to a Sienna investments portfolio
    Then the pipeline exit code is 0
    And the file "outputs/extensions.json" parses as JSON technology extension record for "ATGASNEW" having "min_growth" set to {"2035": 100.0}
    And the file "outputs/extensions.json" parses as JSON technology extension record for "ATGASNEW" having "e_sum_max" set to {"2035": 2000.0}
    And the file "outputs/extensions.json" parses as JSON technology extension record for "ATGASNEW" having "capacity_to_activity_unit" set to 8760.0
    And the log does not contain "capacity_to_activity_unit states"
    And the log does not contain "total_technology_annual_activity_upper_limit states"
    And the file "outputs/extensions.json" parses as JSON technology extension record for "ATGASNEW" having "max_growth_rate" set to {"2030": 0.2, "2035": 0.3}
    And the log does not contain "total_annual_min_capacity_investment states"
    And the log does not contain "capacity_additional_max_growth_rate states"

  Scenario: The emission penalty of each year adds to the variable cost of a candidate
    ATGASNEW emits 0.35 t of CO2 for each MWh in 2030 and none in 2035. At 100 USD/t, the
    penalty adds 35 $/MWh in 2030 to its cost of 7 $/MWh.
    Given the otoole parameter "EmissionsPenalty" keyed by "REGION EMISSION YEAR" with default 0 has the rows:
      | REGION | EMISSION | YEAR | VALUE |
      | R1     | CO2      | 2030 | 100   |
      | R1     | CO2      | 2035 | 100   |
    When I translate the otoole model to a Sienna investments portfolio
    Then the pipeline exit code is 0
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "ATGASNEW" having "operation_costs.variable_operation_cost.value_curve.function_data.proportional_term" set to 42.0
    And the file "outputs/extensions.json" parses as JSON technology extension record for "ATGASNEW" having "marginal_cost" set to {"2030": 42.0, "2035": 7.0}
    And the file "decisions.md" contains "`sienna.SupplyTechnology.ATGASNEW.operation_costs emission penalty` = 35.0 \$/MWh | Σ over pollutants of the emission rate in t/MWh"
    And the file "decisions.md" contains "`osemosys.variable_operation_cost.R1/ATGASNEW.the earliest year in scope` = 7.0 \$/MWh"

  Scenario: A candidate with no capital cost in the earliest year takes the cost of the first year in which a plan can build it at a cost
    When I translate the otoole model to a Sienna investments portfolio
    Then the pipeline exit code is 0
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "ATLATESOLAR" having "capital_costs.capital_cost.function_data.proportional_term" set to 500000.0
    And the file "decisions.md" contains "`osemosys.capital_cost.R1/ATLATESOLAR.year 2035` = 500000000.0"

  Scenario: A transport candidate that the model states from a later year takes its ends and its ratios in that year
    ATDELINK takes in and puts out electricity in 2035 only, and its capital cost is of 2035.
    Given the otoole parameter "InputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | FUEL   | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | ATGASCC    | ATGAS  | 1                 | 2030 | 2     |
      | R1     | ATGASNEW   | ATGAS  | 1                 | 2030 | 2     |
      | R1     | ATGASNEW   | ATGAS  | 1                 | 2035 | 1.5   |
      | R1     | ATDELINK   | ATELEC | 1                 | 2035 | 1     |
    And the otoole parameter "OutputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY  | FUEL   | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | ATGASCC     | ATELEC | 1                 | 2030 | 1     |
      | R1     | ATGASNEW    | ATELEC | 1                 | 2030 | 1     |
      | R1     | ATGASNEW    | ATELEC | 1                 | 2035 | 1     |
      | R1     | ATSOLAR     | ATELEC | 1                 | 2030 | 1     |
      | R1     | ATDELINK    | DEELEC | 1                 | 2035 | 0.75  |
    And the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE      |
      | R1     | ATGASNEW   | 2030 | 1000000000 |
      | R1     | ATSOLAR    | 2030 | 600000000  |
      | R1     | ATDELINK   | 2035 | 200000000  |
    When I translate the otoole model to a Sienna investments portfolio
    Then the pipeline exit code is 0
    And the file "outputs/portfolio.json" parses as JSON with component "AggregateTransportTechnology" named "ATDELINK" having "line_loss" set to 0.25
    And the file "outputs/portfolio.json" parses as JSON with component "AggregateTransportTechnology" named "ATDELINK" having "end_region" set to 2

  Scenario: A technology with a capital cost but no room to build in any year is not a candidate, and the report says nothing of it
    When I translate the otoole model to a Sienna investments portfolio
    Then the pipeline exit code is 0
    And the file "outputs/portfolio.json" parses as a portfolio with no component "SupplyTechnology" named "ATLOCKGASCC"
    And the file "outputs/portfolio.json" parses as a portfolio with no component "SupplyTechnology" named "ATFULLGASCC"
    And the file "decisions.md" does not contain "SupplyTechnology.ATLOCKGASCC"
    And the file "decisions.md" does not contain "SupplyTechnology.ATFULLGASCC"

  Scenario: A candidate whose category has no carriers row is left out and reported
    When I translate the otoole model to a Sienna investments portfolio
    Then the pipeline exit code is 0
    And the file "outputs/portfolio.json" parses as a portfolio with no component "SupplyTechnology" named "ATBIO"
    And the log contains "may be built and have a category that no carriers: row names"
    And the log contains "R1/ATBIO"
    And the file "decisions.md" contains "no carriers: row names the category 'biomass'"

  Scenario: The base system holds only the fleet that has residual capacity
    When I translate the otoole model to a Sienna investments portfolio
    Then the pipeline exit code is 0
    And the file "outputs/system.json" parses as JSON with 2 components of type "ThermalStandard"
    And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ATGASCC" having "base_power" set to 500.0
    And the file "outputs/system.json" parses as JSON with 0 components of type "TwoTerminalGenericHVDCLine"

  Scenario: An existing plant becomes the ExistingDevices of the candidate of the same name only, and retires when its residual capacity ends
    When I translate the otoole model to a Sienna investments portfolio
    Then the pipeline exit code is 0
    And the file "outputs/portfolio.json" parses as a portfolio where the "ExistingDevices" of "SupplyTechnology" "ATGASCC" has "existing_devices" set to ["ATGASCC"]
    And the file "outputs/portfolio.json" parses as a portfolio where the "RetirementPotential" of "SupplyTechnology" "ATGASCC" has "planned_retirement_year" set to {"ATGASCC": 2035}
    And the file "outputs/portfolio.json" parses as a portfolio where the "RetirementPotential" of "SupplyTechnology" "ATGASCC" has "eligible_generators" set to ["ATGASCC"]
    And the file "outputs/portfolio.json" parses as a portfolio where "SupplyTechnology" "ATGASNEW" has no "ExistingDevices"
    And the file "outputs/portfolio.json" parses as a portfolio where "SupplyTechnology" "ATGASNEW" has no "RetirementPotential"
    And the file "outputs/portfolio.json" parses as a portfolio where no device is in two "ExistingDevices" lists

  Scenario: A pollutant that every emitting technology emits becomes a CarbonCaps for each year with a limit
    When I translate the otoole model to a Sienna investments portfolio
    Then the pipeline exit code is 0
    And the file "outputs/portfolio.json" parses as JSON with 2 components of type "CarbonCaps"
    And the file "outputs/portfolio.json" parses as JSON with component "CarbonCaps" named "CO2/2030" having "max_mtons" set to 0.5
    And the file "outputs/portfolio.json" parses as JSON with component "CarbonCaps" named "CO2/2030" having "target_year" set to 2030
    And the file "outputs/portfolio.json" parses as JSON with component "CarbonCaps" named "CO2/2035" having "max_mtons" set to 0.25

  Scenario: A pollutant that only some technologies emit goes to extensions.json, and the report names it
    The operations step writes one constraint record for each pollutant with a limit. The
    portfolio step takes out the record of CO2, whose yearly limits become CarbonCaps and which
    states no limit over the model period.
    When I translate the otoole model to a Sienna investments portfolio
    Then the pipeline exit code is 0
    And the file "outputs/portfolio.json" parses as a portfolio with no component "CarbonCaps" named "ATNOX/2030"
    And the file "outputs/extensions.json" parses as JSON constraint extension record for "ATNOX" having "limits" set to [{"period": "year", "value": 100.0, "unit": "t", "investment_period": 2030}]
    And the file "outputs/extensions.json" parses as JSON with no constraint extension record for "CO2"
    And the file "decisions.md" contains "`sienna.constraint.CO2.extensions.limits.year 2030` = 500000.0 t | `sienna.CarbonCaps.CO2/2030.max_mtons` = 0.5 Mt"
    And the file "outputs/extensions.json" parses as JSON constraint extension record for "ATNOX" having "sense" set to "<="
    And the log contains "R1/ATNOX"
    And the file "decisions.md" contains "so the limits go to extensions.json as a constraint record"

  Scenario: A technology that the portfolio leaves out does not decide which pollutant covers the portfolio
    ATBIO has no carriers: row, so the portfolio leaves it out. It emits only ATNOX, and each
    technology of the portfolio still emits CO2.
    Given the otoole parameter "EmissionActivityRatio" keyed by "REGION TECHNOLOGY EMISSION MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | EMISSION | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | ATGASCC    | CO2      | 1                 | 2030 | 400   |
      | R1     | ATGASNEW   | CO2      | 1                 | 2030 | 350   |
      | R1     | ATGASCC    | ATNOX    | 1                 | 2030 | 1     |
      | R1     | ATBIO      | ATNOX    | 1                 | 2030 | 1     |
    When I translate the otoole model to a Sienna investments portfolio
    Then the pipeline exit code is 0
    And the file "outputs/portfolio.json" parses as JSON with 2 components of type "CarbonCaps"
    And the file "outputs/portfolio.json" parses as JSON with component "CarbonCaps" named "CO2/2030" having "max_mtons" set to 0.5

  Scenario: A technology that the portfolio leaves out and that emits the capped pollutant is reported
    ATBIO emits CO2, so OSeMOSYS counts its emissions under the limit, but no CarbonCaps does.
    Given the otoole parameter "EmissionActivityRatio" keyed by "REGION TECHNOLOGY EMISSION MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | EMISSION | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | ATGASCC    | CO2      | 1                 | 2030 | 400   |
      | R1     | ATGASNEW   | CO2      | 1                 | 2030 | 350   |
      | R1     | ATGASCC    | ATNOX    | 1                 | 2030 | 1     |
      | R1     | ATBIO      | CO2      | 1                 | 2030 | 100   |
    When I translate the otoole model to a Sienna investments portfolio
    Then the pipeline exit code is 0
    And the file "outputs/portfolio.json" parses as JSON with 2 components of type "CarbonCaps"
    And the file "decisions.md" contains "`osemosys.emission_rate.R1/ATBIO.pollutant` = R1/CO2"
    And the log contains "1 technology(ies) emit the pollutant of a CarbonCaps but are not in the portfolio, so the cap holds less than the limit counts"

  Scenario: Only the first pollutant in name order that covers the portfolio becomes a CarbonCaps
    ATGASCC and ATGASNEW each emit CO2 and ATNOX, so both pollutants cover the portfolio. A
    CarbonCaps names no pollutant, so ATNOX, which comes first, takes the caps, and the limits
    of CO2 stay in extensions.json.
    Given the otoole parameter "EmissionActivityRatio" keyed by "REGION TECHNOLOGY EMISSION MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | EMISSION | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | ATGASCC    | CO2      | 1                 | 2030 | 400   |
      | R1     | ATGASNEW   | CO2      | 1                 | 2030 | 350   |
      | R1     | ATGASCC    | ATNOX    | 1                 | 2030 | 1     |
      | R1     | ATGASNEW   | ATNOX    | 1                 | 2030 | 1     |
    When I translate the otoole model to a Sienna investments portfolio
    Then the pipeline exit code is 0
    And the file "outputs/portfolio.json" parses as JSON with 1 component of type "CarbonCaps"
    And the file "outputs/portfolio.json" parses as JSON with component "CarbonCaps" named "ATNOX/2030" having "max_mtons" set to 0.0001
    And the file "outputs/portfolio.json" parses as a portfolio with no component "CarbonCaps" named "CO2/2030"
    And the file "outputs/extensions.json" parses as JSON constraint extension record for "CO2" having "sense" set to "<="
    And the log contains "1 pollutant(s) cover the portfolio after a pollutant that comes first in name order"

  Scenario: A transport candidate becomes an AggregateTransportTechnology between two areas
    When I translate the otoole model to a Sienna investments portfolio
    Then the pipeline exit code is 0
    And the file "outputs/portfolio.json" parses as JSON with component "AggregateTransportTechnology" named "ATDELINK" having "start_region" set to 1
    And the file "outputs/portfolio.json" parses as JSON with component "AggregateTransportTechnology" named "ATDELINK" having "end_region" set to 2
    And the file "outputs/portfolio.json" parses as JSON with component "AggregateTransportTechnology" named "ATDELINK" having "line_loss" set to 0.25
    And the file "outputs/portfolio.json" parses as JSON with component "AggregateTransportTechnology" named "ATDELINK" having "capacity_limits" set to {"min": 0.0}
    And the file "outputs/portfolio.json" parses as JSON with component "AggregateTransportTechnology" named "ATDELINK" having "capital_costs.capital_cost.function_data.proportional_term" set to 200000.0
    And the file "outputs/portfolio.json" parses as JSON with component "AggregateTransportTechnology" named "ATDELINK" having "power_systems_type" set to "TwoTerminalGenericHVDCLine"
    And the file "decisions.md" contains "`sienna.AggregateTransportTechnology.ATDELINK.financial_data.capital_recovery_period`"
    And the file "decisions.md" does not contain "`sienna.AggregateTransportTechnology.ATDELINK.lifetime`"

  Scenario: A transport candidate takes the largest maximum capacity of the years in scope, and the smallest minimum
    AggregateTransportTechnology holds one capacity limit for every year. ATDELINK may hold no
    capacity in 2030 and 2 GW in 2035, so a limit of 0 from 2030 alone would let no plan
    build it.
    Given the otoole parameter "TotalAnnualMaxCapacity" keyed by "REGION TECHNOLOGY YEAR" with default -1 has the rows:
      | REGION | TECHNOLOGY  | YEAR | VALUE |
      | R1     | ATGASNEW    | 2030 | 1     |
      | R1     | ATDELINK    | 2030 | 0     |
      | R1     | ATDELINK    | 2035 | 2     |
      | R1     | ATFULLGASCC | 2030 | 0.3   |
      | R1     | ATFULLGASCC | 2035 | 0.3   |
    And the otoole parameter "TotalAnnualMinCapacity" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | ATGASNEW   | 2035 | 0.2   |
      | R1     | ATDELINK   | 2030 | 0.5   |
      | R1     | ATDELINK   | 2035 | 1     |
    And the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE      |
      | R1     | ATGASNEW   | 2030 | 1000000000 |
      | R1     | ATDELINK   | 2030 | 200000000  |
      | R1     | ATDELINK   | 2035 | 200000000  |
    When I translate the otoole model to a Sienna investments portfolio
    Then the pipeline exit code is 0
    And the file "outputs/portfolio.json" parses as JSON with component "AggregateTransportTechnology" named "ATDELINK" having "capacity_limits" set to {"min": 500.0, "max": 2000.0}
    And the file "outputs/extensions.json" parses as JSON technology extension record for "ATDELINK" having "p_nom_max" set to {"2030": 0.0, "2035": 2000.0}
    And the file "outputs/extensions.json" parses as JSON technology extension record for "ATDELINK" having "p_nom_min" set to {"2030": 500.0, "2035": 1000.0}

  Scenario: The demand of each year and the availability of each candidate reach the portfolio and its HDF5 companion
    When I translate the otoole model to a Sienna investments portfolio
    Then the pipeline exit code is 0
    And the file "outputs/portfolio.json" parses as JSON with "time_series_storage_file" set to "portfolio_time_series_storage.h5"
    And the portfolio "outputs/portfolio.json" has a series of "DemandRequirement" "ATELEC" for the year "2030" with 48 values that peak at 200
    And the portfolio "outputs/portfolio.json" has a series of "DemandRequirement" "ATELEC" for the year "2035" with 48 values that peak at 400
    And the portfolio "outputs/portfolio.json" has a series of "SupplyTechnology" "ATSOLAR" for the year "2030" with 48 values that peak at 0.8
    And the portfolio "outputs/portfolio.json" has a series of "SupplyTechnology" "ATSOLAR" for the year "2035" with 48 values that peak at 0.9

  Scenario: The demand of a later year takes the representative days of the earliest year
    The expansion weights each year by the representative days of the earliest year. So the
    MW of 2035 divide its demand by the hours of the timeslices in 2030, and the 2035 demand of
    1752 GWh comes back over those days. With the year_split of 2035 itself, S2B2 would hold
    88.9 MW, not 133.3 MW.
    Given the otoole parameter "YearSplit" keyed by "TIMESLICE YEAR" with default 0 has the rows:
      | TIMESLICE | YEAR | VALUE  |
      | S1B1      | 2030 | 0.125  |
      | S1B2      | 2030 | 0.375  |
      | S2B1      | 2030 | 0.125  |
      | S2B2      | 2030 | 0.375  |
      | S1B1      | 2035 | 0.0625 |
      | S1B2      | 2035 | 0.1875 |
      | S2B1      | 2035 | 0.1875 |
      | S2B2      | 2035 | 0.5625 |
    When I translate the otoole model to a Sienna investments portfolio
    Then the pipeline exit code is 0
    And the portfolio "outputs/portfolio.json" has a series of "DemandRequirement" "ATELEC" for the year "2035" with 48 values from 133.333333333333 to 400
    And the portfolio "outputs/portfolio.json" has a series of "DemandRequirement" "ATELEC" for the year "2035" that starts at "2035-01-01T00:00:00"

  Scenario: An output path in another directory takes the companions of the system and of the portfolio with it
    When I translate the otoole model to a Sienna investments portfolio, with only the system at "plans/system.json" and the portfolio at "plans/portfolio.json"
    Then the pipeline exit code is 0
    And the file "plans/system_time_series_storage.h5" exists
    And the file "plans/extensions.json" exists
    And the file "plans/portfolio_time_series_storage.h5" exists
    And the file "plans/system.json" parses as JSON with "time_series_storage_file" set to "system_time_series_storage.h5"
    And the file "plans/portfolio.json" parses as JSON with "time_series_storage_file" set to "portfolio_time_series_storage.h5"
    And the file "outputs/system_time_series_storage.h5" does not exist
    And the file "outputs/portfolio_time_series_storage.h5" does not exist

  Rule: A storage whose discharging technology a plan may build becomes a StorageTechnology
    The pumped-storage plant ATPHS charges the storage ATPHSS in mode 1 and discharges it in
    mode 2. It takes in 1.25 units of electricity for each unit of its activity when it charges,
    and puts 0.9 of a unit into the storage. It puts out 0.8 when it discharges. It exists in
    2030, and its capital cost and the energy capital cost of the storage let a plan build more.

    Background:
      Given the otoole set "TECHNOLOGY" holds "ATPHS"
      And the otoole set "STORAGE" holds "ATPHSS"
      And the otoole set "MODE_OF_OPERATION" holds "1 2"
      And the otoole parameter "ResidualCapacity" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATPHS      | 2030 | 0.1   |
      And the otoole parameter "InputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | FUEL   | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATPHS      | ATELEC | 1                 | 2030 | 1.25  |
      And the otoole parameter "OutputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | FUEL   | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATPHS      | ATELEC | 2                 | 2030 | 0.8   |
      And the otoole parameter "TechnologyToStorage" keyed by "REGION TECHNOLOGY STORAGE MODE_OF_OPERATION" with default 0 has the rows:
        | REGION | TECHNOLOGY | STORAGE | MODE_OF_OPERATION | VALUE |
        | R1     | ATPHS      | ATPHSS  | 1                 | 0.9   |
      And the otoole parameter "TechnologyFromStorage" keyed by "REGION TECHNOLOGY STORAGE MODE_OF_OPERATION" with default 0 has the rows:
        | REGION | TECHNOLOGY | STORAGE | MODE_OF_OPERATION | VALUE |
        | R1     | ATPHS      | ATPHSS  | 2                 | 1     |
      And the otoole parameter "ResidualStorageCapacity" keyed by "REGION STORAGE YEAR" with default 0 has the rows:
        | REGION | STORAGE | YEAR | VALUE |
        | R1     | ATPHSS  | 2030 | 0.8   |
      And the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE      |
        | R1     | ATPHS      | 2030 | 1000000000 |
      And the otoole parameter "CapitalCostStorage" keyed by "REGION STORAGE YEAR" with default 0 has the rows:
        | REGION | STORAGE | YEAR | VALUE    |
        | R1     | ATPHSS  | 2030 | 50000000 |
      And the otoole parameter "StorageMaxHours" keyed by "REGION STORAGE" with default 0 has the rows:
        | REGION | STORAGE | VALUE |
        | R1     | ATPHSS  | 8     |
      And the otoole parameter "OperationalLifeStorage" keyed by "REGION STORAGE" with default 0 has the rows:
        | REGION | STORAGE | VALUE |
        | R1     | ATPHSS  | 50    |
      And the otoole parameter "DiscountRateStorage" keyed by "REGION STORAGE" with default 0.05 has the rows:
        | REGION | STORAGE | VALUE |
        | R1     | ATPHSS  | 0.06  |
      And a file "user_mappings.yaml" containing the lines:
        | line                                                                                                             |
        | osemosys: {                                                                                                      |
        | units: {capacity: GW, energy: GWh, currency: USD, emissions: t},                                                 |
        | objects: {                                                                                                       |
        | fuels: [{match: "^(?P<country>[A-Z]{2})ELEC$", carrier: electricity, location: "{country}"}],                   |
        | technologies: [{match: "PHS$", category: pumped-storage}]}}                                                      |
        | carriers: [                                                                                                      |
        | {osemosys_category: pumped-storage, sienna_component_type: EnergyReservoirStorage, sienna_prime_mover_type: PS}] |

    Scenario: A pumped-storage candidate is priced for its power and its energy, and adds to the storage that it discharges
      When I translate the otoole model to a Sienna investments portfolio
      Then the pipeline exit code is 0
      And the file "outputs/portfolio.json" parses as JSON with 1 component of type "StorageTechnology"
      And the file "outputs/portfolio.json" parses as JSON with component "StorageTechnology" named "ATPHSS" having "power_systems_type" set to "EnergyReservoirStorage"
      And the file "outputs/portfolio.json" parses as JSON with component "StorageTechnology" named "ATPHSS" having "region" set to [1]
      And the file "outputs/portfolio.json" parses as JSON with component "StorageTechnology" named "ATPHSS" having "capital_costs.discharge_capital_cost.function_data.proportional_term" set to 1250000.0
      And the file "outputs/portfolio.json" parses as JSON with component "StorageTechnology" named "ATPHSS" having "capital_costs.energy_capital_cost.function_data.proportional_term" set to 50000.0
      And the file "outputs/portfolio.json" parses as JSON with component "StorageTechnology" named "ATPHSS" having "capital_costs.charge_capital_cost.function_data.proportional_term" set to 0.0
      And the file "outputs/portfolio.json" parses as JSON with component "StorageTechnology" named "ATPHSS" having "efficiency" set to {"in": 0.72, "out": 0.8}
      And the file "outputs/portfolio.json" parses as JSON with component "StorageTechnology" named "ATPHSS" having "duration_limits" set to {"max": 480.0}
      And the file "outputs/portfolio.json" parses as JSON with component "StorageTechnology" named "ATPHSS" having "lifetime" set to 50
      And the file "outputs/portfolio.json" parses as JSON with component "StorageTechnology" named "ATPHSS" having "financial_data.capital_recovery_period" set to 50
      And the file "outputs/portfolio.json" parses as JSON with component "StorageTechnology" named "ATPHSS" having "financial_data.return_on_equity" set to 0.06
      And the file "decisions.md" contains "`osemosys.storage_lifetime.R1/ATPHSS` = 50.0 yr"
      And the file "decisions.md" contains "`osemosys.storage_discount_rate.R1/ATPHSS` = 0.06"
      And the file "outputs/portfolio.json" parses as a portfolio where the "ExistingDevices" of "StorageTechnology" "ATPHSS" has "existing_devices" set to ["ATPHSS"]
      And the file "outputs/extensions.json" parses as JSON technology extension record for "ATPHSS" having "energy_overnight_cost" set to {"2030": 50000.0, "2035": 0.0}

    Scenario: A storage candidate takes its ratios in the year whose capital cost it states
      The capital cost of ATPHS is of 2035, and in 2035 ATPHS takes in 1 unit of electricity
      for each unit of activity and puts out 0.9.
      Given the otoole parameter "InputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | FUEL   | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATPHS      | ATELEC | 1                 | 2030 | 1.25  |
        | R1     | ATPHS      | ATELEC | 1                 | 2035 | 1     |
      And the otoole parameter "OutputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | FUEL   | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATPHS      | ATELEC | 2                 | 2030 | 0.8   |
        | R1     | ATPHS      | ATELEC | 2                 | 2035 | 0.9   |
      And the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE     |
        | R1     | ATPHS      | 2035 | 900000000 |
      When I translate the otoole model to a Sienna investments portfolio
      Then the pipeline exit code is 0
      And the file "outputs/portfolio.json" parses as JSON with component "StorageTechnology" named "ATPHSS" having "efficiency" set to {"in": 0.9, "out": 0.9}
      And the file "outputs/portfolio.json" parses as JSON with component "StorageTechnology" named "ATPHSS" having "capital_costs.discharge_capital_cost.function_data.proportional_term" set to 1000000.0

    Scenario: Two storage candidates that share one technology are each left out
      ATPHS charges and discharges both ATPHSS and ATTWOS, so each StorageTechnology would take
      its whole power.
      Given the otoole set "STORAGE" holds "ATPHSS ATTWOS"
      And the otoole parameter "TechnologyToStorage" keyed by "REGION TECHNOLOGY STORAGE MODE_OF_OPERATION" with default 0 has the rows:
        | REGION | TECHNOLOGY | STORAGE | MODE_OF_OPERATION | VALUE |
        | R1     | ATPHS      | ATPHSS  | 1                 | 0.9   |
        | R1     | ATPHS      | ATTWOS  | 1                 | 0.9   |
      And the otoole parameter "TechnologyFromStorage" keyed by "REGION TECHNOLOGY STORAGE MODE_OF_OPERATION" with default 0 has the rows:
        | REGION | TECHNOLOGY | STORAGE | MODE_OF_OPERATION | VALUE |
        | R1     | ATPHS      | ATPHSS  | 2                 | 1     |
        | R1     | ATPHS      | ATTWOS  | 2                 | 1     |
      And the otoole parameter "ResidualStorageCapacity" keyed by "REGION STORAGE YEAR" with default 0 has the rows:
        | REGION | STORAGE | YEAR | VALUE |
        | R1     | ATPHSS  | 2030 | 0.8   |
        | R1     | ATTWOS  | 2030 | 0.8   |
      And the otoole parameter "CapitalCostStorage" keyed by "REGION STORAGE YEAR" with default 0 has the rows:
        | REGION | STORAGE | YEAR | VALUE    |
        | R1     | ATPHSS  | 2030 | 50000000 |
        | R1     | ATTWOS  | 2030 | 50000000 |
      When I translate the otoole model to a Sienna investments portfolio
      Then the pipeline exit code is 0
      And the file "outputs/portfolio.json" parses as JSON with 0 component of type "StorageTechnology"
      And the log contains "may be built and share a technology that charges or discharges another storage, so each is left out"

    Scenario: A storage candidate whose charging technology also charges a storage that is not a candidate is left out
      ATCHG charges ATPHSS and ATBATS. ATBAT discharges ATBATS, and no capital cost prices it,
      so ATBATS is not a candidate, but it still uses the charge power of ATCHG.
      Given the otoole set "TECHNOLOGY" holds "ATPHS ATCHG ATBAT"
      And the otoole set "STORAGE" holds "ATPHSS ATBATS"
      And the otoole parameter "ResidualCapacity" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATPHS      | 2030 | 0.1   |
        | R1     | ATCHG      | 2030 | 0.1   |
        | R1     | ATBAT      | 2030 | 0.1   |
      And the otoole parameter "InputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | FUEL   | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATCHG      | ATELEC | 1                 | 2030 | 1.25  |
      And the otoole parameter "OutputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | FUEL   | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATPHS      | ATELEC | 2                 | 2030 | 0.8   |
        | R1     | ATBAT      | ATELEC | 2                 | 2030 | 0.8   |
      And the otoole parameter "TechnologyToStorage" keyed by "REGION TECHNOLOGY STORAGE MODE_OF_OPERATION" with default 0 has the rows:
        | REGION | TECHNOLOGY | STORAGE | MODE_OF_OPERATION | VALUE |
        | R1     | ATCHG      | ATPHSS  | 1                 | 0.9   |
        | R1     | ATCHG      | ATBATS  | 1                 | 0.9   |
      And the otoole parameter "TechnologyFromStorage" keyed by "REGION TECHNOLOGY STORAGE MODE_OF_OPERATION" with default 0 has the rows:
        | REGION | TECHNOLOGY | STORAGE | MODE_OF_OPERATION | VALUE |
        | R1     | ATPHS      | ATPHSS  | 2                 | 1     |
        | R1     | ATBAT      | ATBATS  | 2                 | 1     |
      And the otoole parameter "ResidualStorageCapacity" keyed by "REGION STORAGE YEAR" with default 0 has the rows:
        | REGION | STORAGE | YEAR | VALUE |
        | R1     | ATPHSS  | 2030 | 0.8   |
        | R1     | ATBATS  | 2030 | 0.8   |
      When I translate the otoole model to a Sienna investments portfolio
      Then the pipeline exit code is 0
      And the file "outputs/portfolio.json" parses as JSON with 0 component of type "StorageTechnology"
      And the log contains "may be built and share a technology that charges or discharges another storage, so each is left out"

    Scenario: A storage candidate that states no discount rate takes the default of storage_discount_rate
      The region states 0.07, but OSeMOSYS gives a storage with no row the default of
      DiscountRateStorage, as the operations translation does.
      Given the otoole parameter "DiscountRateStorage" keyed by "REGION STORAGE" with default 0.075 has the rows:
        | REGION | STORAGE | VALUE |
      When I translate the otoole model to a Sienna investments portfolio
      Then the pipeline exit code is 0
      And the file "outputs/portfolio.json" parses as JSON with component "StorageTechnology" named "ATPHSS" having "financial_data.return_on_equity" set to 0.075
      And the file "decisions.md" contains "`osemosys.storage_discount_rate.R1/ATPHSS` = 0.075"
