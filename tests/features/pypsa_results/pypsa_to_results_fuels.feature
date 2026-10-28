@slow @fork_unsafe
Feature: pypsa-to-results counts electricity, and the emissions of the fuels that are not electricity
  A network can hold the buses of fuels that are not electricity, as sienna-to-pypsa writes them
  for an OSeMOSYS model. The results format counts electricity, so a generator, a link and a
  load of a fuel have no production, dispatch, flow or load row. A plant link draws a fuel at
  bus0 and puts out electricity at bus1, so it has the rows of a plant. The emissions count each
  component that states a rate: the gas well for each MWh of gas, the plant link for each MWh
  of electricity, and the pipeline for each MWh that goes in.

  The invented network below has an electricity bus and two gas buses. The well makes 25 MW of
  gas. The plant link burns 20 MW of gas at an efficiency of 0.5. The pipeline moves 1 MW of
  gas. Each of the four hours stands for 2190 hours, so 8760 h, which is a whole year.

  Background:
    Given a PyPSA network
    And the network has 4 snapshots starting 2030-01-01 at 60 minute intervals
    And the network contains bus "node_a" carrier "AC" v_nom 380.0
    And the network contains bus "gas" carrier "gas" v_nom 1.0
    And the network contains bus "gas_b" carrier "gas" v_nom 1.0
    And the network contains generator "well" on "gas" carrier "gas" p_nom 1000.0 p_max_pu 1.0
    And the network contains generator "solar" on "node_a" carrier "solar" p_nom 50.0 p_max_pu 1.0
    And the network contains link "plant" from "gas" to "node_a" with capacity 400.0 MW efficiency 0.5 carrier "gas-cc"
    And the network contains link "pipe" from "gas" to "gas_b" with capacity 100.0 MW efficiency 0.9 carrier "gas"
    And the network contains load "demand" on "node_a" with p_set 10.0 10.0 10.0 10.0
    And the network contains load "gas_demand" on "gas_b" with p_set 0.9 0.9 0.9 0.9
    And the generator "well" dispatches 25 25 25 25
    And the generator "solar" dispatches 0 0 0 0
    And the link "plant" carries flow 20 20 20 20
    And the link "pipe" carries flow 1 1 1 1
    And the snapshot weightings are 2190 2190 2190 2190
    And the generator snapshot weightings are 2190 2190 2190 2190
    And the network objective is 1000.0
    And the network is saved as "inputs/solved.nc"
    And a file "inputs/extensions.json" containing the lines:
      | line |
      | {"generator": [{"name": "well", "emission_rates_t_per_mwh": {"CO2": 0.2}}, {"name": "plant", "emission_rates_t_per_mwh": {"CO2": 0.5}, "own_emission_rates_t_per_mwh": {"CO2": 0.1}}], "conversion": [{"name": "pipe", "emission_rates_t_per_mwh": {"CO2": 0.01}}]} |

  Scenario: The production and the capacity of electricity leave out the components of a fuel
    The plant link puts out 10 MW of electricity for 8760 h. Its capacity is the electricity
    that it can put out, 400 MW × 0.5.
    When I run the pipeline "pypsa-to-results" with overrides "source.path=inputs/solved.nc source.extensions_json_path=inputs/extensions.json"
    Then the pipeline exit code is 0
    And the results parquet "outputs/results.parquet" has these "production" rows:
      | variable   | component | category | timestamp           | value |
      | production | plant     | gas-cc   | 2030-01-01T00:00:00 | 87600 |
      | production | solar     | solar    | 2030-01-01T00:00:00 | 0     |
    And the results parquet "outputs/results.parquet" has these "installed_capacity" rows:
      | variable           | component | category | timestamp           | value |
      | installed_capacity | plant     | gas-cc   | 2030-01-01T00:00:00 | 200   |
      | installed_capacity | solar     | solar    | 2030-01-01T00:00:00 | 50    |

  Scenario: The emissions count the gas well, the own rate of the plant link and the pipeline
    The well emits 25 MW × 8760 h × 0.2 t/MWh, which is 43800 t. The plant link emits 87600 MWh ×
    0.1 t/MWh, which is 8760 t, as the well already counts its gas. The pipeline emits 1 MW ×
    8760 h × 0.01 t/MWh, which is 87.6 t.
    When I run the pipeline "pypsa-to-results" with overrides "source.path=inputs/solved.nc source.extensions_json_path=inputs/extensions.json"
    Then the pipeline exit code is 0
    And the results parquet "outputs/results.parquet" has these "emissions" rows:
      | variable  | component | category | timestamp           | value   |
      | emissions | CO2       |          | 2030-01-01T00:00:00 | 52647.6 |

  Scenario: The hourly rows of electricity hold the plant link, and leave out the gas
    When I run the pipeline "pypsa-to-results" with overrides "source.path=inputs/solved.nc source.extensions_json_path=inputs/extensions.json"
    Then the pipeline exit code is 0
    And the results parquet "outputs/results.parquet" has these "dispatch" rows:
      | variable | component | category | timestamp           | value |
      | dispatch | plant     | gas-cc   | 2030-01-01T00:00:00 | 10    |
      | dispatch | plant     | gas-cc   | 2030-01-01T01:00:00 | 10    |
      | dispatch | plant     | gas-cc   | 2030-01-01T02:00:00 | 10    |
      | dispatch | plant     | gas-cc   | 2030-01-01T03:00:00 | 10    |
      | dispatch | solar     | solar    | 2030-01-01T00:00:00 | 0     |
      | dispatch | solar     | solar    | 2030-01-01T01:00:00 | 0     |
      | dispatch | solar     | solar    | 2030-01-01T02:00:00 | 0     |
      | dispatch | solar     | solar    | 2030-01-01T03:00:00 | 0     |
    And the results parquet "outputs/results.parquet" has these "load" rows:
      | variable | component | category | timestamp           | value |
      | load     | demand    |          | 2030-01-01T00:00:00 | 10    |
      | load     | demand    |          | 2030-01-01T01:00:00 | 10    |
      | load     | demand    |          | 2030-01-01T02:00:00 | 10    |
      | load     | demand    |          | 2030-01-01T03:00:00 | 10    |
    And the results parquet "outputs/results.parquet" has these "flow" rows:
      | variable | component | category | timestamp | value |
