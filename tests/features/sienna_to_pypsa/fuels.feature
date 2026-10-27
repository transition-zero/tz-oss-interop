@slow @fork_unsafe
Feature: Sienna to PyPSA builds the fuels that are not electricity from the extensions sidecar
  Sienna holds electricity only, so a bus, a generator, a link and a load of another fuel reach
  this hop as records of extensions.json that name their buses. Each one becomes a PyPSA
  component where the network holds its buses. A gas plant whose record names the bus of its
  fuel becomes a Link from that bus, so the network prices the fuel once.

  The invented system below has two buses of electricity, a gas plant of 200 MW and a load with
  a profile of four hours. Its sidecar holds the gas buses R1/ATGAS at AT and R1/DEGAS at DE.

  Background:
    Given a Sienna system
    And the system contains a bus "AT"
    And the system contains a bus "DE"
    And the system contains a ThermalStandard "gas" on bus "AT" with base_power 200 rating 1 active_power_min 0 active_power_max 200 marginal_cost 25 prime_mover "CC" fuel "NATURAL_GAS"
    And the system contains a PowerLoad "load" on bus "DE" with max_active_power 100
    And the PowerLoad "load" has a max_active_power series 0.5 1 1 0.5
    And the system has a bus extension record "R1/ATGAS" with "carrier" set to "gas"
    And the system has a bus extension record "R1/ATGAS" with "location" set to "AT"
    And the system has a bus extension record "R1/DEGAS" with "carrier" set to "gas"

  Scenario: A bus record of a fuel becomes a bus with its carrier and its location
    Given the system is saved as "inputs/buses.json"
    When I run translate against "inputs/buses.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 4 buses
    And the PyPSA network "outputs/network.nc" bus "R1/ATGAS" has carrier "gas"
    And the PyPSA network "outputs/network.nc" bus "R1/ATGAS" has location "AT"
    And the PyPSA network "outputs/network.nc" bus "AT" has carrier "AC"
    And the file "decisions.md" contains "| `sienna.bus.R1/ATGAS.extensions.carrier` = gas | `pypsa.Bus.R1/ATGAS.carrier` = gas | extensions.carrier (PyPSA round-trip) |"

  Scenario: A generator record on the bus of a fuel becomes a generator, and its emission rates travel on
    Given the system has a generator extension record "well" with "bus" set to "R1/DEGAS"
    And the system has a generator extension record "well" with "carrier" set to "gas"
    And the system has a generator extension record "well" with "p_nom_extendable" set to true
    And the system has a generator extension record "well" with "marginal_cost" set to 4.0
    And the system has a generator extension record "well" with "emission_rates_t_per_mwh" set to {"CO2": 0.2}
    And the system has a generator extension record "terminal" with "bus" set to "R1/ATGAS"
    And the system has a generator extension record "terminal" with "p_nom" set to 2000.0
    And the system has a generator extension record "terminal" with "p_max_pu" set to 0.8
    And the system is saved as "inputs/generators.json"
    When I run translate against "inputs/generators.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "well" has bus "R1/DEGAS"
    And the PyPSA network "outputs/network.nc" generator "well" is extendable
    And the PyPSA network "outputs/network.nc" generator "well" attribute "marginal_cost" is 4.0
    And the PyPSA network "outputs/network.nc" generator "terminal" attribute "p_nom" is 2000.0
    And the PyPSA network "outputs/network.nc" generator "terminal" attribute "p_max_pu" is 0.8
    And the PyPSA network "outputs/network.nc" generator "terminal" is not extendable
    And the file "outputs/extensions.json" parses as JSON generator extension record for "well" having "emission_rates_t_per_mwh" set to {"CO2": 0.2}
    And the file "outputs/extensions.json" parses as JSON generator extension record for "well" without field "bus"
    And the file "decisions.md" contains "| `sienna.generator.well.extensions.marginal_cost` = 4.0 \$/MWh | `pypsa.Generator.well.marginal_cost` = 4.0 \$/MWh | extensions.marginal_cost (PyPSA round-trip) |"
    And the file "decisions.md" contains "| `pypsa.Generator.terminal.marginal_cost` = 0.0 |  | the sidecar record states no marginal_cost, so PyPSA's own default applies |"
    And the file "decisions.md" contains "| `pypsa.Generator.terminal.committable` = False |  | the sidecar record states no committable, so PyPSA's own default applies |"
    And the file "decisions.md" contains "| `pypsa.Generator.well.p_max_pu` = 1.0 |  | the sidecar record states no p_max_pu, so PyPSA's own default applies |"
    And the file "decisions.md" contains "| `pypsa.Generator.well.p_nom` = 0.0 |  | the sidecar record states no p_nom, so PyPSA's own default applies |"
    And the file "decisions.md" does not contain "| `pypsa.Generator.terminal.p_max_pu` = 1.0 |"

  Scenario: A load record on the bus of a fuel becomes a load, flat or with its series
    Given the system has a load extension record "ATGAS/accumulated" with "bus" set to "R1/ATGAS"
    And the system has a load extension record "ATGAS/accumulated" with "p_set" set to 100.0
    And the system has a load extension record "ATGAS/accumulated" with "carrier" set to "gas"
    And the system has a load record "DEGAS" on bus "R1/DEGAS" with a p_set series 10 20 30 40
    And the system is saved as "inputs/loads.json"
    When I run translate against "inputs/loads.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 3 loads
    And the PyPSA network "outputs/network.nc" load "ATGAS/accumulated" has bus "R1/ATGAS"
    And the PyPSA network "outputs/network.nc" load "ATGAS/accumulated" attribute "p_set" is 100.0
    And the PyPSA network "outputs/network.nc" load "ATGAS/accumulated" has carrier "gas"
    And the PyPSA network "outputs/network.nc" load "DEGAS" has a p_set time series 10 20 30 40
    And the file "decisions.md" does not contain "| `pypsa.Load.DEGAS.p_set` = 0.0 |"

  Scenario: A fuel load record that states no p_set takes PyPSA's own default, and decisions.md says so
    Given the system has a load extension record "ATGAS/accumulated" with "bus" set to "R1/ATGAS"
    And the system is saved as "inputs/empty_load.json"
    When I run translate against "inputs/empty_load.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" load "ATGAS/accumulated" attribute "p_set" is 0.0
    And the file "decisions.md" contains "| `pypsa.Load.ATGAS/accumulated.p_set` = 0.0 |  | the sidecar record states no p_set, so PyPSA's own default applies |"

  Scenario: The fields of a fuel load record that PyPSA has no column for travel on unchanged
    Given the system has a load extension record "ATGAS/accumulated" with "bus" set to "R1/ATGAS"
    And the system has a load extension record "ATGAS/accumulated" with "p_set" set to 100.0
    And the system has a load extension record "ATGAS/accumulated" with "type" set to "industry"
    And the system is saved as "inputs/load_type.json"
    When I run translate against "inputs/load_type.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" load "ATGAS/accumulated" attribute "p_set" is 100.0
    And the file "outputs/extensions.json" parses as JSON load extension record for "ATGAS/accumulated" having "type" set to "industry"

  Scenario: A conversion record between the buses of fuels becomes a link, with a third bus that it draws from
    Given the system has a conversion extension record "pipe" with "bus0" set to "R1/DEGAS"
    And the system has a conversion extension record "pipe" with "bus1" set to "R1/ATGAS"
    And the system has a conversion extension record "pipe" with "bus2" set to "DE"
    And the system has a conversion extension record "pipe" with "efficiency2" set to -0.1
    And the system has a conversion extension record "pipe" with "p_nom" set to 1000.0
    And the system has a conversion extension record "pipe" with "efficiency" set to 0.99
    And the system has a conversion extension record "pipe" with "emission_rates_t_per_mwh" set to {"CO2": 0.01}
    And the system is saved as "inputs/pipe.json"
    When I run translate against "inputs/pipe.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" link "pipe" has bus0 "R1/DEGAS"
    And the PyPSA network "outputs/network.nc" link "pipe" has bus1 "R1/ATGAS"
    And the PyPSA network "outputs/network.nc" link "pipe" has bus2 "DE"
    And the PyPSA network "outputs/network.nc" link "pipe" attribute "efficiency2" is -0.1
    And the PyPSA network "outputs/network.nc" link "pipe" attribute "p_nom" is 1000.0
    And the file "outputs/extensions.json" parses as JSON conversion extension record for "pipe" having "emission_rates_t_per_mwh" set to {"CO2": 0.01}

  Scenario: A gas plant whose record names the bus of its fuel becomes a Link from that bus
    The plant burns 2 MWh of gas for each MWh of electricity, so the Link takes in 400 MW at
    an efficiency of 0.5. Its own cost of 5 $/MWh of electricity is 2.5 $/MWh of gas.
    Given the ThermalStandard "gas" has ext "fuel_buses" set to {"R1/ATGAS": 2.0}
    And the ThermalStandard "gas" has ext "own_marginal_cost" set to 5.0
    And the ThermalStandard "gas" has ext "own_emission_rates_t_per_mwh" set to {"CO2": 0.1}
    And the system is saved as "inputs/plant.json"
    When I run translate against "inputs/plant.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has no generator "gas"
    And the PyPSA network "outputs/network.nc" link "gas" has bus0 "R1/ATGAS"
    And the PyPSA network "outputs/network.nc" link "gas" has bus1 "AT"
    And the PyPSA network "outputs/network.nc" link "gas" attribute "p_nom" is 400.0
    And the PyPSA network "outputs/network.nc" link "gas" attribute "efficiency" is 0.5
    And the PyPSA network "outputs/network.nc" link "gas" attribute "marginal_cost" is 2.5
    And the PyPSA network "outputs/network.nc" link "gas" has carrier "CCGT"
    And the file "outputs/extensions.json" parses as JSON generator extension record for "gas" having "own_emission_rates_t_per_mwh" set to {"CO2": 0.1}
    And the file "decisions.md" contains "| `pypsa.Link.gas.p_nom` = 400.0 MW | base_power × the MWh of that fuel for each MWh of electricity |  | sienna-to-pypsa | sienna_to_pypsa_map_plant_links |"

  Scenario: A gas plant with an annual energy bound stays a Generator, and the log says so
    Given the ThermalStandard "gas" has ext "fuel_buses" set to {"R1/ATGAS": 2.0}
    And the ThermalStandard "gas" has ext "e_sum_min" set to {"2020": 1000.0}
    And the system is saved as "inputs/bounded.json"
    When I run translate against "inputs/bounded.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "gas" has bus "AT"
    And the PyPSA network "outputs/network.nc" has no link "gas"
    And the log contains "1 plant(s) state the buses of their fuels, but each states an annual energy bound, which a PyPSA Link has no attribute for, so each stays a Generator that pays the Sienna price of its fuel: gas"
    And the file "decisions.md" contains "| `sienna.ThermalStandard.gas.extensions.fuel_buses` = {'R1/ATGAS': 2.0} |  |  | the plant states an annual energy bound"

  Scenario: A plant whose fuel has no bus stays a Generator at its Sienna price
    Given the ThermalStandard "gas" has ext "fuel_buses" set to {"R1/ATCOAL": 1.5}
    And the system is saved as "inputs/no_bus.json"
    When I run translate against "inputs/no_bus.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "gas" attribute "marginal_cost" is 25.0
    And the PyPSA network "outputs/network.nc" has no link "gas"
    And the log contains "1 plant(s) state the buses of their fuels, but each names a bus that the network does not hold, so each stays a Generator that pays the Sienna price of its fuel: gas"
    And the file "decisions.md" contains "| `sienna.ThermalStandard.gas.extensions.fuel_buses` = {'R1/ATCOAL': 1.5} |  |  | the plant names a bus that the network does not hold"

  Scenario: A plant that burns four fuels stays a Generator, and the log says so
    A Link of this hop draws a fuel at bus0, bus2 and bus3, and puts out electricity at bus1.
    Given the ThermalStandard "gas" has ext "fuel_buses" set to {"R1/ATGAS": 2.0, "R1/DEGAS": 0.5, "AT": 0.1, "DE": 0.1}
    And the system is saved as "inputs/four_fuels.json"
    When I run translate against "inputs/four_fuels.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "gas" attribute "marginal_cost" is 25.0
    And the PyPSA network "outputs/network.nc" has no link "gas"
    And the log contains "1 plant(s) state the buses of their fuels, but each burns more than 3 fuels, and a Link of this hop draws at bus0, bus2 and bus3 only, so each stays a Generator that pays the Sienna price of its fuel: gas"

  Scenario: A plant whose fuel ratio is not above zero stays a Generator, and the log says so
    A ratio of 0 MWh of fuel for each MWh of electricity gives no efficiency for a Link.
    Given the ThermalStandard "gas" has ext "fuel_buses" set to {"R1/ATGAS": 0.0}
    And the system is saved as "inputs/no_ratio.json"
    When I run translate against "inputs/no_ratio.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "gas" attribute "marginal_cost" is 25.0
    And the PyPSA network "outputs/network.nc" has no link "gas"
    And the log contains "1 plant(s) state the buses of their fuels, but each states a fuel ratio that is not above zero, so each stays a Generator that pays the Sienna price of its fuel: gas"
    And the file "decisions.md" contains "| `sienna.ThermalStandard.gas.extensions.fuel_buses` = {'R1/ATGAS': 0.0} |  |  | the plant states a fuel ratio that is not above zero"

  Scenario: A plant whose fuel ratio is negative stays a Generator
    Given the ThermalStandard "gas" has ext "fuel_buses" set to {"R1/ATGAS": -2.0}
    And the system is saved as "inputs/negative_ratio.json"
    When I run translate against "inputs/negative_ratio.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "gas" attribute "p_nom" is 200.0
    And the PyPSA network "outputs/network.nc" has no link "gas"

  Scenario: An annual bound of a conversion record that becomes a link travels on, and the log says so
    Given the system has a conversion extension record "pipe" with "bus0" set to "R1/DEGAS"
    And the system has a conversion extension record "pipe" with "bus1" set to "R1/ATGAS"
    And the system has a conversion extension record "pipe" with "p_nom" set to 1000.0
    And the system has a conversion extension record "pipe" with "e_sum_max" set to {"2020": 5000.0}
    And the system is saved as "inputs/bounded_pipe.json"
    When I run translate against "inputs/bounded_pipe.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" link "pipe" has bus0 "R1/DEGAS"
    And the log contains "1 energy bound(s) of a link stay in extensions.json and bind nothing, because a PyPSA Link has no e_sum_min or e_sum_max: pipe.e_sum_max"
    And the file "outputs/extensions.json" parses as JSON conversion extension record for "pipe" having "e_sum_max" set to {"2020": 5000.0}
    And the file "decisions.md" contains "| `sienna.conversion.pipe.extensions.e_sum_max` |"

  Scenario: An extendable conversion record keeps the capacity that it has as a floor
    Given the system has a conversion extension record "pipe" with "bus0" set to "R1/DEGAS"
    And the system has a conversion extension record "pipe" with "bus1" set to "R1/ATGAS"
    And the system has a conversion extension record "pipe" with "p_nom" set to 1000.0
    And the system has a conversion extension record "pipe" with "p_nom_extendable" set to true
    And the system is saved as "inputs/extendable_pipe.json"
    When I run translate against "inputs/extendable_pipe.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" link "pipe" is extendable
    And the PyPSA network "outputs/network.nc" link "pipe" attribute "p_nom_min" is 1000.0

  Scenario: A plant that burns a second fuel draws it at bus2, and decisions.md names each column of the Link
    The plant burns 2 MWh of gas and 0.5 MWh of gas from DE for each MWh of electricity, so
    bus2 takes -0.5 / 2 = -0.25 MWh for each MWh that goes in at bus0. The Generator of the
    plant states a discount rate, an efficiency and a marginal cost, which the Link does not
    hold.
    Given the ThermalStandard "gas" has ext "fuel_buses" set to {"R1/ATGAS": 2.0, "R1/DEGAS": 0.5}
    And the ThermalStandard "gas" has ext "discount_rate" set to 0.07
    And the ThermalStandard "gas" has ext "efficiency" set to 0.4
    And the system is saved as "inputs/two_fuels.json"
    When I run translate against "inputs/two_fuels.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" link "gas" has bus0 "R1/ATGAS"
    And the PyPSA network "outputs/network.nc" link "gas" has bus2 "R1/DEGAS"
    And the PyPSA network "outputs/network.nc" link "gas" attribute "efficiency2" is -0.25
    And the file "decisions.md" contains "| `pypsa.Link.gas.efficiency2` = -0.25 | a further fuel of extensions.fuel_buses"
    And the file "decisions.md" contains "| `pypsa.Generator.gas.carrier` = CCGT | `pypsa.Link.gas.carrier` = CCGT | the Generator of the plant moves to the Link"
    And the file "decisions.md" contains "`pypsa.Generator.gas.discount_rate` = 0.07"
    And the file "decisions.md" contains "the Link that replaces it does not hold it"
    And the file "decisions.md" contains "| `pypsa.Generator.gas.marginal_cost` = 25.0 |  |  | the Generator of the plant states the column, and the Link that replaces it does not hold it |"
    And the file "decisions.md" contains "| `pypsa.Generator.gas.efficiency` = 0.4 |  |  | the Generator of the plant states the column, and the Link that replaces it does not hold it |"

  Scenario: The availability of a plant in each hour moves to its Link
    Given the ThermalStandard "gas" has ext "fuel_buses" set to {"R1/ATGAS": 2.0}
    And the ThermalStandard "gas" has a max_active_power series 0.5 1 1 0.5
    And the system is saved as "inputs/hourly_plant.json"
    When I run translate against "inputs/hourly_plant.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has no generator "gas"
    And the PyPSA network "outputs/network.nc" link "gas" has a p_max_pu time series 0.5 1 1 0.5

  Scenario: A plant that the network may build stays a Generator at its Sienna price
    Given the ThermalStandard "gas" has ext "fuel_buses" set to {"R1/ATGAS": 2.0}
    And the ThermalStandard "gas" has ext "p_nom_extendable" set to true
    And the system is saved as "inputs/extendable_plant.json"
    When I run translate against "inputs/extendable_plant.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "gas" is extendable
    And the PyPSA network "outputs/network.nc" generator "gas" attribute "marginal_cost" is 25.0
    And the PyPSA network "outputs/network.nc" has no link "gas"
    And the log contains "1 plant(s) state the buses of their fuels, but each may build more capacity, which a Link of this hop does not, so each stays a Generator that pays the Sienna price of its fuel: gas"
    And the file "decisions.md" contains "| `sienna.ThermalStandard.gas.extensions.fuel_buses` = {'R1/ATGAS': 2.0} |  |  | the plant may build more capacity"

  Scenario: An annual bound of a controllable line travels on, and the log says so
    The HVDC line step_down states an annual bound in its record, which a PyPSA Link has no
    attribute for.
    Given the system contains an HVDC line "step_down" from "AT" to "DE" with p_nom 300 efficiency 0.99
    And the system has a controllable_line extension record "step_down" with "e_sum_max" set to {"2020": 1000.0}
    And the system has a controllable_line extension record "step_down" with "is_conversion" set to true
    And the system is saved as "inputs/bounded_line.json"
    When I run translate against "inputs/bounded_line.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" link "step_down" has bus0 "AT"
    And the log contains "1 energy bound(s) of a link stay in extensions.json and bind nothing, because a PyPSA Link has no e_sum_min or e_sum_max: step_down.e_sum_max"
    And the file "outputs/extensions.json" parses as JSON controllable_line extension record for "step_down" having "e_sum_max" set to {"2020": 1000.0}
    And the file "outputs/extensions.json" parses as JSON controllable_line extension record for "step_down" having "is_conversion" set to true
    And the file "decisions.md" contains "| `sienna.TwoTerminalGenericHVDCLine.step_down.extensions.e_sum_max` |"
