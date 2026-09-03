Feature: composed pipeline
  A composed pipeline names an ordered list of existing pipelines and runs each leg
  in full, including its sinks. Each leg's input is wired to an earlier leg's output
  by reference, so a relocated output cannot silently break the chain. The composed
  pipeline is picked and run from the same translate menu as any other pipeline.

  Background:
    Given a payload file "inputs/source.json" carrying "carried-through"
    And a source plugin "read_payload" reading a payload file
    And a step plugin "note_decision" recording one decision
    And a pipeline "alpha-to-beta" reading "inputs/source.json" and writing to "outputs/interim.json"
    And a pipeline "beta-to-gamma" reading a referenced file and writing to "outputs/final.json"

  Scenario: the decisions report attributes every event to the leg that produced it
    Given a composed pipeline "alpha-to-gamma" chaining "alpha-to-beta" then "beta-to-gamma"
    When I run translate with source "alpha" destination "gamma" pipeline "alpha-to-gamma"
    Then the file "decisions.md" contains "alpha-to-beta"
    And the file "decisions.md" contains "beta-to-gamma"

  Scenario: validate checks a chain's first leg only and says which leg that was
    Given a composed pipeline "alpha-to-gamma" chaining "alpha-to-beta" then "beta-to-gamma"
    When I run validate with source "alpha" destination "gamma" pipeline "alpha-to-gamma"
    Then the printed output contains "checked the first leg only (alpha-to-beta)"

  Scenario: a chain carries its payload over a hand-off left in neither leg's outputs
    Given a composed pipeline "alpha-to-gamma" chaining "alpha-to-beta" then "beta-to-gamma"
    When I run translate with source "alpha" destination "gamma" pipeline "alpha-to-gamma"
    Then the file "outputs/final.json" contains "carried-through"
    And the file "outputs/interim.json" does not exist
    And the run reported a hand-off file "interim.json" and it is now cleaned up

  Scenario: everything an interior leg writes stays out of the project directory
    Given a sink plugin "emit_note" writing to a path only it knows
    And a pipeline "alpha-to-beta" reading "inputs/source.json" and also writing a note
    And a composed pipeline "alpha-to-gamma" chaining "alpha-to-beta" then "beta-to-gamma"
    When I run translate with source "alpha" destination "gamma" pipeline "alpha-to-gamma"
    Then the file "outputs/final.json" contains "carried-through"
    And the file "outputs/note.json" does not exist

  Scenario: the last leg's outputs are the run's, whatever an earlier leg wrote alongside
    Given a sink plugin "emit_note" writing to a path only it knows
    And a pipeline "alpha-to-beta" reading "inputs/source.json" and also writing a note
    And a pipeline "beta-to-gamma" reading a referenced file and also writing a note
    And a composed pipeline "alpha-to-gamma" chaining "alpha-to-beta" then "beta-to-gamma"
    When I run translate with source "alpha" destination "gamma" pipeline "alpha-to-gamma"
    Then the file "outputs/note.json" contains "written"
    And the run wrote "outputs/note.json" into the project exactly once

  Scenario: two interior legs writing the same filename each keep their own copy
    Given a sink plugin "emit_note" writing to a path only it knows
    And a composed pipeline "alpha-to-epsilon" chaining three legs that each write a note
    When I run translate headlessly with pipeline "alpha-to-epsilon" keeping staging
    Then the file "outputs/final.json" contains "carried-through"
    And the run reported 2 hand-off files named "note.json", all still there

  Scenario: the chain names the hand-off, and the leg producing it need not
    Given a pipeline "alpha-to-beta" reading "inputs/source.json" and naming no output path
    And a composed pipeline "alpha-to-gamma" chaining "alpha-to-beta" then "beta-to-gamma" handing over "interim.json"
    When I run translate with source "alpha" destination "gamma" pipeline "alpha-to-gamma"
    Then the file "outputs/final.json" contains "carried-through"

  Scenario: a hand-off no manifest names is rejected, pointing at the chain
    Given a pipeline "alpha-to-beta" reading "inputs/source.json" and naming no output path
    And a composed pipeline "alpha-to-gamma" chaining "alpha-to-beta" then "beta-to-gamma"
    When I run translate with source "alpha" destination "gamma" pipeline "alpha-to-gamma"
    Then the printed output contains "sets no param 'output_path'. Nothing can reference it"
    And the printed output contains "Set 'emit_json.output_path' in the params of leg 'alpha-to-beta'"
    And the file "outputs/final.json" does not exist

  Scenario: keeping staging leaves the interior hand-off on disk to inspect
    Given a composed pipeline "alpha-to-gamma" chaining "alpha-to-beta" then "beta-to-gamma"
    When I run translate headlessly with pipeline "alpha-to-gamma" keeping staging
    Then the file "outputs/final.json" contains "carried-through"
    And the run reported a hand-off file "interim.json" and it is still there

  Scenario: only the run's own boundary uses the configured filesystem
    Given adapters.yaml binds filesystem to "http_filesystem"
    And an http payload at "https://example.test/in.json" carrying "carried-through"
    And a pipeline "url-alpha-to-beta" reading "https://example.test/in.json" and writing to "outputs/interim.json"
    And a pipeline "url-beta-to-gamma" reading a referenced file and writing to "https://example.test/out.json"
    And a composed pipeline "url-to-url" chaining "url-alpha-to-beta" then "url-beta-to-gamma"
    When I run translate with source "alpha" destination "gamma" pipeline "url-to-url"
    Then the http filesystem was never given the hand-off file "interim.json"
    And the http destination "https://example.test/out.json" contains "carried-through"

  Scenario: a chain refuses a step override, and says where that param belongs
    Given a composed pipeline "alpha-to-gamma" chaining "alpha-to-beta" then "beta-to-gamma"
    When I run translate headlessly with pipeline "alpha-to-gamma" overriding "step[0].note=changed"
    Then the log contains "A composed pipeline takes no step override"
    And the log contains "under 'params:'"
    And the file "outputs/final.json" does not exist

  Scenario: adjacent legs must agree on the boundary framework
    Given a pipeline "delta-to-gamma" reading a referenced file and writing to "outputs/final.json"
    And a composed pipeline "alpha-to-gamma" chaining "alpha-to-beta" then "delta-to-gamma"
    When I run translate with source "alpha" destination "gamma" pipeline "alpha-to-gamma"
    Then the printed output contains "'alpha-to-beta' ends in framework 'beta'"
    And the printed output contains "'delta-to-gamma' starts from 'delta'"
    And the file "outputs/final.json" does not exist

  Scenario: a leg that references nothing upstream leaves the chain unwired
    Given a composed pipeline "alpha-to-gamma" chaining "alpha-to-beta" then "beta-to-gamma" with no wiring
    When I run translate with source "alpha" destination "gamma" pipeline "alpha-to-gamma"
    Then the printed output contains "'beta-to-gamma' sets no param referencing 'alpha-to-beta'"
    And the file "outputs/final.json" does not exist

  Scenario: repeating an upstream output as a literal does not count as wiring
    Given a composed pipeline "alpha-to-gamma" chaining "alpha-to-beta" then "beta-to-gamma" wiring "read_payload.path" to "outputs/interim.json"
    When I run translate with source "alpha" destination "gamma" pipeline "alpha-to-gamma"
    Then the printed output contains "'beta-to-gamma' sets no param referencing 'alpha-to-beta'"
    And the file "outputs/final.json" does not exist

  Scenario: a reference to a node the leg does not have names the nodes it does
    Given a composed pipeline "alpha-to-gamma" chaining "alpha-to-beta" then "beta-to-gamma" wiring "read_payload.path" to "$alpha-to-beta.emit_nothing.output_path"
    When I run translate with source "alpha" destination "gamma" pipeline "alpha-to-gamma"
    Then the printed output contains "has no node named 'emit_nothing'"
    And the printed output contains "'emit_json'"

  Scenario: a reference to a pipeline the chain does not run names the legs it does
    Given a composed pipeline "alpha-to-gamma" chaining "alpha-to-beta" then "beta-to-gamma" wiring "read_payload.path" to "$not-a-leg.emit_json.output_path"
    When I run translate with source "alpha" destination "gamma" pipeline "alpha-to-gamma"
    Then the printed output contains "which this composed pipeline does not run"

  Scenario: a reference to a param the node does not set says to set it
    Given a composed pipeline "alpha-to-gamma" chaining "alpha-to-beta" then "beta-to-gamma" wiring "read_payload.path" to "$alpha-to-beta.emit_json.indent"
    When I run translate with source "alpha" destination "gamma" pipeline "alpha-to-gamma"
    Then the printed output contains "Set 'emit_json.indent' in the params of leg 'alpha-to-beta'"
    And the printed output contains "'output_path'"

  Scenario: a reference must name the pipeline, the node and the param it reads
    Given a composed pipeline "alpha-to-gamma" chaining "alpha-to-beta" then "beta-to-gamma" wiring "read_payload.path" to "$alpha-to-beta.output_path"
    When I run translate with source "alpha" destination "gamma" pipeline "alpha-to-gamma"
    Then the printed output contains "Malformed reference '$alpha-to-beta.output_path'"

  Scenario: a param key must name the node and the param it sets
    Given a composed pipeline "alpha-to-gamma" chaining "alpha-to-beta" then "beta-to-gamma" wiring "path" to "$alpha-to-beta.emit_json.output_path"
    When I run translate with source "alpha" destination "gamma" pipeline "alpha-to-gamma"
    Then the printed output contains "Malformed param key 'path'"

  Scenario: a reference must point at a value rather than at another reference
    Given a composed pipeline "alpha-to-gamma" chaining "alpha-to-beta" then "beta-to-gamma" where each leg reads the other's input
    When I run translate with source "alpha" destination "gamma" pipeline "alpha-to-gamma"
    Then the printed output contains "which is another reference rather than a value"

  Scenario: a pipeline with two sinks of one plugin cannot be referenced by name
    Given a pipeline "alpha-to-beta" with two "emit_json" sinks
    And a composed pipeline "alpha-to-gamma" chaining "alpha-to-beta" then "beta-to-gamma"
    When I run translate with source "alpha" destination "gamma" pipeline "alpha-to-gamma"
    Then the printed output contains "more than one node named 'emit_json'"

  Scenario: a chain cannot name a composed pipeline as one of its legs
    Given a composed pipeline "alpha-to-gamma" chaining "alpha-to-beta" then "beta-to-gamma"
    And a composed pipeline "outer" chaining "alpha-to-beta" then "alpha-to-gamma"
    When I run translate with source "alpha" destination "gamma" pipeline "outer"
    Then the printed output contains "'alpha-to-gamma' is itself a composed pipeline"

  Scenario: a mapping pipeline derives the file a leg consumes, from the one file the user wrote
    Given an object mappings file "inputs/object_mappings.yaml" naming "Alamitos CC 1" as "gas_cc"
    And a mapping pipeline "derive-carriers" turning object mappings into carrier mappings
    And a step plugin "report_carriers" recording the carriers it was given
    And a pipeline "beta-to-gamma" reporting carriers and writing to "outputs/final.json"
    And a composed pipeline "alpha-to-gamma" with mappings "derive-carriers" chaining "alpha-to-beta" then "beta-to-gamma"
    When I run translate pipeline "alpha-to-gamma" with user mappings "inputs/object_mappings.yaml"
    Then the file "outputs/final.json" contains "gas_cc"
    And the user was asked for a mappings file exactly once

  Scenario: a mappings file a later leg derives cannot satisfy an earlier one
    Given a step plugin "report_carriers" recording the carriers it was given
    And a carrier mappings file "inputs/carriers.yaml" naming "gas_cc"
    And a pipeline "alpha-to-beta" reading "inputs/source.json" and reporting carriers
    And a pipeline "beta-to-gamma" deriving carriers and writing to "outputs/final.json"
    And a composed pipeline "alpha-to-gamma" chaining "alpha-to-beta" then "beta-to-gamma"
    When I run translate pipeline "alpha-to-gamma" with user mappings "inputs/carriers.yaml"
    Then the file "outputs/final.json" contains "carried-through"
    And the user was asked for a mappings file exactly once

  Scenario: two sinks of one pipeline writing one kind of mappings file is rejected
    Given a pipeline "alpha-to-beta" deriving carriers twice
    When I run translate with source "alpha" destination "beta" pipeline "alpha-to-beta"
    Then the printed output contains "Sink 'emit_late_carriers' and sink 'emit_late_carriers' both write CarrierMappings mappings"

  Scenario: two legs writing one kind of mappings file is rejected before anything runs
    Given an object mappings file "inputs/object_mappings.yaml" naming "Alamitos CC 1" as "gas_cc"
    And a mapping pipeline "derive-carriers" turning object mappings into carrier mappings
    And a pipeline "beta-to-gamma" deriving carriers and writing to "outputs/final.json"
    And a composed pipeline "alpha-to-gamma" with mappings "derive-carriers" chaining "alpha-to-beta" then "beta-to-gamma"
    When I run translate pipeline "alpha-to-gamma" with user mappings "inputs/object_mappings.yaml"
    Then the printed output contains "Pipeline 'derive-carriers' sink 'emit_fixture_carriers' and pipeline 'beta-to-gamma' sink 'emit_late_carriers' both write CarrierMappings mappings"
    And the file "outputs/final.json" does not exist

  Scenario: a leg needing a mappings file nobody wrote says so rather than crashing
    Given a step plugin "report_carriers" recording the carriers it was given
    And a pipeline "beta-to-gamma" reporting carriers and writing to "outputs/final.json"
    And a composed pipeline "alpha-to-gamma" chaining "alpha-to-beta" then "beta-to-gamma"
    When I run translate headlessly with pipeline "alpha-to-gamma"
    Then the log contains "requires a CarrierMappings user mappings file"
    And the log contains "none was provided and nothing in this run derives one"
    And the file "outputs/final.json" does not exist

  Scenario: validate says so rather than asking for a file only a mapping pipeline could write
    Given an object mappings file "inputs/object_mappings.yaml" naming "Alamitos CC 1" as "gas_cc"
    And a mapping pipeline "derive-carriers" turning object mappings into carrier mappings
    And a pipeline "alpha-to-beta" whose source consumes carriers, reading "inputs/source.json"
    And a composed pipeline "alpha-to-gamma" with mappings "derive-carriers" chaining "alpha-to-beta" then "beta-to-gamma"
    When I run validate with source "alpha" destination "gamma" pipeline "alpha-to-gamma"
    Then the printed output contains "needs user mappings (CarrierMappings) that its own mapping pipelines derive"
    And the printed output contains "Translate it instead"
    And the user was not asked for a mappings file

  Scenario: a chain refuses without first asking for a file it would not accept
    Given an object mappings file "inputs/object_mappings.yaml" naming "Alamitos CC 1" as "gas_cc"
    And a mapping pipeline "derive-carriers" turning object mappings into carrier mappings
    And a pipeline "alpha-to-beta" whose source consumes carriers and one other kind, reading "inputs/source.json"
    And a composed pipeline "alpha-to-gamma" with mappings "derive-carriers" chaining "alpha-to-beta" then "beta-to-gamma"
    When I run validate with source "alpha" destination "gamma" pipeline "alpha-to-gamma"
    Then the user was not asked for a mappings file
    And the printed output contains "Translate it instead"

  Scenario: a derived mappings file is read back where the configured filesystem is http
    Given adapters.yaml binds filesystem to "http_filesystem"
    And an http payload at "https://example.test/in.json" carrying "carried-through"
    And an http object mappings file at "https://example.test/objects.yaml" naming "Alamitos CC 1" as "gas_cc"
    And a mapping pipeline "derive-carriers" turning object mappings into carrier mappings
    And a step plugin "report_carriers" recording the carriers it was given
    And a pipeline "url-alpha-to-beta" reading "https://example.test/in.json" and writing to "outputs/interim.json"
    And a pipeline "url-beta-to-gamma" reporting carriers and writing to "https://example.test/out.json"
    And a composed pipeline "url-to-url" with mappings "derive-carriers" chaining "url-alpha-to-beta" then "url-beta-to-gamma"
    When I run translate pipeline "url-to-url" with user mappings "https://example.test/objects.yaml"
    Then the http destination "https://example.test/out.json" contains "gas_cc"

  Scenario: a mapping pipeline reads the same input file the first leg reads
    Given an object mappings file "inputs/object_mappings.yaml" naming "Alamitos CC 1" as "gas_cc"
    And a mapping pipeline "derive-carriers" turning object mappings into carrier mappings
    And a step plugin "report_carriers" recording the carriers it was given
    And a pipeline "beta-to-gamma" reporting carriers and writing to "outputs/final.json"
    And a composed pipeline "alpha-to-gamma" with mappings "derive-carriers" reading the model that "alpha-to-beta" reads, then chaining it to "beta-to-gamma"
    When I run translate pipeline "alpha-to-gamma" with user mappings "inputs/object_mappings.yaml"
    Then the file "outputs/final.json" contains "gas_cc"
