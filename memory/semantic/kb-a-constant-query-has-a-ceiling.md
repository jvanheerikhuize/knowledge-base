---
name: kb-a-constant-query-has-a-ceiling
type: semantic
description: a context query that is a constant has a retrieval ceiling no budget can raise — AUTONOMY.md's fixed session-start query scored zero against 54% of the entries sessions actually went on to edit, reaching 0.460 unbounded where a task-shaped query reaches 0.966
confidence: high
source: measured 2026-08-19 by replaying all 31 commits that modified a pre-existing entry, ranker and budget frozen at each session's own date; scripts/kb.py context_pack(); ROADMAP Phase 19
created: 2026-08-19
last_verified: 2026-08-19
links: [kb-context-budget-is-not-a-pack-size, kb-ranked-retrieval, kb-golden-set-lives-in-the-wording, stranded-branches-need-a-second-channel, kb-a-verdict-expires-faster-than-it-is-written]
---

`AUTONOMY.md` step 1 told every routine session to open with the same string:
`kb.py context "autonomous holiday work"`. [[kb-context-budget-is-not-a-pack-size]]
measured what the pack *hands back* and found the budget shrinking it; nobody
had asked whether the query could reach the right entries in the first place.

## The measurement

One row per commit that modified an entry which already existed at its parent
— an entry the session went *back* to, so an entry it needed. 31 sessions, 87
such entries, 2026-07-28 through 2026-08-18. Each replay runs the shipped
ranker over the store as it stood at the parent commit, with `date.today()`
frozen to the session's own date so decay and episodic recency are the ones
that session saw.

| arm | in the pack | what it is |
|---|---|---|
| `recent` — newest `last_verified` first, no ranker | 8/87 = **0.092** | control: is ranking doing anything |
| `fixed` — the constant query, shipped budget | 17/87 = **0.195** | what sessions actually got |
| `task` — the commit subject as query, shipped budget | 25/87 = 0.287 | |
| `fixed` — constant query, **unbounded** budget | 40/87 = **0.460** | the query's ceiling |
| `task` — task query, **unbounded** budget | 84/87 = **0.966** | |

Paired bootstrap over sessions, 4,000 resamples, 95% CI on the difference:

- `fixed` − `recent` = **+0.104**, CI [+0.025, +0.200] — **the ranker earns its
  keep.** A constant query still beats no ranking at all.
- `task` − `fixed` = +0.091, CI [−0.024, +0.205] — **not distinguishable.** At
  the shipped budget both queries return 2–4 entries, and the budget hides the
  difference between them.
- `task` unbounded − `fixed` unbounded = **+0.506**, CI [+0.400, +0.604].

## The mechanism is invisibility, not ranking

**47 of the 87 entries score zero against the constant query** — they share no
term with it, so BM25 returns nothing and no budget, no re-ranking, and no
tuning reaches them. That is the whole gap between 0.460 and 1.000: the
unbounded arm returns exactly the 40 entries that were visible. Under a
task-shaped query only 2 of 87 are invisible.

So the failure is a property of the *words*, and it is bounded by them:

> A constant query has a fixed ceiling. Raising the budget moves the pack
> toward that ceiling and never past it.

The pack's own advice was wrong in exactly this case. It said "Raise --budget
or narrow the query" — and narrowing helps only with entries that *matched*.

Two corroborating details. The brief was nearly constant: one entry
(`sibling-repo-access-denied-in-routines`) appears in 30 of the 31 packs. And
it was partly obsolete — 16 of 31 packs led with `holiday-autonomy-mandate`,
archived as spent since 2026-08-05, because "holiday" is the query's most
distinctive term.

## Reach is a precondition, not a quality score

`context_pack` now reports **reach**: how many of the retrievable entries the
query scored at all. It is reported and **never gated**, because among queries
that can see the store it predicts nothing — across the 42 golden queries the
median reach is 1.000 whether the query hits rank 1 (n=23) or misses (n=19).
Reach only tells you when a query has put entries out of its own range, which
is why it separates the protocol query (**0.452**, 19 of 42 live entries, after
this entry's own filing) from every golden query (min **0.682**) without saying
anything about the golden queries themselves.

`_retrievable()` restates `rank`'s candidate filters and could drift from
them, so the agreement is pinned behaviourally rather than declared: a store
where every entry carries a shared token makes the two counts equal by
construction, for every combination of `types` and `include_episodic`. All
three filter mutations are killed by that test.

## What was not done

`eval_report` gained no reach term. The golden set's median reach is 1.000, so
the number would be a constant there and would report nothing — the same
reason [[kb-golden-set-lives-in-the-wording]] gives for why a fixture built
from entry titles cannot fail. Reach discriminates between *queries a caller
writes*, and the golden set contains only good ones.

The constant in `AUTONOMY.md` was replaced with an instruction to query the
item at hand. That is a text repair to a text defect — the instruction was
wrong, not merely ignored — which is a different case from the ones
[[stranded-branches-need-a-second-channel]] found unreachable by wording.
