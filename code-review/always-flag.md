# Always flag

A reviewer must check for every rule below, and must raise a comment when the
change breaks one.

Each rule comes from a comment the reader wrote themselves on an earlier pull
request. `/review-fix-cycle` adds a rule here only after the reader approves the
wording. Edit a rule, or delete one, by hand at any time.

## ALWAYS-001 — unexplained-quantitative-claim
since: 2026-08-28
category: unexplained-quantitative-claim
scope: repo
from: transition-zero/tz-oss-interop#297#t297-01, transition-zero/tz-oss-interop#297#t297-02

Documentation must not state how long a run took. Delete a wall-clock duration, a seconds count or a minutes count for a translate, a solve or a results export. A reader cannot reproduce a time measured on a machine they do not know, so the number tells them nothing. A relative claim with no number is allowed, for example "`copperplate` is faster". A size on disk is allowed.
