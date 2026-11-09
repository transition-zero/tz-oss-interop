@slow @fork_unsafe
Feature: tz-osemosys-to-sienna translates one year of a TZ-format model into a Sienna operations system
  The pipeline has the steps of osemosys-csv-to-sienna. Only its source is different, because
  each step reads the canonical stage and not the model file.

  The invented model below has one region, R1, with a gas plant that puts out electricity.

  Scenario: A gas plant with residual capacity becomes a ThermalStandard on the bus of its electricity
    Given a TZ-format model
    And the TZ-format model has the regions "R1"
    And the TZ-format model has the years "2030"
    And the TZ-format model has the timeslices "S1 S2"
    And the TZ-format time definition has the field "year_split" set to {"S1": 0.5, "S2": 0.5}
    And the TZ-format model has the commodities "electricity natural-gas"
    And the TZ-format commodity "electricity" has the field "demand_annual" set to {"R1": {"2030": 876.0}}
    And the TZ-format commodity "electricity" has the field "demand_profile" set to {"R1": {"2030": {"S1": 0.5, "S2": 0.5}}}
    And the TZ-format technology "gas-combined-cycle" has the field "residual_capacity" set to {"R1": {"2030": 0.5}}
    And the TZ-format technology "gas-combined-cycle" has the field "capacity_activity_unit_ratio" set to {"R1": 8760}
    And the TZ-format technology "gas-combined-cycle" has the field "operating_modes" set to [{"id": "generation", "input_activity_ratio": {"R1": {"natural-gas": {"2030": 2.0}}}, "output_activity_ratio": {"R1": {"electricity": {"2030": 1.0}}}}]
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                                                              |
      | osemosys: {                                                                                                                       |
      | units: {capacity: GW, energy: GWh, currency: USD},                                                                                |
      | objects: {                                                                                                                        |
      | fuels: [{match: "^electricity$", carrier: electricity}, {match: "^natural-gas$", carrier: gas}],                                  |
      | technologies: [{match: "^gas-combined-cycle$", category: gas-cc}]}}                                                               |
      | carriers: [{osemosys_category: gas-cc, sienna_component_type: ThermalStandard, sienna_fuel_type: NATURAL_GAS, sienna_prime_mover_type: CC}] |
    When I translate the TZ-format model to Sienna for the year "2030"
    Then the pipeline exit code is 0
    And the file "outputs/system.json" parses as JSON with 1 component of type "ACBus"
    And the file "outputs/system.json" parses as JSON with component "ACBus" named "R1/electricity" having "bustype" set to "PQ"
    And the file "outputs/system.json" parses as JSON with 1 component of type "ThermalStandard"
    And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "gas-combined-cycle" having "base_power" set to 500.0
    And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "gas-combined-cycle" having "bus" set to 1
