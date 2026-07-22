# Agent Memory Knowledge Base

[![kb-lint](https://github.com/jvanheerikhuize/knowledge-base/actions/workflows/kb-lint.yml/badge.svg)](https://github.com/jvanheerikhuize/knowledge-base/actions/workflows/kb-lint.yml)

A file-based, infrastructure-free knowledge base built around the [7 types
of agent memory](https://www.marktechpost.com/2026/06/21/the-7-types-of-agent-memory-a-technical-guide-for-ai-engineers/)
(CoALA-derived), following the ingest/wiki/lint maintenance pattern from
[Karpathy's "LLM Wiki" gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).
Plain markdown + a stdlib-only Python CLI — no database, no server, no
dependencies.

## The 7 memory types

| Type | Holds | Example |
|------|-------|---------|
| `semantic` | Facts about the world/project | "the KB is file-based, no infra" |
| `episodic` | Records of specific past events | "on 2026-07-22 we migrated X" |
| `procedural` | How-to knowledge, workflows | "how to distill a session into memory" |
| `working` | Short-lived scratch state | current task context |
| `retrieval` | Pointers to external sources | URLs, docs, dashboards |
| `parametric` | Notes on model-internal knowledge | what the agent knows without lookup |
| `prospective` | Future intentions with a `due` date | "rotate the token before 2026-09-01" |

Every entry is one markdown file with YAML frontmatter (name, type,
description, confidence, dates, links). The current contents are always
visible in the auto-generated
[memory graph](memory/_generated/graph.md) and
[index](memory/_generated/index.md).

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
tests/        stdlib unittest suites for kb.py and visualize.py
.github/      CI workflow that lints and re-visualizes the KB on every change
docs/         plan, solution overview, roadmap
```

## CLI quickstart

```
python3 scripts/kb.py list
python3 scripts/kb.py search "<keyword>"
python3 scripts/kb.py new --type semantic "<name>"
python3 scripts/kb.py new --type prospective "<name>" --due 2026-12-31
python3 scripts/kb.py lint
python3 scripts/visualize.py
```

`kb.py lint` enforces the frontmatter schema, catches duplicate slugs and
dangling links, and warns on stale, unverified, orphaned, or overdue
entries (`--strict` turns warnings fatal; CI runs that weekly).

## Tests

```
python3 -m unittest discover tests
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

## Original goal

<details>
<summary>The requirements this repo was built from</summary>

**Goal:** create a persistent file-based knowledge base around the 7 types
of agent memory.

**Requirements:**

- readable and editable by humans
- scaffolds into a system readable by any agent; the scaffolder can be
  triggered via a pipeline/action
- file based, no infra needed
- closest to current industry standards
- lives in a subfolder of a repository
- has a single point of entry for an agent
- solution & agent agnostic
- needs an ingestion layer
- needs a visualisation layer
- needs an interface to interact with the knowledge base
- fact checking and confidence scoring

**Sources:**

- <https://www.marktechpost.com/2026/06/21/the-7-types-of-agent-memory-a-technical-guide-for-ai-engineers/>
- <https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f>

</details>

## License

[MIT](LICENSE)
