# Roadmap

```mermaid
gantt
    dateFormat  YYYY-MM-DD
    title Agent Memory Knowledge Base — Roadmap
    section Phase 0 — Research & Design
    Research 7 memory types & LLM-wiki pattern      :done, p0a, 2026-07-22, 1d
    Plan + solution overview + repo init            :done, p0b, 2026-07-22, 1d
    section Phase 1 — Core Scaffold
    Folder-per-memory-type structure                :done, p1a, 2026-07-22, 1d
    Entry schema + templates                        :done, p1b, 2026-07-22, 1d
    AGENT.md single entry point                     :done, p1c, 2026-07-22, 1d
    section Phase 2 — Ingestion & Interface
    kb.py CLI (list/search/show/new)                :done, p2a, 2026-07-22, 1d
    Ingestion workflow docs for agents              :done, p2b, 2026-07-22, 1d
    section Phase 3 — Fact-checking & Visualization
    kb.py lint (staleness, duplicates, links)       :done, p3a, 2026-07-22, 1d
    visualize.py Mermaid graph generator            :done, p3b, 2026-07-22, 1d
    section Phase 4 — Pipeline Integration
    scaffold.sh for dropping into other repos       :done, p4a, 2026-07-22, 1d
    GitHub Action: lint + regen graph on PR         :done, p4b, 2026-07-22, 1d
    section Phase 5 — Audit Fixes (bugs)
    Untrack __pycache__, add .gitignore             :p5a, 2026-07-23, 1d
    Fix scaffold custom-subfolder support           :p5b, after p5a, 1d
    Emit graph.md so GitHub renders the diagram     :p5c, after p5a, 1d
    Staleness as warning; --strict via cron CI      :p5d, after p5b, 1d
    section Phase 6 — Docs & Schema Alignment
    Add parametric to solution-overview enum        :p6a, after p5d, 1d
    Align lint claims with actual behavior          :p6b, after p6a, 1d
    Enforce schema-required fields in lint          :p6c, after p6b, 1d
    section Phase 7 — Source Alignment (LLM-wiki)
    Generate index.md catalog                       :p7a, after p6c, 1d
    Add log.md chronological ingest log             :p7b, after p7a, 1d
    Lint orphan entries (no inbound links)          :p7c, after p7a, 1d
    Lint overdue prospective + type/folder mismatch :p7d, after p7c, 1d
    section Phase 8 — Tests & CI Hygiene
    stdlib unittest suite for kb.py/visualize.py    :p8a, after p7d, 2d
    CI trigger parity + workflow_dispatch           :p8b, after p8a, 1d
    section Phase 9 — Adoption & Iteration
    Dogfood on a real project repo                  :p9a, after p8b, 5d
    Iterate on schema based on real usage           :p9b, after p9a, 5d
```

## Phase details

**Phase 0 — Research & Design (done)**
Reviewed the CoALA-derived 7-memory-type taxonomy and Karpathy's LLM-wiki
maintenance pattern; produced `docs/plan.md` and
`docs/solution-overview.md`; initialized this repo.

**Phase 1 — Core Scaffold (done)**
Stand up `memory/<type>/` folders, a JSON Schema for entry frontmatter, a
markdown template, and `memory/AGENT.md` as the single entry point.

**Phase 2 — Ingestion & Interface (done)**
`scripts/kb.py` gains `new` (scaffold a typed entry), `list`, and `search`
(keyword/frontmatter grep — no embeddings). Ingestion stays agent-assisted:
the operating agent reads a source, classifies it into one of the 7 types,
and runs `kb.py new` to scaffold the file rather than a hardcoded model call
doing it — this is what keeps the system solution-agnostic.

**Phase 3 — Fact-checking & Visualization (done)**
`kb.py lint` flags entries whose `last_verified` is stale past a threshold,
duplicate `name` slugs, and `links:` pointing at entries that don't exist.
`scripts/visualize.py` walks all frontmatter and regenerates
`memory/_generated/graph.mmd`, a Mermaid graph colored by memory type.
(Content-level contradiction detection is not implemented yet — see
Phase 6.)

**Phase 4 — Pipeline Integration (done)**
`scripts/scaffold.sh` copies the `memory/` + `scripts/` template into any
target repo as a subfolder (satisfies "scaffolder can be triggered via a
pipeline/action"). `.github/workflows/kb-lint.yml` runs `kb.py lint` and
regenerates the graph on every PR touching `memory/**`.

---

Phases 5–8 come out of the repository audit performed on 2026-07-22.

**Phase 5 — Audit Fixes (bugs)**
The four findings that cause real breakage:
- `scripts/__pycache__/kb.cpython-312.pyc` is committed and there is no
  `.gitignore` — `git rm --cached` it and ignore build artifacts.
- `scaffold.sh` accepts a `[subfolder-name]` argument, but `kb.py`
  hardcodes `MEMORY = ROOT / "memory"` and the CI workflow hardcodes
  `memory/**` paths, so any non-default name produces a broken install.
  Make the memory dir discoverable (env var / config / upward search) or
  drop the option.
- GitHub does not render standalone `.mmd` files, so the visualization
  layer is invisible where people actually browse the repo. Have
  `visualize.py` also emit `memory/_generated/graph.md` with a
  ```` ```mermaid ```` fence (and fix the AGENT.md claim that the `.mmd`
  renders inline).
- The lint staleness checks (>90d stale, >30d unverified) hard-fail and
  run on every PR touching `memory/**`, so CI goes red purely from time
  passing. Demote staleness to a warning in PR CI and add a `--strict`
  flag exercised by a scheduled (cron) workflow instead.

**Phase 6 — Docs & Schema Alignment**
Make the docs and schema tell the truth about the code:
- `docs/solution-overview.md`'s entry-format `type:` enum omits
  `parametric`; the schema and `kb.py` include it.
- AGENT.md and the docs claim lint catches "contradicting entries" /
  "duplicate slugs with conflicting content" — the code only detects
  duplicate slugs. Either soften the claim or implement a minimal
  content-conflict check (same name, differing confidence/description).
- `memory/schema/entry.schema.json` is referenced by nothing. Enforce its
  required fields and enums inside `kb.py lint` (stdlib-only), or document
  the schema as reference-only.

**Phase 7 — Source Alignment (LLM-wiki pattern)**
Close the gaps against the Karpathy gist the design is based on:
- Generate `memory/_generated/index.md`: a catalog of every entry with its
  one-line description, grouped by type — the gist's `index.md` artifact.
- Add `memory/log.md`: a chronological log of ingests/distillations, the
  gist's `log.md` artifact (append a line from the distill procedure).
- Lint orphan entries — pages with no inbound links — which the gist's
  lint explicitly checks; current lint only catches dangling *outbound*
  links.
- Lint overdue `due:` dates on prospective entries (nothing checks them
  today, so prospective memory never "fires") and flag entries whose
  `type:` frontmatter doesn't match the folder they live in. Add `due:`
  to the entry template.

**Phase 8 — Tests & CI Hygiene**
- A stdlib `unittest` suite exercising `kb.py` and `visualize.py` against
  a temp KB (new/list/search/lint/graph generation), wired into CI.
- CI trigger parity: the `push` trigger should watch the scripts like the
  PR trigger does; add `workflow_dispatch`.
- Small cleanups: use `<br/>` instead of `\n` in Mermaid node labels,
  stop `kb.py search` reading each file twice.

**Phase 9 — Adoption & Iteration**
Use the scaffold on a real working repo, capture friction, and adjust the
schema/CLI. Candidate upgrades (deliberately deferred, not required for v1):
- Optional embedding-based retrieval as a pluggable backend behind the same
  `kb.py search` interface, for repos that *do* want infra.
- A lightweight read-only HTML viewer for the Mermaid graph (still no
  server — a static file).
- MCP server wrapper exposing `kb.py` commands as tools, for agents that
  prefer MCP over shelling out.
