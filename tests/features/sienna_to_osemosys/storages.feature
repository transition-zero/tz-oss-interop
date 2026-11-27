@slow @fork_unsafe
Feature: sienna-to-osemosys-csv turns each Sienna storage into an OSeMOSYS storage
  A Sienna `EnergyReservoirStorage` holds its energy, its power and its two efficiencies on
  one component. OSeMOSYS holds the energy on a member of the `STORAGE` set, and it gives that
  member its power through one technology that charges it and one technology that discharges
  it. So the leg writes one storage and the two technologies that it needs.

  The forward leg merged the activity ratio of each technology with the storage link of that
  technology into one efficiency, so this leg writes each link as 1 and the whole efficiency
  as the activity ratio.

  Background:
    Given a Sienna system
    And the system contains an area "R1"
    And the system contains a bus "R1/electricity" in area "R1"
    And the system contains a PowerLoad "electricity" on bus "R1/electricity" with max_active_power 100
    And the PowerLoad "electricity" has a max_active_power series 10 20 30 40

  Scenario: a storage gives one STORAGE member and the two technologies that move its energy
    The energy of the storage is its `storage_capacity` in hours times its base power, and the
    two technologies take the name of the storage with `/charge` and `/discharge` after it.
    Given the system contains an EnergyReservoirStorage "PHS" on bus "R1/electricity" with base_power 100 storage_capacity 4 initial_level 0.5 rating 1 input_max 1 output_max 1 efficiency_in 0.9 efficiency_out 0.95 discharge_cost 0
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/STORAGE.csv" has 1 rows
    And the otoole CSV file "outputs/model/csv/TECHNOLOGY.csv" has 2 rows
    And the otoole CSV file "outputs/model/csv/TechnologyToStorage.csv" states the values:
      | REGION | TECHNOLOGY | STORAGE | MODE_OF_OPERATION | VALUE |
      | R1     | PHS/charge | PHS     | 1                 | 1     |
    And the otoole CSV file "outputs/model/csv/TechnologyFromStorage.csv" states the values:
      | REGION | TECHNOLOGY    | STORAGE | MODE_OF_OPERATION | VALUE |
      | R1     | PHS/discharge | PHS     | 1                 | 1     |
    And the otoole CSV file "outputs/model/csv/ResidualStorageCapacity.csv" states the values:
      | REGION | STORAGE | YEAR | VALUE |
      | R1     | PHS     | 2020 | 400   |
    And the file "decisions.md" contains "ResidualStorageCapacity"

  Scenario: each efficiency is written as the activity ratio of its own technology
    `efficiency.in` is the megawatt hours stored for each megawatt hour drawn from the bus, so
    the charging technology takes in its reciprocal. `efficiency.out` is the megawatt hours
    sent to the bus for each megawatt hour drawn from the storage.
    Given the system contains an EnergyReservoirStorage "PHS" on bus "R1/electricity" with base_power 100 storage_capacity 4 initial_level 0.5 rating 1 input_max 1 output_max 1 efficiency_in 0.8 efficiency_out 0.5 discharge_cost 0
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/InputActivityRatio.csv" states the values:
      | REGION | TECHNOLOGY | FUEL        | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | PHS/charge | electricity | 1                 | 2020 | 1.25  |
    And the otoole CSV file "outputs/model/csv/OutputActivityRatio.csv" states the values:
      | REGION | TECHNOLOGY    | FUEL        | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | PHS/discharge | electricity | 1                 | 2020 | 0.5   |

  Scenario: each power limit gives the fleet of its own technology
    A Sienna power limit is a share of the base power of the storage, and OSeMOSYS states the
    fleet of a technology in the unit of its activity, which is a megawatt hour of the energy
    of the storage.
    Given the system contains an EnergyReservoirStorage "PHS" on bus "R1/electricity" with base_power 100 storage_capacity 4 initial_level 0.5 rating 1 input_max 0.6 output_max 0.8 efficiency_in 0.8 efficiency_out 0.5 discharge_cost 0
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/ResidualCapacity.csv" states the values:
      | REGION | TECHNOLOGY    | YEAR | VALUE |
      | R1     | PHS/charge    | 2020 | 48    |
      | R1     | PHS/discharge | 2020 | 160   |

  Scenario: the level that the storage starts at becomes StorageLevelStart
    Sienna states the level as a share of the energy of the storage, and OSeMOSYS states it as
    the megawatt hours in the storage at the start of the model period.
    Given the system contains an EnergyReservoirStorage "PHS" on bus "R1/electricity" with base_power 100 storage_capacity 4 initial_level 0.25 rating 1 input_max 1 output_max 1 efficiency_in 0.9 efficiency_out 0.95 discharge_cost 0
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/StorageLevelStart.csv" states the values:
      | REGION | STORAGE | VALUE |
      | R1     | PHS     | 100   |

  Scenario: the lowest level of the storage becomes MinStorageCharge
    Sienna holds the lowest level as a share of the energy of the storage, which is the share
    that OSeMOSYS states.
    Given the system contains an EnergyReservoirStorage "PHS" on bus "R1/electricity" with base_power 100 storage_capacity 4 initial_level 0.5 rating 1 input_max 1 output_max 1 efficiency_in 0.9 efficiency_out 0.95 discharge_cost 0
    And the EnergyReservoirStorage "PHS" states "storage_level_limits" set to {"min": 0.2, "max": 1.0}
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/MinStorageCharge.csv" states the values:
      | REGION | STORAGE | YEAR | VALUE |
      | R1     | PHS     | 2020 | 0.2   |

  Scenario: a lowest level of 0 is the default of the parameter, so it gets no row
    OSeMOSYS reads the default where a model states no row, so a storage that may empty writes
    no `MinStorageCharge` row.
    Given the system contains an EnergyReservoirStorage "PHS" on bus "R1/electricity" with base_power 100 storage_capacity 4 initial_level 0.5 rating 1 input_max 1 output_max 1 efficiency_in 0.9 efficiency_out 0.95 discharge_cost 0
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/STORAGE.csv" has 1 rows
    And the file "outputs/model/csv/MinStorageCharge.csv" does not exist

  Scenario: the build cost and the life of the storage come from its record
    OSeMOSYS prices the energy of a storage and not its power, and no Sienna field holds that
    price, so the `storage` record of the sidecar carries both values.
    Given the system contains an EnergyReservoirStorage "PHS" on bus "R1/electricity" with base_power 100 storage_capacity 4 initial_level 0.5 rating 1 input_max 1 output_max 1 efficiency_in 0.9 efficiency_out 0.95 discharge_cost 0
    And the EnergyReservoirStorage "PHS" has ext "energy_overnight_cost" set to 50000.0
    And the EnergyReservoirStorage "PHS" has ext "lifetime_years" set to 30.0
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/CapitalCostStorage.csv" states the values:
      | REGION | STORAGE | YEAR | VALUE |
      | R1     | PHS     | 2020 | 50000 |
    And the otoole CSV file "outputs/model/csv/OperationalLifeStorage.csv" states the values:
      | REGION | STORAGE | VALUE |
      | R1     | PHS     | 30    |

  Scenario: a storage with no record keeps its ratings, and each absent field is reported
    The record holds the two values that no Sienna field states, so a system with no record
    still gives the storage and reports what the written model takes the default for.
    Given the system contains an EnergyReservoirStorage "PHS" on bus "R1/electricity" with base_power 100 storage_capacity 4 initial_level 0.5 rating 1 input_max 1 output_max 1 efficiency_in 0.9 efficiency_out 0.95 discharge_cost 0
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/ResidualStorageCapacity.csv" states the values:
      | REGION | STORAGE | YEAR | VALUE |
      | R1     | PHS     | 2020 | 400   |
    And the file "outputs/model/csv/CapitalCostStorage.csv" does not exist
    And the file "outputs/model/csv/OperationalLifeStorage.csv" does not exist
    And the file "decisions.md" contains "extensions.energy_overnight_cost"
    And the file "decisions.md" contains "extensions.lifetime_years"

  Scenario: a storage whose power basis this reader does not read is left out
    The power limits of a storage are a share of its base power, so a storage on another power
    basis states its limits in megawatts and reading them as shares would write a number
    nobody meant.
    Given the system contains an EnergyReservoirStorage "PHS" on bus "R1/electricity" with base_power 100 storage_capacity 4 initial_level 0.5 rating 1 input_max 1 output_max 1 efficiency_in 0.9 efficiency_out 0.95 discharge_cost 0
    And the EnergyReservoirStorage "PHS" states "power_units" set to "NATURAL_UNITS"
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the file "outputs/model/csv/STORAGE.csv" does not exist
    And the file "decisions.md" contains "PHS"
    And the log contains "1 storage(s) state a power basis this reader does not read"

  Scenario: a storage that holds no energy is left out
    OSeMOSYS states the level of a storage as a share of its energy, so a storage of no energy
    gives a share that is a division by zero.
    Given the system contains an EnergyReservoirStorage "PHS" on bus "R1/electricity" with base_power 100 storage_capacity 0 initial_level 0 rating 1 input_max 1 output_max 1 efficiency_in 0.9 efficiency_out 0.95 discharge_cost 0
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the file "outputs/model/csv/STORAGE.csv" does not exist
    And the log contains "1 storage(s) hold no energy"

  Scenario: a storage whose efficiency is 0 is left out
    Each efficiency becomes the activity ratio of one technology, and an efficiency of 0 gives
    a ratio that is a division by zero.
    Given the system contains an EnergyReservoirStorage "PHS" on bus "R1/electricity" with base_power 100 storage_capacity 4 initial_level 0.5 rating 1 input_max 1 output_max 1 efficiency_in 0.9 efficiency_out 0 discharge_cost 0
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the file "outputs/model/csv/STORAGE.csv" does not exist
    And the log contains "1 storage(s) state an efficiency of 0"

  Scenario: a storage and a generator both reach the written model
    A storage adds two technologies of its own, so the technology set holds the generator of
    the system and both of them.
    Given the system contains a ThermalStandard "GAS" on bus "R1/electricity" with base_power 100 rating 100 active_power_min 0 active_power_max 100 marginal_cost 25 prime_mover "CT" fuel "NATURAL_GAS"
    And the system contains an EnergyReservoirStorage "PHS" on bus "R1/electricity" with base_power 100 storage_capacity 4 initial_level 0.5 rating 1 input_max 1 output_max 1 efficiency_in 0.9 efficiency_out 0.95 discharge_cost 0
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/TECHNOLOGY.csv" has 3 rows
    And the otoole CSV file "outputs/model/csv/FUEL.csv" has 1 rows
    And the otoole CSV file "outputs/model/csv/ResidualCapacity.csv" states the values:
      | REGION | TECHNOLOGY    | YEAR | VALUE             |
      | R1     | GAS           | 2020 | 100               |
      | R1     | PHS/charge    | 2020 | 90                |
      | R1     | PHS/discharge | 2020 | 105.2631578947368 |
    And the otoole CSV file "outputs/model/csv/OutputActivityRatio.csv" states the values:
      | REGION | TECHNOLOGY    | FUEL        | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | GAS           | electricity | 1                 | 2020 | 1     |
      | R1     | PHS/discharge | electricity | 1                 | 2020 | 0.95  |
