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
    Then the file "outputs/portfolio.json" parses as JSON with 1 component of type "SupplyTechnology"
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "REZ_Solar" having "id" set to 1
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "REZ_Solar" having "available" set to true
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "REZ_Solar" having "power_systems_type" set to "RenewableDispatch"
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "REZ_Solar" having "prime_mover_type" set to "PVe"
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "REZ_Solar" having "region" set to [1]
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "REZ_Solar" having "capacity_limits.min" set to 0.0
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "REZ_Solar" having "capacity_limits.max" set to 500.0
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "REZ_Solar" having "capital_costs.capital_cost.function_data.proportional_term" set to 1200000.0
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "REZ_Solar" having "capital_costs.interconnection_cost" set to 0.0
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "REZ_Solar" having "operation_costs.cost_type" set to "RENEWABLE"
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "REZ_Solar" having "operation_costs.fixed" set to 15000.0
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "REZ_Solar" without field "operation_costs.start_up"
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "REZ_Solar" without field "operation_costs.shut_down"
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "REZ_Solar" having "unit_size" set to 100.0
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "REZ_Solar" having "lifetime" set to 30
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "REZ_Solar" having "financial_data.capital_recovery_period" set to 25
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "REZ_Solar" having "financial_data.return_on_equity" set to 0.07
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "REZ_Solar" having "financial_data.debt_fraction" set to 0.0
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "REZ_Solar" having "financial_data.debt_rate" set to 0.0
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "REZ_Solar" having "financial_data.tax_rate" set to 0.0
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "REZ_Solar" having "financial_data.technology_base_year" set to 2020
    # A carrier the mappings file sends to a renewable type names no fuel, and no PyPSA field
    # states a ramp for a technology, so neither is written at all.
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "REZ_Solar" without field "fuel"
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "REZ_Solar" without field "ramp_limits"
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
    And the file "outputs/portfolio.json" parses as JSON with 1 component of type "DemandRequirement"
    And the file "outputs/portfolio.json" parses as JSON with component "DemandRequirement" named "North_load" having "power_systems_type" set to "PowerLoad"
    And the file "outputs/portfolio.json" parses as JSON with component "DemandRequirement" named "North_load" having "region" set to [1]
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
    Then the file "outputs/portfolio.json" parses as JSON with 1 component of type "StorageTechnology"
    And the file "outputs/portfolio.json" parses as JSON with component "StorageTechnology" named "NewBattery" having "power_systems_type" set to "EnergyReservoirStorage"
    And the file "outputs/portfolio.json" parses as JSON with component "StorageTechnology" named "NewBattery" having "storage_tech" set to "OTHER_MECH"
    And the file "outputs/portfolio.json" parses as JSON with component "StorageTechnology" named "NewBattery" having "prime_mover_type" set to "PS"
    And the file "outputs/portfolio.json" parses as JSON with component "StorageTechnology" named "NewBattery" having "capacity_limits_discharge.max" set to 300.0
    And the file "outputs/portfolio.json" parses as JSON with component "StorageTechnology" named "NewBattery" having "capacity_limits_energy.max" set to 1200.0
    And the file "outputs/portfolio.json" parses as JSON with component "StorageTechnology" named "NewBattery" having "capital_costs.discharge_capital_cost.function_data.proportional_term" set to 800000.0
    And the file "outputs/portfolio.json" parses as JSON with component "StorageTechnology" named "NewBattery" having "capital_costs.charge_capital_cost.function_data.proportional_term" set to 0.0
    And the file "outputs/portfolio.json" parses as JSON with component "StorageTechnology" named "NewBattery" having "operation_costs.cost_type" set to "STORAGE"
    And the file "outputs/portfolio.json" parses as JSON with component "StorageTechnology" named "NewBattery" having "operation_costs.fixed" set to 12000.0
    And the file "outputs/portfolio.json" parses as JSON with component "StorageTechnology" named "NewBattery" having "unit_size_discharge" set to 50.0
    And the file "outputs/portfolio.json" parses as JSON with component "StorageTechnology" named "NewBattery" having "efficiency.in" set to 0.9
    And the file "outputs/portfolio.json" parses as JSON with component "StorageTechnology" named "NewBattery" having "efficiency.out" set to 0.95
    And the file "outputs/portfolio.json" parses as JSON with component "StorageTechnology" named "NewBattery" having "lifetime" set to 15
    And the file "outputs/portfolio.json" parses as JSON with component "StorageTechnology" named "NewBattery" having "financial_data.capital_recovery_period" set to 20

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
    Then the file "outputs/portfolio.json" parses as JSON with 1 component of type "SupplyTechnology"
    And the file "outputs/portfolio.json" parses as a portfolio with no component "SupplyTechnology" named "Unbounded_REZ"
    And the file "decisions.md" contains "`pypsa.Generator.Unbounded_REZ.p_nom_max`"
    And the file "decisions.md" contains "p_nom_max is not a finite number of MW"
    And the log contains "1 Generator(s) are extendable and put no upper bound on the capacity a build may add"

  Scenario: a candidate that names a thermal or a hydro carrier gets that cost representation
    GenericOperationCost is chosen by cost_type, and only the thermal variant states a
    start-up and a shut-down cost.
    Given a PyPSA network
    And the network contains bus "North_bus" carrier "AC" v_nom 380.0 location "North"
    And the network contains generator "New_CCGT" on "North_bus" carrier "CCGT" p_nom 0 p_nom_extendable True
    And generator "New_CCGT" has p_nom_max 400
    And generator "New_CCGT" has overnight_cost 900000
    And generator "New_CCGT" has discount_rate 0.08
    And generator "New_CCGT" has lifetime 30
    And the network contains generator "New_Hydro" on "North_bus" carrier "hydro" p_nom 0 p_nom_extendable True
    And generator "New_Hydro" has p_nom_max 200
    And generator "New_Hydro" has overnight_cost 2000000
    And generator "New_Hydro" has discount_rate 0.05
    And generator "New_Hydro" has lifetime 40
    And the network is saved as "inputs/cost_types.nc"
    When I run the pypsa investments translation against "inputs/cost_types.nc" writing "outputs/portfolio.json"
    Then the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "New_CCGT" having "power_systems_type" set to "ThermalStandard"
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "New_CCGT" having "operation_costs.cost_type" set to "THERMAL"
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "New_CCGT" having "operation_costs.start_up" set to 0.0
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "New_CCGT" having "operation_costs.shut_down" set to 0.0
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "New_CCGT" having "fuel" set to ["NATURAL_GAS"]
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "New_Hydro" having "power_systems_type" set to "HydroDispatch"
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "New_Hydro" having "operation_costs.cost_type" set to "HYDRO_GEN"
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "New_Hydro" without field "operation_costs.start_up"

  Scenario: every component of the portfolio takes its id from one counter
    An association names the component it describes by id alone, so two components of
    different types may not share one.
    Given a PyPSA network
    And the network contains bus "North_bus" carrier "AC" v_nom 380.0 location "North"
    And the network contains load "North_load" on "North_bus" with static p_set 100
    And the network contains generator "REZ_Solar" on "North_bus" carrier "solar" p_nom 0 p_nom_extendable True
    And generator "REZ_Solar" has p_nom_max 500
    And generator "REZ_Solar" has overnight_cost 1200000
    And generator "REZ_Solar" has discount_rate 0.07
    And generator "REZ_Solar" has lifetime 25
    And the network contains storage unit "NewBattery" on "North_bus" carrier "PHS" p_nom 0 max_hours 4.0 efficiency_store 0.9 efficiency_dispatch 0.95 p_nom_extendable True
    And storage unit "NewBattery" has p_nom_max 300
    And storage unit "NewBattery" has overnight_cost 800000
    And storage unit "NewBattery" has discount_rate 0.07
    And storage unit "NewBattery" has lifetime 20
    And the network is saved as "inputs/ids.nc"
    When I run the pypsa investments translation against "inputs/ids.nc" writing "outputs/portfolio.json"
    Then the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "REZ_Solar" having "id" set to 1
    And the file "outputs/portfolio.json" parses as JSON with component "StorageTechnology" named "NewBattery" having "id" set to 2
    And the file "outputs/portfolio.json" parses as JSON with component "DemandRequirement" named "North_load" having "id" set to 3

  Scenario: a load whose bus prices a shortfall is a demand the base system may cut
    The base system writes such a load as an InterruptiblePowerLoad, and power_systems_type
    names the type the base system holds it as.
    Given a PyPSA network
    And the network contains bus "North_bus" carrier "AC" v_nom 380.0 location "North"
    And the network contains load "North_load" on "North_bus" with static p_set 100
    And the network is saved as "inputs/voll.nc"
    And a file "inputs/extensions.json" containing the lines:
      | line |
      | {"bus": [{"name": "North_bus", "value_of_lost_load": 9000.0}]} |
    When I run the pypsa investments translation with sidecar "inputs/extensions.json" against "inputs/voll.nc" writing "outputs/portfolio.json"
    Then the file "outputs/system.json" parses as JSON with 1 components of type "InterruptiblePowerLoad"
    And the file "outputs/portfolio.json" parses as JSON with component "DemandRequirement" named "North_load" having "power_systems_type" set to "InterruptiblePowerLoad"

  Scenario: a candidate the network prices nothing for is left out, and the run completes
    PyPSA leaves overnight_cost and discount_rate at NaN rather than at zero, and a
    technology written from either would build for free or discount at nothing.
    Given a PyPSA network
    And the network contains bus "North_bus" carrier "AC" v_nom 380.0 location "North"
    And the network contains generator "Free_REZ" on "North_bus" carrier "solar" p_nom 0 p_nom_extendable True
    And generator "Free_REZ" has p_nom_max 400
    And generator "Free_REZ" has discount_rate 0.07
    And generator "Free_REZ" has lifetime 25
    And the network contains generator "Unrated_REZ" on "North_bus" carrier "solar" p_nom 0 p_nom_extendable True
    And generator "Unrated_REZ" has p_nom_max 400
    And generator "Unrated_REZ" has overnight_cost 1200000
    And generator "Unrated_REZ" has lifetime 25
    And the network contains generator "Priced_REZ" on "North_bus" carrier "solar" p_nom 0 p_nom_extendable True
    And generator "Priced_REZ" has p_nom_max 400
    And generator "Priced_REZ" has overnight_cost 1200000
    And generator "Priced_REZ" has discount_rate 0.07
    And generator "Priced_REZ" has lifetime 25
    And the network is saved as "inputs/unpriced.nc"
    When I run the pypsa investments translation against "inputs/unpriced.nc" writing "outputs/portfolio.json"
    Then the file "outputs/portfolio.json" parses as JSON with 1 component of type "SupplyTechnology"
    And the file "outputs/portfolio.json" parses as a portfolio with no component "SupplyTechnology" named "Free_REZ"
    And the file "outputs/portfolio.json" parses as a portfolio with no component "SupplyTechnology" named "Unrated_REZ"
    And the file "decisions.md" contains "`pypsa.Generator.Free_REZ.overnight_cost`"
    And the file "decisions.md" contains "`pypsa.Generator.Unrated_REZ.discount_rate`"
    And the log contains "1 Generator(s) are extendable and put no overnight cost on the capacity a build adds"
    And the log contains "1 Generator(s) are extendable and state no discount rate"

  Scenario: a sidecar number that is not finite leaves its field out, and the run completes
    A sidecar is JSON, and a JSON reader accepts the words NaN and Infinity.
    Given a PyPSA network
    And the network contains bus "North_bus" carrier "AC" v_nom 380.0 location "North"
    And the network contains generator "REZ_Solar" on "North_bus" carrier "solar" p_nom 0 p_nom_extendable True
    And generator "REZ_Solar" has p_nom_max 500
    And generator "REZ_Solar" has overnight_cost 1200000
    And generator "REZ_Solar" has discount_rate 0.07
    And generator "REZ_Solar" has lifetime 25
    And the network is saved as "inputs/non_finite_sidecar.nc"
    And a file "inputs/extensions.json" containing the lines:
      | line |
      | {"generator": [{"name": "REZ_Solar", "unit_size_mw": Infinity, "technical_life_years": NaN}]} |
    When I run the pypsa investments translation with sidecar "inputs/extensions.json" against "inputs/non_finite_sidecar.nc" writing "outputs/portfolio.json"
    Then the file "outputs/portfolio.json" parses as JSON with 1 component of type "SupplyTechnology"
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "REZ_Solar" without field "unit_size"
    And the file "outputs/portfolio.json" parses as JSON with component "SupplyTechnology" named "REZ_Solar" without field "lifetime"
    And the file "decisions.md" contains "`pypsa.Generator.REZ_Solar._unit_size_mw` = inf"

  Scenario: a candidate whose lifetime is below one year is left out, and the run completes
    A capital recovery period is a whole number of years, so a lifetime below one year leaves
    no years to recover the overnight cost across.
    Given a PyPSA network
    And the network contains bus "North_bus" carrier "AC" v_nom 380.0 location "North"
    And the network contains generator "REZ_Solar" on "North_bus" carrier "solar" p_nom 0 p_nom_extendable True
    And generator "REZ_Solar" has p_nom_max 500
    And generator "REZ_Solar" has overnight_cost 1200000
    And generator "REZ_Solar" has discount_rate 0.07
    And generator "REZ_Solar" has lifetime 0.5
    And the network is saved as "inputs/short_lifetime.nc"
    When I run the pypsa investments translation against "inputs/short_lifetime.nc" writing "outputs/portfolio.json"
    Then the file "outputs/portfolio.json" parses as JSON with 0 components of type "SupplyTechnology"
    And the log contains "1 Generator(s) are extendable and state a lifetime below one year"
    And the file "decisions.md" contains "lifetime is below one year"

  Scenario: a candidate whose floor is above its ceiling is left out, and the run completes
    A technology states a capacity floor and a capacity ceiling, and no capacity can meet a
    floor above the ceiling.
    Given a PyPSA network
    And the network contains bus "North_bus" carrier "AC" v_nom 380.0 location "North"
    And the network contains generator "REZ_Solar" on "North_bus" carrier "solar" p_nom 0 p_nom_extendable True
    And generator "REZ_Solar" has p_nom_min 600
    And generator "REZ_Solar" has p_nom_max 500
    And generator "REZ_Solar" has overnight_cost 1200000
    And generator "REZ_Solar" has discount_rate 0.07
    And generator "REZ_Solar" has lifetime 25
    And the network is saved as "inputs/inverted_limits.nc"
    When I run the pypsa investments translation against "inputs/inverted_limits.nc" writing "outputs/portfolio.json"
    Then the file "outputs/portfolio.json" parses as JSON with 0 components of type "SupplyTechnology"
    And the log contains "1 Generator(s) are extendable and state a capacity floor above the capacity a build may reach"
    And the file "decisions.md" contains "p_nom_min is above p_nom_max"

  Scenario: a storage candidate with no energy ceiling is left out, and the run completes
    A unit whose max_hours is not a finite number puts no bound on the energy a build may add.
    Given a PyPSA network
    And the network contains bus "North_bus" carrier "AC" v_nom 380.0 location "North"
    And the network contains storage unit "NewPHS" on "North_bus" carrier "PHS" p_nom 0 max_hours inf efficiency_store 0.9 efficiency_dispatch 0.95 p_nom_extendable True
    And storage unit "NewPHS" has p_nom_max 300
    And storage unit "NewPHS" has overnight_cost 800000
    And storage unit "NewPHS" has discount_rate 0.07
    And storage unit "NewPHS" has lifetime 20
    And the network is saved as "inputs/unbounded_energy.nc"
    When I run the pypsa investments translation against "inputs/unbounded_energy.nc" writing "outputs/portfolio.json"
    Then the file "outputs/portfolio.json" parses as JSON with 0 components of type "StorageTechnology"
    And the log contains "1 StorageUnit(s) are extendable and put no upper bound on the energy a build may add"
    And the file "decisions.md" contains "max_hours is not a finite number of hours"

  Scenario: a storage candidate that holds no energy is left out, and the run completes
    A StorageTechnology states the energy a build may add as max_hours of its power, so a
    unit stating no hours could build power it can never charge.
    Given a PyPSA network
    And the network contains bus "North_bus" carrier "AC" v_nom 380.0 location "North"
    And the network contains storage unit "Flat_PHS" on "North_bus" carrier "PHS" p_nom 0 max_hours 0.0 efficiency_store 0.9 efficiency_dispatch 0.95 p_nom_extendable True
    And storage unit "Flat_PHS" has p_nom_max 300
    And storage unit "Flat_PHS" has overnight_cost 800000
    And storage unit "Flat_PHS" has discount_rate 0.07
    And storage unit "Flat_PHS" has lifetime 20
    And the network is saved as "inputs/no_energy.nc"
    When I run the pypsa investments translation against "inputs/no_energy.nc" writing "outputs/portfolio.json"
    Then the file "outputs/portfolio.json" parses as JSON with 0 components of type "StorageTechnology"
    And the file "decisions.md" contains "`pypsa.StorageUnit.Flat_PHS.max_hours`"
    And the file "decisions.md" contains "so the energy capacity limits a build could add are zero MWh"
    And the log contains "1 StorageUnit(s) are extendable and hold no energy"

  Scenario: a candidate whose carrier names another kind's Sienna type is left out
    A StorageTechnology states the base system type a build becomes, and the mappings file may
    send a carrier to a type no storage unit is ever written as.
    Given a PyPSA network
    And the network contains bus "North_bus" carrier "AC" v_nom 380.0 location "North"
    And the network contains storage unit "Odd_PHS" on "North_bus" carrier "solar" p_nom 0 max_hours 4.0 efficiency_store 0.9 efficiency_dispatch 0.95 p_nom_extendable True
    And storage unit "Odd_PHS" has p_nom_max 300
    And storage unit "Odd_PHS" has overnight_cost 800000
    And storage unit "Odd_PHS" has discount_rate 0.07
    And storage unit "Odd_PHS" has lifetime 20
    And the network is saved as "inputs/wrong_target.nc"
    When I run the pypsa investments translation against "inputs/wrong_target.nc" writing "outputs/portfolio.json"
    Then the file "outputs/portfolio.json" parses as JSON with 0 components of type "StorageTechnology"
    And the file "decisions.md" contains "the user mappings file sends this carrier to a type this candidate never holds"
    And the log contains "1 StorageUnit(s) may be built and have a carrier the mappings file sends to a Sienna type this kind of candidate never becomes"

  Scenario: a generator and a storage unit of one name keep their own build years
    PyPSA names a generator and a storage unit independently, so one name may belong to both
    and each technology reads the year its own class states.
    Given a PyPSA network
    And the network contains bus "North_bus" carrier "AC" v_nom 380.0 location "North"
    And the network contains generator "Shared" on "North_bus" carrier "solar" p_nom 200
    And generator "Shared" has build_year 1995
    And the network contains storage unit "Shared" on "North_bus" carrier "PHS" p_nom 100 max_hours 4.0 efficiency_store 0.9 efficiency_dispatch 0.95
    And storage unit "Shared" has build_year 2005
    And the network contains generator "REZ_Solar" on "North_bus" carrier "solar" p_nom 0 p_nom_extendable True
    And generator "REZ_Solar" has p_nom_max 500
    And generator "REZ_Solar" has overnight_cost 1200000
    And generator "REZ_Solar" has discount_rate 0.07
    And generator "REZ_Solar" has lifetime 25
    And the network contains storage unit "NewPHS" on "North_bus" carrier "PHS" p_nom 0 max_hours 4.0 efficiency_store 0.9 efficiency_dispatch 0.95 p_nom_extendable True
    And storage unit "NewPHS" has p_nom_max 300
    And storage unit "NewPHS" has overnight_cost 800000
    And storage unit "NewPHS" has discount_rate 0.07
    And storage unit "NewPHS" has lifetime 20
    And the network is saved as "inputs/shared_names.nc"
    When I run the pypsa investments translation against "inputs/shared_names.nc" writing "outputs/portfolio.json"
    Then the file "outputs/portfolio.json" parses as a portfolio where the "RetirementPotential" of "SupplyTechnology" "REZ_Solar" has "build_year.Shared" set to 1995
    And the file "outputs/portfolio.json" parses as a portfolio where the "RetirementPotential" of "StorageTechnology" "NewPHS" has "build_year.Shared" set to 2005

  Scenario: a hydro storage candidate stands for the hydro units already running
    A StorageUnit whose carrier the mappings file sends to HydroDispatch is still a storage
    technology, and the base system holds the units of that carrier as HydroDispatch, so
    those are the devices the technology adds to.
    Given a PyPSA network
    And the network has 3 snapshots at 60 minute intervals
    And the network contains bus "North_bus" carrier "AC" v_nom 380.0 location "North"
    And the network contains storage unit "OldHydro" on "North_bus" carrier "hydro" p_nom 200 max_hours 6.0 efficiency_dispatch 0.9 inflow 10.0 20.0 30.0
    And storage unit "OldHydro" has build_year 1980
    And the network contains storage unit "NewHydro" on "North_bus" carrier "hydro" p_nom 0 max_hours 6.0 efficiency_store 0.9 efficiency_dispatch 0.95 p_nom_extendable True
    And storage unit "NewHydro" has p_nom_max 300
    And storage unit "NewHydro" has overnight_cost 900000
    And storage unit "NewHydro" has discount_rate 0.07
    And storage unit "NewHydro" has lifetime 30
    And the network is saved as "inputs/hydro_fleet.nc"
    When I run the pypsa investments translation against "inputs/hydro_fleet.nc" writing "outputs/portfolio.json"
    Then the file "outputs/system.json" parses as JSON with 1 components of type "HydroDispatch"
    And the file "outputs/portfolio.json" parses as JSON with component "StorageTechnology" named "NewHydro" having "power_systems_type" set to "HydroDispatch"
    And the file "outputs/portfolio.json" parses as a portfolio where the "ExistingDevices" of "StorageTechnology" "NewHydro" has "existing_devices" set to ["OldHydro"]
    And the file "outputs/portfolio.json" parses as a portfolio where the "RetirementPotential" of "StorageTechnology" "NewHydro" has "eligible_generators" set to ["OldHydro"]
    And the file "outputs/portfolio.json" parses as a portfolio where the "RetirementPotential" of "StorageTechnology" "NewHydro" has "build_year.OldHydro" set to 1980

  Scenario: a technology's fleet is the plant of its own region
    A portfolio groups its technologies by region, so a technology stands for more of what its
    own region already runs. A plant of the same carrier in another region is not one it adds
    to, and not one a build of it may retire.
    Given a PyPSA network
    And the network contains bus "North_bus" carrier "AC" v_nom 380.0 location "North"
    And the network contains bus "South_bus" carrier "AC" v_nom 380.0 location "South"
    And the network contains generator "OldSolar_North" on "North_bus" carrier "solar" p_nom 100
    And the network contains generator "OldSolar_South" on "South_bus" carrier "solar" p_nom 200
    And the network contains generator "REZ_Solar_North" on "North_bus" carrier "solar" p_nom 0 p_nom_extendable True
    And generator "REZ_Solar_North" has p_nom_max 500
    And generator "REZ_Solar_North" has overnight_cost 1200000
    And generator "REZ_Solar_North" has discount_rate 0.07
    And generator "REZ_Solar_North" has lifetime 25
    And the network is saved as "inputs/two_regions.nc"
    When I run the pypsa investments translation against "inputs/two_regions.nc" writing "outputs/portfolio.json"
    Then the file "outputs/portfolio.json" parses as a portfolio where the "ExistingDevices" of "SupplyTechnology" "REZ_Solar_North" has "existing_devices" set to ["OldSolar_North"]
    And the file "outputs/portfolio.json" parses as a portfolio where the "RetirementPotential" of "SupplyTechnology" "REZ_Solar_North" has "eligible_generators" set to ["OldSolar_North"]

  Scenario: a supply technology takes only the devices of its own PyPSA class
    A Generator and a StorageUnit may share a name, and only a StorageUnit becomes a
    HydroDispatch, so a supply technology's fleet is the generators of its carrier alone.
    Given a PyPSA network
    And the network has 3 snapshots at 60 minute intervals
    And the network contains bus "North_bus" carrier "AC" v_nom 380.0 location "North"
    And the network contains storage unit "Shared" on "North_bus" carrier "hydro" p_nom 200 max_hours 6.0 efficiency_dispatch 0.9 inflow 10.0 20.0 30.0
    And the network contains generator "OldSolar" on "North_bus" carrier "solar" p_nom 200
    And the network contains generator "Shared" on "North_bus" carrier "solar" p_nom 0 p_nom_extendable True
    And generator "Shared" has p_nom_max 500
    And generator "Shared" has overnight_cost 1200000
    And generator "Shared" has discount_rate 0.07
    And generator "Shared" has lifetime 25
    And the network is saved as "inputs/shared_hydro_name.nc"
    When I run the pypsa investments translation against "inputs/shared_hydro_name.nc" writing "outputs/portfolio.json"
    Then the file "outputs/system.json" parses as JSON with 1 component of type "HydroDispatch"
    And the file "outputs/portfolio.json" parses as a portfolio where the "ExistingDevices" of "SupplyTechnology" "Shared" has "existing_devices" set to ["OldSolar"]
    And the file "outputs/portfolio.json" parses as a portfolio where the "RetirementPotential" of "SupplyTechnology" "Shared" has "eligible_generators" set to ["OldSolar"]

  Scenario: a constraint whose limit is not a finite number is left out, and the run completes
    A cap states a number of million tonnes, and neither NaN nor Infinity is one.
    Given a PyPSA network
    And the network contains bus "North_bus" carrier "AC" v_nom 380.0 location "North"
    And the network contains generator "GasPlant" on "North_bus" carrier "CCGT" p_nom 500
    And the network contains generator "REZ_Solar" on "North_bus" carrier "solar" p_nom 0 p_nom_extendable True
    And generator "REZ_Solar" has p_nom_max 500
    And generator "REZ_Solar" has overnight_cost 1200000
    And generator "REZ_Solar" has discount_rate 0.07
    And generator "REZ_Solar" has lifetime 25
    And the network is saved as "inputs/non_finite_cap.nc"
    And a file "inputs/extensions.json" containing the lines:
      | line |
      | {"constraint": [{"name": "CarbonBudget", "sense": "<=", "limits": [{"period": "year", "value": Infinity}], "members": [{"name": "GasPlant", "member_class": "Generator"}, {"name": "REZ_Solar", "member_class": "Generator"}]}]} |
    When I run the pypsa investments translation with sidecar "inputs/extensions.json" against "inputs/non_finite_cap.nc" writing "outputs/portfolio.json"
    Then the file "outputs/portfolio.json" parses as JSON with 0 components of type "CarbonCaps"
    And the log contains "1 constraint(s) state a right-hand side that is not a finite number"

  Scenario: a constraint the expansion plan need not meet is left out, and the run completes
    A source says whether its expansion plan has to meet a constraint. A cap written from a
    constraint the plan need not meet would bound a problem the model leaves free.
    Given a PyPSA network
    And the network contains bus "North_bus" carrier "AC" v_nom 380.0 location "North"
    And the network contains generator "GasPlant" on "North_bus" carrier "CCGT" p_nom 500
    And the network contains generator "REZ_Solar" on "North_bus" carrier "solar" p_nom 0 p_nom_extendable True
    And generator "REZ_Solar" has p_nom_max 500
    And generator "REZ_Solar" has overnight_cost 1200000
    And generator "REZ_Solar" has discount_rate 0.07
    And generator "REZ_Solar" has lifetime 25
    And the network is saved as "inputs/dispatch_only_cap.nc"
    And a file "inputs/extensions.json" containing the lines:
      | line |
      | {"constraint": [{"name": "DispatchOnlyBudget", "sense": "<=", "limits": [{"period": "year", "value": 20.0}], "applies_to_expansion_plan": false, "members": [{"name": "GasPlant", "member_class": "Generator"}, {"name": "REZ_Solar", "member_class": "Generator"}]}]} |
    When I run the pypsa investments translation with sidecar "inputs/extensions.json" against "inputs/dispatch_only_cap.nc" writing "outputs/portfolio.json"
    Then the file "outputs/portfolio.json" parses as JSON with 0 components of type "CarbonCaps"
    And the log contains "1 constraint(s) the expansion plan does not have to meet"

  Scenario: a constraint over another class of one name does not reach the whole model
    Two classes may hold an object of one name, so a member counts against the model only
    where its class matches as well.
    Given a PyPSA network
    And the network contains bus "North_bus" carrier "AC" v_nom 380.0 location "North"
    And the network contains generator "Shared" on "North_bus" carrier "CCGT" p_nom 500
    And the network contains generator "REZ_Solar" on "North_bus" carrier "solar" p_nom 0 p_nom_extendable True
    And generator "REZ_Solar" has p_nom_max 500
    And generator "REZ_Solar" has overnight_cost 1200000
    And generator "REZ_Solar" has discount_rate 0.07
    And generator "REZ_Solar" has lifetime 25
    And the network is saved as "inputs/name_clash_cap.nc"
    And a file "inputs/extensions.json" containing the lines:
      | line |
      | {"constraint": [{"name": "NodeFlowLimit", "sense": "<=", "limits": [{"period": "year", "value": 20.0}], "members": [{"name": "Shared", "member_class": "Bus"}, {"name": "REZ_Solar", "member_class": "Generator"}]}]} |
    When I run the pypsa investments translation with sidecar "inputs/extensions.json" against "inputs/name_clash_cap.nc" writing "outputs/portfolio.json"
    Then the file "outputs/portfolio.json" parses as JSON with 0 components of type "CarbonCaps"
    And the log contains "1 constraint(s) weight a named subset of the model rather than all of it"

  Scenario: a generator neither document holds leaves a whole-model constraint whole
    A cap holds every component of the portfolio and the base system it expands. A generator
    an earlier hop of this translator added to shed load reaches neither, so a constraint
    naming everything both documents hold still covers the model.
    Given a PyPSA network
    And the network contains bus "North_bus" carrier "AC" v_nom 380.0 location "North"
    And the network contains load "North_load" on "North_bus" with static p_set 100
    And the network contains generator "GasPlant" on "North_bus" carrier "CCGT" p_nom 500
    And the network contains generator "North_bus_load_shedding" on "North_bus" carrier "load_shedding" p_nom 100 marginal_cost 9000
    And the network contains generator "REZ_Solar" on "North_bus" carrier "solar" p_nom 0 p_nom_extendable True
    And generator "REZ_Solar" has p_nom_max 500
    And generator "REZ_Solar" has overnight_cost 1200000
    And generator "REZ_Solar" has discount_rate 0.07
    And generator "REZ_Solar" has lifetime 25
    And the network is saved as "inputs/whole_model_cap.nc"
    And a file "inputs/extensions.json" containing the lines:
      | line |
      | {"bus": [{"name": "North_bus", "value_of_lost_load": 9000.0}], "constraint": [{"name": "CarbonBudget", "sense": "<=", "limits": [{"period": "year", "value": 20.0}], "members": [{"name": "GasPlant", "member_class": "Generator"}, {"name": "REZ_Solar", "member_class": "Generator"}]}]} |
    When I run the pypsa investments translation with sidecar "inputs/extensions.json" against "inputs/whole_model_cap.nc" writing "outputs/portfolio.json"
    Then the file "outputs/system.json" parses as JSON with 1 components of type "ThermalStandard"
    And the file "outputs/portfolio.json" parses as JSON with 1 component of type "CarbonCaps"
    And the file "outputs/portfolio.json" parses as JSON with component "CarbonCaps" named "CarbonBudget" having "max_mtons" set to 20.0
