---
name: kb-review-load-is-one-cohort
type: semantic
description: every live entry was verified inside one 8-day window of a 90-day cycle, so the store's whole review load lands together (2026-10-26 → 2026-11-03) and confidence decay — which needs differential age — changes no ranking at all; kb.py status and stats now forecast the pile-up
confidence: verified
source: scripts/kb.py (review_forecast, effective_confidence), measured against the real store 2026-08-05, ROADMAP Phase 11
created: 2026-08-05
last_verified: 2026-08-05
links: [kb-forgetting-model, kb-entry-status-model, kb-ranked-retrieval, kb-golden-set-lives-in-the-wording, kb-corrections-happen-in-place, memory-overview-site, kb-the-bundle-was-already-shipped]
---

This store was written in nine days. Every one of its 32 live entries carries a
`last_verified` date inside an **8-day window**, and the review cycle is
`STALE_DAYS = 90`. The store is therefore not a population with a spread of
ages; it is **one cohort**, and almost everything that follows from age is
distorted by that.

**The consequence is dated arithmetic, not a worry.** Replaying the store's own
dates forward with nothing else changing: `current` empties on **2026-10-04**
(all 32 entries ageing at once), the first entry goes stale on **2026-10-26**,
and by **2026-11-03** every live entry is stale and the triage queue has gone
from 0 items to 32. The queue holds at most **two distinct severities**, so its
ordering degrades to alphabetical — 32 rows that all look equally urgent, which
is the same as none of them being urgent.

**Decay needs differential age, and there is none.** `effective_confidence`
demotes a level per elapsed `STALE_DAYS`, and `rank()` multiplies the BM25 score
by the weight of the *decayed* level. When every entry decays on the same day,
that multiplier is a near-global constant and changes no ordering. Measured
rather than argued: the golden set was scored against the store at +0, +45,
+90, +135, +180, +270, +360, +450, +540 and +720 days, with decay on and with
decay removed entirely — **identical at every offset** (success@1 0.517, MRR
0.634 from +45 onward; the small move between +0 and +45 is episodic recency,
which is a different signal and shows in the decay-off column too). 30 of 32
entries share one stored level, so the only ranking effect decay can have is on
the 2 that do not — and from **2027-07-30** even that is gone, because five
confidence levels clamp at `unverified` and the whole store sits there
permanently. A store nobody re-verifies ends with the decay signal switched
off, which is the opposite of what it is for.

The narrow claim matters: decay's *ranking* term is inert here. Its *display*
is not — `[verified -> high, aged]` in search and context packs still tells a
reader the fact is old, and that is unaffected by the cohort. See
[[kb-forgetting-model]].

**The obvious repair makes it permanent.** Re-verifying the store in one sweep
sets every `last_verified` to the same day: the window goes from 8 days to
zero, and the identical pile-up returns exactly one cycle later, forever. The
fix that works is the opposite — re-verify in batches on different days, which
is honest because the check really did happen on the day it is dated.

**What was not built, and why.** Two repairs were rejected on evidence:

- *Stagger the dates.* `last_verified` is a record of when somebody looked. It
  cannot be jittered without lying. A separate per-entry review interval would
  be a frontmatter field with an empty domain — the mistake ROADMAP Phase 4
  already measured.
- *Prioritise the flat queue.* Nothing in this store can rank "worth
  re-checking". Its entire history contains **2 entries of 33** whose one-line
  claim was ever rewritten (`kb-entry-status-model`,
  `kb-duplicate-detection-limits`), and both were corrected within days by a
  later session's measurement — by work, not by the passage of time. Two
  positives cannot support a ranking signal, and the store is too young for the
  staleness clock to have caught anything yet.

So what shipped is a **forecast**, not a change to the model:
`review_forecast()` reports the window, the busiest day, and whether the shape
is a cohort; `kb.py status` ends with it, `kb.py stats` has a REVIEW LOAD
section, and it is published in `site/data.json` and on the status board. The
information was always determined — a review date is just `last_verified + 90`
— and no command reported it, so a store nine days from needing all of its
attention at once read as perfectly clean. See [[kb-entry-status-model]] for
what the board says about today.
