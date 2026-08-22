---
name: kb-a-verdict-expires-faster-than-it-is-written
type: semantic
description: a pair verdict expires on any edit to either entry's claim text, so the pair ledger decays far faster than the entries it judges — 61.5% of 148 verdicts gone in three weeks, half of them within 10 days against a 90-day entry cycle — and three narrower expiry rules were measured and none helps
confidence: high
source: replay of all 30 commits touching memory/ and all 8 touching .kb/verdicts.json, 2026-08-22; plus a full 78-pair judging pass the same day
created: 2026-08-22
last_verified: 2026-08-22
links: [kb-a-blocker-must-remember-its-rulings, kb-duplicate-candidates-by-nearest-neighbour, kb-contradiction-is-a-second-axis, kb-reverification-has-one-rate, kb-corrections-happen-in-place, kb-consolidation-is-owed-work, kb-the-backstop-arrives-after-the-session, kb-a-constant-query-has-a-ceiling, kb-review-load-is-one-cohort, stranded-branches-need-a-second-channel]
---

`judge` writes a verdict about a **pair**, and binds it to a digest of both
entries' claim text — so any edit to either entry expires every verdict that
entry appears in ([[kb-duplicate-candidates-by-nearest-neighbour]]). The rule
is deliberate and the docstring defends it: a judgement about text that no
longer exists is not a judgement.

What nobody had measured is how fast that empties the ledger.

## The rate

Replaying all 30 commits that touch `memory/` and all 8 that touch
`.kb/verdicts.json`, with the ranker and the blocking rule held at today's
version so only the store varies:

| | |
|---|---|
| verdicts ever recorded (before today's pass) | 148 |
| still in force on 2026-08-22 | **51 (34.5%)** |
| expired — an entry's claim text changed | **91 (61.5%)** |
| moot — an entry archived | 6 |
| median observed lifetime of an expired verdict | **5 days** |
| still in force at t+10d | **50.7%** |
| entry review cycle, for comparison | **90 days** |

Survival is not a long tail with an early cliff; it is close to linear decay
from day one. 94.1% survive their first day, 63.2% their first week, and
44.9% three weeks. Every one of the 148 was recorded in a single seven-day
burst (2026-07-31 → 2026-08-07) and **nothing has been judged since**, so the
queue ran from **0 unjudged pairs on 2026-08-01 to 78 on 2026-08-22**,
monotonically, while settled pairs fell 58 → 26.

## Why no narrower rule fixes it

The obvious repair is to expire a verdict when the *relationship* changes
rather than when either entry's bytes do. Three keys were measured against
the same replay, each verdict evaluated from the text it was passed on
against today's text:

| expiry key | verdicts expired |
|---|---|
| whole claim text (shipped) | 80 of 136 |
| the pair's shared token set | 78 of 136 |
| only the lines containing shared vocabulary | 80 of 136 |

Two points of difference across 136 verdicts. The mechanism is in the edits:
of the 21 invalidations locatable in git, **0 added zero tokens shared with
the other entry** — every single one touched the neighbour's material,
because this store is written to cross-reference itself and every phase
write-up discusses its predecessors ([[kb-corrections-happen-in-place]]).
The relationship really does move each time; it just moves by a **median
0.008 Jaccard, maximum 0.049**. The rule is not too coarse. The store is too
self-referential for a pair-level judgement to stay settled.

So the corpus of expiry rules is closed the way
[[kb-review-load-is-one-cohort]]'s repairs were: measured, and none shipped.

## What the expiry has never bought

Across the whole history, **9 pairs were re-judged after being reopened, and
0 came back with a different ruling.** Today's pass re-confirmed a further
**25** — again 0 changed. That is 0 of 34, which is weak evidence for a rule
that fires 3.6 times a day, and it is the only evidence there is: the ledger
has no counter-example, because a ruling has never flipped.

It is not evidence to *remove* the rule, either. Expiry is maximally
sensitive and cannot miss a pair that genuinely converged — the failure it
prevents has therefore never been observed, which is what a working guard
looks like. The honest reading is that it is unfalsified, not that it is
useless.

## The defect was the silence, not the rule

`triage`, `status` and `lint` all read clean on 2026-08-22 while 78 pairs
stood unjudged and the last ruling was 15 days old. `triage_report` reads one
entry at a time, so a pair is structurally invisible to it — the same reason
`lint` cannot see a missing edge ([[kb-consolidation-is-owed-work]]) — and it
said "nothing needs attention" rather than "no *entry* needs attention".

That mattered. Reading the queue turned up a live defect nothing else could
see: `stranded-branches-need-a-second-channel` carried
`confidence: verified` in its frontmatter and a body section headed "Not yet
verified" claiming the workflow had never fired in production, while
[[kb-the-backstop-arrives-after-the-session]] documented that fire in detail.
An entry contradicting **itself** is invisible to `lint`, which reads one
entry, and to `judge`, which compares two. It surfaced because a human-shaped
read of the pair noticed the neighbour said the opposite.

Shipped: `judgement_load()`, reported in `kb.py status`, `kb.py stats`,
`data.json` (`schema_version: 5`) and the MCP `triage` tool, plus a
`candidates` footer that splits the queue into never-judged and reopened —
different work, and one flat number hid that. Reported, never gated, for the
reason [[kb-a-constant-query-has-a-ceiling]]'s reach is reported and not
gated: a store can be behind on this queue and perfectly healthy.

**Confidence is `high`, not `verified`, on one point only:** the survival
curve is drawn from a store that has judged in exactly two bursts, fifteen
days apart. A third burst at a different cadence could bend it. The 61.5%,
the 5-day median and the three-rule comparison are all direct replays and do
not depend on that.
