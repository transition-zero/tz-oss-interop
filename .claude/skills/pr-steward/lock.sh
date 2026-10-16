#!/usr/bin/env bash
# lock.sh state <now_epoch>                held|free, from the tracker's comments on stdin
# lock.sh stale <now_epoch>                the id of each expired marker, one per line
# lock.sh mine <now_epoch> <id> <run id>   yes|no, from the tracker's comments read after posting the marker
set -euo pipefail
expiry=3300

# Each run posts a marker of its own and deletes it when it ends, so no two runs write one comment.
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
mine)
	# Two runs can both read "free" and both post. GitHub gives comment ids in order, so the
	# oldest live marker wins.
	jq -r --argjson now "${2:?now}" --argjson id "${3:?id}" --arg run "${4:?run id}" --argjson e "$expiry" '
		[.[] | select((.body | split("\n")[0]) == "<!-- pr-steward:working -->")
		 | select($now - ((.updated_at // .created_at) | fromdateiso8601) < $e)]
		| sort_by(.id) | first
		| if . != null and .id == $id and (.body | split("\n")[1]) == $run then "yes" else "no" end'
	;;
*)
	echo "usage: $0 state|stale <now_epoch> | mine <now_epoch> <id> <run id>" >&2
	exit 2
	;;
esac
