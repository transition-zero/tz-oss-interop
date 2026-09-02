# code-review

This directory holds what the review-and-fix cycle learned about reviewing this
repository. Git tracks it, so the whole team gets it, and a new clone starts
with it.

| File | What it holds |
|---|---|
| `always-flag.md` | Rules a reviewer must check for. Each one comes from a comment the reader wrote themselves. |
| `never-flag.md` | Rules a reviewer must not raise a comment against. Each one comes from a comment the reader rejected. |
| `ledger.jsonl` | One line for each comment that has not earned a rule yet. |
| `README.md` | This file. |

## How a rule arrives

1. A reviewer raises a comment. The reader accepts it, rejects it or defers it.
2. The verdict becomes a line in `ledger.jsonl`.
3. When one category collects three records across three pull requests, the
   cycle drafts a rule and asks the reader to approve the wording.
4. The approved rule goes into `always-flag.md` or `never-flag.md`, and the
   records that earned it leave `ledger.jsonl`.

A rule carries the reasons that earned it on its `because:` line, so it explains
itself after those records are gone.

## No reviewer reads this directory

The cycle takes every file under `code-review/` out of the diff it gives a
reviewer, and it drops any comment about a file here.

A rule quotes the code it forbids. A reviewer that read the quote asked for the
quoted code to be deleted.

## You own these files

Edit a rule, delete one, or edit a line of the ledger by hand at any time. The
cycle reads what it finds.
