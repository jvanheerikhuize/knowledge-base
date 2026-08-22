---
name: kb-a-blocker-must-remember-its-rulings
type: semantic
description: the restatement queue re-proposed 90% of what it had already put up because it kept no record of what a reader had ruled on — a blocker that refuses to rule needs a ledger, bound to the passage rather than to the entries, or its cost grows with the store while its yield stays flat
confidence: verified
source: replaying restatements() over all 48 commits that have touched memory/ (1,098 proposal-instances, 107 distinct passages), the two acted-on restatements recovered from commit 99a1f26b, and a full read of all 57 proposals standing on 2026-08-21
created: 2026-08-21
last_verified: 2026-08-21
links: [kb-consolidation-is-owed-work, kb-duplicate-candidates-by-nearest-neighbour, kb-corrections-happen-in-place, kb-a-verdict-expires-faster-than-it-is-written]
---

`kb.py candidates` and the passage half of `kb.py consolidate` are the same
design: a **blocker** that narrows a huge space to a readable queue and then
refuses to rule, because deciding is a judgement someone makes by reading
([[kb-duplicate-candidates-by-nearest-neighbour]]). They shipped in the same
phase, on the same day. Only one of them was given a ledger.

`judge` writes its verdict to `.kb/verdicts.json` — the MCP tool's own
description says it is "so the judgement outlives your context and nobody
re-reads the pair" — and a settled pair leaves `candidates` until its text
changes. The passage queue got nothing, so **the only way to record that a
passage had been read was to remember it yourself, and no session outlives its
own context.**

## What that cost, measured

Replaying `restatements()` over all 48 commits that have touched `memory/`,
ranker and code held at today's version so only the store varies:

| | |
|---|---|
| proposal-instances the queue has put up | 1,098 |
| distinct passages behind them | **107** |
| instances that were a passage already put up at an earlier commit | **991 (90%)** |
| passages that have been in the queue at *every* replayed commit | 4 |
| of today's 57 proposals, first seen when the store held 10 entries | 5 |

The queue grew faster than the store it reads: 24 entries and 18 proposals on
2026-07-31, 45 entries and 57 proposals on 2026-08-20 — entries ×1.9, queue
×3.2, and the per-entry rate 0.75 → 1.27. Nothing about the signal changed. The
store simply writes more about itself over time, and every phase write-up
discusses and corrects its predecessors ([[kb-corrections-happen-in-place]]),
which is exactly the shape "this passage reads like another entry" is built to
find.

**The yield did not grow with it.** The 2026-07-31 pass read 22 proposals and
cut 2. Nobody had read the queue since. This session read all 57 and cut
**none**: every one is a correction notice recorded where the wrong claim was, a
paragraph citing the neighbour it argues against, or two entries on one subject.
Across the store's whole history that is **2 real restatements in 107 distinct
proposals** — and a 57-item re-read, every session, to find them.

That ratio is not an argument for deleting the queue. It is what a blocker is
supposed to look like: it is tuned for recall and most of what it surfaces is an
entry legitimately discussing its neighbour. It is an argument that the *reading*
must be incremental. With the ledger, a session reads what has appeared since
the last pass — 0 to 10 per commit across the replay, 3 on the most recent one —
instead of the whole queue.

## The obvious filter is refuted by the only ground truth there is

22 of the 57 proposals carry `mentions_target`: the passage already contains
`[[target]]`, which reads as "an entry merely discussing its neighbour" and is
an inviting way to cut the queue by 39%. **Both of the store's only two
acted-on restatements carry it.** Recovered from commit `99a1f26b`, which cut
them: `kb-roadmap` → `kb-contradiction-is-a-second-axis` (score 61.1,
`cites_target=True`), and step 3 of `persist-insight-to-knowledge-base` →
[[distill-session-into-memory]] (`cites_target=True`). 0 of 2 recall.

The mechanism is the store's own convention: you link what you discuss, so a
citation marks *aboutness* — which a restatement and a discussion share. The tag
is worth printing and must not become a filter; that is now written where the
code is.

The other tag was worse. `linked` — "already linked" — fired on **57 of 57**
proposals, and on every proposal at every commit since 2026-08-05. A tag that
never varies is decoration, so only its rare informative half is printed now:
*no edge between them*.

## The ledger's grain is the design decision

`.kb/verdicts.json` binds a verdict to both entries' content digests. Copying
that convention one level down is wrong in **both** directions, simulated over
the same 48 commits:

| binding | suppresses | fails how |
|---|---|---|
| passage text (shipped) | 991 of 1,098 | — |
| both entries' digests | 1,004 of 1,098 | hides **37** passages nobody dismissed (one ruling covers every other passage of the pair) and still re-presents **24** byte-identical passages because an unrelated paragraph of the host changed |

It suppresses *more*, which is the defect and not the benefit. Entries here are
corrected in place constantly, so an entry digest turns over for reasons that
have nothing to do with the paragraph being ruled on; and a pair here can hold a
dozen passages, so a pair-shaped key cannot say which one was read. Same axis,
wrong dimension — the shape [[kb-a-registry-asks-only-what-it-has-words-for]]
records one level up.

## What shipped

`kb.py dismiss <id> --note "<why it belongs here>"` (and MCP `dismiss`), writing
`.kb/passages.json`; `consolidate` prints an id per proposal, hides dismissed
ones, counts what it hid, and takes `--all`. A dismissal is the only ruling
recordable, deliberately: *acting* on a proposal means cutting the passage,
which changes its text and retires the proposal on its own. The note is warned
about when missing, on the same argument as `kb.py verify --note` — a record
that only says the queue got shorter cannot say whether anyone read anything.

The first pass is filed: all 57 dismissed with reasons, and `consolidate`'s
restatement queue is empty for the first time since the store had ten entries.
