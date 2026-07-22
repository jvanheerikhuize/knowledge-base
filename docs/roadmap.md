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
    Untrack __pycache__, add .gitignore             :done, p5a, 2026-07-23, 1d
    Fix scaffold custom-subfolder support           :done, p5b, after p5a, 1d
    Emit graph.md so GitHub renders the diagram     :done, p5c, after p5a, 1d
    Staleness as warning; --strict via cron CI      :done, p5d, after p5b, 1d
    section Phase 6 — Docs & Schema Alignment
    Add parametric to solution-overview enum        :done, p6a, after p5d, 1d
    Align lint claims with actual behavior          :done, p6b, after p6a, 1d
    Enforce schema-required fields in lint          :done, p6c, after p6b, 1d
    section Phase 7 — Source Alignment (LLM-wiki)
    Generate index.md catalog                       :p7a, after p6c, 1d
    Add log.md chronological ingest log             :p7b, after p7a, 1d
    Lint orphan entries (no inbound links)          :p7c, after p7a, 1d
    Lint overdue prospective + type/folder mismatch :p7d, after p7c, 1d
    section Phase 8 — Tests & CI Hygiene
    stdlib unittest suite for kb.py/visualize.py    :p8a, after p7d, 2d
    CI trigger parity + workflow_dispatch           :p8b, after p8a, 1d
    section Phase 9 — Adoption & Iteration
    Dogfood on a real project repo                  :done, p9a, after p8b, 5d
    Iterate on schema based on real usage           :active, p9b, after p9a, 5d
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

**Phase 6 — Docs & Schema Alignment (done)**
Make the docs and schema tell the truth about the code:
- p6a: `docs/solution-overview.md`'s entry-format `type:` enum (line 107)
  was in fact still missing `parametric` — the earlier claim that this was
  already done turned out to be wrong on direct inspection during this
  reevaluation. Fixed both there and in the lint sequence-diagram line that
  separately overstated lint's checks (see p6b).
- p6b: AGENT.md and the docs claimed lint catches "contradicting entries" /
  "duplicate slugs with conflicting content" when the code only ever
  detected duplicate slugs. Overstated language was found and softened at
  `memory/AGENT.md:46,55`, `docs/plan.md:45,60`, and
  `docs/solution-overview.md:95` (the last of these was in this file
  itself), plus the `kb.py lint` `--help` string, which literally said
  "fact-check / staleness / contradiction pass". All now describe
  duplicate-slug detection only — no content-level contradiction checker
  exists.
- p6c: `memory/schema/entry.schema.json` was referenced by nothing —
  `kb.py lint` never read it. This was invisible in the wild: dotfiles'
  scaffolded copy reported "lint clean" solely because its two real entries
  happened to already satisfy the narrower checks that existed. Fixed by
  loading the schema in `cmd_lint` and enforcing its `required` fields,
  the `name` kebab-case pattern, and the `type` enum (stdlib `json`, no new
  dependency).

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
schema/CLI.

- p9a (done): scaffolded into `dotfiles` via `scripts/scaffold.sh`, wired
  into its README and `kb-lint.yml` CI, and genuinely dogfooded — two real
  entries exist (`memory/semantic/kb-is-file-based.md`,
  `memory/procedural/distill-session-into-memory.md`), both authored
  2026-07-22, not placeholder scaffold content.
- p9b (in progress): friction found from that real usage so far —
  1. The `entry.schema.json` vs. `kb.py lint` enforcement gap (see p6c)
     was only *discovered* because dotfiles' two real entries passed lint
     cleanly despite the hole — a good example of why dogfooding surfaces
     bugs that synthetic testing doesn't.
  2. dotfiles already has a separate, mature AI-context system under
     `.ai/` (ADRs, an authorization/"Decision Protocol" framework, a
     traceability doc, architecture docs) that conceptually overlaps with
     this KB's taxonomy — e.g. ADRs vs. `memory/semantic|procedural`
     entries, `.ai/memory/AUTHORIZATIONS.md` vs. no "authorization" memory
     type here. dotfiles' own README lists both systems side by side in
     its Repository Structure tree with zero cross-reference between them.
     Unscoped for now; p9b should either add a short cross-reference note
     in both READMEs pointing at each other, or explicitly decide the two
     systems serve different concerns and document *why* they stay
     separate.
  3. Scaffolded copies of `kb.py`/`visualize.py` (dotfiles' included) have
     no update mechanism when the source repo's scripts improve. Confirmed:
     after p6c merged here, the fix had to be manually diffed and re-copied
     into dotfiles (dotfiles PR #14, merged) to take effect there — the
     friction is real, not hypothetical. That PR fixed dotfiles' copy once;
     it did not add any lasting or automated mechanism, so the same gap will
     recur on the next `kb.py`/`visualize.py` change. Still worth a
     documented "how to pick up upstream fixes" note, at minimum, or an
     automated check (e.g. a scheduled workflow diffing scaffolded copies
     against upstream).

Candidate upgrades (deliberately deferred, not required for v1):
- Optional embedding-based retrieval as a pluggable backend behind the same
  `kb.py search` interface, for repos that *do* want infra.
- A lightweight read-only HTML viewer for the Mermaid graph (still no
  server — a static file).
- MCP server wrapper exposing `kb.py` commands as tools, for agents that
  prefer MCP over shelling out.
