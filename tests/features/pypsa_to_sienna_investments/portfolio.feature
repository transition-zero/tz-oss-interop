@slow @fork_unsafe
Feature: a PyPSA network that states its own expansion becomes a Sienna portfolio
  pypsa-to-sienna-investments runs the operations steps and the investments step over one
  network and writes two documents: the base system, holding the fleet that already runs,
  and the portfolio, holding what a plan may build beside it.

  A component whose capacity a plan may change becomes a technology named after it. What the
  plan may build is the gap between p_nom_min and p_nom_max; what building it costs is the
  overnight cost, the fixed O&M, and the discount rate and lifetime PyPSA annuitises them
  with. The size of one unit and the technical life have no PyPSA column, so both reach the
  portfolio through the extensions sidecar.

  Scenario: an extendable generator becomes a SupplyTechnology
    Given a PyPSA network
    And the network contains bus "North_bus" carrier "AC" v_nom 380.0 location "North"
    And the network contains generator "REZ_Solar" on "North_bus" carrier "solar" p_nom 0 p_nom_extendable True
    And generator "REZ_Solar" has p_nom_min 0
    And generator "REZ_Solar" has p_nom_max 500
    And generator "REZ_Solar" has overnight_cost 1200000
    And generator "REZ_Solar" has discount_rate 0.07
    And generator "REZ_Solar" has lifetime 25
    And generator "REZ_Solar" has fom_cost 15000
    And the network is saved as "inputs/candidate.nc"
    And a file "inputs/extensions.json" containing the lines:
      | line                                    |
      | {                                       |
      |   "generator": [                        |
      |     {                                   |
      |       "name": "REZ_Solar",              |
      |       "unit_size_mw": 100.0,            |
      |       "technical_life_years": 30.0      |
      |     }                                   |
      |   ]                                     |
      | }                                       |
    When I run the pypsa investments translation with sidecar "inputs/extensions.json" against "inputs/candidate.nc" writing "outputs/portfolio.json"
    Then the file "outputs/portfolio.json" parses as a portfolio with 1 component of type "SupplyTechnology"
    And the file "outputs/portfolio.json" parses as a portfolio with component "SupplyTechnology" named "REZ_Solar" having "id" set to 1
    And the file "outputs/portfolio.json" parses as a portfolio with component "SupplyTechnology" named "REZ_Solar" having "available" set to true
    And the file "outputs/portfolio.json" parses as a portfolio with component "SupplyTechnology" named "REZ_Solar" having "power_systems_type" set to "RenewableDispatch"
    And the file "outputs/portfolio.json" parses as a portfolio with component "SupplyTechnology" named "REZ_Solar" having "prime_mover_type" set to "PVe"
    And the file "outputs/portfolio.json" parses as a portfolio with component "SupplyTechnology" named "REZ_Solar" having "region" set to [1]
    And the file "outputs/portfolio.json" parses as a portfolio with component "SupplyTechnology" named "REZ_Solar" having "capacity_limits.min" set to 0.0
    And the file "outputs/portfolio.json" parses as a portfolio with component "SupplyTechnology" named "REZ_Solar" having "capacity_limits.max" set to 500.0
    And the file "outputs/portfolio.json" parses as a portfolio with component "SupplyTechnology" named "REZ_Solar" having "capital_costs.capital_cost.function_data.proportional_term" set to 1200000.0
    And the file "outputs/portfolio.json" parses as a portfolio with component "SupplyTechnology" named "REZ_Solar" having "capital_costs.interconnection_cost" set to 0.0
    And the file "outputs/portfolio.json" parses as a portfolio with component "SupplyTechnology" named "REZ_Solar" having "operation_costs.cost_type" set to "RENEWABLE"
    And the file "outputs/portfolio.json" parses as a portfolio with component "SupplyTechnology" named "REZ_Solar" having "operation_costs.fixed" set to 15000.0
    And the file "outputs/portfolio.json" parses as a portfolio with component "SupplyTechnology" named "REZ_Solar" having "unit_size" set to 100.0
    And the file "outputs/portfolio.json" parses as a portfolio with component "SupplyTechnology" named "REZ_Solar" having "lifetime" set to 30
    And the file "outputs/portfolio.json" parses as a portfolio with component "SupplyTechnology" named "REZ_Solar" having "financial_data.capital_recovery_period" set to 25
    And the file "outputs/portfolio.json" parses as a portfolio with component "SupplyTechnology" named "REZ_Solar" having "financial_data.return_on_equity" set to 0.07
    And the file "outputs/portfolio.json" parses as a portfolio with component "SupplyTechnology" named "REZ_Solar" having "financial_data.debt_fraction" set to 0.0
    And the file "outputs/portfolio.json" parses as a portfolio with component "SupplyTechnology" named "REZ_Solar" having "financial_data.debt_rate" set to 0.0
    And the file "outputs/portfolio.json" parses as a portfolio with component "SupplyTechnology" named "REZ_Solar" having "financial_data.tax_rate" set to 0.0
    And the file "outputs/portfolio.json" parses as a portfolio with component "SupplyTechnology" named "REZ_Solar" having "financial_data.technology_base_year" set to 2020
    # A carrier the mappings file sends to a renewable type names no fuel, and no PyPSA field
    # states a ramp for a technology, so neither is written at all.
    And the file "outputs/portfolio.json" parses as a portfolio with component "SupplyTechnology" named "REZ_Solar" without field "fuel"
    And the file "outputs/portfolio.json" parses as a portfolio with component "SupplyTechnology" named "REZ_Solar" without field "ramp_limits"
    # The build the plan has yet to decide is not a component of the operations system.
    And the file "outputs/system.json" parses as JSON with 0 components of type "RenewableDispatch"
    And the file "decisions.md" contains "`pypsa.Generator.REZ_Solar.discount_rate` = 0.07"
    And the file "decisions.md" contains "with no debt the weighted average cost of capital equals the return on equity"

  Scenario: the portfolio names the base system it expands, its regions and its demand
    Given a PyPSA network
    And the network contains bus "North_bus" carrier "AC" v_nom 380.0 location "North"
    And the network contains load "North_load" on "North_bus" with static p_set 100
    And the network contains generator "REZ_Wind" on "North_bus" carrier "onwind" p_nom 0 p_nom_extendable True
    And generator "REZ_Wind" has p_nom_max 300
    And generator "REZ_Wind" has overnight_cost 900000
    And generator "REZ_Wind" has discount_rate 0.06
    And generator "REZ_Wind" has lifetime 20
    And the network is saved as "inputs/regions.nc"
    When I run the pypsa investments translation against "inputs/regions.nc" writing "outputs/portfolio.json"
    Then the file "outputs/portfolio.json" parses as JSON with "aggregation" set to "Area"
    And the file "outputs/portfolio.json" parses as JSON with "base_system_file" set to "system.json"
    And the file "outputs/portfolio.json" parses as JSON with "time_series_storage_file" set to "system_time_series_storage.h5"
    And the file "outputs/portfolio.json" parses as JSON with "financial_data.base_year" set to 2020
    And the file "outputs/portfolio.json" parses as JSON with "financial_data.discount_rate" set to 0.0
    And the file "outputs/portfolio.json" parses as a portfolio with 1 component of type "DemandRequirement"
    And the file "outputs/portfolio.json" parses as a portfolio with component "DemandRequirement" named "North_load" having "power_systems_type" set to "PowerLoad"
    And the file "outputs/portfolio.json" parses as a portfolio with component "DemandRequirement" named "North_load" having "region" set to [1]
    And the file "outputs/portfolio.json" parses as a portfolio where the "TopologyMapping" of base system "Area" 1 has "buses" set to ["North_bus"]
    And the file "decisions.md" contains "the buses of the base system that sit in this area"

  Scenario: an existing plant of the same carrier is the technology's fleet
    A technology stands for more of what a carrier already runs, so the base system components
    of that carrier are the devices it may add to and the devices a plan may retire.
    Given a PyPSA network
    And the network contains bus "North_bus" carrier "AC" v_nom 380.0 location "North"
    And the network contains generator "OldSolar" on "North_bus" carrier "solar" p_nom 200
    And generator "OldSolar" has build_year 1995
    And the network contains generator "REZ_Solar" on "North_bus" carrier "solar" p_nom 0 p_nom_extendable True
    And generator "REZ_Solar" has p_nom_max 500
    And generator "REZ_Solar" has overnight_cost 1200000
    And generator "REZ_Solar" has discount_rate 0.07
    And generator "REZ_Solar" has lifetime 25
    And the network is saved as "inputs/fleet.nc"
    And a file "inputs/extensions.json" containing the lines:
      | line                            |
      | {                               |
      |   "generator": [                |
      |     {                           |
      |       "name": "OldSolar",       |
      |       "retirement_year": 2040   |
      |     }                           |
      |   ]                             |
      | }                               |
    When I run the pypsa investments translation with sidecar "inputs/extensions.json" against "inputs/fleet.nc" writing "outputs/portfolio.json"
    Then the file "outputs/portfolio.json" parses as a portfolio where the "ExistingDevices" of "SupplyTechnology" "REZ_Solar" has "existing_devices" set to ["OldSolar"]
    And the file "outputs/portfolio.json" parses as a portfolio where the "RetirementPotential" of "SupplyTechnology" "REZ_Solar" has "eligible_generators" set to ["OldSolar"]
    And the file "outputs/portfolio.json" parses as a portfolio where the "RetirementPotential" of "SupplyTechnology" "REZ_Solar" has "build_year.OldSolar" set to 1995
    And the file "outputs/portfolio.json" parses as a portfolio where the "RetirementPotential" of "SupplyTechnology" "REZ_Solar" has "planned_retirement_year.OldSolar" set to 2040
    And the file "outputs/portfolio.json" parses as a portfolio where the "RetirementPotential" of "SupplyTechnology" "REZ_Solar" has "retirement_cost.function_data.proportional_term" set to 0.0
    And the file "outputs/system.json" parses as JSON with 1 component of type "RenewableDispatch"

  Scenario: an extendable storage unit becomes a StorageTechnology
    Given a PyPSA network
    And the network contains bus "North_bus" carrier "AC" v_nom 380.0 location "North"
    And the network contains storage unit "NewBattery" on "North_bus" carrier "PHS" p_nom 0 max_hours 4.0 efficiency_store 0.9 efficiency_dispatch 0.95 p_nom_extendable True
    And storage unit "NewBattery" has p_nom_max 300
    And storage unit "NewBattery" has overnight_cost 800000
    And storage unit "NewBattery" has discount_rate 0.07
    And storage unit "NewBattery" has lifetime 20
    And storage unit "NewBattery" has fom_cost 12000
    And the network is saved as "inputs/battery.nc"
    And a file "inputs/extensions.json" containing the lines:
      | line                                |
      | {                                   |
      |   "storage": [                      |
      |     {                               |
      |       "name": "NewBattery",         |
      |       "unit_size_mw": 50.0,         |
      |       "technical_life_years": 15.0  |
      |     }                               |
      |   ]                                 |
      | }                                   |
    When I run the pypsa investments translation with sidecar "inputs/extensions.json" against "inputs/battery.nc" writing "outputs/portfolio.json"
    Then the file "outputs/portfolio.json" parses as a portfolio with 1 component of type "StorageTechnology"
    And the file "outputs/portfolio.json" parses as a portfolio with component "StorageTechnology" named "NewBattery" having "power_systems_type" set to "EnergyReservoirStorage"
    And the file "outputs/portfolio.json" parses as a portfolio with component "StorageTechnology" named "NewBattery" having "storage_tech" set to "OTHER_MECH"
    And the file "outputs/portfolio.json" parses as a portfolio with component "StorageTechnology" named "NewBattery" having "prime_mover_type" set to "PS"
    And the file "outputs/portfolio.json" parses as a portfolio with component "StorageTechnology" named "NewBattery" having "capacity_limits_discharge.max" set to 300.0
    And the file "outputs/portfolio.json" parses as a portfolio with component "StorageTechnology" named "NewBattery" having "capacity_limits_energy.max" set to 1200.0
    And the file "outputs/portfolio.json" parses as a portfolio with component "StorageTechnology" named "NewBattery" having "capital_costs.discharge_capital_cost.function_data.proportional_term" set to 800000.0
    And the file "outputs/portfolio.json" parses as a portfolio with component "StorageTechnology" named "NewBattery" having "capital_costs.charge_capital_cost.function_data.proportional_term" set to 0.0
    And the file "outputs/portfolio.json" parses as a portfolio with component "StorageTechnology" named "NewBattery" having "operation_costs.cost_type" set to "STORAGE"
    And the file "outputs/portfolio.json" parses as a portfolio with component "StorageTechnology" named "NewBattery" having "operation_costs.fixed" set to 12000.0
    And the file "outputs/portfolio.json" parses as a portfolio with component "StorageTechnology" named "NewBattery" having "unit_size_discharge" set to 50.0
    And the file "outputs/portfolio.json" parses as a portfolio with component "StorageTechnology" named "NewBattery" having "efficiency.in" set to 0.9
    And the file "outputs/portfolio.json" parses as a portfolio with component "StorageTechnology" named "NewBattery" having "efficiency.out" set to 0.95
    And the file "outputs/portfolio.json" parses as a portfolio with component "StorageTechnology" named "NewBattery" having "lifetime" set to 15
    And the file "outputs/portfolio.json" parses as a portfolio with component "StorageTechnology" named "NewBattery" having "financial_data.capital_recovery_period" set to 20

  Scenario: a candidate that puts no ceiling on its build is left out, and the run completes
    A technology states the most capacity it may hold, and a p_nom_max PyPSA left at infinity
    is no such number.
    Given a PyPSA network
    And the network contains bus "North_bus" carrier "AC" v_nom 380.0 location "North"
    And the network contains generator "Unbounded_REZ" on "North_bus" carrier "solar" p_nom 0 p_nom_extendable True
    And generator "Unbounded_REZ" has overnight_cost 1200000
    And generator "Unbounded_REZ" has discount_rate 0.07
    And generator "Unbounded_REZ" has lifetime 25
    And the network contains generator "Bounded_REZ" on "North_bus" carrier "solar" p_nom 0 p_nom_extendable True
    And generator "Bounded_REZ" has p_nom_max 400
    And generator "Bounded_REZ" has overnight_cost 1200000
    And generator "Bounded_REZ" has discount_rate 0.07
    And generator "Bounded_REZ" has lifetime 25
    And the network is saved as "inputs/unbounded.nc"
    When I run the pypsa investments translation against "inputs/unbounded.nc" writing "outputs/portfolio.json"
    Then the file "outputs/portfolio.json" parses as a portfolio with 1 component of type "SupplyTechnology"
    And the file "outputs/portfolio.json" parses as a portfolio with no component "SupplyTechnology" named "Unbounded_REZ"
    And the file "decisions.md" contains "`pypsa.Generator.Unbounded_REZ.p_nom_max`"
    And the file "decisions.md" contains "p_nom_max is not a finite number of MW"
    And the log contains "1 Generator(s) are extendable and put no upper bound on the capacity a build may add"
