# shellcheck shell=bash
owner=alice
pr() { # number draft labels(csv) base head created [author] [head repo]
	jq -n --argjson n "$1" --argjson d "$2" --arg l "$3" --arg b "$4" --arg h "$5" --arg c "$6" --arg a "${7:-alice}" --arg r "${8:-org/repo}" \
		'{number:$n,draft:$d,user:{login:$a},labels:($l|split(",")|map(select(.!=""))|map({name:.})),base:{ref:$b,repo:{full_name:"org/repo"}},head:{ref:$h,repo:{full_name:$r}},created_at:$c}'
}
promote() { # reviewed-json [dirty-json] [unknown-json]; pulls on stdin
	local pulls lanes
	pulls=$(jq -s .)
	lanes=$(jq -n --argjson p "$pulls" --argjson r "$1" --arg o "$owner" '{pulls: $p, reviewed: $r, owner: $o, dependabot_owner: $o}' | bash "$skill/lane.sh")
	jq -n --argjson p "$pulls" --argjson l "$lanes" --argjson d "${2:-[]}" --argjson u "${3:-[]}" \
		'{pulls: $p, lanes: $l, mergeable: ([$p[] | .number as $n
			| {key: ($n | tostring), value: (if $d | index($n) then "dirty" elif $u | index($n) then "unknown" else "clean" end)}] | from_entries)}' |
		bash "$skill/promote.sh"
}
with_owner() {
	local owner=$1
	shift
	"$@"
}

assert_eq 11 "$( { pr 12 true 'PR Ready' main b12 2026-09-30T10:00:00Z; pr 11 true 'PR Ready' main b11 2026-09-29T10:00:00Z; } | promote '[]')" "promote: the oldest ready draft goes first"
assert_eq "" "$( { pr 11 true '' main b11 2026-09-29T10:00:00Z; } | promote '[]')" "promote: no PR Ready, no promotion"
assert_eq "" "$( { pr 11 true 'PR Ready,hold' main b11 2026-09-29T10:00:00Z; } | promote '[]')" "promote: hold keeps it back"
assert_eq "" "$( { pr 11 true 'PR Ready,needs owner' main b11 2026-09-29T10:00:00Z; } | promote '[]')" "promote: needs owner keeps it back"
assert_eq "" "$( { pr 20 true 'PR Ready' b19 b20 2026-09-29T10:00:00Z; pr 19 false '' main b19 2026-09-28T10:00:00Z; } | promote '[19]')" "promote: a child waits for its parent's coderabbit done"
assert_eq 20 "$( { pr 20 true 'PR Ready' b19 b20 2026-09-29T10:00:00Z; pr 19 false 'PR Ready,coderabbit done' main b19 2026-09-28T10:00:00Z; } | promote '[19]')" "promote: a child goes once its parent is done"
assert_eq "" "$( { pr 30 false 'PR Ready' main b30 2026-09-28T10:00:00Z; pr 31 true 'PR Ready' main b31 2026-09-29T10:00:00Z; } | promote '[]')" "promote: nothing while a review is in flight"
assert_eq 31 "$( { pr 30 false '' main b30 2026-09-28T10:00:00Z; pr 31 true 'PR Ready' main b31 2026-09-29T10:00:00Z; } | promote '[30]')" "promote: a reviewed PR awaiting its fixes is not in flight"
assert_eq 31 "$( { pr 30 false '' main b30 2026-09-28T10:00:00Z; pr 31 true 'PR Ready' main b31 2026-09-29T10:00:00Z; } | promote '[]')" "promote: an unreviewed PR without PR Ready is not in flight"
assert_eq 31 "$( { pr 30 false 'PR Ready,hold' main b30 2026-09-28T10:00:00Z; pr 31 true 'PR Ready' main b31 2026-09-29T10:00:00Z; } | promote '[]')" "promote: an unreviewed held PR is not in flight"
assert_eq 31 "$( { pr 30 false 'PR Ready,needs owner' main b30 2026-09-28T10:00:00Z; pr 31 true 'PR Ready' main b31 2026-09-29T10:00:00Z; } | promote '[]')" "promote: an unreviewed PR waiting on the owner is not in flight"
assert_eq "" "$( { pr 40 true 'PR Ready' main b40 2026-09-28T10:00:00Z bob; } | promote '[]')" "promote: another person's ready draft is never promoted"
assert_eq 41 "$( { pr 40 false 'PR Ready' main b40 2026-09-28T10:00:00Z bob; pr 41 true 'PR Ready' main b41 2026-09-29T10:00:00Z; } | promote '[]')" "promote: another person's review in flight does not block"
assert_eq 40 "$( { pr 40 true 'PR Ready' main b40 2026-09-28T10:00:00Z bob; pr 41 true 'PR Ready' main b41 2026-09-29T10:00:00Z; } | with_owner bob promote '[]')" "promote: each owner promotes their own drafts"
assert_eq 12 "$( { pr 11 true 'PR Ready' main b11 2026-09-29T10:00:00Z; pr 12 true 'PR Ready' main b12 2026-09-30T10:00:00Z; } | promote '[]' '[11]')" "promote: a draft the run found blocked is passed over for the next"
assert_eq 31 "$( { pr 21 true 'PR Ready' b20 b21 2026-09-29T10:00:00Z; pr 20 false 'PR Ready,coderabbit done' main b20 2026-09-28T10:00:00Z; pr 31 true 'PR Ready' main b31 2026-09-30T10:00:00Z; } | promote '[20]' '[21]')" "promote: a blocked rung lets another stack's draft go"
assert_eq "" "$( { pr 11 true 'PR Ready' main b11 2026-09-29T10:00:00Z; } | promote '[]' '[11]')" "promote: nothing when every candidate is blocked"
assert_eq "" "$( { pr 21 true 'PR Ready' b11 b21 2026-09-30T10:00:00Z; pr 11 true 'PR Ready' main b11 2026-09-29T10:00:00Z; } | promote '[]' '[11]')" "promote: a blocked draft's child still waits for it"
assert_eq 50 "$( { pr 50 true 'PR Ready' combined b50 2026-09-29T10:00:00Z; } | promote '[]')" "promote: a stack on a branch with no open PR goes to review"
assert_eq "" "$( { pr 51 true 'PR Ready' b50 b51 2026-09-30T10:00:00Z; pr 50 false 'PR Ready' combined b50 2026-09-29T10:00:00Z; } | promote '[]')" "promote: a rung above it still waits for its parent's coderabbit done"
assert_eq 50 "$( { pr 50 true 'PR Ready' combined b50 2026-09-29T10:00:00Z; pr 60 true '' main combined 2026-09-28T10:00:00Z bob fork/repo; } | promote '[]')" "promote: a fork's branch of the same name does not count as the base's PR"
assert_eq "" "$( { pr 51 true 'PR Ready' b50 b51 2026-09-30T10:00:00Z; pr 60 false 'coderabbit done' main b50 2026-09-28T10:00:00Z bob fork/repo; pr 50 false '' combined b50 2026-09-29T10:00:00Z; } | promote '[]')" "promote: a fork's done PR of the same name does not release a child"
assert_eq 12 "$( { pr 11 true 'PR Ready' main b11 2026-09-29T10:00:00Z; pr 12 true 'PR Ready' main b12 2026-09-30T10:00:00Z; } | promote '[]' '[]' '[11]')" "promote: a draft whose state GitHub has not computed is passed over"
