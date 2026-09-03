@slow @fork_unsafe
Feature: PLEXOS to PyPSA Pipeline translates batteries, pumped storage, and hydro to StorageUnit rows
  A PLEXOS Battery, a pumped-storage plant (a turbine Generator linked to a head and a
  tail Storage), and a reservoir-hydro Generator each collapse into one PyPSA StorageUnit.
  Scalar fields are mapped per the translation doc. A reservoir refills at its Natural
  Inflow, as a value or as a profile, where the model states that inflow in a unit that
  converts to megawatts.

  Scenario: a Battery becomes a PyPSA StorageUnit with carrier battery
    Given a Plexos model
    And the model contains region "West"
    And the model contains node "node_a" in region "West"
    And the model contains battery "bat_1" on node "node_a" with max_power 100 capacity 200 charge_efficiency 81 initial_soc 50
    And the model is saved as "inputs/battery.xml"
    When I run translate against "inputs/battery.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 1 storage unit
    And the PyPSA network "outputs/network.nc" storage unit "bat_1" has bus "node_a"
    And the PyPSA network "outputs/network.nc" storage unit "bat_1" has carrier "battery"
    And the PyPSA network "outputs/network.nc" storage unit "bat_1" attribute "p_nom" is 100.0
    And the PyPSA network "outputs/network.nc" storage unit "bat_1" attribute "max_hours" is 2.0
    And the PyPSA network "outputs/network.nc" storage unit "bat_1" attribute "p_max_pu" is 1.0
    And the PyPSA network "outputs/network.nc" storage unit "bat_1" attribute "p_min_pu" is -1.0
    And the PyPSA network "outputs/network.nc" storage unit "bat_1" attribute "efficiency_store" is 0.9
    And the PyPSA network "outputs/network.nc" storage unit "bat_1" attribute "efficiency_dispatch" is 0.9
    And the PyPSA network "outputs/network.nc" storage unit "bat_1" attribute "state_of_charge_initial" is 100.0
    And the PyPSA network "outputs/network.nc" storage unit "bat_1" attribute "marginal_cost" is 0.0
    And the PyPSA network "outputs/network.nc" storage unit "bat_1" is not cyclic
    And the file "decisions.md" contains "| `plexos.Battery.bat_1.Max Power` = 100.0 MW | `pypsa.StorageUnit.bat_1.p_nom` = 100.0 MW | direct |  | plexos-to-pypsa | plexos_to_pypsa_map_storage_units |"
    And the file "decisions.md" contains "| `plexos.Battery.bat_1.Charge Efficiency` = 81.0 % | `pypsa.StorageUnit.bat_1.efficiency_store` = 0.9 | sqrt(round-trip / 100), split symmetrically |  | plexos-to-pypsa | plexos_to_pypsa_map_storage_units |"

  Scenario: a pumped-storage plant becomes a cyclic PyPSA PHS StorageUnit
    Given a Plexos model
    And the model contains region "West"
    And the model contains node "node_b" in region "West"
    And the model contains pumped storage "phs_1" on node "node_b" with max_capacity 500 pump_efficiency 64 head "phs_head" tail "phs_tail" max_volume 3000 initial_volume 1500
    And the model is saved as "inputs/phs.xml"
    When I run translate against "inputs/phs.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 1 storage unit
    And the PyPSA network "outputs/network.nc" storage unit "phs_1" has bus "node_b"
    And the PyPSA network "outputs/network.nc" storage unit "phs_1" has carrier "PHS"
    And the PyPSA network "outputs/network.nc" storage unit "phs_1" attribute "p_nom" is 500.0
    And the PyPSA network "outputs/network.nc" storage unit "phs_1" attribute "max_hours" is 6.0
    And the PyPSA network "outputs/network.nc" storage unit "phs_1" attribute "p_min_pu" is -1.0
    And the PyPSA network "outputs/network.nc" storage unit "phs_1" attribute "efficiency_store" is 0.8
    And the PyPSA network "outputs/network.nc" storage unit "phs_1" attribute "efficiency_dispatch" is 0.8
    And the PyPSA network "outputs/network.nc" storage unit "phs_1" attribute "state_of_charge_initial" is 1500.0
    And the PyPSA network "outputs/network.nc" storage unit "phs_1" is cyclic
    And the file "decisions.md" contains "| `plexos.Storage.phs_head.Max Volume` = 3000.0 MWh | `pypsa.StorageUnit.phs_1.max_hours` = 6.0 h | head Storage.Max Volume / p_nom |  | plexos-to-pypsa | plexos_to_pypsa_map_storage_units |"

  Scenario: a reservoir whose volume names no unit is read as the model wrote it
    A published export can leave the unit of a volume blank. The values are still the ones
    the modeller meant, so the translation uses them.
    Given a Plexos model
    And the model contains region "West"
    And the model contains node "node_u" in region "West"
    And the model contains pumped storage "phs_plain" on node "node_u" with max_capacity 500 pump_efficiency 64 head "plain_head" tail "plain_tail" max_volume 3000 initial_volume 1500
    And the model is saved as "inputs/plain.xml"
    When I run translate against "inputs/plain.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" storage unit "phs_plain" attribute "max_hours" is 6.0
    And the PyPSA network "outputs/network.nc" storage unit "phs_plain" attribute "state_of_charge_initial" is 1500.0

  Scenario: a reservoir whose volume unit is the PLEXOS dimensionless mark is read as written
    PLEXOS writes "-" for a property that has no unit. That is not a unit, so the
    translation uses the value.
    Given a Plexos model
    And the model contains region "West"
    And the model contains node "node_d" in region "West"
    And the model states "Max Volume" in "-"
    And the model states "Initial Volume" in "-"
    And the model contains pumped storage "phs_dash" on node "node_d" with max_capacity 500 pump_efficiency 64 head "dash_head" tail "dash_tail" max_volume 3000 initial_volume 1500
    And the model is saved as "inputs/dash.xml"
    When I run translate against "inputs/dash.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" storage unit "phs_dash" attribute "max_hours" is 6.0
    And the PyPSA network "outputs/network.nc" storage unit "phs_dash" attribute "state_of_charge_initial" is 1500.0

  Scenario: a reservoir volume stated in GWh converts into MWh
    A published export states a reservoir in GWh. That is energy, so the translation
    converts it rather than reading 1.54 GWh as 1.54 MWh.
    Given a Plexos model
    And the model contains region "West"
    And the model contains node "node_g" in region "West"
    And the model states "Max Volume" in "GWh"
    And the model states "Initial Volume" in "GWh"
    And the model contains pumped storage "phs_gwh" on node "node_g" with max_capacity 500 pump_efficiency 64 head "gwh_head" tail "gwh_tail" max_volume 3 initial_volume 1.5
    And the model is saved as "inputs/gwh.xml"
    When I run translate against "inputs/gwh.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" storage unit "phs_gwh" attribute "max_hours" is 6.0
    And the PyPSA network "outputs/network.nc" storage unit "phs_gwh" attribute "state_of_charge_initial" is 1500.0

  Scenario: a reservoir measured in water, not energy, keeps the PyPSA default rather than a wrong number
    PLEXOS measures a reservoir in whatever suits the model. A Max Volume of 3000 cubic
    metres per day is not 3000 MWh, and writing it as if it were would give this plant six
    hours of storage it does not have, so the volume is left out and the decision says why.
    Given a Plexos model
    And the model contains region "West"
    And the model contains node "node_w" in region "West"
    And the model states "Max Volume" in "CMD"
    And the model states "Initial Volume" in "CMD"
    And the model contains pumped storage "phs_water" on node "node_w" with max_capacity 500 pump_efficiency 64 head "water_head" tail "water_tail" max_volume 3000 initial_volume 1500
    And the model is saved as "inputs/water.xml"
    When I run translate against "inputs/water.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" storage unit "phs_water" attribute "max_hours" is 1.0
    And the PyPSA network "outputs/network.nc" storage unit "phs_water" attribute "state_of_charge_initial" is 0.0
    And the file "decisions.md" contains "names a volume unit that is not megawatt-hours"

  Scenario: a reservoir stating its Natural Inflow in MW refills at that rate
    A reservoir that receives no water can only discharge what it pumps. Where the model
    states the inflow as power, the StorageUnit carries it.
    Given a Plexos model
    And the model contains region "West"
    And the model contains node "node_i" in region "West"
    And the model states "Natural Inflow" in "MW"
    And the model contains pumped storage "phs_inflow" on node "node_i" with max_capacity 500 pump_efficiency 64 head "inflow_head" tail "inflow_tail" max_volume 3000 initial_volume 1500
    And storage "inflow_head" has property "Natural Inflow" 120
    And the model is saved as "inputs/inflow.xml"
    When I run translate against "inputs/inflow.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" storage unit "phs_inflow" attribute "inflow" is 120.0
    And the file "decisions.md" contains "| `plexos.Storage.inflow_head.Natural Inflow` = 120.0 MW | `pypsa.StorageUnit.phs_inflow.inflow` = 120.0 MW | head Storage.Natural Inflow |  | plexos-to-pypsa | plexos_to_pypsa_map_storage_units |"

  Scenario: a Natural Inflow stated in GW converts into MW
    Given a Plexos model
    And the model contains region "West"
    And the model contains node "node_gw" in region "West"
    And the model states "Natural Inflow" in "GW"
    And the model contains pumped storage "phs_gw" on node "node_gw" with max_capacity 500 pump_efficiency 64 head "gw_head" tail "gw_tail" max_volume 3000 initial_volume 1500
    And storage "gw_head" has property "Natural Inflow" 0.12
    And the model is saved as "inputs/inflow_gw.xml"
    When I run translate against "inputs/inflow_gw.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" storage unit "phs_gw" attribute "inflow" is 120.0

  Scenario: an inflow measured in water, not power, keeps the PyPSA default rather than a wrong number
    PLEXOS measures an inflow in whatever suits the model. A Natural Inflow of 120 cumec is
    a flow of water, and 120 MW of power is a different quantity. To convert one into the
    other needs the head of the reservoir and the efficiency of the turbine, which this
    mapping does not read. Thus the inflow is left out and the decision says why.
    Given a Plexos model
    And the model contains region "West"
    And the model contains node "node_cu" in region "West"
    And the model states "Natural Inflow" in "cumec"
    And the model contains pumped storage "phs_cumec" on node "node_cu" with max_capacity 500 pump_efficiency 64 head "cumec_head" tail "cumec_tail" max_volume 3000 initial_volume 1500
    And storage "cumec_head" has property "Natural Inflow" 120
    And the model is saved as "inputs/inflow_cumec.xml"
    When I run translate against "inputs/inflow_cumec.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" storage unit "phs_cumec" attribute "inflow" is 0.0
    And the file "decisions.md" contains "names an inflow unit that is not megawatts"

  Scenario: a Natural Inflow that reads a data file becomes an inflow time series
    A real reservoir refills at a rate that changes through the year, so the inflow is a
    profile rather than one number.
    Given a Plexos model
    And the model contains region "West"
    And the model contains node "node_p" in region "West"
    And the model contains data file "inflow_trace" at "csv/inflow.csv" with hourly values "10, 20, 30, 40"
    And the model states "Natural Inflow" in "MW"
    And the model contains pumped storage "phs_profile" on node "node_p" with max_capacity 500 pump_efficiency 64 head "profile_head" tail "profile_tail" max_volume 3000 initial_volume 1500
    And storage "profile_head" has property "Natural Inflow" from data file "inflow_trace"
    And the model is saved as "inputs/inflow_profile.xml"
    When I run translate against "inputs/inflow_profile.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" storage unit "phs_profile" has an inflow time series 10 20 30 40
    And the file "decisions.md" contains "states its Natural Inflow as a time series, so the static column stays at the default"
    And the file "decisions.md" does not contain "the head Storage states no Natural Inflow"

  Scenario: a Battery has no reservoir, so its inflow takes the PyPSA default
    Given a Plexos model
    And the model contains region "West"
    And the model contains node "node_bi" in region "West"
    And the model contains battery "bat_inflow" on node "node_bi" with max_power 100 capacity 200 charge_efficiency 81 initial_soc 50
    And the model is saved as "inputs/battery_inflow.xml"
    When I run translate against "inputs/battery_inflow.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" storage unit "bat_inflow" attribute "inflow" is 0.0
    And the file "decisions.md" contains "`pypsa.StorageUnit.bat_inflow.inflow` = 0.0 MW"

  Scenario: a reservoir starting above its Max Volume is clamped, and the decision says so
    Given a Plexos model
    And the model contains region "West"
    And the model contains node "node_e" in region "West"
    And the model contains pumped storage "phs_full" on node "node_e" with max_capacity 500 pump_efficiency 64 head "phs_full_head" tail "phs_full_tail" max_volume 3000 initial_volume 4000
    And the model is saved as "inputs/phs_full.xml"
    When I run translate against "inputs/phs_full.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" storage unit "phs_full" attribute "state_of_charge_initial" is 3000.0
    And the file "decisions.md" contains "`pypsa.StorageUnit.phs_full.state_of_charge_initial` = 3000.0 MWh | head Storage.Initial Volume, clamped to 0..p_nom * max_hours |"

  Scenario: a reservoir-hydro Generator becomes a PyPSA hydro StorageUnit that only generates
    Given a Plexos model
    And the model contains region "West"
    And the model contains node "node_c" in region "West"
    And the model contains reservoir hydro "hydro_1" on node "node_c" with max_capacity 200 head "hydro_res" max_volume 800 initial_volume 400
    And the model is saved as "inputs/hydro.xml"
    When I run translate against "inputs/hydro.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 1 storage unit
    And the PyPSA network "outputs/network.nc" storage unit "hydro_1" has bus "node_c"
    And the PyPSA network "outputs/network.nc" storage unit "hydro_1" has carrier "hydro"
    And the PyPSA network "outputs/network.nc" storage unit "hydro_1" attribute "p_nom" is 200.0
    And the PyPSA network "outputs/network.nc" storage unit "hydro_1" attribute "max_hours" is 4.0
    And the PyPSA network "outputs/network.nc" storage unit "hydro_1" attribute "p_min_pu" is 0.0
    And the PyPSA network "outputs/network.nc" storage unit "hydro_1" attribute "efficiency_store" is 1.0
    And the PyPSA network "outputs/network.nc" storage unit "hydro_1" attribute "state_of_charge_initial" is 400.0
    And the PyPSA network "outputs/network.nc" storage unit "hydro_1" is not cyclic
    And the file "decisions.md" contains "| `plexos.Generator.hydro_1.Max Capacity` = 200.0 MW<br>`plexos.Generator.hydro_1.Units` = 1.0 | `pypsa.StorageUnit.hydro_1.p_nom` = 200.0 MW | Max Capacity * Units |  | plexos-to-pypsa | plexos_to_pypsa_map_storage_units |"
    And the file "decisions.md" contains "|  | `pypsa.StorageUnit.hydro_1.p_min_pu` = 0.0 |  | conventional hydro generates but does not pump | plexos-to-pypsa | plexos_to_pypsa_map_storage_units |"

  Scenario: a Storage with no turbine is skipped, not mapped
    Given a Plexos model
    And the model contains region "West"
    And the model contains node "node_a" in region "West"
    And the model contains battery "bat_1" on node "node_a" with max_power 100 capacity 200 charge_efficiency 81 initial_soc 50
    And the model contains storage "orphan" with max_volume 3000 initial_volume 1500
    And the model is saved as "inputs/orphan.xml"
    When I run translate against "inputs/orphan.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 1 storage unit
    And the file "decisions.md" contains "| `plexos.Storage.orphan` |  |  | no Generator names this Storage as a head or tail, so it cannot dispatch | plexos-to-pypsa | plexos_to_pypsa_map_storage_units |"

  Scenario: a turbine becomes a storage unit only, never also a generator
    Given a Plexos model
    And the model contains region "West"
    And the model contains node "node_k" in region "West"
    And the model contains pumped storage "phs_both" on node "node_k" with max_capacity 500 pump_efficiency 64 head "phs_both_head" tail "phs_both_tail" max_volume 3000 initial_volume 1500
    And the model contains reservoir hydro "hydro_both" on node "node_k" with max_capacity 200 head "hydro_both_res" max_volume 800 initial_volume 400
    And the model contains generator "ThermalPlant" with "node=node_k, fuel=Coal, Max Capacity=300, Heat Rate=9"
    And the model is saved as "inputs/both.xml"
    When I run translate against "inputs/both.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 2 storage units
    And the PyPSA network "outputs/network.nc" has no generator "phs_both"
    And the PyPSA network "outputs/network.nc" has no generator "hydro_both"
    And the PyPSA generator "ThermalPlant" in "outputs/network.nc" has bus "node_k"

  Scenario: head and tail reservoirs are found by membership, whatever they are named
    Given a Plexos model
    And the model contains region "West"
    And the model contains node "node_j" in region "West"
    And the model contains pumped storage "alpha" on node "node_j" with max_capacity 500 pump_efficiency 64 head "zzz_unrelated" tail "qqq_other" max_volume 3000 initial_volume 1500
    And the model is saved as "inputs/unrelated_names.xml"
    When I run translate against "inputs/unrelated_names.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 1 storage unit
    And the PyPSA network "outputs/network.nc" storage unit "alpha" has carrier "PHS"
    And the PyPSA network "outputs/network.nc" storage unit "alpha" attribute "max_hours" is 6.0
    And the PyPSA network "outputs/network.nc" storage unit "alpha" attribute "state_of_charge_initial" is 1500.0
    And the file "decisions.md" contains "`plexos.Storage.zzz_unrelated.Max Volume` = 3000.0 MWh"

  Scenario: a Battery stating Duration instead of Capacity still gets its initial level
    Given a Plexos model
    And the model contains region "West"
    And the model contains node "node_f" in region "West"
    And the model contains battery "bat_duration" on node "node_f"
    And battery "bat_duration" has property "Max Power" 100
    And battery "bat_duration" has property "Duration" 2
    And battery "bat_duration" has property "Initial SoC" 50
    And the model is saved as "inputs/bat_duration.xml"
    When I run translate against "inputs/bat_duration.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" storage unit "bat_duration" attribute "max_hours" is 2.0
    And the PyPSA network "outputs/network.nc" storage unit "bat_duration" attribute "state_of_charge_initial" is 100.0
    And the file "decisions.md" contains "`pypsa.StorageUnit.bat_duration.state_of_charge_initial` = 100.0 MWh | Initial SoC / 100 * energy capacity |"

  Scenario: a mothballed turbine has no rated power and is skipped
    Given a Plexos model
    And the model contains region "West"
    And the model contains node "node_g" in region "West"
    And the model contains pumped storage "phs_off" on node "node_g" with max_capacity 500 pump_efficiency 64 head "phs_off_head" tail "phs_off_tail" max_volume 3000 initial_volume 1500
    And generator "phs_off" has property "Units" 0
    And the model is saved as "inputs/phs_off.xml"
    When I run translate against "inputs/phs_off.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 0 storage units
    And the file "decisions.md" contains "| `plexos.Generator.phs_off` |  |  | rated power works out to 0.0 MW, so this unit cannot dispatch | plexos-to-pypsa | plexos_to_pypsa_map_storage_units |"

  Scenario: a Battery stating no Max Power is skipped rather than stopping the translation
    Given a Plexos model
    And the model contains region "West"
    And the model contains node "node_p" in region "West"
    And the model contains battery "powerless" on node "node_p"
    And battery "powerless" has property "Capacity" 400
    And the model is saved as "inputs/powerless.xml"
    When I run translate against "inputs/powerless.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 0 storage units
    And the log contains "dropping Battery 'powerless'"
    And the file "decisions.md" contains "the object states no rated power, which the StorageUnit mapping cannot default"

  Scenario: a turbine with a tail but no head is skipped, naming what it lacks
    Given a Plexos model
    And the model contains region "West"
    And the model contains node "node_h" in region "West"
    And the model contains turbine "headless" on node "node_h" with max_capacity 400 tail "headless_tail"
    And the model is saved as "inputs/headless.xml"
    When I run translate against "inputs/headless.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 0 storage units
    And the file "decisions.md" contains "this Generator has a Tail Storage but no Head Storage and no Pump Efficiency, so it has no reservoir to draw from"

  Scenario: a reservoir with no Max Volume is clamped to the capacity PyPSA enforces
    Given a Plexos model
    And the model contains region "West"
    And the model contains node "node_i" in region "West"
    And the model contains turbine "unbounded" on node "node_i" with max_capacity 500 head "unbounded_head"
    And storage "unbounded_head" has property "Initial Volume" 5000
    And the model is saved as "inputs/unbounded.xml"
    When I run translate against "inputs/unbounded.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" storage unit "unbounded" attribute "max_hours" is 1.0
    And the PyPSA network "outputs/network.nc" storage unit "unbounded" attribute "state_of_charge_initial" is 500.0
    And the file "decisions.md" contains "head Storage.Initial Volume, clamped to 0..p_nom * max_hours"

  Scenario: a pumped-storage plant with a VO&M charge prices its marginal cost
    Given a Plexos model
    And the model contains region "West"
    And the model contains node "node_d" in region "West"
    And the model contains pumped storage "phs_vom" on node "node_d" with max_capacity 500 pump_efficiency 64 head "phs_vom_head" tail "phs_vom_tail" max_volume 3000 initial_volume 1500
    And generator "phs_vom" has property "VO&M Charge" 3.5
    And the model is saved as "inputs/phs_vom.xml"
    When I run translate against "inputs/phs_vom.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" storage unit "phs_vom" attribute "marginal_cost" is 3.5
    And the file "decisions.md" contains "| `plexos.Generator.phs_vom.VO&M Charge` = 3.5 $/MWh | `pypsa.StorageUnit.phs_vom.marginal_cost` = 3.5 $/MWh | VO&M Charge (no fuel, so VO&M only) |  | plexos-to-pypsa | plexos_to_pypsa_map_storage_units |"

  Scenario: a battery's units-out trace derates how much it can discharge
    Given a Plexos model
    And the model contains variable "BatteryOutage" profiling "profiles/battery_out.csv" with hourly values "0, 1, 2"
    And the model contains battery "OutageBattery" on node "Grid_Node" power 100 capacity 400 units 2 units out of variable "BatteryOutage"
    And the model is saved as "inputs/battery_outage.xml"
    When I run translate against "inputs/battery_outage.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA storage unit "OutageBattery" in "outputs/network.nc" has p_max_pu at hour 1 equal to 1.0
    And the PyPSA storage unit "OutageBattery" in "outputs/network.nc" has p_max_pu at hour 2 equal to 0.5
    And the PyPSA storage unit "OutageBattery" in "outputs/network.nc" has p_max_pu at hour 3 equal to 0.0

  Scenario: a battery with no stated initial charge cycles rather than starting empty
    Given a Plexos model
    And the model contains battery "NoStartBattery" on node "Grid_Node" power 100 capacity 400 charge efficiency 90 and no initial state of charge
    And the model is saved as "inputs/no_start.xml"
    When I run translate against "inputs/no_start.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" storage unit "NoStartBattery" is cyclic

  Scenario: End Effects Method decides whether a battery's level cycles
    Given a Plexos model
    And the model contains battery "RecycleBattery" on node "Grid_Node" power 100 capacity 400 initial soc 25 end effects 2
    And the model contains battery "FreeBattery" on node "Grid_Node" power 100 capacity 400 initial soc 25 end effects 1
    And the model is saved as "inputs/end_effects.xml"
    When I run translate against "inputs/end_effects.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" storage unit "RecycleBattery" is cyclic
    And the PyPSA network "outputs/network.nc" storage unit "FreeBattery" is not cyclic

  Scenario: a Battery on no node is skipped, not translated without a bus
    Given a Plexos model
    And the model contains region "West"
    And the model contains node "node_l" in region "West"
    And the model contains battery "bat_busless" on no node
    And battery "bat_busless" has property "Max Power" 100
    And the model is saved as "inputs/bat_busless.xml"
    When I run translate against "inputs/bat_busless.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 0 storage units
    And the file "decisions.md" contains "| `plexos.Battery.bat_busless.Nodes` |  |  | this object is on no Node, so it has no bus to connect to | plexos-to-pypsa | plexos_to_pypsa_map_storage_units |"

  Scenario: a pumping Generator on no node is skipped, not translated without a bus
    Given a Plexos model
    And the model contains region "West"
    And the model contains node "node_m" in region "West"
    And the model contains generator "ghost" with "Max Capacity=100, Pump Efficiency=70"
    And the model is saved as "inputs/ghost.xml"
    When I run translate against "inputs/ghost.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 0 storage units
    And the PyPSA network "outputs/network.nc" has no generator "ghost"
    And the file "decisions.md" contains "| `plexos.Generator.ghost.Nodes` |  |  | this object is on no Node, so it has no bus to connect to | plexos-to-pypsa | plexos_to_pypsa_map_storage_units |"

  Scenario: a turbine whose head reservoir states no volumes falls back to the PyPSA defaults
    Given a Plexos model
    And the model contains region "West"
    And the model contains node "node_n" in region "West"
    And the model contains turbine "bare" on node "node_n" with max_capacity 500 head "bare_head"
    And the model is saved as "inputs/bare.xml"
    When I run translate against "inputs/bare.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 1 storage unit
    And the PyPSA network "outputs/network.nc" storage unit "bare" attribute "max_hours" is 1.0
    And the PyPSA network "outputs/network.nc" storage unit "bare" attribute "state_of_charge_initial" is 0.0
    And the file "decisions.md" contains "PLEXOS states no reservoir capacity; max_hours uses the PyPSA default"

  Scenario: a Storage stating no volumes and feeding no turbine is still skipped
    Given a Plexos model
    And the model contains region "West"
    And the model contains node "node_o" in region "West"
    And the model contains battery "bat_o" on node "node_o" with max_power 100 capacity 200 charge_efficiency 81 initial_soc 50
    And the model contains storage "silent" stating no volumes
    And the model is saved as "inputs/silent.xml"
    When I run translate against "inputs/silent.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 1 storage unit
    And the file "decisions.md" contains "| `plexos.Storage.silent` |  |  | no Generator names this Storage as a head or tail, so it cannot dispatch | plexos-to-pypsa | plexos_to_pypsa_map_storage_units |"

  Scenario: a turbine stating no properties at all is skipped, not silently dropped
    Given a Plexos model
    And the model contains region "West"
    And the model contains node "node_p" in region "West"
    And the model contains turbine "mute" on node "node_p" with head "mute_head"
    And the model is saved as "inputs/mute.xml"
    When I run translate against "inputs/mute.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 0 storage units
    And the PyPSA network "outputs/network.nc" has no generator "mute"
    And the file "decisions.md" contains "| `plexos.Generator.mute.Max Capacity` |  |  | PLEXOS states no Max Capacity, so the object states no rated power, which the StorageUnit mapping cannot default | plexos-to-pypsa | plexos_to_pypsa_map_storage_units |"

  Scenario: a Battery stating a Capacity but no Max Power is skipped, naming what it lacks
    Given a Plexos model
    And the model contains region "West"
    And the model contains node "node_q" in region "West"
    And the model contains battery "bat_nopower" on node "node_q"
    And battery "bat_nopower" has property "Capacity" 200
    And the model is saved as "inputs/bat_nopower.xml"
    When I run translate against "inputs/bat_nopower.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 0 storage units
    And the file "decisions.md" contains "| `plexos.Battery.bat_nopower.Max Power` |  |  | PLEXOS states no Max Power, so the object states no rated power, which the StorageUnit mapping cannot default | plexos-to-pypsa | plexos_to_pypsa_map_storage_units |"

  Scenario: a turbine whose Max Capacity comes from a data file is skipped, naming the data file
    Given a Plexos model
    And the model contains region "West"
    And the model contains node "node_r" in region "West"
    And the model contains data file "Capacity" at "profiles/capacity.csv" with hourly values "100, 100, 100"
    And the model contains generator "filecap" with "node=node_r, Max Capacity=file:Capacity, Pump Efficiency=70"
    And the model is saved as "inputs/filecap.xml"
    When I run translate against "inputs/filecap.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 0 storage units
    And the file "decisions.md" contains "| `plexos.Generator.filecap.Max Capacity` = data file MW |  |  | Max Capacity comes from a data file rather than a value, so this unit has no rated power to size it | plexos-to-pypsa | plexos_to_pypsa_map_storage_units |"

  Scenario: a turbine with negative Units is skipped, not given a negative rated power
    Given a Plexos model
    And the model contains region "West"
    And the model contains node "node_s" in region "West"
    And the model contains pumped storage "phs_neg" on node "node_s" with max_capacity 500 pump_efficiency 64 head "phs_neg_head" tail "phs_neg_tail" max_volume 3000 initial_volume 1500
    And generator "phs_neg" has property "Units" -1
    And the model is saved as "inputs/phs_neg.xml"
    When I run translate against "inputs/phs_neg.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 0 storage units
    And the file "decisions.md" contains "| `plexos.Generator.phs_neg` |  |  | rated power works out to -500.0 MW, so this unit cannot dispatch | plexos-to-pypsa | plexos_to_pypsa_map_storage_units |"

  Scenario: a Battery with no Charge Efficiency is modelled lossless
    Given a Plexos model
    And the model contains region "West"
    And the model contains node "node_v" in region "West"
    And the model contains battery "bat_lossless" on node "node_v"
    And battery "bat_lossless" has property "Max Power" 100
    And battery "bat_lossless" has property "Capacity" 200
    And the model is saved as "inputs/bat_lossless.xml"
    When I run translate against "inputs/bat_lossless.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" storage unit "bat_lossless" attribute "efficiency_store" is 1.0
    And the PyPSA network "outputs/network.nc" storage unit "bat_lossless" attribute "efficiency_dispatch" is 1.0
    And the file "decisions.md" contains "|  | `pypsa.StorageUnit.bat_lossless.efficiency_store` = 1.0 |  | PLEXOS states no round-trip efficiency; storage is modelled lossless | plexos-to-pypsa | plexos_to_pypsa_map_storage_units |"
    And the file "decisions.md" contains "|  | `pypsa.StorageUnit.bat_lossless.efficiency_dispatch` = 1.0 |  | PLEXOS states no round-trip efficiency; storage is modelled lossless | plexos-to-pypsa | plexos_to_pypsa_map_storage_units |"

  Scenario: a Battery stating neither Capacity nor Duration takes the PyPSA max_hours default
    Given a Plexos model
    And the model contains region "West"
    And the model contains node "node_w" in region "West"
    And the model contains battery "bat_sizeless" on node "node_w"
    And battery "bat_sizeless" has property "Max Power" 100
    And the model is saved as "inputs/bat_sizeless.xml"
    When I run translate against "inputs/bat_sizeless.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" storage unit "bat_sizeless" attribute "max_hours" is 1.0
    And the PyPSA network "outputs/network.nc" storage unit "bat_sizeless" attribute "state_of_charge_initial" is 0.0
    And the file "decisions.md" contains "PLEXOS states no reservoir capacity; max_hours uses the PyPSA default"

  Scenario: a turbine with both reservoirs and no Pump Efficiency is still pumped storage
    Given a Plexos model
    And the model contains region "West"
    And the model contains node "node_x" in region "West"
    And the model contains turbine "phs_nopump" on node "node_x" with max_capacity 500 head "phs_nopump_head" tail "phs_nopump_tail"
    And storage "phs_nopump_head" has property "Max Volume" 3000
    And the model is saved as "inputs/phs_nopump.xml"
    When I run translate against "inputs/phs_nopump.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" storage unit "phs_nopump" has carrier "PHS"
    And the PyPSA network "outputs/network.nc" storage unit "phs_nopump" attribute "p_min_pu" is -1.0
    And the PyPSA network "outputs/network.nc" storage unit "phs_nopump" attribute "efficiency_store" is 1.0
    And the PyPSA network "outputs/network.nc" storage unit "phs_nopump" is cyclic

  Scenario: a turbine sizes itself on its head reservoir, never its tail
    Given a Plexos model
    And the model contains region "West"
    And the model contains node "node_y" in region "West"
    And the model contains pumped storage "phs_sized" on node "node_y" with max_capacity 500 pump_efficiency 64 head "phs_sized_head" tail "phs_sized_tail" max_volume 3000 initial_volume 1500
    And storage "phs_sized_tail" has property "Max Volume" 500
    And storage "phs_sized_tail" has property "Initial Volume" 250
    And the model is saved as "inputs/phs_sized.xml"
    When I run translate against "inputs/phs_sized.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" storage unit "phs_sized" attribute "max_hours" is 6.0
    And the PyPSA network "outputs/network.nc" storage unit "phs_sized" attribute "state_of_charge_initial" is 1500.0
    And the file "decisions.md" contains "| `plexos.Storage.phs_sized_head.Max Volume` = 3000.0 MWh | `pypsa.StorageUnit.phs_sized.max_hours` = 6.0 h | head Storage.Max Volume / p_nom |  | plexos-to-pypsa | plexos_to_pypsa_map_storage_units |"
    And the file "decisions.md" contains "| `plexos.Storage.phs_sized_tail.Max Volume` = 500.0 MWh |  |  | the tail reservoir is absorbed into the head's storage unit, so its Max Volume is dropped | plexos-to-pypsa | plexos_to_pypsa_map_storage_units |"

  Scenario: the storage properties PyPSA has no home for are recorded as not mapped
    Given a Plexos model
    And the model contains region "West"
    And the model contains node "node_u" in region "West"
    And the model contains battery "bat_dropped" on node "node_u" with max_power 100 capacity 200 charge_efficiency 81 initial_soc 50
    And battery "bat_dropped" has property "Min SoC" 10
    And battery "bat_dropped" has property "Discharge Efficiency" 95
    And the model contains pumped storage "phs_dropped" on node "node_u" with max_capacity 500 pump_efficiency 64 head "phs_dropped_head" tail "phs_dropped_tail" max_volume 3000 initial_volume 1500
    And storage "phs_dropped_head" has property "Natural Inflow" 40
    And storage "phs_dropped_tail" has property "Max Volume" 2500
    And the model is saved as "inputs/dropped.xml"
    When I run translate against "inputs/dropped.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 2 storage units
    And the file "decisions.md" contains "| `plexos.Battery.bat_dropped.Min SoC` = 10.0 % |  |  | PyPSA treats the full energy capacity as usable, so Min SoC is dropped | plexos-to-pypsa | plexos_to_pypsa_map_storage_units |"
    And the file "decisions.md" contains "| `plexos.Battery.bat_dropped.Discharge Efficiency` = 95.0 % |  |  | PyPSA takes one round-trip efficiency, split evenly across charge and discharge, so Discharge Efficiency is dropped | plexos-to-pypsa | plexos_to_pypsa_map_storage_units |"
    And the file "decisions.md" contains "| `plexos.Storage.phs_dropped_tail.Max Volume` = 2500.0 MWh |  |  | the tail reservoir is absorbed into the head's storage unit, so its Max Volume is dropped | plexos-to-pypsa | plexos_to_pypsa_map_storage_units |"
    # A head reservoir's inflow reaches the storage unit, so it is not among the dropped.
    And the file "decisions.md" contains "| `plexos.Storage.phs_dropped_head.Natural Inflow` = 40.0 MW | `pypsa.StorageUnit.phs_dropped.inflow` = 40.0 MW | head Storage.Natural Inflow |  | plexos-to-pypsa | plexos_to_pypsa_map_storage_units |"
    And the file "decisions.md" does not contain "no turbine draws from this reservoir"

  Scenario: a reservoir no turbine draws from has its Natural Inflow recorded as dropped
    Given a Plexos model
    And the model contains region "West"
    And the model contains node "node_o" in region "West"
    And the model contains storage "orphan_head" stating no volumes
    And storage "orphan_head" has property "Natural Inflow" 40
    And the model is saved as "inputs/orphan_inflow.xml"
    When I run translate against "inputs/orphan_inflow.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the file "decisions.md" contains "| `plexos.Storage.orphan_head.Natural Inflow` = 40.0 MW |  |  | no turbine draws from this reservoir, so its Natural Inflow is dropped | plexos-to-pypsa | plexos_to_pypsa_map_storage_units |"
