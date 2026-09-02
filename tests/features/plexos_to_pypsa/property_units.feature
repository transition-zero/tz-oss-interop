@slow @fork_unsafe
Feature: Read a PLEXOS property in the unit the model states it in

  PLEXOS declares a unit for every property, and two publishers of the same format state
  the same property differently: a heat rate in GJ/MWh or in BTU/kWh, a carbon price per
  tonne, per kilogram or per pound. A value converts as it stages, so every mapping reads
  one convention and the audit trail still names what the model itself wrote.

  Scenario: a plant stated in imperial units costs the same as the metric plant it is
    Given a Plexos model
    And the model measures in "Imperial"
    And the model states "Heat Rate" in "BTU/kWh"
    And the model states "Price" in "$/MMBTU"
    And the model states "Production Rate" in "lb/MMBTU"
    And the model contains fuel "Natural Gas" with price 3
    And the model contains generator "GasPlant" with "node=Grid_Node, fuel=Natural Gas, Max Capacity=500, Heat Rate=8000, VO&M Charge=2"
    And the model is saved as "inputs/imperial.xml"
    When I run translate against "inputs/imperial.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA generator "GasPlant" in "outputs/network.nc" has "marginal_cost" equal to 26
    And the PyPSA generator "GasPlant" in "outputs/network.nc" has "efficiency" equal to 0.4265177
    # The value reads in interop's own unit, and the trail names the model's.
    And the file "decisions.md" contains "`plexos.Generator.GasPlant.Heat Rate` = 8.4404472 GJ/MWh"
    And the file "decisions.md" contains "`plexos.Fuel.Natural Gas.Price` = 2.8434512332474515 $/GJ"

  Scenario: a carbon price stated per pound prices the same carbon as one stated per tonne
    Given a Plexos model
    And the model measures in "Imperial"
    And the model states "Heat Rate" in "BTU/kWh"
    And the model states "Production Rate" in "lb/MMBTU"
    And the model contains fuel "Natural Gas" with price 0
    And the model contains emission "CO2" with price 0.05 on fuel "Natural Gas" production rate 100
    And the model states "Price" in "$/lb"
    And the model contains generator "GasPlant" with "node=Grid_Node, fuel=Natural Gas, Max Capacity=500, Heat Rate=8000"
    And the model is saved as "inputs/carbon.xml"
    When I run translate against "inputs/carbon.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA generator "GasPlant" in "outputs/network.nc" has "marginal_cost" equal to 40
    And the file "decisions.md" contains "`plexos.Emission.CO2.Price` = 110.2311310924388 $/tonne"
    And the file "decisions.md" contains "`plexos.Emission.CO2.Production Rate` = 42.99225946227115 kg/GJ"

  Scenario: a model stating interop's own units is left alone
    Given a Plexos model
    And the model measures in "Metric"
    And the model states "Heat Rate" in "GJ/MWh"
    And the model states "Price" in "$/GJ"
    And the model contains fuel "Natural Gas" with price 3
    And the model contains generator "GasPlant" with "node=Grid_Node, fuel=Natural Gas, Max Capacity=500, Heat Rate=8, VO&M Charge=2"
    And the model is saved as "inputs/metric.xml"
    When I run translate against "inputs/metric.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA generator "GasPlant" in "outputs/network.nc" has "marginal_cost" equal to 26
    And the file "decisions.md" contains "`plexos.Generator.GasPlant.Heat Rate` = 8.0 GJ/MWh<br>"

  Scenario: an imperial model reads its own energy unit as MMBTU
    Given a Plexos model
    And the model measures in "Imperial"
    And the model states "Heat Rate" in "GJ/MWh"
    And the model states "Price" in "$/~"
    And the model contains fuel "Natural Gas" with price 3
    And the model contains generator "GasPlant" with "node=Grid_Node, fuel=Natural Gas, Max Capacity=500, Heat Rate=8"
    And the model is saved as "inputs/generic_imperial.xml"
    When I run translate against "inputs/generic_imperial.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA generator "GasPlant" in "outputs/network.nc" has "marginal_cost" equal to 22.7476099

  Scenario: a metric model reads its own energy unit as GJ
    Given a Plexos model
    And the model measures in "Metric"
    And the model states "Heat Rate" in "GJ/MWh"
    And the model states "Price" in "$/~"
    And the model contains fuel "Natural Gas" with price 3
    And the model contains generator "GasPlant" with "node=Grid_Node, fuel=Natural Gas, Max Capacity=500, Heat Rate=8"
    And the model is saved as "inputs/generic_metric.xml"
    When I run translate against "inputs/generic_metric.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA generator "GasPlant" in "outputs/network.nc" has "marginal_cost" equal to 24

  Scenario: a unit interop cannot convert leaves the value as the model wrote it
    Given a Plexos model
    And the model states "Heat Rate" in "furlongs/fortnight"
    And the model contains fuel "Natural Gas" with price 3
    And the model contains generator "GasPlant" with "node=Grid_Node, fuel=Natural Gas, Max Capacity=500, Heat Rate=8"
    And the model is saved as "inputs/unknown_unit.xml"
    When I run translate against "inputs/unknown_unit.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA generator "GasPlant" in "outputs/network.nc" has "marginal_cost" equal to 24
    And the log contains "Heat Rate in furlongs/fortnight"

  Scenario: a carbon price per "ton" is not read as one per tonne
    A short ton and a tonne differ by about a tenth, and which one a model means by "ton"
    depends on the publisher. Converting as if it were a tonne would put a wrong carbon
    adder on every thermal plant without saying so, so the unit is reported as one interop
    does not read and the value stays as the model wrote it.
    Given a Plexos model
    And the model states "Heat Rate" in "GJ/MWh"
    And the model contains fuel "Natural Gas" with price 3
    And the model contains emission "CO2" with price 0.05 on fuel "Natural Gas" production rate 100
    And the model states "Price" in "$/ton"
    And the model contains generator "GasPlant" with "node=Grid_Node, fuel=Natural Gas, Max Capacity=500, Heat Rate=8"
    And the model is saved as "inputs/short_ton.xml"
    When I run translate against "inputs/short_ton.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the log contains "Price in $/ton"

  Scenario: a profile in a unit that needs converting says so, since only a stated value converts
    Given a Plexos model
    And the model states "Rating" in "kW"
    And the model contains data file "SolarHourly" at "profiles/solar.csv" with hourly values "10, 20, 30"
    And the model contains generator "Solar1" with "node=Grid_Node, category=Solar, Max Capacity=100, Rating=file:SolarHourly"
    And the model is saved as "inputs/profile_unit.xml"
    When I run translate against "inputs/profile_unit.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the log contains "Rating in kW"

  Scenario: the lowest band of a banded heat rate is the one the cost reads
    Given a Plexos model
    And the model contains fuel "Natural Gas" with price 3
    And the model contains generator "GasPlant" with "node=Grid_Node, fuel=Natural Gas, Max Capacity=500"
    And the model contains "Heat Rate" 12 in band 10 for generator "GasPlant"
    And the model contains "Heat Rate" 9 in band 2 for generator "GasPlant"
    And the model contains "Heat Rate" 8 in band 1 for generator "GasPlant"
    And the model is saved as "inputs/banded.xml"
    When I run translate against "inputs/banded.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA generator "GasPlant" in "outputs/network.nc" has "marginal_cost" equal to 24

  Scenario: a start offtake stated in the model's own imperial energy unit converts to GJ
    Given a Plexos model
    And the model measures in "Imperial"
    And the model states "Offtake at Start" in "~"
    And the model states "Price" in "$/~"
    And the model contains fuel "Gas" with price 8
    And the model contains generator "CCGT" with "node=Grid_Node, fuel=Gas, Max Capacity=100, Heat Rate=7"
    And generator "CCGT" burns 1800 GJ of fuel "Gas" to start
    And the model is saved as "inputs/imperial_start.xml"
    When I run translate against "inputs/imperial_start.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    # 1800 MMBTU is 1899.1 GJ, and $8/MMBTU is $7.5834/GJ, so the start costs what it did in
    # the model's own units. Reading the offtake unconverted would price it 5% low.
    Then the PyPSA generator "CCGT" in "outputs/network.nc" has "start_up_cost" equal to 14400
    And the file "decisions.md" contains "`plexos.Generator.CCGT.Offtake at Start` = 1899.10062 GJ"
