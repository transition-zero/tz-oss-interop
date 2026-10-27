@slow @fork_unsafe
Feature: Sienna to PyPSA maps or relays each field of the extensions sidecar
  A field of a sidecar record either becomes a PyPSA attribute or travels on unchanged to the
  PyPSA sidecar, and decisions.md says which for each field. The representative periods become
  the snapshot weightings, and an annual energy bound applies where the snapshots count for a
  whole year.

  The invented system below has two buses, a gas plant and a load with a profile of four hours,
  which starts on 1 January 2020.

  Background:
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a bus "node_b"
    And the system contains a ThermalStandard "gas" on bus "node_a" with base_power 200 rating 1 active_power_min 0 active_power_max 200 marginal_cost 25 prime_mover "CC" fuel "NATURAL_GAS"
    And the system contains a PowerLoad "load" on bus "node_b" with max_active_power 100
    And the PowerLoad "load" has a max_active_power series 0.5 1 1 0.5

  Scenario: Each snapshot counts for the weight of the representative period that holds it
    Given the system has a representative period "day_1" from "2020-01-01T00:00:00" of 2 hours with weight 100
    And the system has a representative period "day_2" from "2020-01-01T02:00:00" of 2 hours with weight 50
    And the system is saved as "inputs/periods.json"
    When I run translate against "inputs/periods.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has snapshot weightings "objective" of 100 100 50 50
    And the PyPSA network "outputs/network.nc" has snapshot weightings "generators" of 100 100 50 50
    And the PyPSA network "outputs/network.nc" has snapshot weightings "stores" of 1 1 1 1
    And the file "outputs/extensions.json" parses as JSON representative_period extension record for "day_2" having "weight" set to 50.0
    And the file "decisions.md" contains "| `sienna.representative_period.day_1.weight` = 100.0 | `pypsa.snapshot_weightings.2020-01-01T00:00:00 to 2020-01-01T01:00:00.objective` = 100.0 h |"
    And the file "decisions.md" contains "| `sienna.representative_period.day_2.extensions.hours` = 2 | `pypsa.representative_period.day_2.extensions.hours` = 2 | relayed unchanged to extensions.json, as PyPSA has no attribute for it |"

  Scenario: A snapshot that no representative period holds counts once
    Given the system has a representative period "day_1" from "2020-01-01T00:00:00" of 2 hours with weight 100
    And the system is saved as "inputs/half.json"
    When I run translate against "inputs/half.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has snapshot weightings "objective" of 100 100 1 1
    And the log contains "2 snapshot(s) fall in no representative period, so each counts once: 2020-01-01T02:00:00"

  Scenario: An annual energy bound applies the value of the year where the snapshots count for that whole year
    The one period of four hours occurs 2190 times, so the snapshots count for 8760 h of 2020.
    Given the system has a representative period "year" from "2020-01-01T00:00:00" of 4 hours with weight 2190
    And the ThermalStandard "gas" has ext "e_sum_min" set to {"2020": 1000.0, "2021": 2000.0}
    And the ThermalStandard "gas" has ext "e_sum_max" set to {"2020": 5000.0}
    And the system is saved as "inputs/bounds.json"
    When I run translate against "inputs/bounds.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "gas" attribute "e_sum_min" is 1000.0
    And the PyPSA network "outputs/network.nc" generator "gas" attribute "e_sum_max" is 5000.0
    And the file "outputs/extensions.json" parses as JSON generator extension record for "gas" having "e_sum_min" set to {"2020": 1000.0, "2021": 2000.0}
    And the file "decisions.md" contains "| `sienna.ThermalStandard.gas.extensions.e_sum_min` = 1000.0 MWh | `pypsa.Generator.gas.e_sum_min` = 1000.0 MWh | the value of 2020, the year of the snapshots, which count for 8760.0 h, the whole year;"

  Scenario: An annual energy bound stays in extensions.json where the snapshots count for less than a year
    Given the ThermalStandard "gas" has ext "e_sum_max" set to {"2020": 5000.0}
    And the system is saved as "inputs/part_year.json"
    When I run translate against "inputs/part_year.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "gas" attribute "e_sum_max" is inf
    And the file "outputs/extensions.json" parses as JSON generator extension record for "gas" having "e_sum_max" set to {"2020": 5000.0}
    And the log contains "1 annual energy bound(s) stay in extensions.json and bind nothing, because the snapshots count for 4.0 h, not one whole year: gas.e_sum_max"
    And the file "decisions.md" contains "| `sienna.ThermalStandard.gas.extensions.e_sum_max` |  |  | the snapshots count for 4.0 h of 2020, not the whole year, so the annual bound does not apply to them; extensions.json keeps it |"

  Scenario: An annual energy bound stays in extensions.json where the snapshots count for neither length of a year
    The one period of four hours occurs 2192.5 times, so the snapshots count for 8770 h, which
    is neither 8760 h nor 8784 h.
    Given the system has a representative period "year" from "2020-01-01T00:00:00" of 4 hours with weight 2192.5
    And the ThermalStandard "gas" has ext "e_sum_max" set to {"2020": 5000.0}
    And the system is saved as "inputs/odd_year.json"
    When I run translate against "inputs/odd_year.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "gas" attribute "e_sum_max" is inf
    And the log contains "because the snapshots count for 8770.0 h, not one whole year: gas.e_sum_max"

  Scenario: The fields of a generator record that PyPSA has no attribute for travel on unchanged
    Given the ThermalStandard "gas" has ext carrier "gas"
    And the ThermalStandard "gas" has ext emission rate 0.4 t/MWh of "CO2"
    And the ThermalStandard "gas" has ext "max_growth" set to {"2020": 0.0}
    And the ThermalStandard "gas" has ext "operating_modes" set to [{"mode": "2", "variable_cost": 3.0}]
    And the system is saved as "inputs/generator.json"
    When I run translate against "inputs/generator.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "gas" has carrier "gas"
    And the file "outputs/extensions.json" parses as JSON generator extension record for "gas" having "emission_rates_t_per_mwh" set to {"CO2": 0.4}
    And the file "outputs/extensions.json" parses as JSON generator extension record for "gas" having "max_growth" set to {"2020": 0.0}
    And the file "outputs/extensions.json" parses as JSON generator extension record for "gas" having "operating_modes" set to [{"mode": "2", "variable_cost": 3.0}]
    And the file "outputs/extensions.json" parses as JSON generator extension record for "gas" without field "carrier"
    And the file "decisions.md" contains "| `sienna.generator.gas.extensions.max_growth` = {'2020': 0.0} | `pypsa.generator.gas.extensions.max_growth` = {'2020': 0.0} | relayed unchanged to extensions.json, as PyPSA has no attribute for it |  | sienna-to-pypsa | sienna_to_pypsa_map_generators |"

  Scenario: A floor that the sidecar states wins over the rating of an extendable plant
    Given the ThermalStandard "gas" is p_nom_extendable in ext
    And the ThermalStandard "gas" has ext "p_nom_min" set to 50.0
    And the system is saved as "inputs/floor.json"
    When I run translate against "inputs/floor.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "gas" attribute "p_nom_min" is 50.0
    And the file "decisions.md" contains "| `sienna.ThermalStandard.gas.extensions.p_nom_min` = 50.0 MW | `pypsa.Generator.gas.p_nom_min` = 50.0 MW | extensions.p_nom_min (PyPSA round-trip) |"

  Scenario: A record whose every field maps is not written to the PyPSA sidecar
    Given the ThermalStandard "gas" has ext carrier "gas"
    And the system is saved as "inputs/mapped.json"
    When I run translate against "inputs/mapped.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the file "outputs/extensions.json" parses as JSON with no generator extension record for "gas"

  Scenario: The generator record of a hydro plant travels on, as the plant becomes a storage unit
    Given the system contains a HydroDispatch "hydro" on bus "node_a" with base_power 100 rating 1 active_power_min 0 active_power_max 100 marginal_cost 5
    And the HydroDispatch "hydro" has ext "category" set to "hydro-dam"
    And the system is saved as "inputs/hydro.json"
    When I run translate against "inputs/hydro.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the file "outputs/extensions.json" parses as JSON generator extension record for "hydro" having "category" set to "hydro-dam"
    And the file "decisions.md" contains "| `sienna.generator.hydro.extensions.category` = hydro-dam | `pypsa.generator.hydro.extensions.category` = hydro-dam |"

  Scenario: A line keeps its cost, its loss and its hourly availability, and its other modes travel on
    The record states the availability factor 0.5, so the series of the capacity factor is
    applied at half its value.
    Given the system contains an HVDC line "line" from "node_a" to "node_b" with p_nom 500.0 efficiency 0.95
    And the TwoTerminalGenericHVDCLine "line" has ext "marginal_cost" set to 10.0
    And the TwoTerminalGenericHVDCLine "line" has ext "p_max_pu" set to 0.5
    And the HVDC line "line" has an ext p_max_pu series 1 0.5 0 1
    And the TwoTerminalGenericHVDCLine "line" has ext "operating_modes" set to [{"mode": "2", "variable_cost": 3.0}]
    And the system is saved as "inputs/line.json"
    When I run translate against "inputs/line.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" link "line" attribute "marginal_cost" is 10.0
    And the PyPSA network "outputs/network.nc" link "line" attribute "efficiency" is 0.95
    And the PyPSA network "outputs/network.nc" link "line" attribute "p_nom" is 1000.0
    And the PyPSA network "outputs/network.nc" link "line" has a p_max_pu time series 0.5 0.25 0 0.5
    And the file "outputs/extensions.json" parses as JSON controllable_line extension record for "line" having "operating_modes" set to [{"mode": "2", "variable_cost": 3.0}]
    And the file "outputs/extensions.json" parses as JSON controllable_line extension record for "line" without field "marginal_cost"

  Scenario: A line that flows both ways and loses energy becomes two one-way links
    PyPSA applies one efficiency and one cost to both directions of a link, so the flow back
    goes on a reverse link from node_b to node_a, which loses and pays as the forward link does.
    Given the system contains an HVDC line "line" from "node_a" to "node_b" with p_nom 500.0 efficiency 0.95
    And the TwoTerminalGenericHVDCLine "line" has ext "marginal_cost" set to 10.0
    And the TwoTerminalGenericHVDCLine "line" has ext "p_min_pu" set to -0.8
    And the HVDC line "line" has an ext p_max_pu series 1 0.5 0 1
    And the system is saved as "inputs/two_way.json"
    When I run translate against "inputs/two_way.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 2 links
    And the PyPSA network "outputs/network.nc" link "line" attribute "p_min_pu" is 0.0
    And the PyPSA network "outputs/network.nc" link "line reverse" has bus0 "node_b"
    And the PyPSA network "outputs/network.nc" link "line reverse" has bus1 "node_a"
    And the PyPSA network "outputs/network.nc" link "line reverse" attribute "p_nom" is 500.0
    And the PyPSA network "outputs/network.nc" link "line reverse" attribute "p_min_pu" is 0.0
    And the PyPSA network "outputs/network.nc" link "line reverse" attribute "efficiency" is 0.95
    And the PyPSA network "outputs/network.nc" link "line reverse" attribute "marginal_cost" is 10.0
    And the PyPSA network "outputs/network.nc" link "line reverse" has a p_max_pu time series 0.8 0.4 0 0.8
    And the file "decisions.md" contains "| `sienna.TwoTerminalGenericHVDCLine.line.active_power_limits_from.min` = -400.0 MW | `pypsa.Link.line.p_min_pu` = 0.0 | a link that flows both ways and loses energy or costs money becomes two one-way links"
    And the file "decisions.md" contains "| `sienna.TwoTerminalGenericHVDCLine.line.active_power_limits_from.min` = -400.0 MW | `pypsa.Link.line reverse.p_max_pu` = 0.8 |"

  Scenario: An extendable line that flows both ways and loses energy stays one link, and the log says so
    Given the system contains an HVDC line "line" from "node_a" to "node_b" with p_nom 500.0 efficiency 0.95
    And the TwoTerminalGenericHVDCLine "line" has ext "p_min_pu" set to -1.0
    And the HVDC line "line" is extendable in ext
    And the system is saved as "inputs/two_way_extendable.json"
    When I run translate against "inputs/two_way_extendable.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 1 link
    And the PyPSA network "outputs/network.nc" link "line" attribute "p_min_pu" is -1.0
    And the log contains "1 extendable link(s) flow both ways and lose energy or cost money, so each stays one link whose flow back gains what its forward flow loses: line"

  Scenario: A storage keeps its yearly cycle and its build year, and its energy cost travels on
    Given the system contains an EnergyReservoirStorage "battery" on bus "node_b" with base_power 10 storage_capacity 4 initial_level 0 rating 1 input_max 1 output_max 1 efficiency_in 1 efficiency_out 1 discharge_cost 0
    And the EnergyReservoirStorage "battery" has ext "cyclic_state_of_charge_per_period" set to true
    And the EnergyReservoirStorage "battery" has ext "build_year" set to 2015
    And the EnergyReservoirStorage "battery" has ext "energy_overnight_cost" set to 5.0
    And the EnergyReservoirStorage "battery" has ext "p_nom_max" set to 40.0
    And the EnergyReservoirStorage "battery" has ext "overnight_cost_per_mw" set to 1000.0
    And the EnergyReservoirStorage "battery" has ext "discount_rate" set to 0.07
    And the system is saved as "inputs/storage.json"
    When I run translate against "inputs/storage.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" storage unit "battery" has "cyclic_state_of_charge_per_period" set
    And the PyPSA network "outputs/network.nc" storage unit "battery" attribute "build_year" is 2015
    And the PyPSA network "outputs/network.nc" storage unit "battery" attribute "p_nom_max" is 40.0
    And the file "outputs/extensions.json" parses as JSON storage extension record for "battery" having "energy_overnight_cost" set to 5.0
    And the file "decisions.md" contains "| `sienna.EnergyReservoirStorage.battery.extensions.cyclic_state_of_charge_per_period` = True | `pypsa.StorageUnit.battery.cyclic_state_of_charge_per_period` = True | extensions.cyclic_state_of_charge_per_period (PyPSA round-trip) |"
    And the file "decisions.md" contains "| `sienna.EnergyReservoirStorage.battery.extensions.p_nom_max` = 40.0 MW | `pypsa.StorageUnit.battery.p_nom_max` = 40.0 MW | extensions.p_nom_max (PyPSA round-trip) |"
    And the file "decisions.md" contains "| `sienna.EnergyReservoirStorage.battery.extensions.overnight_cost_per_mw` = 1000.0 \$/MW | `pypsa.StorageUnit.battery.overnight_cost` = 1000.0 \$/MW | extensions.overnight_cost_per_mw (PyPSA round-trip) |"
    And the PyPSA network "outputs/network.nc" storage unit "battery" attribute "discount_rate" is 0.07
    And the PyPSA network "outputs/network.nc" passes the PyPSA consistency check

  Scenario: An overnight cost with no discount rate stays in extensions.json, and the network leaves it out
    PyPSA cannot annualise an overnight cost without a discount rate, and refuses a network
    that states one without the other.
    Given the system contains an EnergyReservoirStorage "battery" on bus "node_b" with base_power 10 storage_capacity 4 initial_level 0 rating 1 input_max 1 output_max 1 efficiency_in 1 efficiency_out 1 discharge_cost 0
    And the EnergyReservoirStorage "battery" has ext "overnight_cost_per_mw" set to 1000.0
    And the ThermalStandard "gas" has ext "overnight_cost_per_mw" set to 900.0
    And the system is saved as "inputs/unpriced.json"
    When I run translate against "inputs/unpriced.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" storage unit "battery" states no "overnight_cost"
    And the PyPSA network "outputs/network.nc" generator "gas" states no "overnight_cost"
    And the PyPSA network "outputs/network.nc" passes the PyPSA consistency check
    And the file "outputs/extensions.json" parses as JSON storage extension record for "battery" having "overnight_cost_per_mw" set to 1000.0
    And the file "outputs/extensions.json" parses as JSON generator extension record for "gas" having "overnight_cost_per_mw" set to 900.0
    And the file "decisions.md" contains "| `sienna.EnergyReservoirStorage.battery.extensions.overnight_cost_per_mw` = 1000.0 \$/MW |  |  | the record states no discount_rate, and PyPSA cannot annualise an overnight_cost without one, so the network leaves the cost out; extensions.json keeps it |"
    And the log contains "1 StorageUnit(s) state an overnight cost and no discount rate, and PyPSA cannot annualise the cost without one, so the network leaves the cost out and extensions.json keeps it: battery"
    And the log contains "1 Generator(s) state an overnight cost and no discount rate, and PyPSA cannot annualise the cost without one, so the network leaves the cost out and extensions.json keeps it: gas"

  Scenario: The price of lost load of a bus travels on, and the sign of a load maps
    Given the ACBus "node_b" has ext "value_of_lost_load" set to 9000.0
    And the PowerLoad "load" has ext "sign" set to -1.0
    And the system is saved as "inputs/bus.json"
    When I run translate against "inputs/bus.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the file "outputs/extensions.json" parses as JSON bus extension record for "node_b" having "value_of_lost_load" set to 9000.0
    And the PyPSA network "outputs/network.nc" load "load" attribute "sign" is -1.0
    And the file "decisions.md" contains "| `sienna.PowerLoad.load.extensions.sign` = -1.0 | `pypsa.Load.load.sign` = -1.0 | extensions.sign (PyPSA round-trip) |"

  Scenario: A conversion between two buses becomes a Link, and every other conversion travels on
    Given the system has a conversion extension record "a_to_b" with "bus0" set to "node_a"
    And the system has a conversion extension record "a_to_b" with "bus1" set to "node_b"
    And the system has a conversion extension record "a_to_b" with "p_nom" set to 50.0
    And the system has a conversion extension record "a_to_b" with "efficiency" set to 0.9
    And the system has a conversion extension record "a_to_b" with "marginal_cost" set to 2.0
    And the system has a conversion extension record "a_to_b" with "input_fuel" set to "ELC1"
    And the system has a conversion extension record "a_inside" with "bus0" set to "node_a"
    And the system has a conversion extension record "a_inside" with "bus1" set to "node_a"
    And the system has a conversion extension record "a_inside" with "p_nom" set to 10.0
    And the system has a conversion extension record "R1/R2/ELC" with "bus0" set to "R1/ELC"
    And the system has a conversion extension record "R1/R2/ELC" with "bus1" set to "R2/ELC"
    And the system is saved as "inputs/conversion.json"
    When I run translate against "inputs/conversion.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 1 link
    And the PyPSA network "outputs/network.nc" link "a_to_b" has bus1 "node_b"
    And the PyPSA network "outputs/network.nc" link "a_to_b" attribute "p_nom" is 50.0
    And the PyPSA network "outputs/network.nc" link "a_to_b" attribute "efficiency" is 0.9
    And the PyPSA network "outputs/network.nc" link "a_to_b" attribute "marginal_cost" is 2.0
    And the file "outputs/extensions.json" parses as JSON conversion extension record for "a_to_b" having "input_fuel" set to "ELC1"
    And the file "outputs/extensions.json" parses as JSON conversion extension record for "a_to_b" without field "p_nom"
    And the file "outputs/extensions.json" parses as JSON conversion extension record for "a_inside" having "p_nom" set to 10.0
    And the file "outputs/extensions.json" parses as JSON conversion extension record for "R1/R2/ELC" having "bus0" set to "R1/ELC"
    And the file "decisions.md" contains "| `sienna.conversion.a_to_b.extensions.efficiency` = 0.9 | `pypsa.Link.a_to_b.efficiency` = 0.9 | extensions.efficiency (PyPSA round-trip) |"

  Scenario: A two-way line whose reverse name another line holds stays one link, and the log says so
    The line "line reverse" already exists, so the flow back of "line" cannot take that name.
    Given the system contains an HVDC line "line" from "node_a" to "node_b" with p_nom 500.0 efficiency 0.95
    And the TwoTerminalGenericHVDCLine "line" has ext "p_min_pu" set to -0.8
    And the system contains an HVDC line "line reverse" from "node_b" to "node_a" with p_nom 100.0 efficiency 1.0
    And the system is saved as "inputs/reverse_taken.json"
    When I run translate against "inputs/reverse_taken.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 2 links
    And the PyPSA network "outputs/network.nc" link "line" attribute "p_min_pu" is -0.8
    And the PyPSA network "outputs/network.nc" link "line reverse" attribute "p_nom" is 100.0
    And the log contains "1 link(s) flow both ways and lose energy or cost money, but another link holds the name of their flow back, so each stays one link whose flow back gains what its forward flow loses: line"
    And the file "decisions.md" contains "another link holds the name line reverse"

  Scenario: A two-way line that costs money and whose reverse name another line holds reports its cost
    The line loses nothing, so its cost is what a split would carry in each direction.
    Given the system contains an HVDC line "line" from "node_a" to "node_b" with p_nom 500.0 efficiency 1.0
    And the TwoTerminalGenericHVDCLine "line" has ext "marginal_cost" set to 10.0
    And the TwoTerminalGenericHVDCLine "line" has ext "p_min_pu" set to -0.8
    And the system contains an HVDC line "line reverse" from "node_b" to "node_a" with p_nom 100.0 efficiency 1.0
    And the system is saved as "inputs/costly_reverse_taken.json"
    When I run translate against "inputs/costly_reverse_taken.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 2 links
    And the file "decisions.md" contains "| `sienna.TwoTerminalGenericHVDCLine.line.extensions.marginal_cost` = 10.0 \$/MWh |  |  | another link holds the name line reverse"

  Scenario: A conversion under the name of a link travels on, and the log says so
    Given the system contains an HVDC line "line" from "node_a" to "node_b" with p_nom 500.0 efficiency 1.0
    And the system has a conversion extension record "line" with "bus0" set to "node_a"
    And the system has a conversion extension record "line" with "bus1" set to "node_b"
    And the system is saved as "inputs/taken.json"
    When I run translate against "inputs/taken.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 1 link
    And the file "outputs/extensions.json" parses as JSON conversion extension record for "line" having "bus0" set to "node_a"
    And the log contains "1 conversion record(s) join two buses under the name of a link of the network, so each travels on to extensions.json and becomes no link: line"

  Scenario: A policy record and a portfolio record travel on whole
    Given the system has a constraint extension record "CO2CAP" with "type" set to "primary_energy"
    And the system has a constraint extension record "CO2CAP" with "limits" set to [{"period": "year", "value": 100.0, "investment_period": 2020}]
    And the system has a technology extension record "NEWGAS" with "p_nom" set to {"2020": 0.0}
    And the system is saved as "inputs/policy.json"
    When I run translate against "inputs/policy.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the file "outputs/extensions.json" parses as JSON constraint extension record for "CO2CAP" having "type" set to "primary_energy"
    And the file "outputs/extensions.json" parses as JSON technology extension record for "NEWGAS" having "p_nom" set to {"2020": 0.0}
    And the file "decisions.md" contains "| `sienna.constraint.CO2CAP.extensions.type` = primary_energy | `pypsa.constraint.CO2CAP.extensions.type` = primary_energy | relayed unchanged to extensions.json, as PyPSA has no attribute for it |"

  Scenario: A field that a step reads a record for, but neither maps nor relays, is reported as dropped
    Given the ThermalStandard "gas" has ext carrier "gas"
    And the ThermalStandard "gas" has ext "category" set to "gas"
    And the system is saved as "inputs/system.json"
    And a project step "read_carrier_only" that maps the carrier of each generator record and relays nothing
    And a project pipeline "sienna-read-carrier" that runs the step "read_carrier_only"
    When I run translate against "inputs/system.json" pipeline "sienna-read-carrier" writing PyPSA to "outputs/unused.json"
    Then the log contains "1 field(s) of extension records reach no mapping and no relay, so each is dropped: generator gas.category"
    And the file "decisions.md" contains "| `sienna.generator.gas.category` = gas |  |  | a mapping in this translation reads this extension record, but no mapping maps this field and none relays it, so it is dropped rather than carried into the next sidecar |"
