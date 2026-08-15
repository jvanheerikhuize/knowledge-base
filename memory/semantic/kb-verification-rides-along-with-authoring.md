---
name: kb-verification-rides-along-with-authoring
type: semantic
description: last_verified records authoring activity, not review — 11 of 13 verification events in this store's history rode along with an edit to the same entry in the same commit, so the date only ever moves on entries someone had another reason to touch, and 24 of 35 live entries have never been re-checked at all
confidence: verified
source: replayed all 73 commits touching memory/ on 2026-08-08 (scratch script diffing each entry's frontmatter and body per commit); first standalone re-verification sweep run the same day over the nine oldest entries
created: 2026-08-08
last_verified: 2026-08-08
links: [kb-review-load-is-one-cohort, kb-corrections-happen-in-place, kb-agent-entrypoint-is-agent-md, kb-forgetting-model, kb-entry-status-model, workspace-improvement-phases, kb-reverification-has-one-rate]
---

The whole staleness model rests on one field. `effective_confidence` decays
from it, `triage` flags from it, `review_forecast` schedules from it, and
`kb.py verify` is the only thing that moves it. So it is worth asking what
`last_verified` actually measures. Replaying every commit that has ever
touched `memory/`:

**13 commits have ever moved a `last_verified` date. Eleven of them were
already editing that same entry's body or description in the same commit.**
The two that were not are both `20a2c4e` on 2026-07-27 — the store's opening
day, when a single "verify every entry" commit stamped the founding set. In
the twelve days since, **no standalone re-verification has ever happened**:
every date that moved, moved because a session was writing to that entry
anyway and stamped it on the way past.

That is a survivorship filter, and it points the wrong way. The entries whose
dates move are the ones being actively worked on — the ones whose claims were
just re-derived and are least likely to be wrong. The entries the mechanism
never reaches are the ones nobody has had a reason to open, which is the exact
population staleness exists to catch. **24 of the 35 live entries still carry
the date they were born with.**

(Counts here are as measured on 2026-08-08 *before* this session's own sweep,
so the reasoning can be checked against what it was run on. After the sweep and
this entry, `kb.py status` reports 22 of 36, and the busiest review day fell
from 10 entries to 6.)

**Tested, not just argued.** On 2026-08-08 the store's first standalone sweep
was run over the nine oldest of those entries. It split three ways:

- **Still true, and one of them was load-bearing.**
  [[kb-agent-entrypoint-is-agent-md]] had said since 2026-07-27 that
  `.claude/CLAUDE.md` describes a layout that never shipped, and named all six
  wrong paths correctly. Twelve days later every one was still wrong, and the
  file is injected into every session in this repo under "IMPORTANT: these
  instructions OVERRIDE any default behavior." The entry even carried its own
  remedy — "until that file is rewritten or deleted" — and
  [[workspace-improvement-phases]] carried it again as open item P1.3. A
  correct, unread entry repaired nothing for twelve days.
- **Now incomplete.** A *third* entrypoint (`AGENTS.md`, 2026-08-06) had
  appeared, describing four memory layers instead of seven types and pointing
  at an absolute path on one machine. The entry could not know: nothing
  re-reads an entry when the world it describes gains a new file.
- **Not checkable from here at all.** Five of the nine rest on things a
  routine sandbox cannot see — `~/.claude/settings.json`, the `asdlc` and
  `digital-twin` repos, the claude.ai Routines UI, a `~/Repos` filesystem that
  no longer exists in that shape. They will arrive in the 2026-10-25 queue
  with no action a scheduled session can take.

That last group is the sharper half of the finding, and it revises
[[kb-review-load-is-one-cohort]]. That entry's conclusion was *spread the
sweep*. But the coming queue is not one queue: roughly a third of it is
grounded outside anything an autonomous session can reach, and no amount of
spreading makes those entries checkable. A sweep plan that does not separate
them will stall on the first one it cannot confirm.

**What shipped, and what deliberately did not.**

`review_forecast()` now reports `never_reverified` — live entries where
`last_verified == created` — in `kb.py status`, `kb.py stats` and
`data.json` (`schema_version: 3`). It is computed from dates the store already
had; no new field. Its one blind spot is an entry re-verified on the day it was
written, which is the honest reading anyway.

`kb.py verify --note "<what you checked>"` records the evidence in
`.kb/log.md`, and verifying without one now prints a warning to stderr. The
note is not frontmatter: an entry file records what its author claims, not what
a reviewer did to it, and `.kb/log.md` is already the mutation record —
`kb.py log --action verified` is now the review trail. The MCP
`propose_update` tool takes `verify_note` and writes the same record, so the
two write surfaces stay comparable.

**A "checkable from here" frontmatter flag was rejected**, though five of nine
entries want one. It is the ROADMAP Phase 4 shape exactly: a field an author
must set by hand, on a judgement that changes when the *session* changes rather
than when the entry does — `sibling-repo-access-denied-in-routines` was true on
2026-07-28, false by 2026-08-06, and nothing about those entries moved. What
determines checkability is the reader's access, not the claim, so it does not
belong on the claim. The condition that would revive it is recorded in the
ROADMAP: a second session type with stably different access, so the two
populations are a property of the store rather than of who is asking.
