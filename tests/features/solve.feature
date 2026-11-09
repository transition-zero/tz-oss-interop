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
    When I dispatch the solve command for "outputs/system.json" with network model "dcp" output directory "solved-here" unserved energy "penalised" unit commitment "linearised" solver "ipm" presolve "on" crossover "off" time limit "90"
    Then the file "outputs/solver-call.txt" contains "sienna_json_path=outputs/system.json"
    And the file "outputs/solver-call.txt" contains "network_model=dcp"
    And the file "outputs/solver-call.txt" contains "output_dir=solved-here"
    And the file "outputs/solver-call.txt" contains "unit_commitment=linearised"
    And the file "outputs/solver-call.txt" contains "solver=ipm"
    And the file "outputs/solver-call.txt" contains "presolve=on"
    And the file "outputs/solver-call.txt" contains "run_crossover=off"
    And the file "outputs/solver-call.txt" contains "time_limit_seconds=90.0"
    And the file "outputs/solver-call.txt" contains "unserved_energy=penalised"

  Scenario: solve asks whether a load may go unserved at a penalty
    Given a fake solver adapter in project plugins
    And adapters.yaml binds solver to "fake_solver"
    And a file "outputs/system.json" exists
    When I dispatch the solve command for "outputs/system.json" with network model "dcp"
    Then the select prompt "Unserved energy? (refused = every load is met, so one short hour makes the solve infeasible; penalised = a shortfall goes unserved at a high penalty cost)" offered exactly "refused, penalised"

  Scenario: the unserved energy answer defaults to refused
    Given a fake solver adapter in project plugins
    And adapters.yaml binds solver to "fake_solver"
    And a file "outputs/system.json" exists
    When I dispatch the solve command for "outputs/system.json" with network model "dcp"
    Then the file "outputs/solver-call.txt" contains "unserved_energy=refused"
    And the printed output does not contain "unserved_energy="

  Scenario: a penalised solve reports its unserved energy in the result
    Given a fake solver adapter in project plugins
    And adapters.yaml binds solver to "fake_solver"
    And a file "outputs/system.json" exists
    When I dispatch the solve command for "outputs/system.json" with network model "copperplate" output directory "solved" unserved energy "penalised" unit commitment "linearised" solver "simplex" presolve "choose" crossover "choose" time limit "60"
    Then the printed output contains "SUCCESSFULLY_FINALIZED"
    And the printed output contains "unserved_energy=42.5 MWh"

  Scenario: a penalised Sienna solve says that its unserved energy counts the modelled hours only
    The Sienna reading counts each modelled hour once, with no weight for the hours that a
    representative period stands for, so the summary says which hours it counts.
    Given a fake solver adapter in project plugins
    And adapters.yaml binds solver to "fake_solver"
    And a file "outputs/system.json" exists
    When I dispatch the solve command for "outputs/system.json" with network model "copperplate" output directory "solved" unserved energy "penalised" unit commitment "linearised" solver "simplex" presolve "choose" crossover "choose" time limit "60"
    Then the printed output contains "unserved_energy=42.5 MWh in the modelled hours only"

  Scenario: a time limit of zero is refused before the solver is reached
    Given a fake solver adapter in project plugins
    And adapters.yaml binds solver to "fake_solver"
    And a file "outputs/system.json" exists
    When I dispatch the solve command for "outputs/system.json" with network model "dcp" output directory "solved" unserved energy "refused" unit commitment "exact" solver "simplex" presolve "choose" crossover "choose" time limit "0"
    Then a user error is printed containing "time limit must be a positive, finite number, got 0.0"
    And the file "outputs/solver-call.txt" does not exist

  Scenario: a negative time limit is refused too
    Given a fake solver adapter in project plugins
    And adapters.yaml binds solver to "fake_solver"
    And a file "outputs/system.json" exists
    When I dispatch the solve command for "outputs/system.json" with network model "dcp" output directory "solved" unserved energy "refused" unit commitment "exact" solver "simplex" presolve "choose" crossover "choose" time limit "-1"
    Then a user error is printed containing "time limit must be a positive, finite number, got -1.0"
    And the file "outputs/solver-call.txt" does not exist

  Scenario: an infinite time limit is refused before the solver is reached
    Given a fake solver adapter in project plugins
    And adapters.yaml binds solver to "fake_solver"
    And a file "outputs/system.json" exists
    When I dispatch the solve command for "outputs/system.json" with network model "dcp" output directory "solved" unserved energy "refused" unit commitment "exact" solver "simplex" presolve "choose" crossover "choose" time limit "inf"
    Then a user error is printed containing "time limit must be a positive, finite number, got inf"
    And the file "outputs/solver-call.txt" does not exist

  Scenario: solve shows a user error when the JSON file does not exist
    Given a fake solver adapter in project plugins
    And adapters.yaml binds solver to "fake_solver"
    When I dispatch the solve command for "missing.json" with network model "dcp"
    Then a user error is printed containing "file not found"

  Scenario: solve asks for the model type offering every model it can run
    Given a fake solver adapter in project plugins
    And adapters.yaml binds solver to "fake_solver"
    And a file "outputs/system.json" exists
    When I dispatch the solve command for "outputs/system.json" with network model "dcp"
    Then the select prompt "Model type?" offered exactly "sienna, pypsa, sienna-investments"

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

  Scenario: the investments model type expands a portfolio and reports what it cost
    Given a fake expansion adapter in project plugins
    And adapters.yaml binds expansion to "fake_expansion"
    And a file "outputs/portfolio.json" exists
    When I dispatch the expand command for "outputs/portfolio.json"
    Then the printed output contains "SUCCESSFULLY_FINALIZED"
    And the printed output contains "987.654"

  Scenario: every expansion answer reaches the port unchanged
    Given a fake expansion adapter in project plugins
    And adapters.yaml binds expansion to "fake_expansion"
    And a file "outputs/portfolio.json" exists
    When I dispatch the expand command for "outputs/portfolio.json" with balance model "nodal" output directory "built-here" investment treatment "integer" discount rate "0.07" solver "ipm" presolve "on" crossover "off" time limit "90"
    Then the file "outputs/expansion-call.txt" contains "portfolio_json_path=outputs/portfolio.json"
    And the file "outputs/expansion-call.txt" contains "balance_model=nodal"
    And the file "outputs/expansion-call.txt" contains "output_dir=built-here"
    And the file "outputs/expansion-call.txt" contains "investment_treatment=integer"
    And the file "outputs/expansion-call.txt" contains "discount_rate=0.07"
    And the file "outputs/expansion-call.txt" contains "solver=ipm"
    And the file "outputs/expansion-call.txt" contains "presolve=on"
    And the file "outputs/expansion-call.txt" contains "run_crossover=off"
    And the file "outputs/expansion-call.txt" contains "time_limit_seconds=90.0"

  Scenario: a blank discount rate leaves the rate the portfolio states in force
    Given a fake expansion adapter in project plugins
    And adapters.yaml binds expansion to "fake_expansion"
    And a file "outputs/portfolio.json" exists
    When I dispatch the expand command for "outputs/portfolio.json"
    Then the file "outputs/expansion-call.txt" contains "discount_rate=None"

  Scenario: the investments type asks which balance model to respect
    Given a fake expansion adapter in project plugins
    And adapters.yaml binds expansion to "fake_expansion"
    And a file "outputs/portfolio.json" exists
    When I dispatch the expand command for "outputs/portfolio.json"
    Then the select prompt "Balance model? (single-region = one zone; multi-region = zone by zone; nodal = bus by bus)" offered exactly "single-region, multi-region, nodal"

  Scenario: the investments type asks how to treat what a plan may build
    Given a fake expansion adapter in project plugins
    And adapters.yaml binds expansion to "fake_expansion"
    And a file "outputs/portfolio.json" exists
    When I dispatch the expand command for "outputs/portfolio.json"
    Then the select prompt "Investment treatment? (continuous = build any amount of capacity; integer = build whole units only, which is slower)" offered exactly "continuous, integer"

  Scenario: an expansion refuses a time limit of zero before the port is reached
    Given a fake expansion adapter in project plugins
    And adapters.yaml binds expansion to "fake_expansion"
    And a file "outputs/portfolio.json" exists
    When I dispatch the expand command for "outputs/portfolio.json" with balance model "multi-region" output directory "expanded" investment treatment "continuous" discount rate "" solver "simplex" presolve "choose" crossover "choose" time limit "0"
    Then a user error is printed containing "time limit must be a positive, finite number, got 0.0"
    And the file "outputs/expansion-call.txt" does not exist

  Scenario: an expansion refuses an infinite time limit before the port is reached
    Given a fake expansion adapter in project plugins
    And adapters.yaml binds expansion to "fake_expansion"
    And a file "outputs/portfolio.json" exists
    When I dispatch the expand command for "outputs/portfolio.json" with balance model "multi-region" output directory "expanded" investment treatment "continuous" discount rate "" solver "simplex" presolve "choose" crossover "choose" time limit "inf"
    Then a user error is printed containing "time limit must be a positive, finite number, got inf"
    And the file "outputs/expansion-call.txt" does not exist

  Scenario: an expansion refuses a discount rate of zero given on the run before the port is reached
    Given a fake expansion adapter in project plugins
    And adapters.yaml binds expansion to "fake_expansion"
    And a file "outputs/portfolio.json" exists
    When I dispatch the expand command for "outputs/portfolio.json" with balance model "multi-region" output directory "expanded" investment treatment "continuous" discount rate "0" solver "simplex" presolve "choose" crossover "choose" time limit ""
    Then a user error is printed containing "discount rate given on the run must be a positive, finite number, got 0.0"
    And the file "outputs/expansion-call.txt" does not exist

  Scenario: an expansion refuses an infinite discount rate given on the run before the port is reached
    Given a fake expansion adapter in project plugins
    And adapters.yaml binds expansion to "fake_expansion"
    And a file "outputs/portfolio.json" exists
    When I dispatch the expand command for "outputs/portfolio.json" with balance model "multi-region" output directory "expanded" investment treatment "continuous" discount rate "inf" solver "simplex" presolve "choose" crossover "choose" time limit ""
    Then a user error is printed containing "discount rate given on the run must be a positive, finite number, got inf"
    And the file "outputs/expansion-call.txt" does not exist

  Scenario: an expansion asks nothing more after the user cancels the solver prompt
    Given a fake expansion adapter in project plugins
    And adapters.yaml binds expansion to "fake_expansion"
    And a file "outputs/portfolio.json" exists
    When I dispatch the expand command for "outputs/portfolio.json" and cancel the solver prompt
    Then no prompt follows the select prompt "HiGHS solver algorithm?"
    And the file "outputs/expansion-call.txt" does not exist

  Scenario: an expansion asks nothing more after the user cancels the balance model prompt
    Given a fake expansion adapter in project plugins
    And adapters.yaml binds expansion to "fake_expansion"
    And a file "outputs/portfolio.json" exists
    When I dispatch the expand command for "outputs/portfolio.json" and cancel the balance model prompt
    Then no prompt follows the select prompt "Balance model? (single-region = one zone; multi-region = zone by zone; nodal = bus by bus)"
    And the file "outputs/expansion-call.txt" does not exist

  Scenario: an expansion shows a user error when the portfolio does not exist
    Given a fake expansion adapter in project plugins
    And adapters.yaml binds expansion to "fake_expansion"
    When I dispatch the expand command for "missing.json"
    Then a user error is printed containing "file not found"

  Scenario: a missing expansion environment names the investments packages and proceeds when accepted
    Given a fake expansion adapter in project plugins that is not provisioned
    And adapters.yaml binds expansion to "fake_expansion"
    And a file "outputs/portfolio.json" exists
    When I dispatch the expand command for "outputs/portfolio.json" accepting the download
    Then the printed output contains "Julia and the PowerSystemsInvestments.jl packages will be downloaded"
    And the printed output contains "SUCCESSFULLY_FINALIZED"

  Scenario: declining the expansion download cancels the expansion
    Given a fake expansion adapter in project plugins that is not provisioned
    And adapters.yaml binds expansion to "fake_expansion"
    And a file "outputs/portfolio.json" exists
    When I dispatch the expand command for "outputs/portfolio.json" declining the download
    Then the printed output contains "Solve cancelled"
    And the printed output does not contain "SUCCESSFULLY_FINALIZED"
    And the file "outputs/expansion-call.txt" does not exist

  Scenario: a period bound that is not a date stops the expansion before Julia reads it
    The adapter writes each period bound into Julia source, so a bound must parse as a date
    before any Julia runs.
    Given a Julia expansion adapter that stops where Julia would start, in project plugins
    And adapters.yaml binds expansion to "julia_expansion_probe"
    And a file "outputs/portfolio.json" exists
    And a series companion "outputs/portfolio_series.json" whose first period starts with Julia code
    When I dispatch the expand command for "outputs/portfolio.json"
    Then a user error is printed containing "outputs/portfolio_series.json does not hold a series document that the expansion can read"
    And a user error is printed containing "periods.0.start"
    And the printed output does not contain "the probe reached Julia"

  Scenario: a readable series companion reaches the point where Julia starts
    Given a Julia expansion adapter that stops where Julia would start, in project plugins
    And adapters.yaml binds expansion to "julia_expansion_probe"
    And a file "outputs/portfolio.json" exists
    And a series companion "outputs/portfolio_series.json" with one period of 2030
    When I dispatch the expand command for "outputs/portfolio.json"
    Then a user error is printed containing "the probe reached Julia"
