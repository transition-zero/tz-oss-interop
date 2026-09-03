Feature: results pipelines are kept separate from regular translations
  Results pipelines (the ones whose destination framework is "results") live in a
  dedicated subdirectory. Compare draws its selectable frameworks from those
  pipelines, while translate offers only framework-to-framework pipelines and never
  the results format as a destination.

  Scenario: translate does not offer the results format as a destination
    When I start translate and choose source framework "pypsa"
    Then the select prompt "Destination framework?" offered exactly "sienna"

  Scenario: compare offers the frameworks that have a results pipeline
    When I start compare
    Then the select prompt "First result's framework?" offered exactly "caiso-plexos, pypsa, sienna"
