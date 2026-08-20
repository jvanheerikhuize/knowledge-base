---
name: stranded-branches-need-a-second-channel
type: semantic
description: the sixth stranding was a session that believed it had landed and wrote so in DEBRIEF.md — charter prose cannot reach a session that already agrees with it, so the repair has to be a signal from outside the session
confidence: verified
source: PR #55 (opened 2026-08-10T09:20:13Z, merged 2026-08-14 after 4 days open) read against its own DEBRIEF text, the 2026-08-09 charter repair in PR #52, and the workflow-run history for 2026-08-11 through 08-13
created: 2026-08-14
last_verified: 2026-08-20
links: [stranded-branches-track-the-charter-text, kb-prospective-memory-that-fires, kb-the-backstop-arrives-after-the-session]
---

[[stranded-branches-track-the-charter-text]] measured six months of routine
sessions and concluded that stranding tracks what `AUTONOMY.md` authorizes: 0
of 11 while automerge was pre-authorized, 3 of 6 after it was withdrawn. It
repaired the text on 2026-08-09 (PR #52) — the gate is on what a session may
*start*, not on what it may *land*.

**A session stranded work the next day anyway, and not for the reason the
repair addressed.** The prior three strandings withheld the merge deliberately,
reasoning that authorization had lapsed. This one did the opposite: it believed
it had landed, and said so.

## What happened

`claude/cool-cerf-bb1xow`, 2026-08-10 09:20 UTC. The session did the work
correctly — ten golden-set queries, five floors re-baselined, 509 tests green —
pushed, opened **PR #55**, and ended. Its `DEBRIEF.md` line, written in the
same commit, reads:

> Landed directly on `main` per the git strategy (small, scoped, tests green).

It had not. The work sat on a branch behind an open PR for **four days**, while
every one of the 25 legitimately-merged PRs in this repo's history merged
within **62 minutes** of opening (median 4.4). The backlog checkbox on `main`
still read unchecked the whole time, which is the exact invisibility the
charter rule exists to prevent.

## Why this is a different failure

The 2026-08-09 repair works by removing a contradiction a session might reason
its way into. That mechanism requires the session to be *reasoning about
whether it may land*. This one was not:

| | strandings 1–3 (2026-08-06/07) | stranding 6 (2026-08-10) |
|---|---|---|
| did it consider landing? | yes, and declined | no — believed it already had |
| stated reason | "pre-authorization was scoped to the mandate period" | none; asserts compliance |
| would clearer text help? | yes — and it did | **no** — it already agreed with the text |

A session cannot be instructed out of a belief it already holds. Every repair
this repo has tried for stranding — the 2026-07-31 rule, the 2026-08-09
disambiguation, the `git ls-remote` check at session start — is a message
*to the session that might strand*, delivered *before* it strands. None of
them can fire afterwards, and afterwards is the only time the error is visible.

## The recovery channel that did work, and how slowly

The charter's session-start `git ls-remote` check is what eventually found it —
on **day 4**, by this session. Days 2, 3 and 4 of the strand (2026-08-11
through 08-13) left **no repo-visible session trace at all**: the only workflow
runs are the daily `kb-due` cron, no pushes, no PRs, no branches. Whether
routines fired and produced nothing, or did not fire, cannot be determined from
inside the repo — but either way the outcome is the same, and it is the case
against relying on in-session checks alone: **the recovery channel only runs
when a session runs, and a stranding is precisely the state a session leaves
behind when it stops.**

## What shipped

`ROADMAP.md` recorded the reopen condition for a stranded-branch detector on
2026-08-09 — "build it if the repair fails" — with two objections. Both are now
answered:

- *"The defect is in the charter's text, not in its observability."* Falsified
  above. The text was correct and the session believed it complied.
- *"Its standing fires are two branches only Jerry can clear, so it opens an
  issue no routine can close."* Real, and handled: `ACKNOWLEDGED` in
  `scripts/kb_stranded_issue.py` lists those two with a required reason, reports
  them under their own heading, and excludes them from the count that opens the
  issue. **The detector fires zero times today** (verified against the live
  branch list after PR #55 merged). A test asserts every acknowledged branch is
  documented in `AUTONOMY.md`, so the list cannot be grown to silence a real
  stranding.

The predicate is the one already measured at 5-of-5 recall: a `claude/*` branch
with commits not on `main`, tip quiet for 12h. Same split as the `kb-due`
workflow it copies — rendering in a tested script, git and `gh` in the
workflow.

**One dependency worth knowing:** the zero-false-positive property rests on
delete-branch-on-merge being enabled here. A *squash* merge leaves the branch's
commits off `main`, so a squash-merged branch that survived would read as
stranded forever. All 19 PR-merged branches were deleted on the spot, so it has
never happened — but turning that setting off would make this detector lie.

## Not yet verified

The workflow has never fired in production. `confidence: high`, not `verified`,
for the same reason [[kb-prospective-memory-that-fires]] was: the create path,
the update path and the close path are unit tested, but nothing in this
environment can run a scheduled Action. Its first real fire should raise this
entry, and its first *false* fire should lower it.
