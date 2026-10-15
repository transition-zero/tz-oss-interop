@slow @fork_unsafe
Feature: Sienna to PyPSA Pipeline translates ACBus rows to PyPSA Bus
  The Sienna source parses a SiennaSchemas system (a JSON object mapping each type name
  to a list of flat objects with integer ids and integer references), the map step inverts
  the per-component field mappings into a PyPSA bus table, and the sink writes a PyPSA
  NetCDF network. base_voltage becomes v_nom, the ACBus carrier becomes "AC", the
  referenced Area name becomes the bus location, and bustype REF becomes control Slack.

  Scenario: single ACBus referencing an Area translates to one PyPSA AC bus
    Given a Sienna system file "inputs/single_bus.json" with ACBus "bus_AL" base_voltage 380.0 bustype "PQ" in area "AL"
    When I run translate against Sienna system "inputs/single_bus.json" pipeline "sienna-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 1 bus
    And the PyPSA network "outputs/network.nc" bus "bus_AL" attribute "v_nom" is 380.0
    And the PyPSA network "outputs/network.nc" bus "bus_AL" has carrier "AC"
    And the PyPSA network "outputs/network.nc" bus "bus_AL" has control "PQ"
    And the PyPSA network "outputs/network.nc" bus "bus_AL" has location "AL"
    And the file "decisions.md" contains "| `sienna.ACBus.bus_AL.base_voltage` = 380.0 kV | `pypsa.Bus.bus_AL.v_nom` = 380.0 kV | direct |  | sienna-to-pypsa | sienna_to_pypsa_map_components |"
    And the file "decisions.md" contains "| `sienna.ACBus.bus_AL.bustype` = PQ | `pypsa.Bus.bus_AL.control` = PQ | ACBusType -> n.buses.control |  | sienna-to-pypsa | sienna_to_pypsa_map_components |"
    And the file "decisions.md" contains "| `sienna.ACBus.bus_AL.area` = AL | `pypsa.Bus.bus_AL.location` = AL | area name -> location |  | sienna-to-pypsa | sienna_to_pypsa_relate_components |"

  Scenario: ACBus bustype REF maps back to PyPSA control Slack
    Given a Sienna system file "inputs/ref_bus.json" with ACBus "bus_1" base_voltage 220.0 bustype "REF" in area "Z1"
    When I run translate against Sienna system "inputs/ref_bus.json" pipeline "sienna-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" bus "bus_1" has control "Slack"
    And the file "decisions.md" contains "| `sienna.ACBus.bus_1.bustype` = REF | `pypsa.Bus.bus_1.control` = Slack | ACBusType -> n.buses.control |  | sienna-to-pypsa | sienna_to_pypsa_map_components |"

  Scenario: ACBus with no area produces an empty bus location
    Given a Sienna system file "inputs/no_area.json" with ACBus "bus_1" base_voltage 380.0 bustype "PQ" and no area
    When I run translate against Sienna system "inputs/no_area.json" pipeline "sienna-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 1 bus
    And the PyPSA network "outputs/network.nc" bus "bus_1" has empty location

  Scenario: a ThermalStandard missing a required field is left out and the rest translate
    The reader checks every row against SiennaSchemas. A row that fails is left out and
    named in the log, and the other components are still translated.
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a ThermalStandard "good_1" on bus "node_a" with base_power 100.0 rating 100 active_power_min 10.0 active_power_max 100.0 marginal_cost 25.0 prime_mover "ST" fuel "COAL"
    And the system contains a ThermalStandard "bad_1" on bus "node_a" with base_power 100.0 rating 100 active_power_min 10.0 active_power_max 100.0 marginal_cost 25.0 prime_mover "ST" fuel "COAL"
    And the ThermalStandard "bad_1" has no base_power
    And the system is saved as "inputs/bad_row.json"
    When I run translate against "inputs/bad_row.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the log contains "ThermalStandard bad_1 (field base_power)"
    And the PyPSA network "outputs/network.nc" has 1 bus
    And the PyPSA network "outputs/network.nc" has 1 generator
    And the PyPSA network "outputs/network.nc" generator "good_1" has bus "node_a"

  Scenario: a system on another schema line stops and names its version
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system states schema_version "9.0.0"
    And the system is saved as "inputs/other_line.json"
    When I run translate against Sienna system "inputs/other_line.json" pipeline "sienna-to-pypsa" sink output "outputs/network.nc"
    Then the printed output contains "schema_version '9.0.0' is incompatible"

  Scenario: a component type that SiennaSchemas does not define is left out and named
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system has a component "x_1" of the unknown type "FluxCapacitor"
    And the system is saved as "inputs/unknown_type.json"
    When I run translate against "inputs/unknown_type.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the log contains "FluxCapacitor (type unknown to SiennaSchemas)"
    And the PyPSA network "outputs/network.nc" has 1 bus
