# shellcheck shell=bash
now=$(date -u -d 2026-09-30T12:00:00Z +%s 2>/dev/null || date -u -j -f %Y-%m-%dT%H:%M:%SZ 2026-09-30T12:00:00Z +%s)
cr='coderabbitai[bot]'
walk=$'<!-- walkthrough_start -->\n## Walkthrough\nStuff'
limit=$'<!-- walkthrough_start -->\n> ## Review limit reached\n**Next included review available in 42 minutes.**'
j() { jq -n --arg cr "$cr" --arg w "$walk" --arg l "$limit" "$1"; }

assert_eq free "$(j '{prs:[{reviews:[],comments:[],author:"alice"}]}' | bash "$skill/coderabbit.sh" slot "$now" alice)" "slot: nothing recent is free"
assert_eq "wait 20" "$(j '{prs:[{reviews:[{user:{login:$cr},body:"**Actionable comments posted: 1**",submitted_at:"2026-09-30T11:20:00Z"}],comments:[],author:"alice"}]}' | bash "$skill/coderabbit.sh" slot "$now" alice)" "slot: a review 40 minutes ago waits 20"
assert_eq free "$(j '{prs:[{reviews:[{user:{login:$cr},body:"",submitted_at:"2026-09-30T11:50:00Z"}],comments:[],author:"alice"}]}' | bash "$skill/coderabbit.sh" slot "$now" alice)" "slot: a reply in a thread is not a review"
assert_eq free "$(j '{prs:[{reviews:[],comments:[{user:{login:$cr},body:$w,created_at:"2026-09-30T09:00:00Z",updated_at:"2026-09-30T11:50:00Z"}],author:"alice"}]}' | bash "$skill/coderabbit.sh" slot "$now" alice)" "slot: an edit to the walkthrough is not a review"
assert_eq reviewed "$(j '{reviews:[],comments:[{user:{login:$cr},body:($w + "\n> ## Review limit reached\navailable in 5 minutes"),updated_at:"2026-09-30T11:00:00Z"}]}' | bash "$skill/coderabbit.sh" reviewed)" "reviewed: a summary with a limit note still counts"
assert_eq none "$(j '{reviews:[{user:{login:$cr},body:"",submitted_at:"2026-09-30T11:00:00Z"}],comments:[]}' | bash "$skill/coderabbit.sh" reviewed)" "reviewed: a reply in a thread does not count"
assert_eq "wait 30" "$(j '{prs:[{reviews:[],comments:[{user:{login:$cr},body:$l,updated_at:"2026-09-30T11:48:00Z"}],author:"alice"}]}' | bash "$skill/coderabbit.sh" slot "$now" alice)" "slot: a limit notice waits until its named time"
assert_eq free "$(j '{prs:[{reviews:[{user:{login:"jed72"},submitted_at:"2026-09-30T11:59:00Z"}],comments:[],author:"alice"}]}' | bash "$skill/coderabbit.sh" slot "$now" alice)" "slot: a person's review uses no slot"
assert_eq reviewed "$(j '{reviews:[],comments:[{user:{login:$cr},body:$w,updated_at:"2026-09-30T11:00:00Z"}]}' | bash "$skill/coderabbit.sh" reviewed)" "reviewed: a walkthrough alone counts"
assert_eq none "$(j '{reviews:[],comments:[{user:{login:$cr},body:$l,updated_at:"2026-09-30T11:00:00Z"}]}' | bash "$skill/coderabbit.sh" reviewed)" "reviewed: a limit notice does not count"
assert_eq reviewed "$(j '{reviews:[],comments:[{user:{login:$cr},body:"<details><summary>✅ Action performed</summary>Review finished.",updated_at:"2026-09-30T11:00:00Z"}]}' | bash "$skill/coderabbit.sh" reviewed)" "reviewed: Review finished counts"
assert_eq none "$(j '{reviews:[],comments:[{user:{login:"notcoderabbitai[bot]x"},body:$w,updated_at:"2026-09-30T11:00:00Z"}]}' | bash "$skill/coderabbit.sh" reviewed)" "reviewed: the login must match whole"
assert_eq "wait 30" "$(j '{prs:[{reviews:[],comments:[{user:{login:$cr},body:$w,created_at:"2026-09-30T11:30:00Z",updated_at:"2026-09-30T11:55:00Z"}],author:"alice"}]}' | bash "$skill/coderabbit.sh" slot "$now" alice)" "slot: a new walkthrough is a review"
assert_eq free "$(j '{prs:[{reviews:[],comments:[{user:{login:$cr},body:($w + "\n**Next included review available in 46 minutes.**"),created_at:"2026-09-30T09:00:00Z",updated_at:"2026-09-30T11:50:00Z"}],author:"alice"}]}' | bash "$skill/coderabbit.sh" slot "$now" alice)" "slot: a stale limit note left in a summary is ignored"

mine='{author:"alice",reviews:[{user:{login:$cr},body:"**Actionable comments posted: 1**",submitted_at:"2026-09-30T11:20:00Z"}],comments:[]}'
theirs='{author:"bob",reviews:[{user:{login:$cr},body:"**Actionable comments posted: 1**",submitted_at:"2026-09-30T11:55:00Z"}],comments:[]}'
theirs_limit='{author:"bob",reviews:[],comments:[{user:{login:$cr},body:$l,updated_at:"2026-09-30T11:58:00Z"}]}'
assert_eq free "$(j "{prs:[$theirs]}" | bash "$skill/coderabbit.sh" slot "$now" alice)" "slot: another author's review uses none of the owner's allowance"
assert_eq free "$(j "{prs:[$theirs_limit]}" | bash "$skill/coderabbit.sh" slot "$now" alice)" "slot: another author's limit notice does not hold the owner back"
assert_eq "wait 20" "$(j "{prs:[$mine,$theirs]}" | bash "$skill/coderabbit.sh" slot "$now" alice)" "slot: only the owner's own review sets the wait"
assert_eq "wait 55" "$(j "{prs:[$theirs]}" | bash "$skill/coderabbit.sh" slot "$now" bob)" "slot: each owner has an allowance of their own"

j '{prs:[{reviews:[],comments:[]}]}' | bash "$skill/coderabbit.sh" slot "$now" alice >/dev/null 2>&1 && rc=0 || rc=$?
assert_eq 1 "$([ "$rc" -ne 0 ] && echo 1 || echo 0)" "slot: an entry without an author is an error, not a free slot"

ask() { j "$1" | bash "$skill/coderabbit.sh" rerequest "$now" alice; }
notice() { printf '{user:{login:$cr},body:"Review rate limited. available in %s minutes",created_at:"%s",updated_at:"%s"}' "$1" "$2" "$2"; }
asked_by() { printf '{user:{login:"%s"},body:"@coderabbitai review",created_at:"%s",updated_at:"%s"}' "$1" "$2" "$2"; }
me() { asked_by alice "$1"; }
assert_eq ask "$(ask "{reviews:[],comments:[$(notice 30 2026-09-30T11:00:00Z)]}")" "rerequest: an expired limit with no ask since"
assert_eq none "$(ask "{reviews:[],comments:[$(notice 90 2026-09-30T11:00:00Z)]}")" "rerequest: a limit still running"
assert_eq none "$(ask "{reviews:[],comments:[$(notice 30 2026-09-30T11:00:00Z),$(me 2026-09-30T11:40:00Z)]}")" "rerequest: already asked since the notice"
assert_eq none "$(ask "{reviews:[],comments:[{user:{login:\$cr},body:\$w,created_at:\"2026-09-30T11:00:00Z\",updated_at:\"2026-09-30T11:00:00Z\"},$(notice 30 2026-09-30T10:00:00Z)]}")" "rerequest: never once it is reviewed"
assert_eq none "$(ask '{reviews:[],comments:[]}')" "rerequest: no limit notice, nothing to do"
assert_eq give-up "$(ask "{reviews:[],comments:[$(me 2026-09-30T08:00:00Z),$(me 2026-09-30T09:00:00Z),$(me 2026-09-30T10:00:00Z),$(notice 30 2026-09-30T10:01:00Z)]}")" "rerequest: gives up after three asks"
assert_eq ask "$(ask "{reviews:[],comments:[$(notice 30 2026-09-30T11:00:00Z),$(asked_by bob 2026-09-30T11:40:00Z)]}")" "rerequest: another login's ask does not count"
assert_eq ask "$(ask "{reviews:[],comments:[$(asked_by bob 2026-09-30T08:00:00Z),$(asked_by bob 2026-09-30T09:00:00Z),$(asked_by bob 2026-09-30T10:00:00Z),$(notice 30 2026-09-30T10:01:00Z)]}")" "rerequest: another login's asks do not count toward giving up"

allowance_note() { printf '{user:{login:$cr},body:"Your included PR review attempts over the past 7 days set your current allowance at %s reviews per hour.",submitted_at:"%s"}' "$1" "$2"; }
review_at() { printf '{user:{login:$cr},body:"**Actionable comments posted: 1**",submitted_at:"%s"}' "$1"; }
slot_for() { j "{prs:[{author:\"alice\",reviews:[$1],comments:[${2:-}]}]}" | bash "$skill/coderabbit.sh" slot "$now" alice; }
assert_eq free "$(slot_for "$(allowance_note 4 2026-09-30T11:20:00Z)")" "slot: an allowance of 4 leaves a slot after one review"
assert_eq "wait 20" "$(slot_for "$(allowance_note 2 2026-09-30T11:20:00Z),$(review_at 2026-09-30T11:50:00Z)")" "slot: an allowance of 2 waits for the older of two reviews"
assert_eq "wait 20" "$(slot_for "$(allowance_note 4 2026-09-30T08:00:00Z),$(allowance_note 1 2026-09-30T11:20:00Z)")" "slot: the newest note sets the allowance"
assert_eq free "$(slot_for "$(review_at 2026-09-30T11:20:00Z)" '{user:{login:$cr},body:($w + "\nYour plan provides up to 10 included reviews per hour; 9 remain after this review."),created_at:"2026-09-30T11:21:00Z",updated_at:"2026-09-30T11:21:00Z"}')" "slot: a summary's included-reviews note states the allowance"
assert_eq "wait 30" "$(slot_for "$(allowance_note 4 2026-09-30T11:20:00Z)" '{user:{login:$cr},body:$l,updated_at:"2026-09-30T11:48:00Z"}')" "slot: a limit notice holds even under the allowance"
assert_eq "wait 20" "$(j "{prs:[{author:\"bob\",reviews:[$(allowance_note 4 2026-09-30T11:55:00Z)],comments:[]},{author:\"alice\",reviews:[$(review_at 2026-09-30T11:20:00Z)],comments:[]}]}" | bash "$skill/coderabbit.sh" slot "$now" alice)" "slot: another author's note does not set the owner's allowance"

pause_ask() { printf '{user:{login:"%s"},body:"@coderabbitai pause",created_at:"%s"}' "$1" "$2"; }
pause_reply() { printf '{user:{login:$cr},body:"<summary>✅ Action performed</summary>\\n\\nReviews paused.",created_at:"%s"}' "$1"; }
paused_for() { j "{comments:[$1]}" | bash "$skill/coderabbit.sh" paused "${2:-alice}"; }
assert_eq paused "$(paused_for "$(pause_ask alice 2026-09-30T11:00:00Z),$(pause_reply 2026-09-30T11:01:00Z)")" "paused: a reply after the owner's request"
assert_eq none "$(paused_for "$(pause_ask alice 2026-09-30T11:00:00Z)")" "paused: a request with no reply yet"
assert_eq none "$(paused_for "$(pause_ask bob 2026-09-30T11:00:00Z),$(pause_reply 2026-09-30T11:01:00Z)")" "paused: another login's request does not count"
assert_eq none "$(paused_for "$(pause_reply 2026-09-30T10:00:00Z),$(pause_ask alice 2026-09-30T11:00:00Z)")" "paused: a reply before the newest request does not count"
assert_eq none "$(paused_for "$(pause_ask alice 2026-09-30T11:00:00Z),{user:{login:\"mallory\"},body:\"Reviews paused\",created_at:\"2026-09-30T11:01:00Z\"}")" "paused: only CodeRabbit's reply counts"
resume_by() { printf '{user:{login:"%s"},body:"@coderabbitai resume",created_at:"%s"}' "$1" "$2"; }
assert_eq none "$(paused_for "$(pause_ask alice 2026-09-30T11:00:00Z),$(pause_reply 2026-09-30T11:01:00Z),$(resume_by carol 2026-09-30T11:30:00Z)")" "paused: a resume after the pause ends it"
assert_eq paused "$(paused_for "$(resume_by carol 2026-09-30T10:00:00Z),$(pause_ask alice 2026-09-30T11:00:00Z),$(pause_reply 2026-09-30T11:01:00Z)")" "paused: a resume before the newest request does not end it"

summary_at() { printf '{user:{login:$cr},body:$w,created_at:"%s",updated_at:"%s"}' "$1" "$1"; }
assert_eq free "$(slot_for "$(allowance_note 2 2026-09-30T11:20:00Z)" "$(summary_at 2026-09-30T11:21:00Z)")" "slot: a review and its summary count as one review"
assert_eq "wait 20" "$(slot_for "$(allowance_note 2 2026-09-30T11:20:00Z)" "$(summary_at 2026-09-30T11:50:00Z)")" "slot: a summary far from any review is a review of its own"
