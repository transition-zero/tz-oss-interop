@slow @fork_unsafe
Feature: sienna-to-results writes annual rows for a solve over representative periods
  A solve over representative periods states each hour of a period once. The extensions
  sidecar of the system gives each period its first hour, its length and its weight, which is
  how many times the period occurs in the year. The step then also writes production,
  installed capacity and emissions, each at 1 January of the year of the solve.

  The invented system below has a gas plant, a solar plant, a rooftop solar plant with a fixed
  output, a battery and an HVDC line. The solve covers four hours. The solve states the flow of
the HVDC line in MW. The gas plant emits 0.5 t of
  CO2 and 0.01 t of NOX for each MWh.

  Background:
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a bus "node_b"
    And the system contains a ThermalStandard "gas" on bus "node_a" with base_power 200 rating 0.5 active_power_min 0 active_power_max 100 marginal_cost 25 prime_mover "CC" fuel "NATURAL_GAS"
    And the ThermalStandard "gas" has ext carrier "gas"
    And the ThermalStandard "gas" has ext emission rate 0.5 t/MWh of "CO2"
    And the ThermalStandard "gas" has ext emission rate 0.01 t/MWh of "NOX"
    And the system contains a RenewableDispatch "solar" on bus "node_b" with base_power 50 rating 1 active_power 0 marginal_cost 0 prime_mover "PVe"
    And the RenewableDispatch "solar" has ext carrier "solar"
    And the system contains a RenewableNonDispatch "rooftop" on bus "node_b" with base_power 4 rating 1 active_power 0 prime_mover "PVe"
    And the RenewableNonDispatch "rooftop" has ext carrier "solar-rooftop"
    And the system contains an EnergyReservoirStorage "battery" on bus "node_b" with base_power 10 storage_capacity 40 initial_level 0 rating 0.5 input_max 1 output_max 1 efficiency_in 1 efficiency_out 1 discharge_cost 0
    And the system contains an HVDC line "link" from "node_a" to "node_b" with p_nom 20 efficiency 1
    And Sienna solve results
    And the results cover snapshots 2030-01-01T00:00:00 2030-01-01T01:00:00 2030-01-01T02:00:00 2030-01-01T03:00:00
    And the results have ThermalStandard dispatch for "gas" of 10 20 30 40
    And the results have RenewableDispatch dispatch for "solar" of 0 5 5 0
    And the results have RenewableNonDispatch output for "rooftop" of 1 2 2 1
    And the results have EnergyReservoirStorage output for "battery" of 0 0 8 0
    And the results have EnergyReservoirStorage input for "battery" of 4 0 0 0
    And the results have HVDC flow for "link" of 5 -3 0 2
    And the results are saved in "results"

  Scenario: Production weights each hour by its period, and an HVDC line delivers its flow in either direction
    Given the system has a representative period "day_1" from "2030-01-01T00:00:00" of 2 hours with weight 100
    And the system has a representative period "day_2" from "2030-01-01T02:00:00" of 2 hours with weight 50
    And the system is saved as "inputs/system.json"
    When I run the pipeline "sienna-to-results" with overrides "source.system_json_path=inputs/system.json source.extensions_json_path=inputs/system_extensions.json source.results_dir=results"
    Then the pipeline exit code is 0
    And the results parquet "outputs/results.parquet" has these "production" rows:
      | variable   | component | category      | timestamp           | value |
      | production | gas       | gas           | 2030-01-01T00:00:00 | 6500  |
      | production | solar     | solar         | 2030-01-01T00:00:00 | 750   |
      | production | rooftop   | solar-rooftop | 2030-01-01T00:00:00 | 450   |
      | production | battery   | PHS           | 2030-01-01T00:00:00 | 400   |
      | production | link      |               | 2030-01-01T00:00:00 | 900   |
    And the file "decisions.md" contains "the energy that it delivers equals the energy that it sends"

  Scenario: A plant that draws its fuel from a bus keeps its category
    The mapping of the network makes the gas plant a link from the bus of its gas, and the link
    keeps the carrier of the plant.
    Given the system has a bus extension record "R1/GAS" with "carrier" set to "gas"
    And the ThermalStandard "gas" has ext "fuel_buses" set to {"R1/GAS": 2.0}
    And the system has a representative period "day_1" from "2030-01-01T00:00:00" of 2 hours with weight 100
    And the system has a representative period "day_2" from "2030-01-01T02:00:00" of 2 hours with weight 50
    And the system is saved as "inputs/system.json"
    When I run the pipeline "sienna-to-results" with overrides "source.system_json_path=inputs/system.json source.extensions_json_path=inputs/system_extensions.json source.results_dir=results"
    Then the pipeline exit code is 0
    And the results parquet "outputs/results.parquet" holds these "production" rows among others:
      | variable   | component | category | timestamp           | value |
      | production | gas       | gas      | 2030-01-01T00:00:00 | 6500  |
    And the results parquet "outputs/results.parquet" holds these "dispatch" rows among others:
      | variable | component | category | timestamp           | value |
      | dispatch | gas       | gas      | 2030-01-01T00:00:00 | 10    |

  Scenario: A renewable plant has hourly dispatch rows
    Given the system is saved as "inputs/system.json"
    When I run the pipeline "sienna-to-results" with overrides "source.system_json_path=inputs/system.json source.extensions_json_path=inputs/system_extensions.json source.results_dir=results"
    Then the pipeline exit code is 0
    And the results parquet "outputs/results.parquet" holds these "dispatch" rows among others:
      | variable | component | category      | timestamp           | value |
      | dispatch | solar     | solar         | 2030-01-01T01:00:00 | 5     |
      | dispatch | rooftop   | solar-rooftop | 2030-01-01T02:00:00 | 2     |

  Scenario: The hourly flow of an HVDC line is the MW that the solve states
    Given the system is saved as "inputs/system.json"
    When I run the pipeline "sienna-to-results" with overrides "source.system_json_path=inputs/system.json source.extensions_json_path=inputs/system_extensions.json source.results_dir=results"
    Then the pipeline exit code is 0
    And the results parquet "outputs/results.parquet" has these "flow" rows:
      | variable | component | category | timestamp           | value |
      | flow     | link      |          | 2030-01-01T00:00:00 | 5     |
      | flow     | link      |          | 2030-01-01T01:00:00 | -3    |
      | flow     | link      |          | 2030-01-01T02:00:00 | 0     |
      | flow     | link      |          | 2030-01-01T03:00:00 | 2     |

  Scenario: Installed capacity is the rating of each generator, storage and HVDC line
    Given the system has a representative period "day_1" from "2030-01-01T00:00:00" of 2 hours with weight 100
    And the system has a representative period "day_2" from "2030-01-01T02:00:00" of 2 hours with weight 50
    And the system is saved as "inputs/system.json"
    When I run the pipeline "sienna-to-results" with overrides "source.system_json_path=inputs/system.json source.extensions_json_path=inputs/system_extensions.json source.results_dir=results"
    Then the pipeline exit code is 0
    And the results parquet "outputs/results.parquet" has these "installed_capacity" rows:
      | variable           | component | category      | timestamp           | value |
      | installed_capacity | gas       | gas           | 2030-01-01T00:00:00 | 100   |
      | installed_capacity | solar     | solar         | 2030-01-01T00:00:00 | 50    |
      | installed_capacity | rooftop   | solar-rooftop | 2030-01-01T00:00:00 | 4     |
      | installed_capacity | battery   | PHS           | 2030-01-01T00:00:00 | 10    |
      | installed_capacity | link      |               | 2030-01-01T00:00:00 | 20    |

  Scenario: A storage takes the category that its sidecar record names
    Given the EnergyReservoirStorage "battery" has ext "carrier" set to "battery"
    And the system has a representative period "day_1" from "2030-01-01T00:00:00" of 2 hours with weight 100
    And the system has a representative period "day_2" from "2030-01-01T02:00:00" of 2 hours with weight 50
    And the system is saved as "inputs/system.json"
    When I run the pipeline "sienna-to-results" with overrides "source.system_json_path=inputs/system.json source.extensions_json_path=inputs/system_extensions.json source.results_dir=results"
    Then the pipeline exit code is 0
    And the results parquet "outputs/results.parquet" holds these "production" rows among others:
      | variable   | component | category | timestamp           | value |
      | production | battery   | battery  | 2030-01-01T00:00:00 | 400   |
    And the results parquet "outputs/results.parquet" holds these "installed_capacity" rows among others:
      | variable           | component | category | timestamp           | value |
      | installed_capacity | battery   | battery  | 2030-01-01T00:00:00 | 10    |

  Scenario: An annual energy bound of a generator gives no warning, as the results map no network
    The pipeline reuses the Sienna to PyPSA mapping, and skips its energy bounds.
    Given the ThermalStandard "gas" has ext "e_sum_min" set to {"2030": 100.0}
    And the system has a representative period "day_1" from "2030-01-01T00:00:00" of 2 hours with weight 100
    And the system has a representative period "day_2" from "2030-01-01T02:00:00" of 2 hours with weight 50
    And the system is saved as "inputs/system.json"
    When I run the pipeline "sienna-to-results" with overrides "source.system_json_path=inputs/system.json source.extensions_json_path=inputs/system_extensions.json source.results_dir=results"
    Then the pipeline exit code is 0
    And the log does not contain "annual energy bound(s)"

  Scenario: Emissions are the production of each generator times its rate, by pollutant
    Given the system has a representative period "day_1" from "2030-01-01T00:00:00" of 2 hours with weight 100
    And the system has a representative period "day_2" from "2030-01-01T02:00:00" of 2 hours with weight 50
    And the system is saved as "inputs/system.json"
    When I run the pipeline "sienna-to-results" with overrides "source.system_json_path=inputs/system.json source.extensions_json_path=inputs/system_extensions.json source.results_dir=results"
    Then the pipeline exit code is 0
    And the results parquet "outputs/results.parquet" has these "emissions" rows:
      | variable  | component | category | timestamp           | value |
      | emissions | CO2       |          | 2030-01-01T00:00:00 | 3250  |
      | emissions | NOX       |          | 2030-01-01T00:00:00 | 65    |

  Scenario: Hours in no representative period are left out of the year, and reported as one run
    Given the system has a representative period "day_1" from "2030-01-01T00:00:00" of 1 hours with weight 100
    And the system has a representative period "day_2" from "2030-01-01T03:00:00" of 1 hours with weight 50
    And the system is saved as "inputs/system.json"
    When I run the pipeline "sienna-to-results" with overrides "source.system_json_path=inputs/system.json source.extensions_json_path=inputs/system_extensions.json source.results_dir=results"
    Then the pipeline exit code is 0
    And the results parquet "outputs/results.parquet" holds these "production" rows among others:
      | variable   | component | category | timestamp           | value |
      | production | gas       | gas      | 2030-01-01T00:00:00 | 3000  |
      | production | link      |          | 2030-01-01T00:00:00 | 600   |
    And the log contains "2 hour(s) of the solve, in 1 run(s) of consecutive hours, fall in no representative period"
    And the file "decisions.md" contains "2030-01-01T01:00:00 to 2030-01-01T02:00:00"
    And the file "decisions.md" contains "2 consecutive hour(s) of the solve fall in no representative period"

  Scenario Outline: A representative period that cannot weight its hours is left out, and reported
    Given the system has a representative period "day_1" from "2030-01-01T00:00:00" of 2 hours with weight 100
    And the system has a representative period "day_2" from "<first_timestamp>" of <hours> hours with weight <weight>
    And the system is saved as "inputs/system.json"
    When I run the pipeline "sienna-to-results" with overrides "source.system_json_path=inputs/system.json source.extensions_json_path=inputs/system_extensions.json source.results_dir=results"
    Then the pipeline exit code is 0
    And the log contains "1 representative period(s) cannot give their hours a weight"
    And the log contains "2 hour(s) of the solve, in 1 run(s) of consecutive hours, fall in no representative period"
    And the file "decisions.md" contains "## Components skipped (1)"
    And the file "decisions.md" contains "`sienna.representative_period.day_2`"
    And the file "decisions.md" contains "<fault>"
    And the results parquet "outputs/results.parquet" holds these "production" rows among others:
      | variable   | component | category | timestamp           | value |
      | production | gas       | gas      | 2030-01-01T00:00:00 | 3000  |

    Examples:
      | first_timestamp           | hours | weight | fault                                                |
      | not a timestamp           | 2     | 50     | is not an ISO 8601 date and time                     |
      | 2030-01-01T02:00:00+01:00 | 2     | 50     | states a time zone, and the hours of the solve state none |
      | 2030-01-01T02:00:00       | 9000  | 50     | its hours, 9000, is not between 1 and 8784           |
      | 2030-01-01T02:00:00       | 2     | nan    | its weight, nan, is not a finite number of 0 or more |

  Scenario: A representative period that holds an hour of an earlier period is left out, and reported
    Given the system has a representative period "day_1" from "2030-01-01T00:00:00" of 3 hours with weight 100
    And the system has a representative period "day_2" from "2030-01-01T02:00:00" of 2 hours with weight 50
    And the system is saved as "inputs/system.json"
    When I run the pipeline "sienna-to-results" with overrides "source.system_json_path=inputs/system.json source.extensions_json_path=inputs/system_extensions.json source.results_dir=results"
    Then the pipeline exit code is 0
    And the log contains "1 representative period(s) hold an hour that an earlier period holds, so each is left out: day_2"
    And the file "decisions.md" contains "the period day_1 also holds"
    And the log contains "1 hour(s) of the solve, in 1 run(s) of consecutive hours, fall in no representative period"
    And the results parquet "outputs/results.parquet" holds these "production" rows among others:
      | variable   | component | category | timestamp           | value |
      | production | gas       | gas      | 2030-01-01T00:00:00 | 6000  |

  Scenario: A plant that has a rating and no output in the solve has no production, and is reported
    Given the system contains a RenewableNonDispatch "roof_b" on bus "node_b" with base_power 3 rating 1 active_power 0 prime_mover "PVe"
    And the RenewableNonDispatch "roof_b" has ext carrier "solar-rooftop"
    And the system has a representative period "day_1" from "2030-01-01T00:00:00" of 2 hours with weight 100
    And the system has a representative period "day_2" from "2030-01-01T02:00:00" of 2 hours with weight 50
    And the system is saved as "inputs/system.json"
    When I run the pipeline "sienna-to-results" with overrides "source.system_json_path=inputs/system.json source.extensions_json_path=inputs/system_extensions.json source.results_dir=results"
    Then the pipeline exit code is 0
    And the log contains "1 component(s) have a rating, but the solve states no output for them, so they have no production: roof_b"
    And the file "decisions.md" contains "`sienna.RenewableNonDispatch.roof_b`"
    And the results parquet "outputs/results.parquet" holds these "installed_capacity" rows among others:
      | variable           | component | category      | timestamp           | value |
      | installed_capacity | roof_b    | solar-rooftop | 2030-01-01T00:00:00 | 3     |

  Scenario: A solve with no representative periods has no annual rows
    Given the system is saved as "inputs/system.json"
    When I run the pipeline "sienna-to-results" with overrides "source.system_json_path=inputs/system.json source.extensions_json_path=inputs/system_extensions.json source.results_dir=results"
    Then the pipeline exit code is 0
    And the results parquet "outputs/results.parquet" has these "production" rows:
      | variable | component | category | timestamp | value |
    And the results parquet "outputs/results.parquet" has these "installed_capacity" rows:
      | variable | component | category | timestamp | value |
    And the results parquet "outputs/results.parquet" has these "emissions" rows:
      | variable | component | category | timestamp | value |
