#!/usr/bin/env bash
# lane.sh   {"<number>": "<lane>"} for each open PR, from
#           {pulls, reviewed: [<numbers coderabbit.sh called reviewed>], owner, dependabot_owner}
set -euo pipefail

# The first rule that matches names the lane, so the order is the precedence.
jq -c '
	if (.owner // "") == "" then error("lane: no owner") else . end
	| .owner as $owner | .dependabot_owner as $dependabot_owner | (.reviewed // []) as $reviewed
	| [.pulls[] | [.labels[].name] as $labels | .number as $number
	   | (if .user.login != $owner and (.user.login != "dependabot[bot]" or $owner != $dependabot_owner) then "foreign"
	      elif $labels | index("hold") then "held"
	      elif .user.login == "dependabot[bot]" then "dependabot"
	      elif $labels | index("PR Ready") | not then "owner-work"
	      elif $labels | index("needs owner") then "needs-owner"
	      elif .draft then "queued"
	      elif $labels | index("coderabbit done") then "done"
	      elif $reviewed | index($number) then "reviewed"
	      else "in-review" end) as $lane
	   | {key: ($number | tostring), value: $lane}]
	| from_entries'
