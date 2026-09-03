@slow @fork_unsafe
Feature: pypsa_to_sienna_map_components translates PyPSA Generator rows to Sienna RenewableNonDispatch
  PyPSA Generators with the solar-rooftop carrier become RenewableNonDispatch (must-take):
  the system always accepts whatever is available. RenewableNonDispatch has no operation_cost
  field, no active_power_limits, and no reactive_power_limits; its ceiling is the rating
  (static p_max_pu) or a max_active_power time series. A non-zero PyPSA marginal_cost has no
  Sienna home and is recorded as NOT_MAPPED (information lost).

  Scenario: solar-rooftop generator translates to RenewableNonDispatch with no cost field
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network contains generator "rooftop_1" on "bus_1" carrier "solar-rooftop" p_nom 50.0
    And the network is saved as "inputs/rooftop.nc"
    When I run translate against "inputs/rooftop.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with 1 components of type "RenewableNonDispatch"
    And the file "outputs/system.json" parses as JSON with component "RenewableNonDispatch" named "rooftop_1" having "prime_mover_type" set to "PVe"
    And the file "outputs/system.json" parses as JSON with component "RenewableNonDispatch" named "rooftop_1" having "base_power" set to 50.0
    And the file "outputs/system.json" parses as JSON with component "RenewableNonDispatch" named "rooftop_1" having "active_power" set to 50.0
    And the file "outputs/system.json" parses as JSON with component "RenewableNonDispatch" named "rooftop_1" having "reactive_power" set to 0.0
    And the file "outputs/system.json" parses as JSON with component "RenewableNonDispatch" named "rooftop_1" having "rating" set to 1.0
    And the file "outputs/system.json" parses as JSON with component "RenewableNonDispatch" named "rooftop_1" having "power_factor" set to 1.0
    And the file "outputs/system.json" parses as JSON with component "RenewableNonDispatch" named "rooftop_1" without field "operation_cost"
    And the file "outputs/system.json" parses as JSON with component "RenewableNonDispatch" named "rooftop_1" without field "reactive_power_limits"
    And the file "decisions.md" contains "| `pypsa.Generator.rooftop_1.carrier` = solar-rooftop | `sienna.RenewableNonDispatch.rooftop_1.type` = RenewableNonDispatch | renewable carrier -> RenewableNonDispatch |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    And the file "decisions.md" contains "| `pypsa.Generator.rooftop_1.carrier` = solar-rooftop | `sienna.RenewableNonDispatch.rooftop_1.prime_mover_type` = PVe | carrier -> PrimeMovers via user defined mapping |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    And the file "decisions.md" contains "| `pypsa.Generator.rooftop_1.p_nom` = 50.0 MW | `sienna.RenewableNonDispatch.rooftop_1.active_power` = 50.0 MW | effective_p_nom * p_max_pu (must-take initial dispatch = peak available) |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"

  Scenario: solar-rooftop with zero marginal_cost records no information-loss flag
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network contains generator "rooftop_1" on "bus_1" carrier "solar-rooftop" p_nom 50.0 marginal_cost 0.0
    And the network is saved as "inputs/rooftop_free.nc"
    When I run translate against "inputs/rooftop_free.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with 1 components of type "RenewableNonDispatch"
    And the file "decisions.md" does not contain "marginal_cost dropped"

  Scenario: non-zero marginal_cost on solar-rooftop is recorded as lost
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network contains generator "rooftop_1" on "bus_1" carrier "solar-rooftop" p_nom 50.0 marginal_cost 12.0
    And the network is saved as "inputs/rooftop_cost.nc"
    When I run translate against "inputs/rooftop_cost.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "RenewableNonDispatch" named "rooftop_1" without field "operation_cost"
    And the file "decisions.md" contains "| `pypsa.Generator.rooftop_1.marginal_cost` = 12.0 |  |  | RenewableNonDispatch has no operation_cost field; non-zero marginal_cost dropped (information lost) | pypsa-to-sienna | pypsa_to_sienna_map_components |"

  Scenario: active_power and rating use the peak available p_max_pu
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network contains generator "rooftop_1" on "bus_1" carrier "solar-rooftop" p_nom 50.0 p_max_pu 0.8
    And the network is saved as "inputs/rooftop_derate.nc"
    When I run translate against "inputs/rooftop_derate.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "RenewableNonDispatch" named "rooftop_1" having "active_power" set to 40.0
    And the file "outputs/system.json" parses as JSON with component "RenewableNonDispatch" named "rooftop_1" having "rating" set to 0.8

  Scenario: time-varying p_max_pu produces a max_active_power time series stored unchanged
    Given a PyPSA network
    And the network has 3 snapshots at 60 minute intervals
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network contains generator "rooftop_1" on "bus_1" carrier "solar-rooftop" p_nom 50.0 p_max_pu_series 0.7 0.4 0.6
    And the network is saved as "inputs/rooftop_ts.nc"
    When I run translate against "inputs/rooftop_ts.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system_time_series_storage.h5" exists
    And the h5 file "outputs/system_time_series_storage.h5" has a time series for component "RenewableNonDispatch" named "rooftop_1" attribute "max_active_power" with length 3
    And the h5 file "outputs/system_time_series_storage.h5" has a time series for component "RenewableNonDispatch" named "rooftop_1" attribute "max_active_power" with values 0.7 0.4 0.6
    And the file "outputs/system.json" parses as JSON where array "time_series_associations" has length 1
    And the file "outputs/system.json" parses as JSON where TimeSeriesAssociation for component "RenewableNonDispatch" owner id 1 has resolution "PT1H"
