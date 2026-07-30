---
name: kb-contradiction-is-a-second-axis
type: semantic
description: no cheap signal detects contradictions between entries — measured, the best of three candidate detectors caught 5 of 9 — but the nearest-neighbour blocker built for duplicates already surfaces 8 of 9, so contradiction shipped as a second axis on the existing verdict rather than as a new detector
confidence: verified
source: measured 2026-07-30 against the live 22-entry store plus 8 planted contradictions and 1 recovered from this repo's git history; scripts/kb.py AGREEMENTS/standing_contradictions, tests/test_kb.py TestContradictions
created: 2026-07-30
last_verified: 2026-07-30
links: [kb-duplicate-candidates-by-nearest-neighbour, kb-entry-status-model, kb-forgetting-model, kb-duplicate-detection-limits, kb-over-mcp]
---

`memory/AGENT.md` said for months that lint "does not detect content-level
contradictions between entries — no such checker exists yet." It still does not
detect them, and now it says why: **there is no detector worth building.** What
shipped instead is a second question asked of pairs the store was already
putting in front of an agent.

**What was measured.** Nine contradictions were planted in a copy of the live
store — eight hand-written (a capability flipped, a count changed, two
documents each claiming authority, a mechanism described backwards) and one
real, recovered from git: the pre-correction `kb-duplicate-detection-limits`
against the entry that overturned it. Three candidate signals were scored
against them.

| signal | pairs it puts up | contradictions caught |
|---|---|---|
| global topical similarity | positives land at **#2 to #107** of 435 | no usable cut |
| claim-level sentence alignment | 10 pairs (2% of the space) | **4 of 9** |
| negation-polarity mismatch | 12 pairs (3%) | **5 of 9** |
| **the existing `candidates` blocker, `-n 3`** | 62 pairs (14%) | **8 of 9** |
| the existing `candidates` blocker, `-n 5` | 103 pairs (24%) | **9 of 9** |

**Why the two cheap detectors fail matters more than that they fail.** Polarity
mismatch cannot see the commonest shape of disagreement at all: two competing
*positive* assertions — "20 repos" against "22 repos" — where no negation
appears on either side. Its false positives are negation-scope errors ("this is
**not** just a preference" is agreement, read as conflict) and pairs that agree
*about* a contradiction located somewhere else. Claim-level alignment is tight
but blind for the reason [[kb-duplicate-detection-limits]] already established
one level up: two entries rarely word the same claim the same way, and a single
sentence is too short for the overlap to survive rephrasing.

**The structural difference.** Duplication is a *whole-entry* relation;
contradiction is a *sub-claim* relation — one line inside a long entry against
one line inside another. That is why the same blocker needs a wider net here
(`-n 5`, 24% of the pair space) than the 5% that caught 7 of 7 paraphrases in
[[kb-duplicate-candidates-by-nearest-neighbour]]. The single positive missed at
`-n 3` was exactly that shape: a short claim contradicting one line of a long
episodic sweep, whose nearest neighbours are other long sweeps.

**So the shipped thing adds no detector.** `kb.py judge` gained
`--agreement agree|contradict`, an axis independent of
`duplicate|overlap|distinct`. The first says how much two entries say the same
thing; the second says whether they can both be true, and a pair can restate
*and* disagree. Standing contradictions become a `contradiction` triage reason
and the `contradicted` status, placed above `broken` — every other status means
nobody has checked, this one means somebody checked and the store is wrong. It
is deliberately **not** a lint failure: lint checks form, and whether two claims
can both be true is not form.

**Absence is recorded as absence.** A verdict with no agreement stores no key,
so the 46 verdicts written before the axis existed read as *unexamined* rather
than as *fine*, and every one of them came back into `candidates` marked "never
checked for contradiction". That re-opening is why `record_verdict` now keeps an
existing note when none is supplied: the second pass would otherwise spend the
first pass's reasoning to buy its own. It did, once, before that was fixed.

**First full pass, 2026-07-30 — 75 pairs judged at `-n 5`, one real
contradiction.** [[kb-entry-status-model]] said every entry sits in one of
**eight** statuses and its table omitted `archived`; [[kb-forgetting-model]]
said archiving gives an entry its own `archived` state on the board. Both could
not be true. It had stood for two days — since `archive` shipped 2026-07-28 —
through a full duplicate-judging pass, a lint run, and a clean triage, because
nothing had ever asked. Reconciled by correcting the older entry, which now
carries the ten-status table.

**The yield argument, which is the reason to keep asking.** The same 45 pairs
read for duplicates on 2026-07-29 returned **zero** duplicates. Asked the second
question, they returned a real defect. A pair already blocked is nearly free to
ask twice, and the second question is the one with answers in it.
