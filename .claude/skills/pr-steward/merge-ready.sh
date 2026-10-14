#!/usr/bin/env bash
# merge-ready.sh   ready | not-ready: <reason>, from {pr: <pulls/n>, lane: <lane.sh's lane>, reviews, checks, open_threads}
set -euo pipefail

# Reviews arrive oldest first, so each person's last APPROVED or CHANGES_REQUESTED is their
# verdict; COMMENTED is dropped first so a later comment cannot hide an approval.
# The ruleset also dismisses stale approvals and requires resolved threads; the head-commit and
# thread gates stay so that a change to the ruleset cannot loosen the steward's merge rule.
# CI runs only on a PR whose base is main, so lint and the test legs must succeed, not merely be
# skipped. The Windows leg's Python version follows requires-python, so it is matched by prefix.
jq -r '
	.pr as $p | [$p.labels[].name] as $l | $p.user.login as $author
	| ([.reviews[] | select(.user.login != $author) | select(.user.login | endswith("[bot]") | not)
	    | select(.state == "APPROVED" or .state == "CHANGES_REQUESTED")]
	   | group_by(.user.login) | map(last)) as $latest
	| if (.lane // "") | IN("done", "dependabot") | not then "not-ready: lane is \(.lane // "unknown")"
	  elif $p.state != "open" or $p.draft then "not-ready: not an open ready PR"
	  elif $p.base.ref != "main" then "not-ready: base is not main"
	  elif .lane == "dependabot" and ($l | index("needs owner review")) then "not-ready: needs owner review"
	  elif any($latest[]; .state == "CHANGES_REQUESTED") then "not-ready: changes requested"
	  elif any($latest[]; .state == "APPROVED") | not then "not-ready: no approval"
	  elif any($latest[]; .state == "APPROVED" and .commit_id == $p.head.sha) | not then "not-ready: no approval on the head"
	  elif (.checks | length) == 0 or any(.checks[]; .status != "completed" or ((.conclusion | IN("success", "skipped", "neutral")) | not)) then "not-ready: checks not green"
	  elif any(.checks[]; .name == "lint") | not then "not-ready: no lint check"
	  elif any(.checks[]; (.name == "lint" or (.name | startswith("test ("))) and .conclusion != "success") then "not-ready: lint or a test leg did not succeed"
	  elif any(.checks[]; .name | startswith("test (windows-latest,")) | not then "not-ready: no Windows test"
	  elif .open_threads == null then "not-ready: thread count unknown"
	  elif .open_threads > 0 then "not-ready: open review threads"
	  elif $p.mergeable_state != "clean" then "not-ready: mergeable_state is \($p.mergeable_state)"
	  else "ready" end'
