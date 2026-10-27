# An HVDC line states its direction in its operational flow limit

This spec replaces item 6, "HVDC limits", of
`2026-10-14-sienna-schemas-0.2-conformance-design.md`. The other items of that spec do not
change.

## The problem

Item 6 put the flow bounds of an HVDC line in its converter ratings:

- `rating_from = p_nom * p_max_pu`.
- `rating_to = -p_nom * p_min_pu` when `p_min_pu < 0`, else 0.0.
- `rating` is the larger of the two.

SiennaSchemas 0.2 gives these fields a different meaning. On `TwoTerminalGenericHVDCLine`:

- `rating` is the transfer rating of the DC line. It is required.
- `rating_from` and `rating_to` are the converter ratings at the two ends. Both are
  optional. An absent converter rating adds no limit beyond `rating`.
- `operational_flow_limit` is optional. It holds `from_to_min`, `from_to_max`,
  `to_from_min` and `to_from_max`, each 0 or more. It bounds the flow in each direction, in
  addition to the ratings.

Under item 6, a one-way link states `rating_to = 0.0`. A reader that follows the schema
sees a 0 MW converter at the to bus, so the link can deliver no power. Also, a reader of
tz-oss-interop raised an error when a valid document left out a converter rating.

## The design

1. **Writers.** `pypsa-to-sienna` and `plexos-to-sienna` write `rating` and
   `operational_flow_limit`. They do not write `rating_from` or `rating_to`, because
   neither source format states a converter rating.
   - PyPSA: `from_to_max = p_nom * p_max_pu`. `to_from_max = -p_nom * p_min_pu` when
     `p_min_pu < 0`, else 0.0. `rating` is the largest of `p_nom`, `from_to_max` and
     `to_from_max`. A reader caps each flow bound at the rating, so a `p_min_pu` below -1
     must raise the rating.
   - PLEXOS: `from_to_max` is `Max Flow`. `to_from_max` is `-Min Flow` when `Min Flow < 0`,
     else 0.0. `rating` is the larger of the two.
   - Both minimums are 0.0. A positive PyPSA `p_min_pu` stays in the `extensions.json`
     sidecar.
2. **Readers.** The smallest of `rating`, `rating_from` and `rating_to` that the line
   states bounds the flow each way. When `operational_flow_limit` is present, its
   `from_to_max` and `to_from_max` lower that bound. When it is absent, the line can move
   power both ways up to that bound. The readers do not read the two minimums.
3. **PowerSimulations.** The PowerSimulations writer converts the bounds of item 2 to
   `active_power_limits_from = (min = -reverse bound, max = forward bound)`. It multiplies
   them by `1 - loss proportional term` for `active_power_limits_to`.
4. **One rule for both readers.** `interop/plugins/shared/sienna_hvdc_flow.py` holds the
   rule of item 2. The sienna-to-pypsa reader and the PowerSimulations writer both call it.

## What stays open

The meaning of a nonzero `from_to_min` or `to_from_min` is not clear from the schema. For
example, a line can state `from_to_min > 0` and `to_from_max = 0`. The schema does not say
if a zero flow is then allowed. The writers write both minimums as 0.0, and the readers do
not read them, until SiennaSchemas states the meaning.
