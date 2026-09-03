Feature: translation decisions report
  Each translation step appends TranslationEvents to a shared EventLog
  via its ScopedRecorder. At the end of the run, the use case passes
  the collected events to the configured reporter, which renders them
  into one or more files. markdown_report is the default; csv_report
  writes one row per (event, destination). Both name the pipeline the
  event came from as well as the step, so a chain's legs stay distinct;
  noop_report suppresses all output. adapters.yaml may bind the
  reporter to a list of adapters; the container fans the events out to
  each one internally.

  Background:
    Given a step plugin "emit_test_events" that appends a representative set of TranslationEvents
    And a pipeline "decisions-test" running steps "emit_test_events"

  Scenario: markdown_report (default) writes decisions.md as tables
    When I run translate with source "noop" destination "noop" pipeline "decisions-test"
    Then the file "decisions.md" exists
    And the file "decisions.md" contains "| Source | Destination | Rule | Note | Pipeline | Step |"
    And the file "decisions.md" contains "| `pypsa.Generator.gen-1.p_nom` = 100.0 MW | `sienna.ThermalStandard.gen-1.active_power_limits.max` = 1.0 pu_MVA | p_nom / base_power = 100 / 100 |  | decisions-test | emit_test_events |"
    And the file "decisions.md" contains "| `pypsa.Generator.gen-1.carrier` = coal | `sienna.ThermalStandard.gen-1.prime_mover_type` = ST | carrier_lookup[coal] = (ST, COAL) |  | decisions-test | emit_test_events |"
    And the file "decisions.md" contains "| `pypsa.Generator.gen-1.carrier` = coal | `sienna.ThermalStandard.gen-1.fuel` = COAL | carrier_lookup[coal] = (ST, COAL) |  | decisions-test | emit_test_events |"
    And the file "decisions.md" contains "|  | `sienna.ThermalStandard.gen-1.must_run` = False |  | ThermalStandard.must_run not present in PyPSA; using translator default | decisions-test | emit_test_events |"
    And the file "decisions.md" contains "| `pypsa.ShuntImpedance.shunt-1` |  |  | ShuntImpedance has no Sienna equivalent | decisions-test | emit_test_events |"
    And the file "decisions.md" contains "| `pypsa.Generator.gas\|peaker.carrier` = gas | `sienna.ThermalStandard.gas\|peaker.prime_mover_type` = GT | carrier_lookup[gas] = (GT, GAS) |  | decisions-test | emit_test_events |"

  Scenario: csv_report writes one row per destination with the step column
    Given adapters.yaml binds reporter to "csv_report"
    When I run translate with source "noop" destination "noop" pipeline "decisions-test"
    Then the file "decisions.csv" exists
    And the csv "decisions.csv" header is "pipeline,step,kind,source_framework,source_component,source_name,source_attribute,source_value,source_unit,destination_framework,destination_component,destination_name,destination_attribute,destination_value,destination_unit,derivation,note"
    And the csv "decisions.csv" has 8 data rows
    And the csv "decisions.csv" has the row "decisions-test,emit_test_events,VALUE_DERIVED,pypsa,Generator,gen-1,p_nom,100.0,MW,sienna,ThermalStandard,gen-1,active_power_limits.max,1.0,pu_MVA,p_nom / base_power = 100 / 100,"
    And the csv "decisions.csv" has the row "decisions-test,emit_test_events,VALUE_DERIVED,pypsa|pypsa,Bus|Bus,bus-1|bus-2,v_nom|v_nom,380.0|380.0,kV|kV,sienna,Area,area-A,aggregated_voltage,380.0,kV,mean(bus[area=A].v_nom),"
    And the csv "decisions.csv" has the row "decisions-test,emit_test_events,TRANSLATOR_DEFAULT_APPLIED,,,,,,,sienna,ThermalStandard,gen-1,must_run,False,,,ThermalStandard.must_run not present in PyPSA; using translator default"
    And the csv "decisions.csv" has the row "decisions-test,emit_test_events,COMPONENT_SKIPPED,pypsa,ShuntImpedance,shunt-1,,,,,,,,,,,ShuntImpedance has no Sienna equivalent"
    And the csv "decisions.csv" has a row with step "emit_test_events" kind "VALUE_DERIVED" destination_attribute "prime_mover_type"
    And the csv "decisions.csv" has a row with step "emit_test_events" kind "VALUE_DERIVED" destination_attribute "fuel"
    And the csv "decisions.csv" has a row with step "emit_test_events" kind "VALUE_DERIVED" destination_attribute "aggregated_voltage"
    And the csv "decisions.csv" has a row with step "emit_test_events" kind "TRANSLATOR_DEFAULT_APPLIED" destination_attribute "must_run"
    And the csv "decisions.csv" has a row with step "emit_test_events" kind "USER_CONFIG_DEFAULT_APPLIED" destination_attribute "ramp_limits.up"
    And the csv "decisions.csv" has a row with step "emit_test_events" kind "COMPONENT_SKIPPED" destination_attribute ""

  Scenario: a multi-binding fans out internally to both adapters
    Given adapters.yaml multi-binds reporter to "markdown_report" and "csv_report"
    When I run translate with source "noop" destination "noop" pipeline "decisions-test"
    Then the file "decisions.md" exists
    And the file "decisions.csv" exists

  Scenario: noop_report suppresses both reports
    Given adapters.yaml binds reporter to "noop_report"
    When I run translate with source "noop" destination "noop" pipeline "decisions-test"
    Then the file "outputs/noop-ran.txt" exists
    And the file "decisions.md" does not exist
    And the file "decisions.csv" does not exist

  Scenario: an empty section does not truncate the sections after it
    Given a step plugin "emit_sparse_events" that appends only a derived value and a skipped component
    And a pipeline "sparse-decisions-test" running steps "emit_sparse_events"
    When I run translate with source "noop" destination "noop" pipeline "sparse-decisions-test"
    Then the file "decisions.md" contains "## Translator defaults applied (0)"
    And the file "decisions.md" contains "## Components skipped (1)"
    And the file "decisions.md" contains "| `pypsa.ShuntImpedance.shunt-1` |  |  | ShuntImpedance has no Sienna equivalent | sparse-decisions-test | emit_sparse_events |"

  Scenario: rerunning translate overwrites the existing decisions report
    When I run translate with source "noop" destination "noop" pipeline "decisions-test"
    And I run translate with source "noop" destination "noop" pipeline "decisions-test"
    Then the file "decisions.md" exists
    And the file "decisions-2.md" does not exist
