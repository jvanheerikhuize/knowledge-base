---
name: kb-tests-cannot-cover-an-absent-guard
type: semantic
description: three commands shipped without an archived filter and the diagnosis was an archived-blind test corpus — but mutation testing kills 12 of 13 archived guards, so the corpus was never blind; all three bugs were *absent* guards, and no corpus can exercise a line that was not written, which is why the repair is an enumeration of scanners that fails on absence rather than more coverage
confidence: verified
source: measured 2026-08-07 in this repo — 13-mutant run over the archived axis, twice (before and after), plus AST discovery over all four scripts
created: 2026-08-07
last_verified: 2026-08-07
links: [kb-archived-is-a-filter-commands-forget, audit-test-corpora-for-artificial-uniformity, kb-forgetting-model, kb-entry-status-model, kb-test-audit-2026-07-29, kb-over-mcp]
---

Archiving takes an entry out of retrieval without deleting it
([[kb-forgetting-model]]), so every function that scans the store has to decide
what `archived` means to it. Three commands have shipped having never made that
decision — `dupes` (2026-07-29), `eval` (2026-08-05), `lint` (2026-08-06) — and
all three were found by a person reading the code, never by a failing test.

[[kb-archived-is-a-filter-commands-forget]] diagnosed that as an archived-blind
corpus: one archived entry in 34, fixtures that never vary the axis, therefore
a branch no test can reach. It reads as an instance of
[[audit-test-corpora-for-artificial-uniformity]]'s rule 2. **The diagnosis is
wrong, and measuring it is what shows why.**

## The measurement

Mutation test on the axis: delete each of the 13 places `kb.py` consults
`archived`, one at a time, and run the entire suite against each mutant. A
guard no test defends is a mutant that survives.

| corpus | mutants | killed | survived |
|---|---|---|---|
| before (`899a6e3`, 463 tests) | 13 | **12** | 1 — `lint`'s unverified-age warning |
| after (485 tests) | 13 | **13** | 0 |

Twelve of thirteen died, most inside a test written specifically for the
archived case: `test_an_archived_copy_is_not_flagged`,
`test_archived_entries_leave_the_triage_queue`,
`test_archived_entries_are_out_of_the_forecast`, and so on. The corpus was
never blind to this axis. It defends essentially every archived guard that
exists — including in `build_site` and `mcp_server`, whose own fixtures never
archive anything, because the kb.py-level tests cover the functions they call.

## Why both facts are true at once

**You cannot mutate a line that is not there.** All three bugs were guards that
were *never written*, not guards that were written and left undefended. A test
corpus — however large, however diverse its fixtures — can only exercise code
that exists. Coverage of the archived branch was never the missing ingredient:
every command that had the branch had a test for it, and every command that
lacked the branch had nothing for a test to fail against.

This is the sharp edge of the uniformity rule rather than an instance of it.
Rule 2 says a uniform corpus disables code paths that only diverge under
diversity, and the repair it implies is *diversify the fixture*. Diversifying
the fixture here would have changed nothing: a store full of archived entries
still cannot make `dupes` fail on a filter `dupes` does not contain. Fixture
diversity finds **wrong** code. It is structurally incapable of finding
**missing** code, and "missing" is what this defect class always is.

## What does fail on absence

Enumerate the scanners and require each to name its policy. `tests/
test_archived_axis.py` discovers, by AST, every function that reads the whole
store — directly via `iter_entries()`, or transitively through one that does —
and fails if any of them is absent from a registry that assigns one of three
policies: `EXCLUDES` (retired means gone), `CLASSIFIES` (appears, labelled), or
`INCLUDES` (appears unfiltered, reason required). A new scanner cannot be
merged without its author answering the question, which is the one thing all
three bugs had in common.

It earned its keep immediately, on the session that wrote it:

- **11 scanners were missing from a registry compiled by hand** by someone who
  had just read the whole file for this purpose — `context_pack`,
  `capture_report`, `_require`, `list_resources`, `tool_propose_update`,
  `build`, `main`, `_known_names`, `api_update`, `api_delete`, and `_all`.
  Hand-enumeration is the method the advisory corollary depends on, and it
  missed a third of the set under ideal conditions.
- **The discovery rule reproduced the bug it hunts.** Its first version ran the
  transitive closure inside `kb.py` only, so `mcp_server.list_resources` — which
  consumes `_all_entries` and therefore decides the archived question — was
  invisible to it. Scoping a check to one file is the same move as scoping a
  guard to one loop.
- **One real live defect.** `resources/list` advertised archived entries to MCP
  clients with no label at all, while every other surface on that server
  (`search`, `context`, `triage`) filters them out ([[kb-over-mcp]]). Listed
  *and* unlabelled is the one combination that misleads: a client browsing
  resources picks a retired claim believing it current. Fixed by labelling
  rather than hiding — dropping it would leave no way to find the entry you
  want to un-archive — which is the `CLASSIFIES` policy `status` already uses
  ([[kb-entry-status-model]]).

## The method's own trap, recorded

The first mutation run reported **13 of 13 killed** and was worthless. A stray
file copied into `scripts/` broke test discovery, so the suite never ran, so no
`FAIL:` line appeared, so every mutant read as "survived" — and in an earlier
pass, a half-written test that failed unconditionally made every mutant read as
"killed". Both directions of the error are silent, and both produce a clean,
plausible number. A mutation harness must assert that the suite *ran* (`Ran N
tests`, and either failures or `OK`) before believing either verdict. The
harness is deliberately **not** committed: its mutants are anchored to exact
source lines, so it rots into "anchor error" the moment `kb.py` is edited, and
a rotted harness reports coverage that is not there. The registry test is the
durable artifact; the numbers above are the record of the run.
