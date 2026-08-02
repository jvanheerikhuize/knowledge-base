---
name: kb-roadmap
type: prospective
description: the KB's next work is memory evolution and MCP exposure, not more capture — tracked in ROADMAP.md, review quarterly
confidence: high
source: research 2026-07-27 into current agent-memory practice, mapped against this repo's actual CLI surface
created: 2026-07-27
last_verified: 2026-07-30
links: [kb-is-file-based, memory-overview-site, editing-the-kb-without-a-cms, twin-sovereignty-constraint, kb-over-mcp, kb-forgetting-model, kb-duplicate-detection-limits, kb-contradiction-is-a-second-axis, kb-consolidation-is-owed-work, kb-corrections-happen-in-place, kb-prospective-memory-that-fires, kb-instruction-content-lint]
due: 2026-10-27
---

**The intention.** Ten phases are recorded in `../../ROADMAP.md`. Re-read it on
the due date, move what shipped into its Done section, and re-order the rest.
This entry exists so the roadmap surfaces in `kb.py triage` instead of rotting
in a file nobody opens.

**The finding that shaped it.** Agent memory is a lifecycle — formation,
evolution, retrieval — and this repo has only ever built formation. Templates,
`kb.py new`, schema lint, and staleness audits all serve *writing things down*.
Nothing consolidates, ages, retires, or ranks. That is the wrong half to have
finished, because the documented failure mode of a memory store is not losing
facts, it is keeping all of them: stale contradictory entries outrank current
ones until the store is technically complete and practically useless.

**Therefore the ordering.** Ranked retrieval first (Phase 1), because
[[kb-is-file-based]] promises an agent can retrieve relevant facts at inference
time, and an unranked substring match stops delivering that somewhere in the
low dozens of entries. Then MCP exposure (Phase 2), because every consumer
currently shells out and parses text, and the neighbouring projects have all
converged on serving the store as a tool. Then consolidation, decay, and
temporal validity (Phases 3–4), which are what keep the first two honest as the
store grows — though the last of those turned out to need no new frontmatter at
all, per [[kb-corrections-happen-in-place]].

**Two constraints the roadmap must not break.** Every phase is stdlib-only and
git-backed — BM25, shingling, and stdio JSON-RPC were chosen precisely because
they need no dependency. And writes stay proposals: the MCP server stages
changes for review rather than committing them, exactly as
[[editing-the-kb-without-a-cms]] settled for the browser. Under
[[twin-sovereignty-constraint]] none of it may require an API key or an agent
in the loop to function.

**The admission that shaped Phase 3, and how it resolved.** Phase 3 was written
as the answer to a standing admission in `memory/AGENT.md` that nothing checked
entries against each other. The answer turned out to be that there was no
checker to build; what shipped instead is recorded in
[[kb-contradiction-is-a-second-axis]], which is where that finding lives.
