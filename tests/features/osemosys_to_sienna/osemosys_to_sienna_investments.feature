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
  candidate. The solar plant ATLATESOLAR states a capital cost in 2035 only. The biomass plant
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
    And the otoole parameter "OutputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | FUEL   | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | ATGASCC    | ATELEC | 1                 | 2030 | 1     |
      | R1     | ATGASNEW   | ATELEC | 1                 | 2030 | 1     |
      | R1     | ATGASNEW   | ATELEC | 1                 | 2035 | 1     |
      | R1     | ATSOLAR    | ATELEC | 1                 | 2030 | 1     |
      | R1     | ATLATESOLAR | ATELEC | 1                | 2030 | 1     |
      | R1     | ATBIO      | ATELEC | 1                 | 2030 | 1     |
      | R1     | ATLOCKGASCC  | ATELEC | 1                 | 2030 | 1     |
      | R1     | ATFULLGASCC  | ATELEC | 1                 | 2030 | 1     |
      | R1     | ATDELINK   | DEELEC | 1                 | 2030 | 0.75  |
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

  Scenario: A candidate becomes a SupplyTechnology with its capacity limits of each year and the capital cost of the earliest year
    When I translate the otoole model to a Sienna investments portfolio
    Then the pipeline exit code is 0
    And the file "outputs/portfolio.json" parses as JSON with 4 components of type "SupplyTechnology"
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "ATGASNEW" having "power_systems_type" set to "ThermalStandard"
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "ATGASNEW" having "prime_mover_type" set to "CC"
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "ATGASNEW" having "fuel" set to ["NATURAL_GAS"]
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "ATGASNEW" having "region" set to [1]
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "ATGASNEW" having "capacity_limits" set to {"2030.0": {"min": 0.0, "max": 1000.0}, "2035.0": {"min": 200.0}}
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "ATGASNEW" having "capital_costs.capital_cost.function_data.proportional_term" set to 1000000.0
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "ATGASNEW" having "operation_costs.fixed" set to 20000.0
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "ATGASNEW" having "operation_costs.variable_operation_cost.value_curve.function_data.proportional_term" set to 7.0
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "ATGASNEW" having "lifetime" set to 30
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "ATGASNEW" having "financial_data.capital_recovery_period" set to 30
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "ATGASNEW" having "financial_data.return_on_equity" set to 0.07
    And the file "outputs/extensions.json" parses as JSON technology extension record for "ATGASNEW" having "capital_cost_per_mw_by_year" set to {"2030": 1000000.0, "2035": 900000.0}
    And the file "outputs/extensions.json" parses as JSON technology extension record for "ATGASNEW" having "variable_cost_per_mwh_by_year" set to {"2030": 7.0, "2035": 7.0}

  Scenario: A candidate with no capital cost in the earliest year takes the cost of the first year in which a plan can build it at a cost
    When I translate the otoole model to a Sienna investments portfolio
    Then the pipeline exit code is 0
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "ATLATESOLAR" having "capital_costs.capital_cost.function_data.proportional_term" set to 500000.0
    And the file "decisions.md" contains "`osemosys.capital_cost.R1/ATLATESOLAR.year 2035` = 500000000.0"

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
    When I translate the otoole model to a Sienna investments portfolio
    Then the pipeline exit code is 0
    And the file "outputs/portfolio.json" parses as a portfolio with no component "CarbonCaps" named "ATNOX/2030"
    And the file "outputs/extensions.json" parses as JSON constraint extension record for "ATNOX" having "limits" set to [{"period": "year", "value": 100.0, "unit": "t", "year": 2030}]
    And the file "outputs/extensions.json" parses as JSON constraint extension record for "ATNOX" having "sense" set to "<="
    And the log contains "R1/ATNOX"
    And the file "decisions.md" contains "so the limits go to extensions.json as a constraint record"

  Scenario: A transport candidate becomes an AggregateTransportTechnology between two areas
    When I translate the otoole model to a Sienna investments portfolio
    Then the pipeline exit code is 0
    And the file "outputs/portfolio.json" parses as JSON with component "AggregateTransportTechnology" named "ATDELINK" having "start_region" set to 1
    And the file "outputs/portfolio.json" parses as JSON with component "AggregateTransportTechnology" named "ATDELINK" having "end_region" set to 2
    And the file "outputs/portfolio.json" parses as JSON with component "AggregateTransportTechnology" named "ATDELINK" having "line_loss" set to 0.25
    And the file "outputs/portfolio.json" parses as JSON with component "AggregateTransportTechnology" named "ATDELINK" having "capacity_limits" set to {"min": 0.0, "max": 2000.0}
    And the file "outputs/portfolio.json" parses as JSON with component "AggregateTransportTechnology" named "ATDELINK" having "capital_costs.capital_cost.function_data.proportional_term" set to 200000.0
    And the file "outputs/portfolio.json" parses as JSON with component "AggregateTransportTechnology" named "ATDELINK" having "power_systems_type" set to "TwoTerminalGenericHVDCLine"

  Scenario: The demand of each year and the availability of each candidate reach the portfolio and its HDF5 companion
    When I translate the otoole model to a Sienna investments portfolio
    Then the pipeline exit code is 0
    And the file "outputs/portfolio.json" parses as JSON with "time_series_storage_file" set to "portfolio_time_series_storage.h5"
    And the portfolio "outputs/portfolio.json" has a series of "DemandRequirement" "ATELEC" for the year "2030" with 48 values that peak at 200
    And the portfolio "outputs/portfolio.json" has a series of "DemandRequirement" "ATELEC" for the year "2035" with 48 values that peak at 400
    And the portfolio "outputs/portfolio.json" has a series of "SupplyTechnology" "ATSOLAR" for the year "2030" with 48 values that peak at 0.8
    And the portfolio "outputs/portfolio.json" has a series of "SupplyTechnology" "ATSOLAR" for the year "2035" with 48 values that peak at 0.9

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
      And the file "outputs/extensions.json" parses as JSON technology extension record for "ATPHSS" having "energy_capital_cost_per_mwh_by_year" set to {"2030": 50000.0, "2035": 0.0}
