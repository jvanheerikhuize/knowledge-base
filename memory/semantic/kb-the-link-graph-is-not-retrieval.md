---
name: kb-the-link-graph-is-not-retrieval
type: semantic
description: no ranker follows an edge, and at this store's shape none should — the link neighbourhood is 3.2x the context pack, so following one displaces a better bet than it adds
confidence: verified
source: ROADMAP Phase 24 (2026-08-24) — 190 edges scored against the 42-query golden set, plus a replay of all 53 commits that have touched memory/ with the ranker, golden set and clock held fixed
created: 2026-08-24
last_verified: 2026-08-24
links: [kb-context-budget-is-not-a-pack-size, kb-ranked-retrieval, kb-entry-status-model, memory-overview-site, kb-consolidation-is-owed-work, kb-golden-set-lives-in-the-wording]
---

`kb.py rank` scores BM25 plus memory type, confidence and recency.
`context_pack` fills a token budget from that ranking. **Neither reads
`links`**, and no MCP tool does either. The consumers of an edge are the
site's "Links out" / "Linked from" panes, `consolidate`'s missing-edge queue,
`lint`'s orphan warning, and `rm`'s refusal to delete something still linked.
Retrieval is not among them.

That was not what the store said. Until 2026-08-24 `kb.py status --legend`
and `memory/AGENT.md` both defined an `isolated` entry as one that "will not
be found by following the graph" — a retrieval consequence, in a status model
whose neighbouring rows are defined in exactly those terms (`archived` is
"retired from retrieval"). Both are corrected, and
`tests/test_link_graph_is_not_retrieval.py` now pins the claim behaviourally:
strip every `links:` value from the store and ranking and packing come back
bit-identical.

## The graph is not noise, which is why this needed measuring

Two facts that sound contradictory and are both true.

**The edges carry information the ranker does not have.** Ranked by the same
token-set similarity `candidates` blocks on, **114 of 190 edges (60%) are not
among either endpoint's three nearest neighbours**; the median edge sits at
rank 5 and the worst at 41 of 48. A nearest-neighbour pass would never
propose them.

**And the edge predicts the answer.** Over the 19 golden queries whose top hit
is wrong, among every other entry that scored: `P(right answer | linked to the
top hit) = 10/144 = 0.069` against `12/723 = 0.017` for the rest — a **4.2x
lift, Fisher exact one-sided p = 0.0013**.

## And it is still the wrong grain

A 6.9% hit rate has to win a slot from an incumbent. The entry a boosted
neighbour displaces is the rank-2 hit, which is the right answer **26.3%** of
the time — nearly four times as often. The arithmetic behind that is the whole
finding: **one hop names 7.76 entries and the pack holds 2.43**. Following an
edge is not selection at that ratio, it is flooding.

Measured end to end, one hop from the top hit, boost sweep 1.25x → unbounded,
against `recall@pack` on 42 golden queries:

| budget | mean pack | baseline | boost 2x | Δ | 95% CI |
|---|---|---|---|---|---|
| 2,000 (shipped) | 2.43 | 0.714 | 0.690 | **−0.024** | [−0.119, +0.071] |
| 6,000 | 5.86 | 0.762 | 0.786 | +0.024 | [−0.048, +0.095] |
| 9,000 | 8.14 | 0.786 | 0.833 | +0.048 | [+0.000, +0.119] |
| 12,000 | 10.81 | 0.833 | 0.833 | 0.000 | — |

It turns positive only where the pack is large enough to hold the whole
neighbourhood, and washes out again above that, where the budget alone already
returns the answer. Two hops never helps at any budget: the 2-hop
neighbourhood is 31.1 entries, 62% of the store.

The ceiling was checked separately and is not the binding constraint: of the
12 golden queries the pack misses, **7 are one hop from something in the pack**
and 5 from the top hit. The reachable population exists. Precision is what
fails.

## It used to pay, and the date is exact

Replaying all 53 commits that have touched `memory/`, with the ranker, the
golden set and the clock frozen at today's values, the neighbourhood/pack
ratio runs **0.51 (2026-07-27) → 1.05 (2026-07-28) → 2.08 (2026-08-03) →
3.19 (today)**, and the measured gain tracks it inversely (r = −0.36).
(Every figure here is the store as measured, at 49 live entries. Filing this
entry and its six edges takes the neighbourhood to 7.84 and the ratio to
3.23 — the direction, again.)

| ratio | replay points | points where expansion gained | mean Δ recall@pack |
|---|---|---|---|
| below 2.0 | 25 | 12 | **+0.032** |
| 2.0 and above | 28 | 2 | **−0.015** |

Fisher exact one-sided **p = 0.00088**. The last commit at which a 2x link
boost improved the pack is **2026-08-03**, the same day the ratio first
reached 2.0.

Store size and the ratio move together across that replay, so the replay alone
cannot separate them. The budget sweep above does: it holds the store fixed at
today's 49 entries and moves only the pack, and the sign follows the pack.
**The variable is the ratio, not the size.**

## Both curves were already known separately

`kb-context-budget-is-not-a-pack-size` measured the pack falling from 5.14 to
2.75 entries as write-ups got longer, with the budget never touched.
`kb.py stats` has always printed links-per-entry, which has been rising. Each
number had a home; nothing put them in the same fraction. `kb.py eval` now
reports `link_neighbourhood` and `neighbourhood_over_pack` beside
`mean_pack_entries`, and says what past 2.0 means — reported, never gated, the
same call `budget_bound` and `judgement_load` make.

**Nothing was shipped that follows the graph.** The reopen condition is in
`ROADMAP.md`: the ratio back under 2.0 — which today means
`DEFAULT_CONTEXT_BUDGET` at 6,000+, and that is Jerry's call, not a routine's,
for the reason Phase 13 already recorded.

## What an edge is actually for

Not retrieval. It is navigation for a reader on the site, and it is the
substrate `judge` and `consolidate` reason over — a judged `overlap` with no
edge is the defect `consolidate`'s LINK queue exists to catch. `isolated` is
still worth clearing. It is just not worth clearing *for search*, and the
store said otherwise for four weeks.
