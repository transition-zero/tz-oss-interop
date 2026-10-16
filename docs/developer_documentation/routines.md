# The nightly and PR steward routines

Two Conductor routines run agents on this repository. A Conductor routine is a saved
prompt. Conductor runs it in a new cloud workspace of the `tz-oss-interop` project, on
`main`, with the GitHub login of the person who owns it.

| Routine | Skill | When (UTC) | What it does |
| --- | --- | --- | --- |
| Nightly | `.claude/skills/nightly/` | `0 0 * * *` | Labels issues, builds up to two small issues as draft PRs, and reports on the `Nightly triage` issue. It merges nothing. |
| PR steward | `.claude/skills/pr-steward/` | `5 7-19 * * 1-5` | Takes the owner's `PR Ready` PRs through one CodeRabbit review to a merge after a person approves. Merges green Dependabot PRs. Reports on the `PR steward · @<login>` issue. |

All the behaviour is in the skills. A change to a routine is a normal PR, and the next run
after the merge uses it.

## What you can do

- **Send your draft through review:** add `PR Ready` to it.
- **Keep the steward off a PR:** add `hold`.
- **Keep the nightly from building an issue:** add `hold`. The nightly still gives the issue
  its `type:` and `size:` labels.
- **Ask for an overnight build:** add `agent:build` to the issue.
- **Stop the nightly:** add `nightly:paused` to the `Nightly triage` issue.
- **See what a run did:** read its comment on the tracker issue. Each run archives its own
  Conductor workspace, so look for the run in the archived workspaces of the project.

## How the steward moves a PR

The steward gives each open PR one lane, from its labels, its draft flag and CodeRabbit's
review. A run then works on each lane in turn:

| Lane | The PR | The steward |
| --- | --- | --- |
| `queued` | your draft with `PR Ready` | marks it ready when CodeRabbit has a free slot |
| `in-review` | ready, and CodeRabbit has not reviewed it | waits |
| `reviewed` | CodeRabbit reviewed it | answers the findings, then adds `coderabbit done` |
| `needs-owner` | labelled `needs owner` | waits for your answer on the PR |
| `done` | labelled `coderabbit done` | merges it after a person approves the head |
| `dependabot` | Dependabot's, for the Dependabot owner | approves it when CI is green, then merges it |

It never touches another person's PR, a PR with `hold`, or your PR without `PR Ready`. A
run pushes to one of your PRs at most.

## Create a routine

Each routine has two triggers. The `webhook` trigger runs it on an HTTP POST, and the API
can create it. The `cron` trigger runs it on a timetable, and only the Conductor app can
add it.

1. Get a user API key from <https://app.conductor.build/home/api-keys>. A workspace token
   does not work.
2. Create the routine:

   ```bash
   conductor routine create \
     --project-id 7fe0007b-414b-40ec-969a-b5df26a65e86 \
     --name "tz-oss-interop PR steward" \
     --agent claude --model opus-5-5-1m --effort high \
     --prompt-file prompt.md
   ```

   `prompt.md` holds this text, with `/pr-steward` or `/nightly`:

   ```markdown
   Run the `/pr-steward` skill of this repository, unattended. If a JSON body is
   attached to this prompt and it has a `mode` field, give that value to the skill as
   its argument. If not, run the skill with no argument. Do not ask questions.
   ```

3. Store the webhook URL that the command prints. It is the routine's only credential, and
   `conductor routine list` does not show it again.
4. Run the preflight. Read its comment on the tracker issue:

   ```bash
   curl -fsS -X POST -H 'Content-Type: application/json' -d '{"mode": "preflight"}' "$WEBHOOK_URL"
   ```

5. Run the steward once with `{"mode": "dry-run"}`, or the nightly once with `{}`. Read the
   result.
6. In the Conductor app, open the routine and add a schedule trigger with the time from
   the table above.

## One owner for each routine

- **The nightly** has one owner for the repository. The `Nightly triage` issue names that
  person on its `Scheduled by` line. A second person's nightly stops there.
- **The steward** has one routine for each person who wants one. It works only on that
  person's PRs, and keeps its own tracker issue.
- **Dependabot PRs** go to one steward: the login in
  `.claude/skills/pr-steward/dependabot-owner`.
