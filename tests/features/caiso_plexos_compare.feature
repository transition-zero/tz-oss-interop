@slow @fork_unsafe
Feature: the CAISO PLEXOS stack model is comparable against a PyPSA network
  The stack-model CSVs are not shipped with interop; a user extracts them from CAISO's
  published assessment and names them at the source's prompts. Each scenario below builds
  a pair of CSVs in that column shape, so the numbers are the scenario's own.

  Scenario: comparing a PyPSA network against the CAISO PLEXOS stack model produces a report
    Given a CAISO stack model
    And the stack model covers month 7 day 15 hour ending 18 with load 1000.0 and surplus 250.0
    And that hour has "Natural Gas" capacity 1250.0
    And that hour has "Battery Storage" dispatch 60.0
    And the appendix gives "Natural Gas" 1250.0 in Jul
    And the stack model is saved as "inputs/stack_model.csv" and the appendix as "inputs/appendix.csv"
    And a PyPSA network
    And the network has 2 snapshots at 60 minute intervals
    And the network contains bus "b0" carrier "AC" v_nom 380.0
    And the network contains generator "gen_a" on "b0" carrier "coal" p_nom 200.0
    And the network contains load "load_a" on "b0" with p_set 140.0 150.0
    And the generator "gen_a" dispatches 100.0 110.0
    And the snapshot weightings are 1.0 1.0
    And the network objective is 1234.5
    And the network is saved as "inputs/solved.nc"
    When I compare the pypsa network in "inputs/solved.nc" against the CAISO PLEXOS stack model
    Then the file "outputs/comparison_summary.md" exists
    And the file "outputs/comparison_summary.md" contains "caiso-plexos"
    And the file "outputs/comparison_summary.md" contains "| surplus | 1 | 1 | 1 | - | - |"
    And the file "outputs/comparison_summary.md" contains "Battery Storage, Demand Response"
    And the printed output contains "diffs="

  Scenario: available capacity by carrier is compared at category grain against the stack model
    Given a CAISO stack model
    And the stack model covers month 7 day 15 hour ending 18 with load 1000.0 and surplus 250.0
    And that hour has "Natural Gas" capacity 900.0
    And that hour has "Nuclear" capacity 350.0
    And the stack model covers month 7 day 15 hour ending 19 with load 1100.0 and surplus 150.0
    And that hour has "Natural Gas" capacity 900.0
    And that hour has "Nuclear" capacity 350.0
    And the appendix gives "Natural Gas" 900.0 in Jul
    And the stack model is saved as "inputs/stack_model.csv" and the appendix as "inputs/appendix.csv"
    And a PyPSA network
    And the network has 2 snapshots starting 2026-07-15T17:00 at 60 minute intervals
    And the network contains bus "b0" carrier "AC" v_nom 380.0
    And the network contains generator "nuke" on "b0" carrier "Nuclear" p_nom 350.0
    And the network contains generator "gas" on "b0" carrier "Natural Gas" p_nom 900.0
    And the snapshot weightings are 1.0 1.0
    And the network is saved as "inputs/solved.nc"
    When I compare the pypsa network in "inputs/solved.nc" against the CAISO PLEXOS stack model
    Then the file "outputs/comparison_summary.md" exists
    And the file "outputs/comparison_summary.md" contains "| available_capacity | Natural Gas | 2 | 0 | 0 |"
    And the file "outputs/comparison_summary.md" contains "| available_capacity | Nuclear | 2 | 0 | 0 |"

  Scenario: system load is compared by summing per-component load to system grain
    # The two hours state different loads, so a match at the T17:00/T18:00 snapshots only
    # holds under the start-of-interval (hour ending - 1) alignment. A one-hour drift
    # would pair each snapshot with the wrong hour and both rows would differ.
    Given a CAISO stack model
    And the stack model covers month 7 day 15 hour ending 18 with load 1000.0 and surplus 250.0
    And the stack model covers month 7 day 15 hour ending 19 with load 1100.0 and surplus 150.0
    And the appendix gives "Natural Gas" 900.0 in Jul
    And the stack model is saved as "inputs/stack_model.csv" and the appendix as "inputs/appendix.csv"
    And a PyPSA network
    And the network has 2 snapshots starting 2026-07-15T17:00 at 60 minute intervals
    And the network contains bus "b0" carrier "AC" v_nom 380.0
    And the network contains load "load_a" on "b0" with p_set 700.0 750.0
    And the network contains load "load_b" on "b0" with p_set 300.0 350.0
    And the snapshot weightings are 1.0 1.0
    And the network is saved as "inputs/solved.nc"
    When I compare the pypsa network in "inputs/solved.nc" against the CAISO PLEXOS stack model
    Then the file "outputs/comparison_summary.md" exists
    And the file "outputs/comparison_summary.md" contains "| load | - | 2 | 0 | 0 |"

  Scenario: system surplus is compared against the stack model's own surplus column
    # The stack model states 1000.0 MW of load and 250.0 MW of surplus at hour ending 18,
    # so a network carrying that load under 1250.0 MW of capacity should match it.
    Given a CAISO stack model
    And the stack model covers month 7 day 15 hour ending 18 with load 1000.0 and surplus 250.0
    And the appendix gives "Natural Gas" 1250.0 in Jul
    And the stack model is saved as "inputs/stack_model.csv" and the appendix as "inputs/appendix.csv"
    And a PyPSA network
    And the network has 1 snapshots starting 2026-07-15T17:00 at 60 minute intervals
    And the network contains bus "b0" carrier "AC" v_nom 380.0
    And the network contains generator "fleet" on "b0" carrier "Natural Gas" p_nom 1250.0
    And the network contains load "load_a" on "b0" with p_set 1000.0
    And the snapshot weightings are 1.0
    And the network is saved as "inputs/solved.nc"
    When I compare the pypsa network in "inputs/solved.nc" against the CAISO PLEXOS stack model
    Then the file "outputs/comparison_summary.md" exists
    And the file "outputs/comparison_summary.md" contains "| surplus | - | 1 | 0 | 0 |"

  Scenario: appendix monthly capacity joins at month-start timestamps and honours the roll-ups
    # Biogas, Biomass and Geothermal roll up into one Other Renewables figure of 60.0.
    Given a CAISO stack model
    And the stack model covers month 7 day 15 hour ending 18 with load 1000.0 and surplus 250.0
    And the appendix gives "Natural Gas" 900.0 in Sep
    And the appendix gives "Biogas" 10.0 in Sep
    And the appendix gives "Biomass" 20.0 in Sep
    And the appendix gives "Geothermal" 30.0 in Sep
    And the stack model is saved as "inputs/stack_model.csv" and the appendix as "inputs/appendix.csv"
    And a PyPSA network
    And the network has 1 snapshots starting 2026-09-01T00:00 at 60 minute intervals
    And the network contains bus "b0" carrier "AC" v_nom 380.0
    And the network contains generator "gas" on "b0" carrier "Natural Gas" p_nom 900.0
    And the network contains generator "renew" on "b0" carrier "Other Renewables" p_nom 60.0
    And the snapshot weightings are 1.0
    And the network is saved as "inputs/solved.nc"
    When I compare the pypsa network in "inputs/solved.nc" against the CAISO PLEXOS stack model
    Then the file "outputs/comparison_summary.md" exists
    And the file "outputs/comparison_summary.md" contains "| available_capacity | Natural Gas | 1 | 0 | 0 |"
    And the file "outputs/comparison_summary.md" contains "| available_capacity | Other Renewables | 1 | 0 | 0 |"

  Scenario: appendix months outside May to September are not emitted
    Given a CAISO stack model
    And the stack model covers month 7 day 15 hour ending 18 with load 1000.0 and surplus 250.0
    And the appendix gives "Natural Gas" 800.0 in Jan
    And the stack model is saved as "inputs/stack_model.csv" and the appendix as "inputs/appendix.csv"
    And a PyPSA network
    And the network has 1 snapshots starting 2026-01-01T00:00 at 60 minute intervals
    And the network contains bus "b0" carrier "AC" v_nom 380.0
    And the network contains generator "gas" on "b0" carrier "Natural Gas" p_nom 800.0
    And the snapshot weightings are 1.0
    And the network is saved as "inputs/solved.nc"
    When I compare the pypsa network in "inputs/solved.nc" against the CAISO PLEXOS stack model
    Then the file "outputs/comparison_summary.md" exists
    And the file "outputs/comparison_summary.md" contains "_(no shared rows to compare)_"

  Scenario: surplus is recorded as derived from the available capacity and load already reported
    # Compared this way round so the PyPSA leg runs last and its decisions.md survives.
    Given a CAISO stack model
    And the stack model covers month 7 day 15 hour ending 18 with load 1000.0 and surplus 250.0
    And the appendix gives "Natural Gas" 1250.0 in Jul
    And the stack model is saved as "inputs/stack_model.csv" and the appendix as "inputs/appendix.csv"
    And a PyPSA network
    And the network has 2 snapshots at 60 minute intervals
    And the network contains bus "b0" carrier "AC" v_nom 380.0
    And the network contains generator "gen_a" on "b0" carrier "coal" p_nom 200.0
    And the network contains load "load_a" on "b0" with p_set 140.0 150.0
    And the generator "gen_a" dispatches 100.0 110.0
    And the snapshot weightings are 1.0 1.0
    And the network objective is 1234.5
    And the network is saved as "inputs/solved.nc"
    When I compare the CAISO PLEXOS stack model against the pypsa network in "inputs/solved.nc"
    Then the file "decisions.md" contains "`results.results.available_capacity.variable` MW<br>`results.results.load.variable` MW | `results.results.surplus.variable` MW"
    And the file "decisions.md" does not contain "`pypsa.Generator.*.p_nom` MW<br>`pypsa.StorageUnit.*.p_nom` MW<br>`pypsa.Load.*.p_set` MW | `results.results.surplus.variable` MW"
