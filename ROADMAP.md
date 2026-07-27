# Roadmap

What this knowledge base should grow into, and why. Every item below is scoped
to the constraints that define the project ([[kb-is-file-based]]): markdown
files with YAML frontmatter, stdlib-only Python, git as the only durable write
path, no database, no vector store, no service to keep running.

The organising idea comes from how agent memory is described in current
practice — a lifecycle of **formation → evolution → retrieval**, where the
interesting engineering is not in writing memories down but in consolidating,
ageing, and selecting them. This repo is strong at formation (templates, `new`,
schema lint) and weak at the other two. The roadmap is ordered accordingly.

Status legend: `done` · `next` · `planned` · `someday`

---

## Phase 1 — Retrieval that ranks · `next`

**Gap.** `kb.py search` is an unranked substring match over body plus
frontmatter values. Every hit is equal, and the caller sorts by hand. The
success metric in [PURPOSE.md](PURPOSE.md) is that an agent can "retrieve
relevant facts at inference time" — unranked grep does not meet that once the
store passes a few dozen entries.

- **BM25 ranking in `search`.** Classic BM25 is ~40 lines of stdlib; the corpus
  is small enough that scoring every entry per query is free. Ranked output,
  `--limit`, and a score column.
- **Type-aware scoring.** Recency is a first-class signal for `episodic` (what
  happened most recently usually wins); content similarity is the right signal
  for `semantic`. Keep episodic logs out of the semantic ranking by default so
  a busy week of events cannot bury a durable fact.
- **`kb.py context "<task>" [--budget N]`.** Emit a paste-ready context pack:
  the top-ranked entries, trimmed to a token budget, with provenance. This is
  the single command an agent should need at the start of a task, and it is the
  literal shape of the success metric.

## Phase 2 — Expose the KB over MCP · `planned`

**Gap.** Every consumer has to shell out to `kb.py` and parse text. The
near-neighbour projects (Basic Memory, brain.md, kb-mcp, Agent Memory) have all
converged on the same answer: serve the store over MCP so any agent can use it
as a tool.

- `scripts/mcp_server.py`, stdio JSON-RPC, stdlib-only — the same dependency
  posture as the rest of the tooling.
- Tools: `search`, `get`, `context`, `triage`, `status`, and `propose_update`.
- **Writes are proposals by default.** `propose_update` stages a change in the
  working tree for review rather than committing it, mirroring how
  `scripts/serve.py` already works. Git stays the durable write path, per
  [[editing-the-kb-without-a-cms]].

## Phase 3 — Consolidation and forgetting · `planned`

**Gap.** `memory/AGENT.md` states plainly that lint "does not detect
content-level contradictions between entries — no such checker exists yet."
Nothing merges duplicates, nothing ages, nothing retires. The documented
failure mode of memory systems is exactly this: stale contradictory facts
outranking current ones until an agent that remembers everything remembers
nothing useful.

- **`kb.py dupes`** — near-duplicate detection via token shingling, flagging
  pairs of entries that say the same thing in different words.
- **`kb.py consolidate`** — propose merges for near-duplicates, and propose
  distilling repeated `episodic` observations into one `semantic` fact.
  Proposals, never silent rewrites.
- **Contradiction detection** — start mechanical: same subject, conflicting
  frontmatter, or an entry whose body negates one it links to. Report as a
  triage reason code rather than a lint failure.
- **`kb.py archive <name>`** — invalidate rather than delete. Archived entries
  leave the retrieval set but stay readable and stay in the graph, so the audit
  trail survives. Deletion remains available via `rm`.
- **Confidence decay** — `last_verified` ageing should demote confidence, not
  just print a warning. A `verified` fact untouched for a year is not verified.

## Phase 4 — Temporal validity · `planned`

**Gap.** An entry is either true or deleted; there is no way to say "this was
true until March." Systems that handle this well carry validity intervals so a
superseded fact can be excluded from retrieval without losing its history.

- Optional frontmatter: `valid_until`, and `supersedes: <name>`.
- Retrieval skips expired entries; the site renders them as historical.
- Makes the conflict policy explicit and auditable — recency wins, and you can
  see exactly what it won against.

## Phase 5 — Prospective memory that fires · `planned`

**Gap.** `prospective/` entries carry `due:` dates that only surface if someone
runs `triage`. The one memory type that is about the future is inert.

- Scheduled workflow (the weekly `strict-lint` cron is already there) opens or
  updates a GitHub issue when an entry comes due.
- `kb.py due [--within 14d]` for the same view locally.

## Phase 6 — Ingestion without ceremony · `someday`

**Gap.** `memory/working/distill.template.md` is filled in by hand, so capture
depends on remembering to capture.

- **`kb.py distill <transcript>`** — extract candidate atomic facts from a
  session log into a staging area as `confidence: unverified` drafts, for
  review before they join the store. Atomic extraction plus an explicit review
  gate is what keeps a store from filling with restated context.
- **`kb.py import`** — pull entries from a scaffolded copy in another repo,
  which is the missing half of the existing "keeping a scaffolded copy in sync"
  flow.

## Phase 7 — Measure whether the memory is any good · `someday`

**Gap.** There are 98 tests of the tooling and none of the memory. Nothing
tells you whether retrieval got better or worse as the store grew.

- **Retrieval golden set** — a small fixture of query → expected-entry pairs,
  asserted as a regression test. Catches the day a new entry starts shadowing
  an old one.
- **`kb.py stats`** — counts by type and confidence, link density, orphan rate,
  median entry age, growth over time. Surfaced as a panel on the site.

## Phase 8 — Site and graph · `someday`

- Timeline view over `created` / `last_verified`.
- Staleness and confidence heat map, so decay is visible at a glance.
- Saved searches as shareable URLs.

## Phase 9 — Cross-repo integration · `someday`

Named as this repo's role in the workspace: keep wikilinks consistent across
`knowledge-base`, `knowledge`, and `digital-twin`.

- Export a portable bundle (`data.json` plus `memory/`) that another repo can
  read without importing this tooling.
- Cross-repo dangling-link check in CI.
- Must hold [[twin-sovereignty-constraint]]: no API key, no vendor LLM, no
  agent required in the loop for any of it to work.

## Phase 10 — Treat memory as untrusted input · `someday`

A knowledge base that feeds agents is an injection surface. A memory entry that
influences tool selection is a privileged execution path, and model robustness
does not cover it.

- Lint check for instruction-shaped content in entry bodies.
- Keep system-rule memory and preference memory distinguishable, so a
  preference cannot be read as a rule.
- `.kb/log.md` already records every mutation; surface it as a reviewable
  "what changed" view rather than an append-only file nobody reads.

---

## Done

- Folder-per-type store with schema-validated frontmatter.
- `kb.py` CLI: `list search show new lint triage verify set link edit rm`.
- Staleness and unverified-age auditing, strict mode, weekly cron.
- Published overview site with graph, triage queue, and per-entry pages
  ([[memory-overview-site]]).
- Local editing via `scripts/serve.py` with full CLI parity
  ([[editing-the-kb-without-a-cms]]).
- Mutation log in `.kb/log.md`.
