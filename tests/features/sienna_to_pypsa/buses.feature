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
