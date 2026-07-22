# Agent Memory Knowledge Base

A file-based, infrastructure-free knowledge base built around the [7 types
of agent memory](https://www.marktechpost.com/2026/06/21/the-7-types-of-agent-memory-a-technical-guide-for-ai-engineers/)
(CoALA-derived), following the ingest/wiki/lint maintenance pattern from
[Karpathy's "LLM Wiki" gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).

See [`goal.md`](goal.md) for the original requirements this repo was built from.

## Start here

- **Agent entry point:** [`memory/AGENT.md`](memory/AGENT.md) — read this first if
  you're an agent operating on this knowledge base.
- **Design docs:**
  - [`docs/plan.md`](docs/plan.md) — requirements, research basis, design decisions
  - [`docs/solution-overview.md`](docs/solution-overview.md) — architecture, taxonomy
    mapping, and entry lifecycle (mermaid diagrams)
  - [`docs/roadmap.md`](docs/roadmap.md) — phased delivery plan (mermaid gantt)

## Layout

```
memory/       the knowledge base itself, one folder per memory type
scripts/      kb.py (CLI), visualize.py (mermaid graph generator), scaffold.sh
.github/      CI workflow that lints and re-visualizes the KB on every change
docs/         plan, solution overview, roadmap
```

## CLI quickstart

```
python3 scripts/kb.py list
python3 scripts/kb.py search "<keyword>"
python3 scripts/kb.py new --type semantic "<name>"
python3 scripts/kb.py lint
python3 scripts/visualize.py
```

## Scaffolding into another repo

```
scripts/scaffold.sh /path/to/target-repo [subfolder-name]
```

Copies `memory/`, `scripts/kb.py`, `scripts/visualize.py`, and the CI workflow
into the target repo. Solution- and agent-agnostic — no dependency on this repo
at runtime.
