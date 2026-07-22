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

### Keeping a scaffolded copy in sync

`scaffold.sh` copies files once; it does not link the target repo back to this
one, so fixes made here (e.g. a `kb.py` lint bug) don't propagate
automatically. Pick whichever of these fits the target repo:

- **Add this repo as a remote, then selectively check out updated files:**

  ```bash
  git remote add kb-upstream <this-repo-url>
  git fetch kb-upstream
  git diff HEAD kb-upstream/main -- scripts/kb.py scripts/visualize.py
  git checkout kb-upstream/main -- scripts/kb.py scripts/visualize.py
  ```

- **One-off file copy**, if you don't want a permanent remote:

  ```bash
  curl -fsSL <raw-url>/scripts/kb.py -o scripts/kb.py
  curl -fsSL <raw-url>/scripts/visualize.py -o scripts/visualize.py
  ```

- **Automate it** with a scheduled workflow (e.g.
  [`actions-template-sync`](https://github.com/AndreasAugustin/actions-template-sync))
  that opens a PR whenever `scripts/kb.py` or `scripts/visualize.py` changes
  upstream, if the target repo wants sync without a manual check-in.

Only `scripts/kb.py` and `scripts/visualize.py` are meant to be pulled
verbatim — the `memory/` contents and `.kb-config` are the target repo's own
data and shouldn't be overwritten by a sync.

### Relationship to other AI-context systems

Some repos already have a broader AI-assistant context system (ADRs,
authorization policies, request-to-code traceability, architecture docs —
often under something like `.ai/`). This knowledge base is not a replacement
for that: it covers one narrower concern, an agent's own cross-session
*memory* (facts, procedures, past episodes), organized by the 7-type
taxonomy above. A project-governance system and this KB can and should
coexist — see [dotfiles](https://github.com/jvanheerikhuize/dotfiles)'s
`.ai/` (governance) alongside its scaffolded `memory/` (this KB) for an
example of the split.
