@slow @fork_unsafe
Feature: Sienna to PyPSA Pipeline translates Sienna generators to PyPSA Generator rows
  The step reads generator rows from the staged Sienna system, dispatches on
  sienna_type, and emits one PyPSA Generator row per source component. Static
  fields are inverted from the forward PyPSA -> Sienna mappings: base_power ->
  p_nom, rating -> p_max_pu, active_power_limits.min / base_power -> p_min_pu,
  the variable cost proportional term -> marginal_cost, and (prime_mover_type,
  fuel_type) -> carrier. The ext sidecar overrides where present: an ext carrier
  replaces the derived carrier, and ext committable sets a thermal committable
  (otherwise it is non-committable).

  Scenario: a coal ThermalStandard becomes a non-committable PyPSA Generator
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a ThermalStandard "coal_1" on bus "node_a" with base_power 500.0 rating 1.0 active_power_min 100.0 active_power_max 500.0 marginal_cost 25.0 prime_mover "ST" fuel "COAL"
    And the system is saved as "inputs/thermal.json"
    When I run translate against "inputs/thermal.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 1 generator
    And the PyPSA network "outputs/network.nc" generator "coal_1" has bus "node_a"
    And the PyPSA network "outputs/network.nc" generator "coal_1" has carrier "coal"
    And the PyPSA network "outputs/network.nc" generator "coal_1" attribute "p_nom" is 500.0
    And the PyPSA network "outputs/network.nc" generator "coal_1" attribute "p_max_pu" is 1.0
    And the PyPSA network "outputs/network.nc" generator "coal_1" attribute "p_min_pu" is 0.2
    And the PyPSA network "outputs/network.nc" generator "coal_1" attribute "marginal_cost" is 25.0
    And the PyPSA network "outputs/network.nc" generator "coal_1" is not committable
    And the file "decisions.md" contains "| `sienna.ThermalStandard.coal_1.base_power` = 500.0 MVA | `pypsa.Generator.coal_1.p_nom` = 500.0 MW | direct |  | sienna-to-pypsa | sienna_to_pypsa_map_generators |"
    And the file "decisions.md" contains "| `sienna.ThermalStandard.coal_1.rating` = 1.0 | `pypsa.Generator.coal_1.p_max_pu` = 1.0 | direct |  | sienna-to-pypsa | sienna_to_pypsa_map_generators |"
    And the file "decisions.md" contains "| `sienna.ThermalStandard.coal_1.active_power_limits.min` = 100.0 MW | `pypsa.Generator.coal_1.p_min_pu` = 0.2 | active_power_limits.min / base_power |  | sienna-to-pypsa | sienna_to_pypsa_map_generators |"
    And the file "decisions.md" contains "| `sienna.ThermalStandard.coal_1.operation_cost` = 25.0 | `pypsa.Generator.coal_1.marginal_cost` = 25.0 | variable cost proportional term |  | sienna-to-pypsa | sienna_to_pypsa_map_generators |"
    And the file "decisions.md" contains "| `sienna.ThermalStandard.coal_1.prime_mover_type` = ST<br>`sienna.ThermalStandard.coal_1.fuel_type` = COAL | `pypsa.Generator.coal_1.carrier` = coal | (prime_mover_type, fuel_type) -> carrier |  | sienna-to-pypsa | sienna_to_pypsa_map_generators |"

  Scenario: a ThermalStandard with an ext carrier overrides the derived carrier
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a ThermalStandard "coal_1" on bus "node_a" with base_power 500.0 rating 1.0 active_power_min 100.0 active_power_max 500.0 marginal_cost 25.0 prime_mover "ST" fuel "COAL"
    And the ThermalStandard "coal_1" has ext carrier "lignite"
    And the system is saved as "inputs/thermal_ext_carrier.json"
    When I run translate against "inputs/thermal_ext_carrier.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "coal_1" has carrier "lignite"
    And the file "decisions.md" contains "| `sienna.ThermalStandard.coal_1.extensions.carrier` = lignite | `pypsa.Generator.coal_1.carrier` = lignite | extensions.carrier (PyPSA round-trip) |  | sienna-to-pypsa | sienna_to_pypsa_map_generators |"

  Scenario: a ThermalStandard committable in ext becomes a committable PyPSA Generator
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a ThermalStandard "coal_1" on bus "node_a" with base_power 500.0 rating 1.0 active_power_min 100.0 active_power_max 500.0 marginal_cost 25.0 prime_mover "ST" fuel "COAL"
    And the ThermalStandard "coal_1" is committable in ext
    And the system is saved as "inputs/thermal_committable.json"
    When I run translate against "inputs/thermal_committable.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "coal_1" is committable
    And the file "decisions.md" contains "| `sienna.ThermalStandard.coal_1.extensions.committable` = True | `pypsa.Generator.coal_1.committable` = True | extensions.committable (PyPSA round-trip) |  | sienna-to-pypsa | sienna_to_pypsa_map_generators |"

  Scenario: a solar RenewableDispatch becomes a PyPSA Generator
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a RenewableDispatch "solar_1" on bus "node_a" with base_power 200.0 rating 0.9 active_power 0.0 marginal_cost 0.0 prime_mover "PVe"
    And the system is saved as "inputs/solar.json"
    When I run translate against "inputs/solar.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 1 generator
    And the PyPSA network "outputs/network.nc" generator "solar_1" has bus "node_a"
    And the PyPSA network "outputs/network.nc" generator "solar_1" has carrier "solar"
    And the PyPSA network "outputs/network.nc" generator "solar_1" attribute "p_nom" is 200.0
    And the PyPSA network "outputs/network.nc" generator "solar_1" attribute "p_max_pu" is 0.9
    And the file "decisions.md" contains "| `sienna.RenewableDispatch.solar_1.base_power` = 200.0 MVA | `pypsa.Generator.solar_1.p_nom` = 200.0 MW | direct |  | sienna-to-pypsa | sienna_to_pypsa_map_generators |"
    And the file "decisions.md" contains "| `sienna.RenewableDispatch.solar_1.rating` = 0.9 | `pypsa.Generator.solar_1.p_max_pu` = 0.9 | direct |  | sienna-to-pypsa | sienna_to_pypsa_map_generators |"
    And the file "decisions.md" contains "| `sienna.RenewableDispatch.solar_1.prime_mover_type` = PVe | `pypsa.Generator.solar_1.carrier` = solar | (sienna_type, prime_mover_type) -> carrier |  | sienna-to-pypsa | sienna_to_pypsa_map_generators |"

  Scenario: a solar-rooftop RenewableNonDispatch becomes a PyPSA Generator with zero marginal cost
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a RenewableNonDispatch "rooftop_1" on bus "node_a" with base_power 50.0 rating 0.8 active_power 0.0 prime_mover "PVe"
    And the system is saved as "inputs/rooftop.json"
    When I run translate against "inputs/rooftop.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 1 generator
    And the PyPSA network "outputs/network.nc" generator "rooftop_1" has carrier "solar-rooftop"
    And the PyPSA network "outputs/network.nc" generator "rooftop_1" attribute "p_nom" is 50.0
    And the PyPSA network "outputs/network.nc" generator "rooftop_1" attribute "p_max_pu" is 0.8
    And the PyPSA network "outputs/network.nc" generator "rooftop_1" attribute "marginal_cost" is 0.0
    And the file "decisions.md" contains "| `sienna.RenewableNonDispatch.rooftop_1.prime_mover_type` = PVe | `pypsa.Generator.rooftop_1.carrier` = solar-rooftop | (sienna_type, prime_mover_type) -> carrier |  | sienna-to-pypsa | sienna_to_pypsa_map_generators |"

  Scenario: a RenewableDispatch with a max_active_power series produces a p_max_pu time series
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a RenewableDispatch "solar_1" on bus "node_a" with base_power 200.0 rating 1.0 active_power 0.0 marginal_cost 0.0 prime_mover "PVe"
    And the RenewableDispatch "solar_1" has a max_active_power series 0.1 0.8 0.5
    And the system is saved as "inputs/solar_ts.json"
    When I run translate against "inputs/solar_ts.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 1 generator
    And the PyPSA network "outputs/network.nc" generator "solar_1" has a p_max_pu time series 0.1 0.8 0.5

  Scenario: a RenewableDispatch max_active_power series is scaled by the rating
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a RenewableDispatch "wind_1" on bus "node_a" with base_power 200.0 rating 0.9 active_power 0.0 marginal_cost 0.0 prime_mover "WT"
    And the RenewableDispatch "wind_1" has a max_active_power series 0.5 1.0
    And the system is saved as "inputs/wind_ts.json"
    When I run translate against "inputs/wind_ts.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "wind_1" has a p_max_pu time series 0.45 0.9

  Scenario: a ThermalStandard max_active_power series is scaled into a p_max_pu time series
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a ThermalStandard "ccgt_1" on bus "node_a" with base_power 500.0 rating 1.0 active_power_min 0.0 active_power_max 400.0 marginal_cost 25.0 prime_mover "ST" fuel "COAL"
    And the ThermalStandard "ccgt_1" has a max_active_power series 0.5 1.0
    And the system is saved as "inputs/thermal_ts.json"
    When I run translate against "inputs/thermal_ts.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "ccgt_1" has a p_max_pu time series 0.4 0.8

  Scenario: a ThermalStandard ramp_limits in MW/min becomes PyPSA per-snapshot ramp limits
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a ThermalStandard "coal_1" on bus "node_a" with base_power 100.0 rating 1.0 active_power_min 0.0 active_power_max 100.0 marginal_cost 25.0 prime_mover "ST" fuel "COAL"
    And the ThermalStandard "coal_1" has ramp_limits up 0.5 down 0.3
    And the system is saved as "inputs/thermal_ramp.json"
    When I run translate against "inputs/thermal_ramp.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "coal_1" attribute "ramp_limit_up" is 0.3
    And the PyPSA network "outputs/network.nc" generator "coal_1" attribute "ramp_limit_down" is 0.18
    And the file "decisions.md" contains "ramp_limits (MW/min) * resolution / base_power -> ramp_limit (pu/snapshot)"

  Scenario: a ThermalStandard time_limits in hours become PyPSA min up/down snapshots
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a ThermalStandard "coal_1" on bus "node_a" with base_power 100.0 rating 1.0 active_power_min 0.0 active_power_max 100.0 marginal_cost 25.0 prime_mover "ST" fuel "COAL"
    And the ThermalStandard "coal_1" has time_limits up 2.0 down 1.0
    And the system is saved as "inputs/thermal_time_limits.json"
    When I run translate against "inputs/thermal_time_limits.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "coal_1" attribute "min_up_time" is 2.0
    And the PyPSA network "outputs/network.nc" generator "coal_1" attribute "min_down_time" is 1.0
    And the file "decisions.md" contains "time_limits (hours) * 60 / resolution -> min_up_time/min_down_time (snapshots)"

  Scenario: a ThermalStandard time_at_status in hours becomes PyPSA up_time_before snapshots
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a ThermalStandard "coal_1" on bus "node_a" with base_power 100.0 rating 1.0 active_power_min 0.0 active_power_max 100.0 marginal_cost 25.0 prime_mover "ST" fuel "COAL"
    And the ThermalStandard "coal_1" has time_at_status 5.0
    And the system is saved as "inputs/thermal_time_at_status.json"
    When I run translate against "inputs/thermal_time_at_status.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "coal_1" attribute "up_time_before" is 5.0
    And the file "decisions.md" contains "time_at_status (hours) * 60 / resolution -> up_time_before (snapshots)"

  Scenario: a ThermalStandard time_at_status sentinel maps up_time_before back to zero
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a ThermalStandard "coal_1" on bus "node_a" with base_power 100.0 rating 1.0 active_power_min 0.0 active_power_max 100.0 marginal_cost 25.0 prime_mover "ST" fuel "COAL"
    And the ThermalStandard "coal_1" has time_at_status 10000.0
    And the system is saved as "inputs/thermal_status_sentinel.json"
    When I run translate against "inputs/thermal_status_sentinel.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "coal_1" attribute "up_time_before" is 0.0
    And the file "decisions.md" contains "time_at_status = 10000.0 sentinel; up_time_before defaults to 0"

  Scenario: a ThermalStandard start_up and shut_down costs round-trip to PyPSA
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a ThermalStandard "coal_1" on bus "node_a" with base_power 100.0 rating 1.0 active_power_min 0.0 active_power_max 100.0 marginal_cost 25.0 prime_mover "ST" fuel "COAL"
    And the ThermalStandard "coal_1" has start_up_cost 1000.0 shut_down_cost 500.0
    And the system is saved as "inputs/thermal_start_stop.json"
    When I run translate against "inputs/thermal_start_stop.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "coal_1" attribute "start_up_cost" is 1000.0
    And the PyPSA network "outputs/network.nc" generator "coal_1" attribute "shut_down_cost" is 500.0
    And the file "decisions.md" contains "operation_cost.start_up -> start_up_cost"
    And the file "decisions.md" contains "operation_cost.shut_down -> shut_down_cost"

  Scenario: a ThermalStandard p_nom_extendable in ext round-trips to PyPSA
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a ThermalStandard "coal_1" on bus "node_a" with base_power 100.0 rating 1.0 active_power_min 0.0 active_power_max 100.0 marginal_cost 25.0 prime_mover "ST" fuel "COAL"
    And the ThermalStandard "coal_1" is p_nom_extendable in ext
    And the system is saved as "inputs/thermal_extendable.json"
    When I run translate against "inputs/thermal_extendable.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "coal_1" is extendable
    And the file "decisions.md" contains "| `sienna.ThermalStandard.coal_1.extensions.p_nom_extendable` = True | `pypsa.Generator.coal_1.p_nom_extendable` = True | extensions.p_nom_extendable (PyPSA round-trip) |  | sienna-to-pypsa | sienna_to_pypsa_map_generators |"

  Scenario: a RenewableDispatch p_nom_extendable in ext round-trips to PyPSA
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a RenewableDispatch "solar_1" on bus "node_a" with base_power 200.0 rating 0.9 active_power 0.0 marginal_cost 0.0 prime_mover "PVe"
    And the RenewableDispatch "solar_1" is p_nom_extendable in ext
    And the system is saved as "inputs/solar_extendable.json"
    When I run translate against "inputs/solar_extendable.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "solar_1" is extendable

  Scenario: a ThermalStandard without ext p_nom_extendable records a translator default
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a ThermalStandard "coal_1" on bus "node_a" with base_power 100.0 rating 1.0 active_power_min 0.0 active_power_max 100.0 marginal_cost 25.0 prime_mover "ST" fuel "COAL"
    And the system is saved as "inputs/thermal_default_extendable.json"
    When I run translate against "inputs/thermal_default_extendable.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "coal_1" is not extendable
    And the file "decisions.md" contains "| `pypsa.Generator.coal_1.p_nom_extendable` = False |  | no ext.p_nom_extendable; p_nom_extendable defaults to False | sienna-to-pypsa | sienna_to_pypsa_map_generators |"

  Scenario: a RenewableDispatch without ext p_nom_extendable records a translator default
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a RenewableDispatch "solar_1" on bus "node_a" with base_power 200.0 rating 0.9 active_power 0.0 marginal_cost 0.0 prime_mover "PVe"
    And the system is saved as "inputs/solar_default_extendable.json"
    When I run translate against "inputs/solar_default_extendable.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "solar_1" is not extendable
    And the file "decisions.md" contains "| `pypsa.Generator.solar_1.p_nom_extendable` = False |  | no ext.p_nom_extendable; p_nom_extendable defaults to False | sienna-to-pypsa | sienna_to_pypsa_map_generators |"

  Scenario: an oil ThermalStandard derives the PyPSA oil carrier
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a ThermalStandard "oil_1" on bus "node_a" with base_power 100.0 rating 1.0 active_power_min 0.0 active_power_max 100.0 marginal_cost 80.0 prime_mover "GT" fuel "DISTILLATE_FUEL_OIL"
    And the system is saved as "inputs/oil.json"
    When I run translate against "inputs/oil.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "oil_1" has carrier "oil"

  Scenario: a biomass ThermalStandard derives the PyPSA biomass carrier
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a ThermalStandard "bio_1" on bus "node_a" with base_power 100.0 rating 1.0 active_power_min 0.0 active_power_max 100.0 marginal_cost 20.0 prime_mover "ST" fuel "OTHER_BIOMASS_SOLIDS"
    And the system is saved as "inputs/biomass.json"
    When I run translate against "inputs/biomass.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "bio_1" has carrier "biomass"

  Scenario: a geothermal ThermalStandard derives the PyPSA geothermal carrier
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a ThermalStandard "geo_1" on bus "node_a" with base_power 100.0 rating 1.0 active_power_min 0.0 active_power_max 100.0 marginal_cost 0.0 prime_mover "BT" fuel "GEOTHERMAL"
    And the system is saved as "inputs/geothermal.json"
    When I run translate against "inputs/geothermal.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "geo_1" has carrier "geothermal"

  Scenario: a run-of-river RenewableDispatch derives the PyPSA ror carrier
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a RenewableDispatch "ror_1" on bus "node_a" with base_power 150.0 rating 1.0 active_power 0.0 marginal_cost 0.0 prime_mover "HY"
    And the system is saved as "inputs/ror.json"
    When I run translate against "inputs/ror.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "ror_1" has carrier "ror"

  Scenario: an ext carrier recovers a renewable carrier that shares a prime mover
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a RenewableDispatch "offwind_1" on bus "node_a" with base_power 200.0 rating 1.0 active_power 0.0 marginal_cost 0.0 prime_mover "WS"
    And the RenewableDispatch "offwind_1" has ext carrier "offwind-dc"
    And the system is saved as "inputs/offwind_dc.json"
    When I run translate against "inputs/offwind_dc.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "offwind_1" has carrier "offwind-dc"

  Scenario: a zero-capacity RenewableDispatch yields p_min_pu 0 without dividing by zero
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a RenewableDispatch "solar_0" on bus "node_a" with base_power 0.0 rating 1.0 active_power 0.0 marginal_cost 0.0 prime_mover "PVe"
    And the system is saved as "inputs/solar_zero.json"
    When I run translate against "inputs/solar_zero.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "solar_0" attribute "p_min_pu" is 0.0
    And the PyPSA network "outputs/network.nc" generator "solar_0" attribute "p_nom" is 0.0

  Scenario: a series covering fewer snapshots than the network is left off rather than reaching the sink
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a RenewableDispatch "solar_1" on bus "node_a" with base_power 200.0 rating 1.0 active_power 0.0 marginal_cost 0.0 prime_mover "PVe"
    And the RenewableDispatch "solar_1" has a max_active_power series 0.1 0.8 0.5
    And the system contains a RenewableDispatch "solar_2" on bus "node_a" with base_power 200.0 rating 1.0 active_power 0.0 marginal_cost 0.0 prime_mover "PVe"
    And the RenewableDispatch "solar_2" has a max_active_power series 0.2 0.4
    And the system is saved as "inputs/short_series.json"
    When I run translate against "inputs/short_series.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "solar_1" has a p_max_pu time series 0.1 0.8 0.5
    And the PyPSA network "outputs/network.nc" generator "solar_2" has no p_max_pu time series
    And the log contains "the snapshot window holds 3 steps"
    And the log contains "Every TimeSeriesAssociation in one system has to cover the same snapshots"
    And the file "decisions.md" contains "the profile carries 2 values but the snapshot window holds 3, so the component keeps its static value instead"
