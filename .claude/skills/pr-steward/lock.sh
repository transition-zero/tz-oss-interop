#!/usr/bin/env bash
# lock.sh state <now_epoch>   held|free, from the tracker's comments on stdin
# lock.sh stale <now_epoch>   the id of each expired marker, one per line
# lock.sh reuse               the id of the newest released marker, if any
set -euo pipefail
expiry=3300

# A marker is taken again by editing it, so its age runs from its last edit.
markers() {
	jq -r --argjson now "$1" '
		.[] | select((.body | split("\n")[0]) == "<!-- pr-steward:working -->")
		| {id, age: ($now - ((.updated_at // .created_at) | fromdateiso8601))}
		| "\(.id)\t\(.age)"'
}

case "${1:-}" in
state)
	markers "${2:?now}" | awk -F'\t' -v e="$expiry" '$2 < e {h=1} END {print (h ? "held" : "free")}'
	;;
stale)
	markers "${2:?now}" | awk -F'\t' -v e="$expiry" '$2 >= e {print $1}'
	;;
reuse)
	jq -r '[.[] | select((.body | split("\n")[0]) == "<!-- pr-steward:released -->")]
		| sort_by(.created_at) | last | .id // empty'
	;;
*)
	echo "usage: $0 state|stale <now_epoch> | reuse" >&2
	exit 2
	;;
esac
