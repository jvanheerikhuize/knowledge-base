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

## Phase 1 — Retrieval that ranks · `done`

**Gap.** `kb.py search` was an unranked substring match over body plus
frontmatter values. Every hit was equal, and the caller sorted by hand. The
success metric in [PURPOSE.md](PURPOSE.md) is that an agent can "retrieve
relevant facts at inference time" — unranked grep does not meet that once the
store passes a few dozen entries.

- ✅ **BM25 ranking in `search`.** Classic BM25 is ~40 lines of stdlib; the corpus
  is small enough that scoring every entry per query is free. Ranked output,
  `--limit`, and a score column.
- ✅ **Type-aware scoring.** Recency is a first-class signal for `episodic` (what
  happened most recently usually wins); content similarity is the right signal
  for `semantic`. Keep episodic logs out of the semantic ranking by default so
  a busy week of events cannot bury a durable fact.
- ✅ **`kb.py context "<task>" [--budget N]`.** Emit a paste-ready context pack:
  the top-ranked entries, trimmed to a token budget, with provenance. This is
  the single command an agent should need at the start of a task, and it is the
  literal shape of the success metric.

## Phase 2 — Expose the KB over MCP · `done`

**Gap.** Every consumer had to shell out to `kb.py` and parse text. The
near-neighbour projects that were re-checked ([Basic Memory](https://basicmemory.com/),
brain.md — see Sources consulted) have converged on the same answer: serve the
store over MCP so any agent can use it as a tool.

- ✅ `scripts/mcp_server.py`, stdio JSON-RPC, stdlib-only — the same dependency
  posture as the rest of the tooling. Tools call kb.py's *library* functions,
  never its `cmd_*` handlers, because the stdio transport forbids anything on
  stdout that is not an MCP message and those handlers print.
- ✅ Tools: `context`, `search`, `get`, `triage`, `status`, `propose_update`.
  Entries are also published as resources under `kb://entry/<name>`, which is
  the MCP-native way to hand an agent a document it can attach directly.
- ✅ **Writes are proposals.** `propose_update` stages a change in the working
  tree and never commits, mirroring `scripts/serve.py`. Git stays the durable
  write path and the review gate, per [[editing-the-kb-without-a-cms]].
  `--read-only` drops the tool from `tools/list` altogether.

**The version decision, and what is left.** The server speaks `2025-11-25` and
negotiates down to `2025-06-18` / `2025-03-26`. It deliberately does not
implement `2026-07-28`, which landed the day this shipped: that revision deletes
the `initialize` handshake in favour of per-request `_meta`, adds `server/discover`,
and states outright that there is no automatic compatibility with `2025-11-25`.
Implementing a spec no client speaks yet, against SDKs still inside their
ten-week validation window, would trade a working server for a hypothetical one.

- **Open:** re-evaluate `2026-07-28` once the reference SDKs and at least one
  client ship it. The handshake removal is the only structural change that
  touches this server — the tool and resource surfaces are unaffected — so the
  migration is a lifecycle change, not a rewrite.

## Phase 3 — Consolidation and forgetting · `in progress`

**Gap.** `memory/AGENT.md` states plainly that lint "does not detect
content-level contradictions between entries — no such checker exists yet."
Nothing merges duplicates, nothing ages, nothing retires. The documented
failure mode of memory systems is exactly this: stale contradictory facts
outranking current ones until an agent that remembers everything remembers
nothing useful.

- ✅ **`kb.py dupes`** — shipped, but **not** doing what this line originally
  promised, and the gap is the finding. Shingling was measured against a
  hand-written paraphrase of an existing entry: it ranked **#14 of 210 pairs**,
  below thirteen pairs of entries that merely share a subject. On raw 5-word
  shingles it scored 0.000. Lexical similarity ranks topical neighbours above
  actual restatements on hand-written prose, so any threshold low enough to
  catch a paraphrase admits a dozen false positives first.

  So `dupes` is scoped honestly to **near-verbatim** overlap — an entry
  recorded twice, a scaffolded copy drifting back, an agent re-adding its own
  work — at a threshold ~70× the store's observed maximum, and it prints the
  sentence naming its own limit so a clean result is never read as "no
  duplicates". It also reports *containment*, which catches the asymmetric case
  Jaccard scores lowest: a short entry wholly absorbed into a longer one.
  MinHash/LSH were rejected as approximations of a computation that is free at
  this scale. Full write-up: [[kb-duplicate-detection-limits]].

- **Semantic duplicate detection** — still open, and now known to be the hard
  part rather than a threshold tweak. Two routes: embeddings, which break the
  no-infrastructure premise of [[kb-is-file-based]] and the no-vendor-model rule
  of [[twin-sovereignty-constraint]]; or an agent reading candidate pairs and
  judging them, which is exactly how classification already works for `kb.py new`
  and is therefore the consistent choice. Design the second before building it.
- **`kb.py consolidate`** — propose merges, and propose distilling repeated
  `episodic` observations into one `semantic` fact. Proposals, never silent
  rewrites. Blocked on the line above: merging is only as good as the candidate
  set feeding it, and `dupes` currently supplies only the near-verbatim ones.
- **Contradiction detection** — start mechanical: same subject, conflicting
  frontmatter, or an entry whose body negates one it links to. Report as a
  triage reason code rather than a lint failure.
- ✅ **`kb.py archive <name>`** — invalidate rather than delete. Archived entries
  leave the retrieval set (search, context packs, triage) but stay readable,
  stay linked, and stay in the graph, so the audit trail survives. `status`
  accounts for them under an `archived` state; `--undo` reverses it; deletion
  remains available via `rm`.
- ✅ **Confidence decay** — `last_verified` ageing now demotes confidence in
  ranking rather than only printing a warning: one level per staleness period,
  so a `verified` fact untouched for a year is not verified. Applied at read
  time and reversed by `verify`, so the file keeps the level its author
  recorded — decay is never a silent rewrite. Both numbers are surfaced
  wherever they differ, including in context packs, because a claim's age is
  part of its provenance.

**Why the forgetting half shipped first.** Decay and archiving are decisions
about a *single* entry and cannot really be wrong. Merging is a claim about a
*pair*, and the measurement above shows how hard that claim is to make from text
alone. That ordering turned out to be right for a reason that was not obvious
when it was chosen.

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
`knowledge-base`, the workspace wiki, and `digital-twin`. (The workspace
CLAUDE.md still calls that wiki `knowledge`; no such directory exists — the
live repo is `llm-wiki`, per [[workspace-repo-inventory-drift]].)

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
- MCP server over stdio with staged, never-committed writes ([[kb-over-mcp]]).
- Read-time confidence decay and `kb.py archive` — the forgetting half of
  Phase 3 ([[kb-forgetting-model]]).

---

## Sources consulted

Only what was actually read, with the date it was read. Claims in this roadmap
that are not backed by a line here are judgement, not citation.

- MCP specification `2025-11-25` — [lifecycle](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2025-11-25/basic/lifecycle.mdx),
  [transports](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2025-11-25/basic/transports.mdx),
  [tools](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2025-11-25/server/tools.mdx),
  [resources](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2025-11-25/server/resources.mdx),
  and [schema.json](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/schema/2025-11-25/schema.json)
  (2026-07-28) — protocol version string, stdio framing rules, tool/resource
  message shapes, `ToolAnnotations` fields.
- [The 2026-07-28 MCP Specification Release Candidate](https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/)
  (2026-07-28) — the stateless core, removal of the initialize handshake, and
  the explicit "no automatic compatibility with 2025-11-25" statement that
  Phase 2's version decision rests on.
- [CoALA](https://arxiv.org/abs/2309.02427) — the memory taxonomy the folder
  layout follows.

- Near-duplicate detection background (2026-07-28) — [Broder, *Identifying and
  Filtering Near-Duplicate Documents*](https://cs.brown.edu/courses/cs253/papers/nearduplicate.pdf),
  [Stanford IR, *Near-duplicates and shingling*](https://nlp.stanford.edu/IR-book/html/htmledition/near-duplicates-and-shingling-1.html).
  Source of the shingling construction, the standard threshold bands
  (0.7–0.8 conservative, 0.5–0.6 aggressive), and the warning that shingle
  estimates degrade on very short documents — which is why `dupes` skips
  entries under 20 shingles and says which ones it skipped.

**Near-neighbour projects — re-checked 2026-07-28.** The Phase 2 sentence
originally named four; two are confirmed, two are dropped as uncited.

- [Basic Memory](https://basicmemory.com/) — confirmed. Markdown files plus a
  SQLite index and a knowledge graph, served over MCP. Its
  [skills repo](https://github.com/basicmachines-co/basic-memory-skills) ships a
  "memory-defrag" skill that merges duplicates and removes stale information —
  direct prior art for Phase 3 — but publishes no similarity metric and does not
  say whether merges are automatic or proposed, so it settles nothing about the
  hard part.
- **brain.md** — confirmed. Local-first markdown vault with an MCP server, and
  notably a `context_for_query` token-budgeted chunk-packing tool that is the
  same idea as this repo's `kb.py context`, arrived at independently.
- **kb-mcp, "Agent Memory"** — could not be confirmed as distinct projects.
  Dropped rather than left as plausible-looking filler.
