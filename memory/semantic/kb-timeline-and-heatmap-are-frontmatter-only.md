---
name: kb-timeline-and-heatmap-are-frontmatter-only
type: semantic
description: the site's timeline and type×status heat map (ROADMAP Phase 8) read only created/last_verified/status from entries, never git — the Pages checkout is depth-1, so a git-derived view would render every entry as never having changed
confidence: verified
source: scripts/build_site.py build_timeline(), 2026-08-03
created: 2026-08-03
last_verified: 2026-08-14
links: [kb-corrections-happen-in-place, memory-overview-site, kb-instruction-content-lint]
---

ROADMAP Phase 8 was marked `someday` and scoped as execution, not research:
three views over data `kb.py stats` and `status_report()` already compute.
Unlike Phases 4–10, there was no proposed mechanism to measure against — the
one thing worth checking before building was already on record in
[[kb-corrections-happen-in-place]]: `.github/workflows/pages.yml` checks out
the repo at depth 1, so `git log` is unavailable to the build and anything
timelined from it would be silently wrong on the published site, not merely
absent. `kb.py history` hit this and stayed off the site for the same reason.

## What shipped

`timeline.html`, built from `build_site.collect()`'s existing per-entry
`created`, `last_verified`, and `status` fields, nothing else:

- **Growth by month** — a bar per `created` month, widths relative to the
  busiest month. Answers "when did this store grow," which git could also
  answer, but frontmatter already carries it without a deep checkout.
- **Type × status heat map** — a grid, rows by memory type, columns by the
  `status_report()` status (`current`, `stale`, `ageing`, ...), cell shaded by
  count via an alpha-blended background (`_rgba`, not CSS `opacity` — opacity
  would have faded the count text along with the fill and made high-decay
  cells the hardest to read). This is the "staleness/confidence heat map" the
  backlog asked for: `status` already collapses confidence *and*
  `last_verified` age into one value per entry, so the grid needs no second
  metric alongside it.
- **Events** — every `created` and every distinct `last_verified` as one row,
  newest first, since the store has no other newest-first view of "what
  happened when" without reading `.kb/log.md` or git (`changes.html` already
  covers mutations; this covers content dates).

Saved searches shipped alongside on the index page: the search box and type
chips now sync to `?q=`/`?type=` via `URLSearchParams` and
`history.replaceState`, plus a "Copy link" button, so a filtered view of the
index is a URL, not a sequence of clicks someone has to redo.

## What this does not do

No new measurement — `status_report()` is the same decay signal
[[kb-corrections-happen-in-place]] and [[kb-instruction-content-lint]] already
rely on. Not tested against real users; "visible at a glance" was judged by
reading the rendered page, not measured. ROADMAP Phase 8 is closed; ROADMAP
Phase 9 (cross-repo integration) is next and needs sibling-repo access this
routine does not have (see `sibling-repo-access-denied-in-routines`).
