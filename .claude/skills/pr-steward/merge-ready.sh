#!/usr/bin/env bash
# merge-ready.sh   ready | not-ready: <reason>, from {pr: <pulls/n>, reviews, checks, open_threads, owner, dependabot_owner}
set -euo pipefail

# Reviews arrive oldest first, so each person's last APPROVED or CHANGES_REQUESTED is their
# verdict; COMMENTED is dropped first so a later comment cannot hide an approval.
# An approval counts only when it was given on the head commit, so a restack or a fix after it
# needs a fresh one.
# CI runs only on a PR whose base is main, so lint and the test legs must succeed, not merely be
# skipped. The Windows leg's Python version follows requires-python, so it is matched by prefix.
jq -r '
	.pr as $p | [$p.labels[].name] as $l | $p.user.login as $author | (.owner // "") as $owner
	| ([.reviews[] | select(.user.login != $author) | select(.user.login | endswith("[bot]") | not)
	    | select(.state == "APPROVED" or .state == "CHANGES_REQUESTED")]
	   | group_by(.user.login) | map(last)) as $latest
	| if $owner == "" then "not-ready: owner unknown"
	  elif $p.state != "open" or $p.draft then "not-ready: not an open ready PR"
	  elif $p.base.ref != "main" then "not-ready: base is not main"
	  elif ($author != $owner and ($author != "dependabot[bot]" or $owner != .dependabot_owner)) then "not-ready: author not allowed"
	  elif ($l | index("hold")) or ($l | index("needs owner")) then "not-ready: held for the owner"
	  elif $author == "dependabot[bot]" and ($l | index("needs owner review")) then "not-ready: needs owner review"
	  elif $author == $owner and (($l | index("coderabbit done")) | not) then "not-ready: no coderabbit done"
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
