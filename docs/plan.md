# Plan: File-Based Agent Memory Knowledge Base

## Goal

Build a persistent, file-based knowledge base organized around the 7 types of
agent memory, that:

- is readable and editable by humans (plain markdown + YAML frontmatter)
- scaffolds into any repo as a subfolder, via a script triggerable from a
  pipeline/CI action
- needs no infrastructure (no database, no vector store, no server)
- follows the closest available industry conventions
- exposes a single entry point for an agent to orient itself
- is solution- and agent-agnostic (no framework lock-in, no vendor SDK)
- has an ingestion layer, a visualization layer, and an interaction interface
- supports fact-checking and confidence scoring on stored claims

## Research basis

Two sources anchor the design:

1. **"The 7 Types of Agent Memory"** (MarkTechPost, 2026) — taxonomy used
   for the folder structure:
   - Working (in-context / short-term)
   - Semantic (facts, preferences, domain knowledge)
   - Episodic (records of past events/task runs)
   - Procedural (skills, workflows, how-to knowledge)
   - Retrieval / external memory (file-based substitute for a vector DB)
   - Parametric (baked into model weights — out of scope to store, but
     tracked as an explicit "assumed known" boundary)
   - Prospective (future intentions, scheduled goals)

   This taxonomy traces back to the **CoALA framework**
   (Sumers et al., arXiv:2309.02427), which is the closest thing to an
   industry standard for agent memory classification.

2. **Karpathy's "LLM Wiki" gist** — the operating pattern used for how the
   knowledge base is *maintained*:
   - Raw sources are immutable and never edited.
   - A curated, interlinked markdown layer (the wiki/memory files) is
     incrementally updated as new sources are ingested — knowledge
     compounds instead of being re-derived per query.
   - A schema/config document (this repo's `memory/AGENT.md`) defines
     structure and conventions, analogous to a `CLAUDE.md`/`AGENTS.md`.
   - Periodic "lint" passes catch contradictions, orphaned pages, and
     stale claims — this maps directly onto the fact-checking/confidence
     requirement.

## Design decisions

| Requirement | Decision |
|---|---|
| Human readable/editable | Markdown files, YAML frontmatter, no binary formats |
| Agent/solution-agnostic single entry point | `memory/AGENT.md` — any agent reads this first, regardless of framework |
| No infra | No DB/vector store. "Retrieval memory" is plain markdown + grep/keyword search over frontmatter, not embeddings |
| Industry standard alignment | CoALA memory taxonomy + emerging `AGENTS.md` convention + frontmatter style used by Jekyll/Obsidian/Zettelkasten tooling |
| Ingestion layer | `scripts/kb.py new` scaffolds a typed entry from a template; the agent (not a bespoke model call) does the classification/extraction, keeping the system model-agnostic |
| Visualization layer | `scripts/visualize.py` walks frontmatter `links:` fields and emits a Mermaid graph, colored by memory type and confidence |
| Interaction interface | `scripts/kb.py` CLI: `list`, `search`, `show`, `new`, `lint` |
| Fact-checking / confidence | Every entry has `confidence` (verified / high / medium / low / unverified) + `last_verified` date; `kb.py lint` flags stale or contradicting entries |
| Scaffolding via pipeline/action | `scripts/scaffold.sh` copies the `memory/` + `scripts/` layout into a target repo; `.github/workflows/kb-lint.yml` shows the CI trigger pattern |

## Non-goals (v1)

- No embeddings/vector search (would violate "no infra needed"); grep-based
  retrieval is the deliberate trade-off. Documented as an opt-in upgrade
  path in the roadmap.
- No automatic LLM-driven classification pipeline — ingestion is
  agent-assisted (whichever agent is operating the repo follows
  `memory/AGENT.md`), not a hardcoded call to a specific model API.
- No UI server for visualization — Mermaid diagrams render natively in
  markdown viewers (GitHub, most IDEs, Claude artifacts).
