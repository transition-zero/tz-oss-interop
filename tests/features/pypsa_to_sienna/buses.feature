@slow @fork_unsafe
Feature: pypsa_to_sienna_map_components and pypsa_to_sienna_relate_components translate PyPSA Bus rows to Sienna ACBus
  The convert step filters source buses to AC-only and emits an intermediate
  destination table; the topology step derives bustype and areas from each bus's
  control and location fields. Non-AC buses are skipped and recorded in the
  decisions report.

  Scenario: single AC bus translates to one ACBus with correct voltage and area
    Given a PyPSA network
    And the network contains bus "bus_AL" carrier "AC" v_nom 380.0 location "AL"
    And the network is saved as "inputs/single_bus.nc"
    When I run translate against "inputs/single_bus.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with 1 components of type "ACBus"
    And the file "outputs/system.json" parses as JSON with 1 components of type "Area"
    And the file "outputs/system.json" parses as JSON with component "ACBus" named "bus_AL" having "base_voltage" set to 380.0
    And the file "outputs/system.json" parses as JSON with component "ACBus" named "bus_AL" having "id" set to 1
    And the file "outputs/system.json" parses as JSON with component "ACBus" named "bus_AL" having "number" set to 1
    And the file "outputs/system.json" parses as JSON with component "ACBus" named "bus_AL" having "available" set to true
    And the file "outputs/system.json" parses as JSON with component "Area" named "AL" having "name" set to "AL"
    And the file "outputs/system.json" parses as JSON with component "ACBus" named "bus_AL" having "area" set to 1
    And the file "decisions.md" contains "| `pypsa.Bus.bus_AL.v_nom` = 380.0 kV | `sienna.ACBus.bus_AL.base_voltage` = 380.0 kV | direct |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    And the file "decisions.md" contains "| `pypsa.Bus.bus_AL.carrier` = AC | `sienna.ACBus.bus_AL.type` = ACBus | AC carrier -> ACBus |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    And the file "decisions.md" contains "| `pypsa.Bus.bus_AL.location` = AL | `sienna.ACBus.bus_AL.area` = AL | location -> area name; null if absent |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    And the file "decisions.md" contains "|  | `sienna.ACBus.bus_AL.bustype` = PQ |  | n.buses.control absent; defaulted to PQ | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    And the file "decisions.md" contains "| `sienna.ACBus.bus_AL.area` = AL | `sienna.Area.AL` | one Area per distinct location |  | pypsa-to-sienna | pypsa_to_sienna_relate_components |"
    And the file "decisions.md" contains "| `sienna.Area.AL` | `sienna.Area.AL.type` = Area | Area |  | pypsa-to-sienna | pypsa_to_sienna_relate_components |"

  Scenario: a classic NETCDF3 network reads back through the filesystem port
    Given a PyPSA network
    And the network contains bus "bus_AL" carrier "AC" v_nom 380.0 location "AL"
    And the network is saved as classic netCDF "inputs/classic_bus.nc"
    When I run translate against "inputs/classic_bus.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with 1 components of type "ACBus"
    And the file "outputs/system.json" parses as JSON with component "ACBus" named "bus_AL" having "base_voltage" set to 380.0

  Scenario: DC bus is skipped and decisions.md records the component skip
    Given a PyPSA network
    And the network contains bus "bus_AC" carrier "AC" v_nom 380.0
    And the network contains bus "bus_DC" carrier "DC" v_nom 380.0
    And the network is saved as "inputs/ac_dc.nc"
    When I run translate against "inputs/ac_dc.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as valid JSON
    And the file "outputs/system.json" parses as JSON with 1 components of type "ACBus"
    And the file "decisions.md" contains "| `pypsa.Bus.bus_DC` |  |  | carrier='DC': only AC buses are supported in v1 | pypsa-to-sienna | pypsa_to_sienna_map_components |"

  Scenario: recognised control value derives bustype
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0 control "PV"
    And the network is saved as "inputs/pv_control.nc"
    When I run translate against "inputs/pv_control.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "ACBus" named "bus_1" having "bustype" set to "PV"
    And the file "decisions.md" contains "| `pypsa.Bus.bus_1.control` = PV | `sienna.ACBus.bus_1.bustype` = PV | n.buses.control -> ACBusType |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"

  Scenario: unrecognised control value defaults bustype to PQ
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0 control "unknown"
    And the network is saved as "inputs/unknown_control.nc"
    When I run translate against "inputs/unknown_control.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "ACBus" named "bus_1" having "bustype" set to "PQ"
    And the file "decisions.md" contains "|  | `sienna.ACBus.bus_1.bustype` = PQ |  | n.buses.control='unknown' unrecognised; defaulted to PQ | pypsa-to-sienna | pypsa_to_sienna_map_components |"

  Scenario: bus with no location produces no areas and a null area field
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network is saved as "inputs/no_location.nc"
    When I run translate against "inputs/no_location.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as valid JSON
    And the file "outputs/system.json" parses as JSON with 1 components of type "ACBus"
    And the file "outputs/system.json" parses as JSON with component "ACBus" named "bus_1" having "area" set to null
    And the file "outputs/system.json" parses as JSON with 0 components of type "Area"
    And the file "decisions.md" contains "| `pypsa.Bus.bus_1.location` | `sienna.ACBus.bus_1.area` | location -> area name; null if absent |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"

  Scenario: bus produces an extension record with carrier
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network is saved as "inputs/bus_ext.nc"
    When I run translate against "inputs/bus_ext.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/extensions.json" exists
    And the file "outputs/extensions.json" parses as JSON bus extension record for "bus_1" having "carrier" set to "AC"

  Scenario: bus with PyPSA default voltage limits gets fallback voltage_limits of (0.9, 1.1)
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network is saved as "inputs/default_vlimits.nc"
    When I run translate against "inputs/default_vlimits.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "ACBus" named "bus_1" having "voltage_limits" set to {"min": 0.9, "max": 1.1}
    And the file "decisions.md" contains "| `pypsa.Bus.bus_1.v_mag_pu_min` = 0.0<br>`pypsa.Bus.bus_1.v_mag_pu_max` = inf | `sienna.ACBus.bus_1.voltage_limits` = {'min': 0.9, 'max': 1.1} |  | PyPSA defaults (v_mag_pu_min=0.0, v_mag_pu_max=∞) are invalid for Sienna; applying fallback (0.9, 1.1) | pypsa-to-sienna | pypsa_to_sienna_map_components |"

  Scenario: bus at PyPSA's default v_nom, which the netCDF omits, keeps that voltage
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 1.0 location "AL"
    And the network is saved as "inputs/default_v_nom.nc"
    When I run translate against "inputs/default_v_nom.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "ACBus" named "bus_1" having "base_voltage" set to 1.0
    And the file "decisions.md" contains "PyPSA default is 1.0kV when bus voltage level was not specified"

  Scenario: bus with explicit voltage limits uses those values directly
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0 v_mag_pu_min 0.95 v_mag_pu_max 1.05
    And the network is saved as "inputs/explicit_vlimits.nc"
    When I run translate against "inputs/explicit_vlimits.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "ACBus" named "bus_1" having "voltage_limits" set to {"min": 0.95, "max": 1.05}
    And the file "decisions.md" contains "| `pypsa.Bus.bus_1.v_mag_pu_min` = 0.95<br>`pypsa.Bus.bus_1.v_mag_pu_max` = 1.05 | `sienna.ACBus.bus_1.voltage_limits` = {'min': 0.95, 'max': 1.05} | v_mag_pu_min, v_mag_pu_max -> voltage_limits.{min, max} |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"

  Scenario: bus angle is always 0.0 and magnitude comes from v_mag_pu_set
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0 v_mag_pu_set 0.98
    And the network is saved as "inputs/magnitude.nc"
    When I run translate against "inputs/magnitude.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "ACBus" named "bus_1" having "angle" set to 0.0
    And the file "outputs/system.json" parses as JSON with component "ACBus" named "bus_1" having "magnitude" set to 0.98
    And the file "decisions.md" contains "| `pypsa.Bus.bus_1.v_mag_pu_set` = 0.98 | `sienna.ACBus.bus_1.magnitude` = 0.98 | direct |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"

  Scenario: buses in two different locations each reference their own area
    Given a PyPSA network
    And the network contains bus "bus_AL" carrier "AC" v_nom 380.0 location "AL"
    And the network contains bus "bus_AT" carrier "AC" v_nom 420.0 location "AT"
    And the network is saved as "inputs/two_location.nc"
    When I run translate against "inputs/two_location.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as valid JSON
    And the file "outputs/system.json" parses as JSON with 2 components of type "ACBus"
    And the file "outputs/system.json" parses as JSON with component "ACBus" named "bus_AL" having "base_voltage" set to 380.0
    And the file "outputs/system.json" parses as JSON with component "ACBus" named "bus_AT" having "base_voltage" set to 420.0
    And the file "outputs/system.json" parses as JSON with 2 components of type "Area"
    And the file "outputs/system.json" parses as JSON with component "Area" named "AL" having "name" set to "AL"
    And the file "outputs/system.json" parses as JSON with component "Area" named "AT" having "name" set to "AT"
    And the file "decisions.md" contains "| `sienna.ACBus.bus_AL.area` = AL | `sienna.Area.AL` | one Area per distinct location |  | pypsa-to-sienna | pypsa_to_sienna_relate_components |"
    And the file "decisions.md" contains "| `sienna.ACBus.bus_AT.area` = AT | `sienna.Area.AT` | one Area per distinct location |  | pypsa-to-sienna | pypsa_to_sienna_relate_components |"

  Scenario: a field of a bus record this leg reads nothing from is reported as dropped
    The price a shortfall costs is the one thing this leg takes off a bus's sidecar record,
    and asking for the price is what marks the whole record read. Every other field the
    record states is reported here, so a record read for a price it does not carry still
    says what was left behind.
    Given a PyPSA network
    And the network contains bus "bus_AL" carrier "AC" v_nom 380.0
    And the network is saved as "inputs/bus_sidecar.nc"
    And a file "inputs/extensions.json" containing the lines:
      | line |
      | {"bus": [{"name": "bus_AL", "carrier": "AC"}]} |
    When I run translate against "inputs/bus_sidecar.nc" with sidecar "inputs/extensions.json" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with 1 components of type "ACBus"
    And the file "decisions.md" contains "| `pypsa.bus.bus_AL.carrier` = AC |  |  | this translation reads only the price of a shortfall off a bus record, so the record's other fields are dropped | pypsa-to-sienna | pypsa_to_sienna_map_components |"
