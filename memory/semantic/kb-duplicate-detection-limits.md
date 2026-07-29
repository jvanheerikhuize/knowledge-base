---
name: kb-duplicate-detection-limits
type: semantic
description: a global similarity threshold cannot find semantic duplicates — measured, a paraphrase ranked below 13 merely-related pairs — so kb.py dupes is scoped to near-verbatim overlap; the nearest-neighbour framing that did work is a separate entry
confidence: verified
source: measured 2026-07-28 against the live 20-entry store; scripts/kb.py dupe_pairs, tests/test_kb.py TestDupes
created: 2026-07-28
last_verified: 2026-07-28
links: [kb-forgetting-model, kb-ranked-retrieval, kb-is-file-based, kb-duplicate-candidates-by-nearest-neighbour]
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

**Solved 2026-07-29, and not the way this entry expected.** See
[[kb-duplicate-candidates-by-nearest-neighbour]]. Everything measured above is
still true of the question it asked — *can a lexical score decide a pair* — but
that turned out to be one framing of the problem rather than the problem. Asking
each entry for its nearest neighbours instead of thresholding pair scores
globally catches all seven planted paraphrases in 5% of the pair space, using
the same family of metric on the same corpus. The route this entry called
promising-but-unbuilt is what shipped: `kb.py candidates` blocks, an agent
judges, `kb.py judge` records the verdict.

Read the two together. This entry is why the *threshold* on `dupes` is where it
is; the other is why a second command exists beside it.

**The guard.** `TestDupes.test_a_paraphrase_is_not_flagged` pins this finding as
a regression test: it asserts the paraphrase is *not* reported. If a future
session lowers the threshold to "catch more", that test fails and this entry
explains why it was set where it was.
