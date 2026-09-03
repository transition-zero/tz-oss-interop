@slow @fork_unsafe
Feature: the pypsa-to-sienna pipeline validates the source network before translating
  Validators read the staged PyPSA source and append EnergyModelValidationErrors to a
  standalone validation report. They never block: the standalone `validate` command runs
  them against the source without translating, and a `translate` run also runs them and
  writes the report afterwards. This feature covers the PyPSA-specific validators.

  Scenario: a valid network passes reference integrity with a clean report
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0 location "R1"
    And the network contains generator "gen_1" on "bus_1" carrier "coal" p_nom 100.0
    And the network is saved as "inputs/valid.nc"
    When I run validate against "inputs/valid.nc" pipeline "pypsa-to-sienna"
    Then the file "validation-report.md" exists
    And the file "validation-report.md" contains "No validation issues found."

  Scenario: a generator on an undefined bus is a critical reference-integrity error
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0 location "R1"
    And the network contains generator "gen_1" on "bus_missing" carrier "coal" p_nom 100.0
    And the network is saved as "inputs/dangling.nc"
    When I run validate against "inputs/dangling.nc" pipeline "pypsa-to-sienna"
    Then the file "validation-report.md" exists
    And the file "validation-report.md" contains "| CRITICAL | Generator | gen_1 | bus | bus_missing | references bus 'bus_missing' which is not defined | pypsa_bus_reference_integrity |"

  Scenario Outline: a generator with an out-of-range <attribute> is flagged
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0 location "R1"
    And the network contains generator "gen_1" on "bus_1" carrier "coal"
    And generator "gen_1" has <attribute> <value>
    And the network is saved as "inputs/gen.nc"
    When I run validate against "inputs/gen.nc" pipeline "pypsa-to-sienna"
    Then the file "validation-report.md" contains "| <severity> | Generator | gen_1 | <attribute> | <value> | <message> | pypsa_generators |"

    Examples:
      | attribute     | value  | severity | message                          |
      | p_nom         | -100.0 | CRITICAL | p_nom must be non-negative       |
      | p_max_pu      | 2.0    | CRITICAL | p_max_pu must be within [0, 1]   |
      | marginal_cost | -5.0   | WARNING  | marginal_cost is negative        |
      | efficiency    | 1.5    | CRITICAL | efficiency must be within (0, 1] |

  Scenario: a generator with p_min_pu above p_max_pu is a critical bound error
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0 location "R1"
    And the network contains generator "gen_1" on "bus_1" carrier "coal"
    And generator "gen_1" has p_min_pu 0.8
    And generator "gen_1" has p_max_pu 0.5
    And the network is saved as "inputs/gen_order.nc"
    When I run validate against "inputs/gen_order.nc" pipeline "pypsa-to-sienna"
    Then the file "validation-report.md" contains "| CRITICAL | Generator | gen_1 | p_min_pu | 0.8 | p_min_pu must not exceed p_max_pu | pypsa_generators |"

  Scenario Outline: a storage unit with an out-of-range <attribute> is flagged
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0 location "R1"
    And the network contains storage unit "su_1" on "bus_1" carrier "PHS"
    And storage unit "su_1" has <attribute> <value>
    And the network is saved as "inputs/su.nc"
    When I run validate against "inputs/su.nc" pipeline "pypsa-to-sienna"
    Then the file "validation-report.md" contains "| <severity> | StorageUnit | su_1 | <attribute> | <value> | <message> | pypsa_storage_units |"

    Examples:
      | attribute           | value | severity | message                                   |
      | p_nom               | -50.0 | CRITICAL | p_nom must be non-negative                |
      | max_hours           | -1.0  | CRITICAL | max_hours must be non-negative            |
      | efficiency_store    | 0.0   | CRITICAL | efficiency_store must be within (0, 1]    |
      | efficiency_dispatch | 1.5   | CRITICAL | efficiency_dispatch must be within (0, 1] |
      | standing_loss       | 2.0   | CRITICAL | standing_loss must be within [0, 1]       |

  Scenario: a storage unit's initial charge above its energy capacity is a critical bound error
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0 location "R1"
    And the network contains storage unit "su_1" on "bus_1" carrier "PHS"
    And storage unit "su_1" has p_nom 100.0
    And storage unit "su_1" has max_hours 4.0
    And storage unit "su_1" has state_of_charge_initial 500.0
    And the network is saved as "inputs/su_soc.nc"
    When I run validate against "inputs/su_soc.nc" pipeline "pypsa-to-sienna"
    Then the file "validation-report.md" contains "| CRITICAL | StorageUnit | su_1 | state_of_charge_initial | 500.0 | state_of_charge_initial must be within [0, p_nom * max_hours] | pypsa_storage_units |"

  Scenario: a load with negative static p_set is a warning, because a net demand can go below zero
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0 location "R1"
    And the network contains load "load_1" on "bus_1" with static p_set -10.0
    And the network is saved as "inputs/load_static.nc"
    When I run validate against "inputs/load_static.nc" pipeline "pypsa-to-sienna"
    Then the file "validation-report.md" contains "| WARNING | Load | load_1 | p_set | -10.0 | p_set is negative, so the load injects power rather than withdrawing it | pypsa_loads |"

  Scenario: a load with a negative time-series p_set value is a warning too
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0 location "R1"
    And the network has 3 snapshots at 60 minute intervals
    And the network contains load "load_2" on "bus_1" with p_set 10.0 -5.0 20.0
    And the network is saved as "inputs/load_ts.nc"
    When I run validate against "inputs/load_ts.nc" pipeline "pypsa-to-sienna"
    Then the file "validation-report.md" contains "| WARNING | Load | load_2 | p_set | -5.0 | p_set is negative, so the load injects power rather than withdrawing it | pypsa_loads |"

  Scenario Outline: a line with an out-of-range <attribute> is flagged
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0 location "R1"
    And the network contains bus "bus_2" carrier "AC" v_nom 380.0 location "R1"
    And the network contains line "line_1" from "bus_1" to "bus_2"
    And line "line_1" has <attribute> <value>
    And the network is saved as "inputs/line.nc"
    When I run validate against "inputs/line.nc" pipeline "pypsa-to-sienna"
    Then the file "validation-report.md" contains "| <severity> | Line | line_1 | <attribute> | <value> | <message> | pypsa_lines |"

    Examples:
      | attribute | value  | severity | message                        |
      | s_nom     | -100.0 | CRITICAL | s_nom must be non-negative     |
      | r         | -1.0   | CRITICAL | r must be non-negative         |
      | x         | -1.0   | CRITICAL | x must be non-negative         |
      | s_max_pu  | 2.0    | CRITICAL | s_max_pu must be within [0, 1] |

  Scenario Outline: a link with an out-of-range <attribute> is flagged
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "DC" v_nom 380.0 location "R1"
    And the network contains bus "bus_2" carrier "DC" v_nom 380.0 location "R1"
    And the network contains link "link_1" from "bus_1" to "bus_2"
    And link "link_1" has <attribute> <value>
    And the network is saved as "inputs/link.nc"
    When I run validate against "inputs/link.nc" pipeline "pypsa-to-sienna"
    Then the file "validation-report.md" contains "| <severity> | Link | link_1 | <attribute> | <value> | <message> | pypsa_links |"

    Examples:
      | attribute | value  | severity | message                        |
      | p_nom     | -0.1   | CRITICAL | p_nom must be non-negative     |
      | p_max_pu  | 1.1    | CRITICAL | p_max_pu must be within [0, 1] |

  Scenario: two generators sharing a name is a critical uniqueness error
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0 location "R1"
    And the network contains generator "gen_1" on "bus_1" carrier "coal" p_nom 100.0
    And generator "gen_1" is duplicated within its class
    And the network is saved as "inputs/dup_gen.nc"
    When I run validate against "inputs/dup_gen.nc" pipeline "pypsa-to-sienna"
    Then the file "validation-report.md" contains "| CRITICAL | Generator | gen_1 | name | gen_1 | 'gen_1' is not a unique name for a generator | pypsa_unique_names |"

  Scenario: two buses sharing a name is a critical uniqueness error
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0 location "R1"
    And bus "bus_1" is duplicated within its class
    And the network is saved as "inputs/dup_bus.nc"
    When I run validate against "inputs/dup_bus.nc" pipeline "pypsa-to-sienna"
    Then the file "validation-report.md" contains "| CRITICAL | Bus | bus_1 | name | bus_1 | 'bus_1' is not a unique name for a bus | pypsa_unique_names |"

  Scenario: two stores sharing a name is a critical uniqueness error
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0 location "R1"
    And the network contains store "store_1" on "bus_1"
    And store "store_1" is duplicated within its class
    And the network is saved as "inputs/dup_store.nc"
    When I run validate against "inputs/dup_store.nc" pipeline "pypsa-to-sienna"
    Then the file "validation-report.md" contains "| CRITICAL | Store | store_1 | name | store_1 | 'store_1' is not a unique name for a store | pypsa_unique_names |"

  Scenario: two transformers sharing a name is a critical uniqueness error
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0 location "R1"
    And the network contains bus "bus_2" carrier "AC" v_nom 110.0 location "R1"
    And the network contains transformer "trafo_1" from "bus_1" to "bus_2"
    And transformer "trafo_1" is duplicated within its class
    And the network is saved as "inputs/dup_trafo.nc"
    When I run validate against "inputs/dup_trafo.nc" pipeline "pypsa-to-sienna"
    Then the file "validation-report.md" contains "| CRITICAL | Transformer | trafo_1 | name | trafo_1 | 'trafo_1' is not a unique name for a transformer | pypsa_unique_names |"

  Scenario: two shunt impedances sharing a name is a critical uniqueness error
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0 location "R1"
    And the network contains shunt impedance "shunt_1" on "bus_1"
    And shunt impedance "shunt_1" is duplicated within its class
    And the network is saved as "inputs/dup_shunt.nc"
    When I run validate against "inputs/dup_shunt.nc" pipeline "pypsa-to-sienna"
    Then the file "validation-report.md" contains "| CRITICAL | ShuntImpedance | shunt_1 | name | shunt_1 | 'shunt_1' is not a unique name for a shunt impedance | pypsa_unique_names |"
