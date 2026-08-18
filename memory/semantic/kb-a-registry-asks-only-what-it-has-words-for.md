---
name: kb-a-registry-asks-only-what-it-has-words-for
type: semantic
description: the archived-axis registry demands one policy word per store-scanning function, but `rank` decides `archived` twice — once for its results and once for its corpus statistics — so the registry certified the half nobody doubted and never asked about the other
confidence: high
source: ROADMAP Phase 18, 2026-08-18 — measured against the live store and verified by mutation
created: 2026-08-18
last_verified: 2026-08-18
links: [kb-tests-cannot-cover-an-absent-guard, kb-archived-is-a-filter-commands-forget, kb-ranked-retrieval, kb-a-fitted-golden-set-starts-perfect]
---

`tests/test_archived_axis.py` (2026-08-07) exists because three commands shipped
with a missing `archived` guard and no test could have caught them: you cannot
mutate a line that is not there, so the repair was an *enumeration* — discover
every store-scanning function by AST, and fail when one declares no policy.

It works, and it still certified a decision nobody had made. `rank` declares
`EXCLUDES`. That is true of its **results**. Its corpus statistics — `n`, `df`
and `avgdl` — come from `entry_documents()`, which declares `INCLUDES`, so the
same call weighs every candidate against a set of documents it will not return.
Both statements are true of the same function; `SCANNER_POLICY` has one slot per
function, and the slot means *output membership*. So it recorded the half that
was never in doubt and reported the function as compliant.

**The lesson is one level above the module's own.** Enumeration fixes coverage
that cannot see absent code. It does not fix a schema that cannot phrase the
question: a registry asks only what it has words for, and a function that reads
the store for *weights* rather than for *results* had no word. The gap survived
eleven days inside the test module built to end exactly this kind of silence.

Two consequences that were live, undeclared, and are now both declared:

- The store has **two BM25 corpora and they disagree**. `rank` weighs against
  `entry_documents()` (43 documents, archived included); `_bm25_scorer` — behind
  `dupes`, `candidates`, `restatements` and the `capture` restatement check — is
  fed from `_candidate_docs()` (42, archived excluded, and additionally dropping
  anything under `MIN_CANDIDATE_TOKENS`, a second corpus rule with an empty
  domain today). `kb.py search` and `kb.py capture` do not weigh terms the same
  way.
- The whole-store corpus buys two invariants nothing tested. **Filter
  independence:** a live entry's score is identical under `types=`,
  `include_episodic=False` and `include_archived=True` (42 of 42 golden
  queries), so two searches are comparable and `context_pack` can fill a budget
  by comparing scores. **Archive neutrality:** archiving reorders nothing for
  the entries that stay (0 of 42 orderings; scores move 0.001, from the archived
  date's own tokens shifting `avgdl`).

That second invariant is the reverse of what ROADMAP Phase 17 recorded, and the
reversal is the practical warning here. Phase 17 wrote that archiving "silently
reweights every other entry's score" and put it on the reopen table as a defect
awaiting a bigger archive. Under the shipped corpus archiving reweights nothing;
the *proposed fix* is what would make archiving a store-wide score event. The
row named the cure as the disease, and it had a plausible mechanism, so nothing
about reading it would have caught that.

Measured before deciding, because the row claimed the effect grows. Holding the
candidate set fixed and growing only the corpus, the share of queries whose top
hit changes goes 0% → 8.2% by ten extra documents and then flattens (10.0% at
22); the expected entry moves a third of a rank position. Paired over golden
queries at three archive sizes `success@1` moves +0.006, +0.009, −0.003 — sign
flipping, two of three CIs straddling zero. It is real, bounded, saturating, and
directionless: **no measurement can pick a winner, which is precisely why the
choice has to be written down instead of measured again.**

So `CORPUS_POLICY` shipped and the corpus did not change. Discovery is
mechanical and separate from the first registry's — a scorer is any function
carrying both an `idf` and an `avgdl` name, with no transitive closure, because
a caller passing `docs=` picks a corpus but does not build the statistics.
Verified by mutation: making the corpus follow `include_archived` kills both
invariant tests; adding an undeclared scorer kills the discovery test.

**The generalisable form, for the next registry:** when adding one, ask what
*kinds* of decision the enumerated thing makes, not just which things to
enumerate. A row per function is complete only if a function makes one decision.
[[kb-tests-cannot-cover-an-absent-guard]] records the condition for building a
second registry (a fourth instance of a defect class on a new axis); this was
not that. It is the same axis, undeclared in a dimension the schema lacked — so
the repair was a second field, not a second registry.
