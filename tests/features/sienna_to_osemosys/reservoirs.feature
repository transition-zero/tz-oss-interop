@slow @fork_unsafe
Feature: sienna-to-osemosys-csv turns each Sienna reservoir into an OSeMOSYS storage
  A Sienna `HydroReservoir` holds the energy behind a `HydroTurbine`, and the turbine spends
  that energy. OSeMOSYS holds such energy on a member of the `STORAGE` set, and a technology
  that draws on that member states a storage link. So each reservoir becomes one `STORAGE`
  member, and each turbine that the reservoir feeds gains the link that spends it.

  The turbine is already a technology of the generator group, so this group writes no second
  technology for it. The inflow of the reservoir has no Sienna technology behind it, so the
  group writes one charging technology of its own for the inflow.

  Background:
    Given a Sienna system
    And the system contains an area "R1"
    And the system contains a bus "R1/electricity" in area "R1"
    And the system contains a PowerLoad "electricity" on bus "R1/electricity" with max_active_power 100
    And the PowerLoad "electricity" has a max_active_power series 10 20 30 40
    And the system contains a HydroTurbine "DAM_G" on bus "R1/electricity" with base_power 50 rating 50 active_power_min 0 active_power_max 50 marginal_cost 0

  Scenario: a reservoir gives one STORAGE member, and the turbine that it feeds spends it
    The energy of the reservoir is the highest level that it holds, and the turbine draws on
    that energy through a storage link of 1.
    Given the system contains a HydroReservoir "DAM" with max_level 1000 initial_level 600 inflow 0
    And the HydroReservoir "DAM" states "level_data_type" set to "ENERGY"
    And the HydroReservoir "DAM" feeds the HydroTurbine "DAM_G"
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/STORAGE.csv" has 1 rows
    And the otoole CSV file "outputs/model/csv/ResidualStorageCapacity.csv" states the values:
      | REGION | STORAGE | YEAR | VALUE |
      | R1     | DAM     | 2020 | 1000  |
    And the otoole CSV file "outputs/model/csv/TechnologyFromStorage.csv" states the values:
      | REGION | TECHNOLOGY | STORAGE | MODE_OF_OPERATION | VALUE |
      | R1     | DAM_G      | DAM     | 1                 | 1     |
    And the file "decisions.md" contains "ResidualStorageCapacity"

  Scenario: the turbine of the reservoir stays one technology
    The generator group already wrote the turbine, so the reservoir adds no second technology
    for it and the turbine keeps the fleet that its base power states.
    Given the system contains a HydroReservoir "DAM" with max_level 1000 initial_level 600 inflow 0
    And the HydroReservoir "DAM" states "level_data_type" set to "ENERGY"
    And the HydroReservoir "DAM" feeds the HydroTurbine "DAM_G"
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/TECHNOLOGY.csv" has 1 rows
    And the otoole CSV file "outputs/model/csv/ResidualCapacity.csv" states the values:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | DAM_G      | 2020 | 50    |

  Scenario: the level that the reservoir starts at becomes StorageLevelStart
    An energy reservoir states its level in megawatt hours, which is the unit that OSeMOSYS
    states the level of a storage in.
    Given the system contains a HydroReservoir "DAM" with max_level 1000 initial_level 600 inflow 0
    And the HydroReservoir "DAM" states "level_data_type" set to "ENERGY"
    And the HydroReservoir "DAM" feeds the HydroTurbine "DAM_G"
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/StorageLevelStart.csv" states the values:
      | REGION | STORAGE | VALUE |
      | R1     | DAM     | 600   |

  Scenario: the lowest level of the reservoir becomes MinStorageCharge, as a share
    Sienna states the lowest level of an energy reservoir in megawatt hours, and OSeMOSYS
    states it as a share of the energy that the storage holds.
    Given the system contains a HydroReservoir "DAM" with max_level 1000 initial_level 600 inflow 0
    And the HydroReservoir "DAM" states "storage_level_limits" set to {"min": 200, "max": 1000}
    And the HydroReservoir "DAM" states "level_data_type" set to "ENERGY"
    And the HydroReservoir "DAM" feeds the HydroTurbine "DAM_G"
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/MinStorageCharge.csv" states the values:
      | REGION | STORAGE | YEAR | VALUE |
      | R1     | DAM     | 2020 | 0.2   |

  Scenario: a reservoir that may empty gets no MinStorageCharge row
    A lowest level of 0 is the default of the parameter, and OSeMOSYS reads the default where
    a model states no row.
    Given the system contains a HydroReservoir "DAM" with max_level 1000 initial_level 600 inflow 0
    And the HydroReservoir "DAM" states "level_data_type" set to "ENERGY"
    And the HydroReservoir "DAM" feeds the HydroTurbine "DAM_G"
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/STORAGE.csv" has 1 rows
    And the file "outputs/model/csv/MinStorageCharge.csv" does not exist

  Scenario: the inflow of the reservoir becomes a charging technology of its own
    No Sienna component puts the inflow into the reservoir, so the group writes one technology
    that charges the storage and gives it the megawatts of the inflow as its fleet.
    Given the system contains a HydroReservoir "DAM" with max_level 1000 initial_level 600 inflow 20
    And the HydroReservoir "DAM" states "level_data_type" set to "ENERGY"
    And the HydroReservoir "DAM" feeds the HydroTurbine "DAM_G"
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/TECHNOLOGY.csv" has 2 rows
    And the otoole CSV file "outputs/model/csv/TechnologyToStorage.csv" states the values:
      | REGION | TECHNOLOGY | STORAGE | MODE_OF_OPERATION | VALUE |
      | R1     | DAM/inflow | DAM     | 1                 | 1     |
    And the otoole CSV file "outputs/model/csv/ResidualCapacity.csv" states the values:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | DAM_G      | 2020 | 50    |
      | R1     | DAM/inflow | 2020 | 20    |
    And the file "decisions.md" contains "DAM/inflow"

  Scenario: a reservoir of no inflow gets no charging technology
    A reservoir that nothing refills holds the energy that it starts with, so the group writes
    no technology that charges it.
    Given the system contains a HydroReservoir "DAM" with max_level 1000 initial_level 600 inflow 0
    And the HydroReservoir "DAM" states "level_data_type" set to "ENERGY"
    And the HydroReservoir "DAM" feeds the HydroTurbine "DAM_G"
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the file "outputs/model/csv/TechnologyToStorage.csv" does not exist

  Scenario: two turbines of one region both spend the energy of the reservoir
    A reservoir can feed more than one turbine, and each one draws on the same storage.
    Given the system contains a HydroTurbine "DAM_H" on bus "R1/electricity" with base_power 30 rating 30 active_power_min 0 active_power_max 30 marginal_cost 0
    And the system contains a HydroReservoir "DAM" with max_level 1000 initial_level 600 inflow 0
    And the HydroReservoir "DAM" states "level_data_type" set to "ENERGY"
    And the HydroReservoir "DAM" feeds the HydroTurbine "DAM_G"
    And the HydroReservoir "DAM" feeds the HydroTurbine "DAM_H"
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/STORAGE.csv" has 1 rows
    And the otoole CSV file "outputs/model/csv/TechnologyFromStorage.csv" states the values:
      | REGION | TECHNOLOGY | STORAGE | MODE_OF_OPERATION | VALUE |
      | R1     | DAM_G      | DAM     | 1                 | 1     |
      | R1     | DAM_H      | DAM     | 1                 | 1     |

  Scenario: the outflow of the reservoir reaches no table, and is reported
    OSeMOSYS states no outflow that a storage must release, so the leg leaves the value out
    and names it.
    Given the system contains a HydroReservoir "DAM" with max_level 1000 initial_level 600 inflow 0
    And the HydroReservoir "DAM" states "outflow" set to 5
    And the HydroReservoir "DAM" states "level_data_type" set to "ENERGY"
    And the HydroReservoir "DAM" feeds the HydroTurbine "DAM_G"
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/STORAGE.csv" has 1 rows
    And the file "decisions.md" contains "outflow"
    And the log contains "1 reservoir(s) state an outflow that OSeMOSYS has no home for"

  Scenario: a reservoir whose levels are not energy is left out
    A level in cubic metres or in metres of head becomes megawatt hours only through the head
    curve of the reservoir and the conversion factor of its turbine, which OSeMOSYS holds
    neither of.
    Given the system contains a HydroReservoir "DAM" with max_level 1000 initial_level 600 inflow 0
    And the HydroReservoir "DAM" feeds the HydroTurbine "DAM_G"
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the file "outputs/model/csv/STORAGE.csv" does not exist
    And the file "decisions.md" contains "DAM"
    And the log contains "1 reservoir(s) state a level that is not energy"

  Scenario: a reservoir that no turbine draws on is left out
    OSeMOSYS keys a storage by its region, and the bus of a turbine of the reservoir is what
    states that region, so a reservoir that feeds no turbine has no region and nothing that
    spends its energy.
    Given the system contains a HydroReservoir "DAM" with max_level 1000 initial_level 600 inflow 0
    And the HydroReservoir "DAM" states "level_data_type" set to "ENERGY"
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the file "outputs/model/csv/STORAGE.csv" does not exist
    And the log contains "1 reservoir(s) feed no HydroTurbine that reached a technology"

  Scenario: a reservoir that holds no energy is left out
    OSeMOSYS states the lowest level of a storage as a share of the energy that it holds, so a
    reservoir of no energy gives a share that divides by zero.
    Given the system contains a HydroReservoir "DAM" with max_level 0 initial_level 0 inflow 0
    And the HydroReservoir "DAM" states "level_data_type" set to "ENERGY"
    And the HydroReservoir "DAM" feeds the HydroTurbine "DAM_G"
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the file "outputs/model/csv/STORAGE.csv" does not exist
    And the log contains "1 reservoir(s) hold no energy"

  Scenario: a reservoir whose turbines sit in more than one region is left out
    OSeMOSYS keys a storage by one region, so a reservoir whose turbines name two regions has
    no one region to hold its energy in.
    Given the system contains an area "R2"
    And the system contains a bus "R2/electricity" in area "R2"
    And the system contains a HydroTurbine "DAM_H" on bus "R2/electricity" with base_power 30 rating 30 active_power_min 0 active_power_max 30 marginal_cost 0
    And the system contains a HydroReservoir "DAM" with max_level 1000 initial_level 600 inflow 0
    And the HydroReservoir "DAM" states "level_data_type" set to "ENERGY"
    And the HydroReservoir "DAM" feeds the HydroTurbine "DAM_G"
    And the HydroReservoir "DAM" feeds the HydroTurbine "DAM_H"
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the file "outputs/model/csv/STORAGE.csv" does not exist
    And the log contains "1 reservoir(s) feed turbines of more than one region"
