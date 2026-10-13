#!/usr/bin/env bash
# coderabbit.sh slot <now_epoch> <owner>   free|wait <minutes>, from {prs: [{author, reviews, comments}]};
#                                          only the owner's own PRs count, against the allowance their notes state
# coderabbit.sh reviewed                reviewed|none, from {reviews, comments} for one PR
# coderabbit.sh rerequest <now_epoch> <owner>   ask|none|give-up, from {reviews, comments} for one PR;
#                                               asks are the owner's @coderabbitai review comments
set -euo pipefail

# A review with nothing to fix posts no review object, only its "## Walkthrough" summary
# or a "Review finished" notice. An empty-bodied review is a reply in a thread. The summary
# is edited on pauses and replies, so only its created_at is a review time, and a limit note
# left inside a summary is stale; a standalone limit notice is dated by its updated_at,
# because CodeRabbit rewrites one notice in place.
events='
	def cr: .user.login == "coderabbitai[bot]";
	def t(f): f | fromdateiso8601;
	def summary: .body | contains("## Walkthrough");
	[.reviews[] | select(cr) | select((.body // "") != "") | t(.submitted_at)] as $reviews
	| [.comments[] | select(cr) | select(.body | test("Review finished")) | t(.created_at // .updated_at)] as $finished
	| [.comments[] | select(cr) | select(summary)] as $summaries
	| [$summaries[] | select(.created_at) | t(.created_at)] as $summaries_at
	| [.comments[] | select(cr) | select(summary | not) | (.body | capture("available in (?<m>[0-9]+) minute")?) as $c
	   | select($c != null) | {at: t(.updated_at), until: (t(.updated_at) + (($c.m | tonumber) * 60))}] as $limits
	| [.comments[] | select(.user.login == $ARGS.named.owner) | select(.body | contains("@coderabbitai review")) | t(.created_at)] as $asks
	| {reviews: ($reviews + $finished + $summaries_at), reviewed: (($reviews + $finished | length) + ($summaries | length) > 0),
	   limits: $limits, asks: $asks}'

# The allowance is per hour and changes with use; the newest note that states it wins, and
# with no note the allowance is one review an hour.
allowance='
	def stated: (.body // "") | first(capture("allowance at (?<n>[0-9]+) reviews? per hour"),
		capture("up to (?<n>[0-9]+) included reviews? per hour")) | .n | tonumber;
	[(.reviews[] | select(.user.login == "coderabbitai[bot]") | {at: (.submitted_at | fromdateiso8601), n: stated}),
	 (.comments[] | select(.user.login == "coderabbitai[bot]") | {at: ((.created_at // .updated_at) | fromdateiso8601), n: stated})]
	| max_by(.at) | .n // 1'

case "${1:-}" in
slot)
	# CodeRabbit's allowance is per user ("Your … review attempts … set your current
	# allowance"), so another author's reviews and limit notices spend none of the owner's.
	jq -r --argjson now "${2:?now}" --arg owner "${3:?owner}" \
		'[.prs[] | if has("author") then . else error("slot: a PR entry has no author") end
		   | select(.author == $owner)] | {reviews: [.[].reviews[]], comments: [.[].comments[]]}
		| ('"$allowance"') as $allowance
		| '"$events"'
		| [.reviews[] | select(. > $now - 3600)] as $recent
		| (if ($recent | length) < $allowance then 0 else ($recent | sort | reverse)[$allowance - 1] + 3600 end) as $reviews_until
		| ([$reviews_until] + [.limits[].until] | max) as $until
		| if $until <= $now then "free" else "wait \((($until - $now) / 60) | ceil | if . < 1 then 1 else . end)" end'
	;;
reviewed)
	jq -r "$events"' | if .reviewed then "reviewed" else "none" end'
	;;
rerequest)
	jq -r --argjson now "${2:?now}" --arg owner "${3:?owner}" "$events"'
		| (.limits | max_by(.at)) as $last
		| if .reviewed or $last == null or $last.until > $now then "none"
		  elif any(.asks[]; . > $last.at) then "none"
		  elif (.asks | length) >= 3 then "give-up"
		  else "ask" end'
	;;
*)
	echo "usage: $0 slot <now_epoch> <owner> | reviewed | rerequest <now_epoch> <owner>" >&2
	exit 2
	;;
esac
