@slow @fork_unsafe
Feature: a PLEXOS expansion plan becomes a Sienna investments portfolio
  plexos-to-sienna-investments is a composed pipeline, not a translator of its own: it runs
  plexos-to-pypsa and then pypsa-to-sienna-investments over the network the first leg wrote.
  The second leg writes two documents, the base system holding the fleet that already runs
  and the portfolio holding what the plan may build beside it.

  An object stating Max Units Built may be built, and each one becomes a technology named
  after it. What building it costs travels as PyPSA's own expansion fields; the size of one
  unit and the Technical Life have no PyPSA column, so both cross the hub in the extensions
  sidecar and are read back here.

  Scenario: a candidate generator becomes a SupplyTechnology
    Given a Plexos model
    And the model states "Build Cost" in "$/kW"
    And the model states "FO&M Charge" in "$/kW/yr"
    And the model states "WACC" in "%"
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains generator "REZ_Solar" with "node=North_Node, category=Solar, Max Capacity=100, Units=0, Max Units Built=5, Build Cost=1200, WACC=7, Economic Life=25, Technical Life=30, FO&M Charge=15"
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
      | category       | Solar       | RenewableDispatch     |                  | PVe                     |
    When I run the plexos-to-sienna-investments chain against "inputs/model.xml" writing "outputs/portfolio.json"
    Then the file "outputs/portfolio.json" parses as valid JSON
    And the file "outputs/portfolio.json" parses as a portfolio with 1 component of type "SupplyTechnology"
    And the file "outputs/portfolio.json" parses as a portfolio with component "SupplyTechnology" named "REZ_Solar" having "power_systems_type" set to "RenewableDispatch"
    And the file "outputs/portfolio.json" parses as a portfolio with component "SupplyTechnology" named "REZ_Solar" having "prime_mover_type" set to "PVe"
    And the file "outputs/portfolio.json" parses as a portfolio with component "SupplyTechnology" named "REZ_Solar" having "available" set to true
    And the file "outputs/portfolio.json" parses as a portfolio with component "SupplyTechnology" named "REZ_Solar" having "region" set to [1]
    And the file "outputs/portfolio.json" parses as a portfolio with component "SupplyTechnology" named "REZ_Solar" having "capacity_limits.min" set to 0.0
    And the file "outputs/portfolio.json" parses as a portfolio with component "SupplyTechnology" named "REZ_Solar" having "capacity_limits.max" set to 500.0
    And the file "outputs/portfolio.json" parses as a portfolio with component "SupplyTechnology" named "REZ_Solar" having "capital_costs.capital_cost.function_data.proportional_term" set to 1200000.0
    And the file "outputs/portfolio.json" parses as a portfolio with component "SupplyTechnology" named "REZ_Solar" having "operation_costs.fixed" set to 15000.0
    And the file "outputs/portfolio.json" parses as a portfolio with component "SupplyTechnology" named "REZ_Solar" having "unit_size" set to 100.0
    And the file "outputs/portfolio.json" parses as a portfolio with component "SupplyTechnology" named "REZ_Solar" having "lifetime" set to 30
    And the file "outputs/portfolio.json" parses as a portfolio with component "SupplyTechnology" named "REZ_Solar" having "financial_data.capital_recovery_period" set to 25
    And the file "outputs/portfolio.json" parses as a portfolio with component "SupplyTechnology" named "REZ_Solar" having "financial_data.return_on_equity" set to 0.07
    And the file "outputs/system.json" parses as JSON with 0 components of type "RenewableDispatch"
    And the file "outputs/system.json" parses as JSON with 1 component of type "Area"

  Scenario: a candidate Battery becomes a StorageTechnology
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains battery "NewBattery" on node "North_Node" with max_power 50 capacity 200 charge_efficiency 90 initial_soc 50
    And battery "NewBattery" has property "Units" 0
    And battery "NewBattery" has property "Max Units Built" 6
    And battery "NewBattery" has property "Build Cost" 800000
    And battery "NewBattery" has property "WACC" 0.07
    And battery "NewBattery" has property "Economic Life" 20
    And battery "NewBattery" has property "Technical Life" 15
    And the model is saved as "inputs/battery.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
      | category       | Solar       | RenewableDispatch     |                  | PVe                     |
    When I run the plexos-to-sienna-investments chain against "inputs/battery.xml" writing "outputs/portfolio.json"
    Then the file "outputs/portfolio.json" parses as a portfolio with 1 component of type "StorageTechnology"
    And the file "outputs/portfolio.json" parses as a portfolio with component "StorageTechnology" named "NewBattery" having "power_systems_type" set to "EnergyReservoirStorage"
    And the file "outputs/portfolio.json" parses as a portfolio with component "StorageTechnology" named "NewBattery" having "prime_mover_type" set to "BA"
    And the file "outputs/portfolio.json" parses as a portfolio with component "StorageTechnology" named "NewBattery" having "storage_tech" set to "OTHER_MECH"
    And the file "outputs/portfolio.json" parses as a portfolio with component "StorageTechnology" named "NewBattery" having "capacity_limits_discharge.max" set to 300.0
    And the file "outputs/portfolio.json" parses as a portfolio with component "StorageTechnology" named "NewBattery" having "capacity_limits_energy.max" set to 1200.0
    And the file "outputs/portfolio.json" parses as a portfolio with component "StorageTechnology" named "NewBattery" having "capital_costs.discharge_capital_cost.function_data.proportional_term" set to 800000.0
    And the file "outputs/portfolio.json" parses as a portfolio with component "StorageTechnology" named "NewBattery" having "unit_size_discharge" set to 50.0
    And the file "outputs/portfolio.json" parses as a portfolio with component "StorageTechnology" named "NewBattery" having "lifetime" set to 15
    And the file "outputs/portfolio.json" parses as a portfolio with component "StorageTechnology" named "NewBattery" having "financial_data.capital_recovery_period" set to 20

  Scenario: a plant that already runs is the fleet its technology adds to
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains generator "OldSolar" with "node=North_Node, category=Solar, Max Capacity=80, Units=1"
    And the model contains generator "REZ_Solar" with "node=North_Node, category=Solar, Max Capacity=100, Units=0, Max Units Built=5, Build Cost=1200000, WACC=0.07, Economic Life=25"
    And the model is saved as "inputs/fleet.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
      | category       | Solar       | RenewableDispatch     |                  | PVe                     |
    When I run the plexos-to-sienna-investments chain against "inputs/fleet.xml" writing "outputs/portfolio.json"
    Then the file "outputs/system.json" parses as JSON with 1 component of type "RenewableDispatch"
    And the file "outputs/portfolio.json" parses as a portfolio where the "ExistingDevices" of "SupplyTechnology" "REZ_Solar" has "existing_devices" set to ["OldSolar"]
    And the file "outputs/portfolio.json" parses as a portfolio where the "RetirementPotential" of "SupplyTechnology" "REZ_Solar" has "eligible_generators" set to ["OldSolar"]

  Scenario: a Constraint over the whole model becomes a CarbonCaps
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains fuel "Natural Gas" with price 3
    And the model contains generator "GasPlant" with "node=North_Node, fuel=Natural Gas, Max Capacity=500, Heat Rate=9, Units=1"
    And the model contains generator "REZ_Solar" with "node=North_Node, category=Solar, Max Capacity=100, Units=0, Max Units Built=5, Build Cost=1200000, WACC=0.07, Economic Life=25"
    And the model contains constraint "CarbonBudget" over:
      | class     | name      | coefficient property   | coefficient |
      | Generator | GasPlant  | Generation Coefficient | 1           |
      | Generator | REZ_Solar | Generation Coefficient | 1           |
    And constraint "CarbonBudget" states "Sense" of -1
    And constraint "CarbonBudget" states "RHS Year" of 20
    And the model is saved as "inputs/cap.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
      | fuel           | Natural Gas | ThermalStandard       | NATURAL_GAS      | CC                      |
      | category       | Solar       | RenewableDispatch     |                  | PVe                     |
    When I run the plexos-to-sienna-investments chain against "inputs/cap.xml" writing "outputs/portfolio.json"
    Then the file "outputs/portfolio.json" parses as a portfolio with 1 component of type "CarbonCaps"
    And the file "outputs/portfolio.json" parses as a portfolio with component "CarbonCaps" named "CarbonBudget" having "max_mtons" set to 20.0
    And the file "outputs/portfolio.json" parses as a portfolio with component "CarbonCaps" named "CarbonBudget" having "available" set to true
    And the file "outputs/portfolio.json" parses as a portfolio with component "CarbonCaps" named "CarbonBudget" without field "target_year"
    And the file "decisions.md" contains "the year right-hand side of the constraint"

  Scenario: a Constraint over part of the model is left out, and the run completes
    CarbonCaps names no members and no region, so a cap written from a constraint over some
    of the model would hold all of it.
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains fuel "Natural Gas" with price 3
    And the model contains generator "GasPlant" with "node=North_Node, fuel=Natural Gas, Max Capacity=500, Heat Rate=9, Units=1"
    And the model contains generator "REZ_Solar" with "node=North_Node, category=Solar, Max Capacity=100, Units=0, Max Units Built=5, Build Cost=1200000, WACC=0.07, Economic Life=25"
    And the model contains constraint "GasCap" over:
      | class     | name     | coefficient property   | coefficient |
      | Generator | GasPlant | Generation Coefficient | 1           |
    And constraint "GasCap" states "Sense" of -1
    And constraint "GasCap" states "RHS Year" of 5
    And the model is saved as "inputs/scoped.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
      | fuel           | Natural Gas | ThermalStandard       | NATURAL_GAS      | CC                      |
      | category       | Solar       | RenewableDispatch     |                  | PVe                     |
    When I run the plexos-to-sienna-investments chain against "inputs/scoped.xml" writing "outputs/portfolio.json"
    Then the file "outputs/portfolio.json" parses as a portfolio with 0 components of type "CarbonCaps"
    And the file "outputs/portfolio.json" parses as a portfolio with 1 component of type "SupplyTechnology"
    And the file "decisions.md" contains "`pypsa.constraint.GasCap`"
    And the file "decisions.md" contains "CarbonCaps names no members and no region"
    And the log contains "1 constraint(s) weight a named subset of the model rather than all of it, so each is left out"
