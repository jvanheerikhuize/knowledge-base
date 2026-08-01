---
name: kb-corrections-happen-in-place
type: semantic
description: every obsolete claim in this store was corrected in place by the change that caused it, never retired on a date — so validity intervals had nothing to express and kb.py history surfaces the superseded wording instead
confidence: verified
source: replay of all 21 commits touching memory/ (2026-08-01); scripts/kb.py entry_history() and cmd_history()
created: 2026-08-01
last_verified: 2026-08-01
links: [kb-forgetting-model, kb-entry-status-model, kb-duplicate-detection-limits, kb-roadmap]
---

ROADMAP Phase 4 proposed temporal validity: `valid_until` to say when a claim
lapses, `supersedes: <name>` to say which entry replaced which, and retrieval
skipping the expired. Measured against this store's whole history, all three
have an empty domain.

**How claims actually go obsolete here.** Every commit that has ever touched
`memory/` was replayed and every change classified: 38 creations, 30
bookkeeping-only revisions, 22 rewrites, 6 appends, 3 deletions — and all three
deletions were of generated files or a template that moved, never an entry.

- **0 of 26** entries have a claim with a knowable expiry date. All 22 rewrites
  were facts overtaken by an event nobody could have dated: a script deleted, a
  status added, a file moved. The one date-bound entry is `prospective` and
  already carries `due:`.
- **0 of 22** rewrites retired a whole entry. The nearest case is the one
  `supersedes` was written for — [[kb-duplicate-detection-limits]], whose
  conclusion was overturned. It was deliberately corrected in place and linked,
  because its measurement and its regression test were still valid and only the
  conclusion moved. `supersedes` would have mismodelled its single use case.

**The mechanism, which is the durable part.** Obsolescence is repaired *by the
change that causes it, in the same commit*. `1d1c713` deletes
`scripts/visualize.py` and rewrites all four entries citing it. `9dcde20`
deletes `docs/plan.md`, moves the generated tree, and fixes both entries naming
the old paths. The agent that changes the code owns the memory about the code
and changes both at once, so there is never an interval in which a claim is
stale and unrepaired. That is what leaves nothing for a validity interval to
express — and it is a property of an agent-maintained store, not a law: a store
whose facts describe something outside the repo would not behave this way.

**The stronger framing was tested and also failed.** Binding validity to a
*source* rather than a date looks compelling — 92% of entries cite a repo path,
so flag the entry when the path stops resolving. Replayed across all 21
commits, that check fired **244 times with 0 true positives**, and never fired
on the real breaks above, for the same-commit reason. Its 16 standing fires are
all correct citations: five entries cite sibling repos this one cannot see
([[sibling-repo-access-denied-in-routines]]), `site/data.json` is a build output
under a gitignored path, and [[kb-agent-entrypoint-is-agent-md]] names
`ci/lint.py` and `ci/regenerate_graph.py` inside a table whose subject is that
they do not exist — an entry about a missing file necessarily cites a missing
file. Coarsening to "cited file changed since `last_verified`" is no better: 38
of 82 references fire, because almost everything cites `scripts/kb.py`.

**What shipped instead.** Correction-in-place means the superseded wording of a
claim survives **only in git**, which no part of the tooling could reach.
`kb.py history <name>` reads it back, labelling each revision by what it
changed — claim, body, or bookkeeping — because `verify` and `link` touch an
entry far more often than an author does, and an unlabelled `git log` buries
the revisions that matter under the ones that stamped a date. Where the
one-line claim changed, the superseded wording is quoted.

The count is small and worth stating plainly: **2 of 26** entries have had
their claim rewritten, 8 more have body edits under an unchanged claim. What
justifies the command is that the need was already felt twice with no tool to
meet it — one session corrected [[kb-duplicate-detection-limits]] in place and
added a link because there was no way to *show* the change, and the
contradiction pass a day later recovered a prior version of that same entry
from git by hand to use as test data.

**One trap it must not fall into.** `actions/checkout` defaults to
`fetch-depth: 1`, so a shallow clone would show every entry as having exactly
one revision and never having changed — a confident lie. `history` reports
`shallow: true` and says its history is truncated, which is why revisions are
not on the published site yet.

This is the third consecutive roadmap phase whose item was the wrong shape:
Phase 3's duplicate-merge queue was empty, its contradiction detector was
unbuildable, and Phase 4's validity fields had no domain. In each case the
stated *goal* was sound and the proposed *mechanism* was not. Measure the store
before building for it.
