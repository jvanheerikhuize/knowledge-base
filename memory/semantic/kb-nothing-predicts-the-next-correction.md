---
name: kb-nothing-predicts-the-next-correction
type: semantic
description: no signal in this repo picks the entry that gets corrected next — cited-artifact churn is indistinguishable from random and its refined symbol-level form is measurably worse, because churn keyed on last_verified is a coarsened age (84% the same picks) and what makes a claim wrong is almost never visible here
confidence: high
source: replay of all 20 commit-days over this store's history, five prioritiser arms scored against every claim/body edit within a 7d window, paired bootstrap over days (2026-08-16); ROADMAP Phase 16
created: 2026-08-16
last_verified: 2026-08-16
links: [kb-corrections-happen-in-place, kb-reverification-has-one-rate, kb-review-load-is-one-cohort, kb-verification-rides-along-with-authoring, kb-roadmap]
---

ROADMAP Phase 11 left a reopen row: build a **re-verification prioritiser**
when "the store has enough history for *worth re-checking* to be a measurable
property — today it is 2 claim rewrites across 33 entries." That condition is
now met — **6 claim rewrites across 41 entries**, plus 30 body edits across 20
entries — so the row was picked up and the question actually measured. The
answer is no, and the way it fails is worth more than the row was.

## What was measured

Every one of the 20 days on which this repo has a commit was replayed. At each
day the store was reconstructed from the tree, and five arms each named a set
of entries to re-check. An arm scored a hit when an entry it named received a
claim or body edit within the next 7 days — a deliberately generous ground
truth, since it counts extensions as well as corrections.

| arm | picks | precision | lift over base rate |
|---|---|---|---|
| base rate (any entry, any day) | — | 0.194 | 1.00x |
| `never_reverified` | 358 | 0.212 | 1.10x |
| **age** (oldest `last_verified` first) | 382 | 0.199 | 1.03x |
| random | 382 | 0.196 | 1.01x |
| **file-level cited-artifact churn** | 380 | 0.182 | 0.94x |
| **symbol-level cited-artifact churn** | 238 | 0.122 | **0.63x** |

Paired bootstrap over days (4,000 resamples, Δprecision against the random arm):
age `+0.002` CI `[-0.030, +0.034]`, file-churn `-0.015` CI `[-0.037, +0.006]`,
symbol-churn `-0.076` CI `[-0.121, -0.035]`. **The only arm that separates from
random is the most refined one, and it separates in the wrong direction.**

## Why churn looks clever and is not

A churn detector asks whether a file the entry cites changed *since its
`last_verified`*. That window grows with the entry's age, so the predicate is
monotone in age by construction: it is not a semantic staleness signal, it is
`sort by last_verified` with noise on top. Measured directly — **318 of 380
file-churn picks (84%) are entries the age baseline picked anyway**, and on the
live store the entries it fires on have a median age of 8d against 2d for the
ones it stays silent on.

Refining it to the symbol level makes it worse rather than sharper. It can only
fire on the 26 of 41 entries that cite a resolvable `def`/`class`/constant, so
silence on the other 15 is not evidence of freshness — it is absence of a key.
That is why narrowing the fire rate 78% → 38% bought a *drop* in precision:
what was discarded was age information, not noise.

## The reason no repo-observable signal can work

Classifying all six claim rewrites by what actually made the claim wrong:

- **1 rode along** — `kb-duplicate-detection-limits`, rewritten in the same
  commit that shipped `candidates`. Window zero; there was no day on which a
  detector could have fired.
- **1 was caused by another entry** — `kb-entry-status-model`'s status count,
  contradicted by `kb-forgetting-model`, not by any code.
- **3 were caused by state outside this repository** —
  `sibling-repo-access-denied-in-routines` (Jerry's GitHub grant) and
  `workspace-repo-inventory-drift` twice (a sibling repo's submodules and PRs).
  Nothing in this tree changed at all.
- **1 had a long window and the detector is blind to it anyway.**
  `kb-agent-entrypoint-is-agent-md` was correct while `.claude/CLAUDE.md`
  contradicted it for twelve days ([[kb-verification-rides-along-with-authoring]]).
  The entry's `last_verified` was `2026-07-27`; `.claude/CLAUDE.md` was last
  changed `2026-07-25`. **The cited file had not changed since the entry was
  verified, so churn was silent for the entire twelve days.** The defect was a
  file that had gone wrong and *stayed* wrong — the opposite of churn.

The generalisation: churn detects that an artifact *moved*. What retires a
claim here is an artifact being *wrong*, a claim elsewhere disagreeing, or the
world outside the tree changing — and the first of those is usually fixed by
the same commit that causes it ([[kb-corrections-happen-in-place]]).

## What follows

Do not build the prioritiser, and do not build the narrower version that looks
like the fix. The standing action's rule — oldest due first, one entry, at the
rate in [[kb-reverification-has-one-rate]] — is not a placeholder awaiting a
smarter selector. It is within noise of the best arm measured, and two of the
plausible smart selectors are worse than it.

This is also a caution about the shape of the mistake rather than its content:
both churn arms would have *looked* like they were working. They fire on
plausible entries, they fire more on older ones, and 84% of the time they name
what age would have named — so a session that shipped one and eyeballed its
output would have seen sensible-looking results from a detector adding nothing.
The only thing that separated them from the baseline was scoring them against
what actually got corrected.
