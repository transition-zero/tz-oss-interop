@slow @fork_unsafe
Feature: Sienna to PyPSA Pipeline translates a TwoWindingTransformer to a PyPSA Transformer
  A TwoWindingTransformer states its name, and the TransformerCircuit it names holds the
  electrical data. The step reads the two as one row, resolves the Arc to bus0 and bus1, and
  rebases the impedance: Sienna states it per unit of base_power, and PyPSA per unit of s_nom.

  Scenario: a transformer becomes a PyPSA Transformer with its endpoints, rating and impedance
    Given a Sienna system
    And the system contains a bus "high" at 220.0 kV
    And the system contains a bus "low" at 110.0 kV
    And the system contains a transformer "step_1" from "high" to "low" with rating 4.29 r 0.01 x 0.1
    And the system is saved as "inputs/transformer.json"
    When I run translate against "inputs/transformer.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 1 transformer
    And the PyPSA network "outputs/network.nc" has 0 lines
    And the PyPSA network "outputs/network.nc" transformer "step_1" has bus0 "high"
    And the PyPSA network "outputs/network.nc" transformer "step_1" has bus1 "low"
    And the PyPSA network "outputs/network.nc" transformer "step_1" attribute "s_nom" is 429.0
    And the PyPSA network "outputs/network.nc" transformer "step_1" attribute "r" is 0.0429
    And the PyPSA network "outputs/network.nc" transformer "step_1" attribute "x" is 0.429
    And the PyPSA network "outputs/network.nc" transformer "step_1" attribute "tap_ratio" is 1.0
    And the file "decisions.md" contains "| `sienna.TransformerCircuit.step_1.rating` = 4.29 | `pypsa.Transformer.step_1.s_nom` = 429.0 MVA | rating * base_power |  | sienna-to-pypsa | sienna_to_pypsa_map_transmission |"
    And the file "decisions.md" contains "r * s_nom / base_power"

  Scenario: both base voltages have no PyPSA column, because the two buses state the voltage
    Given a Sienna system
    And the system contains a bus "high" at 220.0 kV
    And the system contains a bus "low" at 110.0 kV
    And the system contains a transformer "step_1" from "high" to "low" with rating 4.29 r 0.01 x 0.1
    And the system is saved as "inputs/transformer_voltages.json"
    When I run translate against "inputs/transformer_voltages.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 1 transformer
    And the file "decisions.md" contains "PyPSA takes the voltage of a transformer from its two buses, so a stated base voltage has no column of its own"

  Scenario: a tap that is not nominal becomes the PyPSA tap_ratio
    Given a Sienna system
    And the system contains a bus "high" at 220.0 kV
    And the system contains a bus "low" at 110.0 kV
    And the system contains a transformer "step_1" from "high" to "low" with rating 4.29 r 0.01 x 0.1
    And the transformer "step_1" has tap 1.05
    And the system is saved as "inputs/transformer_tap.json"
    When I run translate against "inputs/transformer_tap.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" transformer "step_1" attribute "tap_ratio" is 1.05
    And the file "decisions.md" contains "| `sienna.TransformerCircuit.step_1.tap` = 1.05 | `pypsa.Transformer.step_1.tap_ratio` = 1.05 | tap -> tap_ratio |  | sienna-to-pypsa | sienna_to_pypsa_map_transmission |"

  Scenario: the ext num_parallel of a transformer round-trips to PyPSA
    Given a Sienna system
    And the system contains a bus "high" at 220.0 kV
    And the system contains a bus "low" at 110.0 kV
    And the system contains a transformer "step_1" from "high" to "low" with rating 4.29 r 0.01 x 0.1
    And the TwoWindingTransformer "step_1" has ext length 42.0 and num_parallel 2
    And the system is saved as "inputs/transformer_ext.json"
    When I run translate against "inputs/transformer_ext.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" transformer "step_1" attribute "num_parallel" is 2.0
    And the file "decisions.md" contains "| `sienna.TransformerCircuit.step_1.extensions.num_parallel` = 2.0 | `pypsa.Transformer.step_1.num_parallel` = 2.0 | extensions.num_parallel (PyPSA round-trip) |  | sienna-to-pypsa | sienna_to_pypsa_map_transmission |"

  Scenario: a stated carrier and length stay in the sidecar, which PyPSA has no column for
    Given a Sienna system
    And the system contains a bus "high" at 220.0 kV
    And the system contains a bus "low" at 110.0 kV
    And the system contains a transformer "step_1" from "high" to "low" with rating 4.29 r 0.01 x 0.1
    And the TwoWindingTransformer "step_1" has ext carrier "AC"
    And the TwoWindingTransformer "step_1" has ext length 42.0 and num_parallel 2
    And the system is saved as "inputs/transformer_length.json"
    When I run translate against "inputs/transformer_length.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the file "outputs/extensions.json" parses as JSON transformer extension record for "step_1" having "length" set to 42.0
    And the file "outputs/extensions.json" parses as JSON transformer extension record for "step_1" having "carrier" set to "AC"
    And the file "decisions.md" contains "relayed unchanged to extensions.json, as PyPSA has no attribute for it"

  Scenario: a transformer that names a circuit the document does not state is left out
    Given a Sienna system
    And the system contains a bus "high" at 220.0 kV
    And the system contains a bus "low" at 110.0 kV
    And the system contains a transformer "step_1" from "high" to "low" with rating 4.29 r 0.01 x 0.1
    And the system contains a transformer "step_2" from "high" to "low" with rating 2.0 r 0.01 x 0.1
    And the transformer "step_2" names circuit 9999
    And the system is saved as "inputs/transformer_dangling.json"
    When I run translate against "inputs/transformer_dangling.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 1 transformer
    And the PyPSA network "outputs/network.nc" has no transformer "step_2"
    And the log contains "1 transformers name a TransformerCircuit that the document does not state, so each is left out"

  Scenario: a transformer in NATURAL_UNITS is left out, because the reader converts COMPONENT_BASE only
    Given a Sienna system
    And the system contains a bus "high" at 220.0 kV
    And the system contains a bus "low" at 110.0 kV
    And the system contains a transformer "step_1" from "high" to "low" with rating 4.29 r 0.01 x 0.1
    And the transformer "step_1" states power_units NATURAL_UNITS
    And the system contains a transformer "step_2" from "high" to "low" with rating 2.0 r 0.01 x 0.1
    And the system is saved as "inputs/transformer_natural.json"
    When I run translate against "inputs/transformer_natural.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 1 transformer
    And the PyPSA network "outputs/network.nc" has no transformer "step_1"
    And the log contains "1 transformers state a power basis this reader does not convert, so each is left out"

  Scenario: a transformer that states a rating of zero is left out, because s_nom divides the impedance
    Given a Sienna system
    And the system contains a bus "high" at 220.0 kV
    And the system contains a bus "low" at 110.0 kV
    And the system contains a transformer "step_1" from "high" to "low" with rating 0.0 r 0.01 x 0.1
    And the system contains a transformer "step_2" from "high" to "low" with rating 2.0 r 0.01 x 0.1
    And the system is saved as "inputs/transformer_unrated.json"
    When I run translate against "inputs/transformer_unrated.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 1 transformer
    And the PyPSA network "outputs/network.nc" has no transformer "step_1"
    And the log contains "1 transformers state a rating of zero, so each is left out"
