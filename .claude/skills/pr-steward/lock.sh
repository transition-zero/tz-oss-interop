#!/usr/bin/env bash
# lock.sh state <now_epoch>   held|free, from the tracker's comments on stdin
# lock.sh stale <now_epoch>   the id of each expired marker, one per line
# lock.sh reuse               the id of the newest released marker, if any
# lock.sh mine <now_epoch> <id> <run id>   yes|no, from the tracker's comments read after taking the marker
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
mine)
	# Two runs can both read "free" and both write. The oldest live marker wins, and only while
	# it still holds that run's id: two runs that edit one reused comment leave the later write.
	jq -r --argjson now "${2:?now}" --argjson id "${3:?id}" --arg run "${4:?run id}" --argjson e "$expiry" '
		[.[] | select((.body | split("\n")[0]) == "<!-- pr-steward:working -->")
		 | select($now - ((.updated_at // .created_at) | fromdateiso8601) < $e)]
		| sort_by(.id) | first
		| if . != null and .id == $id and (.body | split("\n")[1]) == $run then "yes" else "no" end'
	;;
*)
	echo "usage: $0 state|stale <now_epoch> | reuse | mine <now_epoch> <id> <run id>" >&2
	exit 2
	;;
esac
