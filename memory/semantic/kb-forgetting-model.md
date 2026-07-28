---
name: kb-forgetting-model
type: semantic
description: the KB forgets in two ways — confidence decays with age at read time, and archiving retires an entry from retrieval while keeping it readable and in the graph; neither rewrites what an author wrote
confidence: verified
source: scripts/kb.py (effective_confidence, is_archived, cmd_archive), tests/test_kb.py, ROADMAP Phase 3
created: 2026-07-28
last_verified: 2026-07-28
links: [kb-ranked-retrieval, kb-entry-status-model, kb-is-file-based, kb-over-mcp, kb-duplicate-detection-limits]
---

A memory store does not fail by losing facts. It fails by keeping all of them,
until stale claims outrank current ones and an agent that remembers everything
remembers nothing useful. Two mechanisms answer that, and the constraint they
share matters more than either one: **neither rewrites what an author wrote.**

**Confidence decays at read time.** `confidence` records how well a fact was
checked *when it was checked*. On its own it says nothing about how long ago
that was, so an entry can sit at `verified` indefinitely while nobody looks at
it. Ranking therefore uses an aged value — one level down per `STALE_DAYS`
(90) elapsed since `last_verified`, floored at `unverified`. A `verified` fact
untouched for a year competes as `unverified`.

The decay is computed in `effective_confidence()` on every read and reversed by
`kb.py verify`. It is deliberately **not** a stored field: writing the demoted
level back would destroy the author's actual claim and make the ageing
irreversible. Where the stored and effective values differ, both are shown —
`[verified -> unverified, aged]` in search, `confidence: unverified (recorded as
verified, aged)` in a context pack — because a claim's age is part of its
provenance, which is what [[kb-ranked-retrieval]] exists to preserve.

**Archiving retires without destroying.** `kb.py archive <name>` stamps an
`archived` date in the frontmatter. The entry leaves the retrieval set — `rank`,
context packs, and the triage queue all skip it — while the file, its links, and
its position in the graph all stay. `status` still accounts for it under its own
`archived` state, so the store never quietly loses track of an entry. `--undo`
reverses it. Over MCP the same operation runs through `propose_update`, staged
and uncommitted like every other write ([[kb-over-mcp]]).

**Why archive rather than delete.** Deleting destroys the evidence that anyone
ever believed the thing. Archiving keeps the audit trail: what was thought, what
linked to it, and when it stopped being used. `rm` still exists for entries that
should genuinely be gone; archiving is the operation you want almost every time.

**One consequence worth remembering.** Archiving is also the statement that an
entry no longer needs attention, so archived entries drop out of triage and are
exempted from the stale/unverified/orphan lint warnings. Without that, a retired
entry would sit in the queue forever and the queue would stop being clearable —
which is the failure that makes people ignore queues.

**What this does not do.** Nothing here detects that two entries *say the same
thing*, or that one contradicts another. That is the consolidation half of
Phase 3 (`dupes`, `consolidate`, contradiction detection) and remains unbuilt;
the admission in `memory/AGENT.md` that no contradiction checker exists still
stands.
