# shellcheck shell=bash
cr='coderabbitai[bot]'
head=68d1f83f7fbeed2861fe0555abbed44dbf3169e3
older=40769626f44788b83fa6e7107753fbb417fc9aec
rated() { # level, covered commit
	printf '<!-- walkthrough_start -->\n## Walkthrough\nStuff\n<!-- final_review_risk_start -->\n**Merge Risk:** _%s_ · up to `%s`\n<!-- final_review_risk_coverage:{"sourceCommitId":"%s","coveredCommitId":"%s","kind":"reviewed"} -->\n<!-- final_review_risk_end -->\n' "$1" "${2:0:5}" "$2" "$2"
}
risk() { # comments json, labels json
	jq -n --argjson c "$1" --argjson l "$2" --arg h "$head" '{comments: $c, labels: $l, head: $h}' | bash "$skill/merge-risk.sh"
}
walkthrough() { jq -n --arg cr "$cr" --arg b "$1" --arg at "${2:-2026-10-05T10:00:00Z}" '[{user:{login:$cr},body:$b,updated_at:$at}]'; }

assert_eq "add merge-risk:low" "$(risk "$(walkthrough "$(rated '🔵 Low' "$head")")" '[]')" "merge-risk: a rating adds its label"
assert_eq "add merge-risk:moderate" "$(risk "$(walkthrough "$(rated '🟡 Moderate' "$head")")" '[{"name":"PR Ready"}]')" "merge-risk: the level's word names the label"
assert_eq "" "$(risk "$(walkthrough "$(rated '⚪ Minimal' "$head")")" '[{"name":"merge-risk:minimal"}]')" "merge-risk: a label already set is left alone"
assert_eq $'add merge-risk:high\nremove merge-risk:low' "$(risk "$(walkthrough "$(rated '🟠 High' "$head")")" '[{"name":"merge-risk:low"}]')" "merge-risk: a changed rating replaces the old label"
assert_eq "add merge-risk:critical" "$(risk "$(walkthrough "$(rated '🔴 Critical' "$head")")" '[]')" "merge-risk: a level not seen before still names its label"
assert_eq "stale 4076962" "$(risk "$(walkthrough "$(rated '🔵 Low' "$older")")" '[]')" "merge-risk: a rating of an older commit is reported stale"
assert_eq "stale 4076962" "$(risk "$(walkthrough "$(rated '🔵 Low' "$older")")" '[{"name":"merge-risk:high"}]')" "merge-risk: a rating of an older commit changes no label"
assert_eq "" "$(risk "$(walkthrough $'<!-- walkthrough_start -->\n## Walkthrough\nNo rating')" '[{"name":"merge-risk:low"}]')" "merge-risk: no rating changes nothing"
assert_eq "" "$(risk "$(jq -n --arg b "$(rated '🟠 High' "$head")" '[{user:{login:"jed72"},body:$b,updated_at:"2026-10-05T10:00:00Z"}]')" '[]')" "merge-risk: only CodeRabbit's rating counts"
two=$(jq -n --arg cr "$cr" --arg a "$(rated '🟠 High' "$older")" --arg b "$(rated '🔵 Low' "$head")" '[{user:{login:$cr},body:$b,updated_at:"2026-10-05T11:00:00Z"},{user:{login:$cr},body:$a,updated_at:"2026-10-05T09:00:00Z"}]')
assert_eq "add merge-risk:low" "$(risk "$two" '[]')" "merge-risk: the latest-edited rating wins"
assert_eq "" "$(risk "$(walkthrough "$(rated '🔵 Low' "$head" | sed 's/\*\*Merge Risk:\*\* _🔵 Low_/**Merge Risk:** Low/')")" '[]')" "merge-risk: an unrecognised rating line changes nothing"
assert_eq "add merge-risk:high" "$(risk "$(walkthrough "$(rated '🟠 High' "$head" | sed 's/_🟠 High_/**🟠 High**/')")" '[]')" "merge-risk: a rating in bold names its label"
