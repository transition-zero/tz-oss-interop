@slow @fork_unsafe
Feature: osemosys-csv-to-sienna reports each row of a parameter that no step of the pipeline applies
  A parameter of the canonical stage can hold data that no Sienna document has a field for. The
  report step runs last, and records NOT_MAPPED for each member whose rows no step applies or
  writes to extensions.json, and warns once for each parameter.

  The invented model below has the calendar and the demand of the operations features. The gas
  plant ATGASCC at AT is a combined heat and power plant: at mode 1 it puts out 1 unit of the
  electricity ATELEC and 0.8 of a unit of the heat ATHEAT for each unit of its activity.

  Background:
    Given an otoole model
    And the otoole set "REGION" holds "R1"
    And the otoole set "FUEL" holds "ATELEC DEELEC GAS ATHEAT"
    And the otoole set "YEAR" holds "2030 2035"
    And the otoole set "TIMESLICE" holds "S1B1 S1B2 S2B1 S2B2"
    And the otoole set "SEASON" holds "S1 S2"
    And the otoole set "DAYTYPE" holds "1"
    And the otoole set "DAILYTIMEBRACKET" holds "B1 B2"
    And the otoole parameter "YearSplit" keyed by "TIMESLICE YEAR" with default 0 has the rows:
      | TIMESLICE | YEAR | VALUE |
      | S1B1      | 2030 | 0.125 |
      | S1B2      | 2030 | 0.375 |
      | S2B1      | 2030 | 0.125 |
      | S2B2      | 2030 | 0.375 |
    And the otoole parameter "DaySplit" keyed by "DAILYTIMEBRACKET YEAR" with default 0.00137 has the rows:
      | DAILYTIMEBRACKET | YEAR | VALUE    |
      | B1               | 2030 | 0.000685 |
      | B2               | 2030 | 0.002055 |
    And the otoole parameter "Conversionls" keyed by "TIMESLICE SEASON" with default 0 has the rows:
      | TIMESLICE | SEASON | VALUE |
      | S1B1      | S1     | 1     |
      | S1B2      | S1     | 1     |
      | S2B1      | S2     | 1     |
      | S2B2      | S2     | 1     |
    And the otoole parameter "Conversionld" keyed by "TIMESLICE DAYTYPE" with default 0 has the rows:
      | TIMESLICE | DAYTYPE | VALUE |
      | S1B1      | 1       | 1     |
      | S1B2      | 1       | 1     |
      | S2B1      | 1       | 1     |
      | S2B2      | 1       | 1     |
    And the otoole parameter "Conversionlh" keyed by "TIMESLICE DAILYTIMEBRACKET" with default 0 has the rows:
      | TIMESLICE | DAILYTIMEBRACKET | VALUE |
      | S1B1      | B1               | 1     |
      | S1B2      | B2               | 1     |
      | S2B1      | B1               | 1     |
      | S2B2      | B2               | 1     |
    And the otoole parameter "SpecifiedAnnualDemand" keyed by "REGION FUEL YEAR" with default 0 has the rows:
      | REGION | FUEL   | YEAR | VALUE |
      | R1     | ATELEC | 2030 | 876   |
    And the otoole parameter "SpecifiedDemandProfile" keyed by "REGION FUEL TIMESLICE YEAR" with default 0 has the rows:
      | REGION | FUEL   | TIMESLICE | YEAR | VALUE |
      | R1     | ATELEC | S1B1      | 2030 | 0.125 |
      | R1     | ATELEC | S1B2      | 2030 | 0.375 |
      | R1     | ATELEC | S2B1      | 2030 | 0.25  |
      | R1     | ATELEC | S2B2      | 2030 | 0.25  |
    And the otoole parameter "AccumulatedAnnualDemand" keyed by "REGION FUEL YEAR" with default 0 has the rows:
      | REGION | FUEL   | YEAR | VALUE |
      | R1     | DEELEC | 2030 | 876   |
    And the otoole set "TECHNOLOGY" holds "ATGASCC"
    And the otoole set "MODE_OF_OPERATION" holds "1"
    And the otoole parameter "ResidualCapacity" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | ATGASCC    | 2030 | 0.5   |
    And the otoole parameter "OutputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | FUEL   | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | ATGASCC    | ATELEC | 1                 | 2030 | 1     |
      | R1     | ATGASCC    | ATHEAT | 1                 | 2030 | 0.8   |
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                                                         |
      | osemosys: {                                                                                                                  |
      | units: {capacity: GW, energy: GWh, currency: USD, emissions: t},                                                             |
      | objects: {                                                                                                                   |
      | fuels: [                                                                                                                     |
      | {match: "^(?P<country>[A-Z]{2})ELEC$", carrier: electricity, location: "{country}"},                                         |
      | {match: "^(?P<country>[A-Z]{2})HEAT$", carrier: heat, location: "{country}"}],                                               |
      | technologies: [{match: "GASCC$", category: gas-cc}]}}                                                                        |
      | carriers: [                                                                                                                  |
      | {osemosys_category: gas-cc, sienna_component_type: ThermalStandard, sienna_fuel_type: NATURAL_GAS, sienna_prime_mover_type: CC}] |

  Scenario: The heat that a combined heat and power plant puts out is reported
    The ThermalStandard ATGASCC holds the electricity output only, so the heat output reaches
    no Sienna field and no record of extensions.json.
    When I translate the otoole model to Sienna for the year "2030"
    Then the pipeline exit code is 0
    And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ATGASCC" having "bus" set to 1
    And the log contains "output_activity_ratio states"
    And the file "decisions.md" contains "`osemosys.output_activity_ratio.R1/ATGASCC"
