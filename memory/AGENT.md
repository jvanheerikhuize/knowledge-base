# Agent Memory — Entry Point

Read this file first. It is the single point of entry into this knowledge
base, regardless of which agent or framework is operating on it.

## What this is

A file-based, human-readable/editable memory store organized around the 7
types of agent memory (CoALA-derived taxonomy). No database, no vector
store — just markdown files with YAML frontmatter, plus scripts in
`../scripts/` to search, audit, triage, and edit them.

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
   the template (see `../.kb/templates/entry.template.md`).
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
`links:`, duplicate slugs, and violations of `../.kb/schema/entry.schema.json`
(missing required fields, malformed `name`, invalid `type`). It does not
detect content-level contradictions between entries — no such checker
exists yet.

## Entry status

Confidence says how much an entry is trusted; `last_verified` says how
recently anybody looked. Status collapses both — plus links and due dates —
into one answer per entry: *what is the single next thing to do about it.*
Every entry sits in exactly one status, and if several apply the worst wins.

Run `scripts/kb.py status` for the board, `--legend` for this table, or open
`status.html` on the site.

| Status | What it means | How to change it |
|---|---|---|
| `broken` | A frontmatter date will not parse, so the entry escapes every freshness check | `kb.py set <name> last_verified YYYY-MM-DD` |
| `overdue` | A prospective entry whose `due` date has passed — a reminder that already fired | act on it, then `kb.py set <name> due YYYY-MM-DD` (or `kb.py rm <name>`) |
| `stale` | Not re-checked in over 90 days; may still be true, nobody has looked | re-check against the source, then `kb.py verify <name>` |
| `unverified` | Recorded but never confirmed against a primary source — a claim, not a fact | confirm it, then `kb.py verify <name> --confidence verified` |
| `provisional` | Confidence is `low` or `medium` — believed, but the evidence was indirect | check it directly, then `kb.py verify <name> --confidence verified` |
| `isolated` | Nothing links to it, or it links to nothing; unreachable by following the graph | `kb.py link <other-entry> <name>` |
| `ageing` | Still fresh, but past two-thirds of the way to the staleness cutoff | nothing now; re-verify before the review date |
| `current` | Verified recently, trusted, and connected. Nothing to do | nothing; re-verify by the review date to stay here |

`review_by` is `last_verified` + 90 days — the date an entry falls to `stale`
if left alone. This is what keeps "clean" from quietly meaning "unexamined":
`triage` lists only what is already wrong, `status` accounts for everything.

## Interacting with the knowledge base

```
scripts/kb.py list [--type TYPE]         # list entries, optionally filtered
scripts/kb.py search "<query>"           # keyword search across all entries
scripts/kb.py show <name>                # print one entry
scripts/kb.py new --type TYPE "<name>"   # scaffold a new entry
scripts/kb.py lint                       # schema, duplicate-slug, dangling-link, and staleness checks

scripts/kb.py status [--type T] [--status S] [--legend]   # where every entry stands, and what moves it
scripts/kb.py triage                     # what needs attention, most urgent first
scripts/kb.py verify <name> [--confidence LEVEL]   # stamp last_verified as today
scripts/kb.py set <name> <field> <value> # edit one frontmatter field
scripts/kb.py link <name> <target> [--remove]      # manage links: safely
scripts/kb.py edit <name>                # open the file in $EDITOR
scripts/kb.py rm <name> [--force]        # delete, refusing while still linked
```

Mutations are appended to `../.kb/log.md`, so the history of the store is
readable without reading git.

## Browsing the knowledge base

The whole store is published as a browsable site — index, per-entry pages,
and a link graph colored by memory type:

https://jvanheerikhuize.github.io/knowledge-base/

Build it locally with `scripts/build_site.py`, or run `scripts/serve.py` to
browse and edit it in a browser. Nothing generated is committed.

## Further reading

- `../README.md` — design rationale, architecture diagrams, and layout of the repo
