@slow @fork_unsafe
Feature: sienna-to-osemosys-csv turns each generator record into an OSeMOSYS technology
  Sienna holds electricity only, so a technology that supplies a fuel that is not
  electricity has no Sienna component. It travels as a `generator` record of the
  `extensions.json` sidecar, which states the bus of the fuel it puts out, the megawatts of
  that fuel that already run, and what one megawatt hour of it costs.

  Such a record gives one OSeMOSYS technology that puts out that fuel, so a demand for a fuel
  that is not electricity has something to meet it.

  Background:
    Given a Sienna system
    And the system contains an area "R1"
    And the system contains a bus "R1/electricity" in area "R1"
    And the system contains a PowerLoad "electricity" on bus "R1/electricity" with max_active_power 100
    And the PowerLoad "electricity" has a max_active_power series 10 20 30 40
    And the system has a bus extension record "R1/gas" with "location" set to "R1"

  Scenario: a generator record on a fuel bus gives a technology that supplies that fuel
    The record states the megawatts of the fuel that already run and what one megawatt hour
    of it costs, so the technology puts out one megawatt hour of the fuel for one megawatt
    hour of its activity.
    Given the system has a generator extension record "R1/gas supply" with "bus" set to "R1/gas"
    And the system has a generator extension record "R1/gas supply" with "p_nom" set to 500.0
    And the system has a generator extension record "R1/gas supply" with "marginal_cost" set to 3.0
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/ResidualCapacity.csv" states the values:
      | REGION | TECHNOLOGY    | YEAR | VALUE |
      | R1     | R1/gas supply | 2020 | 500   |
    And the otoole CSV file "outputs/model/csv/OutputActivityRatio.csv" states the values:
      | REGION | TECHNOLOGY    | FUEL | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | R1/gas supply | gas  | 1                 | 2020 | 1     |
    And the otoole CSV file "outputs/model/csv/VariableCost.csv" states the values:
      | REGION | TECHNOLOGY    | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | R1/gas supply | 1                 | 2020 | 3     |
    And the otoole CSV file "outputs/model/csv/TECHNOLOGY.csv" has 1 rows
    And the otoole CSV file "outputs/model/csv/FUEL.csv" has 2 rows
    And the file "decisions.md" contains "R1/gas supply"
    And the file "decisions.md" contains "extensions.p_nom"

  Scenario: the availability of such a technology comes from the p_max_pu of its record
    A record states the share of a year that the technology can run as `p_max_pu`, which is
    the `AvailabilityFactor` that the forward leg read it from.
    Given the system has a generator extension record "R1/gas supply" with "bus" set to "R1/gas"
    And the system has a generator extension record "R1/gas supply" with "p_nom" set to 500.0
    And the system has a generator extension record "R1/gas supply" with "p_max_pu" set to 0.9
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/AvailabilityFactor.csv" states the values:
      | REGION | TECHNOLOGY    | YEAR | VALUE |
      | R1     | R1/gas supply | 2020 | 0.9   |
    And the file "outputs/model/csv/CapacityFactor.csv" does not exist

  Scenario: the emission rates and the build cost of such a technology come back
    A record of a fuel technology states what it emits for each megawatt hour of its fuel,
    and what one megawatt of its capacity costs to build and to keep.
    Given the system has a generator extension record "R1/gas supply" with "bus" set to "R1/gas"
    And the system has a generator extension record "R1/gas supply" with "p_nom" set to 500.0
    And the system has a generator extension record "R1/gas supply" with "emission_rates_t_per_mwh" set to {"CH4": 0.02}
    And the system has a generator extension record "R1/gas supply" with "overnight_cost_per_mw" set to 100000.0
    And the system has a generator extension record "R1/gas supply" with "e_sum_max" set to {"2020": 7000000.0}
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/EmissionActivityRatio.csv" states the values:
      | REGION | TECHNOLOGY    | EMISSION | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | R1/gas supply | CH4      | 1                 | 2020 | 0.02  |
    And the otoole CSV file "outputs/model/csv/CapitalCost.csv" states the values:
      | REGION | TECHNOLOGY    | YEAR | VALUE  |
      | R1     | R1/gas supply | 2020 | 100000 |
    And the otoole CSV file "outputs/model/csv/TotalTechnologyAnnualActivityUpperLimit.csv" states the values:
      | REGION | TECHNOLOGY    | YEAR | VALUE   |
      | R1     | R1/gas supply | 2020 | 7000000 |

  Scenario: a plant and the producer of its fuel both give a technology
    A plant that draws its fuel from a bus takes that fuel in, and the record of the producer
    of that fuel puts it out, so the written model balances the fuel.
    Given the system contains a ThermalStandard "GAS" on bus "R1/electricity" with base_power 100 rating 100 active_power_min 0 active_power_max 100 marginal_cost 25 prime_mover "CT" fuel "NATURAL_GAS"
    And the ThermalStandard "GAS" has ext "fuel_buses" set to {"R1/gas": 2.0}
    And the system has a generator extension record "R1/gas supply" with "bus" set to "R1/gas"
    And the system has a generator extension record "R1/gas supply" with "p_nom" set to 500.0
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/TECHNOLOGY.csv" has 2 rows
    And the otoole CSV file "outputs/model/csv/InputActivityRatio.csv" states the values:
      | REGION | TECHNOLOGY | FUEL | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | GAS        | gas  | 1                 | 2020 | 2     |
    And the otoole CSV file "outputs/model/csv/OutputActivityRatio.csv" states the values:
      | REGION | TECHNOLOGY    | FUEL        | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | GAS           | electricity | 1                 | 2020 | 1     |
      | R1     | R1/gas supply | gas         | 1                 | 2020 | 1     |
    And the otoole CSV file "outputs/model/csv/ResidualCapacity.csv" states the values:
      | REGION | TECHNOLOGY    | YEAR | VALUE |
      | R1     | GAS           | 2020 | 100   |
      | R1     | R1/gas supply | 2020 | 500   |

  Scenario: a record that states no bus is the record of a Sienna component
    The record of a Sienna generator carries the fields that no Sienna field holds, and it
    states no bus, so it is no technology of its own.
    Given the system contains a ThermalStandard "GAS" on bus "R1/electricity" with base_power 100 rating 100 active_power_min 0 active_power_max 100 marginal_cost 25 prime_mover "CT" fuel "NATURAL_GAS"
    And the ThermalStandard "GAS" has ext "carrier" set to "gas"
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/TECHNOLOGY.csv" has 1 rows
    And the otoole CSV file "outputs/model/csv/ResidualCapacity.csv" states the values:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | GAS        | 2020 | 100   |

  Scenario: a record whose name is a Sienna generator gives no second technology
    A record of that name belongs to the generator that Sienna holds, so the leg reads it as
    that generator's own and writes one technology and not two.
    Given the system contains a ThermalStandard "GAS" on bus "R1/electricity" with base_power 100 rating 100 active_power_min 0 active_power_max 100 marginal_cost 25 prime_mover "CT" fuel "NATURAL_GAS"
    And the ThermalStandard "GAS" has ext "bus" set to "R1/gas"
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/TECHNOLOGY.csv" has 1 rows
    And the otoole CSV file "outputs/model/csv/ResidualCapacity.csv" states the values:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | GAS        | 2020 | 100   |

  Scenario: a record that states no capacity is left out
    OSeMOSYS states the share of a fleet that a technology can use, so a record of no
    megawatts has no fleet to take a share of.
    Given the system has a generator extension record "R1/gas supply" with "bus" set to "R1/gas"
    And the system has a generator extension record "R1/gas supply" with "p_nom" set to 500.0
    And the system has a generator extension record "R1/coal supply" with "bus" set to "R1/coal"
    And the system has a generator extension record "R1/coal supply" with "marginal_cost" set to 2.0
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/ResidualCapacity.csv" states the values:
      | REGION | TECHNOLOGY    | YEAR | VALUE |
      | R1     | R1/gas supply | 2020 | 500   |
    And the file "decisions.md" contains "R1/coal supply"
    And the log contains "state no capacity"
    And the log contains "1 generator(s) state no capacity"
