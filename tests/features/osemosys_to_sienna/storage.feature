@slow @fork_unsafe
Feature: osemosys-csv-to-sienna turns the storages of one model year into Sienna storage
  The operations step reads the canonical stage of an otoole model for one year. A storage with
  energy becomes an EnergyReservoirStorage. The technology that discharges it gives its bus and
  its base power, and the technology that charges it gives the most power that it can draw.

  The invented model below has two electricity fuels at the locations AT and DE. Two seasons
  and one day type give two days. Each day has a bracket of 6 h and a bracket of 18 h.

  Background:
    Given an otoole model
    And the otoole set "REGION" holds "R1"
    And the otoole set "FUEL" holds "ATELEC DEELEC GAS"
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
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                                                              |
      | osemosys: {units: {energy: GWh}, objects: {fuels: [{match: "^(?P<country>[A-Z]{2})ELEC$", carrier: electricity, location: "{country}"}]}} |

  Rule: A storage with energy becomes an EnergyReservoirStorage that the technology linked to it rates
    The invented storages below are at AT. The pumped-storage plant ATPHS charges the storage
    ATPHSS in mode 1 and discharges it in mode 2. It takes in 1.25 units of electricity for each
    unit of its activity when it charges, and puts 0.9 of a unit into the storage. It puts out
    0.8 when it discharges. Each other storage is left out for one reason:

    - ATBATS has no residual storage capacity in 2030.
    - ATFLYS has a discharging technology whose category no carriers: row names.
    - ATLONES has no technology that charges or discharges it.
    - ATTWOS has two technologies that charge it.
    - ATIDLES has a discharging technology with no residual capacity.
    - ATSUNS has a discharging technology whose carriers: row names a generator.
    - HTHEATS has a discharging technology that puts out an electricity fuel with no location.
    - ATNOOUTS has a discharging technology that puts out no electricity.
    - ATNOINS has a charging technology that takes in no electricity.

    Background:
      Given the otoole set "FUEL" holds "ATELEC DEELEC ATWATER HTHEATF"
      And the otoole set "TECHNOLOGY" holds "ATPHS ATBATT ATFLY ATIDLE ATSUN HTHEAT ATNOOUT ATNOIN"
      And the otoole set "STORAGE" holds "ATPHSS ATBATS ATFLYS ATLONES ATTWOS ATIDLES ATSUNS HTHEATS ATNOOUTS ATNOINS"
      And the otoole set "MODE_OF_OPERATION" holds "1 2"
      And the otoole parameter "ResidualCapacity" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATPHS      | 2030 | 0.1   |
        | R1     | ATBATT     | 2030 | 0.05  |
        | R1     | ATFLY      | 2030 | 0.01  |
        | R1     | ATSUN      | 2030 | 0.01  |
        | R1     | HTHEAT     | 2030 | 0.01  |
        | R1     | ATNOOUT    | 2030 | 0.01  |
        | R1     | ATNOIN     | 2030 | 0.01  |
      And the otoole parameter "InputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | FUEL    | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATPHS      | ATELEC  | 1                 | 2030 | 1.25  |
        | R1     | ATBATT     | ATELEC  | 1                 | 2030 | 1     |
        | R1     | ATFLY      | ATELEC  | 1                 | 2030 | 1     |
        | R1     | ATIDLE     | ATELEC  | 1                 | 2030 | 1     |
        | R1     | ATSUN      | ATELEC  | 1                 | 2030 | 1     |
        | R1     | HTHEAT     | HTHEATF | 1                 | 2030 | 1     |
        | R1     | ATNOOUT    | ATELEC  | 1                 | 2030 | 1     |
        | R1     | ATNOIN     | ATWATER | 1                 | 2030 | 1     |
      And the otoole parameter "OutputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | FUEL    | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATPHS      | ATWATER | 1                 | 2030 | 1     |
        | R1     | ATPHS      | ATELEC  | 2                 | 2030 | 0.8   |
        | R1     | ATBATT     | ATELEC  | 2                 | 2030 | 0.9   |
        | R1     | ATFLY      | ATELEC  | 2                 | 2030 | 0.9   |
        | R1     | ATIDLE     | ATELEC  | 2                 | 2030 | 0.9   |
        | R1     | ATSUN      | ATELEC  | 2                 | 2030 | 0.9   |
        | R1     | HTHEAT     | HTHEATF | 2                 | 2030 | 0.9   |
        | R1     | ATNOOUT    | ATWATER | 2                 | 2030 | 0.9   |
        | R1     | ATNOIN     | ATELEC  | 2                 | 2030 | 0.9   |
      And the otoole parameter "TechnologyToStorage" keyed by "REGION TECHNOLOGY STORAGE MODE_OF_OPERATION" with default 0 has the rows:
        | REGION | TECHNOLOGY | STORAGE  | MODE_OF_OPERATION | VALUE |
        | R1     | ATPHS      | ATPHSS   | 1                 | 0.9   |
        | R1     | ATBATT     | ATBATS   | 1                 | 1     |
        | R1     | ATFLY      | ATFLYS   | 1                 | 1     |
        | R1     | ATPHS      | ATTWOS   | 1                 | 1     |
        | R1     | ATBATT     | ATTWOS   | 1                 | 1     |
        | R1     | ATIDLE     | ATIDLES  | 1                 | 1     |
        | R1     | ATSUN      | ATSUNS   | 1                 | 1     |
        | R1     | HTHEAT     | HTHEATS  | 1                 | 1     |
        | R1     | ATNOOUT    | ATNOOUTS | 1                 | 1     |
        | R1     | ATNOIN     | ATNOINS  | 1                 | 1     |
      And the otoole parameter "TechnologyFromStorage" keyed by "REGION TECHNOLOGY STORAGE MODE_OF_OPERATION" with default 0 has the rows:
        | REGION | TECHNOLOGY | STORAGE  | MODE_OF_OPERATION | VALUE |
        | R1     | ATPHS      | ATPHSS   | 2                 | 1     |
        | R1     | ATBATT     | ATBATS   | 2                 | 1     |
        | R1     | ATFLY      | ATFLYS   | 2                 | 1     |
        | R1     | ATPHS      | ATTWOS   | 2                 | 1     |
        | R1     | ATIDLE     | ATIDLES  | 2                 | 1     |
        | R1     | ATSUN      | ATSUNS   | 2                 | 1     |
        | R1     | HTHEAT     | HTHEATS  | 2                 | 1     |
        | R1     | ATNOOUT    | ATNOOUTS | 2                 | 1     |
        | R1     | ATNOIN     | ATNOINS  | 2                 | 1     |
      And the otoole parameter "ResidualStorageCapacity" keyed by "REGION STORAGE YEAR" with default 0 has the rows:
        | REGION | STORAGE  | YEAR | VALUE |
        | R1     | ATPHSS   | 2030 | 0.8   |
        | R1     | ATFLYS   | 2030 | 0.01  |
        | R1     | ATLONES  | 2030 | 0.5   |
        | R1     | ATTWOS   | 2030 | 0.01  |
        | R1     | ATIDLES  | 2030 | 0.01  |
        | R1     | ATSUNS   | 2030 | 0.01  |
        | R1     | HTHEATS  | 2030 | 0.01  |
        | R1     | ATNOOUTS | 2030 | 0.01  |
        | R1     | ATNOINS  | 2030 | 0.01  |
      And the otoole parameter "StorageLevelStart" keyed by "REGION STORAGE" with default 0 has the rows:
        | REGION | STORAGE | VALUE |
        | R1     | ATPHSS  | 0.2   |
      And the otoole parameter "MinStorageCharge" keyed by "REGION STORAGE YEAR" with default 0 has the rows:
        | REGION | STORAGE | YEAR | VALUE |
        | R1     | ATPHSS  | 2030 | 0.125 |
      And the otoole parameter "VariableCost" keyed by "REGION TECHNOLOGY MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATPHS      | 1                 | 2030 | 500   |
        | R1     | ATPHS      | 2                 | 2030 | 2000  |
      And a file "user_mappings.yaml" containing the lines:
        | line                                                                                                       |
        | osemosys: {                                                                                                |
        | units: {capacity: GW, energy: GWh, currency: USD},                                                         |
        | objects: {                                                                                                 |
        | fuels: [{match: "^(?P<country>[A-Z]{2})ELEC$", carrier: electricity, location: "{country}"},               |
        | {match: "^ATWATER$", carrier: water, location: AT},                                                        |
        | {match: "^(?P<country>[A-Z]{2})?HTHEATF$", carrier: electricity, location: "{country}"}],                 |
        | technologies: [{match: "PHS$", category: pumped-storage}, {match: "BATT$", category: battery},             |
        | {match: "IDLE$", category: battery}, {match: "HEAT$", category: battery},                                  |
        | {match: "NOOUT$", category: battery}, {match: "NOIN$", category: battery},                                 |
        | {match: "FLY$", category: flywheel}, {match: "SUN$", category: solar}]}}                                   |
        | carriers: [                                                                                                |
        | {osemosys_category: pumped-storage, sienna_component_type: EnergyReservoirStorage, sienna_prime_mover_type: PS}, |
        | {osemosys_category: battery, sienna_component_type: EnergyReservoirStorage, sienna_prime_mover_type: BA},  |
        | {osemosys_category: solar, sienna_component_type: RenewableDispatch, sienna_prime_mover_type: PVe}]        |

    Scenario: A pumped-storage plant becomes an EnergyReservoirStorage rated for its electricity
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/system.json" parses as JSON with 1 component of type "EnergyReservoirStorage"
      And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "ATPHSS" having "base_power" set to 80.0
      And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "ATPHSS" having "bus" set to 1
      And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "ATPHSS" having "prime_mover_type" set to "PS"
      And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "ATPHSS" having "storage_capacity" set to 10.0
      And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "ATPHSS" having "efficiency.in" set to 0.72
      And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "ATPHSS" having "efficiency.out" set to 0.8
      And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "ATPHSS" having "input_active_power_limits.max" set to 1.5625
      And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "ATPHSS" having "output_active_power_limits.max" set to 1.0
      And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "ATPHSS" having "initial_storage_capacity_level" set to 0.25
      And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "ATPHSS" having "storage_level_limits.min" set to 0.125
      And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "ATPHSS" having "operation_cost.charge_variable_cost.value_curve.function_data.proportional_term" set to 0.4
      And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "ATPHSS" having "operation_cost.discharge_variable_cost.value_curve.function_data.proportional_term" set to 2.5
      And the file "decisions.md" contains "in = technology_to_storage / the electricity input_activity_ratio at the charge mode"
      And the file "decisions.md" contains "`osemosys.technology_to_storage.R1/ATPHS.ATPHSS` = 0.9"
      And the file "outputs/extensions.json" parses as JSON storage extension record for "ATPHSS" having "carrier" set to "pumped-storage"
      And the file "decisions.md" contains "| `osemosys.technology.R1/ATPHS.category` = pumped-storage | `sienna.EnergyReservoirStorage.ATPHSS.extensions.carrier` = pumped-storage | the category of the discharging technology, which names its carriers: row |"

    Scenario: The availability, the charge and discharge rates and the fixed cost of a storage are applied
      Given the otoole parameter "AvailabilityFactor" keyed by "REGION TECHNOLOGY YEAR" with default 1 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATPHS      | 2030 | 0.5   |
      And the otoole parameter "StorageMaxChargeRate" keyed by "REGION STORAGE" with default 0 has the rows:
        | REGION | STORAGE | VALUE |
        | R1     | ATPHSS  | 438   |
      And the otoole parameter "StorageMaxDischargeRate" keyed by "REGION STORAGE" with default 0 has the rows:
        | REGION | STORAGE | VALUE |
        | R1     | ATPHSS  | 175.2 |
      And the otoole parameter "FixedCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATPHS      | 2030 | 40000 |
      And the otoole parameter "CapacityFactor" keyed by "REGION TECHNOLOGY TIMESLICE YEAR" with default 1 has the rows:
        | REGION | TECHNOLOGY | TIMESLICE | YEAR | VALUE |
        | R1     | ATPHS      | S1B1      | 2030 | 0.5   |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "ATPHSS" having "input_active_power_limits.max" set to 0.78125
      And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "ATPHSS" having "output_active_power_limits.max" set to 0.2
      And the file "outputs/extensions.json" parses as JSON storage extension record for "ATPHSS" having "fom_charge_per_mw_year" set to 50.0
      And the file "outputs/extensions.json" parses as JSON storage extension record for "ATPHSS" having "rating_series" set to "storage.parquet"
      And the parquet file "outputs/storage.parquet" has 48 rows
      And the parquet file "outputs/storage.parquet" has columns "snapshot, name, rating_pu"
      And the file "decisions.md" contains "`osemosys.capacity_factor.R1/ATPHS.each timeslice` | `sienna.EnergyReservoirStorage.ATPHSS.extensions.rating_series` = storage.parquet"

    Scenario: The values of a storage that Sienna has no field for reach extensions.json under the PyPSA names
      The power of the storage costs 1 $/MW of activity of ATPHS, which puts out 0.8 MW of
      electricity, so 1.25 $/MW. Its energy costs 50 USD for each GWh, so 0.05 $/MWh.
      Given the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATPHS      | 2030 | 1000  |
      And the otoole parameter "CapitalCostStorage" keyed by "REGION STORAGE YEAR" with default 0 has the rows:
        | REGION | STORAGE | YEAR | VALUE |
        | R1     | ATPHSS  | 2030 | 50    |
      And the otoole parameter "OperationalLifeStorage" keyed by "REGION STORAGE" with default 0 has the rows:
        | REGION | STORAGE | VALUE |
        | R1     | ATPHSS  | 60    |
      And the otoole parameter "StorageMaxHours" keyed by "REGION STORAGE" with default 0 has the rows:
        | REGION | STORAGE | VALUE |
        | R1     | ATPHSS  | 8     |
      And the otoole parameter "StorageBalanceDay" keyed by "REGION STORAGE" with default 0 has the rows:
        | REGION | STORAGE | VALUE |
        | R1     | ATPHSS  | 1     |
      And the otoole parameter "StorageBalanceSeason" keyed by "REGION STORAGE" with default 0 has the rows:
        | REGION | STORAGE | VALUE |
        | R1     | ATPHSS  | 1     |
      And the otoole parameter "StorageBalanceYear" keyed by "REGION STORAGE" with default 0 has the rows:
        | REGION | STORAGE | VALUE |
        | R1     | ATPHSS  | 0     |
      And the otoole parameter "TotalTechnologyAnnualActivityUpperLimit" keyed by "REGION TECHNOLOGY YEAR" with default -1 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATPHS      | 2030 | 1     |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/extensions.json" parses as JSON storage extension record for "ATPHSS" having "overnight_cost_per_mw" set to 1.25
      And the file "outputs/extensions.json" parses as JSON storage extension record for "ATPHSS" having "energy_overnight_cost" set to 0.05
      And the file "outputs/extensions.json" parses as JSON storage extension record for "ATPHSS" having "lifetime_years" set to 60.0
      And the file "outputs/extensions.json" parses as JSON storage extension record for "ATPHSS" having "duration_max_hours" set to 8.0
      And the file "outputs/extensions.json" parses as JSON storage extension record for "ATPHSS" having "cyclic_state_of_charge_per_day" set to true
      And the file "outputs/extensions.json" parses as JSON storage extension record for "ATPHSS" having "cyclic_state_of_charge_per_season" set to true
      And the file "outputs/extensions.json" parses as JSON storage extension record for "ATPHSS" having "cyclic_state_of_charge_per_period" set to false
      And the file "outputs/extensions.json" parses as JSON storage extension record for "ATPHSS" having "e_sum_max" set to {"2030": 800.0}
      And the file "outputs/extensions.json" parses as JSON storage extension record for "ATPHSS" without field "operating_modes"
      And the log does not contain "storage_balance_day states"
      And the log does not contain "energy_capital_cost states"

    Scenario: A storage that states no discount rate takes the default that the model declares for storage_discount_rate
      The region states its own rate, but OSeMOSYS gives a storage with no row the default of
      DiscountRateStorage, so the region rate does not apply.
      Given the otoole parameter "DiscountRate" keyed by "REGION" with default 0.05 has the rows:
        | REGION | VALUE |
        | R1     | 0.07  |
      And the otoole parameter "DiscountRateStorage" keyed by "REGION STORAGE" with default 0.075 has the rows:
        | REGION | STORAGE | VALUE |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/extensions.json" parses as JSON storage extension record for "ATPHSS" having "discount_rate" set to 0.075
      And the file "decisions.md" contains "| `osemosys.storage_discount_rate.R1/ATPHSS` = 0.075 | `sienna.EnergyReservoirStorage.ATPHSS.extensions.discount_rate` = 0.075 pu | the model states no storage_discount_rate for the member, so the default of the parameter applies; no Sienna field holds it |"

    Scenario: A storage that states a discount rate keeps it
      Given the otoole parameter "DiscountRateStorage" keyed by "REGION STORAGE" with default 0.075 has the rows:
        | REGION | STORAGE | VALUE |
        | R1     | ATPHSS  | 0.06  |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/extensions.json" parses as JSON storage extension record for "ATPHSS" having "discount_rate" set to 0.06
      And the file "decisions.md" contains "| `osemosys.storage_discount_rate.R1/ATPHSS` = 0.06 | `sienna.EnergyReservoirStorage.ATPHSS.extensions.discount_rate` = 0.06 pu | the value of the operations year, which no Sienna field holds |"

    Scenario: Each storage that the operations system cannot hold is left out, and the report names its reason
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the log contains "have no residual storage capacity in the operations year, so each is left out. Storages: R1/ATBATS"
      And the log contains "whose category no carriers: row of the user mappings file names, so each is left out. Storages: R1/ATFLYS"
      And the log contains "lack a technology that charges them or a technology that discharges them, so each is left out. Storages: R1/ATLONES"
      And the log contains "have more than one technology or mode that charges or discharges them, so each is left out. Storages: R1/ATTWOS"
      And the log contains "have a discharging technology with no residual capacity in the operations year, so each is left out. Storages: R1/ATIDLES"
      And the log contains "have a discharging technology whose carriers: row names a type that is not a storage, so each is left out. Storages: R1/ATSUNS"
      And the log contains "have a discharging technology that puts out electricity only to fuels with no location, so each is left out. Storages: R1/HTHEATS"
      And the log contains "put out no electricity at the discharge mode, so each is left out. Storages: R1/ATNOOUTS"
      And the log contains "take in no electricity at the charge mode, so each is left out. Storages: R1/ATNOINS"
      And the file "decisions.md" contains "`osemosys.storage.R1/ATBATS.residual_storage_capacity` = 0.0"
      And the file "decisions.md" contains "the discharging technology R1/ATFLY: no carriers: row names the category 'flywheel'"
      And the file "decisions.md" contains "no technology names the storage in technology_to_storage, so nothing charges it; no technology names the storage in technology_from_storage, so nothing discharges it"
      And the file "decisions.md" contains "`osemosys.storage.R1/ATIDLES.residual_capacity` = 0.0"
      And the file "decisions.md" contains "the residual_capacity of R1/ATIDLE, which discharges the storage, holds none"

    Scenario: Two storages that one technology charges and discharges are each left out, so its power is not counted twice
      Given the otoole parameter "TechnologyToStorage" keyed by "REGION TECHNOLOGY STORAGE MODE_OF_OPERATION" with default 0 has the rows:
        | REGION | TECHNOLOGY | STORAGE | MODE_OF_OPERATION | VALUE |
        | R1     | ATPHS      | ATPHSS  | 1                 | 0.9   |
        | R1     | ATPHS      | ATLONES | 1                 | 0.9   |
      And the otoole parameter "TechnologyFromStorage" keyed by "REGION TECHNOLOGY STORAGE MODE_OF_OPERATION" with default 0 has the rows:
        | REGION | TECHNOLOGY | STORAGE | MODE_OF_OPERATION | VALUE |
        | R1     | ATPHS      | ATPHSS  | 2                 | 1     |
        | R1     | ATPHS      | ATLONES | 2                 | 1     |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/system.json" parses as JSON with 0 component of type "EnergyReservoirStorage"
      And the log contains "share a technology that charges or discharges another storage, so each is left out. Storages: R1/ATLONES, R1/ATPHSS"
      And the file "decisions.md" contains "R1/ATPHS charges or discharges another storage too"

    Scenario: Two storages that one technology charges and discharges in turn are each left out
      ATPHS charges ATPHSS and discharges ATLONES, so both storages would take its whole power.
      Given the otoole parameter "TechnologyToStorage" keyed by "REGION TECHNOLOGY STORAGE MODE_OF_OPERATION" with default 0 has the rows:
        | REGION | TECHNOLOGY | STORAGE | MODE_OF_OPERATION | VALUE |
        | R1     | ATPHS      | ATPHSS  | 1                 | 0.9   |
        | R1     | ATFLY      | ATLONES | 1                 | 1     |
      And the otoole parameter "TechnologyFromStorage" keyed by "REGION TECHNOLOGY STORAGE MODE_OF_OPERATION" with default 0 has the rows:
        | REGION | TECHNOLOGY | STORAGE | MODE_OF_OPERATION | VALUE |
        | R1     | ATBATT     | ATPHSS  | 2                 | 1     |
        | R1     | ATPHS      | ATLONES | 2                 | 1     |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/system.json" parses as JSON with 0 component of type "EnergyReservoirStorage"
      And the log contains "share a technology that charges or discharges another storage, so each is left out. Storages: R1/ATLONES, R1/ATPHSS"

    Scenario: A storage sits on the bus of its discharge, and the report names a charge from another bus
      ATPHS discharges to AT and charges from DE, and a Sienna storage charges at its own bus.
      Given the otoole parameter "InputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | FUEL   | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATPHS      | DEELEC | 1                 | 2030 | 1.25  |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "ATPHSS" having "bus" set to 1
      And the log contains "1 technology(ies) take in electricity at the charge mode at another bus than their component, at two buses, or from a fuel with no location, so the component takes all of it at its own bus. Technologies: R1/ATPHS"
      And the file "decisions.md" contains "the technology takes in electricity at 1 bus(es), the largest at R1/DEELEC, and from 0 fuel(s) with no location; a Sienna component sits on one bus, so all of it is at R1/ATELEC"

    Scenario: A charge at two buses, and a charge from a fuel with no location, are reported
      ATPHS charges from AT, from DE, and from the fuel HTHEATF, which has no location.
      Given the otoole parameter "InputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | FUEL    | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATPHS      | ATELEC  | 1                 | 2030 | 1     |
        | R1     | ATPHS      | DEELEC  | 1                 | 2030 | 0.25  |
        | R1     | ATPHS      | HTHEATF | 1                 | 2030 | 0.1   |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "decisions.md" contains "the technology takes in electricity at 2 bus(es), the largest at R1/ATELEC, and from 1 fuel(s) with no location; a Sienna component sits on one bus, so all of it is at R1/ATELEC"
