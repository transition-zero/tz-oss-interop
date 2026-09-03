@slow @fork_unsafe
Feature: PLEXOS reserves are carried through the plexos_to_pypsa pipeline

  A reserve is an ancillary-service product a PyPSA network file cannot hold, so each one
  is carried into the extensions sidecar rather than dropped, and the network's silence
  about it is recorded in the translation report. The sidecar states the reserve in
  framework-neutral terms, so a later hop into a framework that does have reserves can
  restore it. The requirement is always megawatts: a number on the record where it holds
  at every snapshot, and a companion parquet where it varies.

  Scenario: a reserve is carried to the extensions sidecar
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generator "GasPlant" with "node=Grid_Node, fuel=Natural Gas, Max Capacity=500, Heat Rate=9, VO&M Charge=45"
    And the model contains reserve "SpinningReserve" of type 1 requiring 60 from generators "GasPlant"
    And the model is saved as "inputs/model.xml"
    When I run translate against "inputs/model.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the file "outputs/network.nc" exists
    And the extensions sidecar "outputs/extensions.json" carries reserve "SpinningReserve"
    And the extensions sidecar "outputs/extensions.json" reserve "SpinningReserve" lists contributor "GasPlant"
    And the file "decisions.md" contains "reserve carried to the extensions sidecar"

  Scenario: a Type code says which way the reserve moves output, and which product it is
    PLEXOS packs both into one integer. Type 3 is Regulation Raise, so the sidecar states
    the direction and the product separately, each in its own vocabulary.
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generator "GasPlant" with "node=Grid_Node, fuel=Natural Gas, Max Capacity=500, Heat Rate=9, VO&M Charge=45"
    And the model contains reserve "RegUp" of type 3 requiring 40 from generators "GasPlant"
    And the model is saved as "inputs/regulation.xml"
    When I run translate against "inputs/regulation.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the extensions sidecar "outputs/extensions.json" reserve "RegUp" is a "up" reserve of kind "regulating"

  Scenario: a Type code we cannot map states that we do not know, rather than nothing
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generator "GasPlant" with "node=Grid_Node, fuel=Natural Gas, Max Capacity=500, Heat Rate=9, VO&M Charge=45"
    And the model contains reserve "Mystery" of type 99 requiring 40 from generators "GasPlant"
    And the model is saved as "inputs/unknown_type.xml"
    When I run translate against "inputs/unknown_type.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the extensions sidecar "outputs/extensions.json" reserve "Mystery" is a "unknown" reserve of kind "unknown"

  Scenario: a Min Provision standing on its own is a quantity of megawatts, not a share
    Nothing tags this Min Provision, so 60 is 60 MW of reserve. Reading it as a fraction
    would ask for sixty times system load, so the sidecar states megawatts and no series.
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generator "GasPlant" with "node=Grid_Node, fuel=Natural Gas, Max Capacity=500, Heat Rate=9, VO&M Charge=45"
    And the model contains reserve "SpinningReserve" of type 1 requiring 60 from generators "GasPlant"
    And reserve "SpinningReserve" prices a shortage at 7000
    And reserve "SpinningReserve" is mutually exclusive
    And the model is saved as "inputs/megawatts.xml"
    When I run translate against "inputs/megawatts.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the extensions sidecar "outputs/extensions.json" reserve "SpinningReserve" requires 60 MW
    And the extensions sidecar "outputs/extensions.json" reserve "SpinningReserve" prices a shortage at 7000
    And the extensions sidecar "outputs/extensions.json" reserve "SpinningReserve" shares headroom
    And the file "decisions.md" contains "Min Provision is tagged to no profile"

  Scenario: a reserve PLEXOS marks Not mutually exclusive keeps its own headroom
    PLEXOS states Yes, No or Auto. A reserve marked No draws on headroom of its own, which
    a reader of the code alone could mistake for Yes, since only zero would be false.
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generator "GasPlant" with "node=Grid_Node, fuel=Natural Gas, Max Capacity=500, Heat Rate=9, VO&M Charge=45"
    And the model contains reserve "SpinningReserve" of type 1 requiring 60 from generators "GasPlant"
    And reserve "SpinningReserve" is not mutually exclusive
    And the model is saved as "inputs/exclusive_no.xml"
    When I run translate against "inputs/exclusive_no.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the extensions sidecar "outputs/extensions.json" reserve "SpinningReserve" keeps its own headroom

  Scenario: a Min Provision that is a share of the load profile becomes megawatts per snapshot
    This Min Provision is tagged to a Variable whose Profile is the same file the region's
    demand is read from, so 0.05 is five per cent of system load. The hop that holds the
    load resolves the rule, and what reaches the sidecar is the megawatts it asks for.
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains data file "SystemLoad" at "profiles/load.csv" with hourly values "1000, 2000, 3000"
    And the model contains region load "Grid" with peak 3000 from data file "SystemLoad"
    And the model contains variable "SystemLoadShare" profiling data file "SystemLoad"
    And the model contains generator "GasPlant" with "node=Grid_Node, fuel=Natural Gas, Max Capacity=500, Heat Rate=9, VO&M Charge=45"
    And the model contains reserve "SpinningReserve" of type 1 taking share 0.05 of variable "SystemLoadShare" from generators "GasPlant"
    And the model is saved as "inputs/share.xml"
    When I run translate against "inputs/share.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the extensions sidecar "outputs/extensions.json" reserve "SpinningReserve" reads its requirement from "reserves.parquet"
    And the companion parquet "outputs/reserves.parquet" states reserve "SpinningReserve" requiring 50 100 150 MW
    And the file "decisions.md" contains "megawatts at each snapshot in the companion parquet"

  Scenario: a Min Provision that is a share of something else states no requirement
    The Variable behind this Min Provision profiles a wind trace, not the demand the
    network's loads are built from, so what 0.05 is five per cent of cannot be stated in
    megawatts. The reserve travels without a requirement rather than with a number whose
    meaning is lost.
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains variable "WindTrace" profiling "profiles/wind.csv" with hourly values "10, 20, 30"
    And the model contains generator "GasPlant" with "node=Grid_Node, fuel=Natural Gas, Max Capacity=500, Heat Rate=9, VO&M Charge=45"
    And the model contains reserve "SpinningReserve" of type 1 taking share 0.05 of variable "WindTrace" from generators "GasPlant"
    And the model is saved as "inputs/unknown_share.xml"
    When I run translate against "inputs/unknown_share.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the extensions sidecar "outputs/extensions.json" carries reserve "SpinningReserve"
    And the extensions sidecar "outputs/extensions.json" reserve "SpinningReserve" states no requirement
    And the file "decisions.md" contains "which is not a profile the network's Loads are built from"

  Scenario: a reserve whose Min Provision is the placeholder zero states no requirement
    PLEXOS writes zero where a property supplies no value of its own. The sidecar states
    no requirement and the report says why, rather than passing off a zero as the amount
    of reserve the model wants.
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generator "GasPlant" with "node=Grid_Node, fuel=Natural Gas, Max Capacity=500, Heat Rate=9, VO&M Charge=45"
    And the model contains reserve "Regulation" of type 2 requiring 0 from generators "GasPlant"
    And the model is saved as "inputs/placeholder.xml"
    When I run translate against "inputs/placeholder.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the extensions sidecar "outputs/extensions.json" carries reserve "Regulation"
    And the extensions sidecar "outputs/extensions.json" reserve "Regulation" lists contributor "GasPlant"
    And the extensions sidecar "outputs/extensions.json" reserve "Regulation" states no requirement
    And the file "decisions.md" contains "Min Provision states neither a positive scalar nor a data file"

  Scenario: a requirement held in a data file the package omits states none
    A published model routinely ships its traces as separate downloads. Without the file
    there is no series to state the requirement from, so the record carries no reference
    rather than pointing at a companion parquet that will never be written.
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generator "GasPlant" with "node=Grid_Node, fuel=Natural Gas, Max Capacity=500, Heat Rate=9, VO&M Charge=45"
    And the model names data file "ReserveTrace" at "Traces\reserve.csv" but the package omits it
    And the model contains reserve "SpinningReserve" of type 1 reading its requirement from data file "ReserveTrace" from generators "GasPlant"
    And the model is saved as "inputs/missing_trace.xml"
    When I run translate against "inputs/missing_trace.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the extensions sidecar "outputs/extensions.json" carries reserve "SpinningReserve"
    And the extensions sidecar "outputs/extensions.json" reserve "SpinningReserve" states no requirement
    And the file "decisions.md" contains "the profile behind Min Provision did not stage"
