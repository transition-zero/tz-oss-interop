@slow @fork_unsafe
Feature: sienna-to-osemosys-csv prices each OSeMOSYS technology and bounds its activity
  A Sienna generator states what one megawatt hour of its electricity costs, and its record
  states what one megawatt of its capacity costs to build and to keep. OSeMOSYS states the
  first as `VariableCost` of the mode that the generator runs and the other two as
  `CapitalCost` and `FixedCost` of the technology.

  A plant that draws its fuel from a bus pays for that fuel at the bus, so its own cost and
  its own emission rates are the ones without the fuel. Each other mode of the technology
  states its own cost, its own emission rates and its own bounds in the `extensions.json`
  sidecar.

  Background:
    Given a Sienna system
    And the system contains an area "R1"
    And the system contains a bus "R1/electricity" in area "R1"
    And the system contains a PowerLoad "electricity" on bus "R1/electricity" with max_active_power 100
    And the PowerLoad "electricity" has a max_active_power series 10 20 30 40

  Scenario: a generator states its variable cost, its fixed cost, its capital cost and its life
    The variable cost of a Sienna generator is the proportional term of its cost curve, in
    dollars for each megawatt hour, and the three other values travel in its record.
    Given the system contains a ThermalStandard "GAS" on bus "R1/electricity" with base_power 100 rating 100 active_power_min 0 active_power_max 100 marginal_cost 25 prime_mover "CT" fuel "NATURAL_GAS"
    And the ThermalStandard "GAS" has ext "fom_charge_per_mw_year" set to 1000.0
    And the ThermalStandard "GAS" has ext "overnight_cost_per_mw" set to 500000.0
    And the ThermalStandard "GAS" has ext "lifetime_years" set to 30.0
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/VariableCost.csv" states the values:
      | REGION | TECHNOLOGY | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | GAS        | 1                 | 2020 | 25    |
    And the otoole CSV file "outputs/model/csv/FixedCost.csv" states the values:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | GAS        | 2020 | 1000  |
    And the otoole CSV file "outputs/model/csv/CapitalCost.csv" states the values:
      | REGION | TECHNOLOGY | YEAR | VALUE  |
      | R1     | GAS        | 2020 | 500000 |
    And the otoole CSV file "outputs/model/csv/OperationalLife.csv" states the values:
      | REGION | TECHNOLOGY | VALUE |
      | R1     | GAS        | 30    |
    And the file "decisions.md" contains "VariableCost"

  Scenario: a plant that draws its fuel from a bus states the cost without the fuel
    A Sienna cost curve holds the price of the fuel, because Sienna prices no fuel of its
    own. A written model prices the fuel at the technology that supplies it, so the cost of
    the plant is the `own_marginal_cost` of its record.
    Given the system contains a ThermalStandard "GAS" on bus "R1/electricity" with base_power 100 rating 100 active_power_min 0 active_power_max 100 marginal_cost 40 prime_mover "CT" fuel "NATURAL_GAS"
    And the ThermalStandard "GAS" has ext "fuel_buses" set to {"R1/gas": 2.0}
    And the ThermalStandard "GAS" has ext "own_marginal_cost" set to 5.0
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/VariableCost.csv" states the values:
      | REGION | TECHNOLOGY | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | GAS        | 1                 | 2020 | 5     |

  Scenario: a generator states one emission rate for each pollutant
    OSeMOSYS states the tonnes of a pollutant that one megawatt hour of the activity of a
    mode gives, so each pollutant of the record gives one `EmissionActivityRatio` row.
    Given the system contains a ThermalStandard "GAS" on bus "R1/electricity" with base_power 100 rating 100 active_power_min 0 active_power_max 100 marginal_cost 25 prime_mover "CT" fuel "NATURAL_GAS"
    And the ThermalStandard "GAS" has ext "emission_rates_t_per_mwh" set to {"CO2": 0.4, "NOX": 0.001}
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/EmissionActivityRatio.csv" states the values:
      | REGION | TECHNOLOGY | EMISSION | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | GAS        | CO2      | 1                 | 2020 | 0.4   |
      | R1     | GAS        | NOX      | 1                 | 2020 | 0.001 |
    And the otoole CSV file "outputs/model/csv/EMISSION.csv" has 2 rows

  Scenario: a plant that draws its fuel from a bus states the emission rates without the fuel
    The emission rates of a Sienna generator hold what the producer of its fuel emits. A
    written model emits that at the technology that supplies the fuel, so the rates of the
    plant are the `own_emission_rates_t_per_mwh` of its record.
    Given the system contains a ThermalStandard "GAS" on bus "R1/electricity" with base_power 100 rating 100 active_power_min 0 active_power_max 100 marginal_cost 40 prime_mover "CT" fuel "NATURAL_GAS"
    And the ThermalStandard "GAS" has ext "fuel_buses" set to {"R1/gas": 2.0}
    And the ThermalStandard "GAS" has ext "emission_rates_t_per_mwh" set to {"CO2": 0.6}
    And the ThermalStandard "GAS" has ext "own_emission_rates_t_per_mwh" set to {"CO2": 0.4}
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/EmissionActivityRatio.csv" states the values:
      | REGION | TECHNOLOGY | EMISSION | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | GAS        | CO2      | 1                 | 2020 | 0.4   |

  Scenario: each mode takes its cost and its emission rates from its own record
    A Sienna generator runs one mode, so the cost and the rates of each other mode of its
    technology come from the `operating_modes` entry of that mode.
    Given the system contains a ThermalStandard "GAS" on bus "R1/electricity" with base_power 100 rating 100 active_power_min 0 active_power_max 100 marginal_cost 25 prime_mover "CT" fuel "NATURAL_GAS"
    And the ThermalStandard "GAS" has ext "operating_modes" set to [{"mode": "2", "variable_cost": 10.0, "input_ratios": {"gas": 3.0}, "output_ratios": {"electricity": 1.0}, "emission_rates": {"CO2": 0.2}}, {"mode": "3", "variable_cost": 20.0, "input_ratios": {"oil": 4.0}, "output_ratios": {"electricity": 1.0}, "emission_rates": {"CO2": 0.5}}]
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/VariableCost.csv" states the values:
      | REGION | TECHNOLOGY | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | GAS        | 1                 | 2020 | 25    |
      | R1     | GAS        | 2                 | 2020 | 10    |
      | R1     | GAS        | 3                 | 2020 | 20    |
    And the otoole CSV file "outputs/model/csv/EmissionActivityRatio.csv" states the values:
      | REGION | TECHNOLOGY | EMISSION | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | GAS        | CO2      | 2                 | 2020 | 0.2   |
      | R1     | GAS        | CO2      | 3                 | 2020 | 0.5   |

  Scenario: the annual activity limits of a generator hold in each year that names one
    A record states a limit on the energy of a year for each year that binds, and OSeMOSYS
    states one row for each of those years.
    Given the system contains a ThermalStandard "GAS" on bus "R1/electricity" with base_power 100 rating 100 active_power_min 0 active_power_max 100 marginal_cost 25 prime_mover "CT" fuel "NATURAL_GAS"
    And the ThermalStandard "GAS" has ext "e_sum_max" set to {"2030": 500000.0, "2035": 400000.0}
    And the ThermalStandard "GAS" has ext "e_sum_min" set to {"2030": 1000.0}
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/TotalTechnologyAnnualActivityUpperLimit.csv" states the values:
      | REGION | TECHNOLOGY | YEAR | VALUE  |
      | R1     | GAS        | 2030 | 500000 |
      | R1     | GAS        | 2035 | 400000 |
    And the otoole CSV file "outputs/model/csv/TotalTechnologyAnnualActivityLowerLimit.csv" states the values:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | GAS        | 2030 | 1000  |

  Scenario: the model period activity limits of a generator hold over the whole model
    A limit over the model period states one number for the whole run, so OSeMOSYS keys it by
    the region and the technology alone.
    Given the system contains a ThermalStandard "GAS" on bus "R1/electricity" with base_power 100 rating 100 active_power_min 0 active_power_max 100 marginal_cost 25 prime_mover "CT" fuel "NATURAL_GAS"
    And the ThermalStandard "GAS" has ext "e_sum_max_horizon" set to 900000.0
    And the ThermalStandard "GAS" has ext "e_sum_min_horizon" set to 2000.0
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/TotalTechnologyModelPeriodActivityUpperLimit.csv" states the values:
      | REGION | TECHNOLOGY | VALUE  |
      | R1     | GAS        | 900000 |
    And the otoole CSV file "outputs/model/csv/TotalTechnologyModelPeriodActivityLowerLimit.csv" states the values:
      | REGION | TECHNOLOGY | VALUE |
      | R1     | GAS        | 2000  |

  Scenario: a bound on one mode reaches the model only when the run asks for every parameter
    A bound on the activity of one mode is no parameter of core OSeMOSYS v1.0.1, so the
    default run leaves its file out and names the parameter.
    Given the system contains a ThermalStandard "GAS" on bus "R1/electricity" with base_power 100 rating 100 active_power_min 0 active_power_max 100 marginal_cost 25 prime_mover "CT" fuel "NATURAL_GAS"
    And the ThermalStandard "GAS" has ext "operating_modes" set to [{"mode": "2", "activity_max": {"2020": 100.0}, "input_ratios": {"gas": 3.0}, "output_ratios": {"electricity": 1.0}}]
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the file "outputs/model/csv/TechnologyActivityByModeUpperLimit.csv" does not exist
    And the log contains "TechnologyActivityByModeUpperLimit (OSeMOSYS MUIO model v5.7)"

  Scenario: a bound on one mode is written when the run asks for every parameter
    A run that asks for every parameter writes the bound of the mode that the record states.
    Given the system contains a ThermalStandard "GAS" on bus "R1/electricity" with base_power 100 rating 100 active_power_min 0 active_power_max 100 marginal_cost 25 prime_mover "CT" fuel "NATURAL_GAS"
    And the ThermalStandard "GAS" has ext "operating_modes" set to [{"mode": "2", "activity_max": {"2020": 100.0}, "input_ratios": {"gas": 3.0}, "output_ratios": {"electricity": 1.0}}]
    When I write the Sienna system out as an otoole model in "outputs/model" with every parameter
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/TechnologyActivityByModeUpperLimit.csv" states the values:
      | REGION | TECHNOLOGY | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | GAS        | 2                 | 2020 | 100   |

  Scenario: a value that equals the default of its parameter gets no row
    OSeMOSYS reads the default of a parameter where the model states no row, so a generator
    that costs 0 to run needs no `VariableCost` row. A `RenewableNonDispatch` states no cost
    curve at all and needs none either.
    Given the system contains a ThermalStandard "GAS" on bus "R1/electricity" with base_power 100 rating 100 active_power_min 0 active_power_max 100 marginal_cost 25 prime_mover "CT" fuel "NATURAL_GAS"
    And the system contains a ThermalStandard "FREE" on bus "R1/electricity" with base_power 50 rating 50 active_power_min 0 active_power_max 50 marginal_cost 0 prime_mover "CT" fuel "NATURAL_GAS"
    And the system contains a RenewableNonDispatch "SOLAR" on bus "R1/electricity" with base_power 20 rating 20 active_power 0 prime_mover "PVe"
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/VariableCost.csv" states the values:
      | REGION | TECHNOLOGY | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | GAS        | 1                 | 2020 | 25    |
    And the otoole CSV file "outputs/model/csv/TECHNOLOGY.csv" has 3 rows
