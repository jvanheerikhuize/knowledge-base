---
name: kb-reverification-has-one-rate
type: semantic
description: re-verification has one sustainable rate — live entries over the review cycle, 0.43/day here — and going faster flattens the queue less, because the spread you create is the calendar days you spend and not the entries you do; also, `busiest` cannot see a batch happening, so the forecast now reports effective spread and pace
confidence: high
source: simulation over this store's real last_verified dates (scripts/kb.py review_forecast, STALE_DAYS=90), 2026-08-15; ROADMAP Phase 15
created: 2026-08-15
last_verified: 2026-08-15
links: [kb-review-load-is-one-cohort, kb-verification-rides-along-with-authoring, kb-entry-status-model, stranded-branches-need-a-second-channel, kb-forgetting-model, kb-nothing-predicts-the-next-correction]
---

A review date is `last_verified + STALE_DAYS`, so re-verifying an entry does
not only record a check — it **schedules** that entry's next review, exactly
one cycle out. Every entry re-verified on the same day is therefore booked onto
the same future day. This is the mechanism behind
[[kb-review-load-is-one-cohort]], stated as a rate rather than as a shape.

## The rate

**`live_entries / cycle_days`** — for this store on 2026-08-15, 39/90 =
**0.433 entries a day**, one entry every 2.3 days. (Every figure here is as
measured before this entry and its links were filed; adding them makes the
store 40 entries at 0.444/day and an effective spread of 5.52. They are frozen
so the reasoning can be checked against what it was actually run on — `kb.py
status` reports the live numbers.) That is the only rate that
both flattens the queue and holds it flat, and it is now reported by
`review_forecast()` as `sustainable_per_day`, in `kb.py status`, `kb.py stats`,
`site/data.json` (`schema_version: 4`) and on the status board.

## Faster is worse, measured

Simulated against this store's real `last_verified` dates over two cycles
(180d), oldest-due first, with the six routine-unreachable entries excluded and
a session declining to re-check anything younger than half a cycle:

| pace | verifications | effective spread | distinct due dates |
|---|---|---|---|
| do nothing | 0 | 4.83d | 12 |
| **0.43/day (cycle rate)** | **66** | **22.04d** | **34** |
| 1/day | 115 | 22.04d | 34 |
| 5/day ("a handful") | 127 | 9.69d | 14 |
| 10/day | 132 | 7.07d | 13 |

Five a day does **nearly twice the work for less than half the spread**. The
reason is not subtle once seen: a pace above the cycle rate exhausts the pool of
entries worth re-checking, then idles until the pool refills — and the bursts
*are* the clusters. At the cycle rate there is always exactly one entry ripe,
so due dates land on separate days.

**Convergence takes one full cycle and cannot be bought with effort.** The same
simulation, sampled every 15 days, sits at 4.83 effective days through day +45,
reaches 15.36 at day +90 and settles at 22.04 by day +105. The span of review
dates you can create is the span of calendar days you spend creating them; no
per-day quantity changes that. So this is a standing habit at a low rate, not a
task a session can finish.

**The ceiling is 39.0 effective days** (busiest 1, nothing overdue) — reachable
only if every entry is checkable. It is not: see below.

## `busiest` cannot see a batch happening

`review_forecast` reported `busiest` as its concentration summary, and `busiest`
names only the tallest bar. Measured on the real store on 2026-08-15, batching
k entries onto today leaves `busiest` at **15 for every k from 0 to 13**, while
the effective spread falls 4.83 → 3.46. A session reading `busiest` to check
whether its batch did harm sees "unchanged" across exactly the range of batch
sizes it would plausibly do — and whether the number moves at all depends on the
accident of where the existing maximum sits. (The 2026-08-14 session *did* see
6 → 15, because its own pile became the maximum. Same batch today reads as no
change.)

So the forecast now also carries **`effective_days`**: the inverse Simpson index
over the due-date histogram, `1 / Σ(nᵢ/N)²` — the number of days the load would
occupy if it were spread evenly at its current concentration. Bounded by 1 and
the number of distinct due dates, and monotone under the batching that `busiest`
is blind to. This store: **4.83 of 90 days.**

## The warning is on `verify`, not in a document

Three prior repairs for over-sweeping were all sentences added to files —
[[kb-review-load-is-one-cohort]] (2026-08-05), its own correction (2026-08-14),
and the standing action in `ROADMAP.md`. ROADMAP Phase 14 measured why that
shape of repair fails: a message delivered *before* the mistake never reaches a
session that already believes it is doing the right thing. The 2026-08-14
session read all of that prose and verified 13 entries in one sitting anyway.

`kb.py verify` therefore prints the pace after the batch passes the rate —
`verify_pace_warning()`, on stderr, naming today's count, the sustainable rate,
and the resulting effective spread. Deliberately **not** a refusal and not a
lint failure: a verification that really happened is a true record, and
reverting it would trade it for a false one. The defect is only in how many were
scheduled onto one date, so the response is a number, not a veto.

## The floor a routine cannot lift

Six live entries rest on things a scheduled sandbox cannot see — `asdlc` and
`digital-twin` (sibling repos), the claude.ai Routines UI, `~/.claude/
settings.json` on Jerry's machine, and the pre-2026-08-06 `~/Repos` working-copy
shape. All six were stamped on the store's opening day and have never moved, so
**all six come due on the same date, 2026-10-25** — the first day of the queue.
They put a permanent floor under it: `already_due` never drops below 6 after
that date, and `busiest` never below 6, whatever pace a routine keeps.

This revises [[kb-verification-rides-along-with-authoring]]'s conclusion in one
direction. That entry found that spreading a queue does not make a third of it
checkable; the converse also holds — the unreachable part **stays a cohort
permanently**, so part of the busiest-day number is not a thing to fix, and
reporting it as one invites a session to sweep harder against a floor. Only
Jerry can clear those six.
