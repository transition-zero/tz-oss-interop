@slow @fork_unsafe
Feature: sienna-to-osemosys-csv turns each Sienna generator into an OSeMOSYS technology
  A Sienna generator rates in megawatts of electricity, and OSeMOSYS rates a technology by
  its activity and states how much of each fuel one unit of that activity takes in and puts
  out. The forward leg divided every value of a generator by the electricity output ratio of
  its technology, so the reverse leg writes that ratio as 1 and every value as the quotient
  that the forward leg left.

  A generator runs one operating mode, which the leg names 1. Each other mode of the
  technology travels as an `operating_modes` entry of the `extensions.json` sidecar, and that
  entry states the ratios of its own mode.

  Background:
    Given a Sienna system
    And the system contains an area "R1"
    And the system contains a bus "R1/electricity" in area "R1"
    And the system contains a PowerLoad "electricity" on bus "R1/electricity" with max_active_power 100
    And the PowerLoad "electricity" has a max_active_power series 10 20 30 40

  Scenario: a generator gives one technology, one mode and the capacity of its fleet
    The base power of a Sienna generator is the capacity that already runs, and the written
    model states that capacity as `ResidualCapacity` in megawatts.
    Given the system contains a ThermalStandard "GAS" on bus "R1/electricity" with base_power 100 rating 100 active_power_min 0 active_power_max 100 marginal_cost 25 prime_mover "CT" fuel "NATURAL_GAS"
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/ResidualCapacity.csv" states the values:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | GAS        | 2020 | 100   |
    And the otoole CSV file "outputs/model/csv/TECHNOLOGY.csv" has 1 rows
    And the otoole CSV file "outputs/model/csv/MODE_OF_OPERATION.csv" has 1 rows
    And the file "decisions.md" contains "ResidualCapacity"

  Scenario: the electricity output ratio is written as 1
    The forward leg divided the base power, each activity ratio, each cost and each emission
    rate of a technology by its electricity output ratio, and no Sienna field states that
    ratio. So the leg writes the ratio as 1 and reports every value that the ratio scaled.
    Given the system contains a ThermalStandard "GAS" on bus "R1/electricity" with base_power 100 rating 100 active_power_min 0 active_power_max 100 marginal_cost 25 prime_mover "CT" fuel "NATURAL_GAS"
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/OutputActivityRatio.csv" states the values:
      | REGION | TECHNOLOGY | FUEL        | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | GAS        | electricity | 1                 | 2020 | 1     |
    And the file "decisions.md" contains "writes that ratio as 1"
    And the log contains "no Sienna field states the electricity output ratio"

  Scenario: a generator whose record states fuel buses takes in each of those fuels
    A plant that draws a fuel from a bus states the megawatt hours of that fuel that one
    megawatt hour of its electricity takes, so each entry gives one `InputActivityRatio` row.
    Given the system contains a ThermalStandard "GAS" on bus "R1/electricity" with base_power 100 rating 100 active_power_min 0 active_power_max 100 marginal_cost 25 prime_mover "CT" fuel "NATURAL_GAS"
    And the ThermalStandard "GAS" has ext "fuel_buses" set to {"R1/gas": 2.0, "R1/coal": 0.5}
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/InputActivityRatio.csv" states the values:
      | REGION | TECHNOLOGY | FUEL | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | GAS        | coal | 1                 | 2020 | 0.5   |
      | R1     | GAS        | gas  | 1                 | 2020 | 2     |
    And the otoole CSV file "outputs/model/csv/OutputActivityRatio.csv" states the values:
      | REGION | TECHNOLOGY | FUEL        | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | GAS        | electricity | 1                 | 2020 | 1     |
    And the otoole CSV file "outputs/model/csv/FUEL.csv" has 3 rows

  Scenario: a generator whose record states output buses puts out each of those fuels
    A plant that puts out a fuel that is not electricity states the megawatt hours of that
    fuel that one megawatt hour of its electricity gives, so each entry gives one
    `OutputActivityRatio` row beside the electricity row.
    Given the system contains a ThermalStandard "CHP" on bus "R1/electricity" with base_power 100 rating 100 active_power_min 0 active_power_max 100 marginal_cost 25 prime_mover "CT" fuel "NATURAL_GAS"
    And the ThermalStandard "CHP" has ext "output_buses" set to {"R1/heat": 0.8}
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/OutputActivityRatio.csv" states the values:
      | REGION | TECHNOLOGY | FUEL        | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | CHP        | electricity | 1                 | 2020 | 1     |
      | R1     | CHP        | heat        | 1                 | 2020 | 0.8   |

  Scenario: a generator with two operating mode records gives three modes
    A Sienna generator runs one mode, and the sidecar holds each other mode of its
    technology, so the ratios of each other mode come from its own entry.
    Given the system contains a ThermalStandard "GAS" on bus "R1/electricity" with base_power 100 rating 100 active_power_min 0 active_power_max 100 marginal_cost 25 prime_mover "CT" fuel "NATURAL_GAS"
    And the ThermalStandard "GAS" has ext "operating_modes" set to [{"mode": "2", "input_ratios": {"gas": 3.0}, "output_ratios": {"electricity": 1.0}}, {"mode": "3", "input_ratios": {"oil": 4.0}, "output_ratios": {"electricity": 1.0}}]
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/MODE_OF_OPERATION.csv" has 3 rows
    And the otoole CSV file "outputs/model/csv/InputActivityRatio.csv" states the values:
      | REGION | TECHNOLOGY | FUEL | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | GAS        | gas  | 2                 | 2020 | 3     |
      | R1     | GAS        | oil  | 3                 | 2020 | 4     |
    And the otoole CSV file "outputs/model/csv/OutputActivityRatio.csv" states the values:
      | REGION | TECHNOLOGY | FUEL        | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | GAS        | electricity | 1                 | 2020 | 1     |
      | R1     | GAS        | electricity | 2                 | 2020 | 1     |
      | R1     | GAS        | electricity | 3                 | 2020 | 1     |

  Scenario: the held mode takes the first name that no operating mode record claims
    A sidecar entry names the mode that it states, and the mode that the generator runs is the
    one that no entry names. So a record that names mode 1 leaves mode 2 to the generator.
    Given the system contains a ThermalStandard "GAS" on bus "R1/electricity" with base_power 100 rating 100 active_power_min 0 active_power_max 100 marginal_cost 25 prime_mover "CT" fuel "NATURAL_GAS"
    And the ThermalStandard "GAS" has ext "operating_modes" set to [{"mode": "1", "input_ratios": {"gas": 3.0}, "output_ratios": {"electricity": 1.0}}]
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/OutputActivityRatio.csv" states the values:
      | REGION | TECHNOLOGY | FUEL        | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | GAS        | electricity | 1                 | 2020 | 1     |
      | R1     | GAS        | electricity | 2                 | 2020 | 1     |

  Scenario: a RenewableDispatch with an hourly series gives a capacity factor for each timeslice
    The series of a `RenewableDispatch` is a share of its rating, so one value of the series
    stands for that many megawatts. The share of the whole fleet that the generator can use in
    one hour is those megawatts over its base power, which is the `CapacityFactor` of the
    timeslice of that hour.
    Given the system contains a RenewableDispatch "WIND" on bus "R1/electricity" with base_power 100 rating 50 active_power 0 marginal_cost 0 prime_mover "WT"
    And the RenewableDispatch "WIND" has a max_active_power series 0.2 0.4 0.6 0.8
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/CapacityFactor.csv" states the values:
      | REGION | TECHNOLOGY | TIMESLICE | YEAR | VALUE |
      | R1     | WIND       | 1         | 2020 | 0.1   |
      | R1     | WIND       | 2         | 2020 | 0.2   |
      | R1     | WIND       | 3         | 2020 | 0.3   |
      | R1     | WIND       | 4         | 2020 | 0.4   |
    And the file "decisions.md" contains "CapacityFactor"

  Scenario: a generator that can use its whole fleet in every hour gets no capacity factor
    `CapacityFactor` defaults to 1, so a generator whose output limit is its whole base power
    and which states no series needs no row at all.
    Given the system contains a ThermalStandard "GAS" on bus "R1/electricity" with base_power 100 rating 100 active_power_min 0 active_power_max 100 marginal_cost 25 prime_mover "CT" fuel "NATURAL_GAS"
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the file "outputs/model/csv/CapacityFactor.csv" does not exist

  Scenario: a thermal generator whose output limit is below its fleet uses that share in every hour
    A `ThermalStandard` that states no series can use the same share of its base power in
    every hour, and its `active_power_limits.max` holds that share.
    Given the system contains a ThermalStandard "GAS" on bus "R1/electricity" with base_power 100 rating 100 active_power_min 0 active_power_max 80 marginal_cost 25 prime_mover "CT" fuel "NATURAL_GAS"
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/CapacityFactor.csv" states the values:
      | REGION | TECHNOLOGY | TIMESLICE | YEAR | VALUE |
      | R1     | GAS        | 1         | 2020 | 0.8   |
      | R1     | GAS        | 2         | 2020 | 0.8   |
      | R1     | GAS        | 3         | 2020 | 0.8   |
      | R1     | GAS        | 4         | 2020 | 0.8   |

  Scenario: a generator whose power is not in natural units is left out
    The megawatts of a generator that states another power basis are a share of a base power,
    so reading them as megawatts would write a number nobody meant.
    Given the system contains a ThermalStandard "GAS" on bus "R1/electricity" with base_power 100 rating 100 active_power_min 0 active_power_max 100 marginal_cost 25 prime_mover "CT" fuel "NATURAL_GAS"
    And the system contains a ThermalStandard "BASED" on bus "R1/electricity" with base_power 50 rating 50 active_power_min 0 active_power_max 50 marginal_cost 25 prime_mover "CT" fuel "NATURAL_GAS"
    And the ThermalStandard "BASED" states power_units COMPONENT_BASE
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/ResidualCapacity.csv" states the values:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | GAS        | 2020 | 100   |
    And the file "decisions.md" contains "BASED"
    And the log contains "state a power basis this reader does not read"

  Scenario: a generator with no base power is left out
    OSeMOSYS states the share of a fleet that a technology can use, so a generator of no base
    power has no fleet to take a share of.
    Given the system contains a ThermalStandard "GAS" on bus "R1/electricity" with base_power 100 rating 100 active_power_min 0 active_power_max 100 marginal_cost 25 prime_mover "CT" fuel "NATURAL_GAS"
    And the system contains a ThermalStandard "EMPTY" on bus "R1/electricity" with base_power 0 rating 0 active_power_min 0 active_power_max 0 marginal_cost 25 prime_mover "CT" fuel "NATURAL_GAS"
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/ResidualCapacity.csv" states the values:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | GAS        | 2020 | 100   |
    And the file "decisions.md" contains "EMPTY"
    And the log contains "state no base power"
