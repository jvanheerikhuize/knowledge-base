---
name: kb-consolidation-is-owed-work
type: semantic
description: a curated store accumulates overlap, not duplicates — 87 verdicts, zero duplicates, and the real defect was seven overlapping pairs with no link between them, which lint cannot see because a missing edge is a property of a pair
confidence: verified
source: measured 2026-07-31 against this store's own .kb/verdicts.json plus 7 planted restatement passages; scripts/kb.py consolidation_report()/restatements(), tests/test_kb.py TestConsolidate
created: 2026-07-31
last_verified: 2026-08-21
links: [kb-duplicate-candidates-by-nearest-neighbour, kb-duplicate-detection-limits, kb-contradiction-is-a-second-axis, kb-entry-status-model, kb-roadmap, distill-session-into-memory, kb-corrections-happen-in-place, kb-a-blocker-must-remember-its-rulings, kb-a-verdict-expires-faster-than-it-is-written]
---

`kb.py consolidate` was scoped as "propose merges", queued off the pairs
standing at `duplicate`. **That queue is empty, and structurally likely to stay
empty.** Across two full judging passes this store recorded 87 verdicts: 44
`overlap`, 43 `distinct`, **zero duplicates**. A store curated by an agent that
judges pairs as it writes them does not accumulate duplicates. It accumulates
overlap.

**The defect was inside the overlap bucket, and nothing else could see it.**
`kb.py judge` prints "link them if they are not linked yet" once, when the
verdict is passed — and then the pair settles and drops out of `candidates`
forever, so the advice is given exactly once and never checked again. Seven of
the 44 overlapping pairs had no edge between them. Every one was a real
relation; all seven are now drawn.

`lint` cannot find this and should not be changed to try. Lint catches links
that point *nowhere* and entries that *nobody* links to — both properties of a
single entry, both computable from one file. A missing edge between two
well-connected entries is a property of a **pair**, and the only thing that
knows the pair is real is the verdict ledger. That is the general shape:
*a judgement recorded and not acted on is invisible to every check that reads
one entry at a time.*

**The sub-entry half needed its own metric.** "This paragraph restates another
entry" is not findable by the measure [[kb-duplicate-detection-limits]] uses.
Seven hand-written restatements were planted in a copy of the store, each a
paragraph in one entry restating a *different* entry's claim in different
words. Over 2728 (passage, entry) pairs:

| signal | pairs it puts up | caught |
|---|---|---|
| passage shingle-containment, best entry | 20 (0.7%) | 1 of 7 |
| passage as a BM25 **query**, best entry | 124 (4.5%) | **7 of 7** |
| …that also beats its own host, passage removed | 72 (2.6%) | **7 of 7** |
| …and clears a 1.5× margin over the runner-up | **28 (1.0%)** | **7 of 7** |

Containment fails one level down for the same reason it failed at whole-entry
scale: shingles measure shared *phrasing*, which is exactly what a restatement
does not share. Asking instead "of everything here, which entry is this
paragraph most like" is the framing that rescued duplicate detection in
[[kb-duplicate-candidates-by-nearest-neighbour]], applied to passages.

**The host filter is the new idea.** A passage is worth reading only if it
scores higher against another entry than against **its own entry with that
passage removed** — a paragraph more at home somewhere else than where it is
written. The removal is load-bearing, not a refinement: leave the passage in
and its host wins trivially, every time.

**What the margin costs, stated plainly.** The default 1.5 held the planted set
at full recall but dropped the one real case this store already knew about —
`persist-insight-to-knowledge-base` steps 3–5 restating
[[distill-session-into-memory]]. Those steps *are* found (they beat their own
host) but the runner-up sits close, because procedure steps share vocabulary
(`kb.py new`, lint, triage) with half the store while distinctive prose does
not. `--margin 1.0` surfaces them, at 63 passages to read instead of 22. The
planted positives were topical prose and the default is tuned to them. That is
a real limit on the default, not a rounding error — **when looking for a
restated procedure, lower the margin.**

**First full pass, 2026-07-31.** Seven missing edges drawn. Of 22 restatement
proposals, two were real: [[kb-roadmap]] was retelling the whole
contradiction-detection finding that [[kb-contradiction-is-a-second-axis]]
exists to hold, and the `persist`/`distill` case above. The other 20 are an
entry legitimately discussing its neighbour, which is what a blocker is
supposed to produce — it narrows and then refuses to rule, exactly as
`candidates` does.

Rewriting those three entries expired 26 verdicts and reopened them for
re-judgement. That is the design working rather than a cost to route around: a
verdict is bound to a digest of the text it was passed on, so consolidating an
entry necessarily reopens every claim made about it.

**And that binding is the half this entry got right, on a queue it never
applied it to.** The two verdict-derived queues above settle, because a
judgement is written down. The restatement queue had nowhere to write one, so
the twenty proposals read and left alone on 2026-07-31 came back on every run
after it — six of them still standing, byte-identical, twenty-one days later.
Measured across the store's history the queue re-proposed 90% of what it had
already put up, and its whole yield is the two positives above.
[[kb-a-blocker-must-remember-its-rulings]] carries the measurement and the
repair: `kb.py dismiss`, keyed on the passage rather than on the pair, because
a pair-shaped key cannot say which of a dozen passages was the one read.
