---
name: kb-duplicate-candidates-by-nearest-neighbour
type: semantic
description: semantic duplicates are findable after all — not by lowering a global threshold but by asking each entry for its nearest neighbours; measured, 7 of 7 planted paraphrases caught in 5% of the pair space, with the verdict left to an agent and recorded in .kb/verdicts.json
confidence: verified
source: measured 2026-07-29 against the live 21-entry store plus 7 hand-written paraphrases; scripts/kb.py neighbour_pairs/candidate_pairs, tests/test_kb.py TestCandidates
created: 2026-07-29
last_verified: 2026-07-29
links: [kb-duplicate-detection-limits, kb-forgetting-model, kb-ranked-retrieval, kb-is-file-based, twin-sovereignty-constraint, kb-contradiction-is-a-second-axis, kb-roadmap]
---

[[kb-duplicate-detection-limits]] concluded that lexical similarity cannot find
semantic duplicates in this store. That measurement was sound and its regression
test still passes. The conclusion drawn from it was too broad, and this entry is
the correction.

**What was broken was the question, not the metric.** A global threshold asks
*"is this pair similar in absolute terms"*. Absolute similarity is dominated by
how much vocabulary a **topic** happens to share, and that varies far more
between topics than duplication does within one — so topical neighbours drown
real restatements, exactly as measured. Ask instead *"of everything in the
store, which entries is this one **most** like"* and the per-entry baseline
cancels out. Same metric family, same corpus, different question.

**The measurement.** Seven hand-written paraphrases of live entries — same
claims, no copied phrasing — planted in the store, giving 28 entries and 378
pairs with seven known positives.

| framing | worst positive | pairs to read |
|---|---|---|
| global ranking (the old question) | **#81 of 378** | — |
| per-entry top-1, unioned both ways | **all 7 caught** | **19** (5% of the space) |
| per-entry top-3, unioned both ways | all 7 caught | 55 |

Token-set Jaccard over description+body wins. Shingles are the wrong unit here
because they measure shared *phrasing*, which is precisely what a restatement
does not share. Symmetric BM25 is a near-equal second and needs 2 neighbours
for 7 of 7.

**The union is load-bearing, not a detail.** A long entry's nearest neighbour is
often *not* the short entry restating it, while the short one's nearest
neighbour is reliably the long one. Taking a pair when *either* side nominates
it — rather than requiring mutual agreement — is what took 6 of 7 to 7 of 7 at
no extra cost.

**So the tool blocks and refuses to rule.** `kb.py candidates` is the cheap,
recall-oriented half of the standard record-linkage pair; deciding is the
expensive half, and it is a judgement made by reading both entries. Roughly one
candidate in three to eight is real and no score says which. That division of
labour — tool does the mechanics, operating agent supplies the classification —
is the same one `kb.py new` already uses, and it is what keeps
[[twin-sovereignty-constraint]] intact: no embedding model, no vendor call,
nothing to keep running.

**Verdicts are durable and content-bound.** `kb.py judge <a> <b>
duplicate|overlap|distinct` writes to `.kb/verdicts.json` against a digest of
both entries' description and body, and nothing else. Re-verifying or relinking
an entry does not expire the verdict, because neither changes what it *claims*;
rewriting a body does, and the pair returns marked `TEXT CHANGED SINCE`. That is
what makes the sweep incremental: the first pass over this store cost 42
judgements, a new entry costs about `n` more, never another full sweep. A pair
judged `duplicate` deliberately stays in the queue until someone merges it —
that is outstanding work, not a closed question.

**First full pass, 2026-07-29: 42 pairs judged, zero duplicates** (24 overlap,
18 distinct). One unlinked overlap was found and linked
([[kb-agent-entrypoint-is-agent-md]] ↔ [[workspace-repo-inventory-drift]]). The
closest thing to a real duplicate is [[distill-session-into-memory]] against
[[persist-insight-to-knowledge-base]], judged `overlap` with a note that the
latter's steps 3–5 restate most of the former — the first candidate for a
future `consolidate`.

**Default `-n 3`, not the measured-sufficient `-n 1`.** Recall was already 7/7
at one neighbour, but two positives cleared their nearest rival by under 0.02,
and seven positives is far too small a sample to spend that margin on.

**The measurement harness was not kept**, deliberately — a research script that
nothing runs rots, and `TestCandidates` already pins the claim that matters (the
paraphrase `dupes` must stay quiet about is the one `candidates` must surface).
The cost is real though: re-running the recall numbers means writing fresh
paraphrases first, which is exactly what made correcting the 2026-07-28
conclusion expensive. Budget for that before changing the blocker.

**The transferable lesson.** A negative result can be real, reproducible, and
correctly guarded by a test, and still point at the wrong conclusion — because
what was measured was one *framing* of the question rather than the question.
Before accepting "X cannot work here", check which of those two was tested.
