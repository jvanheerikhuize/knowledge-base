---
name: kb-ranked-retrieval
type: semantic
description: retrieval ranks with BM25 plus three memory-specific signals (type, episodic-only recency, confidence), and `kb.py context` packs the result into a token-budgeted brief with provenance
confidence: verified
source: scripts/kb.py rank()/context_pack(); implemented and tested 2026-07-27
created: 2026-07-27
last_verified: 2026-08-10
links: [kb-is-file-based, kb-entry-status-model, kb-agent-entrypoint-is-agent-md, kb-forgetting-model, kb-duplicate-detection-limits, kb-roadmap, persist-insight-to-knowledge-base, kb-golden-set-lives-in-the-wording, kb-context-budget-is-not-a-pack-size, kb-a-constant-query-has-a-ceiling]
---

The store is deliberately infra-free (see [[kb-is-file-based]]), so a vector
store is off the table. That turns out not to cost much: the corpus is a few
dozen files, so scoring **every** entry on every query is free and needs no
index at all. Classic BM25 (`k1=1.5`, `b=0.75`) is ~40 lines of stdlib.

Generic IR is not enough on its own, though. Three signals specific to a
*memory* store sit on top of the BM25 score:

| Signal | Why it exists |
|---|---|
| Field weighting (name ×3, description ×2, body/meta ×1) | a term in an entry's name says what the entry *is about*; the same term buried in the body may be an aside. Applied by repeating tokens, which leaves BM25 itself unmodified |
| Type prior | a procedure or a durable fact answers "what do I need to know" better than a `working` scratch file or a `parametric` boundary doc |
| Recency — `episodic` only | a log entry decays in usefulness; a fact does not. Applying recency store-wide would quietly punish exactly the entries meant to be timeless. Half-life 90 days |
| Confidence | a small multiplier (0.88–1.10) that reorders near-ties. Deliberately too small to let a trusted-but-irrelevant entry outrank a real match |

Each of those three is a design argument, not a measured gain, and as of
2026-08-02 it is known to be unmeasurable here: ablating the type prior, the
recency term, or the confidence multiplier moves retrieval quality by about
one query on the 29-query golden set, which is inside the noise band
([[kb-golden-set-lives-in-the-wording]]). They are kept because they are cheap
and principled, not because anything shows they help — and the same
measurement says the field weighting's *implementation* has a real cost:
repeating tokens inflates term frequency before BM25 saturates it, so `k1=1.5`
is effectively mistuned for this scorer. Not corrected, because the fix is not
distinguishable from the bug at this store size; the numbers are in ROADMAP
Phase 7.

`kb.py context "<task>"` is the command an agent should reach for first. It
runs the same ranking and packs the result into a paste-ready brief under a
token budget (`--budget`, default 2000, estimated at 4 chars/token — no
tokenizer, no dependency). Two decisions there matter:

- The entry that straddles the budget boundary is **trimmed at a paragraph
  break, not dropped**, so a pack always fills the budget it was given. The
  trim marker is charged against the same budget, so it never overshoots.
- Episodic is **excluded by default**. One past run crowds out durable
  knowledge; `--episodic` opts back in.

**How many entries that buys is not fixed, and falls as entries get longer**
— 5.14 per pack on 2026-07-27, 2.75 on 2026-08-09, with the budget unchanged
throughout. Measured 2026-08-10; the mechanism is entry length alone, and no
rank metric above can see it because none has a budget term
([[kb-context-budget-is-not-a-pack-size]]). A pack now reports whether it
stopped on the budget or on matches, and `kb.py eval` scores `recall_at_pack`
next to the rank numbers.

Every entry in a pack carries its own provenance line — confidence,
`last_verified`, and source path — so nothing enters an agent's context
unattributed, and a reader can tell a `verified` fact from an `unverified`
one without leaving the pack. That ties retrieval to the status model in
[[kb-entry-status-model]]: freshness is not just a maintenance concern, it
travels with the fact.
