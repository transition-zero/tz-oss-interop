@slow @fork_unsafe
Feature: pypsa_to_sienna_map_components translates PyPSA Generator rows to Sienna ThermalStandard
  Each PyPSA Generator whose carrier is in the user-supplied user_mappings.yaml becomes a
  ThermalStandard row. Generators with carriers absent from the file cause a fail-fast error.

  Scenario: CCGT generator translates to ThermalStandard with correct cost and capacity
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network contains generator "ccgt_1" on "bus_1" carrier "CCGT" p_nom 500.0 p_min_pu 0.2 marginal_cost 30.0
    And the network is saved as "inputs/ccgt.nc"
    And a user mappings file with all standard carriers
    When I run translate against "inputs/ccgt.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with 1 components of type "ThermalStandard"
    And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ccgt_1" having "fuel_type" set to "NATURAL_GAS"
    And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ccgt_1" having "prime_mover_type" set to "CC"
    And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ccgt_1" having "base_power" set to 500.0
    And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ccgt_1" having "active_power" set to 100.0
    And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ccgt_1" having "active_power_limits.min" set to 100.0
    And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ccgt_1" having "active_power_limits.max" set to 500.0
    And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ccgt_1" having "operation_cost.cost_type" set to "THERMAL"
    And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ccgt_1" having "operation_cost.fixed" set to 0.0
    And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ccgt_1" having "operation_cost.start_up" set to 0.0
    And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ccgt_1" having "operation_cost.shut_down" set to 0.0
    And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ccgt_1" having "operation_cost.variable.value_curve.function_data.proportional_term" set to 30.0
    # VALUE_DERIVED decisions
    And the file "decisions.md" contains "| `pypsa.Generator.ccgt_1.name` = ccgt_1 | `sienna.ThermalStandard.ccgt_1.name` = ccgt_1 | direct |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    And the file "decisions.md" contains "| `pypsa.Generator.ccgt_1.bus` = bus_1 | `sienna.ThermalStandard.ccgt_1.bus_name` = bus_1 | direct |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    And the file "decisions.md" contains "| `pypsa.Generator.ccgt_1.p_nom` = 500.0 MW | `sienna.ThermalStandard.ccgt_1.base_power` = 500.0 MW | p_nom_opt when p_nom_extendable else p_nom |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    And the file "decisions.md" contains "| `pypsa.Generator.ccgt_1.p_nom` = 500.0 MW | `sienna.ThermalStandard.ccgt_1.active_power` = 100.0 MW | effective_p_nom * p_min_pu (initial dispatch = min operating point) |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    And the file "decisions.md" contains "| `pypsa.Generator.ccgt_1.p_max_pu` = 1.0 | `sienna.ThermalStandard.ccgt_1.rating` = 1.0 | p_max_pu (per-unit nameplate rating; typically 1.0) |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    And the file "decisions.md" contains "| `pypsa.Generator.ccgt_1.p_nom` = 500.0 MW | `sienna.ThermalStandard.ccgt_1.active_power_limits` = {'min': 100.0, 'max': 500.0} MW | min=effective_p_nom*p_min_pu, max=effective_p_nom*p_max_pu (static) |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    And the file "decisions.md" contains "| `pypsa.Generator.ccgt_1.marginal_cost` = 30.0 | `sienna.ThermalStandard.ccgt_1.operation_cost.variable.value_curve.function_data.proportional_term` = 30.0 | flat marginal_cost ($/MWh) -> single-segment linear CostCurve |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    # USER_CONFIG_DEFAULT_APPLIED decisions (carrier classification according to user defined mapping)
    And the file "decisions.md" contains "| `pypsa.Generator.ccgt_1.carrier` = CCGT | `sienna.ThermalStandard.ccgt_1.type` = ThermalStandard |  | according to user defined mapping | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    And the file "decisions.md" contains "| `pypsa.Generator.ccgt_1.carrier` = CCGT | `sienna.ThermalStandard.ccgt_1.fuel_type` = NATURAL_GAS |  | according to user defined mapping | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    And the file "decisions.md" contains "| `pypsa.Generator.ccgt_1.carrier` = CCGT | `sienna.ThermalStandard.ccgt_1.prime_mover_type` = CC |  | according to user defined mapping | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    # TRANSLATOR_DEFAULT_APPLIED decisions
    And the file "decisions.md" contains "|  | `sienna.ThermalStandard.ccgt_1.id` = 1 |  | assigned by 1-based row position in thermal generators DataFrame | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    And the file "decisions.md" contains "|  | `sienna.ThermalStandard.ccgt_1.available` = True |  | PyPSA Generator has no active field; defaulted to True | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    And the file "decisions.md" contains "|  | `sienna.ThermalStandard.ccgt_1.status` = True |  | PyPSA has no separate initial on/off state; defaulted to True | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    And the file "decisions.md" contains "|  | `sienna.ThermalStandard.ccgt_1.reactive_power` = 0.0 |  | PyPSA networks rarely model reactive power for generators | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    And the file "decisions.md" contains "|  | `sienna.ThermalStandard.ccgt_1.ramp_limits` |  | ramp_limit_up/down absent in PyPSA network; ramp_limits set to null | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    And the file "decisions.md" contains "|  | `sienna.ThermalStandard.ccgt_1.must_run` = False |  | PyPSA Generator has no must_run concept; defaulted to False | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    And the file "decisions.md" contains "|  | `sienna.ThermalStandard.ccgt_1.time_limits` |  | min_up_time and min_down_time both zero; time_limits set to null | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    And the file "decisions.md" contains "| `pypsa.Generator.ccgt_1.up_time_before` = 0.0 | `sienna.ThermalStandard.ccgt_1.time_at_status` = 10000.0 | up_time_before=0; defaulted to 10000.0 (Sienna schema default) |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    # Verify values in output JSON
    And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ccgt_1" having "time_limits" set to null
    And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ccgt_1" having "time_at_status" set to 10000.0

  Scenario: generator with ramp limits produces populated ramp_limits struct
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network contains generator "coal_1" on "bus_1" carrier "coal" p_nom 100.0 ramp_limit_up 0.3 ramp_limit_down 0.2
    And the network is saved as "inputs/ramp.nc"
    And a user mappings file with all standard carriers
    When I run translate against "inputs/ramp.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "coal_1" having "ramp_limits.up" set to 0.5
    And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "coal_1" having "ramp_limits.down" set to 0.3333333333333333
    And the file "decisions.md" contains "| `pypsa.Generator.coal_1.ramp_limit_up` = 0.3 | `sienna.ThermalStandard.coal_1.ramp_limits` = {'up': 0.5, 'down': 0.3333333333333333} | effective_p_nom * ramp_limit / 60 min (pu/snapshot -> MW/min) |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"

  @slow
  Scenario: generator without ramp columns produces null ramp_limits
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network contains generator "ocgt_1" on "bus_1" carrier "OCGT" p_nom 200.0
    And the network is saved as "inputs/no_ramp.nc"
    And a user mappings file with all standard carriers
    When I run translate against "inputs/no_ramp.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ocgt_1" having "ramp_limits" set to null
    And the file "decisions.md" contains "|  | `sienna.ThermalStandard.ocgt_1.ramp_limits` |  | ramp_limit_up/down absent in PyPSA network; ramp_limits set to null | pypsa-to-sienna | pypsa_to_sienna_map_components |"

  Scenario: generator with p_max_pu time series produces time_series_metadata row
    Given a PyPSA network
    And the network has 3 snapshots at 60 minute intervals
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network contains generator "nuclear_1" on "bus_1" carrier "nuclear" p_nom 1000.0 p_max_pu_series 0.9 0.85 0.92
    And the network is saved as "inputs/gen_ts.nc"
    And a user mappings file with all standard carriers
    When I run translate against "inputs/gen_ts.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "nuclear_1" having "active_power_limits.max" set to 920.0
    And the file "decisions.md" contains "| `pypsa.Generator.nuclear_1.p_nom` = 1000.0 MW | `sienna.ThermalStandard.nuclear_1.active_power_limits` = {'min': 0.0, 'max': 920.0} MW | min=effective_p_nom*p_min_pu, max=effective_p_nom*ts_peak_p_max_pu (time series) |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    And the file "outputs/system_time_series_storage.h5" exists
    And the h5 file "outputs/system_time_series_storage.h5" has a time series for component "ThermalStandard" named "nuclear_1" attribute "max_active_power" with length 3
    And the h5 file "outputs/system_time_series_storage.h5" has a time series for component "ThermalStandard" named "nuclear_1" attribute "max_active_power" with values 0.9782608695652174 0.9239130434782608 1.0
    And the file "outputs/system.json" parses as JSON where TimeSeriesAssociation for component "ThermalStandard" owner id 1 is named "max_active_power"
    And the file "outputs/system.json" parses as JSON where array "time_series_associations" has length 1
    And the file "outputs/system.json" parses as JSON where TimeSeriesAssociation for component "ThermalStandard" owner id 1 has resolution "PT1H"

  Scenario: generator with static p_max_pu below 1.0 produces derated active_power_limits
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network contains generator "coal_1" on "bus_1" carrier "coal" p_nom 500.0 p_max_pu 0.8
    And the network is saved as "inputs/derating.nc"
    And a user mappings file with all standard carriers
    When I run translate against "inputs/derating.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "coal_1" having "active_power_limits.max" set to 400.0
    And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "coal_1" having "active_power_limits.min" set to 0.0
    And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "coal_1" having "rating" set to 0.8
    And the file "decisions.md" contains "min=effective_p_nom*p_min_pu, max=effective_p_nom*p_max_pu (static)"

  Scenario Outline: <carrier> maps to correct fuel_type and prime_mover_type
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network contains generator "gen_1" on "bus_1" carrier "<carrier>" p_nom 100.0
    And the network is saved as "inputs/<carrier>_carrier.nc"
    And a user mappings file with all standard carriers
    When I run translate against "inputs/<carrier>_carrier.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "gen_1" having "fuel_type" set to "<fuel_type>"
    And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "gen_1" having "prime_mover_type" set to "<prime_mover>"

    Examples:
      | carrier    | fuel_type             | prime_mover |
      | nuclear    | NUCLEAR               | ST          |
      | coal       | COAL                  | ST          |
      | lignite    | COAL                  | ST          |
      | CCGT       | NATURAL_GAS           | CC          |
      | OCGT       | NATURAL_GAS           | GT          |
      | gas        | NATURAL_GAS           | CC          |
      | oil        | DISTILLATE_FUEL_OIL   | GT          |
      | geothermal | GEOTHERMAL            | BT          |
      | biomass    | OTHER_BIOMASS_SOLIDS  | ST          |
      | bioenergy  | OTHER_BIOMASS_SOLIDS  | ST          |
      | waste      | MUNICIPAL_WASTE       | ST          |
      | hydrogen   | OTHER_GAS             | FC          |

  Scenario: a generator whose carrier the mappings file omits is left out, and the rest translate
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network contains generator "wind_1" on "bus_1" carrier "onwind" p_nom 300.0
    And the network contains generator "gas_1" on "bus_1" carrier "CCGT" p_nom 400.0
    And the network is saved as "inputs/wind.nc"
    And a user mappings file covering only carrier "CCGT"
    When I run translate against "inputs/wind.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with 1 component of type "ThermalStandard"
    And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "gas_1" having "active_power_limits.max" set to 400.0
    And the file "decisions.md" contains "`pypsa.Generator.wind_1`"
    And the file "decisions.md" contains "carrier='onwind': the user mappings file names no such carrier"
    And the log contains "1 Generator(s) have a carrier the user mappings file does not name"
    And the log contains "onwind"

  Scenario: generator with committable True produces extension record
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network contains generator "coal_1" on "bus_1" carrier "coal" p_nom 500.0 committable True
    And the network is saved as "inputs/committable.nc"
    And a user mappings file with all standard carriers
    When I run translate against "inputs/committable.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/extensions.json" exists
    And the file "outputs/extensions.json" parses as JSON generator extension record for "coal_1" having "committable" set to true
    And the file "outputs/extensions.json" parses as JSON generator extension record for "coal_1" having "carrier" set to "coal"

  Scenario: generator without committable records committable false in extensions
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network contains generator "nuclear_1" on "bus_1" carrier "nuclear" p_nom 1000.0
    And the network is saved as "inputs/no_committable.nc"
    And a user mappings file with all standard carriers
    When I run translate against "inputs/no_committable.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/extensions.json" parses as JSON generator extension record for "nuclear_1" having "committable" set to false

  Scenario: generator start_up_cost and shut_down_cost populate the operation cost
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network contains generator "coal_1" on "bus_1" carrier "coal" p_nom 500.0 start_up_cost 1500.0 shut_down_cost 700.0
    And the network is saved as "inputs/start_stop.nc"
    And a user mappings file with all standard carriers
    When I run translate against "inputs/start_stop.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "coal_1" having "operation_cost.start_up" set to 1500.0
    And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "coal_1" having "operation_cost.shut_down" set to 700.0
    And the file "decisions.md" contains "| `pypsa.Generator.coal_1.start_up_cost` = 1500.0 | `sienna.ThermalStandard.coal_1.operation_cost.start_up` = 1500.0 | start_up_cost ($) -> operation_cost.start_up |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    And the file "decisions.md" contains "| `pypsa.Generator.coal_1.shut_down_cost` = 700.0 | `sienna.ThermalStandard.coal_1.operation_cost.shut_down` = 700.0 | shut_down_cost ($) -> operation_cost.shut_down |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"

  Scenario: generator with p_nom_extendable True records the flag in extensions
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network contains generator "coal_1" on "bus_1" carrier "coal" p_nom 500.0 p_nom_extendable True
    And the network is saved as "inputs/gen_extendable.nc"
    And a user mappings file with all standard carriers
    When I run translate against "inputs/gen_extendable.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/extensions.json" parses as JSON generator extension record for "coal_1" having "p_nom_extendable" set to true

  Scenario: generator without p_nom_extendable records the flag false in extensions
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network contains generator "nuclear_1" on "bus_1" carrier "nuclear" p_nom 1000.0
    And the network is saved as "inputs/gen_not_extendable.nc"
    And a user mappings file with all standard carriers
    When I run translate against "inputs/gen_not_extendable.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/extensions.json" parses as JSON generator extension record for "nuclear_1" having "p_nom_extendable" set to false
