# Epic body template

`/epic design` writes the epic issue's body in this shape. Replace each `<…>`; keep the
headings. The issue carries the labels `epic` and `type:design`.

````markdown
Owner: @<login>

This epic holds the design. It is the source of the design until the first sub-issue's PR
commits it to `docs/specs/<YYYY-MM-DD>-<topic>-design.md`; after that the spec is, and
this body links to it.

## Goal and scope

<What the feature does for its user, and what it deliberately leaves out.>

## Why this is not trivial

<What the feature touches that is not obvious from its title, with `file:line` evidence.>

## Decisions

### 1. <The question> — **Open**

- **Option A: <name>.** <Consequences, with `file:line` evidence.>
- **Option B: <name>.** <Consequences, with `file:line` evidence.>

**Recommendation:** <A or B, and why, in one or two sentences.>

<!-- When the owner settles it, the heading becomes "— **Decided**" and this line is added: -->
<!-- **Decided:** <the answer>, by @<owner> (<link to their comment>). -->

### 2. <The next question> — **Open**

<…>

## Changes by package

- `<package or path>`: <what changes>

## Test plan

| Acceptance criterion | Test (public boundary) |
| --- | --- |
| <criterion> | <test that pins it> |

## Sub-issues (draft)

### 1. <Title>

- **Goal:** <one or two sentences>
- **Scope:** <what is in, what is not>
- **Acceptance criteria:**
  - <criterion>
- **Depends on:** none
- **Size:** <S|M|L>

### 2. <Title>

- **Goal:** <…>
- **Scope:** <…>
- **Acceptance criteria:**
  - <…>
- **Depends on:** 1
- **Size:** <…>
````

Rules for the body:

- **Every decision is Open until the owner answers it.** The recommendation is Claude's,
  but the answer is the owner's. That is the Decisions rule in the root `CLAUDE.md`.
- **There is no sub-issue for the spec alone.** Sub-issue 1 commits the spec beside its
  own work.
- **Sub-issues are in build order,** and each is one reviewable PR, or 2–3 stacked PRs
  if it grows past about 600–800 lines of non-test code.
