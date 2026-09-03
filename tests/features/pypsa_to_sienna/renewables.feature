@slow @fork_unsafe
Feature: pypsa_to_sienna_map_components translates PyPSA Generator rows to Sienna RenewableDispatch
  Each PyPSA Generator whose carrier is mapped to RenewableDispatch in the user carrier mapping
  becomes a RenewableDispatch row. RenewableDispatch is curtailable: it has no active_power_limits,
  ramp_limits, must_run, or fuel_type. Its ceiling comes from rating (static p_max_pu) or,
  when p_max_pu is time-varying, a max_active_power time series stored in per-unit shape
  (values unchanged, not peak-normalised). operation_cost is a RenewableGenerationCost.

  Scenario: solar generator translates to RenewableDispatch with renewable cost and rating
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network contains generator "solar_1" on "bus_1" carrier "solar" p_nom 200.0 marginal_cost 0.0
    And the network is saved as "inputs/solar.nc"
    When I run translate against "inputs/solar.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with 1 components of type "RenewableDispatch"
    And the file "outputs/system.json" parses as JSON with component "RenewableDispatch" named "solar_1" having "prime_mover_type" set to "PVe"
    And the file "outputs/system.json" parses as JSON with component "RenewableDispatch" named "solar_1" having "base_power" set to 200.0
    And the file "outputs/system.json" parses as JSON with component "RenewableDispatch" named "solar_1" having "active_power" set to 0.0
    And the file "outputs/system.json" parses as JSON with component "RenewableDispatch" named "solar_1" having "reactive_power" set to 0.0
    And the file "outputs/system.json" parses as JSON with component "RenewableDispatch" named "solar_1" having "rating" set to 1.0
    And the file "outputs/system.json" parses as JSON with component "RenewableDispatch" named "solar_1" having "power_factor" set to 1.0
    And the file "outputs/system.json" parses as JSON with component "RenewableDispatch" named "solar_1" having "reactive_power_limits" set to null
    And the file "outputs/system.json" parses as JSON with component "RenewableDispatch" named "solar_1" having "operation_cost.cost_type" set to "RENEWABLE"
    And the file "outputs/system.json" parses as JSON with component "RenewableDispatch" named "solar_1" having "operation_cost.variable.value_curve.function_data.proportional_term" set to 0.0
    # VALUE_DERIVED decisions
    And the file "decisions.md" contains "| `pypsa.Generator.solar_1.name` = solar_1 | `sienna.RenewableDispatch.solar_1.name` = solar_1 | direct |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    And the file "decisions.md" contains "| `pypsa.Generator.solar_1.bus` = bus_1 | `sienna.RenewableDispatch.solar_1.bus_name` = bus_1 | direct |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    And the file "decisions.md" contains "| `pypsa.Generator.solar_1.carrier` = solar | `sienna.RenewableDispatch.solar_1.type` = RenewableDispatch | renewable carrier -> RenewableDispatch |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    And the file "decisions.md" contains "| `pypsa.Generator.solar_1.carrier` = solar | `sienna.RenewableDispatch.solar_1.prime_mover_type` = PVe | carrier -> PrimeMovers via user defined mapping |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    And the file "decisions.md" contains "| `pypsa.Generator.solar_1.p_nom` = 200.0 MW | `sienna.RenewableDispatch.solar_1.base_power` = 200.0 MW | p_nom_opt when p_nom_extendable else p_nom |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    And the file "decisions.md" contains "| `pypsa.Generator.solar_1.p_max_pu` = 1.0 | `sienna.RenewableDispatch.solar_1.rating` = 1.0 | p_max_pu (per-unit nameplate rating; typically 1.0) |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    # TRANSLATOR_DEFAULT_APPLIED decisions
    And the file "decisions.md" contains "|  | `sienna.RenewableDispatch.solar_1.id` = 1 |  | assigned by 1-based row position in renewable generators DataFrame | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    And the file "decisions.md" contains "|  | `sienna.RenewableDispatch.solar_1.available` = True |  | PyPSA Generator has no active field; defaulted to True | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    And the file "decisions.md" contains "|  | `sienna.RenewableDispatch.solar_1.reactive_power` = 0.0 |  | PyPSA networks rarely model reactive power for generators | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    And the file "decisions.md" contains "|  | `sienna.RenewableDispatch.solar_1.power_factor` = 1.0 |  | PyPSA generator schema has no scalar power factor; defaulted to 1.0 | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    And the file "decisions.md" contains "|  | `sienna.RenewableDispatch.solar_1.reactive_power_limits` |  | PyPSA does not model reactive power limits for generators in v1 | pypsa-to-sienna | pypsa_to_sienna_map_components |"

  Scenario: active_power derives from p_min_pu (committed minimum dispatch)
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network contains generator "wind_1" on "bus_1" carrier "onwind" p_nom 300.0 p_min_pu 0.1
    And the network is saved as "inputs/wind_pmin.nc"
    When I run translate against "inputs/wind_pmin.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "RenewableDispatch" named "wind_1" having "active_power" set to 30.0
    And the file "decisions.md" contains "| `pypsa.Generator.wind_1.p_nom` = 300.0 MW | `sienna.RenewableDispatch.wind_1.active_power` = 30.0 MW | effective_p_nom * p_min_pu (initial dispatch = min operating point) |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"

  Scenario: static p_max_pu below 1.0 derates rating
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network contains generator "solar_1" on "bus_1" carrier "solar" p_nom 150.0 p_max_pu 0.8
    And the network is saved as "inputs/solar_derate.nc"
    When I run translate against "inputs/solar_derate.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "RenewableDispatch" named "solar_1" having "rating" set to 0.8

  Scenario: marginal cost becomes a single-segment renewable CostCurve
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network contains generator "wind_1" on "bus_1" carrier "onwind" p_nom 100.0 marginal_cost 5.0
    And the network is saved as "inputs/wind_cost.nc"
    When I run translate against "inputs/wind_cost.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "RenewableDispatch" named "wind_1" having "operation_cost.variable.value_curve.function_data.proportional_term" set to 5.0
    And the file "decisions.md" contains "| `pypsa.Generator.wind_1.marginal_cost` = 5.0 | `sienna.RenewableDispatch.wind_1.operation_cost.variable.value_curve.function_data.proportional_term` = 5.0 | flat marginal_cost ($/MWh) -> single-segment linear CostCurve |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"

  Scenario Outline: <carrier> maps to RenewableDispatch with prime_mover_type <prime_mover>
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network contains generator "gen_1" on "bus_1" carrier "<carrier>" p_nom 100.0
    And the network is saved as "inputs/<carrier>_renewable.nc"
    When I run translate against "inputs/<carrier>_renewable.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with 1 components of type "RenewableDispatch"
    And the file "outputs/system.json" parses as JSON with component "RenewableDispatch" named "gen_1" having "prime_mover_type" set to "<prime_mover>"

    Examples:
      | carrier       | prime_mover |
      | solar         | PVe         |
      | solar-utility | PVe         |
      | onwind        | WT          |
      | on-wind       | WT          |
      | offwind-ac    | WS          |
      | offwind-dc    | WS          |
      | off-wind      | WS          |

  Scenario: time-varying p_max_pu produces a max_active_power time series stored unchanged
    Given a PyPSA network
    And the network has 3 snapshots at 60 minute intervals
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network contains generator "solar_1" on "bus_1" carrier "solar" p_nom 100.0 p_max_pu_series 0.9 0.85 0.92
    And the network is saved as "inputs/solar_ts.nc"
    When I run translate against "inputs/solar_ts.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "RenewableDispatch" named "solar_1" having "rating" set to 1.0
    And the file "outputs/system_time_series_storage.h5" exists
    And the h5 file "outputs/system_time_series_storage.h5" has a time series for component "RenewableDispatch" named "solar_1" attribute "max_active_power" with length 3
    And the h5 file "outputs/system_time_series_storage.h5" has a time series for component "RenewableDispatch" named "solar_1" attribute "max_active_power" with values 0.9 0.85 0.92
    And the file "outputs/system.json" parses as JSON where array "time_series_associations" has length 1
    And the file "outputs/system.json" parses as JSON where TimeSeriesAssociation for component "RenewableDispatch" owner id 1 has resolution "PT1H"

  Scenario: flat time-varying p_max_pu is skipped (no time series emitted)
    Given a PyPSA network
    And the network has 3 snapshots at 60 minute intervals
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network contains generator "solar_1" on "bus_1" carrier "solar" p_nom 100.0 p_max_pu_series 0.5 0.5 0.5
    And the network is saved as "inputs/solar_flat.nc"
    When I run translate against "inputs/solar_flat.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON where array "time_series_associations" has length 0

  Scenario: renewable p_nom_extendable True records the flag in extensions
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network contains generator "solar_1" on "bus_1" carrier "solar" p_nom 200.0 p_nom_extendable True
    And the network is saved as "inputs/solar_extendable.nc"
    When I run translate against "inputs/solar_extendable.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/extensions.json" parses as JSON generator extension record for "solar_1" having "p_nom_extendable" set to true
    And the file "outputs/extensions.json" parses as JSON generator extension record for "solar_1" having "carrier" set to "solar"
