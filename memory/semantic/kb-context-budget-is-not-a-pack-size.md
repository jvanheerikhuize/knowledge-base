---
name: kb-context-budget-is-not-a-pack-size
type: semantic
description: a context pack is bounded by a token budget, so it shrinks as entries get longer — 5.14 entries per pack on 2026-07-27, 2.75 on 2026-08-09, with the budget unchanged and every golden-set metric blind to it because none has a budget term
confidence: verified
source: measured 2026-08-10 by replaying all 34 commits that touch memory/ against today's ranker and golden set; scripts/kb.py context_pack()/eval_report(); ROADMAP Phase 13
created: 2026-08-10
last_verified: 2026-08-19
links: [kb-ranked-retrieval, kb-golden-set-lives-in-the-wording, kb-review-load-is-one-cohort, kb-a-constant-query-has-a-ceiling]
---

`kb.py context` is the command [[kb-ranked-retrieval]] calls "the one an agent
should reach for first", and PURPOSE.md's success metric is written in its
shape. Its size is specified as a **token budget** (`--budget`, default 2000).
That is not a specification of how much an agent receives. It is a
specification of how many *characters* it receives, and the number of entries
that buys falls as entries get longer.

## The measurement

Every one of the 34 commits that has touched `memory/` was replayed with the
ranker and the golden query set held fixed at today's, so the only thing
varying is the store:

| date | entries | median entry | entries per pack |
|---|---|---|---|
| 2026-07-27 | 10 | 1,324 chars | **5.14** |
| 2026-07-31 | 24 | 2,051 | 3.78 |
| 2026-08-03 | 31 | 2,219 | 3.14 |
| 2026-08-09 | 37 | 2,951 | **2.75** |

Monotone, and a 47% decline in thirteen days. The pack today holds a median of
**3** entries and never more than 4.

**Length is the whole mechanism; count is not.** Two controls on today's
store, both at the default budget:

- today's 37 entries, each body truncated to the 2026-07-27 median of 1,324
  chars → **5.25** entries per pack, i.e. the original figure recovered
- only 10 of today's entries, at today's lengths → **2.39**, no better than
  the full store

So the store getting *bigger* costs nothing. The store getting *richer* — the
Phase 4–12 write-ups run to 3,000–6,000 characters each — is what emptied the
pack. A budget in tokens is a stable promise only if entry length is stable,
and nothing here holds it stable or watches it.

## Why nothing caught it

[[kb-golden-set-lives-in-the-wording]] built the instrument for exactly this
class of regression, and it is structurally incapable of seeing this one.
`success@1`, `MRR`, `recall@3` and `recall@5` all ask *where the ranker put an
entry*. None of them reads a budget. Sweeping the budget over the real store:

| budget | entries per pack | recall@pack | recall@3 / recall@5 |
|---|---|---|---|
| 1,000 | 1.57 | 0.571 | 0.714 / 0.786 |
| 2,000 (default) | 2.75 | 0.714 | 0.714 / 0.786 |
| 4,500 | 5.29 | 0.786 | 0.714 / 0.786 |
| 12,000 | 12.86 | 0.857 | 0.714 / 0.786 |

The product's delivery moves by 29 points across that sweep and every rank
metric is bit-identical. Note the middle row: **`recall@pack` and `recall@3`
are the same 20 of 28 queries today, not merely the same count** — the pack
holds about three entries, so recall@3 is what it delivers.

`eval_report`'s docstring claimed `recall@3`/`recall@5` were "what `kb.py
context` actually delivers". That was true on 2026-07-27, when the pack held
5.1 entries, and it was already false when it was written on 2026-08-02, by
which time the pack held 3.5. A description of a moving quantity was recorded
as though it were a definition.

Entry length is *not* an independent axis: BM25 reads document length too, so
lengthening bodies moves the ranking as well. The budget is the clean axis,
and it is the one nothing measured.

## What shipped

- **`recall_at_pack`** in `eval_report`, scoring the pack `context_pack`
  actually returns at the default budget, alongside `mean_pack_entries` and
  `budget_bound`. `kb.py eval --budget N` scores it at any budget. Separate
  from the rank metrics rather than replacing them: they answer different
  questions and only one of them is the product.
- **The pack says why it stopped.** "3 entries" reads identically whether
  three was all there was or all that fit, and those want opposite reactions.
  A pack now reports *stopped on budget* (naming the next entry that did not
  fit — exact, and needing no relevance threshold, because it is the one the
  loop was holding) or *stopped on matches*. Today **28 of 28** golden queries
  are budget-bound. On MCP too, as `budget_bound` / `next_omitted`.
- Floors in `tests/test_retrieval_golden.py` on `recall_at_pack` and on mean
  pack entries, plus a test asserting that sweeping the budget moves the pack
  and leaves every rank metric untouched — which fails if someone removes
  `recall_at_pack` as redundant.

## What deliberately did not ship: a bigger default budget

4,500 tokens restores the 2026-07-27 figure exactly (5.29 entries). It was not
adopted, for the reason the finding is about: **2,000 was also a correct number
once.** Raising it re-establishes today's pack size and starts drifting again
with the next long write-up, and the drift would be just as invisible as this
one was. The stable repair is that the pack reports being budget-bound and the
suite has a floor, so the next erosion is a failing test rather than an
archaeology exercise.

The number is recorded so the decision can be made deliberately rather than by
default. It is Jerry's call, not a routine's: `DEFAULT_CONTEXT_BUDGET` is
caller-facing, and every consumer pays for it in their own context window.

The same shape as [[kb-review-load-is-one-cohort]]: a fixed constant whose
*meaning* is a function of the store, going wrong quietly because nothing
reported the function.

**Correction, 2026-08-19 — the budget is not the only thing bounding a pack,
and this entry framed it as if it were.** Everything above holds, but it treats
"how many entries fit" as the question, and a second bound sits above it:
entries that score zero against the query are unreachable at *any* budget.
Measured over the 87 entries sessions actually went back to, the protocol's
own query could reach only 40 of them however large the budget got
([[kb-a-constant-query-has-a-ceiling]]). The clamp this entry documents is also
what hid that: at the default budget a good query and a bad one both return
2–4 entries, so the difference between them was not distinguishable. Read the
two together — raise the budget for entries that *matched*, re-word for the
ones that did not.
