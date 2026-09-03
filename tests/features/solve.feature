Feature: solve command runs the Sienna solver on a translated model

  Scenario: solve a Sienna JSON with the fake solver and report success
    Given a fake solver adapter in project plugins
    And adapters.yaml binds solver to "fake_solver"
    And a file "outputs/system.json" exists
    When I dispatch the solve command for "outputs/system.json" with network model "dcp"
    Then the printed output contains "SUCCESSFULLY_FINALIZED"

  Scenario: every answer reaches the solver unchanged
    Given a fake solver adapter in project plugins
    And adapters.yaml binds solver to "fake_solver"
    And a file "outputs/system.json" exists
    When I dispatch the solve command for "outputs/system.json" with network model "dcp" output directory "solved-here" unit commitment "linearised" solver "ipm" presolve "on" crossover "off" time limit "90"
    Then the file "outputs/solver-call.txt" contains "sienna_json_path=outputs/system.json"
    And the file "outputs/solver-call.txt" contains "network_model=dcp"
    And the file "outputs/solver-call.txt" contains "output_dir=solved-here"
    And the file "outputs/solver-call.txt" contains "unit_commitment=linearised"
    And the file "outputs/solver-call.txt" contains "solver=ipm"
    And the file "outputs/solver-call.txt" contains "presolve=on"
    And the file "outputs/solver-call.txt" contains "run_crossover=off"
    And the file "outputs/solver-call.txt" contains "time_limit_seconds=90.0"

  Scenario: a time limit of zero is refused before the solver is reached
    Given a fake solver adapter in project plugins
    And adapters.yaml binds solver to "fake_solver"
    And a file "outputs/system.json" exists
    When I dispatch the solve command for "outputs/system.json" with network model "dcp" output directory "solved" unit commitment "exact" solver "simplex" presolve "choose" crossover "choose" time limit "0"
    Then a user error is printed containing "time limit must be a positive number, got 0.0"
    And the file "outputs/solver-call.txt" does not exist

  Scenario: a negative time limit is refused too
    Given a fake solver adapter in project plugins
    And adapters.yaml binds solver to "fake_solver"
    And a file "outputs/system.json" exists
    When I dispatch the solve command for "outputs/system.json" with network model "dcp" output directory "solved" unit commitment "exact" solver "simplex" presolve "choose" crossover "choose" time limit "-1"
    Then a user error is printed containing "time limit must be a positive number, got -1.0"
    And the file "outputs/solver-call.txt" does not exist

  Scenario: solve shows a user error when the JSON file does not exist
    Given a fake solver adapter in project plugins
    And adapters.yaml binds solver to "fake_solver"
    When I dispatch the solve command for "missing.json" with network model "dcp"
    Then a user error is printed containing "file not found"

  Scenario: solve asks for the model type offering sienna and pypsa
    Given a fake solver adapter in project plugins
    And adapters.yaml binds solver to "fake_solver"
    And a file "outputs/system.json" exists
    When I dispatch the solve command for "outputs/system.json" with network model "dcp"
    Then the select prompt "Model type?" offered exactly "sienna, pypsa"

  Scenario: solve asks how to treat unit commitment, as the PyPSA path does
    Given a fake solver adapter in project plugins
    And adapters.yaml binds solver to "fake_solver"
    And a file "outputs/system.json" exists
    When I dispatch the solve command for "outputs/system.json" with network model "dcp"
    Then the select prompt "Unit commitment treatment? (exact = on/off as true binary decisions, applying the start-up cost and the minimum up and down times; linearised = economic dispatch, which is faster and applies neither)" offered exactly "exact, linearised"

  Scenario: the unit commitment answer defaults to exact
    Given a fake solver adapter in project plugins
    And adapters.yaml binds solver to "fake_solver"
    And a file "outputs/system.json" exists
    When I dispatch the solve command for "outputs/system.json" with network model "dcp"
    Then the file "outputs/solver-call.txt" contains "unit_commitment=exact"

  Scenario: a ready solver environment gets no download notice
    Given a fake solver adapter in project plugins
    And adapters.yaml binds solver to "fake_solver"
    And a file "outputs/system.json" exists
    When I dispatch the solve command for "outputs/system.json" with network model "dcp"
    Then the printed output does not contain "will be downloaded"
    And the printed output contains "SUCCESSFULLY_FINALIZED"

  Scenario: a missing solver environment asks for consent and proceeds when accepted
    Given a fake solver adapter in project plugins that is not provisioned
    And adapters.yaml binds solver to "fake_solver"
    And a file "outputs/system.json" exists
    When I dispatch the solve command for "outputs/system.json" accepting the download
    Then the printed output contains "Julia and the PowerSimulations.jl solver packages will be downloaded"
    And the printed output contains "SUCCESSFULLY_FINALIZED"

  Scenario: declining the download cancels solve
    Given a fake solver adapter in project plugins that is not provisioned
    And adapters.yaml binds solver to "fake_solver"
    And a file "outputs/system.json" exists
    When I dispatch the solve command for "outputs/system.json" declining the download
    Then the printed output contains "Solve cancelled"
    And the printed output does not contain "SUCCESSFULLY_FINALIZED"
