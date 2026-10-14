#!/usr/bin/env bash
# coderabbit.sh slot <now_epoch> <owner>   free|wait <minutes>, from {prs: [{author, reviews, comments}]};
#                                          only the owner's own PRs count, against the allowance their notes state
# coderabbit.sh reviewed                reviewed|none, from {reviews, comments} for one PR
# coderabbit.sh rerequest <now_epoch> <owner>   ask|none|give-up, from {reviews, comments} for one PR;
#                                               asks are the owner's @coderabbitai review comments
# coderabbit.sh paused <owner>          paused|none, from {comments} for one PR
set -euo pipefail

cr() { jq -r -L "$(dirname "$0")" "$@"; }

case "${1:-}" in
slot)
	# CodeRabbit's allowance is per user ("Your … review attempts … set your current
	# allowance"), so another author's reviews and limit notices spend none of the owner's.
	cr --argjson now "${2:?now}" --arg owner "${3:?owner}" 'include "coderabbit";
		[.prs[] | if has("author") then . else error("slot: a PR entry has no author") end
		 | select(.author == $owner)] | {reviews: [.[].reviews[]], comments: [.[].comments[]]}
		| allowance as $allowance
		| events
		| [.reviews[] | select(. > $now - 3600)] as $recent
		| (if ($recent | length) < $allowance then 0 else ($recent | sort | reverse)[$allowance - 1] + 3600 end) as $reviews_until
		| ([$reviews_until] + [.limits[].until] | max) as $until
		| if $until <= $now then "free" else "wait \((($until - $now) / 60) | ceil | if . < 1 then 1 else . end)" end'
	;;
reviewed)
	cr 'include "coderabbit"; events | if .reviewed then "reviewed" else "none" end'
	;;
rerequest)
	cr --argjson now "${2:?now}" --arg owner "${3:?owner}" 'include "coderabbit";
		events
		| (.limits | max_by(.at)) as $last
		| if .reviewed or $last == null or $last.until > $now then "none"
		  elif any(.asks[]; . > $last.at) then "none"
		  elif (.asks | length) >= 3 then "give-up"
		  else "ask" end'
	;;
paused)
	cr --arg owner "${2:?owner}" 'include "coderabbit"; if paused then "paused" else "none" end'
	;;
*)
	echo "usage: $0 slot <now_epoch> <owner> | reviewed | rerequest <now_epoch> <owner> | paused <owner>" >&2
	exit 2
	;;
esac
