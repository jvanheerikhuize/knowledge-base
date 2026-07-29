---
name: kb-test-audit-2026-07-29
type: episodic
description: a test-suite overlap/gap audit found two real correctness bugs (kb.py set on links, dupes not excluding archived entries) that no test had caught, not just missing coverage
confidence: verified
source: direct code reading of scripts/kb.py plus a subagent-driven read of all four test files (test_kb.py, test_mcp_server.py, test_build_site.py, test_serve.py) against their source files, 2026-07-29
created: 2026-07-29
last_verified: 2026-07-29
links: [holiday-autonomy-mandate]
---

Ran the "Test consolidation & audit" item from `AUTONOMY.md`'s backlog: read
all 231 tests (across `test_kb.py`, `test_mcp_server.py`, `test_build_site.py`,
`test_serve.py`) against the four source files they cover, looking for
overlap to consolidate and gaps to fill.

**What was expected**: mostly redundant test pairs to merge. **What was
found instead**: the gap analysis surfaced two real, silent bugs, not just
missing coverage —

1. `kb.py set <name> links <value>` wrote the raw string as-is (`links: foo`)
   instead of list syntax (`links: [foo]`). Frontmatter parsing then reads
   `links` back as a *string*, not a list, and code elsewhere calling
   `list(fm.get("links") or [])` (e.g. `cmd_link`) would silently iterate
   its characters. Confirmed by writing the regression test first, then
   reverting the fix — it failed as expected (`0 == 0`, i.e. `set` reported
   success). Fixed by refusing `links` in `cmd_set`, same pattern already
   used for the identity fields `name`/`type`, pointing at `kb.py link`.
2. `dupe_pairs()` (backing `kb.py dupes`) had no archived-entry filter, while
   `_candidate_docs()` (backing `kb.py candidates`) explicitly skips
   `is_archived` entries. `dupes` would flag an archived entry as a live
   duplicate. Confirmed the same way — reverted, regression test failed.
   Fixed by adding the same `is_archived` skip to `dupe_pairs`.

Both were caught by asking "what untested branch could hide a regression",
not by running the existing suite — it was green throughout, on both sides
of each fix.

**Consolidation, the smaller half of the task**: found only mild overlap —
a few tests re-asserting a numeric fact (e.g. jaccard score, budget-cap math)
already pinned by a more specific test elsewhere, and one test-log check that
was a strict subset of another. Trimmed those and repurposed one redundant
confidence-decay test (two ages that landed on the same clamp branch) into a
genuinely new one covering an untested intermediate decay step. Net: test
count went from 231 to 244 — consolidation removed noise, the gap analysis
added more than it removed, because the bugs it found were real.

**What should change next time**: a "test audit" prompt should not be read
as "find redundant tests" alone — the gap half of the exercise is where
actual defects hide, and is worth at least as much attention as the
consolidation half. `AUTONOMY.md`'s backlog phrasing ("consolidate where
LEAN, add coverage where a regression could hide") already says this; this
entry is the evidence that the second half paid off more than the first.
