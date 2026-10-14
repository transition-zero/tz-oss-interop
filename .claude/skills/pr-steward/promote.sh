#!/usr/bin/env bash
# promote.sh   the number of the next draft to mark ready, or nothing, from
#              {pulls: <open pulls list>, lanes: <lane.sh output>, mergeable: {"<number>": <mergeable_state>}}
set -euo pipefail

# A draft that conflicts with its base, or whose state GitHub has not computed, is passed over.
jq -r '
	(.lanes // {}) as $lanes | (.mergeable // {}) as $mergeable
	| def lane: $lanes[.number | tostring] // "unknown";
	[.pulls[] | select(.head.repo.full_name == .base.repo.full_name)] as $local
	| [$local[] | select(lane == "done") | .head.ref] as $done
	| [$local[] | .head.ref] as $heads
	| if any(.pulls[]; lane == "in-review") then empty else
		[.pulls[] | select(lane == "queued")
		 | select(($mergeable[.number | tostring] // "unknown") | IN("dirty", "unknown") | not)
		 | select(.base.ref == "main" or (.base.ref as $b | ($done | index($b)) or ($heads | index($b) | not)))]
		| sort_by(.created_at) | first | .number // empty
	end'
