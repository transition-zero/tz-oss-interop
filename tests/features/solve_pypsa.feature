Feature: Solve a PyPSA network

  solve runs a PyPSA network through HiGHS over a chosen range of dates, writing the
  solved network to its own directory so a re-run never overwrites its input.

  Scenario: solving a network over one day writes a solved copy
    Given a PyPSA network with 48 hourly snapshots saved as "inputs/net.nc"
    When I run solve on "inputs/net.nc" from "2026-09-01" to "2026-09-01" into "outputs/solved"
    Then the file "outputs/solved/net.nc" exists
    And the solved network "outputs/solved/net.nc" has dispatch for 24 snapshots
    And the solve reported success

  Scenario: solving across a month boundary solves each month independently
    A generator only available before the boundary and a storage unit that could carry its
    output past it: solved as one continuous range, storage arbitrage covers every day with
    the cheap generator and the expensive one never runs. Solved month by month, the storage
    resets at the boundary and the second month has no choice but to run the expensive
    generator throughout, since nothing crosses over from the first month's solve.
    Given a PyPSA network
    And the network has 6 snapshots starting 2026-09-29 at 1440 minute intervals
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network contains generator "cheap" on "bus_1" carrier "gas" p_nom 100.0 marginal_cost 1.0 p_max_pu_series 1 1 0 0 0 0
    And the network contains generator "expensive" on "bus_1" carrier "gas" p_nom 100.0 marginal_cost 100.0
    And the network contains load "load_1" on "bus_1" with static p_set 10.0
    And the network contains storage unit "batt" on "bus_1" carrier "battery" p_nom 50.0 p_min_pu -1.0 max_hours 10.0
    And the network is saved as "inputs/monthly.nc"
    When I run solve on "inputs/monthly.nc" from "2026-09-29" to "2026-10-04" into "outputs/solved"
    Then the solved network "outputs/solved/monthly.nc" has generator "expensive" dispatch 0 0 10 10 10 10
    And the solve reported success

  Scenario: the window length is the caller's choice, not a fixed calendar month
    The same network and the same range as the scenario above, but solved in one window
    rather than month by month. Nothing forces a month on a network, so a caller whose
    storage cycles over a longer period asks for a longer window and the battery carries
    the cheap generator's output across the boundary the monthly solve reset at.
    Given a PyPSA network
    And the network has 6 snapshots starting 2026-09-29 at 1440 minute intervals
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network contains generator "cheap" on "bus_1" carrier "gas" p_nom 100.0 marginal_cost 1.0 p_max_pu_series 1 1 0 0 0 0
    And the network contains generator "expensive" on "bus_1" carrier "gas" p_nom 100.0 marginal_cost 100.0
    And the network contains load "load_1" on "bus_1" with static p_set 10.0
    And the network contains storage unit "batt" on "bus_1" carrier "battery" p_nom 50.0 p_min_pu -1.0 max_hours 10.0
    And the network is saved as "inputs/yearly.nc"
    When I run solve on "inputs/yearly.nc" from "2026-09-29" to "2026-10-04" in "year" windows with a 0 day look-ahead into "outputs/solved"
    Then the solved network "outputs/solved/yearly.nc" has generator "expensive" dispatch 0 0 0 0 0 0
    And the solve reported success

  Scenario: a start date with no end still splits by month against the network's own end
    An open-ended range must not be solved as one continuous span either, since that
    would let storage carry across a month boundary just as an unsplit bounded range
    would. The missing end is resolved against the network's own last snapshot first,
    then that span is split by month like any other.
    Given a PyPSA network
    And the network has 6 snapshots starting 2026-09-29 at 1440 minute intervals
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network contains generator "cheap" on "bus_1" carrier "gas" p_nom 100.0 marginal_cost 1.0 p_max_pu_series 1 1 0 0 0 0
    And the network contains generator "expensive" on "bus_1" carrier "gas" p_nom 100.0 marginal_cost 100.0
    And the network contains load "load_1" on "bus_1" with static p_set 10.0
    And the network contains storage unit "batt" on "bus_1" carrier "battery" p_nom 50.0 p_min_pu -1.0 max_hours 10.0
    And the network is saved as "inputs/monthly_open.nc"
    When I run solve on "inputs/monthly_open.nc" from "2026-09-29" onward into "outputs/solved"
    Then the solved network "outputs/solved/monthly_open.nc" has generator "expensive" dispatch 0 0 10 10 10 10
    And the solve reported success

  Scenario: solving a directory solves every network in it
    Given a PyPSA network with 24 hourly snapshots saved as "inputs/ensemble/net_1.nc"
    And a PyPSA network with 24 hourly snapshots saved as "inputs/ensemble/net_2.nc"
    When I run solve on "inputs/ensemble" from "2026-09-01" to "2026-09-01" into "outputs/solved"
    Then the file "outputs/solved/net_1.nc" exists
    And the file "outputs/solved/net_2.nc" exists
    And the solve reported success

  Scenario: a date range outside the network writes nothing
    Given a PyPSA network with 48 hourly snapshots saved as "inputs/net.nc"
    When I run solve on "inputs/net.nc" from "2027-01-01" to "2027-01-01" into "outputs/solved"
    Then the file "outputs/solved/net.nc" does not exist
    And the printed output contains "no snapshots in range"

  Scenario: a start date with no end date solves onward, not the entire network
    Given a PyPSA network with 48 hourly snapshots saved as "inputs/net.nc"
    When I run solve on "inputs/net.nc" from "2026-09-02" onward into "outputs/solved"
    Then the solved network "outputs/solved/net.nc" has dispatch for 24 snapshots

  Scenario: the look-ahead is solved but not reported
    Given a PyPSA network with 1440 hourly snapshots saved as "inputs/twomonth.nc"
    When I run solve on "inputs/twomonth.nc" from "2026-09-01" to "2026-09-30" into "outputs/solved"
    Then the solved network "outputs/solved/twomonth.nc" has dispatch for 720 snapshots
    And the solved network "outputs/solved/twomonth.nc" has no dispatch on "2026-10-05"
    And the solved network "outputs/solved/twomonth.nc" has no bus price on "2026-10-05"
    And the solved network "outputs/solved/twomonth.nc" marks "2026-09-15" as reported
    And the solved network "outputs/solved/twomonth.nc" marks "2026-10-05" as not reported

  Scenario: the look-ahead changes what the reported month itself dispatches
    Without a look-ahead, storage has no reason to hold charge back at a month's end,
    since nothing beyond the solved horizon exists to save it for: it charges only enough
    to cover the reported month itself. With the look-ahead attached, the same solve on
    the month's last day sees that cheap generation is unavailable just after the month
    ends, so it charges storage harder that day to cover the need it can now see coming -
    and that difference shows up in the reported month's own dispatch, not just the
    discarded look-ahead's.
    Given a PyPSA network
    And the network has 6 snapshots starting 2026-09-29 at 1440 minute intervals
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network contains generator "cheap" on "bus_1" carrier "gas" p_nom 100.0 marginal_cost 1.0 p_max_pu_series 1 1 0 0 0 0
    And the network contains generator "expensive" on "bus_1" carrier "gas" p_nom 100.0 marginal_cost 100.0
    And the network contains load "load_1" on "bus_1" with static p_set 10.0
    And the network contains storage unit "batt" on "bus_1" carrier "battery" p_nom 50.0 p_min_pu -1.0 max_hours 10.0
    And the network is saved as "inputs/lookahead_storage.nc"
    When I run solve on "inputs/lookahead_storage.nc" from "2026-09-29" to "2026-09-30" into "outputs/solved"
    Then the solved network "outputs/solved/lookahead_storage.nc" has generator "cheap" dispatch 10 50 0 0 0 0

  Scenario: a month with no data of its own is not solved just because its look-ahead has some
    A request for a month the network has nothing in must not be treated as satisfiable just
    because the two weeks beyond that month happen to contain data - the look-ahead exists to
    extend a real month, not manufacture one out of nothing.
    Given a PyPSA network
    And the network has 120 snapshots starting 2026-10-01 at 60 minute intervals
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network contains generator "gen" on "bus_1" carrier "gas" p_nom 100.0 marginal_cost 10.0
    And the network contains load "load_1" on "bus_1" with static p_set 50.0
    And the network is saved as "inputs/october_only.nc"
    When I run solve on "inputs/october_only.nc" from "2026-09-01" to "2026-09-30" into "outputs/solved"
    Then the file "outputs/solved/october_only.nc" does not exist
    And the printed output contains "no snapshots in range"

  Scenario: the reported objective does not double-count the look-ahead overlap
    Consecutive months' look-aheads overlap: the first month's solve reaches two weeks into
    the second, and the second month solves that same fortnight again as part of its own
    month. The reported objective must count each day once, not sum both windows' full
    solved cost.
    Given a PyPSA network
    And the network has 61 snapshots starting 2026-09-01 at 1440 minute intervals
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network contains generator "gen" on "bus_1" carrier "gas" p_nom 100.0 marginal_cost 1.0
    And the network contains load "load_1" on "bus_1" with static p_set 10.0
    And the network is saved as "inputs/twomonth_cost.nc"
    When I run solve on "inputs/twomonth_cost.nc" from "2026-09-01" to "2026-10-31" into "outputs/solved"
    Then the printed output contains "objective=610"

  Scenario: unit commitment defaults to exact, forcing a committable generator fully on or off
    "gen" only produces between 50 MW (its 100 MW p_nom times p_min_pu 0.5) and 100 MW once
    committed, which exceeds the 30 MW load, so the exact treatment's binary on/off status
    cannot let it serve any of that load: on overshoots, off produces nothing. The load
    must instead be served entirely by the expensive uncommitted "backup" generator.
    Given a PyPSA network
    And the network has 1 snapshots starting 2026-09-01 at 60 minute intervals
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network contains generator "gen" on "bus_1" carrier "gas" p_nom 100.0 marginal_cost 1.0 p_min_pu 0.5 committable True
    And the network contains generator "backup" on "bus_1" carrier "gas" p_nom 100.0 marginal_cost 100.0
    And the network contains load "load_1" on "bus_1" with static p_set 30.0
    And the network is saved as "inputs/uc_exact.nc"
    When I run solve on "inputs/uc_exact.nc" from "2026-09-01" to "2026-09-01" with unit commitment "exact" into "outputs/solved"
    Then the solve reported success
    And the solved network "outputs/solved/uc_exact.nc" has generator "gen" dispatch 0
    And the solved network "outputs/solved/uc_exact.nc" has generator "backup" dispatch 30

  Scenario: unit commitment linearised relaxes the same generator to serve the load directly
    Linearised treats "gen"'s on/off status as a continuous fraction rather than a binary, so
    it can commit to a small enough fraction that its scaled minimum output no longer exceeds
    the 30 MW load. The cheap generator then serves the load directly instead of the solve
    falling back to the expensive "backup" generator, unlike the exact treatment above.
    Given a PyPSA network
    And the network has 1 snapshots starting 2026-09-01 at 60 minute intervals
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network contains generator "gen" on "bus_1" carrier "gas" p_nom 100.0 marginal_cost 1.0 p_min_pu 0.5 committable True
    And the network contains generator "backup" on "bus_1" carrier "gas" p_nom 100.0 marginal_cost 100.0
    And the network contains load "load_1" on "bus_1" with static p_set 30.0
    And the network is saved as "inputs/uc_linearised.nc"
    When I run solve on "inputs/uc_linearised.nc" from "2026-09-01" to "2026-09-01" with unit commitment "linearised" into "outputs/solved"
    Then the solve reported success
    And the solved network "outputs/solved/uc_linearised.nc" has generator "gen" dispatch 30
    And the solved network "outputs/solved/uc_linearised.nc" has generator "backup" dispatch 0

  Scenario: a non-optimal window is reported, not crashed
    A window whose load exceeds every generator's available capacity in one hour is
    infeasible. That must be reported plainly rather than raising, so one bad window does
    not kill an entire ensemble run, and an unsolved window has no dispatch to cost.
    Given a PyPSA network
    And the network has 4 snapshots starting 2026-09-01 at 60 minute intervals
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network contains generator "gen" on "bus_1" carrier "gas" p_nom 100.0 marginal_cost 1.0 p_max_pu_series 1 1 0 1
    And the network contains load "load_1" on "bus_1" with static p_set 50.0
    And the network is saved as "inputs/infeasible.nc"
    When I run solve on "inputs/infeasible.nc" from "2026-09-01" to "2026-09-01" into "outputs/solved"
    Then the printed output contains "status=infeasible"

  Scenario: a negative look-ahead is refused before any network is opened
    Given a PyPSA network with 48 hourly snapshots saved as "inputs/net.nc"
    When I run solve on "inputs/net.nc" from "2026-09-01" to "2026-09-02" in "month" windows with a -5 day look-ahead into "outputs/solved"
    Then the printed output contains "look-ahead must be a whole number of days or zero, got -5"
    And the file "outputs/solved/net.nc" does not exist

  Scenario: a range that ends before it starts is refused rather than solving nothing
    Given a PyPSA network with 48 hourly snapshots saved as "inputs/net.nc"
    When I run solve on "inputs/net.nc" from "2026-09-30" to "2026-09-01" into "outputs/solved"
    Then the printed output contains "start must not be later than end, got 2026-09-30 to 2026-09-01"
    And the file "outputs/solved/net.nc" does not exist
