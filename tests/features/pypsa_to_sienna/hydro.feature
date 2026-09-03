@slow @fork_unsafe
Feature: pypsa_to_sienna_map_components translates PyPSA StorageUnit rows to Sienna HydroDispatch
  Reservoir hydro is a PyPSA StorageUnit (carrier hydro), not a Generator: it has an inflow
  series and a round-trip efficiency. Each such unit becomes a Sienna HydroDispatch dispatched
  under HydroDispatchRunOfRiverBudget, with two time series: max_active_power (flat, from the
  static p_max_pu) as the per-step cap, and hydro_budget (inflow * efficiency_dispatch / p_nom)
  as the horizon energy budget. Only the required HydroDispatch fields are emitted; ramp_limits,
  time_limits, and status have no StorageUnit source and are omitted.

  Scenario: reservoir hydro StorageUnit translates to HydroDispatch with both time series
    Given a PyPSA network
    And the network has 3 snapshots at 60 minute intervals
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network contains storage unit "hydro_1" on "bus_1" carrier "hydro" p_nom 100.0 p_min_pu 0.0 marginal_cost 5.0 efficiency_dispatch 0.9 inflow 10.0 20.0 30.0
    And the network is saved as "inputs/hydro.nc"
    When I run translate against "inputs/hydro.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with 1 components of type "HydroDispatch"
    And the file "outputs/system.json" parses as JSON with component "HydroDispatch" named "hydro_1" having "prime_mover_type" set to "HY"
    And the file "outputs/system.json" parses as JSON with component "HydroDispatch" named "hydro_1" having "base_power" set to 100.0
    And the file "outputs/system.json" parses as JSON with component "HydroDispatch" named "hydro_1" having "active_power" set to 0.0
    And the file "outputs/system.json" parses as JSON with component "HydroDispatch" named "hydro_1" having "reactive_power" set to 0.0
    And the file "outputs/system.json" parses as JSON with component "HydroDispatch" named "hydro_1" having "rating" set to 1.0
    And the file "outputs/system.json" parses as JSON with component "HydroDispatch" named "hydro_1" having "active_power_limits.min" set to 0.0
    And the file "outputs/system.json" parses as JSON with component "HydroDispatch" named "hydro_1" having "active_power_limits.max" set to 100.0
    And the file "outputs/system.json" parses as JSON with component "HydroDispatch" named "hydro_1" having "operation_cost.cost_type" set to "HYDRO_GEN"
    And the file "outputs/system.json" parses as JSON with component "HydroDispatch" named "hydro_1" having "operation_cost.variable.value_curve.function_data.proportional_term" set to 5.0
    And the file "outputs/system.json" parses as JSON with component "HydroDispatch" named "hydro_1" without field "ramp_limits"
    And the file "outputs/system.json" parses as JSON with component "HydroDispatch" named "hydro_1" without field "time_limits"
    And the file "outputs/system.json" parses as JSON with component "HydroDispatch" named "hydro_1" without field "status"
    # Two time series: per-step cap (flat p_max_pu) and horizon energy budget
    And the file "outputs/system_time_series_storage.h5" exists
    And the h5 file "outputs/system_time_series_storage.h5" has a time series for component "HydroDispatch" named "hydro_1" attribute "max_active_power" with length 3
    And the h5 file "outputs/system_time_series_storage.h5" has a time series for component "HydroDispatch" named "hydro_1" attribute "max_active_power" with values 1.0 1.0 1.0
    And the h5 file "outputs/system_time_series_storage.h5" has a time series for component "HydroDispatch" named "hydro_1" attribute "hydro_budget" with length 3
    And the h5 file "outputs/system_time_series_storage.h5" has a time series for component "HydroDispatch" named "hydro_1" attribute "hydro_budget" with values 0.09 0.18 0.27
    And the file "outputs/system.json" parses as JSON where array "time_series_associations" has length 2
    # Decisions
    And the file "decisions.md" contains "| `pypsa.StorageUnit.hydro_1.carrier` = hydro | `sienna.HydroDispatch.hydro_1.type` = HydroDispatch | hydro carrier -> HydroDispatch |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    And the file "decisions.md" contains "| `pypsa.StorageUnit.hydro_1.p_nom` = 100.0 MW | `sienna.HydroDispatch.hydro_1.active_power_limits` = {'min': 0.0, 'max': 100.0} MW | min=effective_p_nom*p_min_pu, max=effective_p_nom*p_max_pu |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    And the file "decisions.md" contains "| `pypsa.StorageUnit.hydro_1.marginal_cost` = 5.0 | `sienna.HydroDispatch.hydro_1.operation_cost.variable.value_curve.function_data.proportional_term` = 5.0 | flat marginal_cost ($/MWh) -> single-segment linear CostCurve |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"

  Scenario: static p_max_pu below 1.0 derates rating, active_power_limits, and the flat cap series
    Given a PyPSA network
    And the network has 3 snapshots at 60 minute intervals
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network contains storage unit "hydro_1" on "bus_1" carrier "hydro" p_nom 50.0 p_min_pu 0.0 p_max_pu 0.8 efficiency_dispatch 1.0 inflow 5.0 5.0 5.0
    And the network is saved as "inputs/hydro_derate.nc"
    When I run translate against "inputs/hydro_derate.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "HydroDispatch" named "hydro_1" having "rating" set to 0.8
    And the file "outputs/system.json" parses as JSON with component "HydroDispatch" named "hydro_1" having "active_power_limits.max" set to 40.0
    And the h5 file "outputs/system_time_series_storage.h5" has a time series for component "HydroDispatch" named "hydro_1" attribute "max_active_power" with values 0.8 0.8 0.8
    And the h5 file "outputs/system_time_series_storage.h5" has a time series for component "HydroDispatch" named "hydro_1" attribute "hydro_budget" with values 0.1 0.1 0.1

  Scenario: a storage unit whose carrier the mappings file omits is left out, and the run completes
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network contains storage unit "batt_1" on "bus_1" carrier "battery" p_nom 20.0
    And the network is saved as "inputs/batt.nc"
    And a user mappings file covering only carrier "CCGT"
    When I run translate against "inputs/batt.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as valid JSON
    And the file "decisions.md" contains "`pypsa.StorageUnit.batt_1`"
    And the file "decisions.md" contains "carrier='battery': the user mappings file names no such carrier"
    And the log contains "1 StorageUnit(s) have a carrier the user mappings file does not name"

  Scenario: a hydro unit with no inflow at all is left out, and the run completes
    A HydroDispatch is dispatched against an energy budget built from its inflow. A unit with
    no inflow has no budget, so it would run at full output every hour on water nobody
    stated.
    Given a PyPSA network
    And the network has 3 snapshots at 60 minute intervals
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network contains storage unit "dry_1" on "bus_1" carrier "hydro" p_nom 50.0
    And the network is saved as "inputs/dry.nc"
    When I run translate against "inputs/dry.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as valid JSON
    And the file "outputs/system.json" parses as JSON with 0 components of type "HydroDispatch"
    And the file "decisions.md" contains "`pypsa.StorageUnit.dry_1`"
    And the file "decisions.md" contains "no inflow time series, so it has no energy budget"
    And the log contains "1 hydro StorageUnit(s) state no inflow"

  Scenario: a hydro unit with no inflow beside one with inflow is the only one left out
    Given a PyPSA network
    And the network has 3 snapshots at 60 minute intervals
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network contains storage unit "wet_1" on "bus_1" carrier "hydro" p_nom 50.0 efficiency_dispatch 1.0 inflow 5.0 5.0 5.0
    And the network contains storage unit "dry_1" on "bus_1" carrier "hydro" p_nom 50.0
    And the network is saved as "inputs/mixed.nc"
    When I run translate against "inputs/mixed.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with 1 component of type "HydroDispatch"
    And the file "outputs/system.json" parses as JSON with component "HydroDispatch" named "wet_1" having "base_power" set to 50.0
