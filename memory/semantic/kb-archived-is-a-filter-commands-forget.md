---
name: kb-archived-is-a-filter-commands-forget
type: semantic
description: every store-scanning command handles `archived` with one guard at the top of its scan, but `kb.py lint` decides per check — so it remembered on two freshness warnings and forgot on the third, leaving an overdue warning no action could clear and a weekly strict-lint cron that would have gone red from 2026-08-10 forever
confidence: verified
source: measured 2026-08-06 in this repo; third instance of a defect class first recorded 2026-07-29
created: 2026-08-06
last_verified: 2026-08-06
links: [kb-forgetting-model, kb-entry-status-model, kb-prospective-memory-that-fires, kb-test-audit-2026-07-29, kb-review-load-is-one-cohort, audit-test-corpora-for-artificial-uniformity]
---

Archiving is how the store retires something on purpose
([[kb-forgetting-model]]): the entry stays readable and stays in the graph, it
just leaves the retrieval set. Every command that scans the store therefore has
to decide what `archived` means to it. Almost all of them make that decision
**once**, in one place, and this entry is about the one that doesn't.

## The shape that works

Seven scanning functions open their per-entry loop with the same two lines:

```
if is_archived(fm):
    continue
```

`dupe_pairs`, `_candidate_docs`, `rank`, `eval_report`, `triage_report`,
`due_report`, `review_forecast`. Two more handle it deliberately rather than by
skipping — `status_report` assigns the `archived` status, which short-circuits
every other status candidate ([[kb-entry-status-model]]), and `stats_report`
counts archived entries as their own bucket. Either way it is **one decision per
command**, taken where the scan starts, visible in one place to anyone editing
the function.

`triage_report`'s comment states the principle exactly: *"Archiving is the
decision that an entry no longer needs attention. Continuing to flag it as stale
would make the queue un-clearable."*

## The shape that fails

`cmd_lint` is the exception, and structurally so. It is not one check — it is
about a dozen independent checks sharing a loop, so "skip archived" is not a
guard at the top but a clause each check has to carry for itself. Three of those
checks are attention-management warnings that an archived entry can never act
on. Two of them remembered:

```
# Freshness warnings are noise on an entry that was retired on
# purpose - archiving already answered "what about this one".
if age > STALE_DAYS and not archived: ...
if confidence == "unverified" and age > UNVERIFIED_DAYS and not archived: ...
```

The third did not. The overdue warning had no `archived` clause — and could not
easily have had one, because it ran *seventeen lines before* `archived` was read
from the frontmatter at all. The variable did not exist yet at that point in the
loop. Ordering, not intent, is what made the omission hard to see.

## What it cost, and the four-day margin

The store's one archived entry is `holiday-autonomy-mandate`, a prospective
entry archived 2026-08-05 per its own closing instruction — the textbook end of
a prospective entry's life ([[kb-prospective-memory-that-fires]]). Its `due`
date is 2026-08-05 and will be in the past forever. So `lint` emitted a warning
that the entry was overdue on every run, permanently, with no action available
that could clear it. Archive it — already done. Verify it — irrelevant to a due
date. Only deleting the entry or hand-editing its frontmatter would silence it,
and both destroy the record.

Under `--strict` a warning is fatal, and `.github/workflows/kb-lint.yml` runs
`kb.py lint --strict` on a weekly Monday cron. The failure had **not** fired
yet: on Monday 2026-08-03 the entry was still two days from due, so that run was
green. The first red run would have been **Monday 2026-08-10**, and every Monday
after. A scheduled session caught it with four days of margin, which is the
useful property of a lint that runs on a cadence *slower* than the thing it
watches — the defect is latent and findable in between.

## Third instance of one class

This is not a one-off. Twice before, a command missed the archived filter, both
times in a path where archived entries were rare enough that nobody hit it:

| date | command | symptom |
|---|---|---|
| 2026-07-29 | `kb.py dupes` | no archived filter where `candidates` had one, so an archived entry could be flagged a live duplicate ([[kb-test-audit-2026-07-29]]) |
| 2026-08-05 | `kb.py eval` | an archived expectation was still "answerable", scoring a guaranteed miss forever ([[kb-review-load-is-one-cohort]]) |
| 2026-08-06 | `kb.py lint` | overdue warning on an archived entry, un-clearable, fatal under `--strict` |

The common cause is not carelessness. It is that **a store with almost no
archived entries cannot exercise its own archived paths.** This store held one
archived entry out of 34 on the day all three bugs existed; every test that
covered these commands used a store with none. The filter is missed precisely
where the fixture is silent, which is why each instance was found by reading
rather than by a failing test.

That is [[audit-test-corpora-for-artificial-uniformity]]'s rule 2 —
*"a corpus that is accidentally uniform silently disables any code path that
only diverges under diversity"* — with `archived` as the uniform axis, and it is
now the third bug that procedure would have predicted. Worth noting the axis is
binary and skewed rather than categorical like the entry-type axis that
procedure was written from: no fixture has to *vary* archived-ness to look
reasonable, so the omission reads as normal test-writing every time.

The corollary for anyone adding a command that scans the store: put the
`archived` decision in the loop header where the other seven have it. If the
command genuinely cannot — because it is a bag of independent checks, like
`lint` — then read `archived` *first*, before any check that might need it, so
the omission is at least expressible.

## The fix

`archived` is now read before the prospective/due block rather than after it,
and the overdue warning carries `and not archived` like its two neighbours. The
malformed-date *problem* stays unconditional: a `due` value that is not a date
is a data-integrity error whether or not the entry is retired, and the same
split already governs `last_verified` (freshness warning suppressed on archived,
bad date still reported). Three regression tests, two of which fail against the
pre-fix code.
