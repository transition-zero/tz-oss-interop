@slow @fork_unsafe
Feature: pypsa_to_sienna_map_components translates PyPSA Load rows to Sienna PowerLoad
  The convert step creates a row in the loads destination table for each PyPSA load.
  The numeric step fills active_power, max_active_power, and base_power from the static
  p_set topology value or the peak of the hourly p_set time series.

  Scenario: load with hourly p_set time series translates to PowerLoad with max_active_power as the peak of the time series
    Given a PyPSA network
    And the network has 2 snapshots at 60 minute intervals
    And the network contains bus "bus_AL" carrier "AC" v_nom 380.0
    And the network contains load "load_AL" on "bus_AL" with p_set 100.0 200.0
    And the network is saved as "inputs/load_ts.nc"
    When I run translate against "inputs/load_ts.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with 1 components of type "PowerLoad"
    And the file "outputs/system.json" parses as JSON with component "PowerLoad" named "load_AL" having "name" set to "load_AL"
    And the file "outputs/system.json" parses as JSON with component "PowerLoad" named "load_AL" having "available" set to true
    And the file "outputs/system.json" parses as JSON with component "PowerLoad" named "load_AL" having "active_power" set to 100.0
    And the file "outputs/system.json" parses as JSON with component "PowerLoad" named "load_AL" having "max_active_power" set to 200.0
    And the file "outputs/system.json" parses as JSON with component "PowerLoad" named "load_AL" having "base_power" set to 200.0
    And the file "outputs/system.json" parses as JSON with component "PowerLoad" named "load_AL" having "conformity" set to "UNDEFINED"
    And the file "decisions.md" contains "| `pypsa.Load.load_AL` | `sienna.PowerLoad.load_AL.type` = PowerLoad | PyPSA Load -> PowerLoad |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    And the file "decisions.md" contains "| `pypsa.Load.load_AL.p_set` = 0.0 MW | `sienna.PowerLoad.load_AL.active_power` = 100.0 MW | p_set static value; time-varying p_set uses first timestep |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    And the file "decisions.md" contains "| `pypsa.Load.load_AL.loads_t.p_set` | `sienna.PowerLoad.load_AL.max_active_power` = 200.0 MW | peak of n.loads_t.p_set time series |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    And the file "outputs/system_time_series_storage.h5" exists
    And the h5 file "outputs/system_time_series_storage.h5" has a time series for component "PowerLoad" named "load_AL" attribute "max_active_power" with length 2
    And the h5 file "outputs/system_time_series_storage.h5" has a time series for component "PowerLoad" named "load_AL" attribute "max_active_power" with values 0.5 1.0

  Scenario: load with static p_set and no time series uses p_set for both active and max active power
    Given a PyPSA network
    And the network contains bus "bus_AL" carrier "AC" v_nom 380.0
    And the network contains load "load_AL" on "bus_AL" with static p_set 150.0
    And the network is saved as "inputs/load_static.nc"
    When I run translate against "inputs/load_static.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "PowerLoad" named "load_AL" having "active_power" set to 150.0
    And the file "outputs/system.json" parses as JSON with component "PowerLoad" named "load_AL" having "max_active_power" set to 150.0
    And the file "outputs/system.json" parses as JSON with component "PowerLoad" named "load_AL" having "base_power" set to 150.0
    And the file "decisions.md" contains "|  | `sienna.PowerLoad.load_AL.available` = True |  | PyPSA Load has no active input field; always True | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    And the file "outputs/system.json" parses as JSON with component "PowerLoad" named "load_AL" having "bus" set to 1
    And the file "decisions.md" contains "| `pypsa.Load.load_AL.p_set` = 150.0 MW | `sienna.PowerLoad.load_AL.active_power` = 150.0 MW | direct |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    And the file "decisions.md" contains "| `pypsa.Load.load_AL.p_set` = 150.0 MW | `sienna.PowerLoad.load_AL.max_active_power` = 150.0 MW | n.loads.p_set static value; no time series present |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    And the file "decisions.md" contains "|  | `sienna.PowerLoad.load_AL.conformity` = UNDEFINED |  | PyPSA Load has no conformity concept | pypsa-to-sienna | pypsa_to_sienna_map_components |"

  Scenario: load with zero p_set falls back to 0.1 MVA base_power
    Given a PyPSA network
    And the network contains bus "bus_AL" carrier "AC" v_nom 380.0
    And the network contains load "load_AL" on "bus_AL" with static p_set 0.0
    And the network is saved as "inputs/load_zero.nc"
    When I run translate against "inputs/load_zero.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "PowerLoad" named "load_AL" having "active_power" set to 0.0
    And the file "outputs/system.json" parses as JSON with component "PowerLoad" named "load_AL" having "max_active_power" set to 0.0
    And the file "outputs/system.json" parses as JSON with component "PowerLoad" named "load_AL" having "base_power" set to 0.1
    And the file "decisions.md" contains "| `pypsa.Load.load_AL.p_set` = 0.0 MW | `sienna.PowerLoad.load_AL.active_power` = 0.0 MW | direct |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    And the file "decisions.md" contains "| `sienna.PowerLoad.load_AL.max_active_power` = 0.0 MW | `sienna.PowerLoad.load_AL.base_power` = 0.1 MVA | max(max_active_power, 0.1) MVA |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"

  Scenario: load produces an extension record with sign, carrier and type
    Given a PyPSA network
    And the network contains bus "bus_AL" carrier "AC" v_nom 380.0
    And the network contains load "load_AL" on "bus_AL" with static p_set 100.0
    And the network is saved as "inputs/load_ext.nc"
    When I run translate against "inputs/load_ext.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/extensions.json" exists
    And the file "outputs/extensions.json" parses as JSON load extension record for "load_AL" having "sign" set to -1
    And the file "outputs/extensions.json" parses as JSON load extension record for "load_AL" having "carrier" set to ""
    And the file "outputs/extensions.json" parses as JSON load extension record for "load_AL" having "type" set to ""

  Scenario Outline: time series resolution is derived from the snapshot interval
    Given a PyPSA network
    And the network has 2 snapshots at <minutes> minute intervals
    And the network contains bus "bus_AL" carrier "AC" v_nom 380.0
    And the network contains load "load_AL" on "bus_AL" with p_set 100.0 200.0
    And the network is saved as "inputs/network.nc"
    When I run translate against "inputs/network.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON where TimeSeriesAssociation for component "PowerLoad" owner id 1 has resolution "<resolution>"

    Examples:
      | minutes | resolution |
      | 15      | PT15M      |
      | 30      | PT30M      |
      | 60      | PT1H       |
      | 1440    | P1D        |
      | 10      | PT600S     |

  Scenario: a load whose bus prices a shortfall becomes the load type a solve may cut
    PyPSA has no field for the price of a shortfall, so it reaches this leg on the bus's
    sidecar record. The load carrying it becomes an InterruptiblePowerLoad, whose
    operation_cost is a LoadCost curve priced at that many dollars per MWh.
    Given a PyPSA network
    And the network contains bus "bus_AL" carrier "AC" v_nom 380.0
    And the network contains load "load_AL" on "bus_AL" with static p_set 100.0
    And the network is saved as "inputs/load_voll.nc"
    And a file "inputs/extensions.json" containing the lines:
      | line |
      | {"bus": [{"name": "bus_AL", "value_of_lost_load": 9000.0}]} |
    When I run translate against "inputs/load_voll.nc" with sidecar "inputs/extensions.json" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with 1 components of type "InterruptiblePowerLoad"
    And the file "outputs/system.json" parses as JSON with 0 components of type "PowerLoad"
    And the file "outputs/system.json" parses as JSON with component "InterruptiblePowerLoad" named "load_AL" having "operation_cost.variable.value_curve.function_data.proportional_term" set to 9000.0
    And the file "decisions.md" contains "| `pypsa.Bus.bus_AL.value_of_lost_load` = 9000.0 $/MWh | `sienna.InterruptiblePowerLoad.load_AL.operation_cost.variable.value_curve.function_data.proportional_term` = 9000.0 $/MWh | the value of lost load its bus carries becomes the LoadCost variable cost curve, so cutting this load costs that much per MWh |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"
