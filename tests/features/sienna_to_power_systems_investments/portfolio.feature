@slow @fork_unsafe
Feature: a Sienna portfolio becomes the document PowerSystemsInvestments reads
  sienna-to-power-systems-investments takes the two documents a translation wrote, the
  portfolio and the operations system it expands, and writes the four files
  PowerSystemsInvestmentsPortfolios.jl loads a Portfolio from.

  The package does not read the SiennaSchemas shape. It reads one flat component list with a
  __metadata__ block naming the Julia type to build, a base system whose name it derives from
  the portfolio's own, and nothing else. The time series travel in a companion document,
  because the package reads a component through a struct with no field for a UUID and loses
  every series the document carried.

  Background:
    Given a PyPSA network
    And the network has 24 snapshots at 60 minute intervals
    And the network contains bus "North_bus" carrier "AC" v_nom 380.0 location "North"
    And the network contains generator "REZ_Solar" on "North_bus" carrier "solar" p_nom 100 p_nom_extendable True p_max_pu_series 0.0 0.1 0.3 0.6 0.9 1.0 0.9 0.6 0.3 0.1 0.0 0.0 0.0 0.1 0.3 0.6 0.9 1.0 0.9 0.6 0.3 0.1 0.0 0.0
    And generator "REZ_Solar" has p_nom_min 100
    And generator "REZ_Solar" has p_nom_max 500
    And generator "REZ_Solar" has overnight_cost 1200000
    And generator "REZ_Solar" has discount_rate 0.07
    And generator "REZ_Solar" has lifetime 25
    And generator "REZ_Solar" has fom_cost 15000
    And the network contains load "North_load" on "North_bus" with p_set 200 250 300 350 400 450 200 250 300 350 400 450 200 250 300 350 400 450 200 250 300 350 400 450
    And the network is saved as "inputs/candidate.nc"
    When I translate "inputs/candidate.nc" into a Sienna portfolio
    And I run the investments solver translation writing "psi/portfolio.json"

  Scenario: a supply technology reaches the flat component list, naming the type to build
    Then the portfolio "psi/portfolio.json" contains 1 component of type "SupplyTechnology"
    And the portfolio "psi/portfolio.json" component "SupplyTechnology" named "REZ_Solar" has field "id" equal to 1
    And the portfolio "psi/portfolio.json" component "SupplyTechnology" named "REZ_Solar" has "__metadata__.module" equal to "PowerSystemsInvestmentsPortfolios"
    And the portfolio "psi/portfolio.json" component "SupplyTechnology" named "REZ_Solar" has "__metadata__.parameters" equal to "['RenewableDispatch']"
    And the portfolio "psi/portfolio.json" component "SupplyTechnology" named "REZ_Solar" has "__metadata__.construct_with_parameters" equal to "True"

  Scenario: an area becomes the Zone a technology names by id
    Then the portfolio "psi/portfolio.json" contains 1 component of type "Zone"
    And the portfolio "psi/portfolio.json" component "Zone" named "North" has field "id" equal to 1
    And the portfolio "psi/portfolio.json" component "SupplyTechnology" named "REZ_Solar" has field "region" equal to [1]

  Scenario: a capital cost becomes the value curve the package's field holds
    Then the portfolio "psi/portfolio.json" component "SupplyTechnology" named "REZ_Solar" has "capital_costs.__metadata__.type" equal to "InputOutputCurve"
    And the portfolio "psi/portfolio.json" component "SupplyTechnology" named "REZ_Solar" has "capital_costs.function_data.__metadata__.type" equal to "LinearFunctionData"
    And the portfolio "psi/portfolio.json" component "SupplyTechnology" named "REZ_Solar" has "capital_costs.function_data.proportional_term" equal to "1200000.0"

  Scenario: an operation cost names the concrete type at every depth
    Then the portfolio "psi/portfolio.json" component "SupplyTechnology" named "REZ_Solar" has "operation_costs.__metadata__.type" equal to "RenewableGenerationCost"
    And the portfolio "psi/portfolio.json" component "SupplyTechnology" named "REZ_Solar" has "operation_costs.variable.__metadata__.type" equal to "CostCurve"
    And the portfolio "psi/portfolio.json" component "SupplyTechnology" named "REZ_Solar" has "operation_costs.fixed" equal to "15000.0"

  Scenario: the rates a technology is financed at name the type the reader builds them from
    Then the portfolio "psi/portfolio.json" component "SupplyTechnology" named "REZ_Solar" has "financial_data.__metadata__.type" equal to "TechnologyFinancialData"
    And the portfolio "psi/portfolio.json" component "SupplyTechnology" named "REZ_Solar" has "financial_data.return_on_equity" equal to "0.07"

  Scenario: a field the reader rejects as null states an empty value instead
    Then the portfolio "psi/portfolio.json" component "SupplyTechnology" named "REZ_Solar" has field "fuel" equal to []
    And the portfolio "psi/portfolio.json" component "SupplyTechnology" named "REZ_Solar" has field "requirements" equal to []
    And the portfolio "psi/portfolio.json" component "SupplyTechnology" named "REZ_Solar" has field "co2" equal to {}
    And the portfolio "psi/portfolio.json" component "SupplyTechnology" named "REZ_Solar" has field "ramp_limits" equal to {"up": 1.0, "down": 1.0}

  Scenario: the portfolio carries no time series, so it names no store
    Then the portfolio "psi/portfolio.json" states no time series storage file

  Scenario: the base system sits beside the portfolio, named as the reader derives the name
    Then the file "psi/portfolio_base_system.json" exists
    And the file "psi/portfolio_base_system_time_series.h5" exists

  Scenario: a capacity factor profile reaches the companion with the features the model looks it up by
    Then the series document "psi/portfolio_series.json" holds 2 records
    And the series document "psi/portfolio_series.json" record for "SupplyTechnology" named "REZ_Solar" holds series "ops_variable_cap_factor" for year "2020" representative day 1
    And the series document "psi/portfolio_series.json" record for "SupplyTechnology" named "REZ_Solar" has field "weight" equal to 365.0

  Scenario: a demand profile reaches the companion in MW, and states the period it falls in
    Then the series document "psi/portfolio_series.json" record for "DemandRequirement" named "North_load" holds series "ops_demand" for year "2020" representative day 1
    And the series document "psi/portfolio_series.json" states one period from "2020-01-01" to "2020-12-31"
