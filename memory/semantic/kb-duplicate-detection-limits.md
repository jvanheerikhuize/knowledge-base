---
name: kb-duplicate-detection-limits
type: semantic
description: lexical similarity cannot find semantic duplicates in this store — measured, a hand-written paraphrase ranked below 13 pairs of merely-related entries — so kb.py dupes is scoped to near-verbatim overlap and says so
confidence: verified
source: measured 2026-07-28 against the live 20-entry store; scripts/kb.py dupe_pairs, tests/test_kb.py TestDupes
created: 2026-07-28
last_verified: 2026-07-28
links: [kb-forgetting-model, kb-ranked-retrieval, kb-is-file-based]
---

`kb.py dupes` finds **text recorded twice**. It does not find **the same claim
written twice**. That distinction was measured rather than assumed, and the
measurement is the reason the tool is scoped the way it is.

**What was measured.** Word-shingle Jaccard (k=3, 5, 7) over the live 20-entry
store, then two candidate metrics — token-set Jaccard and tf-idf cosine —
scored against a deliberately constructed known positive: a hand-written
paraphrase of `kb-is-file-based` making the same assertions with no copied
phrasing.

**The result.**

| metric | rank of the known-positive pair |
|---|---|
| token-set Jaccard | #14 of 210 |
| tf-idf cosine | #16 of 210 |

Above the real paraphrase sat thirteen-plus pairs of entries that share a
subject but say different things — `kb-forgetting-model` with `kb-roadmap`,
`workspace-repo-inventory-drift` with `workspace-audit-2026-07-27`. On raw
5-word shingles the paraphrase scored **0.000**, and the whole store's maximum
pair score was 0.007.

**Why.** Shingling detects copy-paste. The entries here are hand-written prose
about a small set of related topics, so they share vocabulary and subject
matter while sharing almost no phrasing. Every lexical metric therefore ranks
*topical neighbours* above *actual restatements* — the exact inversion that
makes a duplicate-finder useless. Any threshold low enough to catch the
paraphrase admits a dozen false positives first, and a tool whose top hits are
all wrong is one people learn to ignore.

**What was built instead.** `dupes` keeps shingle Jaccard but sits at a
threshold (0.5) about seventy times the store's observed maximum, so it fires
only on genuine near-copies — an entry recorded twice, a scaffolded copy drifting
back in, an agent re-adding what it already wrote. It also reports
*containment*, which is asymmetric and catches the case Jaccard scores lowest:
a short entry wholly absorbed into a longer one. Both numbers are printed,
along with the sentence naming the limit, so nobody reads a clean result as
"there are no duplicates".

MinHash and LSH were considered and rejected. They exist to approximate Jaccard
when O(n²) is intractable; this corpus is a few dozen files, where the exact
computation is free and an approximation would only add error.

**The open problem.** Detecting semantic duplication needs either embeddings —
which breaks the no-infrastructure premise of [[kb-is-file-based]] and the no-
vendor-model rule of [[twin-sovereignty-constraint]] — or an agent reading
candidate pairs and judging them, which is how classification already works for
`kb.py new` and would be consistent with it. The second is the promising route
and remains unbuilt. Until then the honest position is that this store has no
automated defence against saying the same thing twice in different words.

**The guard.** `TestDupes.test_a_paraphrase_is_not_flagged` pins this finding as
a regression test: it asserts the paraphrase is *not* reported. If a future
session lowers the threshold to "catch more", that test fails and this entry
explains why it was set where it was.
