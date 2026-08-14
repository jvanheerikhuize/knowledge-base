---
name: kb-capture-is-a-check-not-an-extractor
type: semantic
description: an entry's one-line claim is not recoverable even from its own body (1 of 30) — the claim is synthesised at write time, so distillation from a transcript has nothing to extract, and kb.py capture checks what you wrote against the store instead
confidence: verified
source: ROADMAP Phase 6 measurement, 2026-08-03
created: 2026-08-03
last_verified: 2026-08-14
links: [kb-consolidation-is-owed-work, kb-duplicate-candidates-by-nearest-neighbour, kb-corrections-happen-in-place, kb-is-file-based, distill-session-into-memory]
---

ROADMAP Phase 6 proposed `kb.py distill <transcript>`: extract candidate
atomic facts from a session log into staged drafts for review. The gap it
named is real — capture depends on remembering to capture. The mechanism is
not, and the store's own text says so before any of it is built.

## The claim is not in the material

The control bounds everything else. For each of the 30 entries, ask whether
its one-line `description` can be recovered from **its own body** — the text
the description was written to summarise, the most favourable corpus that
could exist. Coverage is the share of the description's content words present
in the best-matching candidate sentence.

| candidates drawn from | mean coverage | entries ≥ 0.5 |
|---|---|---|
| the entry's own body (control) | 0.290 | 1 / 30 |
| session material: code + tests | 0.224 | 2 / 30 |
| session material: ROADMAP/DEBRIEF prose | 0.297 | 9 / 30 |
| commit message alone | 0.269 | 3 / 30 |
| all session material together | 0.408 | 11 / 30 |

**No sentence in an entry says what the entry says.** A description is a
synthesis produced at write time; extraction cannot recover it because it was
never in there. Ground truth was the 19 commits that created an entry, with
each entry excluded from its own session's material.

The one corpus that beats the control beats it by being five times larger and
by containing ROADMAP and DEBRIEF paragraphs — prose a person or an agent had
already distilled by hand, in that same session. Extraction scores well
exactly where the work was already done.

## A transcript is not the material either

A real Claude Code transcript (this session's: 275,094 characters, 267 blocks)
is 53.3% tool results, 31.4% tool call inputs, 10.5% attachments and system
reminders, and **0.7%** the assistant's own prose. The reasoning is **0
bytes**: `thinking` blocks persist with their content stripped and only a
signature left, so the model's deliberation is cryptographically unavailable
to any later reader of the file.

And the agent that would run `distill` is the agent that still has the session
in context. It does not need extraction. It needs somewhere to put what it
already knows, and a check that it is not writing something the store holds.

## What shipped instead

`kb.py capture` (CLI and MCP tool) takes a claim **you wrote**, in your words,
and runs the check `memory/AGENT.md` has always asked an author to perform by
hand: which entry does this already belong to? Two measurements set its
behaviour, and neither introduced a new constant:

- **The restatement test transfers to a claim with no host.** Scoring the
  passage as a BM25 query over every entry is `restatements()` minus the host
  term. Fed a true restatement (each entry's own description handed back), the
  top-ranked entry is the source entry **30 of 30**, and the existing
  `RESTATEMENT_MARGIN` of 1.5 fires **29 of 30** — never on the wrong entry.
  Fed a genuinely new claim (each entry held out of the corpus first), it
  fires **7 of 30**, and all 7 name an entry the author had linked to. A fire
  is never noise: it is the entry being restated, or the entry to link to.
- **Only the top neighbour is prefilled as a link.** Against the 132 hand-set
  links here, the top-ranked neighbour of an entry's body is an edge its
  author drew **70%** of the time, falling to 51% by rank 3. The rest are
  printed, not written: a wrong edge is read by `candidates`, `consolidate`,
  and the graph.

`--check` reports and writes nothing. `--type` with `--name` files the passage
as `confidence: unverified`, its first sentence as the description.
`--extend NAME` appends it to the entry that already holds the claim, which is
the point of checking first. Writes are staged, never committed.

The margin is an extra, not the signal — the rank is. A paraphrase written
specifically to defeat lexical overlap ranks its target first but clears 1.5
only in a store large enough to have a runner-up worth beating, and the test
suite asserts that rather than lowering the margin to force it.

## Why this shape and not a review gate

The backlog's warning was that a store fills with restated context, and its
answer was a review gate behind an extractor. A gate on a pile of candidates
gets reviewed the way all such gates get reviewed. Making *"you are restating
[[kb-consolidation-is-owed-work]]"* the first line of output puts the same
judgement where it is cheap and unavoidable.

This is the fourth phase running where measuring the store first showed the
proposed mechanism to be the wrong shape — [[kb-corrections-happen-in-place]]
is the closest sibling, where obsolescence turned out to have no interval, so
validity intervals had nothing to describe. The pattern is strong enough to
state plainly: **measure the store before building for it.**
