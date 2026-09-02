@slow @fork_unsafe
Feature: Translate PLEXOS generators into a PyPSA network

  The plexos-to-pypsa pipeline maps each PLEXOS Generator onto a PyPSA Generator,
  taking the carrier from the fuel or category as the model words it, assembling a single
  marginal cost from the fuel price, heat rate, VO&M charge, and emission, and attaching
  an availability profile to a renewable generator.

  Scenario: a thermal gas generator maps with its full cost and unit-commitment fields
    Given a Plexos model
    And the model contains fuel "Natural Gas" with price 3
    And the model contains emission "CO2" with price 50 on fuel "Natural Gas" production rate 100
    And the model contains generator "GasPlant" with "node=Grid_Node, fuel=Natural Gas, Max Capacity=250, Units=2, Min Stable Level=100, Heat Rate=8, VO&M Charge=2, Start Cost=1000, Max Ramp Up=5, Max Ramp Down=5, Min Up Time=6, Min Down Time=4"
    And the model is saved as "inputs/thermal.xml"
    When I run translate against "inputs/thermal.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the file "outputs/network.nc" exists
    And the PyPSA generator "GasPlant" in "outputs/network.nc" has bus "Grid_Node"
    And the PyPSA generator "GasPlant" in "outputs/network.nc" has carrier "Natural Gas"
    And the PyPSA generator "GasPlant" in "outputs/network.nc" has "p_nom" equal to 500
    And the PyPSA generator "GasPlant" in "outputs/network.nc" has "p_min_pu" equal to 0.2
    And the PyPSA generator "GasPlant" in "outputs/network.nc" has "marginal_cost" equal to 66
    And the PyPSA generator "GasPlant" in "outputs/network.nc" has "ramp_limit_up" equal to 0.6
    And the PyPSA generator "GasPlant" in "outputs/network.nc" has "min_up_time" equal to 6
    And the PyPSA generator "GasPlant" in "outputs/network.nc" has "start_up_cost" equal to 1000
    And the PyPSA generator "GasPlant" in "outputs/network.nc" is committable
    # The carbon term is derived on its own, then feeds the total as a source of it.
    And the file "decisions.md" contains "`pypsa.Generator.GasPlant.marginal_cost carbon term` = 40.0 $/MWh | carbon price x production rate x heat rate / 1000 |"
    And the file "decisions.md" contains "`pypsa.Generator.GasPlant.marginal_cost carbon term` = 40.0 $/MWh | `pypsa.Generator.GasPlant.marginal_cost` = 66.0 $/MWh | fuel price x heat rate + VO&M charge + the carbon term |"
    # Each value is attributed to the PLEXOS object holding it, not to the generator reading it.
    And the file "decisions.md" contains "`plexos.Fuel.Natural Gas.Price` = 3.0 $/GJ"
    And the file "decisions.md" contains "`plexos.Emission.CO2.Price` = 50.0 $/tonne"
    And the file "decisions.md" contains "`plexos.Emission.CO2.Production Rate` = 100.0 kg/GJ"

  Scenario: a generator's category travels in the sidecar whichever word became its carrier
    # A carrier is the fuel or the category, never both, so a crosswalk downstream can only
    # key on the winner unless the other travels beside it.
    Given a Plexos model
    And the model contains generator "GasPlant" with "node=Grid_Node, category=Thermal, fuel=Natural Gas, Max Capacity=500, Heat Rate=9"
    And the model contains generator "SolarFarm" with "node=Grid_Node, category=ISORPS WindSolar, Max Capacity=100"
    And the model is saved as "inputs/categories.xml"
    When I run translate against "inputs/categories.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA generator "GasPlant" in "outputs/network.nc" has carrier "Natural Gas"
    And the extensions sidecar "outputs/extensions.json" generator "GasPlant" has category "Thermal"
    And the PyPSA generator "SolarFarm" in "outputs/network.nc" has carrier "ISORPS WindSolar"
    And the extensions sidecar "outputs/extensions.json" generator "SolarFarm" has category "ISORPS WindSolar"

  Scenario: minimum up time does not change the carrier a fuel names
    Given a Plexos model
    And the model contains generator "Peaker" with "node=Grid_Node, fuel=Natural Gas, Max Capacity=100, Units=1, Min Stable Level=0, Heat Rate=10, VO&M Charge=1, Start Cost=50, Max Ramp Up=20, Max Ramp Down=20, Min Up Time=1, Min Down Time=1"
    And the model is saved as "inputs/peaker.xml"
    When I run translate against "inputs/peaker.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA generator "Peaker" in "outputs/network.nc" has carrier "Natural Gas"

  Scenario: the fuel names the carrier for coal and nuclear generators
    Given a Plexos model
    And the model contains generators:
      | name      | node      | fuel    | Max Capacity | Heat Rate |
      | CoalPlant | Grid_Node | Coal    | 300          | 9         |
      | NukePlant | Grid_Node | Uranium | 1000         | 10        |
    And the model is saved as "inputs/fuels.xml"
    When I run translate against "inputs/fuels.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA generator "CoalPlant" in "outputs/network.nc" has carrier "Coal"
    And the PyPSA generator "NukePlant" in "outputs/network.nc" has carrier "Uranium"

  Scenario: fuels named per region keep their own names rather than collapsing together
    Given a Plexos model
    And the model contains generators:
      | name   | node      | fuel               | Max Capacity | Heat Rate |
      | Blythe | Grid_Node | NG_AZ/Cal_Blythe   | 100          | 9         |
      | SoCal  | Grid_Node | NG_Cal_SoCalGas    | 100          | 9         |
    And the model is saved as "inputs/regional_fuels.xml"
    When I run translate against "inputs/regional_fuels.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA generator "Blythe" in "outputs/network.nc" has carrier "NG_AZ/Cal_Blythe"
    And the PyPSA generator "SoCal" in "outputs/network.nc" has carrier "NG_Cal_SoCalGas"

  Scenario: a renewable generator takes its availability from a file-backed Rating profile
    Given a Plexos model
    And the model contains data file "SolarProfile" at "profiles/solar.csv" with hourly values "100, 150, 200"
    And the model contains generator "Solar1" with "node=Grid_Node, category=Solar, Max Capacity=200, Rating=file:SolarProfile"
    And the model is saved as "inputs/solar.xml"
    When I run translate against "inputs/solar.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA generator "Solar1" in "outputs/network.nc" has carrier "Solar"
    And the PyPSA generator "Solar1" in "outputs/network.nc" is not committable
    And the PyPSA generator "Solar1" in "outputs/network.nc" has p_max_pu at hour 1 equal to 0.5
    And the PyPSA generator "Solar1" in "outputs/network.nc" has p_max_pu at hour 2 equal to 0.75
    And the PyPSA generator "Solar1" in "outputs/network.nc" has p_max_pu at hour 3 equal to 1.0

  Scenario: a retired generator with zero units is skipped
    Given a Plexos model
    And the model contains generator "OldPlant" with "node=Grid_Node, Max Capacity=100, Units=0"
    And the model is saved as "inputs/retired.xml"
    When I run translate against "inputs/retired.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has no generator "OldPlant"

  Scenario: a generator on no node is skipped
    Given a Plexos model
    And the model contains generator "Orphan" with "Max Capacity=100"
    And the model is saved as "inputs/orphan.xml"
    When I run translate against "inputs/orphan.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has no generator "Orphan"

  Scenario: a generator with no minimum stable level can turn down to zero
    Given a Plexos model
    And the model contains generator "FlexPlant" with "node=Grid_Node, fuel=Gas, Max Capacity=100, Heat Rate=8"
    And the model is saved as "inputs/flex.xml"
    When I run translate against "inputs/flex.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA generator "FlexPlant" in "outputs/network.nc" has "p_min_pu" equal to 0

  Scenario: a fuel PyPSA has no conventional name for carries across as the model words it
    Given a Plexos model
    And the model contains generators:
      | name     | node      | fuel          | Max Capacity | Heat Rate |
      | BioPlant | Grid_Node | Biogas        | 50           | 9         |
      | SeamGas  | Grid_Node | Coal Seam Gas | 80           | 9         |
    And the model is saved as "inputs/fuels.xml"
    When I run translate against "inputs/fuels.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA generator "BioPlant" in "outputs/network.nc" has carrier "Biogas"
    And the PyPSA generator "SeamGas" in "outputs/network.nc" has carrier "Coal Seam Gas"

  Scenario: a category carries across in the case the model writes it in
    Given a Plexos model
    And the model contains generators:
      | name       | node      | category      | Max Capacity |
      | LowerSolar | Grid_Node | solar         | 50           |
      | UpperWind  | Grid_Node | OFFSHORE WIND | 50           |
    And the model is saved as "inputs/categorycase.xml"
    When I run translate against "inputs/categorycase.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA generator "LowerSolar" in "outputs/network.nc" has carrier "solar"
    And the PyPSA generator "UpperWind" in "outputs/network.nc" has carrier "OFFSHORE WIND"

  Scenario: a minimum stable level above the available capacity leaves the generator out
    Given a Plexos model
    And the model contains generator "InfeasiblePlant" with "node=Grid_Node, fuel=Coal, Max Capacity=100, Heat Rate=9, Min Stable Factor=50, Outage Factor=40"
    And the model is saved as "inputs/infeasible.xml"
    When I run translate against "inputs/infeasible.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has no generator "InfeasiblePlant"
    And the log contains "dropping Generator 'InfeasiblePlant'"
    And the log contains "p_min_pu 0.5 is above p_max_pu 0.4"
    And the file "decisions.md" contains "| `plexos.Generator.InfeasiblePlant.Min Stable Factor` = 50.0 |  |  | p_min_pu 0.5 sits above p_max_pu 0.4, which PyPSA cannot dispatch, so the generator is dropped |"

  Scenario: a non-fuel dispatchable generator gets a flat cost from its category
    Given a Plexos model
    And the model contains generator "GeoPlant" with "node=Grid_Node, category=Geothermal, Max Capacity=50"
    And the model is saved as "inputs/geo.xml"
    When I run translate against "inputs/geo.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA generator "GeoPlant" in "outputs/network.nc" has carrier "Geothermal"
    And the PyPSA generator "GeoPlant" in "outputs/network.nc" has "marginal_cost" equal to 0

  Scenario: a Rating Factor profile is a percentage availability
    Given a Plexos model
    And the model contains data file "WindProfile" at "profiles/wind.csv" with hourly values "80, 90, 100"
    And the model contains generator "WindFarm" with "node=Grid_Node, category=Wind, Max Capacity=100, Rating Factor=file:WindProfile"
    And the model is saved as "inputs/wind.xml"
    When I run translate against "inputs/wind.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA generator "WindFarm" in "outputs/network.nc" has carrier "Wind"
    And the PyPSA generator "WindFarm" in "outputs/network.nc" is not committable
    And the PyPSA generator "WindFarm" in "outputs/network.nc" has p_max_pu at hour 1 equal to 0.8
    And the PyPSA generator "WindFarm" in "outputs/network.nc" has p_max_pu at hour 2 equal to 0.9
    And the PyPSA generator "WindFarm" in "outputs/network.nc" has p_max_pu at hour 3 equal to 1.0

  Scenario: Min Stable Factor takes precedence over Min Stable Level
    Given a Plexos model
    And the model contains generator "FactorPlant" with "node=Grid_Node, fuel=Gas, Max Capacity=100, Heat Rate=8, Min Stable Factor=40, Min Stable Level=100"
    And the model is saved as "inputs/minstable.xml"
    When I run translate against "inputs/minstable.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA generator "FactorPlant" in "outputs/network.nc" has "p_min_pu" equal to 0.4
    # The decision carries the value that produced p_min_pu, not just the property name.
    And the file "decisions.md" contains "| `plexos.Generator.FactorPlant.Min Stable Factor` = 40.0 | `pypsa.Generator.FactorPlant.p_min_pu` = 0.4 |"

  Scenario: a two-part heat rate gives efficiency and an incremental fuel cost
    Given a Plexos model
    And the model contains fuel "Natural Gas" with price 3
    And the model contains generator "TwoPartPlant" with "node=Grid_Node, fuel=Natural Gas, Max Capacity=100, Heat Rate Base=100, Heat Rate Incr=8"
    And the model is saved as "inputs/twopart.xml"
    When I run translate against "inputs/twopart.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA generator "TwoPartPlant" in "outputs/network.nc" has "efficiency" equal to 0.4
    And the PyPSA generator "TwoPartPlant" in "outputs/network.nc" has "marginal_cost" equal to 24

  Scenario: outage properties derate p_max_pu
    Given a Plexos model
    And the model contains generator "OutageFactorPlant" with "node=Grid_Node, fuel=Coal, Max Capacity=100, Heat Rate=9, Outage Factor=90"
    And the model contains generator "OutageRatingPlant" with "node=Grid_Node, fuel=Coal, Max Capacity=100, Heat Rate=9, Outage Rating=10"
    And the model is saved as "inputs/outage.xml"
    When I run translate against "inputs/outage.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA generator "OutageFactorPlant" in "outputs/network.nc" has "p_max_pu" equal to 0.9
    And the PyPSA generator "OutageRatingPlant" in "outputs/network.nc" has "p_max_pu" equal to 0.9

  Scenario: a multi-fuel generator takes its carrier from its primary fuel
    Given a Plexos model
    And the model contains generator "DualPlant" with "node=Grid_Node, fuel=Coal, fuel=Natural Gas, Max Capacity=300, Heat Rate=9"
    And the model is saved as "inputs/multifuel.xml"
    When I run translate against "inputs/multifuel.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA generator "DualPlant" in "outputs/network.nc" has carrier "Coal"

  Scenario: a generator taking a share of a shared profile gets its share, not the whole profile
    Given a Plexos model
    And the model contains variable "SystemSolar" profiling "profiles/system_solar.csv" with hourly values "1000, 2000, 4000"
    And the model contains generator "SolarShare" with "node=Grid_Node, category=Solar, Max Capacity=100, Rating=variable:SystemSolar:0.025"
    And the model is saved as "inputs/share.xml"
    When I run translate against "inputs/share.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA generator "SolarShare" in "outputs/network.nc" has p_max_pu at hour 1 equal to 0.25
    And the PyPSA generator "SolarShare" in "outputs/network.nc" has p_max_pu at hour 2 equal to 0.5
    And the PyPSA generator "SolarShare" in "outputs/network.nc" has p_max_pu at hour 3 equal to 1.0

  Scenario: a generator sharing a timeslice-banded variable keeps a static availability
    Given a Plexos model
    And the model contains variable "GenericTLAF" with timeslice pattern "M12, H1-7, H23-24"
    And the model contains generator "DeratedPlant" with "node=Grid_Node, category=Solar, Max Capacity=100, Rating=variable:GenericTLAF:0.98"
    And the model is saved as "inputs/timeslice.xml"
    When I run translate against "inputs/timeslice.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA generator "DeratedPlant" in "outputs/network.nc" has "p_nom" equal to 100
    And the PyPSA network "outputs/network.nc" generator "DeratedPlant" has no p_max_pu time series

  Scenario: a generator whose availability profile could not be read keeps its static availability
    This file names months but no year, and neither a Horizon nor the horizon_year
    parameter says which year they belong to, so the warning names what would let it be
    read rather than leaving the profile unaccountably missing.
    Given a Plexos model
    And the model contains monthly data file "SolarMonthly" at "profiles/solar_monthly.csv" for "Solar1" with monthly values "50, 60, 70, 80, 90, 100, 100, 90, 80, 70, 60, 50"
    And the model contains generator "Solar1" with "node=Grid_Node, category=Solar, Max Capacity=100, Rating=file:SolarMonthly"
    And the model is saved as "inputs/undated.xml"
    When I run translate against "inputs/undated.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the log contains "its rows carry no year"
    And the log contains "'horizon_year' parameter"
    And the log contains "no staged series for Generator property 'Rating'"
    And the PyPSA generator "Solar1" in "outputs/network.nc" has "p_nom" equal to 100
    And the PyPSA network "outputs/network.nc" generator "Solar1" has no p_max_pu time series
    And the file "decisions.md" contains "| `plexos.Generator.Solar1.Rating` = profile |  |  | the source staged no series for this profile, so p_max_pu keeps the static availability instead |"

  Scenario: a units-out trace derates availability by the units unavailable
    Given a Plexos model
    And the model contains variable "OutageTrace" profiling "profiles/units_out.csv" with hourly values "0, 1, 2"
    And the model contains generator "OutagePlant" with "node=Grid_Node, fuel=Coal, Max Capacity=100, Units=4, Heat Rate=9, Units Out=variable:OutageTrace"
    And the model is saved as "inputs/unitsout.xml"
    When I run translate against "inputs/unitsout.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA generator "OutagePlant" in "outputs/network.nc" has "p_nom" equal to 400
    And the PyPSA generator "OutagePlant" in "outputs/network.nc" has p_max_pu at hour 1 equal to 1.0
    And the PyPSA generator "OutagePlant" in "outputs/network.nc" has p_max_pu at hour 2 equal to 0.75
    And the PyPSA generator "OutagePlant" in "outputs/network.nc" has p_max_pu at hour 3 equal to 0.5

  Scenario: a minimum stable level cannot exceed the availability the generator ever has
    Given a Plexos model
    And the model contains data file "DipProfile" at "profiles/dip.csv" with hourly values "100, 0, 100"
    And the model contains generator "DipPlant" with "node=Grid_Node, category=Geothermal, Max Capacity=100, Min Stable Level=70, Rating=file:DipProfile"
    And the model is saved as "inputs/dip.xml"
    When I run translate against "inputs/dip.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA generator "DipPlant" in "outputs/network.nc" has "p_min_pu" equal to 0

  Scenario: an outage derates a generator that also follows an availability profile
    Given a Plexos model
    And the model contains data file "DeratedProfile" at "profiles/derated.csv" with hourly values "100, 150, 200"
    And the model contains generator "DeratedSolar" with "node=Grid_Node, category=Solar, Max Capacity=200, Outage Factor=50, Rating=file:DeratedProfile"
    And the model is saved as "inputs/derated.xml"
    When I run translate against "inputs/derated.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA generator "DeratedSolar" in "outputs/network.nc" has p_max_pu at hour 1 equal to 0.25
    And the PyPSA generator "DeratedSolar" in "outputs/network.nc" has p_max_pu at hour 2 equal to 0.375
    And the PyPSA generator "DeratedSolar" in "outputs/network.nc" has p_max_pu at hour 3 equal to 0.5

  Scenario: a generator that ramps up but sets no down rate keeps only the limit it has
    Given a Plexos model
    And the model contains generator "OneWayPlant" with "node=Grid_Node, fuel=Coal, Max Capacity=120, Heat Rate=9, Max Ramp Up=2, Min Up Time=4"
    And the model is saved as "inputs/oneway.xml"
    When I run translate against "inputs/oneway.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA generator "OneWayPlant" in "outputs/network.nc" has "ramp_limit_up" equal to 1
    And the PyPSA generator "OneWayPlant" in "outputs/network.nc" has "min_up_time" equal to 4
    And the PyPSA generator "OneWayPlant" in "outputs/network.nc" has no "ramp_limit_down"
    And the PyPSA generator "OneWayPlant" in "outputs/network.nc" has "min_down_time" equal to 0
    # Each limit is recorded on its own, so the one that is set is still traceable.
    And the file "decisions.md" contains "| `plexos.Generator.OneWayPlant.Max Ramp Up` = 2.0 MW/min | `pypsa.Generator.OneWayPlant.ramp_limit_up` = 1.0 pu/h | Max Ramp x snapshot minutes / p_nom, capped at 1 |  | plexos-to-pypsa | plexos_to_pypsa_map_generators |"
    And the file "decisions.md" does not contain "ramp_limit_down"
    # A generator with a flat Heat Rate is attributed to that property, not Heat Rate Incr.
    And the file "decisions.md" contains "`plexos.Generator.OneWayPlant.Heat Rate` = 9.0 GJ/MWh"

  Scenario: a generator whose capacity comes from a data file is skipped
    Given a Plexos model
    And the model contains data file "Capacity" at "profiles/capacity.csv" with hourly values "100, 100, 100"
    And the model contains generator "Gas1" with "node=Grid_Node, fuel=Natural Gas, Heat Rate=9, Max Capacity=file:Capacity"
    And the model is saved as "inputs/gas.xml"
    When I run translate against "inputs/gas.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has no generator "Gas1"
    And the file "decisions.md" contains "Max Capacity comes from a data file"

  Scenario: a generator with no capacity is skipped
    Given a Plexos model
    And the model contains generator "Gas1" with "node=Grid_Node, fuel=Natural Gas, Heat Rate=9, Max Capacity=0"
    And the model is saved as "inputs/gas.xml"
    When I run translate against "inputs/gas.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has no generator "Gas1"
    And the file "decisions.md" contains "so it can never dispatch"

  Scenario: a profile scales on total capacity, not on one unit's capacity
    Given a Plexos model
    And the model contains data file "Evening" at "profiles/evening.csv" with hourly values "0, 500, 1000"
    And the model contains generator "Peaker" with "node=Grid_Node, fuel=Natural Gas, Heat Rate=9, Max Capacity=500, Units=2, Rating=file:Evening"
    And the model is saved as "inputs/peaker.xml"
    When I run translate against "inputs/peaker.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA generator "Peaker" in "outputs/network.nc" has "p_nom" equal to 1000
    And the PyPSA generator "Peaker" in "outputs/network.nc" has p_max_pu at hour 2 equal to 0.5
    And the PyPSA generator "Peaker" in "outputs/network.nc" has p_max_pu at hour 3 equal to 1.0

  Scenario: of two generators whose profiles cover different snapshots, only the fitting one keeps its profile
    Given a Plexos model
    And the model contains data file "Long" at "profiles/long.csv" with hourly values "0, 100, 100, 0"
    And the model contains data file "Short" at "profiles/short.csv" with hourly values "0, 100"
    And the model contains generator "Gas1" with "node=Grid_Node, fuel=Natural Gas, Heat Rate=9, Max Capacity=100, Rating=file:Long"
    And the model contains generator "Gas2" with "node=Grid_Node, fuel=Natural Gas, Heat Rate=9, Max Capacity=100, Rating=file:Short"
    And the model is saved as "inputs/gas.xml"
    When I run translate against "inputs/gas.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the log contains "Rating on Gas2 carries 2"
    And the log contains "the snapshot window holds 4 steps"
    And the PyPSA network "outputs/network.nc" generator "Gas1" has a p_max_pu time series 0 1 1 0
    And the PyPSA network "outputs/network.nc" generator "Gas2" has no p_max_pu time series

  Scenario: a demand-response resource maps as an ordinary high-cost generator
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains fuel "DR_Fuel" with price 1000
    And the model contains data file "DR_Evening" at "CSVFiles\DR.csv" with hourly values "0, 0, 971, 971, 0"
    And the model contains generator "DR1" with "node=Grid_Node, fuel=DR_Fuel, Max Capacity=971, Heat Rate=10, Rating=file:DR_Evening"
    And the model is saved as "inputs/model.xml"
    When I run translate against "inputs/model.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the file "outputs/network.nc" exists
    And the PyPSA network "outputs/network.nc" generator "DR1" has carrier "DR_Fuel"
    And the PyPSA network "outputs/network.nc" generator "DR1" attribute "p_nom" is 971
    And the PyPSA network "outputs/network.nc" generator "DR1" attribute "marginal_cost" is 10000
    And the demand-response generator "DR1" in "outputs/network.nc" is available only in "0, 0, 1, 1, 0"

  Scenario: a ramp rate that covers the whole unit within one snapshot becomes no limit at all
    A PLEXOS Max Ramp is a rate in MW per minute. Over one snapshot a fast unit can cover
    more than its own capacity, which is not a limit PyPSA can hold: its ramp_limit_up is a
    fraction of p_nom and stops at 1.
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains fuel "Gas" with price 3
    And the model contains generator "FastPeaker" with "node=Grid_Node, fuel=Gas, Max Capacity=60, Heat Rate=9, Max Ramp Up=45, Max Ramp Down=45"
    And the model is saved as "inputs/fast.xml"
    When I run translate against "inputs/fast.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA generator "FastPeaker" in "outputs/network.nc" has "ramp_limit_up" equal to 1
    And the PyPSA generator "FastPeaker" in "outputs/network.nc" has "ramp_limit_down" equal to 1
    And the file "decisions.md" contains "| `plexos.Generator.FastPeaker.Max Ramp Up` = 45.0 MW/min | `pypsa.Generator.FastPeaker.ramp_limit_up` = 1.0 pu/h | Max Ramp x snapshot minutes / p_nom, capped at 1 |  | plexos-to-pypsa | plexos_to_pypsa_map_generators |"

  Scenario: a half-hourly model reads a ramp rate over half an hour, not over an hour
    A PLEXOS Max Ramp is a rate per minute, so the fraction of p_nom it covers depends on
    how long one snapshot is. A half-hourly network covers half of what an hourly one does.
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains fuel "Gas" with price 3
    And the model contains generator "SteadyPlant" with "node=Grid_Node, fuel=Gas, Max Capacity=240, Heat Rate=9, Max Ramp Up=2"
    And the model contains data file "LoadProfile" at "profiles/load.csv" with hourly values "100, 200, 300, 400"
    And the model contains region load "Grid" with peak 400 from data file "LoadProfile"
    And the model contains model "Plan"
    And the model contains horizon "H1" on model "Plan" starting "2026-01-01" spanning 1 days at 48 periods per day
    And the model is saved as "inputs/halfhourly.xml"
    When I run translate against "inputs/halfhourly.xml" pipeline "plexos-to-pypsa" for model "Plan" year 2026 sink output "outputs/network.nc"
    Then the PyPSA generator "SteadyPlant" in "outputs/network.nc" has "ramp_limit_up" equal to 0.25

  Scenario: a static Rating above the nameplate capacity becomes the capacity
    A PLEXOS Rating replaces Max Capacity as the capacity a unit can reach, so a Rating
    above the nameplate is what the unit can produce. p_nom is the reference every per-unit
    field divides by, so it takes the higher of the two and the availability is then full.
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains fuel "Water" with price 0
    And the model contains generator "OverRated" with "node=Grid_Node, fuel=Water, Max Capacity=60, Heat Rate=9, Rating=68, Min Stable Level=30"
    And the model is saved as "inputs/overrated.xml"
    When I run translate against "inputs/overrated.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA generator "OverRated" in "outputs/network.nc" has "p_nom" equal to 68
    And the PyPSA generator "OverRated" in "outputs/network.nc" has "p_max_pu" equal to 1
    And the file "decisions.md" contains "Rating above Max Capacity x Units"

  Scenario: a minimum stable level far below the capacity is written as no minimum at all
    Given a Plexos model
    And the model contains generator "WindFleet" with "node=Grid_Node, category=Wind, Max Capacity=15000, Min Stable Level=0.0067"
    And the model is saved as "inputs/negligible_minimum.xml"
    When I run translate against "inputs/negligible_minimum.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA generator "WindFleet" in "outputs/network.nc" has "p_min_pu" equal to 0
    And the file "decisions.md" contains "a minimum below 0.001 of the unit's own capacity constrains no dispatch, so it is written as zero"

  Scenario: a generator burning no fuel still commits so its minimum binds only while it runs
    Given a Plexos model
    And the model contains generator "RunOfRiver" with "node=Grid_Node, category=Hydro, Max Capacity=21, Min Stable Level=12"
    And the model is saved as "inputs/hydro_minimum.xml"
    When I run translate against "inputs/hydro_minimum.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA generator "RunOfRiver" in "outputs/network.nc" is committable
    And the PyPSA generator "RunOfRiver" in "outputs/network.nc" has "p_min_pu" equal to 0.5714285714285714

  Scenario: a fast generator's ramp limit stops at the whole of its capacity in one hour
    Given a Plexos model
    And the model contains generator "Peaker" with "node=Grid_Node, fuel=Gas, Max Capacity=100, Heat Rate=10, Max Ramp Up=50, Max Ramp Down=50"
    And the model is saved as "inputs/fast_ramp.xml"
    When I run translate against "inputs/fast_ramp.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA generator "Peaker" in "outputs/network.nc" has "ramp_limit_up" equal to 1
    And the PyPSA generator "Peaker" in "outputs/network.nc" has "ramp_limit_down" equal to 1
    # The event still names the MW per minute the source stated, so the clamp is auditable.
    And the file "decisions.md" contains "`plexos.Generator.Peaker.Max Ramp Up` = 50.0 MW/min"

  Scenario: a start priced only as start fuel still costs the generator something
    Given a Plexos model
    And the model contains fuel "Gas" with price 8
    And the model contains generator "CCGT" with "node=Grid_Node, fuel=Gas, Max Capacity=449, Heat Rate=7"
    And generator "CCGT" burns 1800 GJ of fuel "Gas" to start
    And the model is saved as "inputs/start_fuel.xml"
    When I run translate against "inputs/start_fuel.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA generator "CCGT" in "outputs/network.nc" has "start_up_cost" equal to 14400
    And the file "decisions.md" contains "`plexos.Generator.CCGT.Offtake at Start` = 1800.0 GJ"
    And the file "decisions.md" contains "`pypsa.Generator.CCGT.start_up_cost fuel term` = 14400.0 $ | Offtake at Start x the fuel's price |"
    And the file "decisions.md" contains "`pypsa.Generator.CCGT.start_up_cost fuel term` = 14400.0 $ | `pypsa.Generator.CCGT.start_up_cost` = 14400.0 $ | the start fuel prices the start, since the generator states no Start Cost |"

  Scenario: a stated start cost wins over the start fuel rather than being added to it
    Given a Plexos model
    And the model contains fuel "Gas" with price 8
    And the model contains generator "CCGT" with "node=Grid_Node, fuel=Gas, Max Capacity=449, Heat Rate=7, Start Cost=1000"
    And generator "CCGT" burns 1800 GJ of fuel "Gas" to start
    And the model is saved as "inputs/both_start_prices.xml"
    When I run translate against "inputs/both_start_prices.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA generator "CCGT" in "outputs/network.nc" has "start_up_cost" equal to 1000
    And the file "decisions.md" contains "the generator states its own Start Cost, which has already priced whatever fuel a start burns"

  Scenario: a banded start takes its cold-start band, whichever way the model prices it
    Given a Plexos model
    And the model contains fuel "Gas" with price 2
    And the model contains generator "Hot" with "node=Grid_Node, fuel=Gas, Max Capacity=100, Heat Rate=7"
    And the model contains "Start Cost" 1000 in band 1 for generator "Hot"
    And the model contains "Start Cost" 5000 in band 2 for generator "Hot"
    And the model contains generator "Cold" with "node=Grid_Node, fuel=Gas, Max Capacity=100, Heat Rate=7"
    And generator "Cold" burns 300 GJ of fuel "Gas" to start in band 1
    And generator "Cold" burns 900 GJ of fuel "Gas" to start in band 2
    And the model is saved as "inputs/start_bands.xml"
    When I run translate against "inputs/start_bands.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA generator "Hot" in "outputs/network.nc" has "start_up_cost" equal to 5000
    And the PyPSA generator "Cold" in "outputs/network.nc" has "start_up_cost" equal to 1800

  Scenario: a committable generator that prices no start says so rather than starting for free
    Given a Plexos model
    And the model contains generator "FreePlant" with "node=Grid_Node, fuel=Gas, Max Capacity=100, Heat Rate=8"
    And the model is saved as "inputs/no_start_price.xml"
    When I run translate against "inputs/no_start_price.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the file "decisions.md" contains "the generator states neither a Start Cost nor a start fuel, so nothing prices its starts"

  Scenario: the sink writes each number to a fixed number of decimal places
    Given a Plexos model
    And the model contains data file "SolarProfile" at "profiles/solar.csv" with hourly values "100, 150, 200"
    And the model contains generator "CCGT" with "node=Grid_Node, fuel=Gas, Max Capacity=449, Heat Rate=7"
    And the model contains generator "Solar1" with "node=Grid_Node, category=Solar, Max Capacity=300, Rating=file:SolarProfile"
    And the model is saved as "inputs/long_decimals.xml"
    When I run translate against "inputs/long_decimals.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA generator "CCGT" in "outputs/network.nc" has "efficiency" exactly 0.514286
    And the PyPSA generator "Solar1" in "outputs/network.nc" has p_max_pu at hour 1 exactly 0.333333

  Scenario: a generator that starts on a fuel it does not run on pays that fuel's own price
    Given a Plexos model
    And the model contains fuel "Gas" with price 8
    And the model contains fuel "Distillate" with price 25
    And the model contains generator "DualFuel" with "node=Grid_Node, fuel=Gas, Max Capacity=100, Heat Rate=7"
    And generator "DualFuel" burns 1800 GJ of fuel "Distillate" to start
    And the model is saved as "inputs/dual_fuel_start.xml"
    When I run translate against "inputs/dual_fuel_start.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA generator "DualFuel" in "outputs/network.nc" has "start_up_cost" equal to 45000
    And the file "decisions.md" contains "`plexos.Fuel.Distillate.Price` = 25.0 $/GJ"

  Scenario: a minimum the availability ceiling itself makes negligible is written as zero
    Given a Plexos model
    And the model contains data file "OutageProfile" at "profiles/outage.csv" with hourly values "0.05, 100, 100"
    And the model contains generator "Reservoir" with "node=Grid_Node, category=Hydro, Max Capacity=21, Min Stable Level=12, Rating Factor=file:OutageProfile"
    And the model is saved as "inputs/capped_minimum.xml"
    When I run translate against "inputs/capped_minimum.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA generator "Reservoir" in "outputs/network.nc" has "p_min_pu" equal to 0
    And the PyPSA generator "Reservoir" in "outputs/network.nc" is not committable
    And the file "decisions.md" contains "a minimum below 0.001 of the unit's own capacity constrains no dispatch, so it is written as zero"

  Scenario: a start cost of zero leaves the start fuel beside it pricing the start
    Given a Plexos model
    And the model contains fuel "Gas" with price 8
    And the model contains generator "CCGT" with "node=Grid_Node, fuel=Gas, Max Capacity=449, Heat Rate=7, Start Cost=0"
    And generator "CCGT" burns 1800 GJ of fuel "Gas" to start
    And the model is saved as "inputs/zero_start_cost.xml"
    When I run translate against "inputs/zero_start_cost.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA generator "CCGT" in "outputs/network.nc" has "start_up_cost" equal to 14400

  Scenario: a start cost of zero with no start fuel is still a start priced at zero
    Given a Plexos model
    And the model contains generator "FreeStart" with "node=Grid_Node, fuel=Gas, Max Capacity=100, Heat Rate=8, Start Cost=0"
    And the model is saved as "inputs/free_start.xml"
    When I run translate against "inputs/free_start.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the file "decisions.md" contains "`plexos.Generator.FreeStart.Start Cost` = 0.0 $ | `pypsa.Generator.FreeStart.start_up_cost` = 0.0 $"

  Scenario: a generator naming several start fuels starts on the one its heat rate uses
    Given a Plexos model
    And the model contains fuel "Gas" with price 8
    And the model contains fuel "Distillate" with price 25
    And the model contains generator "DualStart" with "node=Grid_Node, fuel=Gas, Max Capacity=100, Heat Rate=7"
    And generator "DualStart" burns 100 GJ of fuel "Gas" to start
    And generator "DualStart" burns 1800 GJ of fuel "Distillate" to start
    And the model contains generator "NeitherStart" with "node=Grid_Node, category=Gas, Max Capacity=100, Min Stable Level=50"
    And generator "NeitherStart" burns 100 GJ of fuel "Gas" to start
    And generator "NeitherStart" burns 1800 GJ of fuel "Distillate" to start
    And the model is saved as "inputs/several_start_fuels.xml"
    When I run translate against "inputs/several_start_fuels.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA generator "DualStart" in "outputs/network.nc" has "start_up_cost" equal to 800
    # A generator burning no fuel has no heat rate to prefer one by, so the largest start wins.
    And the PyPSA generator "NeitherStart" in "outputs/network.nc" has "start_up_cost" equal to 45000
