---
name: kb-access-tracks-the-routine-not-the-day
type: semantic
description: sibling-repo access is not per-session noise — it tracks which routine is running (0 of 7 research-tier probes, 8 of 8 execution-tier, p=0.00016), so the sessions that can see the workspace are exactly the ones that write no entries
confidence: verified
source: all 15 recorded sibling-access probes in AUTONOMY.md and DEBRIEF.md, 2026-08-07 through 2026-08-23; entry-creation commits replayed with git log --diff-filter=A over memory/
created: 2026-08-23
last_verified: 2026-08-23
links: [sibling-repo-access-denied-in-routines, kb-reverification-has-one-rate, kb-verification-rides-along-with-authoring, kb-a-registry-asks-only-what-it-has-words-for, kb-corrections-happen-in-place, kb-the-bundle-was-already-shipped, kb-a-hung-deploy-reports-as-cancelled, kb-ranked-retrieval, kb-tests-cannot-cover-an-absent-guard, workspace-repo-inventory-drift, kb-review-load-is-one-cohort]
---

Every routine session runs the standing mandate's step 1 — probe sibling-repo
access — and records the result. Fifteen probes are on the record, 2026-08-07
through 2026-08-23. Read one at a time they look like noise, and the store says
so: [[sibling-repo-access-denied-in-routines]] has attributed the variation to
"per-session tooling availability" since 2026-08-08, i.e. to chance.

**It is not chance. It tracks which routine is running.**

| | granted | denied |
|---|---|---|
| research tier | 0 | **7** |
| execution tier | **8** | 0 |

Perfect separation, Fisher exact two-sided **p = 0.00016**. And the split is not
confounded by the calendar: on **three** days — 2026-08-07, 2026-08-08 and
2026-08-19 — both outcomes were recorded, same account, same day, different
container, and each time the research-tier session was the one refused.

## Why that matters more than it looks

Two facts that were each recorded separately, and that nobody had put together:

- **The sessions that can reach the workspace write no entries.** Replaying
  `git log --diff-filter=A` over `memory/`: every entry created since
  2026-08-07 is a research-tier phase write-up, with one exception
  ([[kb-a-hung-deploy-reports-as-cancelled]], and its subject is this repo's own
  Pages workflow, not the repo that session had rotated into). The last **five**
  rotations — `digital-twin`, `action-rsi`, `just-in-time`,
  `garmin-vivoactive`, `centauri-control` — read a repo each, found real bugs in
  three of them, and left **zero** entries about any of them.
- **The knowledge went somewhere, just not somewhere retrievable.** Those five
  sessions wrote 1,400–3,000 characters each into `AUTONOMY.md`'s backlog.
  Replaying every commit, the three governing documents crossed `memory/` in
  total size on **2026-08-01** and are now **1.67×** it (356,604 bytes against
  213,752). `AUTONOMY.md` alone is **21,290 tokens** — 10.6× the entire
  `DEFAULT_CONTEXT_BUDGET` of 2,000 that a whole context pack has to fit in, and
  more than one `Read` call returns. None of it is ranked, decayed, deduplicated
  or reachable by `kb.py context`.

So the store has **no entry about any repo a routine actually works in** that
postdates the first rotation. Ask it a task-shaped question about one and it
answers from the only subject it has: itself. `context "what should I know
before working in the action-rsi repository"` leads with
[[kb-ranked-retrieval]]; `"does digital-twin have tests"` leads with
[[kb-tests-cannot-cover-an-absent-guard]]. Both packs are budget-bound at three
entries, none relevant.

The mechanism is the two tiers pulling apart: **the tier with the access does
not write, and the tier that writes does not have the access.**

## The cost already booked: a floor recorded three entries too high

[[kb-reverification-has-one-rate]] recorded a "floor no routine can lift" — six
entries stamped on opening day, never re-verified, all arriving together on
2026-10-25, and `ROADMAP.md` filed it as **Jerry's, not a routine's**, with the
note "not a reason to sweep harder". Six is right; *whose* is not. Read their
`source` fields:

| entry | evidence lives in | who can check it |
|---|---|---|
| `asdlc-governed-change-rules` | the `asdlc` repo | execution tier |
| `twin-sovereignty-constraint` | `digital-twin/docs/SOVEREIGNTY.md` | execution tier |
| `workspace-improvement-phases` | the workspace, now `jvanheerikhuize/repos` | execution tier |
| `routines-ui-not-api-for-prompts` | the claude.ai Routines UI | Jerry |
| `purge-context-after-each-change` | `~/.claude/settings.json` | Jerry |
| `workspace-audit-2026-07-27` | a filesystem on Jerry's machine | Jerry |

**Three, not six.** And the three are not merely reachable in principle — a
session was *inside* `digital-twin` on 2026-08-18 writing tests for it, and
inside the workspace repo on 2026-08-07, 08-08 and 08-09. Each had the entry's
own source open and re-verified nothing, because the row said the floor was
Jerry's.

That is the same shape as [[kb-verification-rides-along-with-authoring]]: a
conclusion held by nobody's attention stays wrong for as long as nothing
re-reads it. Here what went stale was not a claim about code but **a claim about
who can check claims** — derived on 2026-08-15 from the access model of
2026-08-08, frozen as prose, and never recomputed while its inputs moved.

## Deriving the split from `source` was measured and does not work

If grounding is what decides who can re-verify, the obvious move is to read it
off the `source` field every entry already carries — no new frontmatter, the
[[kb-the-bundle-was-already-shipped]] shape. Labels for all 49 entries were
written by hand *first* and frozen, then a classifier over `source`:

| | |
|---|---|
| accuracy | 44 of 49, **0.898** |
| always-answer-`here` baseline | 40 of 49, **0.816** |
| on the 9 entries that are not `here` | **5 of 9** |

The headline number is the base rate talking. On the only class the split exists
to name it is a coin flip, and on the six-entry cohort it would mislabel three.

The failures are not regex bugs and no rewrite fixes them:

- **`source` names the act, not the artifact.** `asdlc-governed-change-rules`
  says "re-checked against the repo" — which repo is not in the field.
  `workspace-improvement-phases` says "direct inspection", object omitted.
  Both are the entries that matter most.
- **Grounding is a set, not a value.** `twin-sovereignty-constraint` reads
  "Jerry, 2026-07-12; corroborated by `digital-twin/docs/SOVEREIGNTY.md`" — two
  grounds, either sufficient, and a one-slot answer has to discard one. That is
  [[kb-a-registry-asks-only-what-it-has-words-for]] exactly: a schema that
  cannot phrase the question certifies half a decision. Worse, the discarded
  half is load-bearing here — collapsing a two-ground entry to its harder ground
  understates what a routine can do, which is the direction of the error being
  repaired.

So nothing was shipped to infer it. Nine entries out of forty-nine is a set a
person reads in one sitting, and a wrong label costs a session a wasted probe
against a wall.

## What to do instead, and it is free

The repair is not a field and not a detector. It is that **the tier holding the
access is the tier that should spend it**: a rotation session is already inside
the repo an entry is grounded in, with that repo cloned, for other reasons. The
charter now asks it to re-verify those entries while it is there, which clears
three of the six at no cost and leaves a Jerry-only floor of **three**.

The one thing this changes about the older conclusion: sibling-grounded entries
looked unmaintainable in July because nothing here could reach them, and
[[kb-corrections-happen-in-place]] says an obsolete claim is repaired by the
change that causes it. Across repos there is no such commit — but there is now a
**recurring visit**. `workspace-repo-inventory-drift` was wrong for eleven days
and was caught by exactly that: a rotation into the repo it describes. The
repair channel a cross-repo entry lacked is the rotation itself, and it did not
exist before 2026-08-07.
