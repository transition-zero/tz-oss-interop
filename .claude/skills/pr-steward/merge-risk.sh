#!/usr/bin/env bash
# merge-risk.sh   label changes for one PR, from {comments, labels, head}, one per line:
#                 "add merge-risk:<level>" and "remove merge-risk:<old>", or only "stale <sha>"
#                 when the rating covers a commit older than head
set -euo pipefail

# CodeRabbit's walkthrough carries its rating between `final_review_risk` markers, as
# "**Merge Risk:** _<emoji> <Level>_" or "**Merge Risk:** **<emoji> <Level>**", and names
# the commit it covers in a coverage comment. The level's own word names the label, so a
# level not seen before still maps.
jq -r '
	. as $pr
	| [.comments[] | select(.user.login == "coderabbitai[bot]")
	 | select(.body | contains("<!-- final_review_risk_start -->"))]
	| (max_by(.updated_at) // null) as $walkthrough
	| ($walkthrough.body // "" | capture("\\*\\*Merge Risk:\\*\\* (?<mark>_|\\*\\*)(?:[^ _*]+ )?(?<level>[A-Za-z]+)\\k<mark>")?) as $rating
	| ($walkthrough.body // "" | capture("\"coveredCommitId\":\"(?<sha>[0-9a-f]{7,40})\"")?) as $covered
	| [$pr.labels[].name | select(startswith("merge-risk:"))] as $held
	| $pr.head as $head
	| if $rating == null then empty
	  elif $covered != null and ($head | startswith($covered.sha) | not) then "stale \($covered.sha[0:7])"
	  else
		("merge-risk:" + ($rating.level | ascii_downcase)) as $label
		| (if ($held | index($label)) then empty else "add \($label)" end),
		  ($held[] | select(. != $label) | "remove \(.)")
	end'
