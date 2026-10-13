#!/usr/bin/env bash
# promote.sh   the number of the next draft to mark ready, or nothing, from
#              {pulls: <open pulls list>, reviewed: [<numbers coderabbit.sh called reviewed>], owner: <login>,
#               blocked: [<drafts this run found it cannot promote>] (optional)}
set -euo pipefail

jq -r '
	def names: [.labels[].name];
	(.owner // "") as $owner | .reviewed as $reviewed | (.blocked // []) as $blocked
	| if $owner == "" then empty else
	[.pulls[] | select(.user.login == $owner)] as $mine
	| ([$mine[] | select(.draft | not) | select(names | index("PR Ready"))
	    | select((names | index("hold")) or (names | index("needs owner")) | not)
	    | select(names | index("coderabbit done") | not)
	    | select(.number as $n | $reviewed | index($n) | not)] | length) as $inflight
	| [.pulls[] | select(.head.repo.full_name == .base.repo.full_name)] as $local
	| [$local[] | select(names | index("coderabbit done")) | .head.ref] as $done
	| [$local[] | .head.ref] as $heads
	| if $inflight > 0 then empty else
		[$mine[] | select(.draft)
		 | select(names | index("PR Ready"))
		 | select((names | index("hold")) or (names | index("needs owner")) | not)
		 | select(.number as $n | $blocked | index($n) | not)
		 | select(.base.ref == "main" or (.base.ref as $b | ($done | index($b)) or ($heads | index($b) | not)))]
		| sort_by(.created_at) | first | .number // empty
	end end'
