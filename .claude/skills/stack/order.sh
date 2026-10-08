#!/usr/bin/env bash
# order.sh   the rungs above {start} in {pulls, start}, depth-first, oldest child first:
#            <number>\t<branch>\t<parent branch>\t<head sha>
# Exit 2: the input is not {pulls: [...], start: <number>}. Exit 3: start is not open.
set -euo pipefail

input=$(cat)
jq -e '(.pulls | type == "array") and (.start | type == "number")' <<<"$input" >/dev/null 2>&1 || {
	echo "order.sh: expected {pulls: [...], start: <number>}; did the pulls fetch fail?" >&2
	exit 2
}
jq -e '.start as $s | any(.pulls[]; .number == $s)' <<<"$input" >/dev/null || {
	echo "order.sh: #$(jq '.start' <<<"$input") is not open: after a merge, cascade from the retargeted child" >&2
	exit 3
}

jq -r '
	.start as $start | .pulls as $p
	| def above($ref): [$p[] | select(.base.ref == $ref)] | sort_by(.created_at)
		| .[] | ., above(.head.ref);
	([$p[] | select(.number == $start)] | first) as $s
	| above($s.head.ref)
	| "\(.number)\t\(.head.ref)\t\(.base.ref)\t\(.head.sha)"' <<<"$input"
