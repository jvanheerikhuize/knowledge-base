---
name: kb-a-fitted-golden-set-starts-perfect
type: semantic
description: a retrieval fixture whose queries were reworded until each reached rank 1 is selected on the outcome it measures — it scores 1.000 at filing and decays as the store grows, and no score can distinguish it from an honest set, though the rank-1 margin can
confidence: high
source: measured 2026-08-17 in this repo; ROADMAP Phase 17
created: 2026-08-17
last_verified: 2026-08-17
links: [kb-golden-set-lives-in-the-wording, kb-ranked-retrieval, kb-context-budget-is-not-a-pack-size]
---

A golden set can be corrupted by *how its queries were filed*, independently of
how they were worded. [[kb-golden-set-lives-in-the-wording]] guards the wording
axis and cannot see this one.

## The shape it makes

Queries filed only once they already reach rank 1 start at a perfect score by
construction and have nowhere to go but down. This store's set splits exactly
along that line — same ranker, same queries, replayed against all 34 commits
that have touched `memory/`:

| cohort | filed | success@1 at filing | success@1 six days later |
|---|---|---|---|
| 28 written question-first, filed at whatever they scored | 2026-08-02 | 0.536 | 0.500 |
| 10 reworded until all ten reached rank 1 | 2026-08-10 | **1.000** | **0.700** |

Across the twelve entries added since it was filed, the honest cohort has lost
one query net and wandered inside a two-query band with no trend. The fitted
cohort lost three of ten across three entries. So the store's apparent retrieval
decline — success@1 0.632 → 0.553, close enough to a 0.50 floor to read as a
regression — is a quarter of the set unwinding at one query per entry filed,
not the ranker.

The tell is that the fitted cohort's *headline* was an improvement. The session
that filed it reported every number raised, because a cohort that cannot score
below 1.000 at birth drags any average upward on the day it lands, and the
floors underneath were then re-baselined against that reading.

## Why nothing catches it

- **No score can.** `success@1`, `mrr`, `recall@3`, `recall@5` and
  `recall_at_pack` all count a win by 1% of score identically to a win by 80%.
  A fitted set and an honest one are indistinguishable in every one of them
  until the corpus grows.
- **The vocabulary guard cannot.** Rewording *away* from an entry's own words
  while steering *toward* its ranking satisfies a title-overlap rule
  comfortably: the fitted queries reuse at most 14% of their entry's title
  words, and so does a blind-written control.
- **A ranker-perturbation test cannot**, which is the useful negative. Flat
  field weights and `k1` at 0.6 and 4.0 cost the fitted cohort 0.100 at worst
  against the honest cohort's 0.071 — indistinguishable. **The fitting is to the
  corpus's composition, not to the ranker's parameters.** That is why adding
  three entries detects it and ablating the ranker does not, and it rules out
  the obvious "an overfitted fixture collapses under ablation" guard.

## What does show it, at filing time

The **rank-1 margin** — how far the top hit finished clear of the runner-up, as
a share of its own score. Rewording stops the moment a query crosses into first
place, so a fitted query wins by a hair:

| cohort | median rank-1 margin at filing | within 20% of the runner-up |
|---|---|---|
| question-first | 0.359 | 2 of 15 |
| reworded-until-first | 0.128 | 6 of 10 |

`eval_report` now reports `median_rank1_margin`, `thin_at_1` and `rank1_hits`,
and `kb.py eval` prints them. Reported, not gated: a threshold would be a
constant fitted to 25 rank-1 hits, which is the mistake
[[kb-golden-set-lives-in-the-wording]] already records.

Alongside it, `uncovered_entries` names entries no query mentions. An uncovered
entry competes for every query and answers none, so it can only lower the score.
It is the other half of any unexplained drop, and the fixable half.

## The control that settles it

Ten fresh queries were written question-first for the same ten target entries,
committed to a file *before* any ranking was run, and scored once with no
rewording: **success@1 0.100**, against the fitted cohort's 1.000 at filing and
0.700 against a larger store. Same targets, same ranker, same day, so neither
target difficulty nor crowding explains the gap — and a mechanical probe
(query = the entry's own description) puts both target sets at rank 1, 10 of 10
and 28 of 28.

Two honest limits. The blind author had already read the fitted wording, which
biases a blind attempt *toward* it — conservative, against the finding rather
than for it. And ten queries is few; the 90-point gap is far larger than that
noise, but the 0.100 itself is not a reliable estimate of what unselected
queries score.

## What follows

- **File the query at whatever it scores.** A query that misses is data — it is
  the only kind of query that can report a ranker getting worse. This is now the
  second rule in `.kb/golden.json`, next to the vocabulary rule.
- **Do not re-baseline floors downward to absorb the unwinding.** That ratifies
  the inflated reading a second time. Add coverage for uncovered entries
  instead, and let a floor break if it breaks — `_diagnosis()` names the
  uncovered entries and the thin-win share so the failure reads correctly.
- **Do not delete the fitted queries.** They are legitimate questions; only
  their filing was selected. They will settle near the honest cohort's rate on
  their own, and deleting them costs coverage of ten entries.
