# Agent Memory — Entry Point

Read this file first. It is the single point of entry into this knowledge
base, regardless of which agent or framework is operating on it.

## What this is

A file-based, human-readable/editable memory store organized around the 7
types of agent memory (CoALA-derived taxonomy). No database, no vector
store, no server — just markdown files with YAML frontmatter, plus scripts
in `../scripts/` to search, audit, and visualize them.

## Folder-per-memory-type

| Folder | Memory type | Use it for |
|---|---|---|
| `semantic/` | Semantic | Durable facts, preferences, domain knowledge — true regardless of when learned |
| `episodic/` | Episodic | Records of specific past events/task runs — what happened, what worked, what failed |
| `procedural/` | Procedural | Skills, workflows, how-to playbooks — reusable steps, not one-off facts |
| `working/` | Working | NOT persisted content. Holds only the template used to distill a session into episodic/semantic entries before context is lost |
| `retrieval/` | Retrieval / external | Indexed reference material meant to be keyword-searched (`kb.py search`), the file-based stand-in for a vector store |
| `parametric/` | Parametric | Documentation-only. Records the boundary of what's assumed already known by any capable model, so entries aren't wasted restating it |
| `prospective/` | Prospective | Future intentions, scheduled goals, things to do or check later |

## Adding a memory

1. Classify the information into one of the 7 types above.
2. Run `scripts/kb.py new --type <type> "<name>"` to scaffold an entry from
   the template (see `templates/entry.template.md`).
3. Fill in the body. Set `confidence` honestly (see rubric below).
4. Link related entries via the `links:` frontmatter field.

## Confidence-scoring rubric

| Value | Meaning |
|---|---|
| `verified` | Cross-checked against a primary source or repeated observation |
| `high` | Single reliable source, internally consistent, not yet cross-checked |
| `medium` | Plausible, single weak/indirect source |
| `low` | Speculative or inferred, not directly sourced |
| `unverified` | Just captured, not yet assessed |

Re-run `scripts/kb.py lint` periodically (or via CI, see
`.github/workflows/kb-lint.yml`) — it flags entries whose `last_verified`
is stale, `confidence: unverified` entries older than 30 days, dangling
`links:`, duplicate slugs, and violations of `memory/schema/entry.schema.json`
(missing required fields, malformed `name`, invalid `type`). It does not
detect content-level contradictions between entries — no such checker
exists yet.

## Interacting with the knowledge base

```
scripts/kb.py list [--type TYPE]         # list entries, optionally filtered
scripts/kb.py search "<query>"           # keyword search across all entries
scripts/kb.py show <name>                # print one entry
scripts/kb.py new --type TYPE "<name>"   # scaffold a new entry
scripts/kb.py lint                       # schema, duplicate-slug, dangling-link, and staleness checks
```

## Visualizing the knowledge base

```
scripts/visualize.py    # regenerates memory/_generated/graph.{mmd,md}
```

`graph.mmd` is the raw Mermaid source, for IDEs and tools that read `.mmd`
directly. GitHub does not render standalone `.mmd` files — view
`_generated/graph.md` instead, which wraps the same diagram in a
` ```mermaid ` fence that GitHub (and Claude artifacts) render inline.

## Further reading

- `../docs/plan.md` — why this structure, requirements traceability
- `../docs/solution-overview.md` — architecture diagrams
- `../docs/roadmap.md` — what's built vs. planned
