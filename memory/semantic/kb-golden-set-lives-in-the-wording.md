---
name: kb-golden-set-lives-in-the-wording
type: semantic
description: a retrieval golden set generated from entry titles scores a perfect 1.000 against every ranker measured, including one that never reads a body — the queries must be paraphrases, and at 28 entries the set detects breakage but is blind to tuning
confidence: verified
source: measured 2026-08-02 in this repo; ROADMAP Phase 7
created: 2026-08-02
last_verified: 2026-08-14
links: [kb-ranked-retrieval, kb-duplicate-detection-limits, kb-forgetting-model]
---

A golden set of query → expected-entry pairs is worth having only if it can
fail. Two things about this one were measured before it shipped, and both
change how it must be written and how it may be asserted.

## Queries built from the entries test nothing

The obvious construction — walk the store, turn each entry into a query — was
scored against fourteen deliberately degraded rankers:

| query set | rankers scoring 1.000 success@1 |
|---|---|
| entry titles ("kb over mcp") | **14 of 14** |
| entry descriptions | 12 of 14 |
| task-shaped paraphrases | 0 of 14 |

A title-derived set is passed by a ranker that never reads an entry body and by
one with no term weighting at all. It would sit in CI going green while
measuring only the tokenizer.

So every query in `.kb/golden.json` is written as the question first and only
then matched to the entry that should answer it — for a hypothetical entry
`deploy-key-rotation`, the question "who do I ask before touching the
production key", not "deploy key rotation". The wording *is* the fixture.
`test_no_query_restates_its_own_entry_title` enforces it: no query may reuse
more than 60% of the words in its entry's name (worst in the current set: 50%).
Without that guard, the natural repair for a failing query — nudge it toward
the entry's vocabulary — quietly converts the suite back into decoration.

**A store that documents itself can contaminate its own fixture.** This entry
originally illustrated the rule by quoting a real query from the set. Because
the write-up lives *in the store being searched*, that made this entry the
top hit for that query, displacing the entry that should have answered it —
recall@5 fell from 0.862 to 0.793 on the commit that added it, which is how it
was caught. Examples in entries must therefore be invented, never lifted, and
`test_no_entry_quotes_a_golden_query` fails the build if one is.

## At this size the set sees breakage, not tuning

28 queries over 28 entries at the time of the study: success@1 0.536, MRR
0.668, recall@3 0.786, recall@5 0.857. (This entry then joined the store with
a query of its own, taking the shipped set to 29/29 at 0.517 / 0.649 / 0.759 /
0.828.) Ablating one signal at a time, with a paired bootstrap over
queries (4,000 resamples, 95% CI on ΔMRR), **two of eleven ablations are
distinguishable from the live ranker**: removing entry bodies (−0.406) and
removing tf saturation (+0.059). Everything the ranker's design turns on —
IDF, field weighting, and all three memory-specific signals in
[[kb-ranked-retrieval]] — moves the score by about one query, which at n=28 is
noise.

Consequences, both binding on future sessions:

- **Assert floors, never scores.** `tests/test_retrieval_golden.py` sets its
  thresholds about four queries below current performance and asserts no tuned
  constant. Raising a floor to lock in an "improvement" inside the noise band
  pins the ranker to its own test.
- **Do not retune on this set.** Raising `k1`, and the principled version of
  the same fix (BM25F: per-field normalised term frequencies, saturated once,
  instead of weighting fields by repeating their tokens), were both measured.
  BM25F scores +0.030 MRR at the standard `k1=1.5`, CI [−0.000, +0.084] — not
  distinguishable from what shipped, nor from simply raising `k1`. Picking
  between them on a 28-query set written in the same session that measured it
  is fitting noise. The numbers are in the ROADMAP for a future session with a
  bigger store to re-run.

The set carries its own expiry: `TestTheSetCanStillFail` scores the
body-blind ranker every run and fails if it ever clears the floors. When that
fires, the store has outgrown the fixture and the fix is new queries — not a
lower bar.

## What this does not claim

One author wrote all 28 queries and every `also_ok` judgement, in the session
that measured them. The comparisons are paired on the same queries so they
survive that, but the absolute 0.536 does not transfer to anyone else's
questions. And 28 queries is few enough that every confidence interval here is
wide — which is itself the result.
