---
name: audit-test-corpora-for-artificial-uniformity
type: procedural
description: when auditing a test suite for coverage gaps, check whether every test builds a corpus with only one value along some axis (one type, one length, one ordering) — that uniformity is exactly what lets loop-variable shadowing and off-by-one bugs hide
confidence: verified
source: knowledge-base test-consolidation audit, session 2026-07-30
created: 2026-07-30
last_verified: 2026-08-07
links: [kb-duplicate-detection-limits, persist-insight-to-knowledge-base, kb-test-audit-2026-07-29, kb-tests-cannot-cover-an-absent-guard]
---

Found while doing the AUTONOMY.md "test consolidation & audit" backlog item:
`scripts/kb.py`'s `cmd_rm` had `for t, other in iter_entries():` overwriting
the outer `t` that `_require()` had already resolved to the *deleted*
entry's own type, so the ingest-log line written after the loop recorded
whichever type `iter_entries()` last yielded — not the type of the entry
actually removed. Every existing `rm` test built a single-type store
(`semantic` only), so `t` never actually changed value across the loop and
the bug was invisible to 267 passing tests.

The general lesson, worth applying whenever auditing a suite for gaps rather
than just running it:

1. **List the axes a test corpus varies along** — entry type, list length
   (0/1/many), ordering, whether values collide. Then check whether any
   test ever varies more than one item along each axis at once.
2. **A corpus that is accidentally uniform (all one type, all one value)
   silently disables any code path that only diverges under diversity** —
   loop variables reused for two purposes, `min`/`max`/tie-break logic,
   dedup keyed on a field that's constant across the fixture. Passing tests
   prove nothing about that path; they never exercised it.
3. **When reading a function under audit, look for a variable used both as
   a loop target and as a value computed earlier in the same function.**
   That's the shape this bug took (`t` from `_require()`, then `t` again
   from the `for` loop) and grep for `for <name>,` reusing an outer name is
   a fast way to scan for it across a file.
4. **Write the regression test against a corpus that actually varies the
   axis**, then verify it fails on the unfixed code before trusting it —
   a test that would pass either way proves nothing about the fix.

This complements [[kb-duplicate-detection-limits]]'s lesson (a metric can
pass its own test and still answer the wrong question) from the coverage
side: a test can pass and still never have exercised the path it claims to
guard, if the fixture that feeds it never varied.

5. **Before reaching for this procedure, check whether the path you are
   worried about exists at all.** Steps 1–4 diagnose a branch that is
   *written* and never *reached*. They are structurally incapable of finding
   a branch that was never written — there is nothing for a fixture, however
   diverse, to make fail. That distinction was measured on 2026-08-07
   ([[kb-tests-cannot-cover-an-absent-guard]]): three commands missing the
   same `archived` filter looked like a textbook rule-2 case, but mutation
   testing killed **12 of 13** archived guards, so the corpus had never been
   uniform in the way the diagnosis assumed. All three were absent guards.
   The tell is the shape of the defect: *wrong* behaviour under some input
   is a uniformity problem and this procedure applies; *no* behaviour,
   because the decision was never made anywhere, needs an enumeration of the
   call sites that must make it, which is a different tool.
